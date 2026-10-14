import datetime as dt
import random
from unittest.mock import patch

import boto3
import pytest

from backend import api
from backend.aws_support import get_item
from backend.domain import DEVICES, report_sql, utcnow
from simulator.main import Gateway, Motor
from tests.conftest import api_event
from tests.test_pipeline import process


def create_directory(monkeypatch):
    from backend.aws_support import client

    cognito = client("cognito-idp")
    pool = cognito.create_user_pool(PoolName="test-directory")["UserPool"]["Id"]
    monkeypatch.setenv("USER_POOL", pool)
    for group in ("viewer", "operator"):
        cognito.create_group(UserPoolId=pool, GroupName=group)
    cognito.admin_create_user(
        UserPoolId=pool,
        Username="test@example.com",
        MessageAction="SUPPRESS",
        UserAttributes=[{"Name": "email", "Value": "test@example.com"}],
    )
    cognito.admin_add_user_to_group(
        UserPoolId=pool, Username="test@example.com", GroupName="operator"
    )
    return cognito, pool


def test_operator_creates_and_assigns_login_user_and_roles(aws, monkeypatch):
    cognito, pool = create_directory(monkeypatch)
    event = api_event(
        "POST", "/users", "operator", {"email": "new@example.com", "roles": ["viewer", "operator"]}
    )
    result = api.handler(event, None)
    assert result["statusCode"] == 201
    assert {
        group["GroupName"]
        for group in cognito.admin_list_groups_for_user(
            UserPoolId=pool, Username="new@example.com"
        )["Groups"]
    } == {"viewer", "operator"}
    result = api.handler(
        api_event("PUT", "/users", "operator", {"email": "new@example.com", "roles": ["viewer"]}),
        None,
    )
    assert result["statusCode"] == 200
    assert [
        group["GroupName"]
        for group in cognito.admin_list_groups_for_user(
            UserPoolId=pool, Username="new@example.com"
        )["Groups"]
    ] == ["viewer"]
    assert api.handler(api_event("GET", "/users", "operator"), None)["statusCode"] == 200


def test_operator_cannot_remove_own_privileged_role(aws, monkeypatch):
    create_directory(monkeypatch)
    result = api.handler(
        api_event("PUT", "/users", "operator", {"email": "test@example.com", "roles": ["viewer"]}),
        None,
    )
    assert result["statusCode"] == 400


def test_invalid_roles_do_not_create_user(aws, monkeypatch):
    cognito, pool = create_directory(monkeypatch)
    result = api.handler(
        api_event("POST", "/users", "operator", {"email": "new@example.com", "roles": ["admin"]}),
        None,
    )
    assert result["statusCode"] == 400
    with pytest.raises(cognito.exceptions.UserNotFoundException):
        cognito.admin_get_user(UserPoolId=pool, Username="new@example.com")


def test_unauthenticated_and_id_tokens_are_rejected(aws):
    event = api_event("GET", "/devices")
    event["requestContext"]["authorizer"] = {}
    assert api.handler(event, None)["statusCode"] == 403
    event = api_event("GET", "/devices")
    event["requestContext"]["authorizer"]["jwt"]["claims"]["token_use"] = "id"
    assert api.handler(event, None)["statusCode"] == 403


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/controls/motor-01", {"mode": "overheat"}),
        ("POST", "/controls/reset-all", {}),
        ("GET", "/users", {}),
        ("POST", "/users", {"email": "test@example.com", "roles": ["operator"]}),
        ("PUT", "/users", {"email": "test@example.com", "roles": ["operator"]}),
    ],
)
def test_viewers_cannot_control_or_manage_users_directly(aws, method, path, payload):
    assert api.handler(api_event(method, path, payload=payload), None)["statusCode"] == 403


def test_role_revocation_is_enforced_even_with_stale_operator_token(aws):
    with patch.object(
        api.client("cognito-idp"), "admin_list_groups_for_user", return_value={"Groups": []}
    ):
        assert (
            api.handler(
                api_event("POST", "/controls/motor-01", "operator", {"mode": "overheat"}), None
            )["statusCode"]
            == 403
        )


def test_control_is_pending_until_ack_and_stale_ack_does_not_supersede(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    user = {"sub": "operator", "username": "operator@example.com"}
    first = api.request_control("motor-01", "overheat", user)
    assert first["status"] == "pending"
    assert gateway.modes["motor-01"] == "normal"
    second = api.request_control("motor-01", "vibration", user)
    assert not gateway.apply(first)
    assert get_item(aws["controls"], "motor-01", "CONTROL")["requestId"] == second["requestId"]
    assert gateway.apply(second)
    assert gateway.modes["motor-01"] == "vibration"
    assert gateway.modes["motor-02"] == "normal"
    assert api.device_view("motor-01")["control"]["status"] == "applied"


def test_disconnect_silences_only_one_motor_and_remote_reset_resumes(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    user = {"sub": "operator"}
    assert gateway.apply(api.request_control("motor-02", "disconnect", user))
    assert {r["deviceId"] for r in gateway.readings()} == {"motor-01", "motor-03"}
    assert gateway.apply(api.request_control("motor-02", "normal", user))
    assert {r["deviceId"] for r in gateway.readings()} == set(DEVICES)


def test_new_simulator_run_resets_stale_faults_and_old_run_ack_is_rejected(aws):
    session = boto3.Session(region_name="ap-southeast-2")
    first = Gateway(aws["controls"], session)
    first.initialize()
    old = api.request_control("motor-01", "overheat", {"sub": "operator"})
    first.apply(old)
    second = Gateway(aws["controls"], session)
    second.initialize()
    assert all(mode == "normal" for mode in second.modes.values())
    assert not first.apply(old)
    assert get_item(aws["controls"], "motor-01", "CONTROL")["runId"] == second.run_id


def test_fault_ramps_and_normal_recovery_fit_demo_timing():
    motor = Motor("motor-01", random.Random(42))
    normals = [motor.sample("normal", "run") for _ in range(50)]
    assert all(r["temperatureC"] < 75 and r["vibrationMmS"] < 4.5 for r in normals)
    hot = [motor.sample("overheat", "run") for _ in range(3)]
    assert all(r["temperatureC"] > 75 for r in hot)
    resets = [motor.sample("normal", "run") for _ in range(3)]
    assert all(r["temperatureC"] < 75 for r in resets)
    assert abs(resets[-1]["temperatureC"] - 52) < 2
    vibration = [motor.sample("vibration", "run") for _ in range(3)]
    assert all(r["vibrationMmS"] > 4.5 for r in vibration)


def test_stopped_reporting_remains_online_and_disconnected_becomes_offline(aws, reading):
    process([reading(operatingState="stopped", powerWatts=0)])
    view = api.device_view("motor-01")
    assert view["online"] and view["latest"]["operatingState"] == "stopped"
    with patch("backend.api.utcnow", return_value=utcnow() + dt.timedelta(seconds=61)):
        assert not api.device_view("motor-01")["online"]


def test_control_timeout_display_is_failed_without_false_ack(aws):
    api.request_control("motor-01", "overheat", {"sub": "operator"})
    with patch("backend.api.utcnow", return_value=utcnow() + dt.timedelta(seconds=61)):
        assert api.device_view("motor-01")["control"]["status"] == "failed"
    assert get_item(aws["controls"], "motor-01", "CONTROL")["status"] == "pending"


def test_reading_cursor_cannot_read_another_partition(aws):
    cursor = api.cursor_encode({"pk": "NOTIFY", "sk": "META"})
    assert (
        api.handler(
            api_event("GET", "/devices/motor-01/readings", params={"cursor": cursor}), None
        )["statusCode"]
        == 400
    )


def test_report_ownership_prevents_cross_user_result_access(aws, monkeypatch):
    query = "01234567-89ab-cdef-0123-456789abcdef"
    aws["data"].put_item(Item={"pk": f"REPORT#{query}", "sk": "META", "owner": "different-user"})
    with patch.object(api.client("athena"), "get_query_execution") as get:
        result = api.handler(api_event("GET", f"/reports/{query}"), None)
        assert result["statusCode"] == 403
        get.assert_not_called()


@pytest.mark.parametrize("report", ["temperature", "vibration", "power"])
def test_predefined_report_sql_deduplicates_and_bounds_partitions(report):
    today = str(utcnow().date())
    sql = report_sql(report, today, today, "motor-01", "ccproj")
    assert "PARTITION BY eventid" in sql and "occurrence = 1" in sql
    assert f"day BETWEEN '{today}' AND '{today}'" in sql
    assert "deviceid = 'motor-01'" in sql


@pytest.mark.parametrize(
    "params",
    [
        ("arbitrary SQL", 0, 0, None),
        ("temperature", 40, 0, None),
        ("temperature", 9, 0, None),
        ("temperature", 0, -1, None),
        ("temperature", 0, 0, "motor-01'; DROP TABLE telemetry"),
    ],
)
def test_reports_reject_sql_injection_and_unbounded_dates(params):
    report, start_offset, end_offset, device = params
    today = utcnow().date()
    with pytest.raises(ValueError):
        report_sql(
            report,
            str(today - dt.timedelta(days=start_offset)),
            str(today - dt.timedelta(days=end_offset)),
            device,
            "ccproj",
        )


def test_daily_report_quota_is_enforced_before_athena(aws):
    today = str(utcnow().date())
    aws["data"].put_item(Item={"pk": f"QUOTA#{today}", "sk": "REPORTS", "used": 100})
    with patch.object(api.client("athena"), "start_query_execution") as start:
        with pytest.raises(ValueError, match="limit"):
            api.start_report(
                {"report": "temperature", "start": today, "end": today}, {"sub": "user"}
            )
        start.assert_not_called()
