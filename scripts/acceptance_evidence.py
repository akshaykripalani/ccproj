"""Capture read-only, non-secret deployed configuration and health evidence."""

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.aws_cli import ACCOUNT, call, identity

ROOT = Path(__file__).resolve().parents[1]


def capture():
    identity()
    deployment = json.loads((ROOT / ".runtime" / "deployment.json").read_text())
    p = deployment["platform"]
    now = dt.datetime.now(dt.timezone.utc)
    specs = {
        "stacks": [
            "cloudformation",
            "describe-stacks",
            "--query",
            "Stacks[?starts_with(StackName, 'ccproj')].{name:StackName,status:StackStatus}",
        ],
        "subscriptions": ["sns", "list-subscriptions-by-topic", "--topic-arn", p["AlertTopicArn"]],
        "consumer": ["lambda", "get-event-source-mapping", "--uuid", p["ProcessingMapping"]],
        "alarms": ["cloudwatch", "describe-alarms", "--alarm-name-prefix", "ccproj-"],
        "budget": [
            "budgets",
            "describe-budget",
            "--account-id",
            ACCOUNT,
            "--budget-name",
            "ccproj-total-ceiling",
        ],
        "budgetNotifications": [
            "budgets",
            "describe-notifications-for-budget",
            "--account-id",
            ACCOUNT,
            "--budget-name",
            "ccproj-total-ceiling",
        ],
        "instance": [
            "ec2",
            "describe-instances",
            "--instance-ids",
            deployment["simulator"]["InstanceId"],
            "--query",
            "Reservations[].Instances[].{id:InstanceId,state:State.Name,type:InstanceType,metadata:MetadataOptions,volumes:BlockDeviceMappings}",
        ],
        "managedInstance": [
            "ssm",
            "describe-instance-information",
            "--filters",
            "Key=InstanceIds,Values=" + deployment["simulator"]["InstanceId"],
        ],
        "recentTTL": ["dynamodb", "describe-time-to-live", "--table-name", p["DataTable"]],
        "archiveVersioning": ["s3api", "get-bucket-versioning", "--bucket", p["ArchiveBucket"]],
        "archiveRetention": [
            "s3api",
            "get-bucket-lifecycle-configuration",
            "--bucket",
            p["ArchiveBucket"],
        ],
        "hostingPrivacy": ["s3api", "get-public-access-block", "--bucket", p["FrontendBucket"]],
        "athenaLimits": ["athena", "get-work-group", "--work-group", p["AthenaWorkgroup"]],
    }
    for label, key in (("queue", "QueueUrl"), ("deadLetters", "DlqUrl")):
        specs[label] = [
            "sqs",
            "get-queue-attributes",
            "--queue-url",
            p[key],
            "--attribute-names",
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ]
    for device in ("motor-01", "motor-02", "motor-03"):
        specs[device] = [
            "dynamodb",
            "get-item",
            "--table-name",
            p["DataTable"],
            "--consistent-read",
            "--key",
            json.dumps({"pk": {"S": device}, "sk": {"S": "STATE"}}),
        ]

    def read(item):
        name, args = item
        try:
            return name, call(args, "Capture deployed acceptance evidence: " + name)
        except RuntimeError as exc:
            return name, {"unavailable": str(exc)}

    with ThreadPoolExecutor(max_workers=4) as executor:
        evidence = dict(executor.map(read, specs.items()))
    evidence["capturedAt"] = now.isoformat()
    evidence["region"] = "ap-southeast-2"
    target = ROOT / "docs" / "deployed-evidence.json"
    target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(target)
    return evidence


if __name__ == "__main__":
    capture()
