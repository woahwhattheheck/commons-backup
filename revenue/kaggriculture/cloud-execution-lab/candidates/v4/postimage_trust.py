"""Trust boundary for the sole TITAN V4 graph -> postimage executor.

This module is deliberately policy-free.  It authenticates the control files
and source paths that the existing ``build_composed_postimage.py`` consumes,
then lets that runner keep all composition/materialization semantics.

The pins below bind one reviewed runner generation.  Any intentional change to
COMPOSITION.json, check_composition_graph.py, or build_composed_postimage.py
must explicitly rebind these constants before the trusted front-end can run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MANIFEST_NAME = "COMPOSITION.json"
CHECKER_NAME = "check_composition_graph.py"
RUNNER_NAME = "build_composed_postimage.py"

PINNED_CONTROL_BLOBS: dict[str, str] = {
    MANIFEST_NAME: "e44cade4d3b05a2c06e4aa73481b65f5d6b8ff89",
    CHECKER_NAME: "97a5ff513ecf44a064fd284b2cee5b8c299cd81d",
    RUNNER_NAME: "41b467d665f6e1497bc6de697a06712f404fbcfd",
}


class TrustError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TrustError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> Any:
    raise TrustError(f"non-finite JSON constant: {token}")


def strict_load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TrustError(f"cannot read {path.name}: {exc}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrustError(f"{path.name} is not UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise TrustError(f"invalid JSON {path.name}: {exc}") from exc
    if type(value) is not dict:
        raise TrustError(f"{path.name}: top-level object required")
    return value, data


def _safe_rel(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise TrustError(f"unsafe relative path: {value!r}")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise TrustError(f"unsafe relative path: {value!r}")
    return rel


def symlink_prefix(root: Path, rel: str) -> str | None:
    rel_path = _safe_rel(rel)
    cur = root
    for part in rel_path.parts:
        cur = cur / part
        if cur.is_symlink():
            try:
                return cur.relative_to(root).as_posix()
            except ValueError:
                return str(cur)
    return None


def checked_under(
    root: Path,
    rel: str,
    *,
    expected_blob: str | None = None,
    must_exist: bool = True,
) -> Path:
    root = root.resolve(strict=True)
    rel_path = _safe_rel(rel)
    link = symlink_prefix(root, rel)
    if link is not None:
        raise TrustError(f"symlink ancestry is forbidden at {link!r}")
    target = root.joinpath(*rel_path.parts)
    try:
        resolved = target.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
        raise TrustError(f"path escapes/missing: {rel}") from exc
    if must_exist and not resolved.is_file():
        raise TrustError(f"regular file required: {rel}")
    if expected_blob is not None:
        if len(expected_blob) != 40 or any(c not in "0123456789abcdef" for c in expected_blob):
            raise TrustError(f"invalid expected Git blob for {rel}")
        actual = git_blob(resolved.read_bytes())
        if actual != expected_blob:
            raise TrustError(f"source drift for {rel}: expected {expected_blob}, got {actual}")
    return resolved


def _canonical_manifest_path(workspace: Path, supplied: Path | None) -> Path:
    canonical = checked_under(workspace, MANIFEST_NAME)
    if supplied is None:
        return canonical
    try:
        supplied_resolved = supplied.resolve(strict=True)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise TrustError("manifest path is missing/invalid") from exc
    if supplied_resolved != canonical:
        raise TrustError(
            f"alternate manifest refused; only {MANIFEST_NAME} in the canonical workspace is authorized"
        )
    return canonical


def verify_control_sources(
    workspace: Path,
    *,
    manifest_path: Path | None = None,
    pins: Mapping[str, str] = PINNED_CONTROL_BLOBS,
) -> tuple[dict[str, Any], bytes, dict[str, Path]]:
    workspace = workspace.resolve(strict=True)
    required = (MANIFEST_NAME, CHECKER_NAME, RUNNER_NAME)
    missing = [name for name in required if name not in pins]
    if missing:
        raise TrustError("missing control pin(s): " + ", ".join(missing))

    canonical_manifest = _canonical_manifest_path(workspace, manifest_path)
    paths = {
        MANIFEST_NAME: canonical_manifest,
        CHECKER_NAME: checked_under(workspace, CHECKER_NAME, expected_blob=pins[CHECKER_NAME]),
        RUNNER_NAME: checked_under(workspace, RUNNER_NAME, expected_blob=pins[RUNNER_NAME]),
    }
    manifest, manifest_bytes = strict_load_json(canonical_manifest)
    actual_manifest = git_blob(manifest_bytes)
    expected_manifest = pins[MANIFEST_NAME]
    if actual_manifest != expected_manifest:
        raise TrustError(
            f"source drift for {MANIFEST_NAME}: expected {expected_manifest}, got {actual_manifest}"
        )
    return manifest, manifest_bytes, paths


def repo_root(workspace: Path, manifest: Mapping[str, Any]) -> Path:
    raw = manifest.get("canonical_root")
    rel = _safe_rel(raw)
    workspace = workspace.resolve(strict=True)
    root = workspace
    for _ in rel.parts:
        root = root.parent
    try:
        expected = checked_under(root, rel.as_posix())
    except TrustError as exc:
        # canonical_root is a directory, while checked_under normally requires a file.
        target = root.joinpath(*rel.parts)
        link = symlink_prefix(root, rel.as_posix())
        if link is not None:
            raise TrustError(f"canonical_root uses symlink ancestry at {link!r}") from exc
        try:
            expected = target.resolve(strict=True)
            expected.relative_to(root.resolve(strict=True))
        except (FileNotFoundError, RuntimeError, OSError, ValueError) as inner:
            raise TrustError("canonical_root escapes/missing") from inner
    if expected.resolve(strict=True) != workspace:
        raise TrustError("workspace does not match manifest canonical_root")
    return root.resolve(strict=True)


def verify_adapter_paths(
    workspace: Path,
    manifest: Mapping[str, Any],
    adapters: Mapping[str, Mapping[str, Any]],
) -> None:
    workspace = workspace.resolve(strict=True)
    repo = repo_root(workspace, manifest)
    for cid, spec in adapters.items():
        entrypoints = spec.get("entrypoints", {})
        if not isinstance(entrypoints, Mapping):
            raise TrustError(f"malformed adapter entrypoints: {cid}")
        for rel, expected_blob in entrypoints.items():
            checked_under(workspace, str(rel), expected_blob=str(expected_blob))

        sources = spec.get("sources", {})
        if not isinstance(sources, Mapping):
            raise TrustError(f"malformed adapter support sources: {cid}")
        for key, expected_blob in sources.items():
            if not isinstance(key, str) or ":" not in key:
                raise TrustError(f"malformed support source key: {key!r}")
            scope, rel = key.split(":", 1)
            if scope == "workspace":
                base = workspace
            elif scope == "repo":
                base = repo
            else:
                raise TrustError(f"unknown support source scope: {scope}")
            checked_under(base, rel, expected_blob=str(expected_blob))

        outputs = spec.get("support_outputs", [])
        if not isinstance(outputs, list):
            raise TrustError(f"malformed support output registry: {cid}")
        for rel in outputs:
            _safe_rel(rel)
