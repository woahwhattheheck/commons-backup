"""Shared primitives for the TITAN dynamic import provenance gate."""
from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

SCHEMA = "titan.import-provenance-custody.v1"
ENTRY_MODULE_PREFIX = "_titan_custody_entry_"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
MODULE_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
SPECIAL_ORIGINS = {"built-in", "frozen", "namespace"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def normalize_relative(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ValueError(f"invalid relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative path: {raw!r}")
    return path.as_posix()


def load_manifest(path: Path) -> tuple[dict[str, str], str, str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if isinstance(value, Mapping) and isinstance(value.get("files"), Mapping):
        value = value["files"]
    if not isinstance(value, Mapping):
        raise ValueError("manifest must map relative paths to SHA-256")
    manifest: dict[str, str] = {}
    for raw_path, raw_hash in value.items():
        rel = normalize_relative(str(raw_path))
        digest = str(raw_hash).lower()
        if not HASH_RE.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 for {rel!r}")
        if rel in manifest:
            raise ValueError(f"duplicate manifest path: {rel}")
        manifest[rel] = digest
    manifest = dict(sorted(manifest.items()))
    return manifest, sha256_bytes(raw), sha256_bytes(canonical_bytes(manifest))


def local_top_levels(manifest: Mapping[str, str]) -> list[str]:
    names: set[str] = set()
    for rel in manifest:
        path = PurePosixPath(rel)
        if path.suffix != ".py":
            continue
        if len(path.parts) == 1:
            if path.stem != "__init__":
                names.add(path.stem)
        else:
            names.add(path.parts[0])
    return sorted(names)


def under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def lexical_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.abspath(path))


def display_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if under(path, root) else f"OUTSIDE_ROOT/{path.name}"


def origin_record(raw: str | None, root: Path) -> dict[str, Any]:
    if not raw or raw in SPECIAL_ORIGINS:
        return {"kind": "special", "value": raw}
    lexical = lexical_path(raw)
    resolved = lexical.resolve(strict=False)
    return {
        "kind": "filesystem",
        "lexical_path": display_path(lexical, root),
        "resolved_path": display_path(resolved, root),
        "lexical_inside_root": under(lexical, root),
        "resolved_inside_root": under(resolved, root),
    }


def symlink_components(path: Path, root: Path) -> list[str]:
    if not under(path, root):
        return []
    cursor = root
    links: list[str] = []
    for part in path.relative_to(root).parts:
        cursor /= part
        try:
            if cursor.is_symlink():
                links.append(cursor.relative_to(root).as_posix())
        except OSError:
            pass
    return links


def dedupe_violations(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique = {canonical_bytes(dict(item)): dict(item) for item in items}
    return sorted(
        unique.values(),
        key=lambda item: (
            str(item.get("code", "")),
            str(item.get("module", "")),
            str(item.get("path", "")),
            str(item.get("detail", "")),
        ),
    )


def audit_manifest_tree(root: Path, manifest: Mapping[str, str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for rel, expected in manifest.items():
        lexical = lexical_path(root / PurePosixPath(rel))
        resolved = lexical.resolve(strict=False)
        links = symlink_components(lexical, root)
        if links:
            violations.append({"code": "MANIFEST_SYMLINK", "path": rel, "detail": ",".join(links)})
        if not under(lexical, root) or not under(resolved, root):
            violations.append({"code": "MANIFEST_PATH_ESCAPE", "path": rel})
            continue
        if not lexical.is_file():
            violations.append({"code": "MANIFEST_FILE_MISSING", "path": rel})
            continue
        observed = sha256_file(lexical)
        if observed != expected:
            violations.append(
                {
                    "code": "MANIFEST_HASH_MISMATCH",
                    "path": rel,
                    "expected_sha256": expected,
                    "observed_sha256": observed,
                }
            )
    return violations


def loader_name(module: Any) -> str | None:
    spec = getattr(module, "__spec__", None)
    loader = getattr(spec, "loader", None) if spec is not None else None
    loader = loader or getattr(module, "__loader__", None)
    if loader is None:
        return None
    cls = type(loader)
    return f"{cls.__module__}.{cls.__qualname__}"


def audit_module(
    name: str,
    module: Any,
    root: Path,
    manifest: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    spec = getattr(module, "__spec__", None)
    file_raw = getattr(module, "__file__", None)
    spec_raw = getattr(spec, "origin", None) if spec is not None else None
    effective_raw = file_raw or spec_raw
    record: dict[str, Any] = {
        "name": name,
        "loader": loader_name(module),
        "file": origin_record(str(file_raw) if file_raw is not None else None, root),
        "spec_origin": origin_record(str(spec_raw) if spec_raw is not None else None, root),
        "manifest_path": None,
        "expected_sha256": None,
        "observed_sha256": None,
    }
    if not effective_raw or effective_raw in SPECIAL_ORIGINS:
        violations.append({"code": "MODULE_WITHOUT_SOURCE", "module": name, "detail": repr(effective_raw)})
        return record, violations

    lexical = lexical_path(str(effective_raw))
    resolved = lexical.resolve(strict=False)
    inside = under(lexical, root)
    if not inside:
        violations.append({"code": "MODULE_OUTSIDE_ROOT", "module": name, "path": display_path(lexical, root)})
    elif not under(resolved, root):
        violations.append({"code": "MODULE_PATH_ESCAPE", "module": name, "path": display_path(lexical, root)})

    links = symlink_components(lexical, root)
    if links:
        violations.append(
            {"code": "SYMLINKED_MODULE", "module": name, "path": links[0], "detail": ",".join(links)}
        )

    if lexical.is_file():
        record["observed_sha256"] = sha256_file(lexical)
    if inside:
        rel = lexical.relative_to(root).as_posix()
        record["manifest_path"] = rel
        record["expected_sha256"] = manifest.get(rel)
        if rel not in manifest:
            violations.append({"code": "UNMANIFESTED_MODULE", "module": name, "path": rel})
        elif record["observed_sha256"] != manifest[rel]:
            violations.append(
                {
                    "code": "MODULE_HASH_MISMATCH",
                    "module": name,
                    "path": rel,
                    "expected_sha256": manifest[rel],
                    "observed_sha256": record["observed_sha256"],
                }
            )

    source_loader = isinstance(
        getattr(spec, "loader", None), importlib.machinery.SourceFileLoader
    ) if spec is not None else False
    if not source_loader:
        violations.append({"code": "NON_SOURCE_LOADER", "module": name, "detail": record["loader"]})
    if lexical.suffix != ".py":
        violations.append({"code": "NON_SOURCE_MODULE_SUFFIX", "module": name, "path": display_path(lexical, root)})

    if file_raw and spec_raw and file_raw not in SPECIAL_ORIGINS and spec_raw not in SPECIAL_ORIGINS:
        if Path(str(file_raw)).resolve(strict=False) != Path(str(spec_raw)).resolve(strict=False):
            violations.append({"code": "MODULE_FILE_SPEC_DISAGREE", "module": name})
    return record, violations
