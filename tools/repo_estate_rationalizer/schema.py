#!/usr/bin/env python3
"""Deterministic advisory rationalizer for a GitHub repository estate.

The tool never changes repository visibility, archive state, branches, Actions, or
billing.  Positive publication/archive recommendations require explicit retained
source-trusted owner evidence bound to the exact repository generation being evaluated; caller assertions alone never establish publication/archive authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SNAPSHOT_SCHEMA = "commons.repo-estate.snapshot/v1"
EVIDENCE_SCHEMA = "commons.repo-estate.evidence/v1"
PACKET_SCHEMA = "commons.repo-estate.rationalizer/v1"
MAX_FILE_BYTES = 4_000_000
MAX_ROWS = 10_000
MAX_TEXT = 256
MAX_EVIDENCE_AGE = timedelta(days=7)
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,255}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VISIBILITY = {"public", "private"}
INTENTS = {"keep_private", "review_public", "review_archive"}
PUBLIC_CLASS = "PUBLIC_RELEASE_OK"
LEGAL_PUBLIC = "CLEAR_FOR_PUBLIC_RELEASE"
SECRET_CLEAR = "CLEAR"
AUTHORITY = {
    "advisory_only": True,
    "repository_visibility_mutation_authorized": False,
    "repository_archive_mutation_authorized": False,
    "repository_delete_authorized": False,
    "branch_or_actions_mutation_authorized": False,
    "billing_or_spend_mutation_authorized": False,
    "publication_safety_certified": False,
}


class EstateError(ValueError):
    """Input cannot safely support an estate recommendation packet."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EstateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> None:
    raise EstateError(f"non-finite JSON value: {token}")


def loads_strict(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except EstateError:
        raise
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise EstateError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EstateError(f"value is not canonical JSON: {exc}") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _plain(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EstateError(f"{label} must be a plain object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise EstateError(f"{label} must be a list")
    if len(value) > MAX_ROWS:
        raise EstateError(f"{label} exceeds {MAX_ROWS} rows")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise EstateError(f"{label} must be boolean")
    return value


def _int(value: Any, label: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
        raise EstateError(f"{label} must be integer in [{minimum}, {maximum}]")
    return value


def _text(value: Any, label: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or len(value) > MAX_TEXT:
        raise EstateError(f"{label} is invalid")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise EstateError(f"{label} has invalid shape")
    return value


def _optional_sha1(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or SHA1_RE.fullmatch(value) is None:
        raise EstateError(f"{label} must be null or exact 40-hex commit SHA")
    return value


def _time(value: Any, label: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise EstateError(f"{label} must be canonical UTC second text")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise EstateError(f"{label} must be canonical UTC second text") from exc


def _canon_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EstateError("trusted current time must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fresh(observed: datetime, now: datetime) -> bool:
    delta = now - observed
    return timedelta(0) <= delta <= MAX_EVIDENCE_AGE


def validate_snapshot(value: Any) -> dict[str, Any]:
    obj = _plain(value, "snapshot")
    expected = {"schema", "owner", "captured_at", "repositories"}
    if set(obj) != expected:
        raise EstateError("snapshot keys mismatch")
    if obj.get("schema") != SNAPSHOT_SCHEMA:
        raise EstateError("snapshot schema mismatch")
    owner = _text(obj.get("owner"), "snapshot.owner", pattern=REPO_RE)
    captured = _time(obj.get("captured_at"), "snapshot.captured_at")
    repos = _list(obj.get("repositories"), "snapshot.repositories")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(repos):
        row = _plain(raw, f"snapshot.repositories[{idx}]")
        keys = {"name", "visibility", "archived", "default_branch", "default_branch_sha"}
        if set(row) != keys:
            raise EstateError(f"snapshot.repositories[{idx}] keys mismatch")
        name = _text(row.get("name"), f"repo[{idx}].name", pattern=REPO_RE)
        folded = name.casefold()
        if folded in seen:
            raise EstateError(f"duplicate/case-aliased repository identity: {name}")
        seen.add(folded)
        visibility = row.get("visibility")
        if visibility not in VISIBILITY:
            raise EstateError(f"repo[{idx}].visibility invalid")
        branch = _text(row.get("default_branch"), f"repo[{idx}].default_branch", pattern=REPO_RE)
        normalized.append(
            {
                "name": name,
                "visibility": visibility,
                "archived": _bool(row.get("archived"), f"repo[{idx}].archived"),
                "default_branch": branch,
                "default_branch_sha": _optional_sha1(row.get("default_branch_sha"), f"repo[{idx}].default_branch_sha"),
            }
        )
    normalized.sort(key=lambda r: r["name"].casefold())
    return {
        "schema": SNAPSHOT_SCHEMA,
        "owner": owner,
        "captured_at": _canon_time(captured),
        "repositories": normalized,
    }


def _validate_fresh_ref(raw: Any, label: str, now: datetime, sha: str) -> dict[str, Any]:
    obj = _plain(raw, label)
    if set(obj) != {"result", "commit_sha", "observed_at", "ref"}:
        raise EstateError(f"{label} keys mismatch")
    result = _text(obj.get("result"), f"{label}.result")
    commit = _text(obj.get("commit_sha"), f"{label}.commit_sha", pattern=SHA1_RE)
    observed = _time(obj.get("observed_at"), f"{label}.observed_at")
    ref = _text(obj.get("ref"), f"{label}.ref", pattern=REF_RE)
    if commit != sha:
        raise EstateError(f"{label} is bound to a different commit")
    return {"result": result, "commit_sha": commit, "observed_at": _canon_time(observed), "ref": ref, "fresh": _fresh(observed, now)}


def validate_evidence(value: Any, now: datetime) -> dict[str, dict[str, Any]]:
    obj = _plain(value, "evidence")
    if set(obj) != {"schema", "repositories"} or obj.get("schema") != EVIDENCE_SCHEMA:
        raise EstateError("evidence schema/keys mismatch")
    rows = _list(obj.get("repositories"), "evidence.repositories")
    out: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(rows):
        row = _plain(raw, f"evidence.repositories[{idx}]")
        expected = {
            "repository", "default_branch_sha", "intent", "owner_authorized", "owner_authority_ref",
            "secret_scan", "content_classification", "content_classification_ref", "legal_ip_review", "legal_ip_ref",
            "open_work", "dependencies", "archive_authorized", "archive_authority_ref",
        }
        if set(row) != expected:
            raise EstateError(f"evidence.repositories[{idx}] keys mismatch")
        name = _text(row.get("repository"), f"evidence[{idx}].repository", pattern=REPO_RE)
        folded = name.casefold()
        if folded in out:
            raise EstateError(f"duplicate/case-aliased evidence repository: {name}")
        sha = _text(row.get("default_branch_sha"), f"evidence[{idx}].default_branch_sha", pattern=SHA1_RE)
        intent = row.get("intent")
        if intent not in INTENTS:
            raise EstateError(f"evidence[{idx}].intent invalid")
        owner_authorized = _bool(row.get("owner_authorized"), f"evidence[{idx}].owner_authorized")
        owner_ref = _text(row.get("owner_authority_ref"), f"evidence[{idx}].owner_authority_ref", pattern=REF_RE)
        secret = _validate_fresh_ref(row.get("secret_scan"), f"evidence[{idx}].secret_scan", now, sha)
        content = _text(row.get("content_classification"), f"evidence[{idx}].content_classification")
        content_ref = _text(row.get("content_classification_ref"), f"evidence[{idx}].content_classification_ref", pattern=REF_RE)
        legal = _text(row.get("legal_ip_review"), f"evidence[{idx}].legal_ip_review")
        legal_ref = _text(row.get("legal_ip_ref"), f"evidence[{idx}].legal_ip_ref", pattern=REF_RE)
        open_work = _plain(row.get("open_work"), f"evidence[{idx}].open_work")
        if set(open_work) != {"open_prs", "open_issues", "active_claims", "observed_at", "ref"}:
            raise EstateError(f"evidence[{idx}].open_work keys mismatch")
        work_seen = _time(open_work.get("observed_at"), f"evidence[{idx}].open_work.observed_at")
        open_norm = {
            "open_prs": _int(open_work.get("open_prs"), f"evidence[{idx}].open_work.open_prs"),
            "open_issues": _int(open_work.get("open_issues"), f"evidence[{idx}].open_work.open_issues"),
            "active_claims": _int(open_work.get("active_claims"), f"evidence[{idx}].open_work.active_claims"),
            "observed_at": _canon_time(work_seen),
            "ref": _text(open_work.get("ref"), f"evidence[{idx}].open_work.ref", pattern=REF_RE),
            "fresh": _fresh(work_seen, now),
        }
        deps = _plain(row.get("dependencies"), f"evidence[{idx}].dependencies")
        if set(deps) != {"consumer_count", "replacement_repository", "replacement_verified", "observed_at", "ref"}:
            raise EstateError(f"evidence[{idx}].dependencies keys mismatch")
        dep_seen = _time(deps.get("observed_at"), f"evidence[{idx}].dependencies.observed_at")
        replacement = deps.get("replacement_repository")
        if replacement is not None:
            replacement = _text(replacement, f"evidence[{idx}].dependencies.replacement_repository", pattern=REPO_RE)
        dep_norm = {
            "consumer_count": _int(deps.get("consumer_count"), f"evidence[{idx}].dependencies.consumer_count"),
            "replacement_repository": replacement,
            "replacement_verified": _bool(deps.get("replacement_verified"), f"evidence[{idx}].dependencies.replacement_verified"),
            "observed_at": _canon_time(dep_seen),
            "ref": _text(deps.get("ref"), f"evidence[{idx}].dependencies.ref", pattern=REF_RE),
            "fresh": _fresh(dep_seen, now),
        }
        archive_authorized = _bool(row.get("archive_authorized"), f"evidence[{idx}].archive_authorized")
        archive_ref = _text(row.get("archive_authority_ref"), f"evidence[{idx}].archive_authority_ref", pattern=REF_RE)
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
