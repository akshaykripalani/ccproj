"""Real deployed React acceptance with disposable hosted-login accounts."""

import json
import os
import subprocess

import pytest

from tests.live.conftest import PROJECT

pytestmark = pytest.mark.live


def test_deployed_react_browser_acceptance(live, record_property):
    environment = os.environ.copy()
    environment["CCPROJ_DASHBOARD_URL"] = live.platform["DashboardUrl"]
    for role in ("viewer", "operator"):
        email, password = live.users[role]
        environment[f"CCPROJ_{role.upper()}_EMAIL"] = email
        environment[f"CCPROJ_{role.upper()}_PASSWORD"] = password
    # Environment stays in process memory: no credentials file, browser trace or video.
    result = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "run", "test:live"],
        cwd=PROJECT / "frontend",
        env=environment,
        timeout=1000,
        check=False,
    )
    assert result.returncode == 0, "Deployed browser acceptance failed; inspect nonsecret test results"
    report = json.loads((PROJECT / "frontend/test-results/live-results.json").read_text())
    record_property("browser_scenarios_passed", report["stats"]["expected"])
