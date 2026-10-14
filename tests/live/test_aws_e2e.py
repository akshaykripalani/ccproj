import datetime as dt
import secrets
import time

import pytest
import requests

from backend.domain import canonical, digest, timestamp, utcnow
from scripts.aws_cli import call, run
from tests.live.conftest import wait_for

pytestmark = pytest.mark.live


def measurement(device="motor-01", observed=None, temperature=52):
    return {
        "schemaVersion": 1,
        "eventId": "live-test:" + secrets.token_hex(12),
        "deviceId": device,
        "observedAt": observed or timestamp(utcnow()),
        "temperatureC": temperature,
        "vibrationMmS": 1.5,
        "powerWatts": 420,
        "operatingState": "running",
    }


def test_real_authentication_roles_and_direct_api_rejections(live):
    assert live.api("GET", "/devices", role=None).status_code in (401, 403)
    assert live.api("GET", "/devices", role="viewer").status_code == 200
    assert (
        live.api("POST", "/controls/motor-01", {"mode": "overheat"}, role="viewer").status_code
        == 403
    )
    assert live.api("GET", "/users", role="viewer").status_code == 403
    assert live.api("GET", "/users").status_code == 200
    token = live.token("operator")["IdToken"]
    result = requests.get(
        live.platform["ApiUrl"] + "/devices",
        headers={"Authorization": "Bearer " + token},
        timeout=20,
    )
    assert result.status_code in (401, 403)
    assert requests.post(
        live.platform["ApiUrl"] + "/telemetry", json={"readings": [measurement()]}, timeout=20
    ).status_code in (401, 403)


def test_ec2_normal_operation_and_controls_fault_recovery(live):
    assert live.api("POST", "/controls/reset-all", {}).status_code == 202
    wait_for(
        lambda: all(
            live.state(device)["control"].get("appliedMode") == "normal"
            for device in ("motor-01", "motor-02", "motor-03")
        ),
        timeout=60,
    )
    wait_for(
        lambda: all(
            live.state(device)["online"] for device in ("motor-01", "motor-02", "motor-03")
        ),
        timeout=60,
    )
    try:
        for mode, rule in (("overheat", "temperature"), ("vibration", "vibration")):
            result = live.api("POST", "/controls/motor-01", {"mode": mode})
            assert result.status_code == 202 and result.json()["status"] == "pending"
            request_id = result.json()["requestId"]
            wait_for(
                lambda request_id=request_id: (
                    (control := live.state()["control"]).get("requestId") == request_id
                    and control.get("status") == "applied"
                ),
                timeout=30,
            )
            wait_for(lambda rule=rule: live.state()["latest"]["rules"][rule]["active"], timeout=75)
            assert not live.state("motor-02")["latest"]["rules"][rule]["active"]
            result = live.api("GET", "/alerts", params={"deviceId": "motor-01", "state": "active"})
            assert result.status_code == 200 and any(
                alert["rule"] == rule for alert in result.json()["alerts"]
            )
            assert live.api("POST", "/controls/motor-01", {"mode": "normal"}).status_code == 202
            wait_for(
                lambda rule=rule: not live.state()["latest"]["rules"][rule]["active"], timeout=90
            )
        assert live.api("POST", "/controls/motor-02", {"mode": "disconnect"}).status_code == 202
        wait_for(lambda: not live.state("motor-02")["online"], timeout=100)
        assert live.state("motor-01")["online"] and live.state("motor-03")["online"]
        assert live.api("POST", "/controls/motor-02", {"mode": "normal"}).status_code == 202
        wait_for(lambda: live.state("motor-02")["online"], timeout=40)
    finally:
        assert live.api("POST", "/controls/reset-all", {}).status_code == 202


def test_real_pipeline_deduplication_ordering_and_archive(paused_simulator, record_property):
    live = paused_simulator
    newer = measurement()
    sent_at = time.monotonic()
    assert live.send([newer])[0] == 202
    wait_for(lambda: live.state()["latest"]["eventId"] == newer["eventId"], timeout=60)
    assert time.monotonic() - sent_at < 30, "PRD normal-latency target exceeded"
    record_property("telemetry_latency_seconds", round(time.monotonic() - sent_at, 3))
    assert live.send([newer])[0] == 202
    older = measurement(observed=timestamp(utcnow() - dt.timedelta(minutes=2)), temperature=99)
    assert live.send([older])[0] == 202
    wait_for(
        lambda: {newer["eventId"], older["eventId"]}.issubset(
            {r["eventId"] for r in live.api("GET", "/devices/motor-01/readings").json()["readings"]}
        )
    )
    envelope = canonical(
        {"readings": [newer], "batchId": digest([newer]), "receivedAt": timestamp(utcnow())}
    )
    call(
        [
            "sqs",
            "send-message",
            "--queue-url",
            live.platform["QueueUrl"],
            "--message-body",
            envelope,
            "--message-group-id",
            "factory",
            "--message-deduplication-id",
            "forced-retry-" + secrets.token_hex(8),
        ],
        "Exercise DynamoDB deduplication independently of SQS's five-minute dedup window",
    )
    wait_for(
        lambda: (
            int(
                call(
                    [
                        "sqs",
                        "get-queue-attributes",
                        "--queue-url",
                        live.platform["QueueUrl"],
                        "--attribute-names",
                        "ApproximateNumberOfMessages",
                        "ApproximateNumberOfMessagesNotVisible",
                    ],
                    "Wait for forced duplicate processing",
                )["Attributes"]["ApproximateNumberOfMessagesNotVisible"]
            )
            == 0
        )
    )
    assert live.state()["latest"]["eventId"] == newer["eventId"]
    readings = live.api("GET", "/devices/motor-01/readings").json()["readings"]
    assert sum(r["eventId"] == newer["eventId"] for r in readings) == 1
    objects = call(
        [
            "s3api",
            "list-objects-v2",
            "--bucket",
            live.platform["ArchiveBucket"],
            "--prefix",
            "telemetry/day=" + utcnow().date().isoformat() + "/",
        ],
        "Verify real archive objects",
    )["Contents"]
    assert objects


def test_processing_interruption_buffers_then_catches_up(paused_simulator):
    live = paused_simulator
    mapping = live.platform["ProcessingMapping"]
    value = measurement()
    run(
        ["lambda", "update-event-source-mapping", "--uuid", mapping, "--no-enabled"],
        "Live E2E: pause processing mapping",
    )
    try:
        wait_for(
            lambda: (
                call(
                    ["lambda", "get-event-source-mapping", "--uuid", mapping],
                    "Check paused processing state",
                )["State"]
                == "Disabled"
            ),
            timeout=90,
        )
        # Disabling the mapping does not cancel an already issued SQS long poll.
        # Allow that poll and any bounded invocation to finish before injecting.
        time.sleep(35)
        assert live.send([value])[0] == 202
        wait_for(
            lambda: (
                sum(
                    int(count)
                    for count in call(
                        [
                            "sqs",
                            "get-queue-attributes",
                            "--queue-url",
                            live.platform["QueueUrl"],
                            "--attribute-names",
                            "ApproximateNumberOfMessages",
                            "ApproximateNumberOfMessagesNotVisible",
                        ],
                        "Wait for queue backlog visibility",
                    )["Attributes"].values()
                )
                >= 1
            ),
            timeout=240,
        )
    finally:
        run(
            ["lambda", "update-event-source-mapping", "--uuid", mapping, "--enabled"],
            "Live E2E: restore processing mapping",
        )
    wait_for(
        lambda: any(
            r["eventId"] == value["eventId"]
            for r in live.api("GET", "/devices/motor-01/readings").json()["readings"]
        ),
        timeout=420,
    )


def test_poison_message_isolated_and_corrected_then_redriven(paused_simulator):
    live = paused_simulator
    unique = "poison-" + secrets.token_hex(8)
    call(
        [
            "sqs",
            "send-message",
            "--queue-url",
            live.platform["QueueUrl"],
            "--message-body",
            '{"invalid":true}',
            "--message-group-id",
            "factory",
            "--message-deduplication-id",
            unique,
        ],
        "Live E2E: inject isolated poison envelope",
    )
    wait_for(
        lambda: (
            int(
                call(
                    [
                        "sqs",
                        "get-queue-attributes",
                        "--queue-url",
                        live.platform["DlqUrl"],
                        "--attribute-names",
                        "ApproximateNumberOfMessages",
                    ],
                    "Observe poison message dead-letter isolation",
                )["Attributes"]["ApproximateNumberOfMessages"]
            )
            >= 1
        ),
        timeout=720,
        interval=20,
    )
    # Test redrive is demonstrated with a valid envelope placed directly in the DLQ.
    # Do not repeatedly redrive the invalid body without correcting it.
    value = measurement()
    envelope = canonical(
        {"readings": [value], "batchId": digest([value]), "receivedAt": timestamp(utcnow())}
    )
    call(
        [
            "sqs",
            "send-message",
            "--queue-url",
            live.platform["DlqUrl"],
            "--message-body",
            envelope,
            "--message-group-id",
            "factory",
            "--message-deduplication-id",
            value["eventId"],
        ],
        "Place corrected test envelope in DLQ for recovery",
    )
    # Receive/remove ONLY the known test poison; leave any unrelated failed messages alone.
    messages = call(
        [
            "sqs",
            "receive-message",
            "--queue-url",
            live.platform["DlqUrl"],
            "--max-number-of-messages",
            "10",
            "--visibility-timeout",
            "5",
        ],
        "Inspect isolated live-test envelopes",
    ).get("Messages", [])
    for item in messages:
        if item["Body"] == '{"invalid":true}':
            call(
                [
                    "sqs",
                    "delete-message",
                    "--queue-url",
                    live.platform["DlqUrl"],
                    "--receipt-handle",
                    item["ReceiptHandle"],
                ],
                "Remove known invalid test envelope after inspection",
            )
    call(
        [
            "sqs",
            "start-message-move-task",
            "--source-arn",
            live.platform["DlqArn"],
            "--destination-arn",
            live.platform["QueueArn"],
            "--max-number-of-messages-per-second",
            "1",
        ],
        "Live E2E: redrive corrected test envelope",
    )
    wait_for(lambda: live.state()["latest"]["eventId"] == value["eventId"], timeout=120)


def test_bounded_athena_reports_and_private_https_hosting(live):
    today = utcnow().date().isoformat()
    for report in ("temperature", "vibration", "power"):
        result = live.api("POST", "/reports", {"report": report, "start": today, "end": today})
        assert result.status_code == 202
        query = result.json()["reportId"]

        def completed_report(query=query):
            record = live.api("GET", "/reports/" + query).json()
            return record if record.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED") else None

        record = wait_for(completed_report, timeout=120)
        assert record["status"] == "SUCCEEDED" and record["rows"]
        assert record["bytesScanned"] <= 10485760
        assert live.api("GET", "/reports/" + query, role="viewer").status_code == 403
    page = requests.get(live.platform["DashboardUrl"], timeout=30)
    assert page.status_code == 200 and "cloudfront" in page.headers.get("via", "").lower()
    assert page.headers.get("x-content-type-options") == "nosniff"
    config = requests.get(live.platform["DashboardUrl"] + "/config.json", timeout=20)
    assert config.status_code == 200 and config.json()["apiUrl"] == live.platform["ApiUrl"]
    private = requests.get(
        f"https://{live.platform['FrontendBucket']}.s3.ap-southeast-2.amazonaws.com/index.html",
        timeout=20,
    )
    assert private.status_code == 403
