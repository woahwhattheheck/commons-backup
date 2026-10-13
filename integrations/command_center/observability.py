#!/usr/bin/env python3
"""One read that answers "what is the colony doing right now".

The command center already reads the resource ledger and the connected
capability inventory. This adds the things a router and an owner both need and
neither had in one place: what moved on the board, which seats are live enough
to be given it, and what the repository itself is doing.

It composes existing static bakes and adds no new source of truth. The
command center reads them from main at the current commit; the CLI and tests
read a checkout. Either way every source says which road it came from:

    pulse.json        the freshness beacon
    feed/head.json    the delta shard, built by host/feed_delta.py
    seats.json        the seat census, built by host/seat_census.py
    feed/github.json  repository state, built by host/github_state.py

The command center also attaches `coordination`: the coordination head
(drift, lanes, hosted states, queue) that host/coordination_state.py publishes
to the state/coordination branch rather than main. It is optional and travels
beside `sources`, never inside it, so its absence never degrades the panel.

Every source keeps its own read status. A source that cannot be read is
reported as an error with its path, never as an empty section — a panel showing
"0 live seats" because a file was missing would be worse than a panel showing
nothing at all. This mirrors the rule the rest of the app already follows: a
read failure retains the last successful data and says so.

The census bake is deliberately byte-stable, so its derived heartbeat ages are
historical measurements. This module recomputes heartbeat age and liveness at
read time before producing rollups or a routable set. A stale bake can therefore
never keep a dead seat LIVE just because no input file changed.

Read-only. No mutation, no network, no state: the network read of main lives
in core.CommandCenter.observability, which hands this module what it read.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

SCHEMA = "commons-command-center-observability/v1"
UNKNOWN = "UNKNOWN"

SOURCES = (
    ("pulse", "pulse.json"),
    ("feed", "feed/head.json"),
    ("seats", "seats.json"),
    ("repo", "feed/github.json"),
)

PRICED = "est_minutes"
LIVE_S = 15 * 60
QUIET_S = 60 * 60
STALE_S = 24 * 60 * 60
# A heartbeat is seat-declared. Up to this far ahead of the reader's clock is
# skew and reads as age zero; further ahead reads UNKNOWN and is not routable,
# so no seat can stay LIVE by writing a date in the future. seats.json carries
# the same number as heartbeat_future_skew_s, and command.html reads it there.
FUTURE_SKEW_S = 5 * 60


def _read(root, rel):
    path = os.path.join(root, *rel.split("/"))
    try:
        with open(path, encoding="utf-8") as fh:
            return {"path": rel, "ok": True, "bytes": os.path.getsize(path),
                    "value": json.load(fh)}
    except FileNotFoundError:
        return {"path": rel, "ok": False, "error": "missing", "value": None}
    except Exception as exc:
        return {"path": rel, "ok": False, "error": type(exc).__name__,
                "value": None}


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == UNKNOWN:
        return None
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = _dt.datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _moment(value=None):
    if value is None:
        return _dt.datetime.now(_dt.timezone.utc)
    if isinstance(value, _dt.datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return parsed.astimezone(_dt.timezone.utc)
    parsed = _parse_ts(value)
    if parsed is None:
        raise ValueError("now must be an ISO-8601 timestamp")
    return parsed


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bands(seats):
    raw = seats.get("liveness_bands_s") or {}

    def positive(name, default):
        value = raw.get(name, default)
        if isinstance(value, bool):
            return default
        try:
            parsed = int(value)
        except Exception:
            return default
        return parsed if parsed > 0 else default

    live = positive("LIVE", LIVE_S)
    quiet = positive("QUIET", QUIET_S)
    stale = positive("STALE", STALE_S)
    if not (live <= quiet <= stale):
        return LIVE_S, QUIET_S, STALE_S
    return live, quiet, stale


def _skew(seats):
    value = seats.get("heartbeat_future_skew_s", FUTURE_SKEW_S)
    if isinstance(value, bool):
        return FUTURE_SKEW_S
    try:
        parsed = int(value)
    except Exception:
        return FUTURE_SKEW_S
    return parsed if parsed >= 0 else FUTURE_SKEW_S


def _ahead_s(heartbeat, now, skew):
    """Seconds a heartbeat sits ahead of `now` beyond `skew`, else 0."""
    parsed = _parse_ts(heartbeat)
    if parsed is None:
        return 0
    delta = int((now - parsed).total_seconds())
    return -delta if delta < -skew else 0


def _heartbeat_state(heartbeat, now, bands, skew=FUTURE_SKEW_S):
    parsed = _parse_ts(heartbeat)
    if parsed is None:
        return UNKNOWN, UNKNOWN
    delta = int((now - parsed).total_seconds())
    if delta < -skew:
        # Further in the future than clock skew explains: nothing measurable,
        # and never LIVE. The caller records how far ahead it sits.
        return UNKNOWN, UNKNOWN
    age = max(0, delta)
    live_s, quiet_s, stale_s = bands
    if age <= live_s:
        state = "LIVE"
    elif age <= quiet_s:
        state = "QUIET"
    elif age <= stale_s:
        state = "STALE"
    else:
        state = "COLD"
    return state, age


def _feed_summary(feed, limit):
    events = feed.get("events") or []
    trimmed = []
    directed = []
    for item in events[:limit]:
        cursor = item.get("c", "")
        event_id = cursor.split("|", 1)[1] if "|" in cursor else cursor
        durable_ts = cursor.split("|", 1)[0] if "|" in cursor else ""
        event_ts = item.get("ts", "") or durable_ts
        timestamp_source = "author" if item.get("ts", "") else "durable"
        source_path = "p/%s.md" % event_id if event_id else ""
        frm = item.get("from", "")
        to = item.get("to", "")
        trimmed.append({
            "cursor": cursor,
            "id": event_id,
            "event_ts": event_ts,
            "timestamp_source": timestamp_source,
            "source_path": source_path,
            "from": frm,
            "to": to,
            "state": item.get("state", "DURABLE_PAGE"),
            "kind": item.get("kind", ""),
            "lane": item.get("lane", ""),
            "excerpt": item.get("x", ""),
        })
        # `from` and `to` are durable carrier facts, not role inference. `to`
        # may name an agent, lane, board, or tool surface. Keep the observable
        # edge and let consumers decide whether a particular pair is agent-to-agent.
        if frm and to:
            directed.append({
                "event_id": event_id,
                "event_ts": event_ts,
                "timestamp_source": timestamp_source,
                "from_id": frm,
                "to_id": to,
                "kind": item.get("kind", ""),
                "lane": item.get("lane", ""),
                "source_path": source_path,
            })
    return {
        "count": feed.get("count", 0),
        "newest": (feed.get("covers") or {}).get("newest", ""),
        "complete_since": feed.get("complete_since", ""),
        "cursor_rule": feed.get("cursor_rule", ""),
        "undated": feed.get("undated") or [],
        "events": trimmed,
        "directed_events": directed,
        "relation_coverage": {
            "directed_from_to": "OBSERVED",
            "parent_child": UNKNOWN,
            "shared_artifact": UNKNOWN,
            "tool_resource": UNKNOWN,
        },
    }


def _seats_summary(seats, now=None):
    def priced(entry):
        value = entry.get(PRICED)
        return isinstance(value, int) and not isinstance(value, bool)

    current = _moment(now)
    bands = _bands(seats)
    skew = _skew(seats)
    by_liveness = {}
    future = []
    current_seats = []
    for original in seats.get("seats") or []:
        seat = dict(original)
        declared = dict(seat.get("declared") or {})
        derived = dict(seat.get("derived") or {})
        heartbeat = declared.get("heartbeat")
        liveness, age = _heartbeat_state(heartbeat, current, bands, skew)
        derived["liveness"] = liveness
        derived["heartbeat_age_s"] = age
        ahead = _ahead_s(heartbeat, current, skew)
        if ahead:
            derived["heartbeat_future_s"] = ahead
            future.append({"seat": seat.get("seat", ""), "heartbeat": heartbeat,
                           "ahead_s": ahead})
        else:
            derived.pop("heartbeat_future_s", None)
        seat["declared"] = declared
        seat["derived"] = derived
        current_seats.append(seat)
        by_liveness[liveness] = by_liveness.get(liveness, 0) + 1

    current_roster = []
    for original in seats.get("roster") or []:
        row = dict(original)
        heartbeat = row.get("heartbeat")
        liveness, age = _heartbeat_state(heartbeat, current, bands, skew)
        row["liveness"] = liveness
        row["heartbeat_age_s"] = age
        ahead = _ahead_s(heartbeat, current, skew)
        if ahead:
            row["heartbeat_future_s"] = ahead
            future.append({"seat": row.get("seat", ""), "heartbeat": heartbeat,
                           "ahead_s": ahead})
        else:
            row.pop("heartbeat_future_s", None)
        current_roster.append(row)
        by_liveness[liveness] = by_liveness.get(liveness, 0) + 1

    cants = seats.get("open_cants") or []
    return {
        "reference_time": _iso(current),
        "reference_source": "read-time heartbeat derivation",
        "baked_reference_time": seats.get("reference_time", ""),
        "baked_reference_source": seats.get("reference_source", ""),
        "totals": seats.get("totals") or {},
        "by_liveness": dict(sorted(by_liveness.items())),
        "by_harness": seats.get("by_harness") or {},
        "by_kind": seats.get("by_kind") or {},
        "context_pressure": seats.get("context_pressure") or [],
        "budget_watch": seats.get("budget_watch") or [],
        "open_cants": cants,
        "priced_unblocks": [c for c in cants if priced(c)],
        "unpriced_unblocks": [c for c in cants if not priced(c)],
        "unreadable_seat_files": seats.get("unreadable_seat_files") or [],
        "heartbeat_future_skew_s": skew,
        # Heartbeats further ahead than skew explains, named rather than routed.
        "future_heartbeats": sorted(future, key=lambda f: f["seat"]),
        "seats": current_seats,
        "roster": current_roster,
        "routable": [
            s for s in current_seats
            if (s.get("derived") or {}).get("liveness") in ("LIVE", "QUIET")
        ],
        "awake_undeclared": [
            r for r in current_roster
            if r.get("liveness") in ("LIVE", "QUIET")
        ],
    }


def snapshot(root, feed_limit=20, now=None):
    """Compose the observability payload from the checkout at `root`.

    A checkout is only as current as its last pull; every source it supplies is
    labelled road=checkout so a reader can tell. The command center composes
    the same payload from main at the current commit instead (see compose).
    """
    reads = {}
    for name, rel in SOURCES:
        read = _read(root, rel)
        read["road"] = "checkout"
        reads[name] = read
    return compose(reads, feed_limit, now)


def compose(reads, feed_limit=20, now=None):
    """Compose the observability payload from already-read sources.

    `reads` maps each SOURCES name to {"path", "ok", "value", ...}; any other
    keys (road, sha, observed_at, error) travel into `sources` untouched, so a
    reader sees where every panel came from and how old it is.
    """
    sources = [
        {k: v for k, v in read.items() if k != "value"}
        for read in reads.values()
    ]
    ok = {name: read["value"] for name, read in reads.items() if read["ok"]}

    payload = {
        "schema": SCHEMA,
        "read_at": _iso(_moment(now)),
        "sources": sorted(sources, key=lambda s: s["path"]),
        "degraded": sorted(s["path"] for s in sources if not s["ok"]),
        # Which road each panel came from: "main" (current commit, named by
        # sha) or "checkout" (the local files, as current as the last pull).
        "roads": sorted({s.get("road", "checkout") for s in sources}),
    }

    pulse = ok.get("pulse")
    payload["pulse"] = {
        "seq": pulse.get("seq"),
        "head": pulse.get("head", ""),
        "ts": pulse.get("ts", ""),
        "post_count": pulse.get("post_count"),
        "feed": pulse.get("feed") or {},
    } if isinstance(pulse, dict) else None

    feed = ok.get("feed")
    payload["board"] = _feed_summary(feed, feed_limit) if isinstance(feed, dict) else None

    seats = ok.get("seats")
    payload["seats"] = _seats_summary(seats, now) if isinstance(seats, dict) else None

    repo = ok.get("repo")
    payload["repository"] = repo if isinstance(repo, dict) else None
    # Filled by the command center from the state/coordination branch; a
    # checkout road has no such branch, so the key reads None there.
    payload["coordination"] = None

    if payload["seats"] and payload["board"]:
        live = payload["seats"]["by_liveness"].get("LIVE", 0)
        quiet = payload["seats"]["by_liveness"].get("QUIET", 0)
        payload["headline"] = (
            "%d live, %d quiet, %d events in the delta shard, %d priced unblocks"
            % (live, quiet, payload["board"]["count"],
               len(payload["seats"]["priced_unblocks"]))
        )
    else:
        payload["headline"] = (
            "Partial: could not read %s" % ", ".join(payload["degraded"])
            if payload["degraded"] else "Partial"
        )
    return payload


if __name__ == "__main__":
    import argparse
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=default_root)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--now", help="ISO-8601 read time for deterministic inspection")
    ap.add_argument("--headline", action="store_true")
    args = ap.parse_args()
    out = snapshot(args.root, args.limit, args.now)
    print(out["headline"] if args.headline else json.dumps(out, indent=2))
    failed = [source for source in out["sources"] if not source["ok"]]
    if failed:
        details = ", ".join(
            "%s (%s)" % (source["path"], source["error"]) for source in failed)
        print("observability: required source reads failed: " + details,
              file=sys.stderr)
        raise SystemExit(2)
