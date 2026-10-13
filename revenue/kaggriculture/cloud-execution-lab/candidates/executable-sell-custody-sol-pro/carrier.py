# SPDX-License-Identifier: Apache-2.0
"""Canonical TITAN entrypoint with private executable-prefix receipt profiling.

The candidate never imports the mutable repository runtime graph directly.  It
verifies the exact current canonical archive, materializes every declared member
into a private process-owned arena, rejects ambient root-module collisions, and
loads canonical ``main.py`` from that arena.  Only the arena-local
``frozen_selected.FrozenSelected`` binding is replaced, before canonical lazy
construction, by the source-pinned receipt-profile subclass.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
ARCHIVE = LAB / "exports" / "titan-current.tar.gz"
PATCH = HERE / "executable_receipt_profile.py"

EXPECTED_ARCHIVE_SHA256 = "17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86"
EXPECTED_ARCHIVE_BYTES = 427_870
EXPECTED_SOURCE_MANIFEST_SHA256 = "1feec5a68ffde28ab7b5c7d2c92a34aa66ff5705b7d88182ef6af98df8bb5083"
EXPECTED_RUNTIME_FILES = 109
EXPECTED_ARCHIVE_MEMBERS = EXPECTED_RUNTIME_FILES + 1  # SOURCE.json
EXPECTED_PATCH_GIT_BLOB = "8e984812e15a84db14ee7311b047e0c8483132da"
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load(name: str, path: Path):
    """Load one exact file under a collision-resistant private module name."""
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"private candidate source is not a regular file: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        raise
    return module


def _safe_member_parts(name: str) -> tuple[str, ...]:
    """Return one canonical relative POSIX member path or fail closed."""
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise RuntimeError("canonical archive contains an invalid member name")
    pure = PurePosixPath(name)
    parts = pure.parts
    if pure.is_absolute() or not parts or any(part in ("", ".", "..") for part in parts):
        raise RuntimeError(f"unsafe canonical archive member: {name!r}")
    if PurePosixPath(*parts).as_posix() != name:
        raise RuntimeError(f"noncanonical archive member path: {name!r}")
    return tuple(parts)


def _verify_manifest(root: Path, members: Mapping[str, bytes]) -> dict[str, Any]:
    manifest_bytes = members.get("SOURCE.json")
    if manifest_bytes is None:
        raise RuntimeError("canonical archive is missing SOURCE.json")
    if _sha256(manifest_bytes) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("canonical SOURCE.json digest drift")
    try:
        manifest = json.loads(manifest_bytes)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("canonical SOURCE.json is not valid JSON") from exc
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or len(runtime) != EXPECTED_RUNTIME_FILES:
        raise RuntimeError("canonical runtime member cardinality drift")
    if manifest.get("entrypoint") != "main.py::agent":
        raise RuntimeError("canonical archive entrypoint drift")
    if manifest.get("config") != "TITAN-CONFIG.json":
        raise RuntimeError("canonical archive config drift")
    expected_names = set(runtime) | {"SOURCE.json"}
    if set(members) != expected_names:
        missing = sorted(expected_names - set(members))
        extra = sorted(set(members) - expected_names)
        raise RuntimeError(
            f"canonical archive/member manifest mismatch; missing={missing[:4]}, extra={extra[:4]}"
        )
    for name, metadata in runtime.items():
        _safe_member_parts(name)
        if not isinstance(metadata, dict):
            raise RuntimeError(f"invalid canonical runtime metadata for {name}")
        data = members[name]
        if type(metadata.get("bytes")) is not int or metadata["bytes"] != len(data):
            raise RuntimeError(f"canonical runtime byte-count drift for {name}")
        digest = metadata.get("sha256")
        if not isinstance(digest, str) or digest != _sha256(data):
            raise RuntimeError(f"canonical runtime digest drift for {name}")
        if not isinstance(metadata.get("source_path"), str):
            raise RuntimeError(f"canonical runtime source identity missing for {name}")
        target = root.joinpath(*PurePosixPath(name).parts)
        if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
            raise RuntimeError(f"private runtime materialization drift for {name}")
    return manifest


def _materialize_private_runtime():
    """Verify and materialize the exact standalone canonical archive."""
    if not ARCHIVE.is_file() or ARCHIVE.is_symlink():
        raise RuntimeError(f"canonical archive is not a regular file: {ARCHIVE}")
    archive_bytes = ARCHIVE.read_bytes()
    if len(archive_bytes) != EXPECTED_ARCHIVE_BYTES:
        raise RuntimeError(
            f"canonical archive length drift: expected {EXPECTED_ARCHIVE_BYTES}, got {len(archive_bytes)}"
        )
    actual_archive_sha256 = _sha256(archive_bytes)
    if actual_archive_sha256 != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(
            "canonical archive digest drift: "
            f"expected {EXPECTED_ARCHIVE_SHA256}, got {actual_archive_sha256}"
        )

    owner = tempfile.TemporaryDirectory(prefix="titan-sol-quoin-runtime-")
    root = Path(owner.name).resolve()
    members: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as bundle:
            for member in bundle:
                if not member.isfile():
                    raise RuntimeError(
                        f"canonical archive member is not a regular file: {member.name!r}"
                    )
                parts = _safe_member_parts(member.name)
                if member.name in members:
                    raise RuntimeError(f"duplicate canonical archive member: {member.name}")
                if type(member.size) is not int or not 0 <= member.size <= MAX_MEMBER_BYTES:
                    raise RuntimeError(f"canonical archive member size rejected: {member.name}")
                stream = bundle.extractfile(member)
                if stream is None:
                    raise RuntimeError(f"cannot read canonical archive member: {member.name}")
                data = stream.read(member.size + 1)
                if len(data) != member.size:
                    raise RuntimeError(f"canonical archive member length mismatch: {member.name}")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise RuntimeError("canonical archive exceeds private-runtime byte ceiling")
                target = root.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(data)
                members[member.name] = data
        if len(members) != EXPECTED_ARCHIVE_MEMBERS:
            raise RuntimeError(
                "canonical archive member cardinality drift: "
                f"expected {EXPECTED_ARCHIVE_MEMBERS}, got {len(members)}"
            )
        manifest = _verify_manifest(root, members)
    except BaseException:
        owner.cleanup()
        raise

    receipt = {
        "archive_sha256": actual_archive_sha256,
        "archive_bytes": len(archive_bytes),
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "runtime_files": len(manifest["runtime"]),
        "archive_members": len(members),
        "materialized_bytes": total,
        "entrypoint": manifest["entrypoint"],
        "config": manifest["config"],
    }
    return owner, root, manifest, receipt


def _runtime_collision_names(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    names: set[str] = set()
    for raw_name in manifest["runtime"]:
        path = PurePosixPath(raw_name)
        if len(path.parts) == 1 and path.suffix == ".py" and path.stem != "main":
            names.add(path.stem)
        elif len(path.parts) > 1 and path.parts[0] == "reference":
            names.add("reference")
    return tuple(sorted(names))


def _module_origin(module: Any) -> Path | None:
    value = getattr(module, "__file__", None)
    if not value:
        return None
    try:
        return Path(value).resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _assert_private_runtime_modules() -> None:
    """Never consume a same-named module imported from outside this arena."""
    for name in _RUNTIME_NAMES:
        module = sys.modules.get(name)
        if module is None:
            continue
        origin = _module_origin(module)
        if origin is None or not _inside(_ARENA_ROOT, origin):
            raise RuntimeError(
                f"ambient runtime module collision: {name} from {origin or '<unknown>'}"
            )


def _assert_arena_module(module: Any, relative: str) -> None:
    origin = _module_origin(module)
    expected = (_ARENA_ROOT / relative).resolve()
    if origin != expected:
        raise RuntimeError(
            f"private runtime import escaped arena: expected {expected}, got {origin}"
        )


_ARENA_OWNER, _ARENA_ROOT, _ARENA_MANIFEST, _ARENA_RECEIPT = (
    _materialize_private_runtime()
)
_RUNTIME_NAMES = _runtime_collision_names(_ARENA_MANIFEST)
_assert_private_runtime_modules()
_arena_text = str(_ARENA_ROOT)
while _arena_text in sys.path:
    sys.path.remove(_arena_text)
sys.path.insert(0, _arena_text)

if not PATCH.is_file() or PATCH.is_symlink():
    raise RuntimeError(f"candidate patch is not a regular file: {PATCH}")
actual_patch_blob = _git_blob_sha1(PATCH)
if actual_patch_blob != EXPECTED_PATCH_GIT_BLOB:
    raise RuntimeError(
        f"candidate patch drift: expected {EXPECTED_PATCH_GIT_BLOB}, got {actual_patch_blob}"
    )
_PATCH_MODULE = _load("_sol_quoin_executable_receipt_profile_patch", PATCH)
_install = _PATCH_MODULE.install
_CANONICAL = _load(
    "_sol_quoin_receipt_profile_private_main", _ARENA_ROOT / "main.py"
)
_ORIGINAL_NEW_INSTANCE = _CANONICAL._new_instance
_LAST_INSTALL_RECEIPT: dict[str, Any] | None = None


def _candidate_new_instance(root: Path, feature_data: dict[str, Any]):
    """Patch only the private arena before canonical lazy construction."""
    global _LAST_INSTALL_RECEIPT
    if Path(root).resolve() != _ARENA_ROOT:
        raise RuntimeError(
            f"canonical main escaped private arena: expected {_ARENA_ROOT}, got {Path(root).resolve()}"
        )
    _assert_private_runtime_modules()
    import frozen_selected

    _assert_arena_module(frozen_selected, "frozen_selected.py")
    install_receipt = _install(frozen_selected)
    instance = _ORIGINAL_NEW_INSTANCE(root, feature_data)
    import titan_runtime

    _assert_arena_module(titan_runtime, "titan_runtime.py")
    _assert_private_runtime_modules()
    _LAST_INSTALL_RECEIPT = {
        **install_receipt,
        "private_runtime": dict(_ARENA_RECEIPT),
        "patch_git_blob": actual_patch_blob,
        "frozen_selected_origin": str(Path(frozen_selected.__file__).resolve()),
        "titan_runtime_origin": str(Path(titan_runtime.__file__).resolve()),
    }
    return instance


# Canonical ``agent`` resolves this hook at construction time.  Its prelude,
# whole-call deadline, fallback, reconstruction, final-pressure ordering, and
# every post-selection transform remain the canonical implementation.
_CANONICAL._new_instance = _candidate_new_instance


def agent(observation, configuration=None):
    return _CANONICAL.agent(observation, configuration)
