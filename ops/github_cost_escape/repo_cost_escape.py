#!/usr/bin/env python3
"""Offline GitHub repository cost/visibility migration planner.

Consumes a JSON repository inventory (for example GitHub API list-repos output)
and an optional policy overlay. It never mutates repositories. Output is a
reviewable plan separating repository visibility decisions from hosted-CI cost.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

SENSITIVE_CLASSES = {"customer", "regulated", "secret-bearing", "proprietary"}


@dataclass(frozen=True)
class Decision:
    repository: str
    visibility: str
    action: str
    rationale: list[str]
    ci_action: str
    risk: str
    requires_human_approval: bool = True


def _name(repo: dict[str, Any]) -> str:
    return str(repo.get("repository_full_name") or repo.get("full_name") or repo.get("name") or "<unknown>")


def _private(repo: dict[str, Any]) -> bool:
    visibility = str(repo.get("visibility") or "").lower()
    if visibility:
        return visibility == "private"
    return bool(repo.get("private", False))


def _policy_for(repo: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    name = _name(repo)
    per_repo = overlay.get("repositories", {}).get(name, {})
    defaults = overlay.get("defaults", {})
    merged = dict(defaults)
    merged.update(per_repo)
    return merged


def decide(repo: dict[str, Any], overlay: dict[str, Any]) -> Decision:
    name = _name(repo)
    visibility = "private" if _private(repo) else "public"
    size = int(repo.get("size") or 0)
    archived = bool(repo.get("archived", False))
    p = _policy_for(repo, overlay)

    classification = str(p.get("classification", "unknown")).lower()
    public_reviewed = bool(p.get("public_release_reviewed", False))
    separable = bool(p.get("separable_public_core", False))
    force_private = bool(p.get("force_private", False))
    retention_required = bool(p.get("retention_required", False))

    reasons: list[str] = []
    risk = "low"

    if visibility == "public":
        action = "already_public"
        reasons.append("repository is already public; no visibility migration needed")
    elif force_private or classification in SENSITIVE_CLASSES:
        action = "keep_private"
        risk = "high" if classification in {"customer", "regulated", "secret-bearing"} else "medium"
        reasons.append(f"policy classification={classification!r} requires private custody")
    elif archived:
        action = "archive_cost_review"
        reasons.append("repository is already archived; review whether the private copy is still required")
    elif size == 0 and not retention_required:
        action = "empty_private_retirement_candidate"
        reasons.append("private repository reports size=0 and has no retention requirement")
    elif public_reviewed:
        action = "publish_safe_candidate"
        risk = "medium"
        reasons.append("explicit public_release_reviewed=true supplied by policy overlay")
        reasons.append("visibility change still requires a separate human approval and secret-history review")
    elif separable:
        action = "split_public_core_private_data"
        risk = "medium"
        reasons.append("policy marks a separable public core; extract only reviewed non-sensitive code")
        reasons.append("keep customer data, credentials, private history, and proprietary overlays private")
    else:
        action = "review_required"
        risk = "medium"
        reasons.append("private repository has no explicit evidence authorizing publication, retirement, or splitting")

    hosted_minutes = p.get("hosted_ci_minutes_estimate")
    hosted_fanout = p.get("hosted_ci_fanout")
    if p.get("disable_hosted_ci", False):
        ci_action = "hosted_ci_disabled_by_policy"
    elif hosted_minutes is not None and float(hosted_minutes) > 0:
        if p.get("free_external_ci_available", False):
            ci_action = "migrate_hosted_ci_to_free_external_capacity"
        elif hosted_fanout is not None and int(hosted_fanout) > 1:
            ci_action = "consolidate_hosted_ci_fanout"
        else:
            ci_action = "profile_hosted_ci_before_next_run"
    else:
        ci_action = "ci_cost_unknown_or_zero"

    return Decision(
        repository=name,
        visibility=visibility,
        action=action,
        rationale=reasons,
        ci_action=ci_action,
        risk=risk,
    )


def plan(repositories: Iterable[dict[str, Any]], overlay: dict[str, Any]) -> list[Decision]:
    decisions = [decide(repo, overlay) for repo in repositories]
    priority = {
        "empty_private_retirement_candidate": 0,
        "archive_cost_review": 1,
        "split_public_core_private_data": 2,
        "publish_safe_candidate": 3,
        "review_required": 4,
        "keep_private": 5,
        "already_public": 6,
    }
    return sorted(decisions, key=lambda d: (priority.get(d.action, 99), d.repository.lower()))


def normalize_inventory(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for key in ("repositories", "items"):
            if isinstance(doc.get(key), list):
                return doc[key]
        if isinstance(doc.get("result"), dict) and isinstance(doc["result"].get("repositories"), list):
            return doc["result"]["repositories"]
    raise ValueError("inventory must be a repository list or object containing repositories/items")


def render_markdown(decisions: list[Decision]) -> str:
    lines = [
        "# GitHub cost escape plan",
        "",
        "This report is advisory only. It does not change repository visibility, delete repositories, or run CI.",
        "",
        "| Repository | Visibility | Visibility action | CI action | Risk |",
        "|---|---|---|---|---|",
    ]
    for d in decisions:
        lines.append(f"| `{d.repository}` | {d.visibility} | `{d.action}` | `{d.ci_action}` | {d.risk} |")
    lines.extend(["", "## Rationale", ""])
    for d in decisions:
        lines.append(f"### {d.repository}")
        lines.extend(f"- {r}" for r in d.rationale)
        lines.append("- human approval required before any destructive or visibility-changing action")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inventory", type=Path)
    ap.add_argument("--policy", type=Path)
    ap.add_argument("--format", choices=("json", "markdown"), default="markdown")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    inventory = normalize_inventory(json.loads(args.inventory.read_text(encoding="utf-8")))
    overlay: dict[str, Any] = {}
    if args.policy:
        overlay = json.loads(args.policy.read_text(encoding="utf-8"))

    decisions = plan(inventory, overlay)
    if args.format == "json":
        text = json.dumps([asdict(d) for d in decisions], indent=2, sort_keys=True) + "\n"
    else:
        text = render_markdown(decisions) + "\n"

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
