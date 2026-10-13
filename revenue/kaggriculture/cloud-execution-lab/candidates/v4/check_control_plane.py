#!/usr/bin/env python3
"""Strict byte/custody preflight for the sole canonical TITAN V4 control plane.

This wrapper does not replace the existing composition/integration validators. It
first rejects ambiguous control bytes and trust-path tricks, snapshots the exact
validator sources and strict ledger inputs used by this run, then delegates to
the existing validators without reopening those ledger trust bytes.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import stat
import sys
import tempfile
import types
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_FILES = ("CANONICAL.json", "INTEGRATION.json", "COMPOSITION.json")
GIT_BLOB_ID = re.compile(r"git-blob:[0-9a-f]{40}\Z")
RELATION_FIELDS = ("requires", "before", "after", "conflicts")
DECLARED_PATH_FIELDS = ("receipt", "composition_receipt")
DELEGATE_FILES = ("check_integration_ledger.py", "check_composition_graph.py")


class ControlPlaneError(ValueError):
    pass


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ControlPlaneError(f"duplicate object key {key!r}")
        out[key] = value
    return out


def _reject_constant(token: str) -> Any:
    raise ControlPlaneError(f"non-finite JSON constant {token!r}")


def _safe_relpath(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    p = PurePosixPath(value)
    return not p.is_absolute() and "." not in p.parts and ".." not in p.parts


def _require_secure_open_capabilities() -> None:
    for name in ("O_DIRECTORY", "O_NOFOLLOW"):
        value = getattr(os, name, None)
        if isinstance(value, bool) or not isinstance(value, int) or value == 0:
            raise ControlPlaneError(f"secure control-root traversal requires os.{name}")
    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    if os.open not in supports_dir_fd:
        raise ControlPlaneError("secure control-root traversal requires os.open dir_fd support")


def _require_topology_snapshot_capabilities() -> None:
    _require_secure_open_capabilities()
    if os.listdir not in getattr(os, "supports_fd", ()):
        raise ControlPlaneError("secure topology snapshot requires os.listdir fd support")
    if os.stat not in getattr(os, "supports_dir_fd", ()):
        raise ControlPlaneError("secure topology snapshot requires os.stat dir_fd support")
    if os.stat not in getattr(os, "supports_follow_symlinks", ()):
        raise ControlPlaneError("secure topology snapshot requires os.stat follow_symlinks support")


def _dir_open_flags() -> int:
    _require_secure_open_capabilities()
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_DIRECTORY | os.O_NOFOLLOW


def _file_open_flags() -> int:
    _require_secure_open_capabilities()
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW


def _topology_identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _directory_epoch(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


def _snapshot_directory_topology(
    source_fd: int,
    snapshot_root: Path,
    prefix: PurePosixPath = PurePosixPath(),
) -> None:
    """Mirror names and file kinds from one anchored directory into a temp tree."""
    before_directory = os.fstat(source_fd)
    if not stat.S_ISDIR(before_directory.st_mode):
        raise ControlPlaneError(f"composition topology {prefix.as_posix()!r} is not a directory")
    try:
        names = sorted(os.listdir(source_fd))
    except OSError as exc:
        raise ControlPlaneError(
            f"cannot list composition topology {prefix.as_posix()!r}: {exc}"
        ) from exc

    for name in names:
        rel = prefix / name
        try:
            before = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        except OSError as exc:
            raise ControlPlaneError(f"cannot stat composition topology {rel.as_posix()!r}: {exc}") from exc

        destination = snapshot_root / rel
        if stat.S_ISDIR(before.st_mode):
            child_fd = -1
            try:
                try:
                    child_fd = os.open(name, _dir_open_flags(), dir_fd=source_fd)
                except OSError as exc:
                    raise ControlPlaneError(
                        f"cannot open composition topology directory {rel.as_posix()!r}: {exc}"
                    ) from exc
                opened = os.fstat(child_fd)
                if _topology_identity(opened) != _topology_identity(before):
                    raise ControlPlaneError(
                        f"composition topology changed before directory capture at {rel.as_posix()!r}"
                    )
                destination.mkdir(parents=True, exist_ok=False)
                _snapshot_directory_topology(child_fd, snapshot_root, rel)
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
        elif stat.S_ISREG(before.st_mode):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.touch(exist_ok=False)
        elif stat.S_ISLNK(before.st_mode):
            raise ControlPlaneError(
                f"symlink ancestry is forbidden at {rel.as_posix()!r}; object must not be a symlink"
            )
        else:
            raise ControlPlaneError(
                f"unsupported composition topology object at {rel.as_posix()!r}"
            )

        try:
            after = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        except OSError as exc:
            raise ControlPlaneError(
                f"composition topology changed during capture at {rel.as_posix()!r}: {exc}"
            ) from exc
        if _topology_identity(after) != _topology_identity(before):
            raise ControlPlaneError(
                f"composition topology changed during capture at {rel.as_posix()!r}"
            )

    try:
        names_after = sorted(os.listdir(source_fd))
    except OSError as exc:
        raise ControlPlaneError(
            f"cannot relist composition topology {prefix.as_posix()!r}: {exc}"
        ) from exc
    after_directory = os.fstat(source_fd)
    if names_after != names or _directory_epoch(after_directory) != _directory_epoch(before_directory):
        raise ControlPlaneError(
            f"composition topology directory changed during capture at {prefix.as_posix()!r}"
        )


def _capture_topology_snapshot(root_fd: int, snapshot_root: Path) -> None:
    """Capture one immutable directory/regular-file topology from the anchored root."""
    _require_topology_snapshot_capabilities()
    try:
        source_fd = os.dup(root_fd)
    except OSError as exc:
        raise ControlPlaneError(f"cannot duplicate control root for topology snapshot: {exc}") from exc
    try:
        _snapshot_directory_topology(source_fd, snapshot_root)
    except OSError as exc:
        raise ControlPlaneError(f"cannot materialize composition topology snapshot: {exc}") from exc
    finally:
        os.close(source_fd)


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_control_root(root: Path, *, label: str = "control root") -> int:
    """Anchor one lexical absolute directory without following any ancestor."""
    _require_secure_open_capabilities()
    absolute = _lexical_absolute(root)
    anchor = absolute.anchor
    if not anchor:
        raise ControlPlaneError(f"{label}: absolute filesystem anchor is unavailable")
    current_fd = -1
    try:
        try:
            current_fd = os.open(anchor, _dir_open_flags())
        except OSError as exc:
            raise ControlPlaneError(f"cannot open filesystem anchor for {label}: {exc}") from exc
        for part in absolute.parts[1:]:
            try:
                next_fd = os.open(part, _dir_open_flags(), dir_fd=current_fd)
            except OSError as exc:
                raise ControlPlaneError(
                    f"cannot open {label} directory component {part!r}: {exc}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        opened = os.fstat(current_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise ControlPlaneError(f"{label} must resolve to a directory")
        result = current_fd
        current_fd = -1
        return result
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _starting_root_fd(root: Path, root_fd: int | None, *, label: str) -> int:
    if root_fd is None:
        return _open_control_root(root, label=label)
    try:
        return os.dup(root_fd)
    except OSError as exc:
        raise ControlPlaneError(f"cannot duplicate anchored control root for {label}: {exc}") from exc


def _assert_control_root_identity(root: Path, root_fd: int) -> None:
    """Reject rename/replacement of the lexical control-root pathname mid-run."""
    current_fd = _open_control_root(root, label="control root")
    try:
        anchored = os.fstat(root_fd)
        current = os.fstat(current_fd)
        if (anchored.st_dev, anchored.st_ino) != (current.st_dev, current.st_ino):
            raise ControlPlaneError("control root changed during verification")
    finally:
        os.close(current_fd)


def _open_directory_beneath(
    root: Path,
    rel: str,
    *,
    label: str,
    root_fd: int | None = None,
) -> int:
    """Open a directory below ``root`` without following any path component."""
    if not _safe_relpath(rel):
        raise ControlPlaneError(f"{label}: unsafe relative path {rel!r}")
    current_fd = _starting_root_fd(root, root_fd, label=label)
    try:
        for part in PurePosixPath(rel).parts:
            try:
                next_fd = os.open(part, _dir_open_flags(), dir_fd=current_fd)
            except OSError as exc:
                raise ControlPlaneError(
                    f"cannot open {label} directory component {part!r}: {exc}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        opened = os.fstat(current_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise ControlPlaneError(f"{label} must resolve to a directory")
        result = current_fd
        current_fd = -1
        return result
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _directory_exists_beneath(
    root: Path,
    rel: str,
    *,
    label: str,
    root_fd: int | None = None,
) -> bool:
    try:
        fd = _open_directory_beneath(root, rel, label=label, root_fd=root_fd)
    except ControlPlaneError:
        return False
    os.close(fd)
    return True


def _read_regular_bytes_beneath(
    root: Path,
    rel: str,
    *,
    label: str,
    root_fd: int | None = None,
) -> bytes:
    """Single-open snapshot below root with no-follow traversal on every component."""
    if not _safe_relpath(rel):
        raise ControlPlaneError(f"{label}: unsafe relative path {rel!r}")
    parts = PurePosixPath(rel).parts
    if not parts:
        raise ControlPlaneError(f"{label}: empty relative path")
    current_fd = _starting_root_fd(root, root_fd, label=label)
    file_fd = -1
    try:
        for part in parts[:-1]:
            try:
                next_fd = os.open(part, _dir_open_flags(), dir_fd=current_fd)
            except OSError as exc:
                raise ControlPlaneError(
                    f"cannot open {label} directory component {part!r}: {exc}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        try:
            file_fd = os.open(parts[-1], _file_open_flags(), dir_fd=current_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ControlPlaneError(f"{label} must not be a symlink") from exc
            raise ControlPlaneError(f"cannot open {label}: {exc}") from exc
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ControlPlaneError(f"{label} must be a regular file")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = -1
            return stream.read()
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if current_fd >= 0:
            os.close(current_fd)


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    """Single-open snapshot with no-follow traversal across the absolute parent."""
    absolute = _lexical_absolute(path)
    parent_fd = _open_control_root(absolute.parent, label=f"{label} parent")
    file_fd = -1
    try:
        try:
            file_fd = os.open(absolute.name, _file_open_flags(), dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ControlPlaneError(f"{label} must not be a symlink") from exc
            raise ControlPlaneError(f"cannot open {label}: {exc}") from exc
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ControlPlaneError(f"{label} must be a regular file")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = -1
            return stream.read()
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(parent_fd)


def _strict_json_bytes(raw: bytes, *, name: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ControlPlaneError(f"{name} is not UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ControlPlaneError) as exc:
        raise ControlPlaneError(f"{name} invalid JSON: {exc}") from exc
    if type(value) is not dict:
        raise ControlPlaneError(f"{name} must contain one JSON object")
    return value


def strict_load(path: Path) -> dict[str, Any]:
    return _strict_json_bytes(
        _read_regular_bytes(path, label=path.name),
        name=path.name,
    )


def strict_load_beneath(
    root: Path,
    rel: str,
    *,
    root_fd: int | None = None,
) -> dict[str, Any]:
    name = PurePosixPath(rel).name
    return _strict_json_bytes(
        _read_regular_bytes_beneath(root, rel, label=name, root_fd=root_fd),
        name=name,
    )


def _symlink_prefix(root: Path, rel: str) -> str | None:
    cur = root
    for part in PurePosixPath(rel).parts:
        cur = cur / part
        if cur.is_symlink():
            try:
                return cur.relative_to(root).as_posix()
            except ValueError:
                return str(cur)
    return None


def _check_trust_path(
    root: Path,
    rel: Any,
    label: str,
    errors: list[str],
    *,
    require_file: bool = False,
) -> None:
    if not _safe_relpath(rel):
        errors.append(f"{label}: unsafe relative path {rel!r}")
        return
    assert isinstance(rel, str)
    symlink = _symlink_prefix(root, rel)
    if symlink is not None:
        errors.append(f"{label}: symlink ancestry is forbidden at {symlink!r}")
        return
    if require_file:
        target = root / PurePosixPath(rel)
        if not target.is_file():
            errors.append(f"{label}: declared file is missing at {rel!r}")


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _walk_identity_fields(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in {"input_identity", "output_identity"}:
                if not isinstance(child, str) or GIT_BLOB_ID.fullmatch(child) is None:
                    errors.append(
                        f"COMPOSITION identity {child_path}: expected git-blob:<40 lowercase hex>, got {child!r}"
                    )
            _walk_identity_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_identity_fields(child, f"{path}[{index}]", errors)


def _harden_composition(root: Path, composition: dict[str, Any], errors: list[str]) -> None:
    components = composition.get("components")
    if isinstance(components, list):
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                continue
            cid = component.get("id")
            label = cid if isinstance(cid, str) and cid else f"index:{index}"

            if "package" in component:
                _check_trust_path(root, component.get("package"), f"component {label} package", errors)
            entrypoints = component.get("entrypoints")
            if isinstance(entrypoints, list):
                for ep_index, entrypoint in enumerate(entrypoints):
                    _check_trust_path(
                        root,
                        entrypoint,
                        f"component {label} entrypoint[{ep_index}]",
                        errors,
                    )

            for field in DECLARED_PATH_FIELDS:
                if field in component:
                    _check_trust_path(
                        root,
                        component.get(field),
                        f"component {label} {field}",
                        errors,
                        require_file=True,
                    )

            for field in RELATION_FIELDS:
                values = component.get(field)
                if isinstance(values, list) and all(isinstance(v, str) for v in values):
                    for duplicate in _duplicate_values(values):
                        errors.append(
                            f"component {label} {field}: duplicate relation target {duplicate!r}"
                        )

    discovery = composition.get("discovery")
    if isinstance(discovery, dict):
        roots = discovery.get("roots")
        if isinstance(roots, list):
            for index, scan_root in enumerate(roots):
                _check_trust_path(root, scan_root, f"discovery roots[{index}]", errors)
        ignore = discovery.get("ignore")
        if isinstance(ignore, list):
            for index, item in enumerate(ignore):
                path = item.get("path") if isinstance(item, dict) else item
                if isinstance(path, str):
                    _check_trust_path(root, path, f"discovery ignore[{index}]", errors)

    _walk_identity_fields(composition, "", errors)


def _harden_integration(
    root: Path,
    integration: dict[str, Any],
    errors: list[str],
    *,
    root_fd: int | None = None,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    manifest_snapshots: dict[str, dict[str, Any]] = {}
    custody_directory_snapshots: set[str] = set()
    blocked = integration.get("custody_blocked")
    if not isinstance(blocked, list):
        return manifest_snapshots, custody_directory_snapshots
    for index, row in enumerate(blocked):
        if not isinstance(row, dict):
            continue
        lane = row.get("lane")
        label = lane if isinstance(lane, str) and lane else f"index:{index}"
        custody_path = row.get("custody_path")
        _check_trust_path(root, custody_path, f"custody {label}", errors)
        if _safe_relpath(custody_path):
            assert isinstance(custody_path, str)
            if _directory_exists_beneath(
                root,
                custody_path,
                label=f"custody {label}",
                root_fd=root_fd,
            ):
                custody_directory_snapshots.add(custody_path)
        if row.get("status") != "awaiting_raw_payload" or not _safe_relpath(custody_path):
            continue
        assert isinstance(custody_path, str)
        manifest_rel = (PurePosixPath(custody_path) / "MANIFEST.json").as_posix()
        _check_trust_path(root, manifest_rel, f"custody {label} manifest", errors, require_file=True)
        if any(item.startswith(f"custody {label} manifest:") for item in errors):
            continue
        try:
            manifest_snapshots[manifest_rel] = strict_load_beneath(
                root,
                manifest_rel,
                root_fd=root_fd,
            )
        except ControlPlaneError as exc:
            errors.append(f"custody {label} manifest: {exc}")
    return manifest_snapshots, custody_directory_snapshots


def _read_regular_utf8_beneath(
    root: Path,
    rel: str,
    *,
    root_fd: int,
) -> str:
    name = PurePosixPath(rel).name
    raw = _read_regular_bytes_beneath(
        root,
        rel,
        label=f"validator module {name}",
        root_fd=root_fd,
    )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ControlPlaneError(f"validator module {name} is not UTF-8: {exc}") from exc


def _load_module_snapshot(
    root: Path,
    rel: str,
    module_name: str,
    *,
    root_fd: int,
):
    source = _read_regular_utf8_beneath(root, rel, root_fd=root_fd)
    path = root / PurePosixPath(rel)
    try:
        code = compile(source, str(path), "exec")
    except (SyntaxError, ValueError) as exc:
        raise ControlPlaneError(f"cannot compile validator module {path.name}: {exc}") from exc
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = None
    exec(code, module.__dict__, module.__dict__)
    return module


def _dump_snapshot(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _populate_integration_snapshot(
    snapshot_root: Path,
    canonical: dict[str, Any],
    integration: dict[str, Any],
    manifest_snapshots: dict[str, dict[str, Any]],
    custody_directory_snapshots: set[str],
) -> None:
    _dump_snapshot(snapshot_root / "CANONICAL.json", canonical)
    _dump_snapshot(snapshot_root / "INTEGRATION.json", integration)

    blocked = integration.get("custody_blocked")
    if isinstance(blocked, list):
        for row in blocked:
            if not isinstance(row, dict):
                continue
            custody_path = row.get("custody_path")
            if not _safe_relpath(custody_path):
                continue
            assert isinstance(custody_path, str)
            if custody_path in custody_directory_snapshots:
                (snapshot_root / PurePosixPath(custody_path)).mkdir(parents=True, exist_ok=True)

    for manifest_rel, manifest in manifest_snapshots.items():
        _dump_snapshot(snapshot_root / PurePosixPath(manifest_rel), manifest)


def _delegate(
    root: Path,
    root_fd: int,
    canonical: dict[str, Any],
    integration: dict[str, Any],
    composition: dict[str, Any],
    composition_root: Path,
    manifest_snapshots: dict[str, dict[str, Any]],
    custody_directory_snapshots: set[str],
    errors: list[str],
) -> None:
    try:
        ledger = _load_module_snapshot(
            root,
            DELEGATE_FILES[0],
            "_titan_v4_integration_validator",
            root_fd=root_fd,
        )
        graph = _load_module_snapshot(
            root,
            DELEGATE_FILES[1],
            "_titan_v4_composition_validator",
            root_fd=root_fd,
        )
    except Exception as exc:
        errors.append(f"delegate load failure: {type(exc).__name__}: {exc}")
        return

    try:
        with tempfile.TemporaryDirectory(prefix="titan-v4-ledger-snapshot-") as td:
            snapshot_root = Path(td)
            _populate_integration_snapshot(
                snapshot_root,
                canonical,
                integration,
                manifest_snapshots,
                custody_directory_snapshots,
            )
            ledger_errors = ledger.validate(snapshot_root)
    except Exception as exc:
        errors.append(f"integration delegate failure: {type(exc).__name__}: {exc}")
    else:
        if not isinstance(ledger_errors, list):
            errors.append("integration delegate returned non-list errors")
        else:
            errors.extend(f"integration: {item}" for item in ledger_errors)

    try:
        graph_result = graph.validate_manifest(composition, composition_root)
    except Exception as exc:
        errors.append(f"composition delegate failure: {type(exc).__name__}: {exc}")
    else:
        if not isinstance(graph_result, dict) or not isinstance(graph_result.get("errors"), list):
            errors.append("composition delegate returned malformed result")
        else:
            for item in graph_result["errors"]:
                errors.append(
                    "composition: " + json.dumps(item, sort_keys=True, separators=(",", ":"))
                )


def validate_control_plane(root: Path, *, delegate: bool = True) -> dict[str, Any]:
    root = _lexical_absolute(root)
    errors: list[str] = []
    loaded: dict[str, dict[str, Any]] = {}
    root_fd = -1
    topology_tmp: tempfile.TemporaryDirectory[str] | None = None
    composition_root: Path | None = None

    try:
        try:
            root_fd = _open_control_root(root)
        except ControlPlaneError as exc:
            errors.append(str(exc))
            return {
                "ok": False,
                "delegate": delegate,
                "checked_files": list(EXPECTED_FILES),
                "errors": sorted(errors),
            }

        for name in EXPECTED_FILES:
            try:
                loaded[name] = strict_load_beneath(root, name, root_fd=root_fd)
            except ControlPlaneError as exc:
                errors.append(str(exc))

        canonical = loaded.get("CANONICAL.json")
        composition = loaded.get("COMPOSITION.json")
        integration = loaded.get("INTEGRATION.json")
        manifest_snapshots: dict[str, dict[str, Any]] = {}
        custody_directory_snapshots: set[str] = set()

        if composition is not None:
            try:
                topology_tmp = tempfile.TemporaryDirectory(prefix="titan-v4-composition-topology-")
                composition_root = Path(topology_tmp.name)
                _capture_topology_snapshot(root_fd, composition_root)
                _harden_composition(composition_root, composition, errors)
            except (ControlPlaneError, OSError) as exc:
                errors.append(f"composition topology: {exc}")
                if topology_tmp is not None:
                    topology_tmp.cleanup()
                topology_tmp = None
                composition_root = None

        if integration is not None:
            manifest_snapshots, custody_directory_snapshots = _harden_integration(
                root,
                integration,
                errors,
                root_fd=root_fd,
            )

        if (
            delegate
            and canonical is not None
            and composition is not None
            and composition_root is not None
            and integration is not None
            and not errors
        ):
            try:
                _assert_control_root_identity(root, root_fd)
            except ControlPlaneError as exc:
                errors.append(str(exc))
            if not errors:
                _delegate(
                    root,
                    root_fd,
                    canonical,
                    integration,
                    composition,
                    composition_root,
                    manifest_snapshots,
                    custody_directory_snapshots,
                    errors,
                )
                try:
                    _assert_control_root_identity(root, root_fd)
                except ControlPlaneError as exc:
                    errors.append(str(exc))
    finally:
        if topology_tmp is not None:
            topology_tmp.cleanup()
        if root_fd >= 0:
            os.close(root_fd)

    errors = sorted(errors)
    return {
        "ok": not errors,
        "delegate": delegate,
        "checked_files": list(EXPECTED_FILES),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-delegate", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    result = validate_control_plane(Path(args.root), delegate=not args.no_delegate)
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("TITAN V4 control plane OK" if result["ok"] else "TITAN V4 control plane INVALID")
        for error in result["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
