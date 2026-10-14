"""One factory gateway, three motors, independently polled demo controls."""
import argparse
import json
import logging
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config

from backend.domain import DEVICES, canonical, native, timestamp, utcnow

log = logging.getLogger("simulator")


def signed_request(url, payload, session, region="ap-south-1"):
    data = canonical(payload).encode()
    request = AWSRequest(method="POST", url=url, data=data, headers={"Content-Type": "application/json"})
    SigV4Auth(session.get_credentials().get_frozen_credentials(), "execute-api", region).add_auth(request)
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=dict(request.headers), method="POST"), timeout=12) as result:
        return result.status, json.loads(result.read())


class Motor:
    def __init__(self, device, randomizer):
        self.device = device
        self.random = randomizer
        self.temperature = 52.0
        self.vibration = 1.5
        self.power = 420.0
        self.sequence = 0

    def sample(self, mode, run_id):
        self.sequence += 1
        if mode == "disconnect":
            return None
        target_temperature = 95.0 if mode == "overheat" else 52.0
        target_vibration = 7.0 if mode == "vibration" else 1.5
        self.temperature += (target_temperature - self.temperature) * 0.7 + self.random.uniform(-0.4, 0.4)
        self.vibration += (target_vibration - self.vibration) * 0.7 + self.random.uniform(-0.08, 0.08)
        self.power += (420.0 - self.power) * 0.2 + self.random.uniform(-4, 4)
        return {"schemaVersion": 1, "eventId": f"{run_id}:{self.device}:{self.sequence}", "deviceId": self.device, "observedAt": timestamp(utcnow()), "temperatureC": round(self.temperature, 2), "vibrationMmS": round(self.vibration, 3), "powerWatts": 0 if mode == "stopped" else round(self.power, 2), "operatingState": "stopped" if mode == "stopped" else "running"}


class Gateway:
    def __init__(self, control_table, session, seed=42):
        self.table = control_table
        self.session = session
        self.run_id = uuid.uuid4().hex
        self.modes = {device: "normal" for device in DEVICES}
        self.motors = [Motor(device, random.Random(seed + i)) for i, device in enumerate(DEVICES)]
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def initialize(self):
        now = timestamp(utcnow())
        self.table.put_item(Item={"pk": "GATEWAY", "sk": "RUN", "runId": self.run_id, "startedAt": now})
        for device in DEVICES:
            self.table.put_item(Item={"pk": device, "sk": "CONTROL", "runId": self.run_id, "requestId": f"startup-{self.run_id}-{device}", "requestedMode": "normal", "appliedMode": "normal", "requestedAt": now, "appliedAt": now, "status": "applied"})

    def apply(self, record):
        if record.get("runId") != self.run_id:
            return False
        device = record["pk"]
        mode = record.get("requestedMode")
        if device not in self.modes or mode not in ("normal", "overheat", "vibration", "disconnect"):
            return False
        try:
            self.table.update_item(Key={"pk": device, "sk": "CONTROL"}, ConditionExpression=Attr("requestId").eq(record["requestId"]) & Attr("runId").eq(self.run_id), UpdateExpression="SET appliedMode = :mode, appliedAt = :at, #status = :status", ExpressionAttributeNames={"#status": "status"}, ExpressionAttributeValues={":mode": mode, ":at": timestamp(utcnow()), ":status": "applied"})
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        with self.lock:
            self.modes[device] = mode
        return True

    def poll(self):
        while not self.stop.is_set():
            try:
                for device in DEVICES:
                    record = self.table.get_item(Key={"pk": device, "sk": "CONTROL"}, ConsistentRead=True).get("Item")
                    if record and record.get("status") != "applied":
                        self.apply(record)
            except Exception as exc:
                log.warning("Control polling failed (%s); retaining current modes", type(exc).__name__)
            self.stop.wait(5)

    def readings(self):
        with self.lock:
            modes = dict(self.modes)
        return [reading for motor in self.motors if (reading := motor.sample(modes[motor.device], self.run_id))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.environ.get("API_URL"), required=not os.environ.get("API_URL"))
    parser.add_argument("--control-table", default=os.environ.get("CONTROL_TABLE"), required=not os.environ.get("CONTROL_TABLE"))
    parser.add_argument("--region", default="ap-south-1")
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
    config = Config(retries={"mode": "standard", "total_max_attempts": 3}, connect_timeout=3, read_timeout=5)
    gateway = Gateway(session.resource("dynamodb", config=config).Table(args.control_table), session, args.seed)
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
                status, result = signed_request(args.api_url.rstrip("/") + "/telemetry", pending, session, args.region)
                if status != 202:
                    raise RuntimeError("Telemetry was not accepted")
                if args.test_scenario == "duplicate":
                    signed_request(args.api_url.rstrip("/") + "/telemetry", pending, session, args.region)
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
                log.warning("Telemetry throttled/unavailable status=%s; retrying stable event IDs", exc.code)
            except Exception as exc:
                failures += 1
                log.warning("Telemetry transmission failed (%s); retrying stable event IDs", type(exc).__name__)
            gateway.stop.wait(min(60, 2 ** min(failures, 5)) if failures else args.interval)
    except KeyboardInterrupt:
        log.info("Simulator interrupted")
    finally:
        gateway.stop.set()
        worker.join(timeout=6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
