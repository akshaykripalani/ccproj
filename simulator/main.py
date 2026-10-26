"""One factory gateway, three motors, independently polled demo controls."""

import argparse
import json
import logging
import os
import random
import threading
import urllib.error
import urllib.request
import uuid

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config

from backend.domain import DEVICES, MODES, canonical, native, timestamp, utcnow
from backend.equipment import DEFAULT_PROFILE, validate_profile
from simulator.equipment import Equipment as Motor

log = logging.getLogger("simulator")


def signed_request(url, payload, session, region="ap-southeast-2"):
    data = canonical(payload).encode()
    request = AWSRequest(
        method="POST", url=url, data=data, headers={"Content-Type": "application/json"}
    )
    SigV4Auth(session.get_credentials().get_frozen_credentials(), "execute-api", region).add_auth(
        request
    )
    with urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=dict(request.headers), method="POST"),
        timeout=12,
    ) as result:
        return result.status, json.loads(result.read())


class Gateway:
    def __init__(self, control_table, session, seed=42):
        self.table = control_table
        self.session = session
        self.run_id = uuid.uuid4().hex
        self.modes = {device: "normal" for device in DEVICES}
        self.profiles = {device: dict(DEFAULT_PROFILE) for device in DEVICES}
        self.interval = 10
        self.motors = [Motor(device, random.Random(seed + i)) for i, device in enumerate(DEVICES)]
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def initialize(self):
        now = timestamp(utcnow())
        self.table.put_item(
            Item={"pk": "GATEWAY", "sk": "RUN", "runId": self.run_id, "startedAt": now}
        )
        for device in DEVICES:
            previous = self.table.get_item(Key={"pk": device, "sk": "CONTROL"}).get("Item", {})
            self.profiles[device] = validate_profile(previous.get("profile", {}))
            self.table.put_item(
                Item={
                    "profile": native(self.profiles[device]),
                    "pk": device,
                    "sk": "CONTROL",
                    "runId": self.run_id,
                    "requestId": f"startup-{self.run_id}-{device}",
                    "requestedMode": "normal",
                    "appliedMode": "normal",
                    "requestedAt": now,
                    "appliedAt": now,
                    "status": "applied",
                }
            )

    def apply(self, record):
        if record.get("runId") != self.run_id:
            return False
        device = record["pk"]
        mode = record.get("requestedMode")
        if device not in self.modes or mode not in MODES:
            return False
        try:
            self.table.update_item(
                Key={"pk": device, "sk": "CONTROL"},
                ConditionExpression=Attr("requestId").eq(record["requestId"])
                & Attr("runId").eq(self.run_id),
                UpdateExpression="SET appliedMode = :mode, appliedAt = :at, #status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":mode": mode,
                    ":at": timestamp(utcnow()),
                    ":status": "applied",
                },
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        with self.lock:
            self.modes[device] = "normal" if mode == "repair" else mode
            self.profiles[device] = validate_profile(record.get("profile", {}))
            if mode in ("normal", "repair"):
                next(m for m in self.motors if m.device == device).reset()
        return True

    def poll(self):
        while not self.stop.is_set():
            try:
                for device in DEVICES:
                    record = self.table.get_item(
                        Key={"pk": device, "sk": "CONTROL"}, ConsistentRead=True
                    ).get("Item")
                    if record and record.get("status") != "applied":
                        self.apply(record)
            except Exception as exc:
                log.warning(
                    "Control polling failed (%s); retaining current modes", type(exc).__name__
                )
            self.stop.wait(5)

    def readings(self):
        result = []
        with self.lock:
            for motor in self.motors:
                reading = motor.sample(
                    self.modes[motor.device],
                    self.run_id,
                    self.profiles[motor.device],
                    self.interval,
                )
                if reading:
                    result.append(reading)
                if motor.completed_cooldown:
                    motor.completed_cooldown = False
                    existing = self.table.get_item(
                        Key={"pk": motor.device, "sk": "CONTROL"}, ConsistentRead=True
                    ).get("Item", {})
                    if existing.get("requestedMode") == "cooldown":
                        try:
                            self.table.update_item(
                                Key={"pk": motor.device, "sk": "CONTROL"},
                                ConditionExpression=Attr("requestId").eq(existing["requestId"]),
                                UpdateExpression="SET requestedMode = :mode, appliedMode = :mode, maintenanceAction = :action, maintenanceAt = :at",
                                ExpressionAttributeValues={
                                    ":mode": "normal",
                                    ":action": "Restarted automatically",
                                    ":at": timestamp(utcnow()),
                                },
                            )
                            self.modes[motor.device] = "normal"
                        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                            pass
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api-url", default=os.environ.get("API_URL"), required=not os.environ.get("API_URL")
    )
    parser.add_argument(
        "--control-table",
        default=os.environ.get("CONTROL_TABLE"),
        required=not os.environ.get("CONTROL_TABLE"),
    )
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-scenario", choices=("stopped", "duplicate", "invalid", "burst"))
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.interval < 1 or args.interval > 60:
        parser.error("interval must be 1-60 seconds")
    if args.test_scenario == "burst" and not args.max_batches:
        parser.error("burst requires --max-batches to bound test traffic")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = boto3.Session(region_name=args.region)
    config = Config(
        retries={"mode": "standard", "total_max_attempts": 3}, connect_timeout=3, read_timeout=5
    )
    gateway = Gateway(
        session.resource("dynamodb", config=config).Table(args.control_table), session, args.seed
    )
    gateway.interval = args.interval
    gateway.initialize()
    if args.test_scenario == "stopped":
        gateway.modes["motor-01"] = "stopped"
    worker = threading.Thread(target=gateway.poll, daemon=True)
    worker.start()
    pending = None
    sent = 0
    failures = 0
    log.info("Factory gateway started run=%s; all motors normal", gateway.run_id)
    try:
        while not gateway.stop.is_set() and (not args.max_batches or sent < args.max_batches):
            if pending is None:
                pending = {"readings": gateway.readings()}
                if not pending["readings"]:
                    pending = None
                    gateway.stop.wait(args.interval)
                    continue
                if args.test_scenario == "invalid":
                    pending["readings"][0]["temperatureC"] = "invalid"
            try:
                status, result = signed_request(
                    args.api_url.rstrip("/") + "/telemetry", pending, session, args.region
                )
                if status != 202:
                    raise RuntimeError("Telemetry was not accepted")
                if args.test_scenario == "duplicate":
                    signed_request(
                        args.api_url.rstrip("/") + "/telemetry", pending, session, args.region
                    )
                sent += 1
                pending = None
                failures = 0
                log.info("Telemetry accepted batches=%s", sent)
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code != 429:
                    log.error("Non-retryable telemetry rejection status=%s", exc.code)
                    if args.test_scenario == "invalid" and exc.code == 400:
                        return 0
                    return 1
                failures += 1
                log.warning(
                    "Telemetry throttled/unavailable status=%s; retrying stable event IDs", exc.code
                )
            except Exception as exc:
                failures += 1
                log.warning(
                    "Telemetry transmission failed (%s); retrying stable event IDs",
                    type(exc).__name__,
                )
            gateway.stop.wait(min(60, 2 ** min(failures, 5)) if failures else args.interval)
    except KeyboardInterrupt:
        log.info("Simulator interrupted")
    finally:
        gateway.stop.set()
        worker.join(timeout=6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
