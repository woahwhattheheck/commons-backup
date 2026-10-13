#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed archive and executable gate for the TITAN W0 capability split."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Iterable

SCHEMA = 1
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 4096
REQUIRED_RUNTIME_MEMBERS = (
    "main.py", "titan_runtime.py", "spatial_tempo.py",
    "TITAN-CONFIG.json", "SOURCE.json",
)


class GateFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Archive:
    path: Path
    sha256: str
    size: int
    files: dict[str, bytes]
    directories: tuple[str, ...]

    @property
    def member_count(self) -> int:
        return len(self.files) + len(self.directories)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _strict_json_bytes(data: bytes, label: str) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise GateFailure("json.duplicate_key", f"{label}: duplicate key {key!r}")
            out[key] = value
        return out

    def constant(value):
        raise GateFailure("json.non_finite", f"{label}: non-finite constant {value!r}")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateFailure("json.utf8", f"{label}: not UTF-8: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except GateFailure:
        raise
    except json.JSONDecodeError as exc:
        raise GateFailure("json.syntax", f"{label}: invalid JSON: {exc}") from exc


def _strict_json_file(path: Path) -> Any:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise GateFailure("contract.read", f"cannot read {path}: {exc}") from exc
    return _strict_json_bytes(data, str(path))


def _normal_name(raw: str) -> tuple[str, bool]:
    if not raw or "\x00" in raw or "\\" in raw:
        raise GateFailure("archive.path", f"unsafe archive member name {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise GateFailure("archive.path", f"unsafe archive member name {raw!r}")
    name = path.as_posix().rstrip("/")
    if not name:
        raise GateFailure("archive.path", f"empty normalized archive member {raw!r}")
    return name, raw.endswith("/")


def read_archive(path: Path) -> Archive:
    path = path.resolve()
    try:
        sha256, size = _hash_file(path)
    except OSError as exc:
        raise GateFailure("archive.read", f"cannot read archive {path}: {exc}") from exc
    if size > MAX_ARCHIVE_BYTES:
        raise GateFailure("archive.too_large", f"archive is {size} bytes")

    files: dict[str, bytes] = {}
    directories: set[str] = set()
    names: set[str] = set()
    folded: dict[str, str] = {}
    total = 0
    try:
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_MEMBERS:
                raise GateFailure("archive.member_limit", f"archive has {len(members)} members")
            for member in members:
                name, slash_directory = _normal_name(member.name)
                if name in names:
                    raise GateFailure("archive.duplicate", f"duplicate member {name!r}")
                names.add(name)
                key = name.casefold()
                if key in folded:
                    raise GateFailure(
                        "archive.case_collision",
                        f"case-fold collision {folded[key]!r} / {name!r}")
                folded[key] = name
                if member.isdir():
                    directories.add(name)
                    continue
                if slash_directory or not member.isreg():
                    raise GateFailure(
                        "archive.member_type",
                        f"member {name!r} is not a regular file or directory")
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise GateFailure("archive.member_size", f"member {name!r} has size {member.size}")
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    raise GateFailure("archive.total_size", f"expanded bytes exceed {MAX_TOTAL_BYTES}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise GateFailure("archive.extract", f"cannot read member {name!r}")
                data = handle.read(MAX_MEMBER_BYTES + 1)
                if len(data) != member.size:
                    raise GateFailure(
                        "archive.member_size",
                        f"member {name!r} declared {member.size}, read {len(data)}")
                files[name] = data
    except GateFailure:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise GateFailure("archive.format", f"cannot parse {path}: {exc}") from exc
    all_names = set(files) | directories
    for name in all_names:
        for parent in PurePosixPath(name).parents:
            parent_name = parent.as_posix()
            if parent_name == ".":
                break
            if parent_name in files:
                raise GateFailure(
                    "archive.path_collision",
                    f"regular file {parent_name!r} is the parent of member {name!r}")
    return Archive(path=path, sha256=sha256, size=size, files=files,
                   directories=tuple(sorted(directories)))


def _member_rows(archive: Archive, names: Iterable[str]) -> list[dict[str, Any]]:
    rows = []
    for name in sorted(names):
        data = archive.files.get(name)
        rows.append({"path": name, "bytes": None if data is None else len(data),
                     "sha256": None if data is None else _hash_bytes(data)})
    return rows


def _list(contract: dict[str, Any], key: str) -> set[str]:
    value = contract.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise GateFailure("contract.schema", f"{key} must be an array of non-empty strings")
    return set(value)


def _validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        raise GateFailure("contract.schema", f"contract schema must equal {SCHEMA}")
    expected = contract.get("expected_base")
    if not isinstance(expected, dict):
        raise GateFailure("contract.schema", "expected_base must be an object")
    sha = expected.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise GateFailure("contract.schema", "expected_base.sha256 must be lowercase SHA-256")
    for key in ("bytes", "members"):
        if type(expected.get(key)) is not int or expected[key] < 0:
            raise GateFailure("contract.schema", f"expected_base.{key} must be a non-negative integer")
    for key in (
        "required_touched_members", "allowed_changed_members", "allowed_added_members",
        "allowed_deleted_members", "manifest_bound_members",
    ):
        _list(contract, key)
    timeout = contract.get("probe_timeout_seconds", 30)
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise GateFailure("contract.schema", "probe_timeout_seconds must be an integer in [1,120]")
    return contract


def _validate_base(base: Archive, contract: dict[str, Any]) -> None:
    expected = contract["expected_base"]
    if base.sha256 != expected["sha256"]:
        raise GateFailure("base.sha256", f"base SHA-256 {base.sha256} != {expected['sha256']}")
    if base.size != expected["bytes"]:
        raise GateFailure("base.bytes", f"base bytes {base.size} != {expected['bytes']}")
    if base.member_count != expected["members"]:
        raise GateFailure(
            "base.members", f"base members {base.member_count} != {expected['members']}")
    missing = sorted(set(REQUIRED_RUNTIME_MEMBERS) - set(base.files))
    if missing:
        raise GateFailure("base.members", f"base missing required members: {missing}")


def _validate_delta(base: Archive, candidate: Archive,
                    contract: dict[str, Any]) -> dict[str, list[str]]:
    base_names = set(base.files)
    candidate_names = set(candidate.files)
    added = candidate_names - base_names
    deleted = base_names - candidate_names
    common = base_names & candidate_names
    changed = {name for name in common if base.files[name] != candidate.files[name]}
    touched = added | deleted | changed

    allowed_changed = _list(contract, "allowed_changed_members")
    allowed_added = _list(contract, "allowed_added_members")
    allowed_deleted = _list(contract, "allowed_deleted_members")
    required = _list(contract, "required_touched_members")
    unexpected_changed = changed - allowed_changed
    unexpected_added = added - allowed_added
    unexpected_deleted = deleted - allowed_deleted
    missing_required = required - touched
    if unexpected_changed:
        raise GateFailure("delta.changed", f"unexpected changed members: {sorted(unexpected_changed)}")
    if unexpected_added:
        raise GateFailure("delta.added", f"unexpected added members: {sorted(unexpected_added)}")
    if unexpected_deleted:
        raise GateFailure("delta.deleted", f"unexpected deleted members: {sorted(unexpected_deleted)}")
    if missing_required:
        raise GateFailure("delta.required", f"required members were not touched: {sorted(missing_required)}")
    return {"changed": sorted(changed), "added": sorted(added),
            "deleted": sorted(deleted), "touched": sorted(touched)}


def _validate_config(candidate: Archive) -> dict[str, Any]:
    config = _strict_json_bytes(candidate.files["TITAN-CONFIG.json"], "TITAN-CONFIG.json")
    if not isinstance(config, dict):
        raise GateFailure("config.type", "TITAN-CONFIG.json must contain an object")
    if "weed_continuation" not in config:
        raise GateFailure("config.weed_continuation_missing",
                          "TITAN-CONFIG.json must explicitly contain weed_continuation")
    if type(config["weed_continuation"]) is not bool or config["weed_continuation"] is not False:
        raise GateFailure("config.weed_continuation_not_false",
                          "TITAN-CONFIG.json weed_continuation must be literal false")
    return config


def _validate_manifest(candidate: Archive, config: dict[str, Any],
                       contract: dict[str, Any]) -> dict[str, Any]:
    source = _strict_json_bytes(candidate.files["SOURCE.json"], "SOURCE.json")
    if not isinstance(source, dict):
        raise GateFailure("manifest.type", "SOURCE.json must contain an object")
    defaults = source.get("default")
    if not isinstance(defaults, dict):
        raise GateFailure("manifest.default", "SOURCE.json.default must be an object")
    if defaults != config:
        raise GateFailure("manifest.default", "SOURCE.json.default must equal TITAN-CONFIG.json exactly")
    runtime = source.get("runtime")
    if not isinstance(runtime, dict):
        raise GateFailure("manifest.runtime", "SOURCE.json.runtime must be an object")
    rows = []
    for name in sorted(_list(contract, "manifest_bound_members")):
        data = candidate.files.get(name)
        if data is None:
            raise GateFailure("manifest.member_missing", f"candidate missing bound member {name!r}")
        entry = runtime.get(name)
        if not isinstance(entry, dict):
            raise GateFailure("manifest.entry", f"SOURCE.json.runtime missing {name!r}")
        actual_sha = _hash_bytes(data)
        actual_bytes = len(data)
        if entry.get("sha256") != actual_sha or entry.get("bytes") != actual_bytes:
            raise GateFailure(
                "manifest.hash",
                f"SOURCE.json.runtime[{name!r}] does not bind actual bytes")
        rows.append({"path": name, "sha256": actual_sha, "bytes": actual_bytes})
    return {"entrypoint": source.get("entrypoint"), "bound_members": rows}


def _materialize(archive: Archive, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for name in sorted(archive.directories, key=lambda item: (item.count("/"), item)):
        (root / Path(*PurePosixPath(name).parts)).mkdir(parents=True, exist_ok=True)
    for name, data in sorted(archive.files.items()):
        target = root / Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise GateFailure("materialize.collision", f"materialization collision at {name!r}")
        with target.open("xb") as handle:
            handle.write(data)
        target.chmod(0o644)


def _run_probe(candidate: Archive, probe: Path, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="titan-w0-gate-") as temp:
        work = Path(temp)
        root = work / "candidate"
        _materialize(candidate, root)
        result_path = work / "probe-result.json"
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(probe.resolve()), str(root), str(result_path)],
                cwd=work, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GateFailure("probe.timeout", f"runtime probe exceeded {timeout}s") from exc
        if not result_path.is_file():
            raise GateFailure(
                "probe.receipt_missing",
                f"runtime probe exited {completed.returncode} without a result; stderr={completed.stderr[-2000:]!r}")
        result = _strict_json_file(result_path)
        if not isinstance(result, dict) or result.get("schema") != 1:
            raise GateFailure("probe.receipt", "runtime probe returned an invalid receipt")
        if completed.returncode != 0 or result.get("ok") is not True:
            error = result.get("error", completed.stderr[-2000:])
            raise GateFailure("probe.failed", f"runtime probe failed: {error}")
        matrix = result.get("matrix")
        if not isinstance(matrix, list) or len(matrix) != 32:
            raise GateFailure("probe.matrix", "runtime probe did not return all 32 capability masks")
        reachability = result.get("reachability")
        if not isinstance(reachability, list) or len(reachability) != 8:
            raise GateFailure("probe.reachability", "runtime probe did not return all 8 P/T/W controls")
        return result


def _archive_summary(archive: Archive) -> dict[str, Any]:
    # Deliberately omit local paths so identical inputs produce identical receipts
    # across runners and workspaces.
    return {"sha256": archive.sha256, "bytes": archive.size,
            "members": archive.member_count, "files": len(archive.files),
            "directories": len(archive.directories)}


def _receipt_hash(receipt: dict[str, Any]) -> str:
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("utf-8")
    return _hash_bytes(payload)


def verify(base_path: Path, candidate_path: Path, contract_path: Path,
           probe_path: Path) -> dict[str, Any]:
    contract = _validate_contract(_strict_json_file(contract_path))
    base = read_archive(base_path)
    candidate = read_archive(candidate_path)
    _validate_base(base, contract)
    delta = _validate_delta(base, candidate, contract)
    config = _validate_config(candidate)
    manifest = _validate_manifest(candidate, config, contract)
    probe = _run_probe(candidate, probe_path, contract.get("probe_timeout_seconds", 30))
    contract_sha256, contract_bytes = _hash_file(contract_path.resolve())
    probe_sha256, probe_bytes = _hash_file(probe_path.resolve())
    receipt = {
        "schema": SCHEMA,
        "status": "PASS",
        "contract": {"sha256": contract_sha256, "bytes": contract_bytes},
        "probe_program": {"sha256": probe_sha256, "bytes": probe_bytes},
        "base": _archive_summary(base),
        "candidate": _archive_summary(candidate),
        "delta": delta,
        "changed_members": _member_rows(candidate, delta["touched"]),
        "config": {"weed_continuation": config["weed_continuation"],
                   "capability_values": {name: config.get(name, False) for name in probe["capabilities"]}},
        "manifest": manifest,
        "probe": probe,
    }
    receipt["receipt_sha256"] = _receipt_hash(receipt)
    return receipt


def _write_receipt(path: Path | None, receipt: dict[str, Any]) -> None:
    text = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--probe", type=Path,
                        default=Path(__file__).with_name("runtime_probe.py"))
    args = parser.parse_args(argv)
    try:
        receipt = verify(args.base, args.candidate, args.contract, args.probe)
        code = 0
    except GateFailure as exc:
        receipt = {"schema": SCHEMA, "status": "HOLD",
                   "failure": {"code": exc.code, "message": exc.message}}
        receipt["receipt_sha256"] = _receipt_hash(receipt)
        code = 2
    except BaseException as exc:
        receipt = {"schema": SCHEMA, "status": "ERROR",
                   "failure": {"code": "internal", "message": f"{type(exc).__name__}: {exc}"}}
        receipt["receipt_sha256"] = _receipt_hash(receipt)
        code = 3
    _write_receipt(args.receipt, receipt)
    if args.receipt is not None:
        print(f"{receipt['status']}: {receipt['receipt_sha256']} -> {args.receipt}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
