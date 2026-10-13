# SPDX-License-Identifier: Apache-2.0
"""Canonical TITAN entrypoint with isolated saturated-queue SELL expansion."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPOSITORY = LAB.parents[2].resolve()
BUILD_INTEGRATED = LAB / "build_integrated.py"
SOURCE_MANIFEST = LAB / "runtime/integrated-selected/CURRENT-SOURCE.json"
EXPECTED_GIT_BLOBS = {
    HERE / "growth_patch.py": "f1803dafb558745376f28d3c9e005c4688ff4452",
    LAB / "main.py": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    LAB / "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    LAB / "frozen_selected.py": "fc7baf5c179818a55037f6a61d92984d81d1a21c",
    LAB / "TITAN-CONFIG.json": "3a3bef83899d3010fad623b628d9e95d9978111b",
    BUILD_INTEGRATED: "05994d946885ff0fe2a2ce77439fd335174900aa",
    SOURCE_MANIFEST: "f5d8a9f1338dbef5396de8f23262453b0f70e832",
}
REQUIRED_ROOT_MODULES = {
    "frozen_selected",
    "mechanics",
    "observed_clone",
    "scheduler",
    "selected_sell_core",
    "seller_snapshot",
    "titan_runtime",
}


def _regular_repository_file(path: Path) -> Path:
    """Return a normalized regular file below the checkout with no symlink hop."""
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(REPOSITORY)
    except ValueError as error:
        raise RuntimeError(f"SOL-AMPLIFIER source escapes checkout: {path}") from error
    cursor = REPOSITORY
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError(f"SOL-AMPLIFIER source uses a symlink: {cursor}")
    if not lexical.is_file():
        raise RuntimeError(f"SOL-AMPLIFIER dependency is not a regular file: {lexical}")
    resolved = lexical.resolve(strict=True)
    if resolved != lexical:
        raise RuntimeError(f"SOL-AMPLIFIER source resolution changed: {lexical} -> {resolved}")
    return lexical


def _git_blob_sha1(path: Path) -> str:
    data = _regular_repository_file(path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(_regular_repository_file(path).read_bytes()).hexdigest()


def _load_private(name: str, path: Path):
    """Execute an exact source file without publishing a process-global alias."""
    source = _regular_repository_file(path)
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_entry_files() -> dict[str, str]:
    receipt: dict[str, str] = {}
    for path, expected in EXPECTED_GIT_BLOBS.items():
        actual = _git_blob_sha1(path)
        if actual != expected:
            raise RuntimeError(
                f"SOL-AMPLIFIER dependency drift: {path.name}; "
                f"expected {expected}, got {actual}"
            )
        receipt[path.relative_to(REPOSITORY).as_posix()] = actual
    return receipt


def _manifest_runtime() -> Mapping[str, Mapping[str, Any]]:
    payload = json.loads(_regular_repository_file(SOURCE_MANIFEST).read_text(encoding="utf-8"))
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise RuntimeError("SOL-AMPLIFIER current source manifest has no runtime map")
    return runtime


def _verify_and_install_source_roots() -> dict[str, Any]:
    """Bind source-tree bare imports to the canonical archive source closure.

    ``frozen_selected`` imports ``scheduler``, which imports ``observed_clone``
    from a repository sibling mapped beside it in the canonical archive.  A
    raw source-tree loader otherwise sees only the candidate and lab parents.
    Derive the full mapping from the pinned canonical builder, verify every
    mapped byte against the pinned current manifest, then expose only the
    mapped root parents in canonical source-tree order.
    """
    builder = _load_private("_sol_amplifier_build_integrated", BUILD_INTEGRATED)
    mapping = builder.source_files()
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("SOL-AMPLIFIER canonical source map is empty")
    runtime = _manifest_runtime()
    if set(mapping) != set(runtime):
        missing = sorted(set(mapping) - set(runtime))
        extra = sorted(set(runtime) - set(mapping))
        raise RuntimeError(
            f"SOL-AMPLIFIER source-map/manifest mismatch; missing={missing[:4]} extra={extra[:4]}"
        )

    source_records: dict[str, dict[str, Any]] = {}
    root_records: dict[str, dict[str, Any]] = {}
    mapped_parents: list[Path] = []
    seen_parents: set[Path] = {LAB.resolve()}
    closure_digest = hashlib.sha256()

    for member in sorted(mapping):
        raw_source = mapping[member]
        if not isinstance(member, str) or not isinstance(raw_source, str):
            raise RuntimeError("SOL-AMPLIFIER source map must contain string paths")
        record = runtime.get(member)
        if not isinstance(record, dict):
            raise RuntimeError(f"SOL-AMPLIFIER manifest record missing for {member}")
        origin = _regular_repository_file(LAB / raw_source)
        data = origin.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if (
            record.get("source_path") != raw_source
            or type(record.get("bytes")) is not int
            or record.get("bytes") != len(data)
            or record.get("sha256") != digest
        ):
            raise RuntimeError(f"SOL-AMPLIFIER manifest byte mismatch for {member}")
        relative_origin = origin.relative_to(REPOSITORY).as_posix()
        source_records[member] = {
            "source_path": raw_source,
            "repository_path": relative_origin,
            "bytes": len(data),
            "sha256": digest,
        }
        closure_digest.update(member.encode("utf-8") + b"\0")
        closure_digest.update(relative_origin.encode("utf-8") + b"\0")
        closure_digest.update(bytes.fromhex(digest))

        member_path = Path(member)
        if member_path.parent != Path(".") or member_path.suffix != ".py":
            continue
        module_name = member_path.stem
        if not module_name.isidentifier() or module_name in root_records:
            raise RuntimeError(f"SOL-AMPLIFIER invalid root module mapping: {member}")
        allowed = {origin}
        mirror = Path(os.path.abspath(LAB / member))
        if mirror != origin and mirror.is_file() and not mirror.is_symlink():
            mirror = _regular_repository_file(mirror)
            if _sha256(mirror) == digest:
                allowed.add(mirror)
        root_records[module_name] = {
            "member": member,
            "declared_origin": relative_origin,
            "allowed_origins": sorted(
                path.relative_to(REPOSITORY).as_posix() for path in allowed
            ),
            "sha256": digest,
        }
        parent = origin.parent
        if parent not in seen_parents:
            seen_parents.add(parent)
            mapped_parents.append(parent)

    if not REQUIRED_ROOT_MODULES.issubset(root_records):
        absent = sorted(REQUIRED_ROOT_MODULES - set(root_records))
        raise RuntimeError(f"SOL-AMPLIFIER required root modules absent: {absent}")

    # Candidate-local helpers win first. Manifest-derived root parents precede
    # the lab fallback so compatibility mirrors with different bytes cannot
    # shadow the archive-owned modules they share a bare import name with.
    ordered = [HERE.resolve(), *mapped_parents, LAB.resolve()]
    for root in reversed(ordered):
        value = str(root)
        while value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)

    for module_name, record in root_records.items():
        allowed = {REPOSITORY / path for path in record["allowed_origins"]}
        loaded = sys.modules.get(module_name)
        if loaded is not None:
            loaded_file = getattr(loaded, "__file__", None)
            if not loaded_file or _regular_repository_file(Path(loaded_file)) not in allowed:
                raise RuntimeError(
                    f"SOL-AMPLIFIER preloaded module collision: {module_name}"
                )
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            raise RuntimeError(f"SOL-AMPLIFIER root module is not importable: {module_name}")
        actual = _regular_repository_file(Path(spec.origin))
        if actual not in allowed or _sha256(actual) != record["sha256"]:
            raise RuntimeError(
                f"SOL-AMPLIFIER root module resolves outside closure: "
                f"{module_name} -> {actual}"
            )
        record["import_origin"] = actual.relative_to(REPOSITORY).as_posix()

    observed = root_records["observed_clone"]
    return {
        "mapped_files": len(source_records),
        "mapped_sha256": closure_digest.hexdigest(),
        "root_modules": root_records,
        "pythonpath": [path.relative_to(REPOSITORY).as_posix() for path in ordered],
        "observed_clone": {
            "import_origin": observed["import_origin"],
            "sha256": observed["sha256"],
        },
    }


_ENTRY_FILES = _verify_entry_files()
_SOURCE_CLOSURE = _verify_and_install_source_roots()
_GROWTH_PATCH = _load_private(
    "_sol_amplifier_full_queue_growth_patch", HERE / "growth_patch.py"
)
attach = _GROWTH_PATCH.attach
_CANONICAL = _load_private(
    "_sol_amplifier_full_queue_growth_main", LAB / "main.py"
)
_ORIGINAL_NEW_INSTANCE = _CANONICAL._new_instance
_LAST_INSTALL_RECEIPT: dict[str, Any] | None = None


def _candidate_new_instance(root: Path, feature_data: dict[str, Any]):
    """Attach the private selected-seller class before canonical lazy init."""
    global _LAST_INSTALL_RECEIPT
    instance = _ORIGINAL_NEW_INSTANCE(root, feature_data)
    import frozen_selected

    expected = REPOSITORY / _SOURCE_CLOSURE["root_modules"]["frozen_selected"]["import_origin"]
    actual = _regular_repository_file(Path(frozen_selected.__file__))
    if actual != expected:
        raise RuntimeError(f"SOL-AMPLIFIER selected consumer alias: {actual} != {expected}")
    _LAST_INSTALL_RECEIPT = {
        **attach(instance, frozen_selected),
        "entry_files": dict(_ENTRY_FILES),
        "source_closure": dict(_SOURCE_CLOSURE),
    }
    return instance


# Canonical agent resolves this global during its existing timed construction.
# Its prelude, whole-call deadline, fallback, reconstruction and final-pressure
# return boundary remain the original implementation.
_CANONICAL._new_instance = _candidate_new_instance


def agent(observation, configuration=None):
    return _CANONICAL.agent(observation, configuration)
