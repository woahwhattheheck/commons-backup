#!/usr/bin/env python3
"""Fail-open stale-demand authority auditor.

Consumes explicit demand metadata plus a connector/operator supplied GitHub authority
snapshot. It never queries or mutates Slack/GitHub itself. Retirement decisions require
repository evidence pinned to the same commit that was observed as current authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

SCHEMA = "demand-authority-audit/v1"
REPORT_SCHEMA = "demand-authority-audit-report/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/issues/([1-9][0-9]*)/?$")
PR_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/pull/([1-9][0-9]*)/?$")


class EvidenceError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _obj(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{name} must be an object")
    return value


def _arr(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{name} must be an array")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{name} must be non-empty text")
    return value.strip()


def _repo(value: Any, name: str) -> str:
    text = _text(value, name)
    if not REPO.fullmatch(text):
        raise EvidenceError(f"{name} must be owner/repository")
    return text


def _commit(value: Any, name: str) -> str:
    text = _text(value, name).lower()
    if not HEX40.fullmatch(text):
        raise EvidenceError(f"{name} must be a full 40-hex SHA")
    return text


def _path(value: Any, name: str) -> str:
    text = _text(value, name)
    if text.startswith("/") or "\\" in text or "\x00" in text:
        raise EvidenceError(f"{name} must be repository-relative POSIX path")
    if any(part in {"", ".", ".."} for part in text.split("/")):
        raise EvidenceError(f"{name} contains unsafe path segment")
    return text


def _unique_paths(values: Sequence[Any], name: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for idx, value in enumerate(values):
        path = _path(value, f"{name}[{idx}]")
        if path in seen:
            raise EvidenceError(f"{name} contains duplicate {path!r}")
        seen.add(path)
        out.append(path)
    return out


def _source(value: Any, repo: str, name: str, evidence_commit: str | None = None) -> Dict[str, str]:
    src = _obj(value, name)
    kind = _text(src.get("kind"), f"{name}.kind")
    locator = _text(src.get("locator"), f"{name}.locator")
    if kind == "github_issue":
        match = ISSUE_URL.fullmatch(locator)
        if not match or match.group(1).lower() != repo.lower():
            raise EvidenceError(f"{name}.locator must be an issue URL in {repo}")
    elif kind == "github_pr":
        match = PR_URL.fullmatch(locator)
        if not match or match.group(1).lower() != repo.lower():
            raise EvidenceError(f"{name}.locator must be a PR URL in {repo}")
    elif kind == "repository_artifact":
        _path(locator, f"{name}.locator")
        if evidence_commit is None:
            raise EvidenceError(f"{name} repository artifact requires an evidence commit")
        source_commit = _commit(src.get("commit"), f"{name}.commit")
        if source_commit != evidence_commit:
            raise EvidenceError(f"{name}.commit must equal the evidence commit")
        return {"kind": kind, "locator": locator, "commit": source_commit}
    else:
        raise EvidenceError(f"{name}.kind is not GitHub/repository authority")
    return {"kind": kind, "locator": locator}


def _path_evidence(raw: Any, repo: str, evidence_commit: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    by_path: Dict[str, Dict[str, Any]] = {}
    conflicts: List[str] = []
    for idx, raw_row in enumerate(_arr(raw, "authority.paths")):
        row = _obj(raw_row, f"authority.paths[{idx}]")
        path = _path(row.get("path"), f"authority.paths[{idx}].path")
        row_repo = _repo(row.get("repo"), f"authority.paths[{idx}].repo")
        row_commit = _commit(row.get("commit"), f"authority.paths[{idx}].commit")
        present = row.get("present")
        if not isinstance(present, bool):
            raise EvidenceError(f"authority.paths[{idx}].present must be boolean")
        normalized: Dict[str, Any] = {"path": path, "repo": row_repo, "commit": row_commit, "present": present}
        if present:
            normalized["blob_sha"] = _commit(row.get("blob_sha"), f"authority.paths[{idx}].blob_sha")
        elif row.get("blob_sha") not in (None, ""):
            raise EvidenceError(f"authority.paths[{idx}].blob_sha cannot accompany present=false")
        if row_repo.lower() != repo.lower():
            conflicts.append(f"PATH_REPO_MISMATCH:{path}")
        if row_commit != evidence_commit:
            conflicts.append(f"PATH_COMMIT_MISMATCH:{path}")
        if path in by_path:
            conflicts.append(f"PATH_DUPLICATE:{path}" if by_path[path] == normalized else f"PATH_CONFLICT:{path}")
        else:
            by_path[path] = normalized
    return by_path, sorted(set(conflicts))


def _carrier(raw: Any, repo: str) -> Tuple[Dict[str, Any] | None, List[str]]:
    if raw in (None, {}):
        return None, []
    row = _obj(raw, "authority.carrier")
    row_repo = _repo(row.get("repo"), "authority.carrier.repo")
    number = row.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise EvidenceError("authority.carrier.number must be positive integer")
    state = _text(row.get("state"), "authority.carrier.state").upper()
    if state not in {"OPEN", "CLOSED", "MERGED"}:
        raise EvidenceError("authority.carrier.state must be OPEN, CLOSED, or MERGED")
    head_sha = _commit(row.get("head_sha"), "authority.carrier.head_sha")
    merge_sha = None if row.get("merge_commit_sha") in (None, "") else _commit(row.get("merge_commit_sha"), "authority.carrier.merge_commit_sha")
    ancestor = row.get("merge_commit_is_ancestor_of_evidence_commit")
    if not isinstance(ancestor, bool):
        raise EvidenceError("authority.carrier.merge_commit_is_ancestor_of_evidence_commit must be boolean")
    source = _source(row.get("source"), repo, "authority.carrier.source")
    conflicts = []
    if row_repo.lower() != repo.lower():
        conflicts.append("CARRIER_REPO_MISMATCH")
    if state == "MERGED" and merge_sha is None:
        conflicts.append("MERGED_CARRIER_MISSING_MERGE_COMMIT")
    if state != "MERGED" and ancestor:
        conflicts.append("NONMERGED_CARRIER_MARKED_ANCESTOR")
    return {
        "repo": row_repo,
        "number": number,
        "state": state,
        "head_sha": head_sha,
        "merge_commit_sha": merge_sha,
        "merge_commit_is_ancestor_of_evidence_commit": ancestor,
        "source": source,
    }, sorted(set(conflicts))


def _supersession(raw: Any, repo: str, evidence_commit: str) -> Dict[str, Any] | None:
    if raw in (None, {}):
        return None
    row = _obj(raw, "authority.superseded_by")
    status = _text(row.get("status"), "authority.superseded_by.status").upper()
    if status not in {"LANDED", "MERGED"}:
        raise EvidenceError("authority.superseded_by.status must be LANDED or MERGED")
    ancestor = row.get("commit_is_ancestor_of_evidence_commit")
    if not isinstance(ancestor, bool):
        raise EvidenceError("authority.superseded_by.commit_is_ancestor_of_evidence_commit must be boolean")
    return {
        "operation_id": _text(row.get("operation_id"), "authority.superseded_by.operation_id"),
        "status": status,
        "commit": _commit(row.get("commit"), "authority.superseded_by.commit"),
        "commit_is_ancestor_of_evidence_commit": ancestor,
        "source": _source(row.get("source"), repo, "authority.superseded_by.source", evidence_commit),
    }


def _fence(raw: Any, repo: str, evidence_commit: str) -> Dict[str, Any] | None:
    if raw in (None, {}):
        return None
    row = _obj(raw, "authority.fence")
    active = row.get("active")
    if not isinstance(active, bool):
        raise EvidenceError("authority.fence.active must be boolean")
    reason = _text(row.get("reason"), "authority.fence.reason")
    allowed = {"SOURCE_BYTES_LOST", "DO_NOT_RECONSTRUCT", "OWNER_HOLD", "EXTERNAL_AUTHORITY_BLOCKED", "TERMINAL_NOT_APPLICABLE"}
    if active and reason not in allowed:
        raise EvidenceError(f"authority.fence.reason must be one of {sorted(allowed)}")
    return {"active": active, "reason": reason, "source": _source(row.get("source"), repo, "authority.fence.source", evidence_commit)}


def _reason(code: str, details: Iterable[str] = ()) -> Dict[str, Any]:
    row: Dict[str, Any] = {"code": code}
    details = sorted(set(details))
    if details:
        row["details"] = details
    return row


def audit(envelope: Mapping[str, Any]) -> Dict[str, Any]:
    root = _obj(envelope, "envelope")
    if root.get("schema") != SCHEMA:
        raise EvidenceError(f"schema must equal {SCHEMA!r}")
    demand = _obj(root.get("demand"), "demand")
    authority = _obj(root.get("authority"), "authority")
    demand_id = _text(demand.get("demand_id"), "demand.demand_id")
    advertised_state = _text(demand.get("advertised_state"), "demand.advertised_state").upper()
    repo = _repo(demand.get("repo"), "demand.repo")
    authority_repo = _repo(authority.get("repo"), "authority.repo")
    observed_ref = _text(authority.get("observed_ref"), "authority.observed_ref")
    observed_commit = _commit(authority.get("observed_commit"), "authority.observed_commit")
    evidence_commit = _commit(authority.get("evidence_commit"), "authority.evidence_commit")
    required_paths = _unique_paths(_arr(demand.get("required_paths", []), "demand.required_paths"), "demand.required_paths")

    conflicts: List[str] = []
    if authority_repo.lower() != repo.lower():
        conflicts.append("AUTHORITY_REPO_MISMATCH")
    stale = evidence_commit != observed_commit
    paths, path_conflicts = _path_evidence(authority.get("paths", []), repo, evidence_commit)
    conflicts.extend(path_conflicts)
    carrier, carrier_conflicts = _carrier(authority.get("carrier"), repo)
    conflicts.extend(carrier_conflicts)
    superseded = _supersession(authority.get("superseded_by"), repo, evidence_commit)
    fence = _fence(authority.get("fence"), repo, evidence_commit)

    missing = [p for p in required_paths if p not in paths]
    absent = [p for p in required_paths if p in paths and not paths[p]["present"]]
    present = [p for p in required_paths if p in paths and paths[p]["present"]]
    decision = "KEEP_OPEN"
    reasons: List[Dict[str, Any]] = []

    if conflicts:
        decision = "CONFLICT"
        reasons.append(_reason("CONTRADICTORY_AUTHORITY", conflicts))
    elif stale:
        reasons.append(_reason("STALE_AUTHORITY_SNAPSHOT", [f"evidence_commit={evidence_commit}", f"observed_commit={observed_commit}"]))
    elif fence and fence["active"]:
        decision = "FENCED"
        reasons.append(_reason("DURABLE_FENCE", [fence["reason"]]))
    elif superseded and superseded["commit_is_ancestor_of_evidence_commit"]:
        decision = "SUPERSEDED"
        reasons.append(_reason("LANDED_SUPERSEDING_CARRIER", [superseded["operation_id"], superseded["commit"]]))
    elif superseded:
        reasons.append(_reason("SUPERSESSION_NOT_ON_OBSERVED_AUTHORITY", [superseded["operation_id"], superseded["commit"]]))
    elif carrier and carrier["state"] == "MERGED" and carrier["merge_commit_sha"] and carrier["merge_commit_is_ancestor_of_evidence_commit"] and not missing and not absent and len(present) == len(required_paths):
        decision = "LANDED"
        reasons.append(_reason("MERGED_CARRIER_AND_REQUIRED_PATHS_PRESENT", [f"pr={carrier['number']}", carrier["merge_commit_sha"]]))
    else:
        if not carrier:
            reasons.append(_reason("NO_MERGED_CARRIER_AUTHORITY"))
        elif carrier["state"] != "MERGED":
            reasons.append(_reason("CARRIER_NOT_MERGED", [carrier["state"]]))
        elif not carrier["merge_commit_is_ancestor_of_evidence_commit"]:
            reasons.append(_reason("MERGE_NOT_PROVEN_ON_OBSERVED_AUTHORITY"))
        if missing:
            reasons.append(_reason("MISSING_PATH_EVIDENCE", missing))
        if absent:
            reasons.append(_reason("REQUIRED_PATH_ABSENT", absent))
    if advertised_state != "OPEN":
        reasons.append(_reason("ADVERTISED_STATE_NOT_OPEN", [advertised_state]))

    recommendation = {
        "KEEP_OPEN": "retain demand; collect current GitHub authority before any retirement",
        "LANDED": "retire stale OPEN demand as landed; do not rebuild",
        "SUPERSEDED": "retire stale OPEN demand as superseded; use canonical successor",
        "FENCED": "retire from build queue while durable fence remains active; do not reconstruct",
        "CONFLICT": "retain demand and resolve contradictory authority before any mutation",
    }[decision]
    required_set = set(required_paths)
    core = {
        "schema": REPORT_SCHEMA,
        "decision": decision,
        "recommendation": recommendation,
        "demand": {"demand_id": demand_id, "advertised_state": advertised_state, "repo": repo, "required_paths": required_paths},
        "authority": {
            "repo": authority_repo,
            "observed_ref": observed_ref,
            "observed_commit": observed_commit,
            "evidence_commit": evidence_commit,
            "carrier": carrier,
            "superseded_by": superseded,
            "fence": fence,
            "required_path_evidence": [paths[p] for p in sorted(paths) if p in required_set],
        },
        "reasons": reasons,
        "input_sha256": _sha256(root),
        "mutations_performed": 0,
    }
    report = dict(core)
    report["receipt_sha256"] = _sha256(core)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-open stale-demand authority auditor")
    parser.add_argument("evidence_json", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        report = audit(payload)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        parser.exit(2, f"demand-authority-audit: {exc}\n")
    if args.pretty:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(_canon(report).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
