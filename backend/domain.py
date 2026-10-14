"""Telemetry validation and deterministic equipment rules, independent of AWS."""

import datetime as dt
import hashlib
import json
import math
import re
from decimal import Decimal

DEVICES = ("motor-01", "motor-02", "motor-03")
MODES = ("normal", "overheat", "vibration", "disconnect")
RULES = {"temperature": ("temperatureC", 75), "vibration": ("vibrationMmS", 4.5)}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def timestamp(value):
    return (
        value.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("observedAt must be an ISO-8601 UTC string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observedAt must be an ISO-8601 UTC string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("observedAt must include UTC timezone")
    return parsed


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda x: float(x) if isinstance(x, Decimal) else str(x),
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def native(value):
    """Convert JSON floats to Decimal before DynamoDB resource serialization."""
    return json.loads(canonical(value), parse_float=Decimal)


def validate_reading(reading, now=None):
    now = now or utcnow()
    if not isinstance(reading, dict):
        raise ValueError("Each reading must be an object")
    required = {
        "schemaVersion",
        "eventId",
        "deviceId",
        "observedAt",
        "temperatureC",
        "vibrationMmS",
        "powerWatts",
        "operatingState",
    }
    if set(reading) != required:
        raise ValueError("Reading must contain exactly the documented telemetry fields")
    if type(reading["schemaVersion"]) is not int or reading["schemaVersion"] != 1:
        raise ValueError("schemaVersion must be 1")
    if reading["deviceId"] not in DEVICES:
        raise ValueError("Unregistered deviceId")
    if not isinstance(reading["eventId"], str) or not re.fullmatch(
        r"[A-Za-z0-9:_.-]{1,160}", reading["eventId"]
    ):
        raise ValueError("eventId must be 1-160 safe identifier characters")
    observed = parse_time(reading["observedAt"])
    if observed > now + dt.timedelta(seconds=60) or observed < now - dt.timedelta(hours=24):
        raise ValueError(
            "observedAt must be within the last 24 hours, allowing 60 seconds clock skew"
        )
    for field, lower, upper in (
        ("temperatureC", -40, 200),
        ("vibrationMmS", 0, 100),
        ("powerWatts", 0, 100000),
    ):
        value = reading[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, Decimal))
            or not math.isfinite(float(value))
            or not lower <= value <= upper
        ):
            raise ValueError(f"{field} must be a finite number between {lower} and {upper}")
    if reading["operatingState"] not in ("running", "stopped"):
        raise ValueError("operatingState must be running or stopped")
    return {**reading, "observedAt": timestamp(observed)}


def validate_batch(body, now=None):
    if not isinstance(body, dict) or set(body) != {"readings"}:
        raise ValueError("Body must contain readings only")
    values = body["readings"]
    if not isinstance(values, list) or not 1 <= len(values) <= 30:
        raise ValueError("readings must contain 1-30 readings")
    result = [validate_reading(value, now) for value in values]
    if len({r["eventId"] for r in result}) != len(result):
        raise ValueError("Duplicate eventId within one batch")
    return result


def evolve(previous, reading, received_at):
    """Only newer measurements advance consecutive-reading rules; receipt updates liveness."""
    state = dict(previous or {})
    state["lastSeen"] = max(state.get("lastSeen", received_at), received_at)
    changes = []
    if state.get("observedAt", "") >= reading["observedAt"]:
        return state, changes
    state.update(reading)
    rules = {key: dict(value) for key, value in state.get("rules", {}).items()}
    for rule, (field, threshold) in RULES.items():
        status = rules.get(rule, {"active": False, "above": 0, "healthy": 0})
        breached = float(reading[field]) > threshold
        status["above"] = int(status.get("above", 0)) + 1 if breached else 0
        status["healthy"] = 0 if breached else int(status.get("healthy", 0)) + 1
        status["above"] = min(status["above"], 3)
        status["healthy"] = min(status["healthy"], 3)
        if not status["active"] and status["above"] >= 3:
            status.update(
                active=True, alertId=f"{reading['observedAt']}#{rule}#{reading['eventId']}"
            )
            changes.append({"kind": "activated", "rule": rule, "alertId": status["alertId"]})
        elif status["active"] and status["healthy"] >= 3:
            status["active"] = False
            changes.append({"kind": "resolved", "rule": rule, "alertId": status["alertId"]})
        rules[rule] = status
    state["rules"] = rules
    return state, changes


def report_sql(report, start, end, device, database):
    """Bounded predefined SQL; identifiers and values never accept arbitrary SQL."""
    start_day, end_day = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    today = utcnow().date()
    if (
        start_day > end_day
        or end_day > today
        or start_day < today - dt.timedelta(days=29)
        or (end_day - start_day).days > 6
    ):
        raise ValueError("Report date range must be 1-7 days within the last 30 days")
    if device is not None and device not in DEVICES:
        raise ValueError("Unregistered deviceId")
    expressions = {
        "temperature": "avg(temperaturec) AS average_temperature_c, max(temperaturec) AS maximum_temperature_c, count(*) AS reading_count",
        "vibration": "sum(CASE WHEN vibrationmms > 4.5 THEN 1 ELSE 0 END) AS breached_readings",
        "power": "avg(CASE WHEN operatingstate = 'running' THEN powerwatts END) AS average_running_power_watts, count(CASE WHEN operatingstate = 'running' THEN 1 END) AS running_reading_count",
    }
    if report not in expressions:
        raise ValueError("report must be temperature, vibration, or power")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,100}", database):
        raise ValueError("Invalid configured database")
    predicate = f"AND deviceid = '{device}'" if device else ""
    # Archive retries and resend envelopes may contain the same event: reports deduplicate.
    return f"""WITH unique_events AS (
      SELECT *, row_number() OVER (PARTITION BY eventid ORDER BY receivedat) AS occurrence
      FROM {database}.telemetry WHERE day BETWEEN '{start}' AND '{end}' {predicate}
    ) SELECT deviceid, day, {expressions[report]} FROM unique_events
      WHERE occurrence = 1 GROUP BY deviceid, day ORDER BY day, deviceid"""
