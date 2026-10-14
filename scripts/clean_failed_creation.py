"""Clean only empty resources retained by a rolled-back initial project creation."""

import json
from pathlib import Path

from scripts.aws_cli import call, identity, run

ROOT = Path(__file__).resolve().parents[1]


def main():
    identity()
    stack = call(
        ["cloudformation", "describe-stacks", "--stack-name", "ccproj"],
        "Verify failed initial creation is fully rolled back",
    )["Stacks"][0]
    if stack["StackStatus"] != "ROLLBACK_COMPLETE":
        raise RuntimeError("Only a rolled-back initial creation can be cleaned")
    resources = call(
        ["cloudformation", "list-stack-resources", "--stack-name", "ccproj"],
        "Identify exact resources retained by failed initial creation",
    )["StackResourceSummaries"]
    retained = [r for r in resources if r["ResourceStatus"] == "DELETE_SKIPPED"]
    for resource in retained:
        kind, identifier = resource["ResourceType"], resource["PhysicalResourceId"]
        if kind == "AWS::S3::Bucket":
            result = call(
                ["s3api", "list-object-versions", "--bucket", identifier],
                "Verify failed-creation bucket has no data or versions",
            )
            if result.get("Versions") or result.get("DeleteMarkers"):
                raise RuntimeError("Refusing to remove any bucket containing data")
        elif kind == "AWS::DynamoDB::Table":
            result = call(
                [
                    "dynamodb",
                    "scan",
                    "--table-name",
                    identifier,
                    "--consistent-read",
                    "--select",
                    "COUNT",
                    "--limit",
                    "1",
                ],
                "Verify retained failed-creation table contains no telemetry",
            )
            if result["Count"] or result.get("LastEvaluatedKey"):
                raise RuntimeError("Refusing to remove any table containing data")
        elif kind == "AWS::Cognito::UserPool":
            result = call(
                ["cognito-idp", "list-users", "--user-pool-id", identifier, "--limit", "1"],
                "Verify failed-creation user pool contains no users",
            )
            if result["Users"] or result.get("PaginationToken"):
                raise RuntimeError("Refusing to remove a user pool with accounts")
        elif kind == "AWS::KMS::Key":
            call(
                ["kms", "describe-key", "--key-id", identifier],
                "Inspect only the encryption key retained by this failed initial creation",
            )
        else:
            raise RuntimeError("Unsupported retained resource: " + kind)
    # All emptiness checks finish before any cleanup begins.
    for resource in retained:
        kind, identifier = resource["ResourceType"], resource["PhysicalResourceId"]
        if kind == "AWS::S3::Bucket":
            call(
                ["s3api", "delete-bucket", "--bucket", identifier],
                "Remove verified-empty failed-creation bucket",
            )
        elif kind == "AWS::DynamoDB::Table":
            call(
                ["dynamodb", "delete-table", "--table-name", identifier],
                "Remove verified-empty failed-creation table",
            )
        elif kind == "AWS::Cognito::UserPool":
            call(
                ["cognito-idp", "delete-user-pool", "--user-pool-id", identifier],
                "Remove verified-empty failed-creation user pool",
            )
        else:
            call(
                [
                    "kms",
                    "schedule-key-deletion",
                    "--key-id",
                    identifier,
                    "--pending-window-in-days",
                    "7",
                ],
                "Schedule removal of only the abandoned failed-creation encryption key",
            )
    call(
        ["cloudformation", "delete-stack", "--stack-name", "ccproj"],
        "Remove rolled-back initial stack metadata after empty-resource cleanup",
    )
    run(
        ["cloudformation", "wait", "stack-delete-complete", "--stack-name", "ccproj"],
        "Wait before recreating corrected project stack",
    )
    (ROOT / "docs" / "failed-create-cleanup.json").write_text(
        json.dumps(
            {
                "stackId": stack["StackId"],
                "retainedResourcesCleaned": retained,
                "note": "All tables/pools/buckets were checked empty; KMS deletion uses AWS's seven-day pending window.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
