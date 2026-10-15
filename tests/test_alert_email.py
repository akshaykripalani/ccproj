from decimal import Decimal
from unittest.mock import patch

import pytest
from boto3.dynamodb.conditions import Key

from backend import notifications
from backend.alert_email import render_email
from backend.aws_support import client, query_items
from backend.domain import parse_time
from tests.test_pipeline import process


@pytest.mark.parametrize(
    "rule,overrides,subject,measurement,limit,other",
    [
        (
            "temperature",
            {"temperature": Decimal("81.25")},
            "Forge alert: Motor 02 over temperature",
            "Temperature: 81.25 °C",
            "Limit: 75 °C",
            "Vibration: 1.5 mm/s",
        ),
        (
            "vibration",
            {"vibration": Decimal("4.5000001")},
            "Forge alert: Motor 02 high vibration",
            "Vibration: 4.5000001 mm/s",
            "Limit: 4.5 mm/s",
            "Temperature: 52 °C",
        ),
    ],
)
def test_fault_pipeline_publishes_readable_email_once(
    aws, reading, rule, overrides, subject, measurement, limit, other
):
    for sequence in (1, 2, 3):
        assert process([reading(sequence, device="motor-02", **overrides)]) == {
            "batchItemFailures": []
        }
    intent = query_items(aws["data"], Key("pk").eq("NOTIFY"))[0]
    assert intent["rule"] == rule
    with (
        patch("backend.notifications.subscriptions", return_value={"confirmed": 1, "pending": 0}),
        patch.object(
            client("sns"), "publish", return_value={"MessageId": "readable-alert"}
        ) as publish,
    ):
        assert notifications.handler({}, None)["published"] == 1
        assert notifications.handler({}, None)["published"] == 0
    publish.assert_called_once()
    message = publish.call_args.kwargs
    assert message["TopicArn"] == aws["topic"]
    assert message["Subject"] == subject
    assert len(subject) < 100 and "\n" not in subject
    body = message["Message"]
    detected = parse_time(intent["reading"]["observedAt"]).strftime("%d %b %Y, %H:%M:%S UTC")
    for expected in (
        measurement,
        limit,
        other,
        "Power: 420 W",
        "Operating state: Running",
        f"Detected: {detected}",
        "3 consecutive readings above the limit",
        "https://dashboard.example.test/#/devices/motor-02",
        "Operators can use Reset",
        "Check Forge for the current state",
    ):
        assert expected in body
    assert "{" not in body and "eventId" not in body and intent["sk"] not in body
    saved = query_items(aws["data"], Key("pk").eq("NOTIFY"))[0]
    assert saved["delivery"] == "sns_accepted" and saved["snsMessageId"] == "readable-alert"
    assert "workStatus" not in saved


def test_delayed_email_uses_detection_time_and_equipment_link(reading):
    intent = {
        "deviceId": "motor-03",
        "rule": "temperature",
        "reading": reading(temperature=81, observed="2026-10-14T10:00:00.000Z"),
    }
    body = render_email(intent, "https://dashboard.example.test/")["Message"]
    assert "Detected: 14 Oct 2026, 10:00:00 UTC" in body
    assert "https://dashboard.example.test/#/devices/motor-03" in body
