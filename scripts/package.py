"""Content-addressed releases; bundle pure-Python SDK wheels for Lambda and EC2."""

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download_wheels(wheels):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--index-url",
            "https://pypi.org/simple",
            "--timeout",
            "120",
            "--only-binary=:all:",
            "--python-version",
            "3.12",
            "--platform",
            "manylinux2014_aarch64",
            "--dest",
            str(wheels),
            "-r",
            str(ROOT / "requirements-runtime.txt"),
        ],
        check=True,
    )


def bundle(build, wheels):
    backend = build / "backend.zip"
    with zipfile.ZipFile(backend, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((ROOT / "backend").glob("*.py")):
            bundle.write(path, path.relative_to(ROOT).as_posix())
        for wheel in sorted(wheels.glob("*.whl")):
            with zipfile.ZipFile(wheel) as source:
                for name in source.namelist():
                    if not name.endswith("/"):
                        bundle.writestr(name, source.read(name))
    simulator = build / "simulator.tar.gz"
    with tarfile.open(simulator, "w:gz") as bundle:
        for directory in ("backend", "simulator"):
            for path in sorted((ROOT / directory).glob("*.py")):
                bundle.add(path, arcname=path.relative_to(ROOT).as_posix())
        bundle.add(ROOT / "requirements-runtime.txt", arcname="requirements-runtime.txt")
        for wheel in sorted(wheels.glob("*.whl")):
            bundle.add(wheel, arcname="wheels/" + wheel.name)
    result = {}
    for name, path in (("backend", backend), ("simulator", simulator)):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[name] = {
            "path": str(path),
            "key": f"releases/{digest}/{path.name}",
            "sha256": digest,
        }
    (build / "release.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def package():
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    # pip's download directory is additive. A reused directory can silently mix
    # old and newly resolved SDK versions, producing duplicate ZIP entries.
    with tempfile.TemporaryDirectory(prefix="wheels-", dir=build) as directory:
        wheels = Path(directory)
        download_wheels(wheels)
        return bundle(build, wheels)


if __name__ == "__main__":
    print(json.dumps(package(), indent=2))
