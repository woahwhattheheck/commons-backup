#!/usr/bin/env python3
"""Deterministic advisory rationalizer for a GitHub repository estate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.repo_estate_rationalizer.schema import *
from tools.repo_estate_rationalizer.schema import _canon_time, _plain, _time
_AUTHORITY_GENERATION: tuple[tuple[str, bool], ...] = (
    ("advisory_only", True),
    ("repository_visibility_mutation_authorized", False),
    ("repository_archive_mutation_authorized", False),
    ("repository_delete_authorized", False),
    ("branch_or_actions_mutation_authorized", False),
    ("billing_or_spend_mutation_authorized", False),
    ("publication_safety_certified", False),
)


class _FrozenSchemaGeneration:
    """Validation/hash/time generation detached from mutable schema-module globals."""

    __slots__ = (
        "plain", "parse_time", "canon_time", "loads_strict", "canonical_json",
        "sha256_json", "validate_snapshot", "validate_evidence",
    )

    def __init__(
        self,
        *,
        plain,
        parse_time,
        canon_time,
        loads_strict,
        canonical_json,
        sha256_json,
        validate_snapshot,
        validate_evidence,
    ):
        self.plain = plain
        self.parse_time = parse_time
        self.canon_time = canon_time
        self.loads_strict = loads_strict
        self.canonical_json = canonical_json
        self.sha256_json = sha256_json
        self.validate_snapshot = validate_snapshot
        self.validate_evidence = validate_evidence


def _build_frozen_schema_generation() -> _FrozenSchemaGeneration:
    """Capture the transitive schema dependency graph once at module import."""

    error = EstateError
    snapshot_schema = SNAPSHOT_SCHEMA
    evidence_schema = EVIDENCE_SCHEMA
    max_rows = MAX_ROWS
    max_text = MAX_TEXT
    max_age = MAX_EVIDENCE_AGE
    sha1_re = SHA1_RE
    repo_re = REPO_RE
    ref_re = REF_RE
    utc_re = UTC_RE
    visibility = frozenset(VISIBILITY)
    intents = frozenset(INTENTS)
    utc = UTC
    json_loads = json.loads
    json_dumps = json.dumps
    json_error = json.JSONDecodeError
    digest = hashlib.sha256
    parse_datetime = datetime.strptime
    zero = timedelta(0)

    def plain(value: Any, label: str) -> dict[str, Any]:
        if type(value) is not dict:
            raise error(f"{label} must be a plain object")
        return value

    def rows(value: Any, label: str) -> list[Any]:
        if type(value) is not list:
            raise error(f"{label} must be a list")
        if len(value) > max_rows:
            raise error(f"{label} exceeds {max_rows} rows")
        return value

    def boolean(value: Any, label: str) -> bool:
        if type(value) is not bool:
            raise error(f"{label} must be boolean")
        return value

    def integer(
        value: Any,
        label: str,
        *,
        minimum: int = 0,
        maximum: int = 1_000_000,
    ) -> int:
        if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
            raise error(f"{label} must be integer in [{minimum}, {maximum}]")
        return value

    def text(value: Any, label: str, *, pattern=None) -> str:
        if type(value) is not str or not value or len(value) > max_text:
            raise error(f"{label} is invalid")
        if pattern is not None and pattern.fullmatch(value) is None:
            raise error(f"{label} has invalid shape")
        return value

    def optional_sha1(value: Any, label: str) -> str | None:
        if value is None:
            return None
        if type(value) is not str or sha1_re.fullmatch(value) is None:
            raise error(f"{label} must be null or exact 40-hex commit SHA")
        return value

    def parse_time(value: Any, label: str) -> datetime:
        if type(value) is not str or utc_re.fullmatch(value) is None:
            raise error(f"{label} must be canonical UTC second text")
        try:
            return parse_datetime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=utc)
        except ValueError as exc:
            raise error(f"{label} must be canonical UTC second text") from exc

    def canon_time(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise error("trusted current time must be timezone-aware")
        return value.astimezone(utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fresh(observed: datetime, now: datetime) -> bool:
        delta = now - observed
        return zero <= delta <= max_age

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise error(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def reject_constant(token: str) -> None:
        raise error(f"non-finite JSON value: {token}")

    def loads_strict(text_value: str) -> Any:
        try:
            return json_loads(
                text_value,
                object_pairs_hook=strict_object,
                parse_constant=reject_constant,
            )
        except error:
            raise
        except (json_error, RecursionError, TypeError, ValueError) as exc:
            raise error(f"invalid JSON: {exc}") from exc

    def canonical_json(value: Any) -> str:
        try:
            return json_dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise error(f"value is not canonical JSON: {exc}") from exc

    def sha256_json(value: Any) -> str:
        return digest(canonical_json(value).encode("utf-8")).hexdigest()

    def validate_snapshot_frozen(value: Any) -> dict[str, Any]:
        obj = plain(value, "snapshot")
        expected = {"schema", "owner", "captured_at", "repositories"}
        if set(obj) != expected:
            raise error("snapshot keys mismatch")
        if obj.get("schema") != snapshot_schema:
            raise error("snapshot schema mismatch")
        owner = text(obj.get("owner"), "snapshot.owner", pattern=repo_re)
        captured = parse_time(obj.get("captured_at"), "snapshot.captured_at")
        repos = rows(obj.get("repositories"), "snapshot.repositories")
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for idx, raw in enumerate(repos):
            row = plain(raw, f"snapshot.repositories[{idx}]")
            keys = {"name", "visibility", "archived", "default_branch", "default_branch_sha"}
            if set(row) != keys:
                raise error(f"snapshot.repositories[{idx}] keys mismatch")
            name = text(row.get("name"), f"repo[{idx}].name", pattern=repo_re)
            folded = name.casefold()
            if folded in seen:
                raise error(f"duplicate/case-aliased repository identity: {name}")
            seen.add(folded)
            repo_visibility = row.get("visibility")
            if repo_visibility not in visibility:
                raise error(f"repo[{idx}].visibility invalid")
            branch = text(row.get("default_branch"), f"repo[{idx}].default_branch", pattern=repo_re)
            normalized.append(
                {
                    "name": name,
                    "visibility": repo_visibility,
                    "archived": boolean(row.get("archived"), f"repo[{idx}].archived"),
                    "default_branch": branch,
                    "default_branch_sha": optional_sha1(
                        row.get("default_branch_sha"),
                        f"repo[{idx}].default_branch_sha",
                    ),
                }
            )
        normalized.sort(key=lambda row: row["name"].casefold())
        return {
            "schema": snapshot_schema,
            "owner": owner,
            "captured_at": canon_time(captured),
            "repositories": normalized,
        }

    def validate_fresh_ref(raw: Any, label: str, now: datetime, sha: str) -> dict[str, Any]:
        obj = plain(raw, label)
        if set(obj) != {"result", "commit_sha", "observed_at", "ref"}:
            raise error(f"{label} keys mismatch")
        result = text(obj.get("result"), f"{label}.result")
        commit = text(obj.get("commit_sha"), f"{label}.commit_sha", pattern=sha1_re)
        observed = parse_time(obj.get("observed_at"), f"{label}.observed_at")
        retained_ref = text(obj.get("ref"), f"{label}.ref", pattern=ref_re)
        if commit != sha:
            raise error(f"{label} is bound to a different commit")
        return {
            "result": result,
            "commit_sha": commit,
            "observed_at": canon_time(observed),
            "ref": retained_ref,
            "fresh": fresh(observed, now),
        }

    def validate_evidence_frozen(value: Any, now: datetime) -> dict[str, dict[str, Any]]:
        obj = plain(value, "evidence")
        if set(obj) != {"schema", "repositories"} or obj.get("schema") != evidence_schema:
            raise error("evidence schema/keys mismatch")
        evidence_rows = rows(obj.get("repositories"), "evidence.repositories")
        out: dict[str, dict[str, Any]] = {}
        for idx, raw in enumerate(evidence_rows):
            row = plain(raw, f"evidence.repositories[{idx}]")
            expected = {
                "repository", "default_branch_sha", "intent", "owner_authorized",
                "owner_authority_ref", "secret_scan", "content_classification",
                "content_classification_ref", "legal_ip_review", "legal_ip_ref",
                "open_work", "dependencies", "archive_authorized",
                "archive_authority_ref",
            }
            if set(row) != expected:
                raise error(f"evidence.repositories[{idx}] keys mismatch")
            name = text(row.get("repository"), f"evidence[{idx}].repository", pattern=repo_re)
            folded = name.casefold()
            if folded in out:
                raise error(f"duplicate/case-aliased evidence repository: {name}")
            sha = text(row.get("default_branch_sha"), f"evidence[{idx}].default_branch_sha", pattern=sha1_re)
            intent = row.get("intent")
            if intent not in intents:
                raise error(f"evidence[{idx}].intent invalid")
            owner_authorized = boolean(row.get("owner_authorized"), f"evidence[{idx}].owner_authorized")
            owner_ref = text(row.get("owner_authority_ref"), f"evidence[{idx}].owner_authority_ref", pattern=ref_re)
            secret = validate_fresh_ref(row.get("secret_scan"), f"evidence[{idx}].secret_scan", now, sha)
            content = text(row.get("content_classification"), f"evidence[{idx}].content_classification")
            content_ref = text(row.get("content_classification_ref"), f"evidence[{idx}].content_classification_ref", pattern=ref_re)
            legal = text(row.get("legal_ip_review"), f"evidence[{idx}].legal_ip_review")
            legal_ref = text(row.get("legal_ip_ref"), f"evidence[{idx}].legal_ip_ref", pattern=ref_re)

            open_work = plain(row.get("open_work"), f"evidence[{idx}].open_work")
            if set(open_work) != {"open_prs", "open_issues", "active_claims", "observed_at", "ref"}:
                raise error(f"evidence[{idx}].open_work keys mismatch")
            work_seen = parse_time(open_work.get("observed_at"), f"evidence[{idx}].open_work.observed_at")
            open_norm = {
                "open_prs": integer(open_work.get("open_prs"), f"evidence[{idx}].open_work.open_prs"),
                "open_issues": integer(open_work.get("open_issues"), f"evidence[{idx}].open_work.open_issues"),
                "active_claims": integer(open_work.get("active_claims"), f"evidence[{idx}].open_work.active_claims"),
                "observed_at": canon_time(work_seen),
                "ref": text(open_work.get("ref"), f"evidence[{idx}].open_work.ref", pattern=ref_re),
                "fresh": fresh(work_seen, now),
            }

            deps = plain(row.get("dependencies"), f"evidence[{idx}].dependencies")
            if set(deps) != {"consumer_count", "replacement_repository", "replacement_verified", "observed_at", "ref"}:
                raise error(f"evidence[{idx}].dependencies keys mismatch")
            dep_seen = parse_time(deps.get("observed_at"), f"evidence[{idx}].dependencies.observed_at")
            replacement = deps.get("replacement_repository")
            if replacement is not None:
                replacement = text(replacement, f"evidence[{idx}].dependencies.replacement_repository", pattern=repo_re)
            dep_norm = {
                "consumer_count": integer(deps.get("consumer_count"), f"evidence[{idx}].dependencies.consumer_count"),
                "replacement_repository": replacement,
                "replacement_verified": boolean(deps.get("replacement_verified"), f"evidence[{idx}].dependencies.replacement_verified"),
                "observed_at": canon_time(dep_seen),
                "ref": text(deps.get("ref"), f"evidence[{idx}].dependencies.ref", pattern=ref_re),
                "fresh": fresh(dep_seen, now),
            }

            archive_authorized = boolean(row.get("archive_authorized"), f"evidence[{idx}].archive_authorized")
            archive_ref = text(row.get("archive_authority_ref"), f"evidence[{idx}].archive_authority_ref", pattern=ref_re)
            out[folded] = {
                "repository": name,
                "default_branch_sha": sha,
                "intent": intent,
                "owner_authorized": owner_authorized,
                "owner_authority_ref": owner_ref,
                "secret_scan": secret,
                "content_classification": content,
                "content_classification_ref": content_ref,
                "legal_ip_review": legal,
                "legal_ip_ref": legal_ref,
                "open_work": open_norm,
                "dependencies": dep_norm,
                "archive_authorized": archive_authorized,
                "archive_authority_ref": archive_ref,
            }
        return out

    return _FrozenSchemaGeneration(
        plain=plain,
        parse_time=parse_time,
        canon_time=canon_time,
        loads_strict=loads_strict,
        canonical_json=canonical_json,
        sha256_json=sha256_json,
        validate_snapshot=validate_snapshot_frozen,
        validate_evidence=validate_evidence_frozen,
    )


_FROZEN_SCHEMA = _build_frozen_schema_generation()


class _Generation:
    """Source-captured semantic generation.

    Production owns one instance built at import time. Tests may build isolated
    generations with explicit frozen clocks and source-trusted authority refs.
    No production call surface accepts semantic override keywords.
    """

    __slots__ = ("compile_at", "compile_packet", "verify_packet")

    def __init__(self, *, compile_at, compile_packet, verify_packet):
        self.compile_at = compile_at
        self.compile_packet = compile_packet
        self.verify_packet = verify_packet


def _build_generation(
    *,
    trusted_owner_refs: frozenset[str],
    trusted_archive_refs: frozenset[str],
    clock_now,
    _authority_generation: tuple[tuple[str, bool], ...] = _AUTHORITY_GENERATION,
    _validate_snapshot_generation=_FROZEN_SCHEMA.validate_snapshot,
    _validate_evidence_generation=_FROZEN_SCHEMA.validate_evidence,
    _canonical_json_generation=_FROZEN_SCHEMA.canonical_json,
    _loads_strict_generation=_FROZEN_SCHEMA.loads_strict,
    _sha256_generation=_FROZEN_SCHEMA.sha256_json,
    _canon_time_generation=_FROZEN_SCHEMA.canon_time,
    _time_generation=_FROZEN_SCHEMA.parse_time,
    _plain_generation=_FROZEN_SCHEMA.plain,
    _utc_generation=UTC,
    _error_generation=EstateError,
    _max_age: timedelta = timedelta(days=7),
    _packet_schema: str = PACKET_SCHEMA,
    _secret_clear: str = SECRET_CLEAR,
    _public_class: str = PUBLIC_CLASS,
    _legal_public: str = LEGAL_PUBLIC,
) -> _Generation:
    # Freeze every semantic root exactly once for this generation. In
    # particular, production passes datetime.now as a bound callable here at
    # import time, so later rebinding of the exported rr.datetime name cannot
    # alter freshness/currentness admission.
    owner_refs = frozenset(trusted_owner_refs)
    archive_refs = frozenset(trusted_archive_refs)
    authority = tuple(_authority_generation)

    def decision(repo: dict[str, Any], ev: dict[str, Any] | None) -> dict[str, Any]:
        if repo["visibility"] == "public":
            return {
                "repository": repo["name"],
                "state": "PUBLIC_ALREADY",
                "reasons": ["ALREADY_PUBLIC"],
                "branch_sha": repo["default_branch_sha"],
            }
        if ev is None:
            return {
                "repository": repo["name"],
                "state": "HOLD",
                "reasons": ["MISSING_PUBLICATION_RETENTION_EVIDENCE"],
                "branch_sha": repo["default_branch_sha"],
            }

        reasons: list[str] = []
        sha = repo["default_branch_sha"]
        if sha is None:
            reasons.append("MISSING_CURRENT_BRANCH_SHA")
        elif ev["default_branch_sha"] != sha:
            reasons.append("BRANCH_GENERATION_DRIFT")

        # Keeping data private is fail-closed and never needs a publication
        # credential.
        if ev["intent"] == "keep_private":
            return {
                "repository": repo["name"],
                "state": "KEEP_PRIVATE" if not reasons else "HOLD",
                "reasons": reasons or ["CONSERVATIVE_KEEP_PRIVATE"],
                "branch_sha": sha,
            }

        if not ev["owner_authorized"]:
            reasons.append("OWNER_AUTHORITY_NOT_PROVEN")
        elif ev["owner_authority_ref"] not in owner_refs:
            reasons.append("OWNER_AUTHORITY_NOT_SOURCE_TRUSTED")
        if ev["secret_scan"]["result"] != _secret_clear or not ev["secret_scan"]["fresh"]:
            reasons.append("SECRET_SCAN_NOT_CURRENT_CLEAR")
        if ev["content_classification"] != _public_class:
            reasons.append("CONTENT_NOT_CLEARED_FOR_PUBLIC_RELEASE")
        if ev["legal_ip_review"] != _legal_public:
            reasons.append("LEGAL_IP_NOT_CLEARED_FOR_PUBLIC_RELEASE")
        if not ev["open_work"]["fresh"]:
            reasons.append("OPEN_WORK_SNAPSHOT_STALE")
        if not ev["dependencies"]["fresh"]:
            reasons.append("DEPENDENCY_SNAPSHOT_STALE")

        if ev["intent"] == "review_public":
            return {
                "repository": repo["name"],
                "state": "PUBLICATION_REVIEW" if not reasons else "HOLD",
                "reasons": reasons or ["SOURCE_TRUSTED_PUBLICATION_REVIEW_EVIDENCE_COMPLETE"],
                "branch_sha": sha,
            }

        if ev["intent"] == "review_archive":
            if not ev["archive_authorized"]:
                reasons.append("ARCHIVE_AUTHORITY_NOT_PROVEN")
            elif ev["archive_authority_ref"] not in archive_refs:
                reasons.append("ARCHIVE_AUTHORITY_NOT_SOURCE_TRUSTED")
            if any(ev["open_work"][key] for key in ("open_prs", "open_issues", "active_claims")):
                reasons.append("OPEN_WORK_BLOCKS_ARCHIVE")
            if ev["dependencies"]["consumer_count"]:
                reasons.append("ACTIVE_CONSUMERS_BLOCK_ARCHIVE")
            if (
                ev["dependencies"]["replacement_repository"] is not None
                and not ev["dependencies"]["replacement_verified"]
            ):
                reasons.append("REPLACEMENT_RELATION_UNVERIFIED")
            return {
                "repository": repo["name"],
                "state": "ARCHIVE_REVIEW" if not reasons else "HOLD",
                "reasons": reasons or ["SOURCE_TRUSTED_ARCHIVE_REVIEW_EVIDENCE_COMPLETE"],
                "branch_sha": sha,
            }

        raise _error_generation("unreachable evidence intent")

    def compile_at(snapshot: Any, evidence: Any, *, now: datetime) -> dict[str, Any]:
        snap = _validate_snapshot_generation(snapshot)
        if now.tzinfo is None or now.utcoffset() is None:
            raise _error_generation("trusted current time must be timezone-aware")
        current = now.astimezone(_utc_generation)
        snap_time = _time_generation(snap["captured_at"], "snapshot.captured_at")
        if snap_time > current or current - snap_time > _max_age:
            raise _error_generation("repository snapshot is stale or from the future")

        evmap = _validate_evidence_generation(evidence, current)
        frozen_evidence = _loads_strict_generation(_canonical_json_generation(evidence))
        frozen_evmap = _validate_evidence_generation(frozen_evidence, current)
        if frozen_evmap != evmap:
            raise _error_generation("evidence changed while being frozen")
        frozen_evidence["repositories"].sort(key=lambda row: row["repository"].casefold())

        names = {repo["name"].casefold() for repo in snap["repositories"]}
        extras = sorted(
            ev["repository"] for key, ev in evmap.items() if key not in names
        )
        if extras:
            raise _error_generation(
                f"evidence references repositories absent from snapshot: {extras}"
            )

        decisions = [
            decision(repo, evmap.get(repo["name"].casefold()))
            for repo in snap["repositories"]
        ]
        counts: dict[str, int] = {}
        for row in decisions:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        private_count = sum(repo["visibility"] == "private" for repo in snap["repositories"])
        public_count = len(snap["repositories"]) - private_count

        packet: dict[str, Any] = {
            "schema": _packet_schema,
            "evaluated_at": _canon_time_generation(current),
            "owner": snap["owner"],
            "source": {
                "snapshot_sha256": _sha256_generation(snap),
                "evidence_sha256": _sha256_generation(frozen_evidence),
                "snapshot_captured_at": snap["captured_at"],
            },
            "estate": {
                "repository_count": len(snap["repositories"]),
                "private_repository_count": private_count,
                "public_repository_count": public_count,
                "state_counts": dict(sorted(counts.items())),
            },
            "decisions": decisions,
            "authority": dict(authority),
        }
        packet["packet_sha256"] = _sha256_generation(packet)
        return packet

    def compile_packet(snapshot: Any, evidence: Any) -> dict[str, Any]:
        return compile_at(snapshot, evidence, now=clock_now(_utc_generation))

    def verify_packet(packet: Any, snapshot: Any, evidence: Any) -> bool:
        try:
            obj = _plain_generation(packet, "packet")
            if obj.get("authority") != dict(authority):
                return False
            receipt = obj.get("packet_sha256")
            if (
                type(receipt) is not str
                or len(receipt) != 64
                or any(char not in "0123456789abcdef" for char in receipt)
            ):
                return False
            unsigned = dict(obj)
            unsigned.pop("packet_sha256", None)
            if _sha256_generation(unsigned) != receipt:
                return False
            evaluated = _time_generation(obj.get("evaluated_at"), "packet.evaluated_at")
            current = clock_now(_utc_generation)
            if evaluated > current or current - evaluated > _max_age:
                return False
            return obj == compile_at(snapshot, evidence, now=evaluated)
        except (_error_generation, TypeError, ValueError):
            return False

    return _Generation(
        compile_at=compile_at,
        compile_packet=compile_packet,
        verify_packet=verify_packet,
    )


def _make_test_generation(
    *,
    trusted_owner_refs: frozenset[str] = frozenset(),
    trusted_archive_refs: frozenset[str] = frozenset(),
    clock_now,
) -> _Generation:
    """Build an isolated test generation; never used by the CLI/public surface."""
    return _build_generation(
        trusted_owner_refs=trusted_owner_refs,
        trusted_archive_refs=trusted_archive_refs,
        clock_now=clock_now,
    )


_PRODUCTION_GENERATION = _build_generation(
    trusted_owner_refs=frozenset(),
    trusted_archive_refs=frozenset(),
    clock_now=datetime.now,
)

compile_packet = _PRODUCTION_GENERATION.compile_packet
verify_packet = _PRODUCTION_GENERATION.verify_packet


def render_markdown(packet: Any) -> str:
    obj = _plain(packet, "packet")
    if obj.get("schema") != PACKET_SCHEMA:
        raise EstateError("packet schema mismatch")
    estate = _plain(obj.get("estate"), "packet.estate")
    lines = [
        "# Repository Estate Rationalizer",
        "",
        f"- repositories: **{estate['repository_count']}**",
        f"- private: **{estate['private_repository_count']}**",
        f"- public: **{estate['public_repository_count']}**",
        f"- evaluated_at: `{obj['evaluated_at']}`",
        "",
        "## Decisions",
    ]
    for row in obj.get("decisions", []):
        reasons = ", ".join(row["reasons"])
        lines.append(f"- `{row['repository']}` — **{row['state']}** — {reasons}")
    lines += [
        "",
        "This is advisory decision support only. It does not authorize repository visibility, archive/delete, branch, Actions, billing, or spend mutations.",
        "A PUBLICATION_REVIEW or ARCHIVE_REVIEW state is not a safety certification; a human/operator must still perform the separate irreversible repository action.",
        f"Packet SHA-256: `{obj['packet_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def _open_parent(path: Path, *, create: bool = False) -> int:
    if not path.name or path.name in {".", ".."}:
        raise EstateError("path must name a file")
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise EstateError("platform lacks descriptor-safe directory flags")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow | directory
    try:
        return os.open(path.parent, flags)
    except OSError as exc:
        raise EstateError(f"cannot pin parent directory for {path}: {exc}") from exc


def _read_regular(path: Path) -> bytes:
    pfd = _open_parent(path)
    try:
        try:
            before = os.stat(path.name, dir_fd=pfd, follow_symlinks=False)
        except OSError as exc:
            raise EstateError(f"cannot inspect {path}: {exc}") from exc
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise EstateError(f"{path.name} must be a bounded regular file")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        nonblock = getattr(os, "O_NONBLOCK", None)
        if nofollow is None or nonblock is None:
            raise EstateError("platform lacks descriptor-safe file flags")
        fd = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow | nonblock,
            dir_fd=pfd,
        )
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
                raise EstateError(f"{path.name} changed while opening")
            data = bytearray()
            while True:
                chunk = os.read(fd, min(131072, MAX_FILE_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_FILE_BYTES:
                    raise EstateError(f"{path.name} is too large")
            after = os.fstat(fd)
            linked = os.stat(path.name, dir_fd=pfd, follow_symlinks=False)
            generation = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            if generation != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise EstateError(f"{path.name} changed while reading")
            if (linked.st_dev, linked.st_ino, linked.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
                raise EstateError(f"{path.name} pathname changed while reading")
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(pfd)

def _load(path: Path) -> dict[str, Any]:
    try:
        return _plain(loads_strict(_read_regular(path).decode("utf-8")), path.name)
    except UnicodeDecodeError as exc:
        raise EstateError(f"{path.name} is not UTF-8") from exc


def _write_exclusive(path: Path, text: str) -> None:
    pfd = _open_parent(path, create=True)
    try:
        try:
            os.stat(path.name, dir_fd=pfd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise EstateError(f"cannot inspect output {path}: {exc}") from exc
        else:
            raise EstateError(f"output already exists: {path}")

        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise EstateError("platform lacks O_NOFOLLOW")
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | nofollow,
            0o600,
            dir_fd=pfd,
        )
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise EstateError("created output is not a regular file")
            data = text.encode("utf-8")
            view = memoryview(data)
            while view:
                n = os.write(fd, view)
                if n <= 0:
                    raise EstateError("short write")
                view = view[n:]
            os.fsync(fd)
            after = os.fstat(fd)
            linked = os.stat(path.name, dir_fd=pfd, follow_symlinks=False)
            if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                raise EstateError("output descriptor generation changed")
            if (linked.st_dev, linked.st_ino) != (opened.st_dev, opened.st_ino):
                raise EstateError("output pathname changed while writing")
        finally:
            # Never unlink an uncertain pathname on failure. A partial file is
            # retained fail-closed for explicit operator inspection.
            os.close(fd)
    finally:
        os.close(pfd)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--snapshot", type=Path, required=True)
    c.add_argument("--evidence", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--markdown", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--snapshot", type=Path, required=True)
    v.add_argument("--evidence", type=Path, required=True)
    v.add_argument("--packet", type=Path, required=True)
    v.add_argument("--markdown", type=Path)
    args = p.parse_args(argv)
    try:
        snapshot = _load(args.snapshot)
        evidence = _load(args.evidence)
        if args.cmd == "compile":
            packet = compile_packet(snapshot, evidence)
            _write_exclusive(args.out, json.dumps(packet, indent=2, sort_keys=True, allow_nan=False) + "\n")
            _write_exclusive(args.markdown, render_markdown(packet))
            print(packet["packet_sha256"])
            return 0
        packet = _load(args.packet)
        if not verify_packet(packet, snapshot, evidence):
            print("REFUSED: packet verification failed", file=sys.stderr)
            return 2
        if args.markdown is not None and _read_regular(args.markdown).decode("utf-8") != render_markdown(packet):
            print("REFUSED: markdown does not match packet", file=sys.stderr)
            return 2
        print("VERIFIED")
        return 0
    except (EstateError, OSError, UnicodeError, TypeError) as exc:
        # Normalize malformed public input and local I/O faults at the CLI boundary.
        # Descriptor helpers keep their conservative partial-file retention semantics.
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
