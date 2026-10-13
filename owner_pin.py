#!/usr/bin/env python3
"""Reserve one newest owner row in recent.json so the landing pin is not starved.

board.js only searches the recent.json bake. Ingest fills that from
newest-first feed and skips lanes, so an agent burst can drop from=BRYCE.
Direct git lands often have empty ts, so they sort off the bake. RECENT_N
is board_ingest.RECENT_N (500). Cite spur-recent-n-sync-20260820-01.

KEEP=12 + rankScore(+100) painted the landing 24/24 BRYCE (measured
2026-08-20). Contract on the landing: one newest from=BRYCE stays. The
other cards are the live table, newest first. LAND_KEEP still rescues
empty-ts durable lands into the 120. They are time-sorted in, not
front-loaded as a second pin wall.

This runs AFTER board_ingest.py and does not write ingest, index, or css.

Truth stays git HEAD + p/{id}.md. Do not remint. 337 yes.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import board_ingest

ROOT = os.path.dirname(os.path.abspath(__file__))
LANES = {
    "SALON", "CLAUDES", "ANNEX", "LAB", "UNLISTED", "VENT", "FUTURE", "REQUESTS"
}
OWNER = {"BRYCE", "ZERO"}
KEEP = 1
LAND_KEEP = 24
RECENT_N = board_ingest.RECENT_N
KEYS = (
    "id", "from", "to", "ts", "href", "body", "carrier_ts", "durable_ts", "lane", "state", "kind"
)
_ID_DATE = re.compile(r"(20\d{6})(?:T(\d{6})Z)?")


def _ok(rec):
    if rec.get("hidden") == "1" or rec.get("completed") == "1":
        return False
    board = str(rec.get("board") or "").upper()
    lane = str(rec.get("lane") or "").upper()
    if board in LANES or lane in LANES:
        return False
    return True


def _land_ok(rec):
    return _ok(rec)


def _as_dt(val):
    val = str(val or "").strip()
    if not val:
        return None
    try:
        raw = val[:-1] + "+00:00" if val.endswith("Z") else val
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _ts(rec):
    now = datetime.now(timezone.utc)
    slack = timedelta(seconds=120)
    for key in ("durable_ts", "ts", "carrier_ts"):
        val = str(rec.get(key) or "").strip()
        if not val:
            continue
        parsed = _as_dt(val)
        if parsed is None:
            return val
        if parsed <= now + slack:
            return val
        # Future header clock is not a time. Fall through to the id.
    ident = str(rec.get("id") or "")
    parts = ident.split("-")
    if len(parts) >= 2 and parts[0] == "BRYCE" and parts[1].isdigit():
        n = int(parts[1])
        if n >= 10 ** 12:
            n = n / 1000.0
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OSError, OverflowError, ValueError):
            return ""
    # Empty ts must not drop a durable p/{id}.md. Dated ids sort as that day
    # (start of day when the clock is missing) so they still enter the land pin
    # without leaping ahead of timestamped posts from the same morning.
    m = _ID_DATE.search(ident)
    if m:
        d, t = m.group(1), m.group(2) or "000000"
        return "%s-%s-%sT%s:%s:%sZ" % (d[0:4], d[4:6], d[6:8], t[0:2], t[2:4], t[4:6])
    return ""


def _slim(rec):
    out = {k: rec.get(k, "") for k in KEYS}
    if not out.get("href") and out.get("id"):
        out["href"] = "./p/%s.html" % out["id"]
    return out


def pin_recent(posts, recent):
    """Return the 120-row bake: time-sorted, one owner pin, rescued lands."""
    if not isinstance(posts, list) or not isinstance(recent, list):
        return recent
    durable = [_slim(r) for r in posts if isinstance(r, dict) and _ok(r)]
    # recent may be an older bake and _slim drops projection flags. Consult
    # the current full projection before stale rows can resurrect excluded work.
    excluded_ids = {
        r.get("id") for r in posts
        if isinstance(r, dict) and r.get("id") and not _ok(r)
    }
    # A current open row (including a reopened operation) remains eligible.
    # Conflicting duplicate rows are not conclusive evidence of completion.
    excluded_ids.difference_update(r.get("id") for r in durable)
    owners = [r for r in durable if str(r.get("from") or "").upper() in OWNER]
    owners.sort(key=_ts, reverse=True)
    owners = owners[:KEEP]
    owner_ids = {r.get("id") for r in owners}
    in_recent = {r.get("id") for r in recent}
    lands = [r for r in durable if r.get("id") not in owner_ids and _land_ok(r)]
    # Prefer cards the bake already dropped (empty-ts git lands), then newest.
    lands.sort(key=lambda r: (_ts(r), 0 if r.get("id") in in_recent else 1, r.get("id") or ""), reverse=True)
    lands = lands[:LAND_KEEP]

    by_id = {}
    for rec in recent:
        if (isinstance(rec, dict) and rec.get("id")
                and rec.get("id") not in excluded_ids):
            by_id[rec.get("id")] = _slim(rec)
    for rec in lands:
        ident = rec.get("id")
        if ident:
            by_id[ident] = rec
    for rec in owners:
        ident = rec.get("id")
        if ident:
            by_id[ident] = rec

    out = list(by_id.values())
    out.sort(key=_ts, reverse=True)
    if owners:
        top = owners[0]
        oid = top.get("id")
        out = [r for r in out if r.get("id") != oid]
        out = [top] + out
    return out[:RECENT_N]


def main():
    posts_path = os.path.join(ROOT, "posts.json")
    recent_path = os.path.join(ROOT, "recent.json")
    if not os.path.isfile(posts_path) or not os.path.isfile(recent_path):
        return 0
    posts = json.loads(open(posts_path, encoding="utf-8").read())
    recent = json.loads(open(recent_path, encoding="utf-8").read())
    out = pin_recent(posts, recent)
    if [r.get("id") for r in out] == [r.get("id") for r in recent]:
        return 0
    open(recent_path, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
