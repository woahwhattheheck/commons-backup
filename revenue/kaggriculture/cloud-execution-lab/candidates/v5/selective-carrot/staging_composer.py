#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose approved TITAN V5 component replacements onto exact production-v3.

This is staging infrastructure, not a policy selector. Each component must bind
exact replacement preimages/postimages or authenticated additions. The composer
applies components in explicit order and emits one deterministic candidate
archive plus one receipt. It never decides whether a component is economically
qualified.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import Any

from publication_custody import publish_exclusive

BASELINE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
COMPONENT_SCHEMA = "titan-v5-staging-component/v1"
RECEIPT_SCHEMA = "titan-v5-single-staging-composer/v1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPONENT_REQUIRED_KEYS = {
    "schema", "component_id", "baseline_archive_sha256", "depends_on",
    "conflicts_with", "overlap_after", "replacements", "kaggle_submission_hold",
}
_COMPONENT_OPTIONAL_KEYS = {"additions"}
_REPLACEMENT_KEYS = {"source", "preimage_sha256", "postimage_sha256"}
_ADDITION_KEYS = {"source", "postimage_sha256"}


class ComposerError(ValueError):
    pass


def _os_path(path: Path) -> str:
    """Return an OS path that preserves Windows paths beyond MAX_PATH."""
    raw = os.path.abspath(os.fspath(path))
    if os.name != "nt" or raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_regular(path: Path) -> bytes:
    """Single-capture one ordinary final pathname without following a symlink."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(_os_path(path), flags)
    except OSError as exc:
        raise ComposerError(f"cannot open ordinary file {path}: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise ComposerError(f"path is not an ordinary file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ComposerError(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ComposerError(f"non-finite JSON constant in {label}: {value}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise ComposerError(f"non-UTF8 JSON in {label}") from exc
    except json.JSONDecodeError as exc:
        raise ComposerError(f"invalid JSON in {label}: {exc}") from exc


def _canonical_member(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ComposerError("member path must be a nonempty string")
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or str(rel) != name:
        raise ComposerError(f"noncanonical member path: {name}")
    return name


def archive_members(raw: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise ComposerError(f"invalid baseline archive: {exc}") from exc
    with archive:
        for member in archive.getmembers():
            name = _canonical_member(member.name)
            if not member.isfile() or name in result:
                raise ComposerError(f"noncanonical baseline member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ComposerError(f"missing baseline member payload: {name}")
            result[name] = stream.read()
    if not result:
        raise ComposerError("baseline archive is empty")
    return result


def archive_bytes(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, body in sorted(files.items()):
            _canonical_member(name)
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(body))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as zipped:
        zipped.write(raw.getvalue())
    return packed.getvalue()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ComposerError(f"{field} must be a list of strings")
    if len(value) != len(set(value)):
        raise ComposerError(f"{field} contains duplicates")
    for item in value:
        if not _ID_RE.fullmatch(item):
            raise ComposerError(f"invalid component id in {field}: {item}")
    return list(value)


def _source_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ComposerError("replacement source must be a nonempty relative path")
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or "\\" in value or str(rel) != value:
        raise ComposerError(f"noncanonical replacement source path: {value}")
    current = Path(root)
    for part in rel.parts:
        current = current / part
        try:
            mode = os.lstat(_os_path(current)).st_mode
        except OSError as exc:
            raise ComposerError(f"replacement source missing: {value}") from exc
        if stat.S_ISLNK(mode):
            raise ComposerError(f"replacement source crosses symlink: {value}")
    return current


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ComposerError(f"{field} must be a lowercase SHA256")
    return value


def load_component(path: Path) -> dict[str, Any]:
    path = Path(path)
    raw = read_regular(path)
    obj = _strict_json(raw, str(path))
    if not isinstance(obj, dict):
        raise ComposerError("component manifest must be a JSON object")
    keys = set(obj)
    missing_keys = _COMPONENT_REQUIRED_KEYS - keys
    extra_keys = keys - _COMPONENT_REQUIRED_KEYS - _COMPONENT_OPTIONAL_KEYS
    if missing_keys or extra_keys:
        raise ComposerError(
            "component manifest keys differ: "
            + repr(sorted(missing_keys | extra_keys))
        )
    if obj["schema"] != COMPONENT_SCHEMA:
        raise ComposerError("unknown component schema")
    component_id = obj["component_id"]
    if not isinstance(component_id, str) or not _ID_RE.fullmatch(component_id):
        raise ComposerError("invalid component_id")
    if obj["baseline_archive_sha256"] != BASELINE_SHA256:
        raise ComposerError("component baseline is not exact production-v3")
    if obj["kaggle_submission_hold"] is not True:
        raise ComposerError("component must retain kaggle_submission_hold=true")
    depends = _string_list(obj["depends_on"], "depends_on")
    conflicts = _string_list(obj["conflicts_with"], "conflicts_with")
    if component_id in depends or component_id in conflicts:
        raise ComposerError("component cannot depend on or conflict with itself")
    overlap = obj["overlap_after"]
    if not isinstance(overlap, dict):
        raise ComposerError("overlap_after must be an object")
    normalized_overlap: dict[str, str] = {}
    for member, prior in overlap.items():
        member = _canonical_member(member)
        if not isinstance(prior, str) or not _ID_RE.fullmatch(prior):
            raise ComposerError(f"invalid overlap predecessor for {member}")
        normalized_overlap[member] = prior
    replacements = obj["replacements"]
    additions = obj.get("additions", {})
    if not isinstance(replacements, dict):
        raise ComposerError("replacements must be an object")
    if not isinstance(additions, dict):
        raise ComposerError("additions must be an object")
    if not replacements and not additions:
        raise ComposerError("component must declare at least one replacement or addition")

    normalized: dict[str, dict[str, Any]] = {}
    for member, spec in replacements.items():
        member = _canonical_member(member)
        if not isinstance(spec, dict) or set(spec) != _REPLACEMENT_KEYS:
            raise ComposerError(f"replacement keys differ for {member}")
        pre = _sha(spec["preimage_sha256"], f"{member}.preimage_sha256")
        post = _sha(spec["postimage_sha256"], f"{member}.postimage_sha256")
        source_path = _source_path(path.parent, spec["source"])
        source_raw = read_regular(source_path)
        if digest(source_raw) != post:
            raise ComposerError(f"replacement postimage mismatch: {member}")
        normalized[member] = {
            "source": spec["source"],
            "preimage_sha256": pre,
            "postimage_sha256": post,
            "body": source_raw,
        }

    normalized_additions: dict[str, dict[str, Any]] = {}
    for member, spec in additions.items():
        member = _canonical_member(member)
        if member in normalized:
            raise ComposerError(f"component declares member as replacement and addition: {member}")
        if not isinstance(spec, dict) or set(spec) != _ADDITION_KEYS:
            raise ComposerError(f"addition keys differ for {member}")
        post = _sha(spec["postimage_sha256"], f"{member}.postimage_sha256")
        source_path = _source_path(path.parent, spec["source"])
        source_raw = read_regular(source_path)
        if digest(source_raw) != post:
            raise ComposerError(f"addition postimage mismatch: {member}")
        normalized_additions[member] = {
            "source": spec["source"],
            "postimage_sha256": post,
            "body": source_raw,
        }

    if set(normalized_overlap) - set(normalized):
        raise ComposerError("overlap_after names a member not replaced by this component")
    return {
        "component_id": component_id,
        "manifest_path": str(path),
        "manifest_sha256": digest(raw),
        "depends_on": depends,
        "conflicts_with": conflicts,
        "overlap_after": normalized_overlap,
        "replacements": normalized,
        "additions": normalized_additions,
    }


def compose_files(
    baseline: dict[str, bytes], components: list[dict[str, Any]]
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    if not components:
        raise ComposerError("at least one component is required")
    files = dict(baseline)
    included_set: set[str] = set()
    last_writer: dict[str, str] = {}
    applied: list[dict[str, Any]] = []
    for component in components:
        cid = component["component_id"]
        if cid in included_set:
            raise ComposerError(f"duplicate component_id: {cid}")
        missing = [dep for dep in component["depends_on"] if dep not in included_set]
        if missing:
            raise ComposerError(f"component {cid} has unsatisfied dependency: {missing[0]}")
        conflict = next((x for x in component["conflicts_with"] if x in included_set), None)
        if conflict is not None:
            raise ComposerError(f"component {cid} conflicts with {conflict}")
        reverse = next(
            (prev["component_id"] for prev in components[: len(applied)]
             if cid in prev["conflicts_with"]),
            None,
        )
        if reverse is not None:
            raise ComposerError(f"component {reverse} conflicts with {cid}")
        changed: dict[str, dict[str, Any]] = {}
        for member, replacement in sorted(component["replacements"].items()):
            if member not in files:
                raise ComposerError(f"component {cid} targets missing member: {member}")
            if digest(files[member]) != replacement["preimage_sha256"]:
                raise ComposerError(f"component {cid} preimage mismatch: {member}")
            prior = last_writer.get(member)
            declared = component["overlap_after"].get(member)
            if prior is None:
                if declared is not None:
                    raise ComposerError(
                        f"component {cid} declares overlap on untouched member: {member}"
                    )
            elif declared != prior:
                raise ComposerError(
                    f"component {cid} overlaps {member} after {prior} without exact declaration"
                )
            files[member] = replacement["body"]
            last_writer[member] = cid
            changed[member] = {
                "preimage_sha256": replacement["preimage_sha256"],
                "postimage_sha256": replacement["postimage_sha256"],
                "overlap_after": declared,
            }

        added: dict[str, dict[str, Any]] = {}
        for member, addition in sorted(component.get("additions", {}).items()):
            if member in files:
                raise ComposerError(f"component {cid} addition targets existing member: {member}")
            files[member] = addition["body"]
            last_writer[member] = cid
            added[member] = {
                "postimage_sha256": addition["postimage_sha256"],
                "absence_precondition": True,
            }

        included_set.add(cid)
        applied.append({
            "component_id": cid,
            "manifest_sha256": component["manifest_sha256"],
            "depends_on": list(component["depends_on"]),
            "conflicts_with": list(component["conflicts_with"]),
            "replacements": changed,
            "additions": added,
        })
    return files, applied


def compose(baseline_raw: bytes, components: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    if digest(baseline_raw) != BASELINE_SHA256:
        raise ComposerError("baseline archive is not exact production-v3")
    baseline = archive_members(baseline_raw)
    files, applied = compose_files(baseline, components)
    packed = archive_bytes(files)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "baseline_archive_sha256": BASELINE_SHA256,
        "candidate_archive_sha256": digest(packed),
        "member_count": len(files),
        "components": applied,
        "files": {name: digest(body) for name, body in sorted(files.items())},
        "kaggle_submission_hold": True,
    }
    return packed, receipt


def publish_pair(out: Path, receipt_path: Path, archive_raw: bytes, receipt_raw: bytes) -> None:
    """Publish composer archive+receipt through the canonical shared custody primitive."""
    out, receipt_path = Path(out), Path(receipt_path)
    if out == receipt_path:
        raise ComposerError("archive and receipt paths must differ")
    try:
        publish_exclusive(((out, archive_raw), (receipt_path, receipt_raw)))
    except ValueError as exc:
        # Keep the composer's public error surface fail-closed while delegating
        # all create-exclusive reservation/write/verify/rollback semantics.
        raise ComposerError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--component", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        baseline_raw = read_regular(args.baseline)
        components = [load_component(path) for path in args.component]
        packed, receipt = compose(baseline_raw, components)
        receipt_raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
        publish_pair(args.out, args.receipt, packed, receipt_raw)
    except (ComposerError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "candidate_archive_sha256": receipt["candidate_archive_sha256"],
        "components": [item["component_id"] for item in receipt["components"]],
        "member_count": receipt["member_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
