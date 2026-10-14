"""Deterministic conservative monthly model using rates checked on 14 October 2026."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    hours = 730
    seconds = hours * 3600
    batches = seconds / 10
    readings = batches * 3
    components = {
        "EC2 t4g.micro": hours * 0.0106,
        "One public IPv4": hours * 0.005,
        "8 GiB gp3 disk": 8 * 0.096,
        "One KMS key": 1,
        "Ten standard alarms": 10 * 0.10,
        "DynamoDB transactional writes (6 units per reading)": readings * 6 * 0.00000071,
        "DynamoDB reads (3 per reading plus controls)": (readings * 3 + seconds / 5 * 3)
        * 0.0000001425,
        "S3 archive PUTs": batches * 0.0000055,
        "FIFO SQS send/receive/delete estimate": batches * 3 * 0.0000005,
        "Lambda requests (ingest/process/notifier)": (batches * 2 + seconds / 60) * 0.0000002,
        "Lambda ARM duration allowance (1s each ingest/process; 256MiB)": (
            batches * 2 + seconds / 60
        )
        * 0.25
        * 0.0000133334,
        "Allowance: API, logs, storage, reports, frontend transfer": 5,
    }
    result = {
        "region": "ap-southeast-2",
        "hours": hours,
        "readingCount": int(readings),
        "usdByComponent": {key: round(value, 4) for key, value in components.items()},
        "estimatedMonthlyUsd": round(sum(components.values()), 2),
        "estimated14DayUsd": round(sum(components.values()) * (14 * 24) / hours, 2),
        "projectCeilingUsd": 50,
        "notificationsUsd": [20, 30, 40],
        "assumptions": [
            "Public on-demand rates checked through logged AWS Pricing API calls on 14 October 2026; see AWS_COMMANDS.txt and pricing-snapshot.json.",
            "Conservative model applies neither signup credits nor monthly free allowances. The $5 variable-service allowance is an estimate, not a validated billing rate.",
            "One second per Lambda invocation is a planning allowance; use live metrics and actual billing after deployment.",
            "This is a bounded workload estimate, not a hard cap or a guarantee of indefinite hosting within $50.",
            "Budget notifications do not stop resources; user approval is required before spending-related stops.",
        ],
    }
    (ROOT / "docs" / "budget-model.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
