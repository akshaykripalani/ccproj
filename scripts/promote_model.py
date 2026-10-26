"""Promote or roll back an evaluated local model through the existing CloudFormation stack."""

import argparse
import json

from scripts.aws_cli import identity
from scripts.deploy import ROOT, deploy_stack
from scripts.model_release import publish_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "version", help="Evaluated rf-... version; an earlier release performs a rollback"
    )
    args = parser.parse_args()
    identity()
    path = ROOT / "docs/ccproj-deployment.json"
    deployed = json.loads(path.read_text())
    parameters = {
        "ArtifactBucket": deployed["artifacts"],
        "BackendKey": deployed["release"]["backend"]["key"],
        "BudgetStart": deployed["budgetPeriod"]["start"],
        "BudgetEnd": deployed["budgetPeriod"]["end"],
        **publish_model(deployed["artifacts"], args.version),
    }
    deployed["platform"] = deploy_stack(
        deployed["stack"], str(ROOT / "infra/platform.json"), parameters, deployed["artifacts"]
    )
    for destination in (path, ROOT / ".runtime/deployment.json"):
        destination.write_text(json.dumps(deployed, indent=2) + "\n")
    print("Deployed model", args.version)


if __name__ == "__main__":
    main()
