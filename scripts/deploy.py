"""Deploy CloudFormation and seed initial accounts with an append-only CLI record."""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from scripts.aws_cli import call, run
from scripts.package import package
from scripts.preflight import preflight
from scripts.update_simulator import update_simulator
from scripts.validate import validate

ROOT = Path(__file__).resolve().parents[1]


def outputs(stack):
    record = call(
        ["cloudformation", "describe-stacks", "--stack-name", stack], "Read deployed stack outputs"
    )["Stacks"][0]
    return {item["OutputKey"]: item["OutputValue"] for item in record["Outputs"]}


def deploy_stack(name, template, parameters=None, artifacts=None):
    args = [
        "cloudformation",
        "deploy",
        "--stack-name",
        name,
        "--template-file",
        template,
        "--capabilities",
        "CAPABILITY_IAM",
        "--no-fail-on-empty-changeset",
        "--tags",
        "Project=ccproj",
    ]
    if artifacts:
        args += ["--s3-bucket", artifacts, "--s3-prefix", "templates"]
    if parameters:
        args += ["--parameter-overrides", *[f"{key}={value}" for key, value in parameters.items()]]
    result = run(args, f"Deploy CloudFormation stack {name}", check=False)
    if result.returncode:
        # Retrieve account-aware validation/operation failures rather than only legacy events.
        run(
            ["cloudformation", "describe-events", "--stack-name", name],
            "Inspect deployment and validation failures",
            check=False,
        )
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return outputs(name)


def seed_users(pool):
    for email in ("akshay.kripalani74@nmims.in", "collegeproject@akshaykripalani.com"):
        existing = run(
            ["cognito-idp", "admin-get-user", "--user-pool-id", pool, "--username", email],
            "Inspect required initial account",
            check=False,
            private=True,
        )
        if existing.returncode:
            if "UserNotFoundException" not in existing.stderr:
                raise RuntimeError("Could not inspect required initial account")
            # Cognito generates the temporary password and emails its invitation.
            call(
                [
                    "cognito-idp",
                    "admin-create-user",
                    "--user-pool-id",
                    pool,
                    "--username",
                    email,
                    "--user-attributes",
                    f"Name=email,Value={email}",
                    "--desired-delivery-mediums",
                    "EMAIL",
                ],
                "Create required invited dashboard account",
                private=True,
            )
        for role in ("viewer", "operator"):
            call(
                [
                    "cognito-idp",
                    "admin-add-user-to-group",
                    "--user-pool-id",
                    pool,
                    "--username",
                    email,
                    "--group-name",
                    role,
                ],
                "Assign required initial application roles",
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", default="ccproj")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    validate()
    if args.build_only:
        package()
        return 0
    preflight()
    release = package()
    artifacts = deploy_stack(args.stack + "-artifacts", str(ROOT / "infra" / "bootstrap.json"))[
        "ArtifactBucket"
    ]
    for entry in release.values():
        run(
            ["s3", "cp", entry["path"], f"s3://{artifacts}/{entry['key']}", "--sse", "AES256"],
            "Upload content-addressed release package",
        )
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    budget_file = ROOT / "docs" / (args.stack + "-budget-period.json")
    if budget_file.exists():
        budget = json.loads(budget_file.read_text())
    else:
        budget = {
            "start": int(dt.datetime.now(dt.timezone.utc).timestamp()),
            "end": int(dt.datetime(2027, 3, 16, tzinfo=dt.timezone.utc).timestamp()),
        }
        budget_file.write_text(json.dumps(budget))
    platform = deploy_stack(
        args.stack,
        str(ROOT / "infra" / "platform.json"),
        {
            "ArtifactBucket": artifacts,
            "BackendKey": release["backend"]["key"],
            "BudgetStart": budget["start"],
            "BudgetEnd": budget["end"],
        },
        artifacts,
    )
    seed_users(platform["UserPoolId"])
    web_config = {
        "apiUrl": platform["ApiUrl"],
        "clientId": platform["ClientId"],
        "userPoolId": platform["UserPoolId"],
        "loginDomain": platform["LoginDomain"],
        "callbackUrl": platform["DashboardUrl"] + "/callback",
        "logoutUrl": platform["DashboardUrl"] + "/",
        "region": "ap-southeast-2",
    }
    config = runtime / "config.json"
    config.write_text(json.dumps(web_config, indent=2) + "\n")
    run(
        [
            "s3",
            "cp",
            str(config),
            f"s3://{platform['FrontendBucket']}/config.json",
            "--content-type",
            "application/json",
            "--cache-control",
            "no-store",
            "--sse",
            "AES256",
        ],
        "Publish non-secret frontend integration configuration",
    )
    run(
        [
            "s3",
            "cp",
            str(ROOT / "hosting" / "index.html"),
            f"s3://{platform['FrontendBucket']}/index.html",
            "--content-type",
            "text/html",
            "--cache-control",
            "no-cache",
            "--sse",
            "AES256",
        ],
        "Publish AWS deployment landing page for later React integration",
    )
    api_id = platform["ApiUrl"].split("//")[1].split(".")[0]
    simulator = deploy_stack(
        args.stack + "-simulator",
        str(ROOT / "infra" / "simulator.json"),
        {
            "ArtifactBucket": artifacts,
            "SimulatorKey": release["simulator"]["key"],
            "ApiUrl": platform["ApiUrl"],
            "ApiId": api_id,
            "ControlTable": platform["ControlTable"],
        },
        artifacts,
    )
    record = {
        "stack": args.stack,
        "artifacts": artifacts,
        "platform": platform,
        "simulator": simulator,
        "release": release,
        "budgetPeriod": budget,
    }
    (runtime / "deployment.json").write_text(json.dumps(record, indent=2) + "\n")
    (ROOT / "docs" / (args.stack + "-deployment.json")).write_text(
        json.dumps(record, indent=2) + "\n"
    )
    update_simulator(simulator["InstanceId"], artifacts, release["simulator"]["key"])
    print("Deployment completed. Run live E2E tests and confirm the SNS email subscription.")
    print(platform["DashboardUrl"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
