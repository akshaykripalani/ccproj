"""Apply a release through SSM; instance user data alone does not rerun on updates."""

import json
import time
from pathlib import Path

from scripts.aws_cli import call, run

ROOT = Path(__file__).resolve().parents[1]


def update_simulator(instance, artifacts, key):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = call(
            [
                "ssm",
                "describe-instance-information",
                "--filters",
                f"Key=InstanceIds,Values={instance}",
            ],
            "Wait for SSM-managed simulator readiness",
        )
        if (
            result["InstanceInformationList"]
            and result["InstanceInformationList"][0]["PingStatus"] == "Online"
        ):
            break
        time.sleep(10)
    else:
        raise RuntimeError("Simulator did not become available through SSM within ten minutes")
    commands = [
        "set -e",
        "test -f /etc/systemd/system/ccproj-simulator.service",
        "sudo systemctl stop ccproj-simulator",
        "trap 'sudo systemctl start ccproj-simulator' EXIT",
        f"aws s3 cp 's3://{artifacts}/{key}' /tmp/ccproj-update.tar.gz --region ap-southeast-2",
        "sudo tar -xzf /tmp/ccproj-update.tar.gz -C /opt/ccproj",
        "sudo /opt/ccproj/venv/bin/pip install --no-index --find-links /opt/ccproj/wheels -r /opt/ccproj/requirements-runtime.txt",
        "sudo chown -R ccproj:ccproj /opt/ccproj",
        "sudo systemctl start ccproj-simulator",
    ]
    location = ROOT / ".runtime" / "update-simulator.json"
    location.parent.mkdir(exist_ok=True)
    location.write_text(
        json.dumps(
            {
                "InstanceIds": [instance],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": commands},
            }
        )
    )
    result = call(
        ["ssm", "send-command", "--cli-input-json", "file://" + str(location)],
        "Apply content-addressed simulator release via SSM",
    )
    command = result["Command"]["CommandId"]
    run(
        ["ssm", "wait", "command-executed", "--command-id", command, "--instance-id", instance],
        "Wait for supervised simulator release update",
    )
