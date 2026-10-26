"""Publish evaluated, versioned models; CloudFormation parameters select the release."""

import json
import re
from pathlib import Path

from scripts.aws_cli import run

ROOT = Path(__file__).resolve().parents[1]


def publish_model(bucket, version=None):
    release = json.loads((ROOT / "models/release.json").read_text())
    version = version or release["version"]
    if not re.fullmatch(r"rf-[a-f0-9]{12}", version):
        raise ValueError("Invalid model version")
    folder = ROOT / "models" / version
    evaluation = json.loads((folder / "evaluation.json").read_text())
    model = json.loads((folder / "model.json").read_text())
    if not evaluation.get("releaseGatePassed") or model["version"] != version:
        raise ValueError("Only evaluated releases may be deployed")
    for name in ("model.json", "evaluation.json"):
        run(
            [
                "s3",
                "cp",
                str(folder / name),
                f"s3://{bucket}/models/{version}/{name}",
                "--sse",
                "AES256",
            ],
            "Publish evaluated model artifact",
        )
    compact = {
        key: evaluation[key]
        for key in ("heldOut", "trendBaseline", "warningLeadMinutes", "episodes", "horizonMinutes")
    }
    return {
        "ModelVersion": version,
        "ModelKey": f"models/{version}/model.json",
        "ModelEvaluation": json.dumps(compact, separators=(",", ":")),
    }
