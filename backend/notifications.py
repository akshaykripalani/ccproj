import logging
import os

from boto3.dynamodb.conditions import Key

from backend.alert_email import render_email
from backend.aws_support import client, query_items, table
from backend.domain import timestamp, utcnow

log = logging.getLogger(__name__)


def subscriptions():
    pages = (
        client("sns")
        .get_paginator("list_subscriptions_by_topic")
        .paginate(TopicArn=os.environ["ALERT_TOPIC"])
    )
    items = [item for page in pages for item in page["Subscriptions"]]
    return {
        "confirmed": sum(item["SubscriptionArn"] != "PendingConfirmation" for item in items),
        "pending": sum(item["SubscriptionArn"] == "PendingConfirmation" for item in items),
    }


def handler(event, context):
    target = table()
    status = subscriptions()
    items = query_items(
        target, Key("workStatus").eq("pending"), IndexName="Work", PaginationConfig={"MaxItems": 50}
    )
    published = 0
    failed = 0
    for intent in items:
        key = {"pk": intent["pk"], "sk": intent["sk"]}
        if not status["confirmed"]:
            target.update_item(
                Key=key,
                UpdateExpression="SET delivery = :delivery",
                ExpressionAttributeValues={":delivery": "pending_confirmation"},
            )
            continue
        try:
            result = client("sns").publish(
                TopicArn=os.environ["ALERT_TOPIC"],
                **render_email(intent, os.environ["DASHBOARD_URL"]),
            )
            target.update_item(
                Key=key,
                UpdateExpression="SET delivery = :status, publishedAt = :at, snsMessageId = :id REMOVE workStatus, workAt",
                ExpressionAttributeValues={
                    ":status": "sns_accepted",
                    ":at": timestamp(utcnow()),
                    ":id": result["MessageId"],
                },
            )
            published += 1
        except Exception:
            failed += 1
            log.exception("Notification attempt failed alert=%s", intent["sk"])
            # Keep intent pending for the next scheduled attempt. A crash after SNS
            # acceptance but before marking it can duplicate mail; no exactly-once claim.
    if failed:
        raise RuntimeError(
            f"{failed} notification attempts failed; pending intents retained for retry"
        )
    return {"published": published, "subscriptions": status}
