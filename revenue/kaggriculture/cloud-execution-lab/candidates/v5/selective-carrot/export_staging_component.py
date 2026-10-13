#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export an authenticated TITAN V5 candidate delta as a staging component.

This is convergence plumbing for the single production-v3/V5 line. It does not
decide whether a candidate won economics or promotion gates. The output schema
is exactly ``titan-v5-staging-component/v1`` consumed by the staging composer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Iterable

from publication_custody import publish_exclusive
import staging_composer


BASELINE_SHA256 = staging_composer.BASELINE_SHA256
COMPONENT_SCHEMA = staging_composer.COMPONENT_SCHEMA
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ExportError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_regular(path: Path) -> bytes:
    path = Path(path)
    # Windows ``os.open`` otherwise uses text mode. A gzip stream may contain
    # byte 0x1a, which the CRT treats as EOF; the exact production-v3 archive
    # currently hits that byte at offset 32 and was therefore misread as a
    # 32-byte input. Binary mode is a no-op on POSIX and preserves every byte
    # on Windows.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ExportError(f"cannot open ordinary file {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ExportError(f"path is not an ordinary file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def canonical_member(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ExportError("archive member path must be a nonempty string")
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or str(rel) != name:
        raise ExportError(f"noncanonical or reserved archive member path: {name}")
    return name


def source_name(member: str) -> str:
    return f"files/{hashlib.sha256(member.encode('utf-8')).hexdigest()}.bin"


def archive_members(raw: bytes, label: str) -> dict[str, bytes]:
    try:
        return staging_composer.archive_members(raw)
    except staging_composer.ComposerError as exc:
        raise ExportError(f"invalid {label} archive: {exc}") from exc


def _sha(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ExportError(f"{field} must be a lowercase SHA256")
    return value


def _component_id(value: str, field: str = "component_id") -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ExportError(f"invalid {field}: {value!r}")
    return value


def _id_list(values: Iterable[str], field: str) -> list[str]:
    out = [_component_id(value, field) for value in values]
    if len(out) != len(set(out)):
        raise ExportError(f"{field} contains duplicates")
    return out


def _parse_overlap(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ExportError("overlap must be MEMBER=COMPONENT")
        member, prior = raw.split("=", 1)
        member = canonical_member(member)
        prior = _component_id(prior, "overlap predecessor")
        if member in result:
            raise ExportError(f"duplicate overlap declaration: {member}")
        result[member] = prior
    return result


def _strict_json(raw: bytes, label: str):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ExportError(f"duplicate JSON key in {label}: {key}")
            out[key] = value
        return out

    def constant(value):
        raise ExportError(f"non-finite JSON constant in {label}: {value}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise ExportError(f"non-UTF8 JSON in {label}") from exc
    except json.JSONDecodeError as exc:
        raise ExportError(f"invalid JSON in {label}: {exc}") from exc


def receipt_graph_state(
    *,
    receipt_raw: bytes,
    receipt_sha256: str,
    current_sha256: str,
    baseline: dict[str, bytes],
    current: dict[str, bytes],
) -> tuple[dict[str, str], set[str], dict[str, set[str]]]:
    """Authenticate one composer receipt and reconstruct writers plus graph state."""
    expected_receipt = _sha(receipt_sha256, "current_receipt_sha256")
    if digest(receipt_raw) != expected_receipt:
        raise ExportError("current composer receipt SHA256 mismatch")
    obj = _strict_json(receipt_raw, "current composer receipt")
    required = {
        "schema", "baseline_archive_sha256", "candidate_archive_sha256",
        "member_count", "components", "files", "kaggle_submission_hold",
    }
    if not isinstance(obj, dict) or set(obj) != required:
        raise ExportError("current composer receipt keys differ")
    if obj["schema"] != staging_composer.RECEIPT_SCHEMA:
        raise ExportError("current receipt schema is not the landed composer schema")
    if obj["baseline_archive_sha256"] != BASELINE_SHA256:
        raise ExportError("current receipt baseline is not exact production-v3")
    if obj["candidate_archive_sha256"] != current_sha256:
        raise ExportError("current receipt candidate SHA256 does not bind current archive")
    if obj["kaggle_submission_hold"] is not True:
        raise ExportError("current receipt must retain kaggle_submission_hold=true")
    if type(obj["member_count"]) is not int or obj["member_count"] != len(current):
        raise ExportError("current receipt member_count mismatch")
    files = obj["files"]
    if not isinstance(files, dict) or set(files) != set(current):
        raise ExportError("current receipt file surface mismatch")
    for member, body in current.items():
        if files.get(member) != digest(body):
            raise ExportError(f"current receipt file hash mismatch: {member}")

    components = obj["components"]
    if not isinstance(components, list) or not components:
        raise ExportError("current receipt components must be a nonempty list")
    hashes = {member: digest(body) for member, body in baseline.items()}
    last_writer: dict[str, str] = {}
    included: set[str] = set()
    historical_conflicts: dict[str, set[str]] = {}
    component_keys = {
        "component_id", "manifest_sha256", "depends_on", "conflicts_with",
        "replacements", "additions",
    }
    for component in components:
        if not isinstance(component, dict) or set(component) != component_keys:
            raise ExportError("current receipt component keys differ")
        cid = _component_id(component["component_id"], "receipt component_id")
        if cid in included:
            raise ExportError(f"duplicate receipt component_id: {cid}")
        _sha(component["manifest_sha256"], "receipt manifest_sha256")
        raw_depends = component["depends_on"]
        raw_conflicts = component["conflicts_with"]
        if type(raw_depends) is not list:
            raise ExportError("receipt depends_on must be a list")
        if type(raw_conflicts) is not list:
            raise ExportError("receipt conflicts_with must be a list")
        depends = _id_list(raw_depends, "receipt depends_on")
        conflicts = _id_list(raw_conflicts, "receipt conflicts_with")
        if cid in depends or cid in conflicts:
            raise ExportError(f"receipt component {cid} depends/conflicts with itself")
        missing = [dep for dep in depends if dep not in included]
        if missing:
            raise ExportError(f"receipt component {cid} has unsatisfied dependency: {missing[0]}")
        conflict = next((item for item in conflicts if item in included), None)
        if conflict is not None:
            raise ExportError(f"receipt component {cid} conflicts with {conflict}")
        reverse = next(
            (prior for prior, prior_conflicts in historical_conflicts.items()
             if cid in prior_conflicts),
            None,
        )
        if reverse is not None:
            raise ExportError(f"receipt component {reverse} conflicts with {cid}")

        replacements = component["replacements"]
        additions = component["additions"]
        if not isinstance(replacements, dict) or not isinstance(additions, dict):
            raise ExportError("receipt replacements/additions must be objects")
        if not replacements and not additions:
            raise ExportError(f"receipt component {cid} has no writes")
        if set(replacements) & set(additions):
            raise ExportError(f"receipt component {cid} duplicates a member write")
        for member, spec in sorted(replacements.items()):
            member = canonical_member(member)
            if not isinstance(spec, dict) or set(spec) != {
                "preimage_sha256", "postimage_sha256", "overlap_after"
            }:
                raise ExportError(f"receipt replacement keys differ: {member}")
            pre = _sha(spec["preimage_sha256"], f"receipt {member}.preimage_sha256")
            post = _sha(spec["postimage_sha256"], f"receipt {member}.postimage_sha256")
            if member not in hashes or hashes[member] != pre:
                raise ExportError(f"receipt replacement preimage mismatch: {member}")
            prior = last_writer.get(member)
            declared = spec["overlap_after"]
            if prior is None:
                if declared is not None:
                    raise ExportError(f"receipt overlap on untouched member: {member}")
            elif declared != prior:
                raise ExportError(f"receipt overlap predecessor mismatch: {member}")
            hashes[member] = post
            last_writer[member] = cid
        for member, spec in sorted(additions.items()):
            member = canonical_member(member)
            if not isinstance(spec, dict) or set(spec) != {
                "postimage_sha256", "absence_precondition"
            }:
                raise ExportError(f"receipt addition keys differ: {member}")
            if spec["absence_precondition"] is not True:
                raise ExportError(f"receipt addition lacks absence precondition: {member}")
            if member in hashes:
                raise ExportError(f"receipt addition targets existing member: {member}")
            hashes[member] = _sha(
                spec["postimage_sha256"], f"receipt {member}.postimage_sha256"
            )
            last_writer[member] = cid

        included.add(cid)
        historical_conflicts[cid] = set(conflicts)

    if hashes != files:
        raise ExportError("current receipt history does not reproduce final file hashes")
    return last_writer, included, historical_conflicts


def derive_component(
    *,
    baseline_raw: bytes,
    current_raw: bytes,
    candidate_raw: bytes,
    candidate_sha256: str,
    current_sha256: str | None,
    component_id: str,
    current_receipt_raw: bytes | None = None,
    current_receipt_sha256: str | None = None,
    depends_on: Iterable[str] = (),
    conflicts_with: Iterable[str] = (),
    overlap_after: dict[str, str] | None = None,
) -> tuple[dict, dict[str, bytes]]:
    if digest(baseline_raw) != BASELINE_SHA256:
        raise ExportError("baseline archive is not exact production-v3")
    expected_candidate = _sha(candidate_sha256, "candidate_sha256")
    if digest(candidate_raw) != expected_candidate:
        raise ExportError("candidate archive SHA256 mismatch")

    if current_sha256 is None:
        if current_raw != baseline_raw:
            raise ExportError("non-baseline current archive requires current_sha256")
        if current_receipt_raw is not None or current_receipt_sha256 is not None:
            raise ExportError("baseline current must not supply a composer receipt")
        expected_current = None
    else:
        expected_current = _sha(current_sha256, "current_sha256")
        if digest(current_raw) != expected_current:
            raise ExportError("current archive SHA256 mismatch")
        if current_receipt_raw is None or current_receipt_sha256 is None:
            raise ExportError("non-baseline current archive requires authenticated composer receipt")

    cid = _component_id(component_id)
    depends = _id_list(depends_on, "depends_on")
    conflicts = _id_list(conflicts_with, "conflicts_with")
    if cid in depends or cid in conflicts:
        raise ExportError("component cannot depend on or conflict with itself")
    impossible = sorted(set(depends) & set(conflicts))
    if impossible:
        raise ExportError(
            f"component cannot both depend on and conflict with: {impossible[0]}"
        )

    overlap = dict(overlap_after or {})
    for member, prior in overlap.items():
        canonical_member(member)
        _component_id(prior, "overlap predecessor")

    baseline = archive_members(baseline_raw, "baseline")
    current = archive_members(current_raw, "current")
    candidate = archive_members(candidate_raw, "candidate")
    if expected_current is None:
        last_writer: dict[str, str] = {}
        included: set[str] = set()
        historical_conflicts: dict[str, set[str]] = {}
    else:
        last_writer, included, historical_conflicts = receipt_graph_state(
            receipt_raw=current_receipt_raw,
            receipt_sha256=current_receipt_sha256,
            current_sha256=expected_current,
            baseline=baseline,
            current=current,
        )

    if cid in included:
        raise ExportError(f"component_id already included in current history: {cid}")
    missing_dep = next((dep for dep in depends if dep not in included), None)
    if missing_dep is not None:
        raise ExportError(f"component has unsatisfied dependency: {missing_dep}")
    forward_conflict = next((item for item in conflicts if item in included), None)
    if forward_conflict is not None:
        raise ExportError(f"component conflicts with included component: {forward_conflict}")
    reverse_conflict = next(
        (prior for prior, prior_conflicts in historical_conflicts.items()
         if cid in prior_conflicts),
        None,
    )
    if reverse_conflict is not None:
        raise ExportError(f"historical component {reverse_conflict} conflicts with {cid}")

    missing_baseline = sorted(set(baseline) - set(current))
    if missing_baseline:
        raise ExportError(f"current archive deletes production-v3 member: {missing_baseline[0]}")
    deleted = sorted(set(current) - set(candidate))
    if deleted:
        raise ExportError(f"candidate deletes current member: {deleted[0]}")

    replacements: dict[str, dict[str, str]] = {}
    additions: dict[str, dict[str, str]] = {}
    payloads: dict[str, bytes] = {}
    changed_members: set[str] = set()

    for member in sorted(candidate):
        after = candidate[member]
        if member in current:
            before = current[member]
            if after == before:
                continue
            changed_members.add(member)
            prior = last_writer.get(member)
            declared = overlap.get(member)
            if prior is None:
                if declared is not None:
                    raise ExportError(f"overlap declared on baseline-owned member: {member}")
            elif declared != prior:
                raise ExportError(
                    f"replacement requires exact overlap predecessor {prior}: {member}"
                )
            source = source_name(member)
            replacements[member] = {
                "source": source,
                "preimage_sha256": digest(before),
                "postimage_sha256": digest(after),
            }
            payloads[source] = after
        else:
            changed_members.add(member)
            source = source_name(member)
            additions[member] = {
                "source": source,
                "postimage_sha256": digest(after),
            }
            payloads[source] = after

    if not changed_members:
        raise ExportError("candidate has no delta from current archive")
    extra_overlap = sorted(set(overlap) - set(replacements))
    if extra_overlap:
        raise ExportError(f"overlap names non-replacement member: {extra_overlap[0]}")

    manifest = {
        "schema": COMPONENT_SCHEMA,
        "component_id": cid,
        "baseline_archive_sha256": BASELINE_SHA256,
        "depends_on": depends,
        "conflicts_with": conflicts,
        "overlap_after": {key: overlap[key] for key in sorted(overlap)},
        "replacements": replacements,
        "additions": additions,
        "kaggle_submission_hold": True,
    }
    return manifest, payloads


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")


def preflight_component(manifest: dict, payloads: dict[str, bytes]) -> None:
    with tempfile.TemporaryDirectory(prefix="titan-v5-component-preflight-") as td:
        root = Path(td)
        (root / "COMPONENT.json").write_bytes(manifest_bytes(manifest))
        for source, raw in payloads.items():
            rel = PurePosixPath(source)
            target = root.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        try:
            loaded = staging_composer.load_component(root / "COMPONENT.json")
        except staging_composer.ComposerError as exc:
            raise ExportError(f"landed composer rejected generated component: {exc}") from exc
        if loaded["component_id"] != manifest["component_id"]:
            raise ExportError("composer preflight component identity mismatch")
        if set(loaded["replacements"]) != set(manifest["replacements"]):
            raise ExportError("composer preflight replacement surface mismatch")
        if set(loaded.get("additions", {})) != set(manifest["additions"]):
            raise ExportError("composer preflight addition surface mismatch")


def publish_component(out_dir: Path, manifest: dict, payloads: dict[str, bytes]) -> None:
    out_dir = Path(out_dir)
    if out_dir.exists():
        try:
            mode = os.lstat(out_dir).st_mode
        except OSError as exc:
            raise ExportError(f"cannot inspect output directory {out_dir}: {exc}") from exc
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise ExportError(f"output path is not an ordinary directory: {out_dir}")
        entries = list(out_dir.iterdir())
        if entries:
            scaffold = out_dir / "files"
            try:
                scaffold_mode = os.lstat(scaffold).st_mode
            except OSError as exc:
                raise ExportError(f"output directory is not empty: {out_dir}") from exc
            if (
                len(entries) != 1
                or entries[0] != scaffold
                or not stat.S_ISDIR(scaffold_mode)
                or stat.S_ISLNK(scaffold_mode)
                or any(scaffold.iterdir())
            ):
                raise ExportError(f"output directory is not empty: {out_dir}")
    preflight_component(manifest, payloads)
    requested: list[tuple[Path, bytes]] = [
        (out_dir / "COMPONENT.json", manifest_bytes(manifest))
    ]
    for source, raw in sorted(payloads.items()):
        rel = PurePosixPath(source)
        if rel.is_absolute() or ".." in rel.parts or "\\" in source or str(rel) != source:
            raise ExportError(f"noncanonical output source path: {source}")
        requested.append((out_dir.joinpath(*rel.parts), raw))
    if len(requested) < 2:
        raise ExportError("component publication requires manifest plus source payload")
    try:
        publish_exclusive(requested)
    except Exception as exc:
        raise ExportError(f"component publication failed: {exc}") from exc


def export_component(
    *,
    baseline_path: Path,
    candidate_path: Path,
    candidate_sha256: str,
    out_dir: Path,
    component_id: str,
    current_path: Path | None = None,
    current_sha256: str | None = None,
    current_receipt_path: Path | None = None,
    current_receipt_sha256: str | None = None,
    depends_on: Iterable[str] = (),
    conflicts_with: Iterable[str] = (),
    overlap_values: Iterable[str] = (),
) -> dict:
    baseline_raw = read_regular(baseline_path)
    current_raw = baseline_raw if current_path is None else read_regular(current_path)
    current_receipt_raw = (
        None if current_receipt_path is None else read_regular(current_receipt_path)
    )
    candidate_raw = read_regular(candidate_path)
    overlap = _parse_overlap(overlap_values)
    manifest, payloads = derive_component(
        baseline_raw=baseline_raw,
        current_raw=current_raw,
        candidate_raw=candidate_raw,
        candidate_sha256=candidate_sha256,
        current_sha256=current_sha256,
        component_id=component_id,
        current_receipt_raw=current_receipt_raw,
        current_receipt_sha256=current_receipt_sha256,
        depends_on=depends_on,
        conflicts_with=conflicts_with,
        overlap_after=overlap,
    )
    publish_component(out_dir, manifest, payloads)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export exact candidate delta for TITAN V5 staging composer"
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--component-id", required=True)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--current-sha256")
    parser.add_argument("--current-receipt", type=Path)
    parser.add_argument("--current-receipt-sha256")
    parser.add_argument("--depends-on", action="append", default=[])
    parser.add_argument("--conflicts-with", action="append", default=[])
    parser.add_argument("--overlap-after", action="append", default=[], metavar="MEMBER=COMPONENT")
    args = parser.parse_args(argv)
    current_group = (
        args.current,
        args.current_sha256,
        args.current_receipt,
        args.current_receipt_sha256,
    )
    if any(value is not None for value in current_group) and not all(
        value is not None for value in current_group
    ):
        parser.error(
            "--current, --current-sha256, --current-receipt, and "
            "--current-receipt-sha256 must be supplied together"
        )
    manifest = export_component(
        baseline_path=args.baseline,
        candidate_path=args.candidate,
        candidate_sha256=args.candidate_sha256,
        out_dir=args.out_dir,
        component_id=args.component_id,
        current_path=args.current,
        current_sha256=args.current_sha256,
        current_receipt_path=args.current_receipt,
        current_receipt_sha256=args.current_receipt_sha256,
        depends_on=args.depends_on,
        conflicts_with=args.conflicts_with,
        overlap_values=args.overlap_after,
    )
    print(json.dumps({
        "component_id": manifest["component_id"],
        "replacements": sorted(manifest["replacements"]),
        "additions": sorted(manifest["additions"]),
        "output": str(args.out_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
