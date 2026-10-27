"""Compact learned-model inference and bounded maintenance decisions."""

import json
import logging
import os
import uuid
from functools import lru_cache

from boto3.dynamodb.conditions import Attr

from backend.aws_support import client, get_item, table
from backend.domain import DEVICES, native, parse_time, timestamp, utcnow
from backend.features import features, score

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_model():
    response = client("s3").get_object(
        Bucket=os.environ["MODEL_BUCKET"], Key=os.environ["MODEL_KEY"]
    )
    model = json.loads(response["Body"].read())
    if model["version"] != os.environ["MODEL_VERSION"]:
        raise ValueError("Model artifact does not match configured release")
    return model


def record(device, action, at, identity, **details):
    try:
        table().put_item(
            Item=native(
                {
                    "pk": device,
                    "sk": f"MAINT#{at}#{identity}",
                    "deviceId": device,
                    "action": action,
                    "at": at,
                    "expiresAt": int(parse_time(at).timestamp()) + 30 * 86400,
                    **details,
                }
            ),
            ConditionExpression=Attr("pk").not_exists(),
        )
    except client("dynamodb").exceptions.ConditionalCheckFailedException:
        pass  # Stable event identity: retries preserve the original record and expiry.


def maintenance(device, state, control, now):
    active = {key: value for key, value in state.get("rules", {}).items() if value.get("active")}
    if control.get("maintenanceAction") == "Restarted automatically":
        record(device, "Restarted automatically", control["maintenanceAt"], control["requestId"])
    # The control poller can acknowledge a repair before its first new telemetry batch.
    # Do not use pre-command faults to undo that repair or request another cooldown.
    if (
        state.get("observedAt")
        and control.get("appliedAt")
        and parse_time(state["observedAt"]) < parse_time(control["appliedAt"])
    ):
        return
    if (
        not active
        and state.get("operatingState") == "running"
        and control.get("status") == "applied"
        and control.get("requestedMode") in ("normal", "repair")
        and control.get("maintenanceAction") == "Repair needed"
    ):
        try:
            table("CONTROL_TABLE").update_item(
                Key={"pk": device, "sk": "CONTROL"},
                ConditionExpression=Attr("requestId").eq(control["requestId"])
                & Attr("maintenanceEpisode").eq(control["maintenanceEpisode"]),
                UpdateExpression="REMOVE maintenanceAction, maintenanceAt, maintenanceEpisode",
            )
        except client("dynamodb").exceptions.ConditionalCheckFailedException:
            pass  # A newer operator command or fault episode owns the current label.
        return
    if not active or control.get("status") != "applied":
        return
    rule = "vibration" if "vibration" in active else "temperature"
    episode = active[rule]["alertId"]
    if control.get("maintenanceEpisode") == episode:
        if control.get("maintenanceAction") == "Repair needed":
            return
        if rule == "temperature" and control.get("requestedMode") == "cooldown":
            elapsed = (now - parse_time(control["requestedAt"])).total_seconds()
            if (
                elapsed >= max(120, 600 / int(state.get("simulationSpeed", 1)))
                and float(state["temperatureC"]) > 75
            ):
                table("CONTROL_TABLE").update_item(
                    Key={"pk": device, "sk": "CONTROL"},
                    ConditionExpression=Attr("requestId").eq(control["requestId"]),
                    UpdateExpression="SET maintenanceAction = :action",
                    ExpressionAttributeValues={":action": "Repair needed"},
                )
                record(
                    device,
                    "Repair needed",
                    timestamp(now),
                    "persistent-" + episode,
                    reason="Overheating persisted during cooldown; automatic retry suppressed",
                )
        return
    if control.get("requestedMode") in ("normal", "overheat", "vibration", "repair"):
        action = "Repair needed" if rule == "vibration" else "Cooling down"
        updated = {
            **control,
            "maintenanceAction": action,
            "maintenanceAt": timestamp(now),
            "maintenanceEpisode": episode,
        }
        if rule == "temperature":
            updated.update(
                requestId=uuid.uuid4().hex,
                requestedMode="cooldown",
                requestedAt=timestamp(now),
                requestedBy="automation",
                status="pending",
            )
        try:
            table("CONTROL_TABLE").put_item(
                Item=native(updated), ConditionExpression=Attr("requestId").eq(control["requestId"])
            )
        except client("dynamodb").exceptions.ConditionalCheckFailedException:
            return
        record(
            device,
            action,
            timestamp(now),
            episode,
            reason="Mechanical inspection required"
            if rule == "vibration"
            else "Transient thermal recovery: stop, cool and restart",
        )


def predict_device(device, model):
    state = get_item(table(), device, "STATE")
    control = get_item(table("CONTROL_TABLE"), device, "CONTROL") or {}
    now = utcnow()
    if not state or (now - parse_time(state["lastSeen"])).total_seconds() > 60:
        return {"deviceId": device, "status": "offline"}
    window = state.get("featureWindow", [])
    if len(window) < 2:
        return {"deviceId": device, "status": "warming_up"}
    risk, fault = score(model, features(window, device))
    has_fault = any(rule.get("active") for rule in state.get("rules", {}).values())
    warning = (
        risk >= model["riskThreshold"]
        and not has_fault
        and state.get("operatingState") == "running"
    )
    prediction = {
        "pk": device,
        "sk": "PREDICTION",
        "modelVersion": model["version"],
        "riskScore": round(risk, 4),
        "faultType": fault,
        "horizonMinutes": 5,
        "warning": warning,
        "at": timestamp(now),
        "sourceObservedAt": state["observedAt"],
        "simulationSpeed": int(state.get("simulationSpeed", 1)),
    }
    previous = get_item(table(), device, "PREDICTION") or {}
    # Also run on duplicate scoring attempts so a retry finishes interrupted maintenance.
    maintenance(device, state, control, now)
    try:
        table().put_item(
            Item=native(prediction),
            ConditionExpression=Attr("sourceObservedAt").not_exists()
            | Attr("sourceObservedAt").lt(state["observedAt"]),
        )
    except client("dynamodb").exceptions.ConditionalCheckFailedException:
        return {"deviceId": device, "status": "already_scored"}
    if warning and not previous.get("warning"):
        record(
            device,
            "Fault predicted",
            prediction["at"],
            state["eventId"],
            faultType=fault,
            modelVersion=model["version"],
            riskScore=prediction["riskScore"],
            sourceObservedAt=state["observedAt"],
        )
    return {
        "deviceId": device,
        "status": "warning" if warning else "scored",
        "riskScore": prediction["riskScore"],
    }


def handler(event, context):
    model = load_model()
    results, failures = [], []
    for device in DEVICES:
        try:
            results.append(predict_device(device, model))
        except Exception:
            log.exception("Prediction failed device=%s", device)
            failures.append(device)
    if failures:
        raise RuntimeError("Prediction failed for " + ", ".join(failures))
    return {"modelVersion": model["version"], "results": results}
