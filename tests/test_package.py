import tarfile
import zipfile

from scripts import package


def test_release_excludes_stale_wheels_and_bundles_only_current_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "ROOT", tmp_path)
    for name in ("backend", "simulator"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")
    (tmp_path / "requirements-runtime.txt").write_text("boto3==1.43.113\n")
    stale = tmp_path / "build" / "wheels" / "stale.whl"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"not a current dependency")
    resolutions = []

    def download(wheels):
        assert list(wheels.iterdir()) == []
        resolutions.append(wheels)
        with zipfile.ZipFile(wheels / "current.whl", "w") as wheel:
            wheel.writestr("sdk/__init__.py", f"VERSION = {len(resolutions)}")

    monkeypatch.setattr(package, "download_wheels", download)
    for version in (1, 2):
        result = package.package()
        with zipfile.ZipFile(result["backend"]["path"]) as backend:
            assert len(backend.namelist()) == len(set(backend.namelist()))
            assert backend.read("sdk/__init__.py").decode() == f"VERSION = {version}"
        with tarfile.open(result["simulator"]["path"]) as simulator:
            assert "wheels/current.whl" in simulator.getnames()
            assert "wheels/stale.whl" not in simulator.getnames()
        assert not resolutions[-1].exists()
    assert resolutions[0] != resolutions[1]
    assert stale.exists()
