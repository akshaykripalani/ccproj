"""Conservative seven-device planning model; no shutdown date and no AWS writes."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    pricing = json.loads((ROOT / "docs/predictive-pricing.json").read_text())
    rates = {item["usageType"]: float(item["usd"]) for item in pricing["rates"]}
    hours, devices = 730, 7
    seconds = hours * 3600
    batches, reconciliation = seconds / 10, seconds / 60
    predictions = batches + reconciliation
    readings = batches * devices
    arm, write, read = (
        rates[key]
        for key in ("APS2-Lambda-GB-Second-ARM", "APS2-WriteRequestUnits", "APS2-ReadRequestUnits")
    )
    components = {
        "Existing EC2, disk, IPv4, KMS and twelve alarms": 730 * 0.0106
        + 8 * 0.096
        + 730 * 0.005
        + 1
        + 12 * 0.1,
        "Telemetry transactional writes: 12 units per reading allowance": readings * 12 * write,
        "Telemetry and controls reads": (readings * 3 + seconds / 5 * devices) * read,
        "Prediction writes: one unit per device": predictions * devices * write,
        "Prediction reads: three units per device": predictions * devices * 3 * read,
        "Archive PUTs and FIFO queue requests": batches * (0.0000055 + 3 * 0.0000005),
        "Existing Lambda calls: 1s ingest, 3s process, 1s notifier at 256MiB": (
            batches * 4 + reconciliation
        )
        * 0.25
        * arm
        + (batches * 2 + reconciliation) * 0.0000002,
        "Inference Lambda: 1s per batch at 256MiB": predictions * 0.25 * arm
        + predictions * 0.0000002,
        "API, logs, storage, history queries, transfer and scheduler allowance": 5,
    }
    points = pricing["lambdaDurationMetrics"]["Datapoints"]
    samples = sum(point["SampleCount"] for point in points)
    average = sum(point["Average"] * point["SampleCount"] for point in points) / samples
    result = {
        "devices": devices,
        "hours": hours,
        "estimatedMonthlyUsd": round(sum(components.values()), 2),
        "illustrativeSevenDayUsd": round(sum(components.values()) * 168 / hours, 2),
        "inferenceLambdaMonthlyUsd": round(
            components["Inference Lambda: 1s per batch at 256MiB"], 2
        ),
        "measuredInference": {
            "sampleCount": samples,
            "averageDurationMs": round(average, 2),
            "maximumDurationMs": max(point["Maximum"] for point in points),
        },
        "usdByComponent": {key: round(value, 4) for key, value in components.items()},
        "notes": [
            "Planning estimate before credits/free allowances, not a bill or spending cap. Seven days is an illustration, not a shutdown schedule.",
            "Current Sydney ARM compute and DynamoDB rates are in predictive-pricing.json. EC2/disk/IPv4/other baseline rates use the 14 October recorded price model; request pricing uses $0.20 per million.",
            "All seven devices report every ten seconds; inference scores a batch, not a separate Lambda call for every device. A minute schedule reconciles retries.",
            "Twelve transactional write units per reading is a conservative allowance for the bounded feature window; actual item sizes and charges vary. API activity and user-triggered reports vary.",
            "The initial inference observations include cold/release transitions and are not a steady-state benchmark. Maximum duration is reported, not substituted as an average.",
            "No second EC2, GPU, always-on ML endpoint, provisioned Lambda concurrency, NAT gateway or paid plan upgrade was added.",
        ],
    }
    (ROOT / "docs/predictive-budget-model.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
