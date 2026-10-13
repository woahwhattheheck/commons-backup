# SPDX-License-Identifier: Apache-2.0
"""Execute the stale-SOURCE predecessor and the repaired successor."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "packet_build_v3.py.txt"
HELPER = HERE / "source_manifest_closure.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tar_bytes(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        for name in sorted(files):
            blob = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(blob))
    return raw.getvalue()


def initial_source(main_blob: bytes) -> bytes:
    value = {
        "checkpoint": {"operation": "synthetic-predecessor"},
        "runtime": {
            "main.py": {
                "bytes": len(main_blob),
                "sha256": sha256(main_blob),
                "source_path": "main.py",
            }
        },
    }
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def make_lab(root: Path, *, patched: bool):
    old_main = b"VALUE = 'old'\n"
    new_main = b"VALUE = 'new'\n"
    source = initial_source(old_main)
    archive = tar_bytes({"SOURCE.json": source, "main.py": old_main})
    canon = root / "canonical.tar.gz"
    canon.write_bytes(archive)
    candidate = root / "candidate"
    candidate.mkdir()
    (candidate / "overlay").mkdir()
    (candidate / "overlay" / "lane.py").write_bytes(b"LANE = True\n")
    (candidate / "apply_v3.py").write_text(
        "from pathlib import Path\n"
        "def apply(src):\n"
        f"    Path(src, 'main.py').write_bytes({new_main!r})\n"
        "    return src\n",
        encoding="utf-8",
    )
    (candidate / "V3-MANIFEST.json").write_text(
        json.dumps({"base": {"sha256": sha256(archive)}}),
        encoding="utf-8",
    )
    shutil.copyfile(FIXTURE, candidate / "build_v3.py")
    if patched:
        patcher = load_module("_source_closure_patcher", HERE / "patch_packet.py")
        patcher.patch(candidate, HELPER)
    return candidate, canon, source, old_main, new_main


def run_case(*, patched: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="v3-source-closure-") as temp:
        root = Path(temp)
        candidate, canon, source_before, old_main, new_main = make_lab(root, patched=patched)
        old_path = list(sys.path)
        sys.path.insert(0, str(candidate))
        try:
            module = load_module(
                "_patched_build_v3" if patched else "_predecessor_build_v3",
                candidate / "build_v3.py",
            )
            files = module.package_files(canon)
        finally:
            sys.path[:] = old_path
            sys.modules.pop("apply_v3", None)
            sys.modules.pop("source_manifest_closure", None)
        manifest = json.loads(files["SOURCE.json"])
        runtime = manifest["runtime"]
        result = {
            "patched": patched,
            "main_changed": files["main.py"] == new_main and files["main.py"] != old_main,
            "overlay_added": files["lane.py"] == b"LANE = True\n",
            "source_bytes_changed": files["SOURCE.json"] != source_before,
            "source_runtime_names": sorted(runtime),
            "source_main_sha256": runtime["main.py"]["sha256"],
            "actual_main_sha256": sha256(files["main.py"]),
            "source_lane_present": "lane.py" in runtime,
        }
        result["closed"] = (
            result["source_main_sha256"] == result["actual_main_sha256"]
            and result["source_lane_present"]
            and set(runtime) == {"main.py", "lane.py"}
        )
        return result


def report() -> dict[str, object]:
    fixture_sha = sha256(FIXTURE.read_bytes())
    predecessor = run_case(patched=False)
    successor = run_case(patched=True)
    if fixture_sha != "cfcb383e6cba811e17d687cb080fea1f55723c8aa734edbe9c37ec3743f923d0":
        raise AssertionError("packet build fixture drift")
    if predecessor["closed"] or predecessor["source_bytes_changed"]:
        raise AssertionError("predecessor no longer reproduces stale SOURCE.json")
    if not successor["closed"] or not successor["source_bytes_changed"]:
        raise AssertionError("successor did not close SOURCE.json")
    return {
        "schema": "titan.v3-source-manifest-predecessor.v1",
        "packet_build_v3_sha256": fixture_sha,
        "predecessor": predecessor,
        "successor": successor,
        "verdict": "PREDECESSOR_STALE_SUCCESSOR_CLOSED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    value = report()
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.check is not None:
        if args.check.read_text(encoding="utf-8") != encoded:
            raise SystemExit("predecessor receipt drift")
    if args.json is not None:
        args.json.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
