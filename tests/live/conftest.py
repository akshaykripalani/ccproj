"""Real AWS fixtures. Never silently turn access failures into passing live tests."""

import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import boto3
import pytest
import requests

from scripts.aws_cli import call, identity, run
from simulator.main import signed_request

PROJECT = Path(__file__).resolve().parents[2]


def private_call(service, operation, payload, purpose):
    # Sensitive inputs live only in a restrictive OS temp directory outside the repo.
    with tempfile.TemporaryDirectory(prefix="ccproj-auth-") as directory:
        location = Path(directory).resolve()
        assert location.parent == Path(tempfile.gettempdir()).resolve()
        if os.name == "nt":
            subprocess.run(
                [
                    "icacls",
                    str(location),
                    "/inheritance:r",
                    "/grant:r",
                    os.environ["USERNAME"] + ":(OI)(CI)F",
                ],
                capture_output=True,
                check=True,
            )
        else:
            location.chmod(0o700)
        file = location / "input.json"
        file.write_text(json.dumps(payload), encoding="utf-8")
        if os.name != "nt":
            file.chmod(0o600)
        return call(
            [service, operation, "--cli-input-json", "file://" + str(file)], purpose, private=True
        )


def wait_for(check, timeout=120, interval=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError(f"Condition did not become true within {timeout} seconds")


class Live:
    def __init__(self, deployment):
        self.deployment = deployment
        self.platform = deployment["platform"]
        self.session = boto3.Session(region_name="ap-south-1")
        self.users = {}
        self.tokens = {}

    def token(self, role):
        if role not in self.tokens or time.monotonic() - self.tokens[role][0] > 240:
            email, password = self.users[role]
            result = private_call(
                "cognito-idp",
                "admin-initiate-auth",
                {
                    "UserPoolId": self.platform["UserPoolId"],
                    "ClientId": self.platform["ClientId"],
                    "AuthFlow": "ADMIN_USER_PASSWORD_AUTH",
                    "AuthParameters": {"USERNAME": email, "PASSWORD": password},
                },
                "Authenticate disposable live-test user (secrets withheld)",
            )
            self.tokens[role] = (time.monotonic(), result["AuthenticationResult"])
        return self.tokens[role][1]

    def api(self, method, path, payload=None, role="operator", **kwargs):
        headers = {"Authorization": "Bearer " + self.token(role)["AccessToken"]} if role else {}
        return requests.request(
            method,
            self.platform["ApiUrl"] + path,
            json=payload,
            headers=headers,
            timeout=20,
            **kwargs,
        )

    def send(self, readings):
        return signed_request(
            self.platform["ApiUrl"] + "/telemetry", {"readings": readings}, self.session
        )

    def state(self, device="motor-01"):
        result = self.api("GET", "/devices/" + device)
        assert result.status_code == 200
        return result.json()

    def service(self, action):
        assert action in ("start", "stop", "restart")
        params = PROJECT / ".runtime" / "service-command.json"
        params.parent.mkdir(exist_ok=True)
        params.write_text(
            json.dumps(
                {
                    "InstanceIds": [self.deployment["simulator"]["InstanceId"]],
                    "DocumentName": "AWS-RunShellScript",
                    "Parameters": {"commands": [f"sudo systemctl {action} ccproj-simulator"]},
                }
            )
        )
        result = call(
            ["ssm", "send-command", "--cli-input-json", "file://" + str(params)],
            "Live test: temporarily " + action + " simulator service",
        )
        command = result["Command"]["CommandId"]
        run(
            [
                "ssm",
                "wait",
                "command-executed",
                "--command-id",
                command,
                "--instance-id",
                self.deployment["simulator"]["InstanceId"],
            ],
            "Wait for simulator service exercise",
        )


@pytest.fixture(scope="session")
def live():
    if os.environ.get("CCPROJ_LIVE") != "1":
        pytest.skip("Live AWS tests require CCPROJ_LIVE=1 and a deployed environment")
    identity()
    deployment = json.loads((PROJECT / ".runtime" / "deployment.json").read_text())
    target = Live(deployment)
    suffix = secrets.token_hex(6)
    try:
        for role in ("viewer", "operator"):
            email = f"ccproj-e2e-{role}-{suffix}@example.invalid"
            password = "Aa1!" + secrets.token_urlsafe(24)
            private_call(
                "cognito-idp",
                "admin-create-user",
                {
                    "UserPoolId": target.platform["UserPoolId"],
                    "Username": email,
                    "MessageAction": "SUPPRESS",
                    "UserAttributes": [{"Name": "email", "Value": email}],
                },
                "Create disposable live-test user without email",
            )
            target.users[role] = (email, password)
            private_call(
                "cognito-idp",
                "admin-set-user-password",
                {
                    "UserPoolId": target.platform["UserPoolId"],
                    "Username": email,
                    "Password": password,
                    "Permanent": True,
                },
                "Set disposable test password (secrets withheld)",
            )
            call(
                [
                    "cognito-idp",
                    "admin-add-user-to-group",
                    "--user-pool-id",
                    target.platform["UserPoolId"],
                    "--username",
                    email,
                    "--group-name",
                    role,
                ],
                "Grant disposable test role",
            )
        yield target
    finally:
        for email, _ in target.users.values():
            call(
                [
                    "cognito-idp",
                    "admin-delete-user",
                    "--user-pool-id",
                    target.platform["UserPoolId"],
                    "--username",
                    email,
                ],
                "Remove only disposable live-test user",
                check=False,
            )


@pytest.fixture
def paused_simulator(live):
    live.service("stop")
    try:
        # Accepted backlog may still contain the final simulator transmission.
        time.sleep(12)
        yield live
    finally:
        live.service("start")
