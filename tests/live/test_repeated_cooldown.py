"""Exercise two unattended thermal recovery cycles on every deployed asset."""

import json

import pytest

from backend.equipment import default_profile
from tests.live.conftest import PROJECT, wait_for
from tests.live.test_predictive import profile, restore_default

pytestmark = pytest.mark.live


def test_apply_approved_default_fleet_profiles(live):
    devices = live.api("GET", "/devices").json()["devices"]
    for device in devices:
        restore_default(live, device["deviceId"])

    def applied():
        rows = live.api("GET", "/devices").json()["devices"]
        return rows if all(row["control"]["status"] == "applied" for row in rows) else None

    final = wait_for(applied, timeout=45)
    assert all(row["profile"] == default_profile(row["deviceId"]) for row in final)


def test_all_seven_assets_repeat_automatic_cooldown(live):
    initial = live.api("GET", "/devices").json()["devices"]
    original = {device["deviceId"]: device["profile"] for device in initial}
    recoveries = {device: {} for device in original}
    try:
        for device in original:
            profile(live, device, "overheat", minutes=10, speed=10)

        def two_cycles():
            devices = live.api("GET", "/devices").json()["devices"]
            for item in devices:
                control = item["control"]
                assert control.get("maintenanceAction") != "Repair needed", item["deviceId"]
                if control.get("maintenanceAction") == "Restarted automatically":
                    recoveries[item["deviceId"]][control["requestId"]] = control["maintenanceAt"]
            return devices if all(len(cycles) >= 2 for cycles in recoveries.values()) else None

        final = wait_for(two_cycles, timeout=300, interval=5)
        (PROJECT / "docs/repeated-cooldown-live-evidence.json").write_text(
            json.dumps(
                {
                    "outcome": "All seven assets automatically recovered twice without manual repair",
                    "recoveries": recoveries,
                    "modelVersion": final[0]["prediction"]["modelVersion"],
                    "profile": {"faultMode": "overheat", "failureAfterMinutes": 10, "speed": 10},
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        for device, saved in original.items():
            # API numeric serialization can return 1.0; profile validation expects
            # an integer speed, matching the browser's JSON.stringify output.
            result = live.api(
                "POST", "/profiles/" + device, {**saved, "speed": int(saved["speed"])}
            )
            assert result.status_code == 202, result.text
        wait_for(
            lambda: all(
                item["control"]["status"] == "applied"
                for item in live.api("GET", "/devices").json()["devices"]
            ),
            timeout=45,
        )
