# SPDX-License-Identifier: Apache-2.0
"""Materialize exact canonical control and one-hunk candidate runtime arenas."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from typing import Any, Mapping

from physical_fill import patch_scheduler_bytes, sha256_bytes

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
POINTER = LAB / "runtime" / "integrated-selected" / "CURRENT-ARCHIVE.json"
SOURCE = LAB / "runtime" / "integrated-selected" / "CURRENT-SOURCE.json"

EXPECTED_POINTER_GIT_BLOB = "5bd67f93b832b6f35ea6482d35cebdd0d600cbe1"
EXPECTED_SOURCE_GIT_BLOB = "d80b40e345bcdbacfed9f7f4c8173aeb134fd781"
EXPECTED_ARCHIVE_SHA256 = "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
EXPECTED_ARCHIVE_BYTES = 428_158
EXPECTED_SOURCE_MANIFEST_SHA256 = "3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469"
EXPECTED_RUNTIME_FILES = 109
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 256


def git_blob_sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _safe_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise RuntimeError("invalid archive member name")
    pure = PurePosixPath(name)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in ("", ".", "..") for part in parts):
        raise RuntimeError(f"unsafe archive member: {name!r}")
    if PurePosixPath(*parts).as_posix() != name:
        raise RuntimeError(f"noncanonical archive member: {name!r}")
    return tuple(parts)


def _load_json(path: Path, expected_blob: str) -> tuple[bytes, dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"required source is not a regular file: {path}")
    data = path.read_bytes()
    actual = git_blob_sha1_bytes(data)
    if actual != expected_blob:
        raise RuntimeError(f"source drift for {path.name}: expected {expected_blob}, got {actual}")
    try:
        value = json.loads(data)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid JSON in {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"top-level JSON object required in {path}")
    return data, value


def _read_members(archive: Path) -> dict[str, bytes]:
    if not archive.is_file() or archive.is_symlink():
        raise RuntimeError(f"canonical archive is not a regular file: {archive}")
    payload = archive.read_bytes()
    if len(payload) != EXPECTED_ARCHIVE_BYTES:
        raise RuntimeError(
            f"archive byte drift: expected {EXPECTED_ARCHIVE_BYTES}, got {len(payload)}"
        )
    digest = sha256_bytes(payload)
    if digest != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(f"archive digest drift: expected {EXPECTED_ARCHIVE_SHA256}, got {digest}")
    members: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as bundle:
        for member in bundle:
            if len(members) >= MAX_MEMBERS:
                raise RuntimeError("archive member ceiling exceeded")
            if not member.isfile():
                raise RuntimeError(f"nonregular archive member: {member.name!r}")
            _safe_parts(member.name)
            if member.name in members:
                raise RuntimeError(f"duplicate archive member: {member.name}")
            if type(member.size) is not int or not 0 <= member.size <= MAX_MEMBER_BYTES:
                raise RuntimeError(f"rejected archive member size: {member.name}")
            stream = bundle.extractfile(member)
            if stream is None:
                raise RuntimeError(f"cannot read archive member: {member.name}")
            data = stream.read(member.size + 1)
            if len(data) != member.size:
                raise RuntimeError(f"archive length mismatch: {member.name}")
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise RuntimeError("archive expanded byte ceiling exceeded")
            members[member.name] = data
    return members


def _verify_members(
    members: Mapping[str, bytes],
    source_bytes: bytes,
    source: Mapping[str, Any],
) -> None:
    runtime = source.get("runtime")
    if not isinstance(runtime, dict) or len(runtime) != EXPECTED_RUNTIME_FILES:
        raise RuntimeError("runtime source cardinality drift")
    if sha256_bytes(source_bytes) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("CURRENT-SOURCE digest drift")
    expected = set(runtime) | {"SOURCE.json"}
    if set(members) != expected:
        missing = sorted(expected - set(members))
        extra = sorted(set(members) - expected)
        raise RuntimeError(f"archive/source member drift; missing={missing[:4]}, extra={extra[:4]}")
    if members["SOURCE.json"] != source_bytes:
        raise RuntimeError("archive SOURCE.json is not byte-identical to CURRENT-SOURCE.json")
    for name, metadata in runtime.items():
        _safe_parts(name)
        if not isinstance(metadata, dict):
            raise RuntimeError(f"invalid runtime metadata: {name}")
        data = members[name]
        if type(metadata.get("bytes")) is not int or metadata["bytes"] != len(data):
            raise RuntimeError(f"runtime byte-count drift: {name}")
        if metadata.get("sha256") != sha256_bytes(data):
            raise RuntimeError(f"runtime digest drift: {name}")


def _write_tree(root: Path, members: Mapping[str, bytes]) -> None:
    for name in sorted(members):
        target = root.joinpath(*_safe_parts(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(members[name])


def _tree_digest(root: Path, names: list[str]) -> str:
    h = hashlib.sha256()
    for name in sorted(names):
        data = root.joinpath(*PurePosixPath(name).parts).read_bytes()
        h.update(name.encode("utf-8") + b"\0")
        h.update(str(len(data)).encode("ascii") + b"\0")
        h.update(data)
    return h.hexdigest()


def materialize(destination: Path) -> dict[str, Any]:
    """Create destination/control and destination/candidate atomically."""
    destination = Path(destination).resolve()
    pointer_bytes, pointer = _load_json(POINTER, EXPECTED_POINTER_GIT_BLOB)
    source_bytes, source = _load_json(SOURCE, EXPECTED_SOURCE_GIT_BLOB)
    required_pointer = {
        "path": "exports/titan-current.tar.gz",
        "entrypoint": "main.py::agent",
        "config": "TITAN-CONFIG.json",
        "sha256": EXPECTED_ARCHIVE_SHA256,
        "bytes": EXPECTED_ARCHIVE_BYTES,
        "runtime_files": EXPECTED_RUNTIME_FILES,
        "source_manifest": "runtime/integrated-selected/CURRENT-SOURCE.json",
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
    }
    if pointer != required_pointer:
        raise RuntimeError("CURRENT-ARCHIVE pointer drift")
    archive = LAB / pointer["path"]
    members = _read_members(archive)
    _verify_members(members, source_bytes, source)
    if destination.exists():
        raise RuntimeError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".", dir=destination.parent))
    try:
        control = staging / "control"
        candidate = staging / "candidate"
        control.mkdir()
        candidate.mkdir()
        _write_tree(control, members)
        _write_tree(candidate, members)
        candidate_scheduler, patch = patch_scheduler_bytes(members["scheduler.py"])
        (candidate / "scheduler.py").write_bytes(candidate_scheduler)
        names = sorted(members)
        control_digest = _tree_digest(control, names)
        candidate_digest = _tree_digest(candidate, names)
        unchanged = []
        changed = []
        for name in names:
            a = (control / name).read_bytes()
            b = (candidate / name).read_bytes()
            (changed if a != b else unchanged).append(name)
        if changed != ["scheduler.py"]:
            raise RuntimeError(f"candidate changed unexpected members: {changed}")
        receipt = {
            "schema_version": 1,
            "operation": "TITAN-V3-ACTIVE-PURCHASE-PHYSICAL-FILL-20260910-01",
            "archive": {
                "path": pointer["path"],
                "sha256": pointer["sha256"],
                "bytes": pointer["bytes"],
                "runtime_files": pointer["runtime_files"],
                "source_manifest_sha256": pointer["source_manifest_sha256"],
                "pointer_git_blob": EXPECTED_POINTER_GIT_BLOB,
                "source_git_blob": EXPECTED_SOURCE_GIT_BLOB,
                "pointer_sha256": sha256_bytes(pointer_bytes),
            },
            "control": {"tree_sha256": control_digest, "entrypoint": "control/main.py::agent"},
            "candidate": {
                "tree_sha256": candidate_digest,
                "entrypoint": "candidate/main.py::agent",
                "changed_members": changed,
                "unchanged_member_count": len(unchanged),
                "patch": patch,
            },
        }
        (staging / "MATERIALIZATION.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(staging, destination)
        return receipt
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    receipt = materialize(args.destination)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
