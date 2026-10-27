"""Bounded live recovery verification through the gateway's real control table.

Uses the audited project CLI. Restores approved fleet profiles even after failure.
No Cognito login or synthetic telemetry is needed for this controller exercise.
"""

import concurrent.futures
import json
import time
import uuid
from pathlib import Path

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from backend.domain import DEVICES, native, timestamp, utcnow
from backend.equipment import default_profile
from scripts.aws_cli import call, identity

ROOT = Path(__file__).resolve().parents[1]


def main():
    identity()
    deployment = json.loads((ROOT / "docs/ccproj-deployment.json").read_text())
    platform = deployment["platform"]
    decoder, encoder = TypeDeserializer(), TypeSerializer()
    request = {
        platform["DataTable"]: {
            "Keys": [{"pk": {"S": d}, "sk": {"S": "STATE"}} for d in DEVICES],
            "ConsistentRead": True,
        },
        platform["ControlTable"]: {
            "Keys": [{"pk": {"S": d}, "sk": {"S": "CONTROL"}} for d in DEVICES],
            "ConsistentRead": True,
        },
    }
    keys = ROOT / ".runtime/cooldown-verification-keys.json"
    keys.write_text(json.dumps(request))

    def snapshot():
        result = call(
            ["dynamodb", "batch-get-item", "--request-items", "file://" + str(keys)],
            "Read bounded live cooldown verification state",
        )
        assert not result.get("UnprocessedKeys"), (
            "Retry verification if the bounded snapshot was throttled"
        )
        rows = [
            {k: decoder.deserialize(v) for k, v in row.items()}
            for group in result["Responses"].values()
            for row in group
        ]
        return {(row["pk"], row["sk"]): row for row in rows}

    def set_profiles(profiles):
        before = snapshot()

        def update(device):
            previous = before[(device, "CONTROL")]
            values = {
                ":previous": previous["requestId"],
                ":profile": profiles[device],
                ":mode": "normal",
                ":request": uuid.uuid4().hex,
                ":at": timestamp(utcnow()),
                ":who": "operator-live-verification",
                ":pending": "pending",
                ":empty": "",
            }
            payload = {
                "TableName": platform["ControlTable"],
                "Key": {"pk": {"S": device}, "sk": {"S": "CONTROL"}},
                "ConditionExpression": "requestId = :previous",
                "UpdateExpression": "SET #p = :profile, requestedMode = :mode, requestId = :request, requestedAt = :at, requestedBy = :who, #s = :pending, maintenanceAction = :empty, maintenanceEpisode = :empty",
                "ExpressionAttributeNames": {"#p": "profile", "#s": "status"},
                "ExpressionAttributeValues": {
                    k: encoder.serialize(native(v)) for k, v in values.items()
                },
            }
            location = ROOT / (".runtime/cooldown-profile-" + device + ".json")
            for attempt in range(3):
                location.write_text(json.dumps(payload))
                try:
                    call(
                        ["dynamodb", "update-item", "--cli-input-json", "file://" + str(location)],
                        "Request bounded cooldown verification profile for " + device,
                    )
                    return
                except RuntimeError as error:
                    if "ConditionalCheckFailedException" not in str(error):
                        raise
                    raw = call(
                        [
                            "dynamodb",
                            "get-item",
                            "--table-name",
                            platform["ControlTable"],
                            "--key",
                            json.dumps(payload["Key"]),
                            "--consistent-read",
                        ],
                        "Reconcile concurrent automatic recovery for " + device,
                    )["Item"]
                    current = {k: decoder.deserialize(v) for k, v in raw.items()}
                    if current["requestId"] == values[":request"]:
                        return  # A transport retry followed a successful conditional write.
                    if current.get("requestedBy") != "automation" or attempt == 2:
                        raise  # Never overwrite a new human command.
                    payload["ExpressionAttributeValues"][":previous"] = encoder.serialize(
                        current["requestId"]
                    )

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(update, device) for device in DEVICES]
            failures = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    failures.append(error)
            if failures:
                raise failures[0]

    recoveries = {device: {} for device in DEVICES}
    try:
        set_profiles(
            {
                device: {
                    "enabled": True,
                    "faultMode": "overheat",
                    "failureAfterMinutes": 10,
                    "speed": 10,
                }
                for device in DEVICES
            }
        )
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            rows = snapshot()
            for device in DEVICES:
                control = rows[(device, "CONTROL")]
                assert control.get("maintenanceAction") != "Repair needed", device
                if control.get("maintenanceAction") == "Restarted automatically":
                    recoveries[device][control["requestId"]] = control["maintenanceAt"]
            print(
                json.dumps(
                    {
                        "automaticRestarts": {
                            device: len(cycles) for device, cycles in recoveries.items()
                        }
                    }
                ),
                flush=True,
            )
            if all(len(cycles) >= 2 for cycles in recoveries.values()):
                break
            time.sleep(8)
        else:
            raise AssertionError("Not every device completed two automatic recovery cycles")
        (ROOT / "docs/repeated-cooldown-live-evidence.json").write_text(
            json.dumps(
                {
                    "outcome": "All seven assets automatically recovered twice without manual repair",
                    "method": "Real EC2 telemetry and inference Lambda; audited conditional control-table requests",
                    "account": "039379078306",
                    "region": "ap-southeast-2",
                    "profile": "default",
                    "recoveries": recoveries,
                    "checkedAt": timestamp(utcnow()),
                    "testProfile": {
                        "enabled": True,
                        "faultMode": "overheat",
                        "failureAfterMinutes": 10,
                        "speed": 10,
                    },
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        set_profiles({device: default_profile(device) for device in DEVICES})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            rows = snapshot()
            if all(
                rows[(d, "CONTROL")].get("status") == "applied"
                and rows[(d, "CONTROL")]["profile"] == default_profile(d)
                and rows[(d, "STATE")]["operatingState"] == "running"
                and not any(rule["active"] for rule in rows[(d, "STATE")]["rules"].values())
                for d in DEVICES
            ):
                print(
                    "Approved three/two/two profiles restored and all devices healthy", flush=True
                )
                break
            time.sleep(5)
        else:
            raise AssertionError("Approved profiles did not finish restoring")


if __name__ == "__main__":
    main()
