#!/usr/bin/env python3
"""Authenticated front-end for the sole TITAN V4 graph postimage runner.

This is not a second assembler. It verifies the exact canonical manifest,
checker, existing runner generation, and every runner adapter/support source,
then executes immutable authenticated byte snapshots through the existing
``build_composed_postimage.py`` semantics. There is no alternate-manifest
option and no post-verification source reopen for executable/control receipt
bytes.
"""
from __future__ import annotations

import argparse
import copy
import json
import types
from pathlib import Path
from typing import Any

import postimage_trust as trust


class _SnapshotReadPath:
    """Path proxy whose byte reads are pinned to one authenticated snapshot."""

    __slots__ = ("_path", "_data")

    def __init__(self, path: Path, data: bytes):
        self._path = Path(path)
        self._data = bytes(data)

    def read_bytes(self) -> bytes:
        return self._data

    def __fspath__(self) -> str:
        return str(self._path)

    def __str__(self) -> str:
        return str(self._path)

    def __getattr__(self, name: str):
        return getattr(self._path, name)


def _module_from_bytes(
    data: bytes,
    path: Path,
    name: str,
    *,
    error_type: type[Exception],
    error_message: str,
):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except Exception as exc:
        raise error_type(error_message) from exc
    return module


def _capture_expected(path: Path, expected_blob: str, label: str) -> bytes:
    data = path.read_bytes()
    actual = trust.git_blob(data)
    if actual != expected_blob:
        raise trust.TrustError(
            f"source drift while snapshotting {label}: expected {expected_blob}, got {actual}"
        )
    return data


def _load_runner(path: Path):
    expected = trust.PINNED_CONTROL_BLOBS[trust.RUNNER_NAME]
    data = _capture_expected(path, expected, trust.RUNNER_NAME)
    return _module_from_bytes(
        data,
        path,
        "_titan_v4_pinned_postimage_runner",
        error_type=trust.TrustError,
        error_message="cannot load authenticated graph postimage runner",
    )


def _snapshot_adapter_inputs(
    workspace: Path,
    manifest: dict[str, Any],
    adapters: dict[str, dict[str, Any]],
) -> tuple[dict[tuple[str, str], bytes], dict[tuple[str, str], bytes]]:
    """Capture every executable/support source only after exact path+blob checks."""
    trust.verify_adapter_paths(workspace, manifest, adapters)
    entrypoints: dict[tuple[str, str], bytes] = {}
    sources: dict[tuple[str, str], bytes] = {}
    repo: Path | None = None

    for cid, spec in adapters.items():
        raw_entrypoints = spec.get("entrypoints", {})
        if not isinstance(raw_entrypoints, dict):
            raise trust.TrustError(f"malformed adapter entrypoints: {cid}")
        for rel, expected_blob in raw_entrypoints.items():
            rel_s = str(rel)
            expected_s = str(expected_blob)
            path = trust.checked_under(
                workspace,
                rel_s,
                expected_blob=expected_s,
            )
            entrypoints[(rel_s, expected_s)] = _capture_expected(
                path,
                expected_s,
                f"{cid}:{rel_s}",
            )

        raw_sources = spec.get("sources", {})
        if not isinstance(raw_sources, dict):
            raise trust.TrustError(f"malformed adapter support sources: {cid}")
        for key, expected_blob in raw_sources.items():
            if not isinstance(key, str) or ":" not in key:
                raise trust.TrustError(f"malformed support source key: {key!r}")
            scope, rel = key.split(":", 1)
            if scope == "workspace":
                base = workspace
            elif scope == "repo":
                if repo is None:
                    repo = trust.repo_root(workspace, manifest)
                base = repo
            else:
                raise trust.TrustError(f"unknown support source scope: {scope}")
            expected_s = str(expected_blob)
            path = trust.checked_under(base, rel, expected_blob=expected_s)
            sources[(key, expected_s)] = _capture_expected(
                path,
                expected_s,
                f"{cid}:{key}",
            )
    return entrypoints, sources


def _bind_snapshot_loaders(
    runner: Any,
    *,
    workspace: Path,
    canonical_manifest: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    checker_bytes: bytes,
    entrypoint_bytes: dict[tuple[str, str], bytes],
    support_source_bytes: dict[tuple[str, str], bytes],
) -> None:
    """Make the pinned runner consume captured bytes instead of reopening sources."""
    error_type = runner.MaterializationError
    original_under = getattr(runner, "_under", None)
    if not callable(original_under):
        raise trust.TrustError("authenticated graph postimage runner missing _under()")
    workspace = workspace.resolve(strict=True)
    canonical_manifest = canonical_manifest.resolve(strict=True)
    frozen_manifest = copy.deepcopy(manifest)
    frozen_manifest_bytes = bytes(manifest_bytes)
    frozen_checker_bytes = bytes(checker_bytes)
    frozen_entrypoints = {key: bytes(value) for key, value in entrypoint_bytes.items()}
    frozen_sources = {key: bytes(value) for key, value in support_source_bytes.items()}

    def snapshot_load_json(path: Path):
        if Path(path) != canonical_manifest:
            raise error_type("authenticated manifest snapshot only authorizes canonical COMPOSITION.json")
        return copy.deepcopy(frozen_manifest), frozen_manifest_bytes

    def snapshot_load_checker(requested_workspace: Path):
        if Path(requested_workspace).resolve(strict=True) != workspace:
            raise error_type("checker requested for non-canonical workspace")
        module = _module_from_bytes(
            frozen_checker_bytes,
            workspace / trust.CHECKER_NAME,
            "_titan_v4_snapshot_checker",
            error_type=error_type,
            error_message="cannot load authenticated composition checker snapshot",
        )
        validate = getattr(module, "validate_manifest", None)
        if not callable(validate):
            raise error_type("composition checker missing validate_manifest()")
        return module

    def snapshot_under(root: Path, rel: str, *, must_exist: bool = True):
        path = original_under(root, rel, must_exist=must_exist)
        try:
            canonical_root = Path(root).resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise error_type("cannot resolve authenticated path root") from exc
        if canonical_root == workspace and rel == trust.CHECKER_NAME and must_exist:
            return _SnapshotReadPath(Path(path), frozen_checker_bytes)
        return path

    def snapshot_load_module(path: Path, expected_blob: str, label: str):
        try:
            rel = Path(path).relative_to(workspace).as_posix()
        except ValueError as exc:
            raise error_type("adapter path is outside authenticated workspace") from exc
        data = frozen_entrypoints.get((rel, expected_blob))
        if data is None:
            raise error_type("adapter was not captured in authenticated snapshot: " + rel)
        if trust.git_blob(data) != expected_blob:
            raise error_type("authenticated adapter snapshot identity mismatch: " + rel)
        return _module_from_bytes(
            data,
            Path(path),
            "_titan_v4_snapshot_adapter_" + expected_blob[:16],
            error_type=error_type,
            error_message="cannot load authenticated adapter snapshot: " + label,
        )

    def snapshot_load_support_source(
        requested_workspace: Path,
        _repo_root: Path,
        key: str,
        expected_blob: str,
    ) -> bytes:
        if Path(requested_workspace).resolve(strict=True) != workspace:
            raise error_type("support source requested for non-canonical workspace")
        data = frozen_sources.get((key, expected_blob))
        if data is None:
            raise error_type("support source was not captured in authenticated snapshot: " + key)
        if trust.git_blob(data) != expected_blob:
            raise error_type("authenticated support snapshot identity mismatch: " + key)
        return data

    runner.load_json = snapshot_load_json
    runner._load_checker = snapshot_load_checker
    runner._under = snapshot_under
    runner._load_module = snapshot_load_module
    runner._load_support_source = snapshot_load_support_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).parent)
    parser.add_argument("--check", action="store_true", help="validate canonical graph + pinned adapters only")
    parser.add_argument("--package", type=Path, help="authenticated extracted native package")
    parser.add_argument("--output", type=Path, help="new disposable composed output directory")
    args = parser.parse_args()

    try:
        workspace = args.workspace.resolve(strict=True)
        manifest, manifest_bytes, paths = trust.verify_control_sources(workspace)
        checker_bytes = _capture_expected(
            paths[trust.CHECKER_NAME],
            trust.PINNED_CONTROL_BLOBS[trust.CHECKER_NAME],
            trust.CHECKER_NAME,
        )
        runner = _load_runner(paths[trust.RUNNER_NAME])
        adapters = getattr(runner, "ADAPTERS", None)
        if not isinstance(adapters, dict):
            raise trust.TrustError("authenticated runner exposes malformed ADAPTERS")
        entrypoint_bytes, support_source_bytes = _snapshot_adapter_inputs(
            workspace,
            manifest,
            adapters,
        )
        canonical_manifest = paths[trust.MANIFEST_NAME]
        _bind_snapshot_loaders(
            runner,
            workspace=workspace,
            canonical_manifest=canonical_manifest,
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            checker_bytes=checker_bytes,
            entrypoint_bytes=entrypoint_bytes,
            support_source_bytes=support_source_bytes,
        )

        if args.check:
            if args.package is not None or args.output is not None:
                raise trust.TrustError("--check cannot be combined with --package/--output")
            result = runner.check_only(
                workspace,
                manifest_path=canonical_manifest,
                adapters=adapters,
            )
        else:
            if args.package is None or args.output is None:
                raise trust.TrustError("--package and --output are required unless --check is used")
            result = runner.materialize(
                workspace,
                args.package,
                args.output,
                manifest_path=canonical_manifest,
                adapters=adapters,
            )
    except (trust.TrustError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
