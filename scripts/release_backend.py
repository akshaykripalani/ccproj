"""Update Lambda/model code without reprovisioning or restarting the simulator."""

import argparse
import json

from scripts.aws_cli import identity, run
from scripts.deploy import ROOT, deploy_stack
from scripts.model_release import publish_model
from scripts.package import package
from scripts.validate import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-version")
    args = parser.parse_args()
    identity()
    validate()
    deployed = json.loads((ROOT / "docs/ccproj-deployment.json").read_text())
    release = package()["backend"]
    run(
        [
            "s3",
            "cp",
            release["path"],
            f"s3://{deployed['artifacts']}/{release['key']}",
            "--sse",
            "AES256",
        ],
        "Publish backend-only release",
    )
    parameters = {
        "ArtifactBucket": deployed["artifacts"],
        "BackendKey": release["key"],
        "BudgetStart": deployed["budgetPeriod"]["start"],
        "BudgetEnd": deployed["budgetPeriod"]["end"],
        **publish_model(deployed["artifacts"], args.model_version),
    }
    deployed["platform"] = deploy_stack(
        deployed["stack"], str(ROOT / "infra/platform.json"), parameters, deployed["artifacts"]
    )
    deployed["release"]["backend"] = release
    for path in (ROOT / "docs/ccproj-deployment.json", ROOT / ".runtime/deployment.json"):
        path.write_text(json.dumps(deployed, indent=2) + "\n")
    print("Backend/model release deployed; simulator unchanged")


if __name__ == "__main__":
    main()
