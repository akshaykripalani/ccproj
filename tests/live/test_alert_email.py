"""Capture one real equipment notification while the confirmed email also receives it."""

import json
import secrets

import pytest

from scripts.aws_cli import call
from tests.live.conftest import PROJECT, wait_for

pytestmark = pytest.mark.live


def test_readable_email_from_real_ec2_fault_and_scheduled_notifier(live):
    initial = live.api("GET", "/devices").json()["devices"]
    assert all(
        d["online"]
        and d["control"].get("appliedMode") == "normal"
        and not any(r["active"] for r in d["latest"]["rules"].values())
        for d in initial
    ), "Start this notification exercise with all shared motors healthy"
    topic = live.platform["AlertTopicArn"]
    queue = call(
        [
            "sqs",
            "create-queue",
            "--queue-name",
            "ccproj-email-capture-" + secrets.token_hex(6),
            "--attributes",
            json.dumps({"SqsManagedSseEnabled": "true", "MessageRetentionPeriod": "300"}),
        ],
        "Create disposable encrypted capture queue for email publication verification",
    )["QueueUrl"]
    subscription = None
    changed = False
    try:
        arn = call(
            ["sqs", "get-queue-attributes", "--queue-url", queue, "--attribute-names", "QueueArn"],
            "Read disposable notification capture queue ARN",
        )["Attributes"]["QueueArn"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "sns.amazonaws.com"},
                    "Action": "sqs:SendMessage",
                    "Resource": arn,
                    "Condition": {
                        "ArnEquals": {"aws:SourceArn": topic},
                        "StringEquals": {"aws:SourceAccount": "039379078306"},
                    },
                },
                {
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "sqs:*",
                    "Resource": arn,
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                },
            ],
        }
        call(
            [
                "sqs",
                "set-queue-attributes",
                "--queue-url",
                queue,
                "--attributes",
                json.dumps({"Policy": json.dumps(policy)}),
            ],
            "Allow only the existing project SNS topic to publish to the disposable capture queue",
        )
        subscription = call(
            [
                "sns",
                "subscribe",
                "--topic-arn",
                topic,
                "--protocol",
                "sqs",
                "--notification-endpoint",
                arn,
                "--return-subscription-arn",
            ],
            "Capture actual notifier subject and body through a temporary SNS subscription",
        )["SubscriptionArn"]
        changed = True
        assert live.api("POST", "/controls/motor-01", {"mode": "overheat"}).status_code == 202
        wait_for(lambda: live.state()["latest"]["rules"]["temperature"]["active"], timeout=100)
        alert_id = live.state()["latest"]["rules"]["temperature"]["alertId"]

        def capture():
            messages = call(
                [
                    "sqs",
                    "receive-message",
                    "--queue-url",
                    queue,
                    "--wait-time-seconds",
                    "10",
                    "--max-number-of-messages",
                    "10",
                ],
                "Wait for the scheduled notifier's real readable fault publication",
            ).get("Messages", [])
            for message in messages:
                envelope = json.loads(message["Body"])
                if envelope.get("Subject") == "Forge alert: Motor 01 over temperature":
                    return envelope
            return None

        envelope = wait_for(capture, timeout=150)
        assert envelope["TopicArn"] == topic
        body = envelope["Message"]
        for expected in (
            "Motor 01 is over its temperature limit.",
            "Temperature:",
            "Detected:",
            " UTC",
            "Vibration:",
            "Power:",
            live.platform["DashboardUrl"] + "/#/devices/motor-01",
        ):
            assert expected in body
        assert "{" not in body and "eventId" not in body
        assert "Operating state:" not in body and "Limit:" not in body
        assert "consecutive readings" not in body and "Operators can" not in body

        def accepted():
            record = call(
                [
                    "dynamodb",
                    "get-item",
                    "--table-name",
                    live.platform["DataTable"],
                    "--consistent-read",
                    "--key",
                    json.dumps({"pk": {"S": "NOTIFY"}, "sk": {"S": alert_id}}),
                ],
                "Verify captured SNS message ID matches the persisted fault notification",
            ).get("Item", {})
            return (
                record if record.get("snsMessageId", {}).get("S") == envelope["MessageId"] else None
            )

        intent = wait_for(accepted, timeout=30)
        assert intent["delivery"]["S"] == "sns_accepted" and "workStatus" not in intent
        response = PROJECT / ".runtime" / "readable-email-retry.json"
        result = call(
            [
                "lambda",
                "invoke",
                "--function-name",
                live.platform["NotifierFunction"],
                "--cli-binary-format",
                "raw-in-base64-out",
                "--payload",
                "{}",
                str(response),
            ],
            "Verify completed readable notification is not republished on retry",
        )
        assert "FunctionError" not in result
        assert json.loads(response.read_text())["published"] == 0
        evidence = {
            "subject": envelope["Subject"],
            "message": body,
            "snsMessageId": envelope["MessageId"],
            "publishedAt": envelope["Timestamp"],
            "alertId": alert_id,
            "delivery": "sns_accepted",
            "retryPublished": 0,
            "proof": "Actual SNS publication captured via disposable SQS; inbox receipt is not asserted.",
        }
        (PROJECT / "docs" / "readable-email-live.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    finally:
        try:
            if changed:
                assert live.api("POST", "/controls/motor-01", {"mode": "normal"}).status_code == 202
                wait_for(
                    lambda: (
                        live.state()["control"].get("appliedMode") == "normal"
                        and not live.state()["latest"]["rules"]["temperature"]["active"]
                    ),
                    timeout=110,
                )
        finally:
            try:
                if subscription and subscription != "PendingConfirmation":
                    call(
                        ["sns", "unsubscribe", "--subscription-arn", subscription],
                        "Remove only the temporary capture subscription",
                    )
            finally:
                call(
                    ["sqs", "delete-queue", "--queue-url", queue],
                    "Remove only the disposable notification capture queue",
                )
