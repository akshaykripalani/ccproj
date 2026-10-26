import datetime as dt
import gzip
import json
from unittest.mock import patch

import pytest
from boto3.dynamodb.conditions import Key

from backend import api, ingestion, notifications, processor
from backend.aws_support import client, get_item, query_items
from backend.domain import canonical, digest, timestamp, utcnow
from tests.conftest import api_event


def message(readings, identity="message-1", received=None):
    return {
        "messageId": identity,
        "body": canonical(
            {
                "readings": readings,
                "batchId": digest(readings),
                "receivedAt": received or timestamp(utcnow()),
            }
        ),
    }


def process(readings, **kwargs):
    return processor.handler({"Records": [message(readings, **kwargs)]}, None)


def test_end_to_end_ingestion_queue_archive_state_and_api(aws, reading):
    readings = [reading(device=f"motor-0{i}") for i in range(1, 4)]
    accepted = ingestion.handler({"body": canonical({"readings": readings})}, None)
    assert accepted["statusCode"] == 202
    records = aws["sqs"].receive_message(QueueUrl=aws["queue"])["Messages"]
    assert processor.handler(
        {"Records": [{"messageId": m["MessageId"], "body": m["Body"]} for m in records]}, None
    ) == {"batchItemFailures": []}
    overview = api.handler(api_event("GET", "/devices"), None)
    assert overview["statusCode"] == 200
    devices = json.loads(overview["body"])["devices"]
    assert len(devices) == 7
    assert all(device["online"] for device in devices if device["deviceId"].startswith("motor-"))
    assert all(
        not device["online"] for device in devices if not device["deviceId"].startswith("motor-")
    )
    assert all(device["latest"]["temperatureC"] == 52 for device in devices if device["latest"])
    objects = aws["s3"].list_objects_v2(Bucket="ccproj-test-archive")["Contents"]
    assert len(objects) == 1
    with aws["s3"].get_object(Bucket="ccproj-test-archive", Key=objects[0]["Key"])["Body"] as body:
        archived = [json.loads(line) for line in gzip.decompress(body.read()).splitlines()]
    assert {r["eventId"] for r in archived} == {r["eventId"] for r in readings}
    chart = json.loads(api.handler(api_event("GET", "/devices/motor-01/readings"), None)["body"])
    assert len(chart["readings"]) == 1
    assert (
        chart["readings"][0]["expiresAt"]
        == int(
            dt.datetime.fromisoformat(readings[0]["observedAt"].replace("Z", "+00:00")).timestamp()
        )
        + 86400
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(temperatureC=True),
        lambda r: r.update(vibrationMmS=-1),
        lambda r: r.update(powerWatts=float("inf")),
        lambda r: r.update(deviceId="unknown"),
        lambda r: r.pop("eventId"),
        lambda r: r.update(schemaVersion=True),
        lambda r: r.update(observedAt="2026-10-14T10:00:00"),
        lambda r: r.update(observedAt=timestamp(utcnow() + dt.timedelta(minutes=5))),
        lambda r: r.update(observedAt=timestamp(utcnow() - dt.timedelta(days=2))),
        lambda r: r.update(operatingState="offline"),
        lambda r: r.update(scenario="overheat"),
    ],
)
def test_invalid_requests_never_enter_queue(aws, reading, mutate):
    value = reading()
    mutate(value)
    result = ingestion.handler({"body": json.dumps({"readings": [value]})}, None)
    assert result["statusCode"] == 400
    assert "Messages" not in aws["sqs"].receive_message(QueueUrl=aws["queue"])


def test_queue_failure_never_returns_accepted(aws, reading):
    with patch.object(client("sqs"), "send_message", side_effect=RuntimeError("queue unavailable")):
        with pytest.raises(RuntimeError):
            ingestion.handler({"body": canonical({"readings": [reading()]})}, None)


def test_duplicate_envelopes_and_events_do_not_change_state_or_archive_versions(aws, reading):
    value = reading()
    assert process([value])["batchItemFailures"] == []
    state = get_item(aws["data"], "motor-01", "STATE")
    for _ in range(3):
        assert process([value])["batchItemFailures"] == []
    assert get_item(aws["data"], "motor-01", "STATE") == state
    assert (
        len(query_items(aws["data"], Key("pk").eq("motor-01") & Key("sk").begins_with("READING#")))
        == 1
    )
    assert len(aws["s3"].list_object_versions(Bucket="ccproj-test-archive")["Versions"]) == 1
    process([value, reading(2, device="motor-02")])
    assert get_item(aws["data"], "motor-01", "STATE") == state


def test_older_event_preserves_latest_and_rule_counters_but_updates_receipt(aws, reading):
    process([reading(10, temperature=90)])
    newer = get_item(aws["data"], "motor-01", "STATE")
    received = timestamp(utcnow() + dt.timedelta(seconds=1))
    process([reading(1, temperature=20)], received=received)
    after = get_item(aws["data"], "motor-01", "STATE")
    assert after["eventId"] == newer["eventId"]
    assert after["rules"] == newer["rules"]
    assert after["lastSeen"] == received


def test_fault_activation_resolution_and_new_episode(aws, reading):
    for i in (1, 2):
        process([reading(i, temperature=95)])
    assert not get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]
    third = reading(3, temperature=95)
    process([third])
    first = get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]
    assert first["active"]
    process([third])
    for i in (4, 5):
        process([reading(i)])
        assert get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]
    process([reading(6)])
    assert not get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]
    assert get_item(aws["data"], "motor-01", f"ALERT#{first['alertId']}")["state"] == "resolved"
    for i in (7, 8, 9):
        process([reading(i, temperature=95)])
    assert len(query_items(aws["data"], Key("pk").eq("NOTIFY"))) == 2
    assert (
        len(query_items(aws["data"], Key("pk").eq("motor-01") & Key("sk").begins_with("ALERT#")))
        == 2
    )


def test_consecutive_means_interrupted_breach_does_not_activate(aws, reading):
    for i, temp in enumerate([90, 90, 52, 90, 90], 1):
        process([reading(i, temperature=temp)])
    assert not get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]


def test_s3_failure_does_not_commit_database_state(aws, reading):
    value = reading()
    with patch.object(client("s3"), "put_object", side_effect=RuntimeError("archive unavailable")):
        assert process([value])["batchItemFailures"] == [{"itemIdentifier": "message-1"}]
    assert get_item(aws["data"], "motor-01", "STATE") is None
    assert process([value])["batchItemFailures"] == []


def test_database_failure_after_archive_retries_without_duplicate_history(aws, reading):
    values = [reading(1, temperature=90), reading(2, temperature=90), reading(3, temperature=90)]
    real = client("dynamodb").transact_write_items
    count = 0

    def fail_second(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("database unavailable")
        return real(**kwargs)

    with patch.object(client("dynamodb"), "transact_write_items", side_effect=fail_second):
        assert process(values)["batchItemFailures"]
    assert process(values)["batchItemFailures"] == []
    assert get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]
    assert len(query_items(aws["data"], Key("pk").eq("NOTIFY"))) == 1
    assert len(aws["s3"].list_object_versions(Bucket="ccproj-test-archive")["Versions"]) == 1


def test_fifo_partial_failure_stops_before_unprocessed_messages(aws, reading):
    bad = {"messageId": "bad", "body": "invalid json"}
    records = [message([reading(1)], "good"), bad, message([reading(2)], "later")]
    result = processor.handler({"Records": records}, None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad"}, {"itemIdentifier": "later"}]}
    assert get_item(aws["data"], "motor-01", "STATE")["eventId"].endswith(":1")


def test_old_queued_message_validates_at_receipt_not_processing_time(aws, reading):
    old = utcnow() - dt.timedelta(days=3)
    value = reading(observed=timestamp(old))
    assert (
        process([value], received=timestamp(old + dt.timedelta(seconds=1)))["batchItemFailures"]
        == []
    )


def test_reused_event_identity_with_changed_measurement_fails(aws, reading):
    value = reading()
    process([value])
    assert process([{**value, "temperatureC": 96}])["batchItemFailures"]
    assert get_item(aws["data"], "motor-01", "STATE")["temperatureC"] == 52


def test_unconfirmed_email_outbox_and_retry_then_single_publish(aws, reading):
    for i in (1, 2, 3):
        process([reading(i, vibration=8)])
    with (
        patch("backend.notifications.subscriptions", return_value={"confirmed": 0, "pending": 1}),
        patch.object(client("sns"), "publish") as publish,
    ):
        assert notifications.handler({}, None)["published"] == 0
        publish.assert_not_called()
    intent = query_items(aws["data"], Key("pk").eq("NOTIFY"))[0]
    assert intent["delivery"] == "pending_confirmation"
    with (
        patch("backend.notifications.subscriptions", return_value={"confirmed": 1, "pending": 0}),
        patch.object(client("sns"), "publish", side_effect=RuntimeError("SNS unavailable")),
    ):
        with pytest.raises(RuntimeError, match="retained"):
            notifications.handler({}, None)
    with (
        patch("backend.notifications.subscriptions", return_value={"confirmed": 1, "pending": 0}),
        patch.object(
            client("sns"), "publish", return_value={"MessageId": "published-1"}
        ) as publish,
    ):
        assert notifications.handler({}, None)["published"] == 1
        assert notifications.handler({}, None)["published"] == 0
        publish.assert_called_once()


def test_midnight_batch_archive_partitions_by_measurement_date(aws, reading):
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    # Validation at receipt allows the previous evening and present midnight.
    values = [
        reading(1, observed=timestamp(today - dt.timedelta(seconds=1))),
        reading(2, observed=timestamp(today)),
    ]
    assert process(values)["batchItemFailures"] == []
    assert len(aws["s3"].list_objects_v2(Bucket="ccproj-test-archive")["Contents"]) == 2


def test_archive_object_version_recovery_and_replay_suppresses_notifications(aws, reading):
    original = b"evidence-v1"
    key = "recovery/probe.txt"
    first = aws["s3"].put_object(Bucket="ccproj-test-archive", Key=key, Body=original)["VersionId"]
    aws["s3"].put_object(Bucket="ccproj-test-archive", Key=key, Body=b"overwritten")
    aws["s3"].delete_object(Bucket="ccproj-test-archive", Key=key)
    aws["s3"].copy_object(
        Bucket="ccproj-test-archive",
        Key=key,
        CopySource={"Bucket": "ccproj-test-archive", "Key": key, "VersionId": first},
    )
    with aws["s3"].get_object(Bucket="ccproj-test-archive", Key=key)["Body"] as result:
        assert result.read() == original
    for i in (1, 2, 3):
        value = reading(i, temperature=95)
        processor.process_reading(value, timestamp(utcnow()), "replayed-object", replay=True)
    assert get_item(aws["data"], "motor-01", "STATE")["rules"]["temperature"]["active"]
    assert not query_items(aws["data"], Key("pk").eq("NOTIFY"))
