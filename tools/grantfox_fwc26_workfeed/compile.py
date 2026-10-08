from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

REQUIRED_LABELS = {
    "grantfox oss",
    "maybe rewarded",
    "official campaign | fwc26",
}

COMMAND_PREFIXES = (
    "npm ",
    "pnpm ",
    "yarn ",
    "cargo ",
    "pytest",
    "python -m pytest",
    "go test",
    "forge ",
    "npx ",
)

CASH_RE = re.compile(
    r"(?<![\w])(?:\$\s?\d[\d,]*(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s*(?:USDC|USD|XLM))(?![\w])",
    re.IGNORECASE,
)

CLAIM_HINT_RE = re.compile(
    r"\b(comment|apply|claim|request assignment|wait for (?:a )?maintainer|wait for assignment)\b",
    re.IGNORECASE,
)

SECURITY_TERMS = (
    "auth",
    "authorization",
    "security",
    "multisig",
    "multi-sig",
    "settlement",
    "escrow",
    "wallet",
    "payment",
    "payout",
    "admin",
    "contract",
    "soroban",
    "solidity",
    "vrf",
    "jury",
    "slashing",
    "vault",
    "secret",
    "keypair",
    "signature",
    "private key",
    "seed phrase",
    "redaction",
    "fund-safety",
)


class WorkfeedError(ValueError):
    """Input is not safe enough to compile into a swarm workfeed."""


@dataclass(frozen=True)
class Candidate:
    key: str
    repository: str
    number: int
    title: str
    url: str
    state: str
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    observed_claimants: tuple[str, ...]
    open_pull_requests: tuple[str, ...]
    coordination_owners: tuple[str, ...]
    observed_at: str | None
    repository_archived: bool | None
    campaign_active: bool | None
    status: str
    reward_class: str
    explicit_reward_mentions: tuple[str, ...]
    claim_required: bool
    security_sensitive: bool
    commands: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "repository": self.repository,
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "state": self.state,
            "labels": list(self.labels),
            "assignees": list(self.assignees),
            "observed_claimants": list(self.observed_claimants),
            "open_pull_requests": list(self.open_pull_requests),
            "coordination_owners": list(self.coordination_owners),
            "observed_at": self.observed_at,
            "repository_archived": self.repository_archived,
            "campaign_active": self.campaign_active,
            "status": self.status,
            "reward_class": self.reward_class,
            "explicit_reward_mentions": list(self.explicit_reward_mentions),
            "claim_required": self.claim_required,
            "security_sensitive": self.security_sensitive,
            "commands": list(self.commands),
            "reason": self.reason,
        }


def _norm_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped[0] == "[":
        value = json.loads(text)
        if not isinstance(value, list):
            raise WorkfeedError("JSON input must be an array of issue objects")
        return value
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkfeedError(f"invalid JSONL on line {line_no}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise WorkfeedError(f"JSONL line {line_no} must be an object")
        records.append(value)
    return records


def _repo_number(record: dict[str, Any]) -> tuple[str, int]:
    repo = record.get("repository") or record.get("repo")
    number = record.get("number", record.get("issue_number"))
    if not isinstance(repo, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo
    ):
        raise WorkfeedError("each issue requires repository='owner/name'")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise WorkfeedError(f"{repo}: issue number must be a positive integer")
    return repo, number


def _issue_url(value: Any, repo: str, number: int) -> str:
    key = f"{repo}#{number}"
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        raise WorkfeedError(f"{key}: canonical GitHub issue URL is required")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise WorkfeedError(f"{key}: canonical GitHub issue URL is required") from exc
    match = re.fullmatch(r"/([^/]+/[^/]+)/issues/([1-9][0-9]*)/?", parsed.path)
    if (
        parsed.scheme not in {"https", "http"}
        or parsed.netloc.lower() != "github.com"
        or match is None
        or match[1].lower() != repo.lower()
        or match[2] != str(number)
    ):
        raise WorkfeedError(f"{key}: GitHub issue URL must match repository and number")
    # Retain display spelling while removing fragments/query strings and
    # normalizing HTTP/trailing slash variants to the issue's canonical URL.
    return f"https://github.com/{repo}/issues/{number}"


def _labels(record: dict[str, Any]) -> tuple[str, ...]:
    raw = record.get("labels") or []
    if not isinstance(raw, list):
        raise WorkfeedError("labels must be a list")
    labels: list[str] = []
    for item in raw:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            labels.append(item["name"])
        else:
            raise WorkfeedError("labels entries must be strings or {'name': string}")
    return tuple(labels)


def _assignees(record: dict[str, Any]) -> tuple[str, ...]:
    raw = record.get("assignees") or []
    if not isinstance(raw, list):
        raise WorkfeedError("assignees must be a list")
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and isinstance(item.get("login"), str):
            result.append(item["login"])
        else:
            raise WorkfeedError("assignees entries must be strings or {'login': string}")
    return tuple(result)


# Only official GrantFox bot posts can establish a campaign assignment. A
# GitHub search result with assignees=[] is not sufficient evidence of vacancy.
BOT_ASSIGNMENT_RE = re.compile(
    r"@([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)\s+has been assigned to this issue\b",
    re.IGNORECASE,
)


def _campaign_bot_assignees(record: dict[str, Any]) -> tuple[str, ...]:
    # Raw GitHub issue comments, oldest to newest when possible. This does not
    # treat ordinary contributor interest or pasted bot text as an assignment.
    raw = record.get("issue_comments") or []
    if not isinstance(raw, list):
        raise WorkfeedError("issue_comments must be a list")
    result: list[str] = []
    for comment in raw:
        if not isinstance(comment, dict):
            raise WorkfeedError("issue_comments entries must be GitHub comment objects")
        user = comment.get("user")
        if isinstance(user, dict):
            user = user.get("login")
        if not isinstance(user, str) or user.lower() != "grantfox-oss[bot]":
            continue
        body = comment.get("body")
        if not isinstance(body, str):
            continue
        match = BOT_ASSIGNMENT_RE.search(body)
        if match and match.group(1).lower() not in {name.lower() for name in result}:
            result.append(match.group(1))
    return tuple(result)


def _observed_claimants(record: dict[str, Any]) -> tuple[str, ...]:
    raw = record.get("claimant_comments") or record.get("claim_comments") or []
    if not isinstance(raw, list):
        raise WorkfeedError("claimant_comments must be a list")
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            claimant = item.strip()
        elif isinstance(item, dict):
            user = item.get("user")
            if isinstance(user, dict):
                user = user.get("login")
            claimant = str(user or item.get("login") or "").strip()
        else:
            raise WorkfeedError("claimant_comments entries must be strings or objects")
        if claimant and claimant not in result:
            result.append(claimant)
    return tuple(result)


def _open_pull_requests(record: dict[str, Any]) -> tuple[str, ...]:
    raw = record.get("open_pull_requests") or record.get("open_prs") or []
    if not isinstance(raw, list):
        raise WorkfeedError("open_pull_requests must be a list")
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(item.get("url") or item.get("html_url") or item.get("number") or "").strip()
        else:
            raise WorkfeedError("open_pull_requests entries must be strings or objects")
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _coordination_owners(record: dict[str, Any]) -> tuple[str, ...]:
    raw = record.get("coordination_claims") or record.get("swarm_claims") or []
    if not isinstance(raw, list):
        raise WorkfeedError("coordination_claims must be a list")
    result: list[str] = []
    for item in raw:
        if isinstance(item, str):
            owner = item.strip()
        elif isinstance(item, dict):
            owner = str(item.get("owner") or item.get("session") or item.get("user") or "").strip()
        else:
            raise WorkfeedError("coordination_claims entries must be strings or objects")
        if owner and owner not in result:
            result.append(owner)
    return tuple(result)


def _parse_iso8601(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise WorkfeedError(f"{field} must be an ISO-8601 timestamp string")
    text = value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WorkfeedError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise WorkfeedError(f"{field} must include a timezone offset")
    return parsed


def _commands(body: str) -> tuple[str, ...]:
    found: list[str] = []
    for command in re.findall(r"`([^`\n]+)`", body):
        normalized = command.strip()
        lower = normalized.lower()
        if any(lower.startswith(prefix) for prefix in COMMAND_PREFIXES):
            if normalized not in found:
                found.append(normalized)
    return tuple(found)


def classify(
    record: dict[str, Any], *, fresh_after: str | None = None, require_active_campaign: bool = False
) -> Candidate:
    repo, number = _repo_number(record)
    key = f"{repo}#{number}"
    title = record.get("title")
    url = record.get("url") or record.get("html_url") or record.get("display_url")
    state = str(record.get("state") or "open").lower()
    body = str(record.get("body") or "")
    labels = _labels(record)
    # Preserve native assignees and official FWC26 bot-assignment receipts.
    assignees = tuple(dict.fromkeys((*_assignees(record), *_campaign_bot_assignees(record))))
    observed_claimants = _observed_claimants(record)
    open_pull_requests = _open_pull_requests(record)
    coordination_owners = _coordination_owners(record)
    archive_fields = [name for name in ("repository_archived", "repo_archived") if name in record]
    for name in archive_fields:
        if record[name] is not None and type(record[name]) is not bool:
            raise WorkfeedError(f"{key}: {name} must be a boolean or null")
    if len(archive_fields) == 2 and record["repository_archived"] is not record["repo_archived"]:
        raise WorkfeedError(f"{key}: conflicting repository archive evidence")
    repository_archived = record[archive_fields[0]] if archive_fields else None
    campaign_active = record.get("campaign_active")
    if campaign_active is not None and type(campaign_active) is not bool:
        raise WorkfeedError(f"{key}: campaign_active must be a boolean or null")
    observed_at_value = record.get("observed_at", record.get("snapshot_observed_at"))
    observed_at_dt = _parse_iso8601(observed_at_value, f"{key}: observed_at")
    fresh_after_dt = _parse_iso8601(fresh_after, "fresh_after") if fresh_after else None
    stale_evidence = fresh_after_dt is not None and (
        observed_at_dt is None or observed_at_dt < fresh_after_dt
    )

    if not isinstance(title, str) or not title.strip():
        raise WorkfeedError(f"{key}: title is required")
    url = _issue_url(url, repo, number)

    normalized_labels = {_norm_label(x) for x in labels}
    missing = REQUIRED_LABELS - normalized_labels

    explicit_mentions = tuple(dict.fromkeys(m.group(0).strip() for m in CASH_RE.finditer(body)))
    if explicit_mentions:
        reward_class = "EXPLICIT_AMOUNT_MENTIONED"
    elif "may be rewarded" in body.lower() or "maybe rewarded" in normalized_labels:
        reward_class = "DISCRETIONARY_CAMPAIGN_REWARD"
    else:
        reward_class = "NO_REWARD_EVIDENCE"

    claim_required = bool(CLAIM_HINT_RE.search(body))
    security_sensitive = any(term in f"{title}\n{body}".lower() for term in SECURITY_TERMS)

    if state != "open":
        status = "INELIGIBLE"
        reason = f"issue state is {state}"
    elif missing:
        status = "INELIGIBLE"
        reason = "missing required campaign labels: " + ", ".join(sorted(missing))
    elif repository_archived is True:
        status = "REPOSITORY_ARCHIVED"
        reason = "repository is archived and cannot accept new pull requests"
    elif stale_evidence:
        status = "STALE_EVIDENCE"
        if observed_at_dt is None:
            reason = f"snapshot has no observed_at; freshness floor is {fresh_after}"
        else:
            reason = f"snapshot observed_at {observed_at_value} is older than freshness floor {fresh_after}"
    elif assignees:
        status = "ASSIGNED"
        reason = "already assigned to: " + ", ".join(assignees)
    elif observed_claimants or open_pull_requests:
        status = "CLAIMED_OR_PR_OPEN"
        pieces: list[str] = []
        if observed_claimants:
            pieces.append("observed claimant(s): " + ", ".join(observed_claimants))
        if open_pull_requests:
            pieces.append("open PR(s): " + ", ".join(open_pull_requests))
        reason = "; ".join(pieces)
    elif coordination_owners:
        status = "SWARM_TAKEN"
        reason = "active swarm coordination owner(s): " + ", ".join(coordination_owners)
    elif campaign_active is False:
        status = "CAMPAIGN_INACTIVE"
        reason = "provided campaign activity evidence says the sponsor campaign is inactive"
    elif require_active_campaign and campaign_active is not True:
        status = "CAMPAIGN_UNVERIFIED"
        reason = "active sponsor campaign evidence is required, but campaign_active is unknown"
    elif claim_required:
        status = "CLAIM_REQUIRED"
        reason = "issue text describes an application/assignment step"
    else:
        status = "READY"
        reason = "open, campaign-labelled, and unassigned"

    return Candidate(
        key=key,
        repository=repo,
        number=number,
        title=title.strip(),
        url=url,
        state=state,
        labels=labels,
        assignees=assignees,
        observed_claimants=observed_claimants,
        open_pull_requests=open_pull_requests,
        coordination_owners=coordination_owners,
        observed_at=str(observed_at_value) if observed_at_value not in (None, "") else None,
        repository_archived=repository_archived,
        campaign_active=campaign_active,
        status=status,
        reward_class=reward_class,
        explicit_reward_mentions=explicit_mentions,
        claim_required=claim_required,
        security_sensitive=security_sensitive,
        commands=_commands(body),
        reason=reason,
    )


def compile_records(
    records: Iterable[dict[str, Any]], *, fresh_after: str | None = None,
    require_active_campaign: bool = False,
) -> list[Candidate]:
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for record in records:
        candidate = classify(record, fresh_after=fresh_after, require_active_campaign=require_active_campaign)
        issue_identity = candidate.key.lower()
        if issue_identity in seen:
            raise WorkfeedError(f"duplicate issue key: {candidate.key}")
        seen.add(issue_identity)
        candidates.append(candidate)

    rank = {
        "READY": 0,
        "CLAIM_REQUIRED": 1,
        "SWARM_TAKEN": 2,
        "CLAIMED_OR_PR_OPEN": 3,
        "ASSIGNED": 4,
        "STALE_EVIDENCE": 5,
        "REPOSITORY_ARCHIVED": 6,
        "CAMPAIGN_UNVERIFIED": 7,
        "CAMPAIGN_INACTIVE": 8,
        "INELIGIBLE": 9,
    }
    candidates.sort(
        key=lambda c: (
            rank[c.status],
            0 if c.reward_class == "EXPLICIT_AMOUNT_MENTIONED" else 1,
            1 if c.security_sensitive else 0,
            c.repository.lower(),
            c.number,
        )
    )
    return candidates


def render_markdown(candidates: Iterable[Candidate]) -> str:
    rows = list(candidates)
    counts: dict[str, int] = {}
    for c in rows:
        counts[c.status] = counts.get(c.status, 0) + 1

    lines = [
        "# GrantFox FWC26 workfeed",
        "",
        "Generated from supplied GitHub issue snapshots. This file does **not** claim, assign, apply, contact maintainers, or guarantee payment.",
        "",
        "## Summary",
        "",
        f"- READY: {counts.get('READY', 0)}",
        f"- CLAIM_REQUIRED: {counts.get('CLAIM_REQUIRED', 0)}",
        f"- SWARM_TAKEN: {counts.get('SWARM_TAKEN', 0)}",
        f"- CLAIMED_OR_PR_OPEN: {counts.get('CLAIMED_OR_PR_OPEN', 0)}",
        f"- ASSIGNED: {counts.get('ASSIGNED', 0)}",
        f"- STALE_EVIDENCE: {counts.get('STALE_EVIDENCE', 0)}",
        f"- REPOSITORY_ARCHIVED: {counts.get('REPOSITORY_ARCHIVED', 0)}",
        f"- CAMPAIGN_UNVERIFIED: {counts.get('CAMPAIGN_UNVERIFIED', 0)}",
        f"- CAMPAIGN_INACTIVE: {counts.get('CAMPAIGN_INACTIVE', 0)}",
        f"- INELIGIBLE: {counts.get('INELIGIBLE', 0)}",
        "",
        "## Queue",
        "",
        "| Status | Issue | Campaign | Reward evidence | Security-sensitive | Commands |",
        "|---|---|---|---|---:|---|",
    ]
    for c in rows:
        reward = c.reward_class
        if c.explicit_reward_mentions:
            reward += " (" + ", ".join(c.explicit_reward_mentions) + ")"
        commands = "<br>".join(f"`{cmd}`" for cmd in c.commands) or "—"
        issue = f"[{c.key}]({c.url}) — {c.title}"
        campaign = "active" if c.campaign_active is True else "inactive" if c.campaign_active is False else "unknown"
        lines.append(
            f"| {c.status} | {issue} | {campaign} | {reward} | {'yes' if c.security_sensitive else 'no'} | {commands} |"
        )
        lines.append(f"\n> **{c.key}:** {c.reason}\n")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    candidates: list[Candidate], out_dir: Path, *, fresh_after: str | None = None,
    require_active_campaign: bool = False,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "evidence_fresh_after": fresh_after,
        "require_active_campaign": require_active_campaign,
        "authority": {
            "claims_issues": False,
            "assigns_issues": False,
            "guarantees_payment": False,
            "mutates_external_systems": False,
        },
        "issues": [c.to_dict() for c in candidates],
    }
    (out_dir / "queue.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "QUEUE.md").write_text(render_markdown(candidates), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile GrantFox FWC26 GitHub issue snapshots into a safe swarm workfeed."
    )
    parser.add_argument("input", type=Path, help="JSON array or JSONL issue snapshot file")
    parser.add_argument("--out-dir", type=Path, required=True, help="exclusive output directory")
    parser.add_argument(
        "--fresh-after",
        help="optional ISO-8601 freshness floor; older or missing observed_at snapshots become STALE_EVIDENCE",
    )
    parser.add_argument(
        "--require-active-campaign", action="store_true",
        help="do not route unassigned issues without explicit campaign_active=true evidence",
    )
    args = parser.parse_args(argv)

    if args.out_dir.exists():
        raise WorkfeedError(f"output directory already exists: {args.out_dir}")

    candidates = compile_records(
        _read_records(args.input), fresh_after=args.fresh_after,
        require_active_campaign=args.require_active_campaign,
    )
    write_outputs(
        candidates, args.out_dir, fresh_after=args.fresh_after,
        require_active_campaign=args.require_active_campaign,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

