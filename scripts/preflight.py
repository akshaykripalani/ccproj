"""Read-only access evidence, with every AWS command appended to the audit file."""
import concurrent.futures
import json
from pathlib import Path
import sys

from scripts.aws_cli import identity, run

CHECKS = [
    ["cloudformation", "list-stacks", "--max-items", "1"],
    ["ec2", "describe-instance-type-offerings", "--filters", "Name=instance-type,Values=t4g.micro"],
    ["ssm", "get-parameter", "--name", "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64", "--query", "Parameter.Value"],
    ["lambda", "list-functions", "--max-items", "1"],
    ["apigatewayv2", "get-apis", "--max-results", "1"],
    ["sqs", "list-queues", "--max-results", "1"],
    ["dynamodb", "list-tables", "--limit", "1"],
    ["s3api", "list-buckets", "--query", "Buckets[].Name"],
    ["cognito-idp", "list-user-pools", "--max-results", "1"],
    ["athena", "list-work-groups", "--max-results", "1"],
    ["glue", "get-databases", "--max-results", "1"],
    ["sns", "list-topics", "--max-items", "1"],
    ["logs", "describe-log-groups", "--limit", "1"],
    ["cloudfront", "list-distributions", "--max-items", "1"],
    ["iam", "list-roles", "--max-items", "1"],
    ["cloudtrail", "describe-trails"],
    ["budgets", "describe-budgets", "--account-id", "039379078306", "--max-results", "1"],
    ["kms", "list-keys", "--limit", "1"],
]


def check(args):
    result = run(args, "Preflight: required service access", check=False)
    return {"service": args[0], "exitCode": result.returncode, "allowed": result.returncode == 0, "error": result.stderr.strip() if result.returncode else None}


def preflight():
    active = identity()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(check, CHECKS))
    report = {"account": active["Account"], "identity": active["Arn"], "region": "ap-south-1", "results": results, "note": "Successful reads do not prove create/pass-role permission. CloudFormation change sets and live tests still required."}
    destination = Path(__file__).resolve().parents[1] / "docs" / "access-check.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failures = [r["service"] for r in results if not r["allowed"]]
    for result in results:
        print(result["service"], "ALLOWED" if result["allowed"] else "DENIED")
    if failures:
        raise RuntimeError("Deployment preflight blocked: " + ", ".join(failures))
    return report


def main():
    try:
        preflight()
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
