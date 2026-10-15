import datetime as dt
import json

import boto3
import pytest
from moto import mock_aws

from backend import aws_support
from backend.domain import canonical, timestamp, utcnow


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("USER_POOL", "test-pool")
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "ap-southeast-2",
        "DATA_TABLE": "test-data",
        "CONTROL_TABLE": "test-controls",
        "ARCHIVE_BUCKET": "ccproj-test-archive",
        "GLUE_DATABASE": "ccproj",
        "ATHENA_WORKGROUP": "reports",
        "OFFLINE_SECONDS": "60",
        "DASHBOARD_URL": "https://dashboard.example.test",
    }.items():
        monkeypatch.setenv(name, value)
    aws_support.client.cache_clear()
    aws_support.dynamodb.cache_clear()
    with mock_aws():
        db = boto3.resource("dynamodb", region_name="ap-southeast-2")
        for name in ("test-data", "test-controls"):
            props = {
                "TableName": name,
                "BillingMode": "PAY_PER_REQUEST",
                "KeySchema": [
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                ],
            }
            if name == "test-data":
                props["AttributeDefinitions"] += [
                    {"AttributeName": "workStatus", "AttributeType": "S"},
                    {"AttributeName": "workAt", "AttributeType": "S"},
                ]
                props["GlobalSecondaryIndexes"] = [
                    {
                        "IndexName": "Work",
                        "KeySchema": [
                            {"AttributeName": "workStatus", "KeyType": "HASH"},
                            {"AttributeName": "workAt", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ]
            db.create_table(**props)
        s3 = aws_support.client("s3")
        s3.create_bucket(
            Bucket="ccproj-test-archive",
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )
        s3.put_bucket_versioning(
            Bucket="ccproj-test-archive", VersioningConfiguration={"Status": "Enabled"}
        )
        sqs = aws_support.client("sqs")
        queue = sqs.create_queue(QueueName="telemetry.fifo", Attributes={"FifoQueue": "true"})[
            "QueueUrl"
        ]
        monkeypatch.setenv("QUEUE_URL", queue)
        topic = aws_support.client("sns").create_topic(Name="motor-alerts")["TopicArn"]
        monkeypatch.setenv("ALERT_TOPIC", topic)
        yield {
            "data": db.Table("test-data"),
            "controls": db.Table("test-controls"),
            "s3": s3,
            "sqs": sqs,
            "queue": queue,
            "topic": topic,
        }
    aws_support.client.cache_clear()
    aws_support.dynamodb.cache_clear()


@pytest.fixture
def reading():
    def make(
        sequence=1, device="motor-01", temperature=52, vibration=1.5, observed=None, **overrides
    ):
        return {
            "schemaVersion": 1,
            "eventId": f"test:{device}:{sequence}",
            "deviceId": device,
            "observedAt": observed or timestamp(utcnow() - dt.timedelta(seconds=60 - sequence)),
            "temperatureC": temperature,
            "vibrationMmS": vibration,
            "powerWatts": 420,
            "operatingState": "running",
            **overrides,
        }

    return make


def api_event(method, path, role="viewer", payload=None, params=None):
    return {
        "rawPath": path,
        "requestContext": {
            "requestId": "test",
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "test-user",
                        "username": "test@example.com",
                        "token_use": "access",
                        "cognito:groups": canonical([role]),
                    }
                }
            },
        },
        "body": json.dumps(payload or {}),
        "queryStringParameters": params,
    }
