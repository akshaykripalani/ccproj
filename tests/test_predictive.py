import datetime as dt
import json
import random
from pathlib import Path

import boto3
import pytest

from backend import api, predictor
from backend.aws_support import get_item
from backend.domain import DEVICES, evolve, native, timestamp, utcnow, validate_reading
from backend.equipment import CATALOG, default_profile, validate_profile
from backend.features import features, score
from simulator.equipment import Equipment
from simulator.main import Gateway
from tests.conftest import api_event
from tests.test_api_controls import create_directory

ROOT = Path(__file__).resolve().parents[1]


def model():
    release = json.loads((ROOT / "models/release.json").read_text())
    return json.loads((ROOT / release["modelPath"]).read_text())


def test_all_equipment_types_emit_valid_type_specific_telemetry():
    assert len(DEVICES) == 7
    assert len({item["type"] for item in CATALOG.values()}) == 5
    for device in DEVICES:
        reading = Equipment(device, random.Random(42)).sample("normal", "test")
        assert validate_reading(reading) == reading
    assert (
        "flowLitresMin"
        in Equipment("pump-01", random.Random(1)).sample("normal", "test")["metrics"]
    )
    assert (
        "outputPowerWatts"
        in Equipment("generator-01", random.Random(1)).sample("normal", "test")["metrics"]
    )


def test_default_fleet_has_three_manual_two_thermal_and_two_mechanical_profiles(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    for device in DEVICES:
        profile = get_item(aws["controls"], device, "CONTROL")["profile"]
        assert profile == default_profile(device)
        if device.startswith("motor-"):
            assert not profile["enabled"]
            machine = Equipment(device, random.Random(42))
            for _ in range(720):
                row = machine.sample("normal", "unattended")
                assert row["temperatureC"] < 75 and row["vibrationMmS"] < 4.5
                assert row["operatingState"] == "running"
            for _ in range(5):
                row = machine.sample("vibration", "manual")
            assert row["operatingState"] == "stopped"
        else:
            assert profile["enabled"]
            assert profile["faultMode"] == (
                "overheat" if device in ("pump-01", "fan-01") else "vibration"
            )


@pytest.mark.parametrize(
    "profile",
    [
        {"speed": 100},
        {"failureAfterMinutes": 0},
        {"enabled": "yes"},
        {"faultMode": "unknown"},
        {"secret": "bad"},
    ],
)
def test_invalid_profiles_are_rejected(profile):
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_model_warns_before_unseen_mechanical_and_thermal_failures():
    artifact = model()
    for kind in ("overheat", "vibration"):
        machine = Equipment("pump-01", random.Random(8765))
        window, warned, failed = [], False, False
        for _ in range(240):
            row = machine.sample(
                "normal",
                "unseen",
                {"enabled": True, "faultMode": kind, "failureAfterMinutes": 30, "speed": 1},
            )
            window = [r for r in window if row["simulationTime"] - r["simulationTime"] <= 120] + [
                row
            ]
            if row["temperatureC"] > 75 or row["vibrationMmS"] > 4.5:
                failed = True
                break
            if (
                len(window) > 1
                and score(artifact, features(window, "pump-01"))[0] >= artifact["riskThreshold"]
            ):
                warned = True
        assert failed and warned


def test_mechanical_latch_requires_manual_reset_and_thermal_cooldown_recovers():
    machine = Equipment("motor-01", random.Random(1))
    for _ in range(5):
        machine.sample("vibration", "test", {"enabled": False})
    for _ in range(5):
        row = machine.sample("normal", "test", {"enabled": False})
    assert row["operatingState"] == "stopped" and row["vibrationMmS"] > 4.5
    machine.reset()
    for _ in range(6):
        row = machine.sample("normal", "test", {"enabled": False})
    assert row["operatingState"] == "running" and row["vibrationMmS"] < 4.5
    for _ in range(4):
        machine.sample("overheat", "test")
    for _ in range(10):
        machine.sample("cooldown", "test", {"enabled": False})
        if machine.completed_cooldown:
            break
    assert machine.completed_cooldown and machine.temperature < 65


def test_profile_permission_and_new_device_routes(aws, monkeypatch):
    create_directory(monkeypatch)
    profile = {"enabled": True, "speed": 10, "failureAfterMinutes": 30, "faultMode": "vibration"}
    assert (
        api.handler(api_event("POST", "/profiles/pump-01", payload=profile), None)["statusCode"]
        == 403
    )
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    result = api.handler(api_event("POST", "/profiles/pump-01", "operator", profile), None)
    assert result["statusCode"] == 202
    assert gateway.apply(json.loads(result["body"]))
    assert gateway.profiles["pump-01"]["speed"] == 10
    assert api.handler(api_event("GET", "/devices/pump-01"), None)["statusCode"] == 200
    assert api.handler(api_event("GET", "/devices/unknown-01"), None)["statusCode"] == 400


def test_bounded_auto_repair_respects_superseding_operator_commands(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    control = get_item(aws["controls"], "motor-01", "CONTROL")
    now = utcnow()
    state = {
        "rules": {"temperature": {"active": True, "alertId": "thermal-1"}},
        "simulationSpeed": 10,
        "temperatureC": 95,
    }
    predictor.maintenance("motor-01", state, control, now)
    cooling = get_item(aws["controls"], "motor-01", "CONTROL")
    assert cooling["requestedMode"] == "cooldown" and cooling["maintenanceAction"] == "Cooling down"
    assert gateway.apply(cooling)
    assert get_item(aws["controls"], "motor-01", "CONTROL")["status"] == "applied"
    cooling["status"] = "applied"
    predictor.maintenance("motor-01", state, cooling, now + dt.timedelta(seconds=130))
    assert get_item(aws["controls"], "motor-01", "CONTROL")["maintenanceAction"] == "Repair needed"
    operator = api.request_control("motor-01", "repair", {"sub": "operator"})
    predictor.maintenance("motor-01", state, control, now)
    assert get_item(aws["controls"], "motor-01", "CONTROL")["requestId"] == operator["requestId"]


def test_old_or_duplicate_predictions_do_not_overwrite_newer_result(aws):
    machine = Equipment("motor-01", random.Random(8))
    state = None
    for index in range(5):
        row = machine.sample("normal", "test")
        row["observedAt"] = timestamp(utcnow() - dt.timedelta(seconds=50 - index * 10))
        state, _ = evolve(state, row, timestamp(utcnow()))
    aws["data"].put_item(Item=native({**state, "pk": "motor-01", "sk": "STATE"}))
    first = predictor.predict_device("motor-01", model())
    second = predictor.predict_device("motor-01", model())
    assert first["status"] == "scored" and second["status"] == "already_scored"


def test_feature_window_does_not_accept_out_of_order_measurements():
    machine = Equipment("motor-01", random.Random(10))
    first = machine.sample("normal", "test")
    newer = {
        **machine.sample("normal", "test"),
        "observedAt": timestamp(utcnow() + dt.timedelta(seconds=10)),
    }
    state, _ = evolve(None, newer, timestamp(utcnow()))
    after, _ = evolve(state, first, timestamp(utcnow()))
    assert after["featureWindow"] == state["featureWindow"]


def test_new_thermal_episode_after_manual_repair_still_cools_automatically(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    repaired = api.request_control("motor-01", "repair", {"sub": "operator"})
    assert gateway.apply(repaired)
    control = get_item(aws["controls"], "motor-01", "CONTROL")
    assert control["requestedMode"] == "repair" and control["status"] == "applied"
    state = {
        "rules": {"temperature": {"active": True, "alertId": "new-thermal-after-repair"}},
        "simulationSpeed": 1,
        "temperatureC": 95,
    }
    predictor.maintenance("motor-01", state, control, utcnow())
    cooling = get_item(aws["controls"], "motor-01", "CONTROL")
    assert cooling["requestedMode"] == "cooldown" and cooling["maintenanceAction"] == "Cooling down"


@pytest.mark.parametrize("rule", ["temperature", "vibration"])
def test_pre_repair_telemetry_cannot_reassert_a_fault_after_repair(aws, rule):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    repaired = api.request_control("motor-01", "repair", {"sub": "operator"})
    assert gateway.apply(repaired)
    control = get_item(aws["controls"], "motor-01", "CONTROL")
    applied = dt.datetime.fromisoformat(control["appliedAt"].replace("Z", "+00:00"))
    state = {
        "observedAt": timestamp(applied - dt.timedelta(seconds=1)),
        "rules": {rule: {"active": True, "alertId": "pre-repair-fault"}},
        "temperatureC": 95,
    }
    predictor.maintenance("motor-01", state, control, applied)
    assert get_item(aws["controls"], "motor-01", "CONTROL") == control
    # A real later thermal/mechanical episode must still trigger its maintenance path.
    state["observedAt"] = timestamp(applied + dt.timedelta(seconds=10))
    predictor.maintenance("motor-01", state, control, applied + dt.timedelta(seconds=10))
    updated = get_item(aws["controls"], "motor-01", "CONTROL")
    assert updated["maintenanceAction"] == (
        "Cooling down" if rule == "temperature" else "Repair needed"
    )


def test_healthy_running_telemetry_clears_stale_repair_label(aws):
    gateway = Gateway(aws["controls"], boto3.Session(region_name="ap-southeast-2"))
    gateway.initialize()
    control = get_item(aws["controls"], "motor-01", "CONTROL")
    control.update(
        maintenanceAction="Repair needed",
        maintenanceEpisode="old-mechanical",
        maintenanceAt=control["appliedAt"],
    )
    aws["controls"].put_item(Item=control)
    state = {"observedAt": timestamp(utcnow()), "operatingState": "running", "rules": {}}
    predictor.maintenance("motor-01", state, control, utcnow())
    updated = get_item(aws["controls"], "motor-01", "CONTROL")
    assert "maintenanceAction" not in updated
    assert updated["requestId"] == control["requestId"]
    # A stale invocation must not clear a label belonging to a newer fault episode.
    aws["controls"].put_item(Item={**control, "maintenanceEpisode": "new-mechanical"})
    predictor.maintenance("motor-01", state, control, utcnow())
    assert (
        get_item(aws["controls"], "motor-01", "CONTROL")["maintenanceEpisode"] == "new-mechanical"
    )
