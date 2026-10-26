import gzip
import json
import logging
import os

from boto3.dynamodb.types import TypeSerializer

from backend.aws_support import client, get_item, table
from backend.domain import (
    canonical,
    digest,
    evolve,
    native,
    parse_time,
    timestamp,
    utcnow,
    validate_batch,
)

log = logging.getLogger(__name__)
serializer = TypeSerializer()


def encoded(item):
    return {key: serializer.serialize(value) for key, value in native(item).items()}


def process_reading(reading, received_at, archive_key, *, replay=False, target=None):
    target = target or table()
    marker_key = (f"EVENT#{reading['eventId']}", "META")
    fingerprint = digest(reading)
    for attempt in range(5):
        existing = get_item(target, *marker_key)
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise ValueError("An eventId was reused with a different measurement")
            return "duplicate"
        previous = get_item(target, reading["deviceId"], "STATE")
        state, changes = evolve(previous, reading, received_at)
        revision = int((previous or {}).get("revision", 0))
        state.update(pk=reading["deviceId"], sk="STATE", revision=revision + 1)
        ttl = int(parse_time(reading["observedAt"]).timestamp()) + 86400
        marker = {
            "pk": marker_key[0],
            "sk": "META",
            "fingerprint": fingerprint,
            "archiveKey": archive_key,
            "expiresAt": int(utcnow().timestamp()) + 31 * 86400,
        }
        recent = {
            **reading,
            "pk": reading["deviceId"],
            "sk": f"READING#{reading['observedAt']}#{reading['eventId']}",
            "receivedAt": received_at,
            "expiresAt": ttl,
        }
        # A low-level transaction is required for atomic marker, state, recent reading,
        # alert history and notification intent. Resource conditions are used elsewhere.
        operations = [
            {
                "Put": {
                    "TableName": target.name,
                    "Item": encoded(marker),
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            },
            {"Put": {"TableName": target.name, "Item": encoded(recent)}},
            {
                "Put": {
                    "TableName": target.name,
                    "Item": encoded(state),
                    "ConditionExpression": "revision = :old"
                    if previous
                    else "attribute_not_exists(pk)",
                    **(
                        {"ExpressionAttributeValues": {":old": {"N": str(revision)}}}
                        if previous
                        else {}
                    ),
                }
            },
        ]
        for change in changes:
            alert_key = {"pk": reading["deviceId"], "sk": f"ALERT#{change['alertId']}"}
            if change["kind"] == "activated":
                alert = {
                    **alert_key,
                    **change,
                    "state": "active",
                    "reading": reading,
                    "activatedAt": reading["observedAt"],
                    "expiresAt": int(utcnow().timestamp()) + 30 * 86400,
                }
                operations.append({"Put": {"TableName": target.name, "Item": encoded(alert)}})
                if not replay:
                    intent = {
                        "pk": "NOTIFY",
                        "sk": change["alertId"],
                        "deviceId": reading["deviceId"],
                        "rule": change["rule"],
                        "reading": reading,
                        "delivery": "pending",
                        "workStatus": "pending",
                        "workAt": received_at,
                        "expiresAt": int(utcnow().timestamp()) + 30 * 86400,
                    }
                    operations.append({"Put": {"TableName": target.name, "Item": encoded(intent)}})
            else:
                operations.append(
                    {
                        "Update": {
                            "TableName": target.name,
                            "Key": encoded(alert_key),
                            "UpdateExpression": "SET #state = :resolved, resolvedAt = :at",
                            "ExpressionAttributeNames": {"#state": "state"},
                            "ExpressionAttributeValues": {
                                ":resolved": {"S": "resolved"},
                                ":at": {"S": reading["observedAt"]},
                            },
                        }
                    }
                )
        try:
            # Native resource clients install marshalling hooks; use the unmodified
            # low-level client here since the transaction is explicitly serialized.
            client("dynamodb").transact_write_items(TransactItems=operations)
            return "processed"
        except client("dynamodb").exceptions.TransactionCanceledException as exc:
            reasons = exc.response.get("CancellationReasons", [])
            if any(
                reason.get("Code") not in ("None", "ConditionalCheckFailed", "TransactionConflict")
                for reason in reasons
            ):
                raise
            if attempt == 4:
                raise
    raise RuntimeError("Concurrent state update could not be committed")


def archive(envelope):
    lines = [canonical({**r, "receivedAt": envelope["receivedAt"]}) for r in envelope["readings"]]
    day = min(r["observedAt"][:10] for r in envelope["readings"])
    # Partition by observed date. Cross-midnight batches get separate date objects.
    keys = {}
    for day in sorted({r["observedAt"][:10] for r in envelope["readings"]}):
        lines = [
            canonical({**r, "receivedAt": envelope["receivedAt"]})
            for r in envelope["readings"]
            if r["observedAt"].startswith(day)
        ]
        key = f"telemetry/day={day}/{envelope['batchId']}.json.gz"
        try:
            client("s3").put_object(
                Bucket=os.environ["ARCHIVE_BUCKET"],
                Key=key,
                Body=gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0),
                ContentType="application/x-ndjson",
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
        except client("s3").exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] not in ("PreconditionFailed", "412"):
                raise
        keys[day] = key
    return keys


def process_message(message):
    envelope = json.loads(message["body"])
    received = parse_time(envelope["receivedAt"])
    # Accepted messages can wait in SQS/DLQ for days; validate relative to receipt.
    envelope["readings"] = validate_batch({"readings": envelope["readings"]}, received)
    if envelope["batchId"] != digest(envelope["readings"]):
        raise ValueError("Invalid batch identity")
    for reading in envelope["readings"]:
        existing = get_item(table(), f"EVENT#{reading['eventId']}", "META")
        if existing and existing["fingerprint"] != digest(reading):
            raise ValueError("An eventId was reused with a different measurement")
    keys = archive(envelope)
    for reading in envelope["readings"]:
        process_reading(reading, timestamp(received), keys[reading["observedAt"][:10]])
    if os.environ.get("PREDICTOR_FUNCTION"):
        # Async acceptance is required; retry-safe state commits tolerate a retry here.
        client("lambda").invoke(
            FunctionName=os.environ["PREDICTOR_FUNCTION"], InvocationType="Event", Payload=b"{}"
        )


def handler(event, context):
    records = event["Records"]
    for index, message in enumerate(records):
        try:
            process_message(message)
        except Exception:
            log.exception("Processing failed message=%s", message["messageId"])
            # FIFO: stop at first failure and retry all unprocessed messages to
            # preserve ordering. Previously committed event markers prevent recounting.
            return {
                "batchItemFailures": [{"itemIdentifier": r["messageId"]} for r in records[index:]]
            }
    return {"batchItemFailures": []}
