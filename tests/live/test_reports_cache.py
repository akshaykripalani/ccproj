import datetime as dt
import json
import secrets
import urllib.error

import pytest
import requests

from backend.domain import digest, timestamp, utcnow
from scripts.aws_cli import call, run
from tests.live.conftest import PROJECT, wait_for
from tests.live.test_aws_e2e import measurement

pytestmark = pytest.mark.live


def report(live, kind, day):
    response = live.api(
        "POST", "/reports", {"report": kind, "start": day, "end": day, "deviceId": "motor-03"}
    )
    assert response.status_code == 202
    query = response.json()["reportId"]

    def complete():
        result = live.api("GET", "/reports/" + query).json()
        return result if result.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED") else None

    result = wait_for(complete)
    assert result["status"] == "SUCCEEDED"
    return result["rows"][0] if result["rows"] else {}


def test_signed_invalid_telemetry_is_rejected_before_queueing(live):
    invalid = measurement()
    invalid["temperatureC"] = "invalid"
    with pytest.raises(urllib.error.HTTPError) as rejected:
        live.send([invalid])
    assert rejected.value.code == 400


def test_athena_results_match_known_new_measurements(live):
    observed = utcnow() - dt.timedelta(hours=23)
    day = observed.date().isoformat()
    before = {kind: report(live, kind, day) for kind in ("temperature", "vibration", "power")}
    readings = [
        measurement(
            "motor-03", observed=timestamp(observed + dt.timedelta(seconds=i)), temperature=temp
        )
        for i, temp in enumerate((40, 60, 80))
    ]
    readings[0].update(powerWatts=200)
    readings[1].update(powerWatts=300, vibrationMmS=8)
    readings[2].update(powerWatts=0, operatingState="stopped")
    assert live.send(readings)[0] == 202
    key = f"telemetry/day={day}/{digest(readings)}.json.gz"
    wait_for(
        lambda: (
            call(
                [
                    "s3api",
                    "list-objects-v2",
                    "--bucket",
                    live.platform["ArchiveBucket"],
                    "--prefix",
                    key,
                ],
                "Wait for known-data report archive",
            ).get("KeyCount")
            == 1
        )
    )
    after = {kind: report(live, kind, day) for kind in ("temperature", "vibration", "power")}
    count = int(before["temperature"].get("reading_count", 0))
    average = float(before["temperature"].get("average_temperature_c", 0))
    assert int(after["temperature"]["reading_count"]) == count + 3
    assert float(after["temperature"]["average_temperature_c"]) == pytest.approx(
        (average * count + 180) / (count + 3)
    )
    assert float(after["temperature"]["maximum_temperature_c"]) == max(
        float(before["temperature"].get("maximum_temperature_c", 0)), 80
    )
    assert (
        int(after["vibration"]["breached_readings"])
        == int(before["vibration"].get("breached_readings", 0)) + 1
    )
    running = int(before["power"].get("running_reading_count", 0))
    power = float(before["power"].get("average_running_power_watts") or 0)
    assert int(after["power"]["running_reading_count"]) == running + 2
    assert float(after["power"]["average_running_power_watts"]) == pytest.approx(
        (power * running + 500) / (running + 2)
    )


def test_cloudfront_cache_and_deliberate_update_visibility(live):
    key = "e2e-cache-" + secrets.token_hex(8) + ".txt"
    file = PROJECT / ".runtime" / key
    bucket = live.platform["FrontendBucket"]
    url = live.platform["DashboardUrl"] + "/" + key
    try:
        file.write_text("cache-version-one")
        run(
            [
                "s3",
                "cp",
                str(file),
                f"s3://{bucket}/{key}",
                "--cache-control",
                "public,max-age=3600",
                "--content-type",
                "text/plain",
            ],
            "Upload owned CloudFront cache test asset",
        )
        first = requests.get(url, timeout=20)
        assert first.status_code == 200 and first.text == "cache-version-one"
        cached = requests.get(url, timeout=20)
        assert cached.text == "cache-version-one" and "Hit" in cached.headers.get("X-Cache", "")
        file.write_text("cache-version-two")
        run(
            [
                "s3",
                "cp",
                str(file),
                f"s3://{bucket}/{key}",
                "--cache-control",
                "public,max-age=3600",
                "--content-type",
                "text/plain",
            ],
            "Update only owned test asset at the private origin",
        )
        assert requests.get(url, timeout=20).text == "cache-version-one"
        invalidation = call(
            [
                "cloudfront",
                "create-invalidation",
                "--distribution-id",
                live.platform["DistributionId"],
                "--paths",
                "/" + key,
            ],
            "Invalidate only owned cache exercise asset",
        )["Invalidation"]["Id"]
        run(
            [
                "cloudfront",
                "wait",
                "invalidation-completed",
                "--distribution-id",
                live.platform["DistributionId"],
                "--id",
                invalidation,
            ],
            "Wait for deliberate cache update",
        )
        assert requests.get(url, timeout=20).text == "cache-version-two"
    finally:
        versions = call(
            ["s3api", "list-object-versions", "--bucket", bucket, "--prefix", key],
            "Inspect only owned cache test object versions",
        )
        items = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in versions.get("Versions", []) + versions.get("DeleteMarkers", [])
            if item["Key"] == key
        ]
        if items:
            file.write_text(json.dumps({"Objects": items, "Quiet": True}))
            call(
                ["s3api", "delete-objects", "--bucket", bucket, "--delete", "file://" + str(file)],
                "Remove only owned cache exercise versions",
            )
