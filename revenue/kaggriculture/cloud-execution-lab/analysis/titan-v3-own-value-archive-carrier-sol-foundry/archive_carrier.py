#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize two closure-bound TITAN archive entrypoints for a paired panel."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from typing import Any, Mapping
import uuid

from archive_runtime_guard import (
    ArchiveRuntimeGuardError,
    guard_runtime,
    runtime_tree_sha256,
)

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 512
POINTER_KEYS = {
    "path",
    "entrypoint",
    "config",
    "sha256",
    "bytes",
    "runtime_files",
    "source_manifest",
    "source_manifest_sha256",
}
REQUIRED_ROOT_MODULES = (
    "observed_clone",
    "scheduler",
    "selected_sell_core",
    "titan_runtime",
    "main",
)


class ArchiveCarrierError(RuntimeError):
    """The release archive or generated carrier violated a fail-closed contract."""


def _strict_json_bytes(data: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ArchiveCarrierError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ArchiveCarrierError(f"{label} contains non-finite JSON constant {value}")

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveCarrierError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _true_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ArchiveCarrierError(f"{label} must be an integer >= {minimum}")
    return value


def _hex_digest(value: Any, label: str, *, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ArchiveCarrierError(f"{label} must be a {length}-character hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ArchiveCarrierError(f"{label} must be a {length}-character hex digest") from exc
    return value.lower()


def _canonical_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArchiveCarrierError(f"{label} is not a canonical relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in ("", ".", "..") for part in path.parts):
        raise ArchiveCarrierError(f"{label} is not a canonical relative path")
    return value


def _under(root: Path, relative: str, label: str) -> Path:
    name = _canonical_name(relative, label)
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / Path(*PurePosixPath(name).parts)).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ArchiveCarrierError(f"{label} escapes lab root")
    return candidate


def _read_pointer(lab_root: Path, pointer_path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        pointer_bytes = pointer_path.read_bytes()
    except OSError as exc:
        raise ArchiveCarrierError(f"cannot read archive pointer: {exc}") from exc
    pointer = _strict_json_bytes(pointer_bytes, "CURRENT-ARCHIVE.json")
    if not isinstance(pointer, dict) or set(pointer) != POINTER_KEYS:
        raise ArchiveCarrierError(
            "CURRENT-ARCHIVE.json keys drift: "
            f"expected={sorted(POINTER_KEYS)!r}, got={sorted(pointer) if isinstance(pointer, dict) else type(pointer).__name__!r}"
        )
    if pointer.get("entrypoint") != "main.py::agent":
        raise ArchiveCarrierError("current archive entrypoint is not main.py::agent")
    if pointer.get("config") != "TITAN-CONFIG.json":
        raise ArchiveCarrierError("current archive config is not TITAN-CONFIG.json")
    _canonical_name(pointer.get("path"), "archive pointer path")
    _canonical_name(pointer.get("source_manifest"), "source manifest path")
    _true_int(pointer.get("bytes"), "archive byte count", minimum=1)
    _true_int(pointer.get("runtime_files"), "runtime file count", minimum=1)
    _hex_digest(pointer.get("sha256"), "archive SHA-256")
    _hex_digest(pointer.get("source_manifest_sha256"), "source manifest SHA-256")
    _under(lab_root, pointer["path"], "archive pointer path")
    _under(lab_root, pointer["source_manifest"], "source manifest path")
    return pointer, pointer_bytes


def _read_archive(lab_root: Path, pointer: Mapping[str, Any]) -> tuple[dict[str, bytes], bytes]:
    archive_path = _under(lab_root, pointer["path"], "archive pointer path")
    try:
        data = archive_path.read_bytes()
    except OSError as exc:
        raise ArchiveCarrierError(f"cannot read current archive: {exc}") from exc
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveCarrierError(f"archive exceeds {MAX_ARCHIVE_BYTES} byte safety bound")
    if len(data) != pointer["bytes"]:
        raise ArchiveCarrierError(
            f"archive byte-count drift: expected {pointer['bytes']}, got {len(data)}"
        )
    actual_sha = _sha256(data)
    if actual_sha != pointer["sha256"]:
        raise ArchiveCarrierError(
            f"archive SHA-256 drift: expected {pointer['sha256']}, got {actual_sha}"
        )

    members: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            infos = archive.getmembers()
            if len(infos) > MAX_MEMBERS:
                raise ArchiveCarrierError(f"archive exceeds {MAX_MEMBERS} member safety bound")
            names = [info.name for info in infos]
            canonical_names: list[str] = []
            seen_names: set[str] = set()
            for raw_name in names:
                name = _canonical_name(raw_name, "archive member")
                if name in seen_names:
                    raise ArchiveCarrierError(f"archive duplicates member {name!r}")
                seen_names.add(name)
                canonical_names.append(name)
            if canonical_names != sorted(canonical_names):
                raise ArchiveCarrierError("archive members are not in canonical sorted order")
            for info, name in zip(infos, canonical_names):
                if not info.isreg():
                    raise ArchiveCarrierError(f"archive member is not a regular file: {name}")
                if type(info.size) is not int or info.size < 0 or info.size > MAX_MEMBER_BYTES:
                    raise ArchiveCarrierError(f"archive member size is unsafe: {name}")
                total += info.size
                if total > MAX_TOTAL_BYTES:
                    raise ArchiveCarrierError(
                        f"archive expands beyond {MAX_TOTAL_BYTES} byte safety bound"
                    )
                stream = archive.extractfile(info)
                if stream is None:
                    raise ArchiveCarrierError(f"cannot read archive member {name}")
                payload = stream.read(info.size + 1)
                if len(payload) != info.size:
                    raise ArchiveCarrierError(
                        f"archive member byte-count mismatch: {name}; expected {info.size}, got {len(payload)}"
                    )
                members[name] = payload
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ArchiveCarrierError(f"cannot parse current archive: {exc}") from exc
    return members, data


def _validate_source_manifest(
    lab_root: Path,
    pointer: Mapping[str, Any],
    members: Mapping[str, bytes],
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    source_bytes = members.get("SOURCE.json")
    if source_bytes is None:
        raise ArchiveCarrierError("archive is missing SOURCE.json")
    source_sha = _sha256(source_bytes)
    if source_sha != pointer["source_manifest_sha256"]:
        raise ArchiveCarrierError(
            "archive SOURCE.json digest drift: "
            f"expected {pointer['source_manifest_sha256']}, got {source_sha}"
        )
    source_path = _under(lab_root, pointer["source_manifest"], "source manifest path")
    try:
        repository_source = source_path.read_bytes()
    except OSError as exc:
        raise ArchiveCarrierError(f"cannot read current source manifest: {exc}") from exc
    if repository_source != source_bytes:
        raise ArchiveCarrierError("archive SOURCE.json differs from CURRENT-SOURCE.json")

    source = _strict_json_bytes(source_bytes, "SOURCE.json")
    if not isinstance(source, dict):
        raise ArchiveCarrierError("SOURCE.json root must be an object")
    if source.get("entrypoint") != pointer["entrypoint"]:
        raise ArchiveCarrierError("SOURCE.json entrypoint differs from archive pointer")
    if source.get("config") != pointer["config"]:
        raise ArchiveCarrierError("SOURCE.json config differs from archive pointer")
    runtime = source.get("runtime")
    if not isinstance(runtime, dict):
        raise ArchiveCarrierError("SOURCE.json runtime map is missing")
    if len(runtime) != pointer["runtime_files"]:
        raise ArchiveCarrierError(
            f"runtime file-count drift: expected {pointer['runtime_files']}, got {len(runtime)}"
        )
    expected_members = set(runtime) | {"SOURCE.json"}
    if set(members) != expected_members:
        raise ArchiveCarrierError(
            "archive member-set differs from SOURCE.json runtime map: "
            f"missing={sorted(expected_members - set(members))!r}, "
            f"unexpected={sorted(set(members) - expected_members)!r}"
        )

    rows: list[dict[str, Any]] = []
    for raw_name in sorted(runtime):
        name = _canonical_name(raw_name, "runtime member")
        record = runtime[raw_name]
        if not isinstance(record, dict):
            raise ArchiveCarrierError(f"runtime record for {name!r} must be an object")
        expected_bytes = _true_int(record.get("bytes"), f"runtime[{name!r}].bytes")
        expected_sha = _hex_digest(record.get("sha256"), f"runtime[{name!r}].sha256")
        payload = members[name]
        actual_sha = _sha256(payload)
        if len(payload) != expected_bytes or actual_sha != expected_sha:
            raise ArchiveCarrierError(
                f"archive member differs from SOURCE.json: {name}; "
                f"expected {expected_bytes}/{expected_sha}, got {len(payload)}/{actual_sha}"
            )
        rows.append({"name": name, "bytes": expected_bytes, "sha256": expected_sha})
    return source, rows, source_sha


def _write_member(root: Path, name: str, data: bytes) -> None:
    path = root / Path(*PurePosixPath(name).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    os.chmod(path, 0o644)


def _entry_source(
    *,
    mode: str,
    source_sha256: str,
    tree_sha256: str,
    guard_sha256: str,
    overlay_sha256: str | None,
) -> bytes:
    if mode not in {"control", "candidate"}:
        raise ArchiveCarrierError(f"unknown carrier mode: {mode}")
    entry_name = f"{mode}_entry.py"
    extras = {"archive_runtime_guard.py": guard_sha256}
    if mode == "candidate":
        if overlay_sha256 is None:
            raise ArchiveCarrierError("candidate entry requires an overlay digest")
        extras["own_value_objective.py"] = overlay_sha256
    common = f'''\
# SPDX-License-Identifier: Apache-2.0
"""Generated {mode} entrypoint for a closure-bound TITAN archive panel."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archive_runtime_guard import guard_runtime, module_origins, reject_foreign_modules

REQUIRED_ROOT_MODULES = {REQUIRED_ROOT_MODULES!r}
RUNTIME_RECEIPT = guard_runtime(
    ROOT,
    expected_source_sha256={source_sha256!r},
    expected_runtime_tree_sha256={tree_sha256!r},
    extra_sha256={extras!r},
    entry_name={entry_name!r},
)
reject_foreign_modules(ROOT, REQUIRED_ROOT_MODULES)
'''
    if mode == "candidate":
        body = '''\
import selected_sell_core as _selected_sell_core

_overlay_path = ROOT / "own_value_objective.py"
_overlay_spec = importlib.util.spec_from_file_location(
    "_titan_archive_own_value_objective_overlay", _overlay_path
)
if _overlay_spec is None or _overlay_spec.loader is None:
    raise ImportError("cannot load own-value objective overlay from carrier root")
_overlay = importlib.util.module_from_spec(_overlay_spec)
_overlay_spec.loader.exec_module(_overlay)
INSTALL_RECEIPT = _overlay.install(module=_selected_sell_core, expected_root=ROOT)
if INSTALL_RECEIPT.get("changed_field") != "MarketPath.score[0]":
    raise RuntimeError("own-value overlay changed an unexpected field")
if INSTALL_RECEIPT.get("actual_git_blob") != INSTALL_RECEIPT.get("expected_git_blob"):
    raise RuntimeError("own-value overlay source binding is not exact")
if INSTALL_RECEIPT.get("canonical_files_modified") is not False:
    raise RuntimeError("own-value overlay reported canonical file mutation")

import main as _canonical_main
MODULE_ORIGINS = module_origins(ROOT, REQUIRED_ROOT_MODULES)


def agent(observation, configuration=None):
    return _canonical_main.agent(observation, configuration)
'''
    else:
        body = '''\
import main as _canonical_main
MODULE_ORIGINS = module_origins(ROOT, REQUIRED_ROOT_MODULES)


def agent(observation, configuration=None):
    return _canonical_main.agent(observation, configuration)
'''
    return textwrap.dedent(common + body).encode("utf-8")


def _copy_runtime(root: Path, members: Mapping[str, bytes]) -> None:
    for name in sorted(members):
        _write_member(root, name, members[name])


def materialize_pair(
    *,
    lab_root: Path,
    pointer_path: Path,
    overlay_path: Path,
    guard_path: Path,
    output_root: Path,
    git_head: str | None,
) -> dict[str, Any]:
    lab_root = lab_root.resolve(strict=True)
    pointer_path = pointer_path.resolve(strict=True)
    expected_pointer = (
        lab_root / "runtime" / "integrated-selected" / "CURRENT-ARCHIVE.json"
    ).resolve(strict=True)
    if pointer_path != expected_pointer:
        raise ArchiveCarrierError(
            f"pointer must be the canonical CURRENT-ARCHIVE.json: {expected_pointer}"
        )
    overlay_path = overlay_path.resolve(strict=True)
    if overlay_path.name != "own_value_objective.py":
        raise ArchiveCarrierError("overlay source must be named own_value_objective.py")
    guard_path = guard_path.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise ArchiveCarrierError(f"output root already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)

    pointer, pointer_bytes = _read_pointer(lab_root, pointer_path)
    members, archive_bytes = _read_archive(lab_root, pointer)
    source, rows, source_sha = _validate_source_manifest(lab_root, pointer, members)
    tree_sha = runtime_tree_sha256(rows)
    overlay_bytes = overlay_path.read_bytes()
    guard_bytes = guard_path.read_bytes()
    overlay_sha = _sha256(overlay_bytes)
    guard_sha = _sha256(guard_bytes)
    entries = {
        mode: _entry_source(
            mode=mode,
            source_sha256=source_sha,
            tree_sha256=tree_sha,
            guard_sha256=guard_sha,
            overlay_sha256=overlay_sha if mode == "candidate" else None,
        )
        for mode in ("control", "candidate")
    }

    stage = output_root.parent / f".{output_root.name}.{uuid.uuid4().hex}.tmp"
    stage.mkdir(mode=0o755)
    try:
        for mode in ("control", "candidate"):
            root = stage / mode
            root.mkdir(mode=0o755)
            _copy_runtime(root, members)
            _write_member(root, "archive_runtime_guard.py", guard_bytes)
            if mode == "candidate":
                _write_member(root, "own_value_objective.py", overlay_bytes)
            _write_member(root, f"{mode}_entry.py", entries[mode])
            try:
                guard_runtime(
                    root,
                    expected_source_sha256=source_sha,
                    expected_runtime_tree_sha256=tree_sha,
                    extra_sha256={
                        "archive_runtime_guard.py": guard_sha,
                        **({"own_value_objective.py": overlay_sha} if mode == "candidate" else {}),
                    },
                    entry_name=f"{mode}_entry.py",
                )
            except ArchiveRuntimeGuardError as exc:
                raise ArchiveCarrierError(f"generated {mode} root failed self-verification: {exc}") from exc

        receipt = {
            "schema_version": 1,
            "operation": "TITAN-PR11899-ARCHIVE-CLOSURE-CARRIER-20260909-01",
            "git_head": git_head,
            "archive": {
                "path": pointer["path"],
                "sha256": _sha256(archive_bytes),
                "bytes": len(archive_bytes),
                "pointer_sha256": _sha256(pointer_bytes),
                "source_manifest": pointer["source_manifest"],
                "source_manifest_sha256": source_sha,
                "runtime_files": len(rows),
                "runtime_tree_sha256": tree_sha,
                "entrypoint": pointer["entrypoint"],
                "config": pointer["config"],
            },
            "control": {
                "root": "control",
                "entrypoint": "control/control_entry.py::agent",
                "entry_sha256": _sha256(entries["control"]),
                "runtime_tree_sha256": tree_sha,
                "overlay_installed": False,
            },
            "candidate": {
                "root": "candidate",
                "entrypoint": "candidate/candidate_entry.py::agent",
                "entry_sha256": _sha256(entries["candidate"]),
                "runtime_tree_sha256": tree_sha,
                "overlay_installed": True,
                "overlay_sha256": overlay_sha,
                "overlay_git_blob": _git_blob_sha1(overlay_bytes),
            },
            "guard_sha256": guard_sha,
            "canonical_runtime_equal": True,
            "canonical_repository_modified": False,
            "source_entrypoint": source.get("entrypoint"),
        }
        _write_member(
            stage,
            "CARRIER-RECEIPT.json",
            (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"),
        )
        os.replace(stage, output_root)
        return receipt
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def verify_pair(output_root: Path) -> dict[str, Any]:
    """Revalidate a published pair, including generated entrypoint fingerprints."""
    output_root = output_root.resolve(strict=True)
    receipt_path = output_root / "CARRIER-RECEIPT.json"
    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        raise ArchiveCarrierError(f"cannot read carrier receipt: {exc}") from exc
    receipt = _strict_json_bytes(receipt_bytes, "CARRIER-RECEIPT.json")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ArchiveCarrierError("unsupported carrier receipt schema")
    archive = receipt.get("archive")
    if not isinstance(archive, dict):
        raise ArchiveCarrierError("carrier receipt lacks archive identity")
    source_sha = _hex_digest(archive.get("source_manifest_sha256"), "source manifest SHA-256")
    tree_sha = _hex_digest(archive.get("runtime_tree_sha256"), "runtime tree SHA-256")
    guard_sha = _hex_digest(receipt.get("guard_sha256"), "guard SHA-256")
    if receipt.get("canonical_runtime_equal") is not True:
        raise ArchiveCarrierError("carrier receipt does not certify equal canonical runtimes")
    if receipt.get("canonical_repository_modified") is not False:
        raise ArchiveCarrierError("carrier receipt reports canonical repository mutation")

    expected_top = {"control", "candidate", "CARRIER-RECEIPT.json"}
    actual_top = {path.name for path in output_root.iterdir()}
    if actual_top != expected_top:
        raise ArchiveCarrierError(
            f"carrier output top-level drift: missing={sorted(expected_top-actual_top)!r}, "
            f"unexpected={sorted(actual_top-expected_top)!r}"
        )

    arms: dict[str, Any] = {}
    for mode in ("control", "candidate"):
        arm = receipt.get(mode)
        if not isinstance(arm, dict):
            raise ArchiveCarrierError(f"carrier receipt lacks {mode} arm")
        if arm.get("root") != mode:
            raise ArchiveCarrierError(f"{mode} arm root identity drift")
        if _hex_digest(arm.get("runtime_tree_sha256"), f"{mode} tree SHA-256") != tree_sha:
            raise ArchiveCarrierError(f"{mode} runtime tree differs from archive receipt")
        expected_overlay = mode == "candidate"
        if arm.get("overlay_installed") is not expected_overlay:
            raise ArchiveCarrierError(f"{mode} overlay identity drift")
        expected_entrypoint = f"{mode}/{mode}_entry.py::agent"
        if arm.get("entrypoint") != expected_entrypoint:
            raise ArchiveCarrierError(f"{mode} entrypoint identity drift")
        root = output_root / mode
        extras = {"archive_runtime_guard.py": guard_sha}
        if mode == "candidate":
            overlay_sha = _hex_digest(arm.get("overlay_sha256"), "candidate overlay SHA-256")
            extras["own_value_objective.py"] = overlay_sha
            overlay_bytes = (root / "own_value_objective.py").read_bytes()
            actual_blob = _git_blob_sha1(overlay_bytes)
            expected_blob = arm.get("overlay_git_blob")
            if not isinstance(expected_blob, str) or len(expected_blob) != 40:
                raise ArchiveCarrierError("candidate overlay Git-blob receipt is malformed")
            try:
                int(expected_blob, 16)
            except ValueError as exc:
                raise ArchiveCarrierError("candidate overlay Git-blob receipt is malformed") from exc
            if actual_blob != expected_blob.lower():
                raise ArchiveCarrierError(
                    f"candidate overlay Git-blob drift: expected {expected_blob}, got {actual_blob}"
                )
        try:
            runtime = guard_runtime(
                root,
                expected_source_sha256=source_sha,
                expected_runtime_tree_sha256=tree_sha,
                extra_sha256=extras,
                entry_name=f"{mode}_entry.py",
            )
        except ArchiveRuntimeGuardError as exc:
            raise ArchiveCarrierError(f"{mode} root verification failed: {exc}") from exc
        entry_path = root / f"{mode}_entry.py"
        actual_entry_sha = _sha256(entry_path.read_bytes())
        expected_entry_sha = _hex_digest(arm.get("entry_sha256"), f"{mode} entry SHA-256")
        if actual_entry_sha != expected_entry_sha:
            raise ArchiveCarrierError(
                f"{mode} entrypoint drift: expected {expected_entry_sha}, got {actual_entry_sha}"
            )
        arms[mode] = {
            "entry_sha256": actual_entry_sha,
            "runtime": runtime,
        }
    return {
        "schema_version": 1,
        "operation": receipt.get("operation"),
        "receipt_sha256": _sha256(receipt_bytes),
        "source_manifest_sha256": source_sha,
        "runtime_tree_sha256": tree_sha,
        "canonical_runtime_equal": True,
        "arms": arms,
    }


PROBE_CODE = r'''
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys

path = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location("_titan_archive_carrier_probe", path)
if spec is None or spec.loader is None:
    raise SystemExit("entrypoint spec unavailable")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = {
    "agent_callable": callable(getattr(module, "agent", None)),
    "module_origins": getattr(module, "MODULE_ORIGINS", None),
    "runtime_receipt": getattr(module, "RUNTIME_RECEIPT", None),
    "install_receipt": getattr(module, "INSTALL_RECEIPT", None),
}
print(json.dumps(result, sort_keys=True, allow_nan=False))
'''


def probe_entry(entry: Path, output: Path | None = None) -> dict[str, Any]:
    entry = entry.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="titan-archive-carrier-probe-") as cwd:
        env = {
            "PATH": os.defpath,
            "HOME": cwd,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", PROBE_CODE, str(entry)],
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    if completed.returncode != 0:
        raise ArchiveCarrierError(
            f"entrypoint probe failed ({completed.returncode}): {completed.stderr[-2000:]}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ArchiveCarrierError("entrypoint probe did not emit JSON") from exc
    if not isinstance(result, dict) or result.get("agent_callable") is not True:
        raise ArchiveCarrierError("entrypoint probe did not resolve a callable agent")
    origins = result.get("module_origins")
    if not isinstance(origins, dict) or set(origins) != set(REQUIRED_ROOT_MODULES):
        raise ArchiveCarrierError("entrypoint probe did not bind every required root module")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    materialize = sub.add_parser("materialize", help="materialize verified control/candidate roots")
    materialize.add_argument("--lab-root", type=Path, required=True)
    materialize.add_argument("--pointer", type=Path, required=True)
    materialize.add_argument("--overlay", type=Path, required=True)
    materialize.add_argument(
        "--guard",
        type=Path,
        default=Path(__file__).resolve().with_name("archive_runtime_guard.py"),
    )
    materialize.add_argument("--output", type=Path, required=True)
    materialize.add_argument("--git-head")

    probe = sub.add_parser("probe", help="load one generated entrypoint in an isolated process")
    probe.add_argument("--entry", type=Path, required=True)
    probe.add_argument("--output", type=Path)

    verify = sub.add_parser("verify", help="revalidate a published carrier pair")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "materialize":
            result = materialize_pair(
                lab_root=args.lab_root,
                pointer_path=args.pointer,
                overlay_path=args.overlay,
                guard_path=args.guard,
                output_root=args.output,
                git_head=args.git_head,
            )
        elif args.command == "probe":
            result = probe_entry(args.entry, args.output)
        else:
            result = verify_pair(args.root)
            if args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8",
                )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ArchiveCarrierError, ArchiveRuntimeGuardError, OSError, ValueError) as exc:
        print(f"archive carrier error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
