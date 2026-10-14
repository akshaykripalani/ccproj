"""All operator AWS CLI calls go through this append-only, secret-safe logger."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
AWS = os.environ.get("CCPROJ_AWS_CLI", r"C:\Users\aksha\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe")
REGION = "ap-south-1"
ACCOUNT = "039379078306"
SENSITIVE = {"--password", "--temporary-password", "--auth-parameters", "--challenge-responses", "--secret-access-key", "--session-token", "--access-token", "--refresh-token"}


def append(line):
    with (ROOT / "AWS_COMMANDS.txt").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def run(args, purpose, *, check=True, private=False):
    args = [str(x) for x in args]
    if any(flag in args for flag in SENSITIVE):
        raise ValueError("Secret-bearing flags are forbidden; use a private input file and private=True")
    if "--region" not in args:
        args += ["--region", REGION]
    args += ["--no-cli-pager"]
    operation_id = uuid.uuid4().hex[:12]
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    append(f"\n[{stamp}] {operation_id} {purpose}\nCOMMAND argv: " + json.dumps([AWS, *args]))
    env = dict(os.environ, AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
    result = subprocess.run([AWS, *args], capture_output=True, text=True, encoding="utf-8", env=env)
    # Never log command output: it can contain tokens or temporary credentials.
    append(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {operation_id} EXIT {result.returncode}" + (" (private response withheld)" if private else ""))
    if check and result.returncode:
        raise RuntimeError(f"AWS command {operation_id} failed ({result.returncode}): " + ("private output withheld" if private else result.stderr.strip()))
    return result


def call(args, purpose, **kwargs):
    result = run(args, purpose, **kwargs)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def identity():
    result = call(["sts", "get-caller-identity"], "Verify deployment identity")
    if result["Account"] != ACCOUNT:
        raise RuntimeError("Refusing to deploy into an unexpected AWS account")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--purpose", required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    params = parser.parse_args()
    args = params.args[1:] if params.args[:1] == ["--"] else params.args
    result = run(args, params.purpose, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
