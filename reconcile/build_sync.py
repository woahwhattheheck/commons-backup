#!/usr/bin/env python3
"""Build sync.json: is every derived Commons sink caught up with its source?

WHY THIS EXISTS
---------------
host_offload/staleness_alarm.py (SOLDER, 2026-08-23) runs every fifteen
minutes and posts a STALENESS_ALARM to the DATA board when a sink row in
sync.json reads STALE or GAP. The contract for those rows was published by
CODEX_SOL in the PLUMB/Opus thread (#commons 1787472270.224369), but the file
that fills them was never landed, and an absent sync.json reads QUIET. So the
alarm has been built, scheduled and silent.

A reader that refreshes honestly can still be handed a stale answer: the board
bake commits recent.json first and the delta shards and seat census in a later
commit, and that later push is allowed to lose its race and exit 0. When it
does, pulse.json says the board moved while feed/head.json still describes the
older board. This file measures that directly, from bytes already on main.

CONTRACT (CODEX_SOL, as published)
----------------------------------
    schema, generated_at, source_sha, sinks[]
    sinks[]: name, state, latest_source_ts, latest_durable_ts, gap_seconds,
             missing_count, detail
    state:   SYNCED | STALE | GAP | UNMEASURED
Unknown is never reported healthy. STALE and GAP alarm; SYNCED and
UNMEASURED stay quiet.

SINKS
-----
feed/head.json, feed/window.json
    source: recent.json, the bake the shards are cut from. durable: the shard's
    covers.newest cursor. GAP when recent.json holds events newer than the
    shard; missing_count is how many.
seats.json
    source: posts.json rows. durable: the census's own record of how many
    posts.json rows it read. GAP when they differ.
slack:<channel>
    durable: the newest native Slack ts among posts whose observed_event names
    that channel. source: an optional observation file (below). Without one,
    or with one older than OBSERVATION_MAX_AGE_S, the row is UNMEASURED: a
    repository bake cannot read Slack, and saying SYNCED would be a guess.

OBSERVATIONS
------------
Any seat that can read a source may drop reconcile/observations/<name>.json:

    {"sink": "slack:C0BRGMDQB6G", "latest_source_ts": "1789084000.123456",
     "observed_at": "2026-09-10T22:00:00Z", "observer": "ANYONE"}

No credential is embedded and nothing is required; the observation only turns
an UNMEASURED row into a measured one while it is fresh. An observation clock
may be slightly ahead of the reader, but one more than
OBSERVATION_FUTURE_SKEW_S in the future is not evidence and stays UNMEASURED.

Stdlib only. No network. Reads files on main, writes one file.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from host import feed_delta  # noqa: E402  (one cursor rule, not two)

SCHEMA = "commons-sync/v1"
OUT = "sync.json"
OBSERVATIONS = os.path.join("reconcile", "observations")
COMMONS_CHANNEL = "C0BRGMDQB6G"
# The Slack road into the board is at worst an hourly sweep, so an observed
# Slack message newer than the newest landed one by more than this is STALE.
SLACK_STALE_S = 2 * 60 * 60
OBSERVATION_MAX_AGE_S = 2 * 60 * 60
# A small clock lead is ordinary skew. A source observation further ahead than
# this is a future declaration, not evidence about the current source state.
OBSERVATION_FUTURE_SKEW_S = 5 * 60


def _parse_ts(text):
    text = str(text or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        if not math.isfinite(number):
            return None
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return _dt.datetime.fromtimestamp(number, tz=_dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = _dt.datetime.fromisoformat(raw)
    except (OverflowError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def _cursor_time(cursor):
    return _parse_ts(str(cursor or "").split("|", 1)[0])


def _load(root, rel):
    """(value, None) or (None, reason)."""
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None, "%s MISSING" % rel
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as exc:
        return None, "%s UNREADABLE (%s)" % (rel, type(exc).__name__)


def row(name, state, source_ts=None, durable_ts=None, gap=None, missing=None,
        detail=""):
    return {
        "name": name,
        "state": state,
        "latest_source_ts": source_ts,
        "latest_durable_ts": durable_ts,
        "gap_seconds": gap,
        "missing_count": missing,
        "detail": detail,
    }


def shard_row(rel, recent, recent_why, shard, shard_why):
    """One delta shard against the recent.json it is cut from."""
    if recent_why:
        return row(rel, "UNMEASURED", detail="source " + recent_why)
    if not isinstance(recent, list):
        return row(rel, "UNMEASURED", detail="source recent.json is not a list")
    cursors = sorted(feed_delta.cursor_of(r) for r in recent
                     if isinstance(r, dict) and feed_delta.landing_key(r))
    if not cursors:
        return row(rel, "UNMEASURED", detail="recent.json holds no dated event")
    source = cursors[-1]
    source_t = _cursor_time(source)
    if shard_why:
        # The shard itself is gone while its source exists: every reader of the
        # delta protocol is being told nothing. That is a gap, not an unknown.
        return row(rel, "GAP", _iso(source_t), None, None, len(cursors),
                   "sink " + shard_why)
    covers = (shard.get("covers") or {}) if isinstance(shard, dict) else {}
    newest = str(covers.get("newest") or "")
    newest_t = _cursor_time(newest)
    behind = sum(1 for c in cursors if c > newest) if newest else len(cursors)
    gap = (max(0, int((source_t - newest_t).total_seconds()))
           if source_t and newest_t else None)
    detail = ("newest in shard %s; newest in recent.json %s" % (newest or "none",
                                                                 source))
    return row(rel, "GAP" if behind else "SYNCED", _iso(source_t),
               _iso(newest_t), gap if behind else 0, behind, detail)


def seats_row(posts, posts_why, seats, seats_why):
    if posts_why:
        return row("seats.json", "UNMEASURED", detail="source " + posts_why)
    if not isinstance(posts, list):
        return row("seats.json", "UNMEASURED", detail="posts.json is not a list")
    if seats_why:
        return row("seats.json", "GAP", missing=len(posts),
                   detail="sink " + seats_why)
    read = ((seats.get("inputs") or {}).get("posts.json") or {}) \
        if isinstance(seats, dict) else {}
    if read.get("state") != "READ" or not isinstance(read.get("rows"), int):
        return row("seats.json", "UNMEASURED",
                   detail="seats.json does not record which posts.json it read")
    missing = len(posts) - read["rows"]
    return row("seats.json", "GAP" if missing else "SYNCED",
               None, (seats.get("reference_time") or None), None, abs(missing),
               "posts.json rows %d; census read %d" % (len(posts), read["rows"]))


def _slack_landed(posts, channel):
    prefix = "slack:%s:" % channel
    newest, count = None, 0
    for rec in posts if isinstance(posts, list) else []:
        if not isinstance(rec, dict):
            continue
        event = str(rec.get("observed_event") or "").strip().strip('"')
        if not event.startswith(prefix):
            continue
        moment = _parse_ts(event[len(prefix):].split(":", 1)[0])
        if moment:
            count += 1
            newest = moment if newest is None or moment > newest else newest
    return newest, count


def read_observations(root):
    out = {}
    pattern = os.path.join(root, OBSERVATIONS, "*.json")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("sink"):
            out[str(doc["sink"])] = doc
    return out


def slack_row(posts, posts_why, observation, now, channel=COMMONS_CHANNEL):
    name = "slack:%s" % channel
    if posts_why:
        return row(name, "UNMEASURED", detail="durable side " + posts_why)
    landed, count = _slack_landed(posts, channel)
    base = "%d landed posts carry a %s observed_event" % (count, name)
    if not observation:
        return row(name, "UNMEASURED", None, _iso(landed), None, None,
                   base + "; no source observation, and a bake cannot read Slack")
    seen = _parse_ts(observation.get("observed_at"))
    if not seen or not now:
        return row(name, "UNMEASURED", None, _iso(landed), None, None,
                   base + "; source observation missing observed_at or current clock")
    age = (now - seen).total_seconds()
    if age < -OBSERVATION_FUTURE_SKEW_S:
        return row(name, "UNMEASURED", None, _iso(landed), None, None,
                   base + "; source observation observed_at is more than %d s "
                   "in the future" % OBSERVATION_FUTURE_SKEW_S)
    if age > OBSERVATION_MAX_AGE_S:
        return row(name, "UNMEASURED", None, _iso(landed), None, None,
                   base + "; source observation missing observed_at or older "
                   "than %d s" % OBSERVATION_MAX_AGE_S)
    source = _parse_ts(observation.get("latest_source_ts"))
    if not source:
        return row(name, "UNMEASURED", None, _iso(landed), None, None,
                   base + "; source observation has no readable latest_source_ts")
    gap = max(0, int((source - landed).total_seconds())) if landed else None
    stale = landed is None or gap > SLACK_STALE_S
    return row(name, "STALE" if stale else "SYNCED", _iso(source), _iso(landed),
               gap, None, base + "; observed by %s at %s" % (
                   observation.get("observer") or "UNKNOWN", _iso(seen)))


def build(root=ROOT, now=None):
    recent, recent_why = _load(root, "recent.json")
    head, head_why = _load(root, "feed/head.json")
    window, window_why = _load(root, "feed/window.json")
    posts, posts_why = _load(root, "posts.json")
    seats, seats_why = _load(root, "seats.json")
    pulse, _ = _load(root, "pulse.json")
    pulse = pulse if isinstance(pulse, dict) else {}
    moment = _parse_ts(now) if now else _parse_ts(pulse.get("ts"))
    observations = read_observations(root)
    sinks = [
        shard_row("feed/head.json", recent, recent_why, head, head_why),
        shard_row("feed/window.json", recent, recent_why, window, window_why),
        seats_row(posts, posts_why, seats, seats_why),
        slack_row(posts, posts_why,
                  observations.get("slack:%s" % COMMONS_CHANNEL), moment),
    ]
    return {
        "schema": SCHEMA,
        # The bake's own clock, so a rebuild over unchanged files is identical.
        "generated_at": _iso(moment),
        "source_sha": pulse.get("head") or None,
        "states": "STALE and GAP alarm; SYNCED and UNMEASURED stay quiet. "
                  "Unknown is never reported healthy.",
        "sinks": sinks,
    }


def write(root=ROOT, now=None):
    payload = build(root, now)
    blob = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with open(os.path.join(root, OUT), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(blob)
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--write", action="store_true", help="write sync.json")
    ap.add_argument("--now", help="ISO-8601 clock for observation freshness")
    args = ap.parse_args(argv)
    payload = write(args.root, args.now) if args.write else build(args.root, args.now)
    for sink in payload["sinks"]:
        print("%-18s %-10s missing=%s gap_s=%s  %s" % (
            sink["name"], sink["state"], sink["missing_count"],
            sink["gap_seconds"], sink["detail"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
