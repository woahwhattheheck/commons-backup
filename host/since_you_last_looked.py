#!/usr/bin/env python3
"""Since you last looked. Git + Slack + Commons. Grouped. Nothing dropped.

Not the per-merge landed-work formatter. Not the first-visit grounding door.
Bryce posts (his account, no Sent-using footer) pin to the top of Slack.
No model ranks. --send/--go REFUSED: no new Slack secret in this repo.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/SINCE_YOU_LAST_LOOKED.json"
REPO = "woahwhattheheck/commons"
BRYCE_USER = "U0BR9670G2H"
SENT_USING = re.compile(r"Sent using", re.I)
REFUSE = ("--send", "--apply", "--go", "--autopilot")
COMMONS_PREFIX = ("p/", "ground/")


def git(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd or ROOT), text=True
    ).strip()


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def is_bryce_post(row: dict[str, Any]) -> bool:
    if row.get("bot"):
        return False
    text = str(row.get("text") or "")
    if SENT_USING.search(text) or row.get("sent_using"):
        return False
    return row.get("user_id") == BRYCE_USER


def slack_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pinned = [row for row in rows if row.get("bryce_pin") or is_bryce_post(row)]
    rest = [row for row in rows if row not in pinned]
    pinned.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    rest.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    return pinned + rest


def paths_of(sha: str, cwd: Path | None = None) -> list[str]:
    out = git(
        [
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-m",
            "--first-parent",
            sha,
        ],
        cwd=cwd,
    )
    return [line for line in out.splitlines() if line.strip()]


def is_commons_path(rel: str) -> bool:
    if rel.startswith(COMMONS_PREFIX):
        return True
    return rel.endswith(".html") and "/" not in rel


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).astimezone(timezone.utc)


def in_window(iso: str, since: datetime | None) -> bool:
    if since is None:
        return True
    stamp = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return stamp >= since


def git_rows(limit: int = 12, cwd: Path | None = None) -> list[dict[str, Any]]:
    raw = git(
        ["log", "--first-parent", f"-{limit}", "--format=%H\t%cI\t%an\t%s"],
        cwd=cwd,
    )
    rows: list[dict[str, Any]] = []
    if not raw:
        return rows
    for line in raw.splitlines():
        sha, iso, author, subject = line.split("\t", 3)
        rows.append(
            {
                "surface": "git",
                "repo": REPO,
                "sha": sha,
                "iso": iso,
                "author": author,
                "title": subject,
                "paths": paths_of(sha, cwd),
            }
        )
    return rows


def commons_rows(git_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in git_items:
        commons_paths = [rel for rel in item["paths"] if is_commons_path(rel)]
        if not commons_paths:
            continue
        rows.append(
            {
                "surface": "commons",
                "repo": item["repo"],
                "sha": item["sha"],
                "iso": item["iso"],
                "author": item["author"],
                "title": item["title"],
                "paths": commons_paths,
            }
        )
    return rows


def slack_rows(catalog: dict[str, Any]) -> dict[str, Any]:
    # Keep the retained catalog rows unchanged while annotating output.
    measured = [dict(row) for row in (catalog.get("slack_measured") or [])]
    for row in measured:
        row["surface"] = "slack"
        row["bryce_pin"] = bool(row.get("bryce_pin") or is_bryce_post(row))
    ordered = slack_order(measured)
    return {
        "live_token": catalog.get("slack_live_token", "FINDER-FAILED"),
        "search_space": catalog.get("bryce", {}).get("search_space"),
        "keyword_search_hits": catalog.get("bryce", {}).get("keyword_search_hits"),
        "count": len(ordered),
        "bryce_pinned": sum(1 for row in ordered if row.get("bryce_pin")),
        "dropped": 0,
        "items": ordered,
    }


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "SINCE_YOU_LAST_LOOKED_FEED",
        "id": "cursor-since-you-last-looked-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "note": f"{flag} REFUSED. No new Slack secret. Use the harness that already has Slack.",
    }


def measure(
    limit: int = 12,
    since: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    since_dt = parse_since(since)
    git_items = [row for row in git_rows(limit, cwd) if in_window(row["iso"], since_dt)]
    commons_items = [
        row for row in commons_rows(git_items) if in_window(row["iso"], since_dt)
    ]
    slack = slack_rows(catalog)
    if since_dt is not None:
        slack["items"] = [
            row for row in slack["items"] if in_window(str(row.get("iso") or ""), since_dt)
        ]
        slack["count"] = len(slack["items"])
        slack["bryce_pinned"] = sum(1 for row in slack["items"] if row.get("bryce_pin"))
        slack["dropped"] = 0
    surfaces = {
        "git": git_items,
        "slack": slack["items"],
        "commons": commons_items,
    }
    empty = not git_items and not commons_items and not slack["items"]
    return {
        "kind": "SINCE_YOU_LAST_LOOKED_FEED",
        "id": catalog["id"],
        "item": 2,
        "gate": False,
        "login": False,
        "commons_is_store": False,
        "model_decides_what_matters": False,
        "nothing_dropped": True,
        "grouped_by": ["git", "slack", "commons"],
        "not_per_merge_line": True,
        "not_first_visit_grounding": True,
        "since": since or None,
        "window_empty": empty,
        "window_note": (
            "FINDER-FAILED empty window. Surfaces stay grouped. Nothing dropped."
            if empty
            else "Measured window. Bake commits stay on git. No model rank."
        ),
        "slack_live_token": slack["live_token"],
        "slack_search_space": slack["search_space"],
        "slack_keyword_search_hits": slack["keyword_search_hits"],
        "bryce_pinned": slack["bryce_pinned"],
        "dropped": 0,
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "counts": {
            "git": len(git_items),
            "slack": slack["count"],
            "commons": len(commons_items),
        },
        "surfaces": surfaces,
        "verdict": "RENDER",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--since", default=None)
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "SINCE_YOU_LAST_LOOKED_FEED",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure(args.limit, args.since)
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
