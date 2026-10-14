"""CLI-driven recovery into a separate disposable state table; no SNS publication."""
import argparse
import gzip
import json
from pathlib import Path
import sys

from boto3.dynamodb.types import TypeSerializer

from backend.domain import evolve, native
from scripts.aws_cli import call, identity, run

ROOT = Path(__file__).resolve().parents[1]


def recover(deployment, prefix):
    identity()
    platform = deployment["platform"]
    name = deployment["stack"] + "-recovery"
    runtime = ROOT / ".runtime" / "recovery"
    runtime.mkdir(parents=True, exist_ok=True)
    template = {"AWSTemplateFormatVersion": "2010-09-09", "Description": "Separate recovery exercise state table; live monitoring data remains untouched", "Resources": {"State": {"Type": "AWS::DynamoDB::Table", "Properties": {"BillingMode": "PAY_PER_REQUEST", "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}], "SSESpecification": {"SSEEnabled": True}}}}, "Outputs": {"Table": {"Value": {"Ref": "State"}}}}
    template_file = runtime / "template.json"
    template_file.write_text(json.dumps(template))
    run(["cloudformation", "deploy", "--stack-name", name, "--template-file", str(template_file), "--no-fail-on-empty-changeset"], "Provision separate recovery exercise state table")
    table_name = call(["cloudformation", "describe-stacks", "--stack-name", name], "Read recovery table identifier")["Stacks"][0]["Outputs"][0]["OutputValue"]
    if table_name == platform["DataTable"]:
        raise RuntimeError("Recovery must never target the live data table")
    objects = call(["s3api", "list-objects-v2", "--bucket", platform["ArchiveBucket"], "--prefix", prefix], "Enumerate archived recovery readings").get("Contents", [])
    if len(objects) > 10000:
        raise ValueError("Recovery exercise is bounded to 10,000 archive objects")
    readings = {}
    for index, item in enumerate(objects):
        if not item["Key"].endswith(".json.gz"):
            continue
        file = runtime / f"archive-{index}.json.gz"
        run(["s3api", "get-object", "--bucket", platform["ArchiveBucket"], "--key", item["Key"], str(file)], "Read archived recovery batch")
        for line in gzip.decompress(file.read_bytes()).splitlines():
            value = json.loads(line)
            readings.setdefault(value["eventId"], value)
    states = {}
    for reading in sorted(readings.values(), key=lambda value: (value["observedAt"], value["eventId"])):
        device = reading["deviceId"]
        measurement = {key: value for key, value in reading.items() if key != "receivedAt"}
        states[device], _ = evolve(states.get(device), measurement, reading["receivedAt"])
    serializer = TypeSerializer()
    for device, state in states.items():
        state.update(pk=device, sk="STATE")
        file = runtime / f"{device}.json"
        file.write_text(json.dumps({key: serializer.serialize(value) for key, value in native(state).items()}))
        call(["dynamodb", "put-item", "--table-name", table_name, "--item", "file://" + str(file)], "Rebuild test device state without notifications")
    return {"table": table_name, "stack": name, "uniqueEvents": len(readings), "devices": len(states), "notifications": "suppressed; this script never calls SNS"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", default=str(ROOT / ".runtime" / "deployment.json"))
    parser.add_argument("--prefix", required=True, help="Bounded telemetry/day=YYYY-MM-DD/ prefix")
    args = parser.parse_args()
    if not args.prefix.startswith("telemetry/day="):
        parser.error("Use a single date partition for the recovery exercise")
    print(json.dumps(recover(json.loads(Path(args.deployment).read_text()), args.prefix), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
