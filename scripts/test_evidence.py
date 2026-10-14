"""Consolidate the latest result of each scenario, preserving raw rerun evidence."""

import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def consolidate():
    latest = {}
    # Git checkout/copy changes filesystem mtimes. Use recorded run timestamps
    # so an old failing retry cannot replace a later passing result after checkout.
    def run_time(path):
        suites = ET.parse(path).getroot().iter("testsuite")
        return min((suite.get("timestamp", "") for suite in suites), default=""), path.name

    sources = sorted((ROOT / "docs").glob("live-*-results.xml"), key=run_time)
    for source in sources:
        for case in ET.parse(source).getroot().iter("testcase"):
            latest[(case.get("classname"), case.get("name"))] = (source.name, case)
    if not latest:
        raise ValueError("No live AWS results found")
    suite = ET.Element(
        "testsuite", name="Latest live AWS acceptance scenarios", tests=str(len(latest))
    )
    cases = []
    for key in sorted(latest):
        source, case = latest[key]
        suite.append(case)
        failed = case.find("failure") is not None or case.find("error") is not None
        skipped = case.find("skipped") is not None
        cases.append(
            {
                "name": case.get("name"),
                "status": "failed" if failed else "skipped" if skipped else "passed",
                "source": source,
                "seconds": float(case.get("time", 0)),
                "measurements": {
                    p.get("name"): p.get("value") for p in case.findall("./properties/property")
                },
            }
        )
    suite.set("failures", str(sum(c["status"] == "failed" for c in cases)))
    suite.set("skipped", str(sum(c["status"] == "skipped" for c in cases)))
    ET.ElementTree(suite).write(
        ROOT / "docs" / "live-acceptance.xml", encoding="utf-8", xml_declaration=True
    )
    summary = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "passed": sum(c["status"] == "passed" for c in cases),
        "total": len(cases),
        "note": "Latest result per scenario across multiple real AWS runs. Raw initial failures remain in source XML files.",
        "cases": cases,
    }
    (ROOT / "docs" / "live-acceptance.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    consolidate()
