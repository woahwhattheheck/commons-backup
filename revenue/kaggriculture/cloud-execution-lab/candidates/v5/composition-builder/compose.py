#!/usr/bin/env python3
"""Build deterministic Titan V5 A/B/AB archives from exact component postimages.

The builder deliberately has no policy semantics. A component is a set of exact
source postimages plus the configuration values required to make those bytes live.
It fails closed on stale hashes, archive/source path escape, incompatible overlays,
conflicting config requirements, and component/baseline preimage drift.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any

SCHEMA = "titan-v5-composition-v2"
CONFIG_MEMBER = "TITAN-CONFIG.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESERVED_VARIANT_NAMES = frozenset({"control"})


class CompositionError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CompositionError(f"{label} must be 64 lowercase hex characters")
    return value


def _safe_rel(value: str, *, label: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise CompositionError(f"unsafe {label}: {value!r}")
    return str(path)


def _read_archive_bytes(data: bytes) -> tuple[list[tarfile.TarInfo], dict[str, bytes]]:
    infos: list[tarfile.TarInfo] = []
    payloads: dict[str, bytes] = {}
    seen: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for raw in archive.getmembers():
            info = copy.copy(raw)
            name = _safe_rel(info.name, label="archive member")
            info.name = name
            if name in seen:
                raise CompositionError(f"duplicate archive member: {name}")
            seen.add(name)
            if info.isfile():
                handle = archive.extractfile(raw)
                if handle is None:
                    raise CompositionError(f"cannot read archive member: {name}")
                payloads[name] = handle.read()
            else:
                payloads[name] = b""
            infos.append(info)
    return infos, payloads


def _write_archive(path: Path, infos: list[tarfile.TarInfo], payloads: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for original in infos:
                    info = copy.copy(original)
                    data = payloads[info.name]
                    if info.isfile():
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                    else:
                        archive.addfile(info)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CompositionError(f"cannot read manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise CompositionError(f"manifest schema must be {SCHEMA!r}")
    baseline = manifest.get("baseline")
    components = manifest.get("components")
    if not isinstance(baseline, dict):
        raise CompositionError("manifest baseline must be an object")
    if not isinstance(components, dict) or len(components) != 2:
        raise CompositionError("manifest must contain exactly two components")
    return manifest


def _load_components(manifest: dict[str, Any], source_root: Path) -> dict[str, dict[str, Any]]:
    try:
        resolved_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise CompositionError(f"cannot resolve source root: {exc}") from exc
    if not resolved_root.is_dir():
        raise CompositionError("source root must resolve to a directory")

    result: dict[str, dict[str, Any]] = {}
    for name, raw in manifest["components"].items():
        if (
            not isinstance(name, str)
            or _COMPONENT_RE.fullmatch(name) is None
            or name in _RESERVED_VARIANT_NAMES
        ):
            raise CompositionError(f"invalid component name: {name!r}")
        if not isinstance(raw, dict):
            raise CompositionError(f"component {name} must be an object")
        files = raw.get("files", [])
        config = raw.get("config", {})
        if not isinstance(files, list) or not files:
            raise CompositionError(f"component {name} needs at least one exact file postimage")
        if not isinstance(config, dict):
            raise CompositionError(f"component {name} config must be an object")
        loaded_files: list[dict[str, Any]] = []
        for entry in files:
            if not isinstance(entry, dict):
                raise CompositionError(f"component {name} file entry must be an object")
            archive_path = _safe_rel(str(entry.get("archive_path", "")), label="archive_path")
            source_path = _safe_rel(str(entry.get("source_path", "")), label="source_path")
            expected = _sha256_text(
                entry.get("sha256"),
                label=f"component {name} file {archive_path} sha256",
            )
            preimage = _sha256_text(
                entry.get("preimage_sha256"),
                label=f"component {name} file {archive_path} preimage_sha256",
            )
            lexical_source = resolved_root.joinpath(*PurePosixPath(source_path).parts)
            try:
                source = lexical_source.resolve(strict=True)
            except OSError as exc:
                raise CompositionError(f"component {name} cannot resolve {source_path}: {exc}") from exc
            try:
                source.relative_to(resolved_root)
            except ValueError as exc:
                raise CompositionError(
                    f"component {name} source escapes source root: {source_path}"
                ) from exc
            if not source.is_file():
                raise CompositionError(f"component {name} source is not a file: {source_path}")
            try:
                data = source.read_bytes()
            except OSError as exc:
                raise CompositionError(f"component {name} cannot read {source_path}: {exc}") from exc
            actual = sha256_bytes(data)
            if actual != expected:
                raise CompositionError(
                    f"component {name} stale source {source_path}: expected {expected}, got {actual}"
                )
            loaded_files.append(
                {
                    "archive_path": archive_path,
                    "source_path": source_path,
                    "preimage_sha256": preimage,
                    "sha256": actual,
                    "data": data,
                }
            )
        result[name] = {"files": loaded_files, "config": config}
    return result


def _validate_preimages(
    base_payloads: dict[str, bytes],
    regular_members: set[str],
    components: dict[str, dict[str, Any]],
) -> None:
    """Authenticate component compatibility with the exact baseline before output."""
    seen: dict[str, tuple[str, str]] = {}
    for name in sorted(components):
        for entry in components[name]["files"]:
            target = entry["archive_path"]
            if target not in base_payloads:
                raise CompositionError(f"component {name} targets absent archive member: {target}")
            if target not in regular_members:
                raise CompositionError(f"component {name} targets non-regular archive member: {target}")
            expected = entry["preimage_sha256"]
            prior = seen.get(target)
            if prior is not None and prior[1] != expected:
                raise CompositionError(
                    f"components {prior[0]} and {name} disagree on baseline preimage for {target}: "
                    f"{prior[1]} != {expected}"
                )
            seen[target] = (name, expected)
            actual = sha256_bytes(base_payloads[target])
            if actual != expected:
                raise CompositionError(
                    f"component {name} baseline preimage mismatch for {target}: "
                    f"expected {expected}, got {actual}"
                )


def _apply_variant(
    base_payloads: dict[str, bytes],
    components: dict[str, dict[str, Any]],
    names: tuple[str, ...],
) -> tuple[dict[str, bytes], list[str], dict[str, Any]]:
    payloads = dict(base_payloads)
    changed: set[str] = set()
    owners: dict[str, tuple[str, str]] = {}
    requested_config: dict[str, Any] = {}

    for name in names:
        component = components[name]
        for entry in component["files"]:
            target = entry["archive_path"]
            if target not in base_payloads:
                raise CompositionError(f"component {name} targets absent archive member: {target}")
            prior = owners.get(target)
            identity = entry["sha256"]
            if prior is not None and prior[1] != identity:
                raise CompositionError(
                    f"components {prior[0]} and {name} conflict on {target}: {prior[1]} != {identity}"
                )
            owners[target] = (name, identity)
            payloads[target] = entry["data"]
            if payloads[target] != base_payloads[target]:
                changed.add(target)

        for key, value in component["config"].items():
            if key in requested_config and requested_config[key] != value:
                raise CompositionError(
                    f"components conflict on config {key!r}: {requested_config[key]!r} != {value!r}"
                )
            requested_config[key] = value

    if requested_config:
        if CONFIG_MEMBER not in base_payloads:
            raise CompositionError(f"archive is missing {CONFIG_MEMBER}")
        try:
            config = json.loads(payloads[CONFIG_MEMBER])
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompositionError(f"invalid {CONFIG_MEMBER}: {exc}") from exc
        if not isinstance(config, dict):
            raise CompositionError(f"{CONFIG_MEMBER} must contain a JSON object")
        for key, value in requested_config.items():
            if key not in config:
                raise CompositionError(f"component requires unknown config key: {key!r}")
            config[key] = value
        rendered = (json.dumps(config, indent=2, sort_keys=False) + "\n").encode()
        payloads[CONFIG_MEMBER] = rendered
        if rendered != base_payloads[CONFIG_MEMBER]:
            changed.add(CONFIG_MEMBER)

    return payloads, sorted(changed), requested_config


def build(*, baseline: Path, source_root: Path, manifest_path: Path, output: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    expected_sha = _sha256_text(manifest["baseline"].get("sha256"), label="baseline.sha256")
    try:
        baseline_bytes = baseline.read_bytes()
    except OSError as exc:
        raise CompositionError(f"cannot read baseline archive: {exc}") from exc
    actual_sha = sha256_bytes(baseline_bytes)
    if actual_sha != expected_sha:
        raise CompositionError(f"baseline SHA256 mismatch: expected {expected_sha}, got {actual_sha}")

    infos, base_payloads = _read_archive_bytes(baseline_bytes)
    expected_members = manifest["baseline"].get("member_count")
    if expected_members is not None and len(infos) != expected_members:
        raise CompositionError(
            f"baseline member count mismatch: expected {expected_members}, got {len(infos)}"
        )
    components = _load_components(manifest, source_root)
    regular_members = {info.name for info in infos if info.isfile()}
    _validate_preimages(base_payloads, regular_members, components)
    names = tuple(sorted(components))
    variants: list[tuple[str, tuple[str, ...]]] = [
        ("control", ()),
        (names[0], (names[0],)),
        (names[1], (names[1],)),
        (f"{names[0]}+{names[1]}", names),
    ]

    # Preflight every variant before creating output. Source/preimage drift,
    # overlay conflicts, and malformed config requirements therefore cannot
    # leave a partial A/B/AB evidence directory behind.
    prepared: list[tuple[str, tuple[str, ...], dict[str, bytes], list[str], dict[str, Any]]] = []
    for label, enabled in variants:
        if not enabled:
            payloads = base_payloads
            changed: list[str] = []
            requested_config: dict[str, Any] = {}
        else:
            payloads, changed, requested_config = _apply_variant(base_payloads, components, enabled)
        prepared.append((label, enabled, payloads, changed, requested_config))

    output.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "baseline": {"sha256": actual_sha, "member_count": len(infos)},
        "components": {},
        "variants": {},
    }
    for name in names:
        receipt["components"][name] = {
            "files": [
                {
                    k: entry[k]
                    for k in ("archive_path", "source_path", "preimage_sha256", "sha256")
                }
                for entry in components[name]["files"]
            ],
            "config": components[name]["config"],
        }

    for label, enabled, payloads, changed, requested_config in prepared:
        filename = label.replace("+", "-plus-") + ".tar.gz"
        target = output / filename
        _write_archive(target, infos, payloads)
        receipt["variants"][label] = {
            "archive": filename,
            "sha256": sha256_file(target),
            "components": list(enabled),
            "changed_members": changed,
            "config": requested_config,
        }

    receipt_path = output / "COMPOSITION.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build(
            baseline=args.baseline,
            source_root=args.source_root,
            manifest_path=args.manifest,
            output=args.output,
        )
    except CompositionError as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
