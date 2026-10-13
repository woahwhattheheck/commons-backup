#!/usr/bin/env python3
"""Build or validate the public-safe Commons repository portfolio projection.

The projection is a read-only routing aid.  It keeps public repository heads
exact while reducing private repositories to aggregate capacity.  A mirror is
CURRENT only when its recorded source is the canonical head; any positive or
unknown gap fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


SCHEMA = "commons-repository-portfolio/v2"
LEGACY_SCHEMA = "commons-repository-portfolio/v1"
SOURCE_SCHEMA = "commons-repository-source/v1"
HEX = set("0123456789abcdef")


class PortfolioError(ValueError):
    """The portfolio projection is incomplete or internally inconsistent."""


def is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and set(value) <= HEX


def classify(repo: dict[str, Any], canonical_sha: str) -> str:
    role = repo.get("role")
    if role == "CANONICAL":
        if repo.get("head_sha") != canonical_sha:
            raise PortfolioError("canonical repository head differs from source_main_sha")
        return "CANONICAL"
    if role == "MIRROR":
        source_sha = repo.get("recorded_source_sha")
        gap = repo.get("commits_behind")
        if not is_sha(source_sha):
            return "MIRROR_UNVERIFIED"
        if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
            return "MIRROR_UNVERIFIED"
        if source_sha == canonical_sha and gap == 0:
            return "CURRENT_MIRROR"
        if gap > 0:
            return "STALE_MIRROR"
        return "MIRROR_INCONSISTENT"
    if role in {"HELP_REFERENCE", "SPRINT_REFERENCE", "PUBLIC_REFERENCE"}:
        if repo.get("head_state") == "EMPTY":
            return "EMPTY_REPOSITORY"
        if repo.get("head_state") == "UNAVAILABLE":
            return "HEAD_UNAVAILABLE"
        return "REFERENCE"
    raise PortfolioError(f"unsupported public repository role: {role!r}")


def observed_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
        return parsed
    except (AttributeError, TypeError, ValueError) as exc:
        raise PortfolioError("observation time must be an ISO timestamp with timezone") from exc


def summarize(repos: list[dict[str, Any]], private_count: int, *, legacy: bool = False) -> dict[str, int]:
    statuses: dict[str, int] = {}
    for repo in repos:
        status = repo["condition"]
        statuses[status] = statuses.get(status, 0) + 1
    result = {
        "accessible_repositories": len(repos) + private_count,
        "public_repositories": len(repos),
        "private_repositories": private_count,
        "canonical_repositories": statuses.get("CANONICAL", 0),
        "current_mirrors": statuses.get("CURRENT_MIRROR", 0),
        "stale_mirrors": statuses.get("STALE_MIRROR", 0),
        "unverified_mirrors": statuses.get("MIRROR_UNVERIFIED", 0)
        + statuses.get("MIRROR_INCONSISTENT", 0),
        "reference_repositories": statuses.get("REFERENCE", 0),
    }
    if not legacy:
        result.update(empty_repositories=sum(row.get("head_state") == "EMPTY" for row in repos),
                      unavailable_heads=sum(row.get("head_state") == "UNAVAILABLE" for row in repos))
    return result


def validate(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("schema") not in {SCHEMA, LEGACY_SCHEMA}:
        raise PortfolioError(f"snapshot is not {SCHEMA} or {LEGACY_SCHEMA}")
    legacy = snapshot["schema"] == LEGACY_SCHEMA
    observed_time(snapshot.get("observed_at"))
    canonical_sha = snapshot.get("source_main_sha")
    if not is_sha(canonical_sha):
        raise PortfolioError("source_main_sha is not a full Git SHA")

    repos = snapshot.get("public_repositories")
    if not isinstance(repos, list) or not repos:
        raise PortfolioError("public_repositories must be a non-empty list")
    names: set[str] = set()
    canonical = 0
    for repo in repos:
        if not isinstance(repo, dict):
            raise PortfolioError("public repository row must be an object")
        name = repo.get("full_name")
        if not isinstance(name, str) or "/" not in name or name in names:
            raise PortfolioError(f"invalid or duplicate public repository: {name!r}")
        names.add(name)
        if repo.get("visibility") != "public":
            raise PortfolioError(f"public row is not public: {name}")
        state = repo.get("head_state", "PRESENT" if legacy else None)
        if state not in {"PRESENT", "EMPTY", "UNAVAILABLE"}:
            raise PortfolioError(f"invalid head_state: {name}")
        if state == "PRESENT" and not is_sha(repo.get("head_sha")):
            raise PortfolioError(f"public row lacks an exact head SHA: {name}")
        if state != "PRESENT" and repo.get("head_sha") is not None:
            raise PortfolioError(f"unobserved head must not retain an old SHA: {name}")
        if not legacy:
            if not isinstance(repo.get("default_branch"), str) or not repo["default_branch"]:
                raise PortfolioError(f"default branch is missing: {name}")
            observed_time(repo.get("head_observed_at"))
            source_url = f"https://api.github.com/repos/{name}/git/ref/heads/{quote(repo['default_branch'], safe='')}"
            if repo.get("head_source") != source_url:
                raise PortfolioError(f"head source does not identify the recorded default branch: {name}")
            if state == "PRESENT" and repo.get("head_http_status") != 200:
                raise PortfolioError(f"present head lacks a successful source read: {name}")
            if state == "EMPTY" and repo.get("head_http_status") != 409:
                raise PortfolioError(f"empty repository lacks an explicit empty-repository response: {name}")
        if repo.get("role") == "CANONICAL":
            canonical += 1
        want = classify(repo, canonical_sha)
        if repo.get("condition") != want:
            raise PortfolioError(f"condition drift for {name}: want {want}")

    if canonical != 1:
        raise PortfolioError("portfolio must contain exactly one canonical repository")

    private = snapshot.get("private_aggregate")
    if not isinstance(private, dict):
        raise PortfolioError("private_aggregate must be an object")
    private_count = private.get("accessible_repository_count")
    if not isinstance(private_count, int) or isinstance(private_count, bool) or private_count < 0:
        raise PortfolioError("private accessible_repository_count must be a non-negative integer")
    forbidden = {"full_name", "head_sha", "default_branch", "commit_title", "url"}
    leaked = sorted(forbidden.intersection(private))
    if leaked:
        raise PortfolioError("private aggregate leaks repository detail: " + ", ".join(leaked))
    if private.get("details_persisted") is not False:
        raise PortfolioError("private details_persisted must be false")

    summary = snapshot.get("summary")
    expected = summarize(repos, private_count, legacy=legacy)
    if summary != expected:
        raise PortfolioError(f"summary drift: want {expected!r}")
    return expected


def build(source: dict[str, Any], previous: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Project a captured observation without network reads or private identifiers."""
    validate(previous)
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise PortfolioError(f"source is not {SOURCE_SCHEMA}")
    if observed_time(source.get("observed_at")) < observed_time(previous["observed_at"]):
        raise PortfolioError("source observation predates the previous snapshot; keep the previous snapshot")
    listing = source.get("listing", {})
    if not isinstance(listing, dict) or listing.get("complete") is not True:
        raise PortfolioError("source listing is incomplete; keep the previous snapshot")
    counts, offsets, size = listing.get("page_counts"), listing.get("page_offsets"), listing.get("page_size")
    if (not isinstance(size, int) or isinstance(size, bool) or size <= 0
            or not isinstance(counts, list) or not counts or not isinstance(offsets, list)
            or offsets != [i * size for i in range(len(counts))]
            or any(not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > size for n in counts)
            or any(n < size and any(counts[i + 1:]) for i, n in enumerate(counts))
            or counts[-1] >= size):
        raise PortfolioError("source pagination does not demonstrate a complete listing")
    public = source.get("public_repositories")
    private_count = source.get("private_repository_count")
    if not isinstance(public, list) or not isinstance(private_count, int) or isinstance(private_count, bool) or private_count < 0:
        raise PortfolioError("source must include public rows and a non-negative private count")
    if len(public) + private_count != sum(counts):
        raise PortfolioError("source rows do not match the listing count")
    old = {row["full_name"]: row for row in previous["public_repositories"]}
    canonical = next(row["full_name"] for row in previous["public_repositories"] if row["role"] == "CANONICAL")
    rows = []
    for item in public:
        if not isinstance(item, dict) or item.get("visibility") != "public":
            raise PortfolioError("source public rows must explicitly identify public repositories")
        row = {key: item.get(key) for key in (
            "full_name", "visibility", "default_branch", "archived", "head_state",
            "head_sha", "head_observed_at", "head_source", "head_http_status")}
        if not isinstance(row["full_name"], str):
            raise PortfolioError("source repository name must be a string")
        if row["head_state"] == "EMPTY" and item.get("head_message") != "Git Repository is empty.":
            raise PortfolioError(f"source lacks the explicit empty-repository response: {row['full_name']}")
        prior = old.get(row["full_name"], {})
        # Listing and head reads are separate observations. A new listing
        # timestamp cannot make an older captured ref read current again.
        if (prior.get("head_observed_at") is not None
                and observed_time(row["head_observed_at"]) < observed_time(prior["head_observed_at"])):
            raise PortfolioError(f"head observation predates the previous snapshot: {row['full_name']}")
        row["role"] = prior.get("role", "PUBLIC_REFERENCE")
        if "purpose" in prior:
            row["purpose"] = prior["purpose"]
        if row["role"] == "MIRROR":
            # A fresh branch head alone says nothing about mirror completeness.
            row.update(recorded_source_sha=None, commits_behind=None)
        rows.append(row)
    canonical_rows = [row for row in rows if row["full_name"] == canonical]
    if len(canonical_rows) != 1 or canonical_rows[0]["head_state"] != "PRESENT":
        raise PortfolioError("canonical head was not observed; keep the previous snapshot")
    canonical_sha = canonical_rows[0]["head_sha"]
    rows.sort(key=lambda row: (row["role"] != "CANONICAL", row["full_name"].casefold()))
    for row in rows:
        row["condition"] = classify(row, canonical_sha)
    snapshot = {
        "schema": SCHEMA,
        "observed_at": source.get("observed_at"),
        "source_main_sha": canonical_sha,
        "authority": "AUTHENTICATED_GITHUB_READ; PUBLIC_DETAILS_ONLY; PRIVATE_CAPACITY_AGGREGATE_ONLY",
        "scope": {"provider": listing.get("provider"), "affiliation": listing.get("affiliation"),
                  "listing_complete": True},
        "public_repositories": rows,
        "private_aggregate": {"accessible_repository_count": private_count, "details_persisted": False,
                              "head_state": "REDACTED_NOT_PERSISTED"},
        "summary": summarize(rows, private_count),
        "evidence": {"source_sha256": source_sha256,
                     "source_schema": SOURCE_SCHEMA,
                     "commons_head": f"https://github.com/{canonical}/commit/{canonical_sha}"},
        "truth": {"canonical_head_observed_at": canonical_rows[0]["head_observed_at"],
                  "backup_is_current": "NOT_VERIFIED", "private_repository_details_persisted": False},
        "rate_plan_boundary": previous.get("rate_plan_boundary", "Repository access does not prove deployment, acceptance or payment."),
    }
    validate(snapshot)
    return snapshot


def write_json(path: Path, value: dict[str, Any]) -> None:
    """A failed refresh leaves the last complete projection in place."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(json.dumps(value, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--build-from", type=Path, help="public-only captured source; existing snapshot supplies routing roles")
    parser.add_argument("--output", type=Path, help="write refreshed projection (requires --build-from)")
    parser.add_argument("--max-age-hours", type=float, help="report stale observations with exit 2")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.output and not args.build_from:
            raise PortfolioError("--output requires --build-from")
        if args.build_from:
            source_bytes = args.build_from.read_bytes()
            snapshot = build(json.loads(source_bytes), snapshot, hashlib.sha256(source_bytes).hexdigest())
        summary = validate(snapshot)
        if args.max_age_hours is not None:
            if not math.isfinite(args.max_age_hours) or args.max_age_hours < 0:
                raise PortfolioError("--max-age-hours must be non-negative")
            observed = [observed_time(snapshot["observed_at"])]
            observed.extend(observed_time(row["head_observed_at"]) for row in snapshot["public_repositories"] if "head_observed_at" in row)
            now = datetime.now(timezone.utc)
            if any((now - stamp).total_seconds() < 0 for stamp in observed):
                raise PortfolioError("observation is in the future")
            if max((now - stamp).total_seconds() for stamp in observed) > args.max_age_hours * 3600:
                raise PortfolioError("repository observation exceeds --max-age-hours; refresh the source")
        if args.output:
            write_json(args.output, snapshot)
        elif args.build_from:
            print(json.dumps(snapshot, indent=2))
            return 0
    except (OSError, UnicodeError, json.JSONDecodeError, PortfolioError) as exc:
        print(f"repository-portfolio: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
