import logging
import os

from backend.aws_support import body, client, response
from backend.domain import canonical, digest, timestamp, utcnow, validate_batch

log = logging.getLogger(__name__)


def handler(event, context):
    try:
        readings = validate_batch(body(event))
    except (ValueError, TypeError, KeyError) as exc:
        return response(400, {"error": str(exc)})
    envelope = {"readings": readings, "receivedAt": timestamp(utcnow())}
    # One factory group orders arrivals across the three demo motors. Each accepted
    # envelope keeps its own archive identity even beyond SQS's deduplication window.
    envelope["batchId"] = digest(readings)
    result = client("sqs").send_message(
        QueueUrl=os.environ["QUEUE_URL"],
        MessageBody=canonical(envelope),
        MessageGroupId="factory",
        MessageDeduplicationId=envelope["batchId"],
    )
    log.info("Queued batch=%s readings=%s", envelope["batchId"], len(readings))
    return response(
        202,
        {
            "status": "queued",
            "accepted": len(readings),
            "batchId": envelope["batchId"],
            "messageId": result["MessageId"],
        },
    )
