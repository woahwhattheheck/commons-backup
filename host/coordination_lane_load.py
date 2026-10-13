#!/usr/bin/env python3
"""Reduce coordination holdings into a conservative per-lane load signal.

This is the additive A3 slice from ground/COMMONS_VISIBILITY_PLAN.md. It consumes
`coordination-lanes.json` plus the JSON emitted by `coordination_state.py holders`
and reports unique active holders per lane inside a declared lookback window.
Malformed evidence never becomes zero: if a holding maps to a lane but its state,
`live` bit, holder, heartbeat, or TTL is unreadable, that lane's load is UNKNOWN.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict

LANES_SCHEMA = "commons-coordination-lanes/v1"
OUT_SCHEMA = "commons-coordination-lane-load/v1"
UNKNOWN = "UNKNOWN"
_KEY_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PR_RE = re.compile(r"^pr-(\d+)$")
_CK_RE = re.compile(r"^ck-([0-9a-f]{4,64})$")


class InputError(ValueError):
    pass


def _strict_int(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError("%s must be an integer, not bool/coercible text" % name)
    if minimum is not None and value < minimum:
        raise InputError("%s must be >= %d" % (name, minimum))
    return value


def _parse_time(value, name):
    if not isinstance(value, str) or not value.strip():
        raise InputError("%s must be a nonempty ISO-8601 string" % name)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InputError("%s is not valid ISO-8601" % name) from exc
    if parsed.tzinfo is None:
        raise InputError("%s must include a timezone" % name)
    return parsed.astimezone(dt.timezone.utc)


def _iso(moment):
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _family_key(value):
    return _KEY_RE.sub("-", value or "").strip("-").lower()[:96]


def _lane_indexes(lanes_doc):
    if not isinstance(lanes_doc, dict) or lanes_doc.get("schema") != LANES_SCHEMA:
        raise InputError("lanes document must use %s" % LANES_SCHEMA)
    lanes = lanes_doc.get("lanes")
    if not isinstance(lanes, list):
        raise InputError("lanes must be a list")
    by_pr = defaultdict(set)
    by_ck = defaultdict(set)
    by_family = defaultdict(set)
    records = {}
    for i, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise InputError("lane[%d] must be an object" % i)
        lane_id = lane.get("lane")
        if not isinstance(lane_id, str) or not lane_id:
            raise InputError("lane[%d].lane must be a nonempty string" % i)
        if lane_id in records:
            raise InputError("duplicate lane id %s" % lane_id)
        chain = lane.get("chain")
        if not isinstance(chain, list):
            raise InputError("%s.chain must be a list" % lane_id)
        clean_chain = []
        for n in chain:
            clean_chain.append(_strict_int(n, "%s.chain[]" % lane_id, 1))
            by_pr[n].add(lane_id)
        content_keys = lane.get("content_keys") or []
        if not isinstance(content_keys, list):
            raise InputError("%s.content_keys must be a list" % lane_id)
        clean_ck = []
        for key in content_keys:
            if not isinstance(key, str) or not re.fullmatch(r"[0-9a-fA-F]{4,64}", key):
                raise InputError("%s has invalid content key" % lane_id)
            key = key.lower()
            clean_ck.append(key)
            by_ck[key].add(lane_id)
        families = lane.get("families") or []
        if not isinstance(families, list):
            raise InputError("%s.families must be a list" % lane_id)
        clean_families = []
        for family in families:
            if not isinstance(family, str) or not family:
                raise InputError("%s has invalid family" % lane_id)
            token = _family_key(family)
            if not token:
                raise InputError("%s has empty normalized family" % lane_id)
            clean_families.append(token)
            by_family[token].add(lane_id)
        records[lane_id] = {
            "lane": lane_id,
            "canonical": lane.get("canonical"),
            "state": lane.get("state"),
            "open": list(lane.get("open") or []),
            "chain": clean_chain,
            "content_keys": clean_ck,
            "families": clean_families,
            "title": lane.get("title") or "",
        }
    return records, by_pr, by_ck, by_family


def _resolve_key(key, by_pr, by_ck, by_family):
    if not isinstance(key, str) or not key:
        return set(), "invalid-key"
    m = _PR_RE.fullmatch(key)
    if m:
        return set(by_pr.get(int(m.group(1)), set())), "pr"
    m = _CK_RE.fullmatch(key)
    if m:
        prefix = m.group(1)
        matches = set()
        for content, lane_ids in by_ck.items():
            if content.startswith(prefix) or prefix.startswith(content):
                matches.update(lane_ids)
        return matches, "content"
    return set(by_family.get(_family_key(key), set())), "family"


def reduce_lane_load(lanes_doc, holdings_doc, *, now, window_s=900,
                     incoming_holder=None, warn_at=4):
    """Return a conservative load signal.

    `active_count` is an integer only when every holding that maps to that lane
    is interpretable. A malformed mapped holding makes the lane UNKNOWN rather
    than silently reducing its count. Unmatched keys are surfaced separately.
    """
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise InputError("now must be timezone-aware datetime")
    now = now.astimezone(dt.timezone.utc)
    window_s = _strict_int(window_s, "window_s", 1)
    warn_at = _strict_int(warn_at, "warn_at", 1)
    if incoming_holder is not None and (not isinstance(incoming_holder, str) or not incoming_holder):
        raise InputError("incoming_holder must be a nonempty string")
    records, by_pr, by_ck, by_family = _lane_indexes(lanes_doc)
    if not isinstance(holdings_doc, dict) or not isinstance(holdings_doc.get("holdings"), list):
        raise InputError("holdings document must contain a holdings list")

    active = defaultdict(set)
    poisoned = defaultdict(list)
    matched_keys = defaultdict(list)
    unmatched = []
    ambiguous = []

    for idx, row in enumerate(holdings_doc["holdings"]):
        label = "holdings[%d]" % idx
        if not isinstance(row, dict):
            unmatched.append({"index": idx, "key": UNKNOWN, "reason": "not-an-object"})
            continue
        key = row.get("key")
        lane_ids, via = _resolve_key(key, by_pr, by_ck, by_family)
        if not lane_ids:
            unmatched.append({"index": idx, "key": key if isinstance(key, str) else UNKNOWN,
                              "reason": "no-lane-match"})
            continue
        if len(lane_ids) > 1:
            item = {"index": idx, "key": key, "lanes": sorted(lane_ids),
                    "reason": "ambiguous-lane-match"}
            ambiguous.append(item)
            for lane_id in lane_ids:
                poisoned[lane_id].append(item)
            continue
        lane_id = next(iter(lane_ids))
        matched_keys[lane_id].append({"key": key, "via": via})

        holder = row.get("holder")
        state = row.get("state")
        live = row.get("live")
        heartbeat = row.get("heartbeat_at")
        ttl_s = row.get("ttl_s")
        malformed = []
        if not isinstance(holder, str) or not holder:
            malformed.append("holder")
        if state not in ("HELD", "RELEASED"):
            malformed.append("state")
        if type(live) is not bool:
            malformed.append("live")
        if type(ttl_s) is not int or ttl_s <= 0:
            malformed.append("ttl_s")
        try:
            beat = _parse_time(heartbeat, label + ".heartbeat_at")
        except InputError:
            beat = None
            malformed.append("heartbeat_at")
        if malformed:
            poisoned[lane_id].append({"index": idx, "key": key,
                                      "reason": "malformed-mapped-holding",
                                      "fields": sorted(set(malformed))})
            continue
        age = (now - beat).total_seconds()
        if age < -5:
            poisoned[lane_id].append({"index": idx, "key": key,
                                      "reason": "future-heartbeat"})
            continue
        lease_live = age <= ttl_s
        if live and state == "HELD" and lease_live and age <= window_s:
            active[lane_id].add(holder)

    out_rows = []
    for lane_id in sorted(records):
        base = records[lane_id]
        holders = sorted(active.get(lane_id, set()))
        problems = poisoned.get(lane_id, [])
        if problems:
            count = UNKNOWN
            would_be = UNKNOWN
            signal = "UNKNOWN"
        else:
            count = len(holders)
            would_be = count + (1 if incoming_holder and incoming_holder not in holders else 0)
            signal = ("WOULD_BE_%d_OR_MORE" % warn_at
                      if incoming_holder and would_be >= warn_at else "CLEAR")
        out_rows.append({
            "lane": lane_id,
            "canonical": base["canonical"],
            "state": base["state"],
            "open": base["open"],
            "title": base["title"],
            "active_holders": holders,
            "active_count": count,
            "incoming_holder": incoming_holder if incoming_holder is not None else UNKNOWN,
            "would_be_count": would_be,
            "signal": signal,
            "matched_keys": matched_keys.get(lane_id, []),
            "problems": problems,
        })

    return {
        "schema": OUT_SCHEMA,
        "observed_at": _iso(now),
        "window_s": window_s,
        "warn_at": warn_at,
        "source": {
            "lanes_schema": lanes_doc.get("schema"),
            "lanes_observed_at": lanes_doc.get("observed_at", UNKNOWN),
            "holdings_branch": holdings_doc.get("branch", UNKNOWN),
            "holdings_tip": holdings_doc.get("tip", UNKNOWN),
        },
        "lanes": out_rows,
        "unmatched_holdings": unmatched,
        "ambiguous_holdings": ambiguous,
    }


def _load(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Conservative active-holder load per coordination lane")
    ap.add_argument("--lanes", required=True, help="coordination-lanes.json")
    ap.add_argument("--holdings", required=True, help="JSON emitted by coordination_state.py holders")
    ap.add_argument("--window", type=int, default=900, help="heartbeat lookback seconds (default 900)")
    ap.add_argument("--warn-at", type=int, default=4, help="warn when incoming holder reaches this count")
    ap.add_argument("--holder", default=None, help="prospective holder name; enables would-be warning")
    ap.add_argument("--now", default=None, help="ISO-8601 clock for deterministic replay")
    args = ap.parse_args(argv)
    if args.lanes == "-" and args.holdings == "-":
        ap.error("only one input may use stdin")
    now = _parse_time(args.now, "--now") if args.now else dt.datetime.now(dt.timezone.utc)
    try:
        result = reduce_lane_load(_load(args.lanes), _load(args.holdings), now=now,
                                  window_s=args.window, incoming_holder=args.holder,
                                  warn_at=args.warn_at)
    except (InputError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("lane-load: %s\n" % exc)
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
