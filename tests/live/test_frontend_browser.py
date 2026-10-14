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
    command = ["npm.cmd" if os.name == "nt" else "npm", "run", "test:live"]
    if environment.get("CCPROJ_UI_GREP"):
        command += ["--", "--grep", environment["CCPROJ_UI_GREP"]]
    result = subprocess.run(
        command,
        cwd=PROJECT / "frontend",
        env=environment,
        timeout=1000,
        check=False,
    )
    assert result.returncode == 0, (
        "Deployed browser acceptance failed; inspect nonsecret test results"
    )
    report = json.loads((PROJECT / "frontend/test-results/live/results.json").read_text())
    summary = {"stats": report["stats"], "scenarios": []}
    for suite in report["suites"]:
        for spec in suite["specs"]:
            summary["scenarios"].append(
                {
                    "title": spec["title"],
                    "ok": spec["ok"],
                    "results": [
                        {"status": result["status"], "durationMs": result["duration"]}
                        for test in spec["tests"]
                        for result in test["results"]
                    ],
                }
            )
    filename = "ui-live-smoke.json" if environment.get("CCPROJ_UI_GREP") else "ui-live-browser.json"
    (PROJECT / "docs" / filename).write_text(json.dumps(summary, indent=2) + "\n")
    record_property("browser_scenarios_passed", report["stats"]["expected"])
