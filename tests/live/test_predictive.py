"""Demonstrate learned warnings, thermal recovery and explicit mechanical repair on AWS."""

import json
import time

import pytest

from backend.equipment import default_profile
from tests.live.conftest import PROJECT, wait_for

pytestmark = pytest.mark.live


def profile(live, device, fault, enabled=True, minutes=10, speed=10):
    result = live.api(
        "POST",
        "/profiles/" + device,
        {"enabled": enabled, "failureAfterMinutes": minutes, "faultMode": fault, "speed": speed},
    )
    assert result.status_code == 202, result.text
    wait_for(lambda: live.state(device)["control"]["status"] == "applied", timeout=40)


def restore_default(live, device):
    saved = default_profile(device)
    profile(
        live,
        device,
        saved["faultMode"],
        saved["enabled"],
        saved["failureAfterMinutes"],
        saved["speed"],
    )


def test_predictive_maintenance_live(live, record_property):
    evidence = {"model": live.api("GET", "/model").json(), "scenarios": []}
    assert evidence["model"]["version"].startswith("rf-")
    assert (
        live.api("POST", "/profiles/pump-01", {"enabled": True}, role="viewer").status_code == 403
    )
    try:
        # Isolate a bounded demonstration from unattended profiles on other assets.
        for device in live.api("GET", "/devices").json()["devices"]:
            profile(live, device["deviceId"], "overheat", enabled=False, speed=1)
        for device, kind in (("pump-01", "overheat"), ("compressor-01", "vibration")):
            profile(live, device, kind)
            warning = wait_for(
                lambda device=device: (
                    s
                    if (s := live.state(device)).get("prediction", {}).get("warning")
                    and not any(r["active"] for r in s["latest"]["rules"].values())
                    else None
                ),
                timeout=140,
                interval=2,
            )
            warning_time = warning["prediction"]["sourceObservedAt"]

            def fault_state(device=device):
                current = live.state(device)
                return (
                    current
                    if any(rule["active"] for rule in current["latest"]["rules"].values())
                    else None
                )

            fault = wait_for(fault_state, timeout=120, interval=2)
            assert warning_time < fault["latest"]["observedAt"]
            scenario = {
                "deviceId": device,
                "kind": kind,
                "warningObservedAt": warning_time,
                "faultObservedAt": fault["latest"]["observedAt"],
                "riskScore": warning["prediction"]["riskScore"],
                "modelVersion": warning["prediction"]["modelVersion"],
            }
            if kind == "overheat":
                recovered = wait_for(
                    lambda device=device: (
                        s
                        if (s := live.state(device))["control"].get("maintenanceAction")
                        == "Restarted automatically"
                        and not any(r["active"] for r in s["latest"]["rules"].values())
                        and s["latest"]["operatingState"] == "running"
                        else None
                    ),
                    timeout=150,
                    interval=3,
                )
                scenario["outcome"] = recovered["control"]["maintenanceAction"]
            else:
                needed = wait_for(
                    lambda device=device: (
                        s
                        if (s := live.state(device))["control"].get("maintenanceAction")
                        == "Repair needed"
                        else None
                    ),
                    timeout=40,
                )
                assert needed["latest"]["operatingState"] == "stopped"
                time.sleep(12)
                assert live.state(device)["latest"]["rules"]["vibration"]["active"]
                result = live.api("POST", "/controls/" + device, {"mode": "repair"})
                assert result.status_code == 202
                wait_for(
                    lambda device=device: (
                        not live.state(device)["latest"]["rules"]["vibration"]["active"]
                    ),
                    timeout=70,
                )
                scenario["outcome"] = "Manual repair restored operation"
            evidence["scenarios"].append(scenario)
            profile(live, device, kind, enabled=False, speed=1)
        events = live.api("GET", "/maintenance").json()["events"]
        actions = {event["action"] for event in events}
        assert {
            "Fault predicted",
            "Cooling down",
            "Restarted automatically",
            "Repair needed",
            "Repaired",
        } <= actions
        evidence["maintenanceEvents"] = events
        devices = live.api("GET", "/devices").json()["devices"]
        assert len(devices) == 7 and all(device["online"] for device in devices)
        assert (
            "outputPowerWatts"
            in next(d for d in devices if d["deviceId"] == "generator-01")["latest"]["metrics"]
        )
    finally:
        # Leave the agreed profiles enabled at normal speed; no scheduled shutdown.
        for device in (
            "motor-01",
            "motor-02",
            "motor-03",
            "pump-01",
            "compressor-01",
            "fan-01",
            "generator-01",
        ):
            restore_default(live, device)
        (PROJECT / "docs/predictive-live-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    record_property("predictive_scenarios", len(evidence["scenarios"]))


def test_persistent_cooldown_is_bounded(live):
    device = "pump-01"
    try:
        profile(live, device, "persistent_overheat")

        def escalation():
            state = live.state(device)
            return state if state["control"].get("maintenanceAction") == "Repair needed" else None

        failed = wait_for(escalation, timeout=300, interval=4)
        assert failed["latest"]["operatingState"] == "stopped"
        assert failed["latest"]["temperatureC"] > 75
        request = failed["control"]["requestId"]
        time.sleep(12)
        assert live.state(device)["control"]["requestId"] == request
        assert live.api("POST", "/controls/" + device, {"mode": "repair"}).status_code == 202
        wait_for(
            lambda: not live.state(device)["latest"]["rules"]["temperature"]["active"], timeout=80
        )
        (PROJECT / "docs/predictive-persistent-evidence.json").write_text(
            json.dumps(
                {
                    "deviceId": device,
                    "outcome": "Stopped, escalated once, required manual repair",
                    "cooldownRequestId": request,
                    "requestedAt": failed["control"]["requestedAt"],
                    "escalationObservedAt": failed["latest"]["observedAt"],
                    "temperatureAtEscalation": failed["latest"]["temperatureC"],
                    "automaticRestartSuppressed": True,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        restore_default(live, device)


def test_thermal_recovery_after_manual_repair(live):
    device = "fan-01"
    try:
        profile(live, device, "overheat")
        assert live.api("POST", "/controls/" + device, {"mode": "repair"}).status_code == 202
        wait_for(lambda: live.state(device)["control"]["status"] == "applied", timeout=40)
        repaired = live.state(device)["control"]
        assert repaired["requestedMode"] == "repair"

        def restarted():
            state = live.state(device)
            return (
                state
                if state["control"].get("maintenanceAction") == "Restarted automatically"
                else None
            )

        recovered = wait_for(restarted, timeout=200, interval=3)
        wait_for(
            lambda: not live.state(device)["latest"]["rules"]["temperature"]["active"], timeout=60
        )
        (PROJECT / "docs/predictive-after-repair-evidence.json").write_text(
            json.dumps(
                {
                    "deviceId": device,
                    "repairRequestId": repaired["requestId"],
                    "subsequentRecoveryRequestId": recovered["control"]["requestId"],
                    "outcome": "A new natural thermal episode after manual repair cooled and restarted automatically",
                    "modelVersion": recovered["prediction"]["modelVersion"],
                    "recoveryAt": recovered["control"]["maintenanceAt"],
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        restore_default(live, device)
