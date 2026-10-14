"""Protected dashboard, control, report and user-management endpoints."""

import base64
import datetime as dt
import json
import logging
import os
import re
import uuid

from boto3.dynamodb.conditions import Attr, Key

from backend.aws_support import body, client, get_item, query_items, response, table
from backend.domain import (
    DEVICES,
    MODES,
    RULES,
    canonical,
    native,
    parse_time,
    report_sql,
    timestamp,
    utcnow,
)
from backend.notifications import subscriptions

log = logging.getLogger(__name__)


class Forbidden(Exception):
    pass


def principal(event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    if claims.get("token_use") != "access" or not claims.get("sub"):
        raise Forbidden("An access token is required")
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        try:
            groups = json.loads(groups)
        except ValueError:
            groups = re.findall(r"\b(?:viewer|operator)\b", groups)
    if not isinstance(groups, list):
        raise Forbidden("Invalid role claims")
    if not {"viewer", "operator"}.intersection(groups):
        raise Forbidden("Viewer or operator role required")
    return {
        "sub": claims["sub"],
        "username": claims.get("username", claims["sub"]),
        "groups": groups,
    }


def operator(user):
    if "operator" not in user["groups"]:
        raise Forbidden("Operator role required")
    # Re-check privileged actions against the current directory so removing a role
    # takes effect even before the caller's ten-minute access token expires.
    result = client("cognito-idp").admin_list_groups_for_user(
        UserPoolId=os.environ["USER_POOL"], Username=user["username"]
    )
    if "operator" not in {group["GroupName"] for group in result["Groups"]}:
        raise Forbidden("Operator role has been revoked")


def device_id(value):
    if value not in DEVICES:
        raise ValueError("Unregistered deviceId")
    return value


def device_view(device):
    state = get_item(table(), device, "STATE") or {}
    last_seen = state.get("lastSeen")
    online = bool(
        last_seen
        and (utcnow() - parse_time(last_seen)).total_seconds()
        < int(os.environ.get("OFFLINE_SECONDS", "60"))
    )
    control = get_item(table("CONTROL_TABLE"), device, "CONTROL") or {
        "requestedMode": "normal",
        "status": "pending",
    }
    if (
        control.get("status") == "pending"
        and control.get("requestedAt")
        and (utcnow() - parse_time(control["requestedAt"])).total_seconds() > 60
    ):
        control = {
            **control,
            "status": "failed",
            "reason": "Simulator acknowledgement timed out; request remains available for reconciliation",
        }
    return {
        "deviceId": device,
        "name": f"Factory {device}",
        "thresholds": {
            rule: {"field": field, "value": threshold} for rule, (field, threshold) in RULES.items()
        },
        "online": online,
        "lastSeen": last_seen,
        "latest": state or None,
        "control": control,
    }


def cursor_encode(key):
    return base64.urlsafe_b64encode(canonical(key).encode()).decode() if key else None


def reading_page(device, params):
    now = utcnow()
    start = parse_time(params.get("from", timestamp(now - dt.timedelta(hours=1))))
    end = parse_time(params.get("to", timestamp(now)))
    if (
        start > end
        or start < now - dt.timedelta(hours=24) - dt.timedelta(seconds=5)
        or end > now + dt.timedelta(seconds=60)
    ):
        raise ValueError("Readings range must be within the last 24 hours")
    limit = int(params.get("limit", "500"))
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be 1-1000")
    kwargs = {}
    if params.get("cursor"):
        key = json.loads(base64.urlsafe_b64decode(params["cursor"]))
        if set(key) != {"pk", "sk"} or key["pk"] != device or not key["sk"].startswith("READING#"):
            raise ValueError("Invalid readings cursor")
        kwargs["ExclusiveStartKey"] = key
    result = table().query(
        KeyConditionExpression=Key("pk").eq(device)
        & Key("sk").between(f"READING#{timestamp(start)}", f"READING#{timestamp(end)}#\uffff"),
        ScanIndexForward=False,
        Limit=limit,
        **kwargs,
    )
    return {
        "readings": result["Items"],
        "nextCursor": cursor_encode(result.get("LastEvaluatedKey")),
    }


def request_control(device, mode, user):
    device_id(device)
    if mode not in MODES:
        raise ValueError("mode must be normal, overheat, vibration, or disconnect")
    target = table("CONTROL_TABLE")
    existing = get_item(target, device, "CONTROL") or {}
    requested = {
        **existing,
        "pk": device,
        "sk": "CONTROL",
        "requestId": uuid.uuid4().hex,
        "requestedMode": mode,
        "requestedBy": user["sub"],
        "requestedAt": timestamp(utcnow()),
        "status": "pending",
    }
    # Unconditional replacement means the last request wins. Simulator ack compares
    # requestId and runId; it can never mark a superseding command as applied.
    target.put_item(Item=native(requested))
    return requested


def start_report(payload, user):
    if set(payload) - {"report", "start", "end", "deviceId"}:
        raise ValueError("Unknown report parameters")
    sql = report_sql(
        payload["report"],
        payload["start"],
        payload["end"],
        payload.get("deviceId"),
        os.environ["GLUE_DATABASE"],
    )
    key = {"pk": f"QUOTA#{utcnow().date()}", "sk": "REPORTS"}
    try:
        table().update_item(
            Key=key,
            UpdateExpression="SET expiresAt = :ttl ADD used :one",
            ConditionExpression=Attr("used").not_exists() | Attr("used").lt(100),
            ExpressionAttributeValues={":ttl": int(utcnow().timestamp()) + 2 * 86400, ":one": 1},
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException as exc:
        raise ValueError("Daily project report limit reached (100)") from exc
    query = client("athena").start_query_execution(
        QueryString=sql,
        WorkGroup=os.environ["ATHENA_WORKGROUP"],
        QueryExecutionContext={"Database": os.environ["GLUE_DATABASE"]},
    )["QueryExecutionId"]
    table().put_item(
        Item={
            "pk": f"REPORT#{query}",
            "sk": "META",
            "owner": user["sub"],
            "parameters": payload,
            "createdAt": timestamp(utcnow()),
            "expiresAt": int(utcnow().timestamp()) + 7 * 86400,
        }
    )
    return {"reportId": query, "status": "QUEUED"}


def report_result(query, user):
    if not re.fullmatch(r"[a-f0-9-]{36}", query):
        raise ValueError("Invalid reportId")
    record = get_item(table(), f"REPORT#{query}", "META")
    if not record or record["owner"] != user["sub"]:
        raise Forbidden("Report is unavailable to this user")
    result = client("athena").get_query_execution(QueryExecutionId=query)["QueryExecution"]
    status = result["Status"]["State"]
    response_data = {
        "reportId": query,
        "status": status,
        "parameters": record["parameters"],
        "bytesScanned": result.get("Statistics", {}).get("DataScannedInBytes", 0),
    }
    if status == "SUCCEEDED":
        rows = client("athena").get_query_results(QueryExecutionId=query, MaxResults=100)[
            "ResultSet"
        ]
        columns = [column["Name"] for column in rows["ResultSetMetadata"]["ColumnInfo"]]
        response_data["rows"] = [
            dict(zip(columns, [cell.get("VarCharValue") for cell in row["Data"]], strict=True))
            for row in rows["Rows"][1:]
        ]
    elif status in ("FAILED", "CANCELLED"):
        response_data["error"] = "Historical query did not complete; consult project query logs"
    return response_data


def manage_users(method, payload, user):
    cognito = client("cognito-idp")
    pool = os.environ["USER_POOL"]
    if method == "GET":
        items = [
            item
            for page in cognito.get_paginator("list_users").paginate(
                UserPoolId=pool, PaginationConfig={"MaxItems": 100}
            )
            for item in page["Users"]
        ]
        return {
            "users": [
                {
                    "username": item["Username"],
                    "enabled": item["Enabled"],
                    "status": item["UserStatus"],
                    "attributes": item["Attributes"],
                    "roles": [
                        g["GroupName"]
                        for g in cognito.admin_list_groups_for_user(
                            UserPoolId=pool, Username=item["Username"]
                        )["Groups"]
                    ],
                }
                for item in items
            ]
        }
    email = payload["email"]
    roles = payload["roles"]
    if (
        not isinstance(email, str)
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or len(email) > 254
    ):
        raise ValueError("A valid email is required")
    if (
        not isinstance(roles, list)
        or not roles
        or len(roles) != len(set(roles))
        or set(roles) - {"viewer", "operator"}
    ):
        raise ValueError("roles must contain viewer and/or operator")
    if email == user["username"] and "operator" not in roles:
        raise ValueError("Operators cannot remove their own operator role")
    if method == "PUT" and "operator" not in roles:
        target_user = cognito.admin_get_user(UserPoolId=pool, Username=email)
        if target_user["Username"] == user["username"]:
            raise ValueError("Operators cannot remove their own operator role")
    if method == "POST":
        # Cognito generates and emails the temporary password; it never enters source.
        cognito.admin_create_user(
            UserPoolId=pool,
            Username=email,
            UserAttributes=[{"Name": "email", "Value": email}],
            DesiredDeliveryMediums=["EMAIL"],
        )
    current = cognito.admin_list_groups_for_user(UserPoolId=pool, Username=email)["Groups"]
    for role in roles:
        cognito.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=role)
    for group in current:
        if group["GroupName"] in ("viewer", "operator") and group["GroupName"] not in roles:
            cognito.admin_remove_user_from_group(
                UserPoolId=pool, Username=email, GroupName=group["GroupName"]
            )
    return {"username": email, "roles": roles}


def handler(event, context):
    try:
        user = principal(event)
        method = event["requestContext"]["http"]["method"]
        path = event.get("rawPath", "").rstrip("/")
        params = event.get("queryStringParameters") or {}
        if path == "/devices" and method == "GET":
            return response(
                200,
                {
                    "devices": [device_view(device) for device in DEVICES],
                    "serverTime": timestamp(utcnow()),
                },
            )
        if match := re.fullmatch(r"/devices/(motor-0[123])(/readings)?", path):
            device = device_id(match[1])
            if method == "GET":
                return response(
                    200, reading_page(device, params) if match[2] else device_view(device)
                )
        if path == "/alerts" and method == "GET":
            devices = [device_id(params["deviceId"])] if params.get("deviceId") else DEVICES
            now = utcnow()
            start = parse_time(params.get("from", timestamp(now - dt.timedelta(days=1))))
            end = parse_time(params.get("to", timestamp(now)))
            if (
                start > end
                or start < now - dt.timedelta(days=30)
                or end > now + dt.timedelta(seconds=60)
            ):
                raise ValueError("Alerts range must be within the last 30 days")
            alerts = []
            for device in devices:
                alerts.extend(
                    query_items(
                        table(),
                        Key("pk").eq(device)
                        & Key("sk").between(
                            f"ALERT#{timestamp(start)}", f"ALERT#{timestamp(end)}#\uffff"
                        ),
                        ScanIndexForward=False,
                        PaginationConfig={"MaxItems": 500},
                    )
                )
            if params.get("state"):
                if params["state"] not in ("active", "resolved"):
                    raise ValueError("state must be active or resolved")
                alerts = [alert for alert in alerts if alert["state"] == params["state"]]
            for alert in alerts:
                intent = get_item(table(), "NOTIFY", alert["alertId"])
                alert["emailStatus"] = (
                    intent.get("delivery", "pending") if intent else "suppressed_replay"
                )
            return response(
                200,
                {
                    "alerts": sorted(alerts, key=lambda a: a["activatedAt"], reverse=True),
                    "subscriptions": subscriptions(),
                },
            )
        if path == "/controls/reset-all" and method == "POST":
            operator(user)
            return response(
                202, {"controls": [request_control(device, "normal", user) for device in DEVICES]}
            )
        if match := re.fullmatch(r"/controls/(motor-0[123])", path):
            if method == "POST":
                operator(user)
                return response(202, request_control(match[1], body(event)["mode"], user))
        if path == "/reports" and method == "POST":
            return response(202, start_report(body(event), user))
        if match := re.fullmatch(r"/reports/([a-f0-9-]{36})", path):
            if method == "GET":
                return response(200, report_result(match[1], user))
        if path == "/users" and method in ("GET", "POST", "PUT"):
            operator(user)
            return response(
                200 if method != "POST" else 201, manage_users(method, body(event), user)
            )
        return response(404, {"error": "Route not found"})
    except Forbidden as exc:
        return response(403, {"error": str(exc)})
    except (ValueError, KeyError, TypeError) as exc:
        return response(400, {"error": str(exc)})
    except Exception:
        log.exception("API failure request=%s", event.get("requestContext", {}).get("requestId"))
        return response(503, {"error": "Service temporarily unavailable"})
