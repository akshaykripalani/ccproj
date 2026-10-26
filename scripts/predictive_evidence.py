"""Read-only final health and public-build hash evidence for the expanded deployment."""

import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from scripts.aws_cli import call, identity

ROOT = Path(__file__).resolve().parents[1]


def capture():
    active = identity()
    deployment = json.loads((ROOT / "docs/ccproj-deployment.json").read_text())
    p = deployment["platform"]
    checks = {
        "stacks": [
            "cloudformation",
            "describe-stacks",
            "--query",
            "Stacks[?starts_with(StackName, 'ccproj')].{name:StackName,status:StackStatus}",
        ],
        "simulator": [
            "ec2",
            "describe-instances",
            "--instance-ids",
            deployment["simulator"]["InstanceId"],
            "--query",
            "Reservations[].Instances[].{id:InstanceId,state:State.Name,type:InstanceType,image:ImageId}",
        ],
        "consumer": [
            "lambda",
            "get-event-source-mapping",
            "--uuid",
            p["ProcessingMapping"],
            "--query",
            "{state:State}",
        ],
        "queue": [
            "sqs",
            "get-queue-attributes",
            "--queue-url",
            p["QueueUrl"],
            "--attribute-names",
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
        "dlq": [
            "sqs",
            "get-queue-attributes",
            "--queue-url",
            p["DlqUrl"],
            "--attribute-names",
            "ApproximateNumberOfMessages",
        ],
        "predictor": [
            "lambda",
            "get-function-configuration",
            "--function-name",
            p["PredictorFunction"],
            "--query",
            "{state:State,update:LastUpdateStatus,memoryMiB:MemorySize,runtime:Runtime,architecture:Architectures,modelVersion:Environment.Variables.MODEL_VERSION}",
        ],
        "alarms": [
            "cloudwatch",
            "describe-alarms",
            "--alarm-name-prefix",
            "ccproj-",
            "--query",
            "MetricAlarms[].{name:AlarmName,state:StateValue}",
        ],
        "budget": [
            "budgets",
            "describe-budget",
            "--account-id",
            active["Account"],
            "--budget-name",
            "ccproj-total-ceiling",
            "--query",
            "Budget.{limit:BudgetLimit,actual:CalculatedSpend.ActualSpend}",
        ],
        "projectInstances": [
            "ec2",
            "describe-instances",
            "--filters",
            "Name=tag:Project,Values=ccproj",
            "--query",
            "Reservations[].Instances[].{id:InstanceId,state:State.Name,type:InstanceType}",
        ],
    }

    def check(pair):
        name, args = pair
        return name, call(args, "Final predictive deployment evidence: " + name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        evidence = dict(pool.map(check, checks.items()))
    from backend.domain import DEVICES

    request = {
        p["DataTable"]: {
            "Keys": [
                {"pk": {"S": device}, "sk": {"S": kind}}
                for device in DEVICES
                for kind in ("STATE", "PREDICTION")
            ],
            "ConsistentRead": True,
        },
        p["ControlTable"]: {
            "Keys": [{"pk": {"S": device}, "sk": {"S": "CONTROL"}} for device in DEVICES],
            "ConsistentRead": True,
        },
    }
    location = ROOT / ".runtime/final-evidence-keys.json"
    location.write_text(json.dumps(request), encoding="utf-8")
    fetched = call(
        ["dynamodb", "batch-get-item", "--request-items", "file://" + str(location)],
        "Final bounded device and prediction snapshot",
    )
    assert not fetched.get("UnprocessedKeys"), (
        "Retry snapshot if DynamoDB returned unprocessed keys"
    )
    index = {
        (row["pk"]["S"], row["sk"]["S"]): row
        for rows in fetched["Responses"].values()
        for row in rows
    }
    keep = {
        "observedAt",
        "lastSeen",
        "temperatureC",
        "vibrationMmS",
        "operatingState",
        "rules",
        "simulationSpeed",
        "modelVersion",
        "riskScore",
        "warning",
        "requestedMode",
        "appliedMode",
        "status",
        "profile",
        "maintenanceAction",
    }
    devices = [
        {
            "deviceId": device,
            **{
                kind: {key: value for key, value in index[(device, kind)].items() if key in keep}
                for kind in ("STATE", "PREDICTION", "CONTROL")
            },
        }
        for device in DEVICES
    ]
    evidence.update(
        account=active["Account"],
        region="ap-southeast-2",
        profile="default",
        checkedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
        devices=devices,
        shutdownScheduled=False,
    )
    assets = []
    base = p["DashboardUrl"]
    for path in sorted((ROOT / "frontend/dist").rglob("*")):
        if path.is_file():
            relative = path.relative_to(ROOT / "frontend/dist").as_posix()
            with urlopen(base + "/" + relative, timeout=30) as response:
                remote = response.read()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert hashlib.sha256(remote).hexdigest() == digest, (
                "Published build mismatch: " + relative
            )
            assets.append({"path": relative, "sha256": digest})
    evidence["publishedAssets"] = assets
    evidence["allPublishedHashesMatch"] = True
    (ROOT / "docs/predictive-deployed-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "devices": len(devices),
                "modelVersion": evidence["predictor"]["modelVersion"],
                "alarmStates": [a["state"] for a in evidence["alarms"]],
                "assetsVerified": len(assets),
                "instance": evidence["simulator"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    capture()
