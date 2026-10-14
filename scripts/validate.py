"""Run local schema, security, and implementation checks before AWS deployment."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from infra.generate import build

ROOT = Path(__file__).resolve().parents[1]


def validate():
    build()
    executable = Path(sys.executable).parent / ("cfn-lint.exe" if os.name == "nt" else "cfn-lint")
    templates = [
        str(ROOT / "infra" / f"{name}.json") for name in ("bootstrap", "platform", "simulator")
    ]
    subprocess.run(
        [str(executable), "--regions", "ap-southeast-2", "--template", *templates],
        check=True,
        cwd=ROOT,
    )
    guard = os.environ.get("CCPROJ_GUARD") or shutil.which("cfn-guard")
    if not guard:
        installed = list((ROOT / ".runtime" / "guard").glob("*/cfn-guard.exe"))
        guard = str(installed[0]) if installed else None
    if not guard:
        raise RuntimeError(
            "Install official cfn-guard or set CCPROJ_GUARD; security validation is required"
        )
    subprocess.run(
        [
            guard,
            "validate",
            "--rules",
            str(ROOT / "infra" / "security.guard"),
            *[part for path in templates for part in ("--data", path)],
            "--output-format",
            "json",
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([sys.executable, "-m", "pytest", "-m", "not live", "-q"], check=True, cwd=ROOT)
    return True


if __name__ == "__main__":
    validate()
