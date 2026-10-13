#!/usr/bin/env python3
"""Emit conservative lane events when a coordination root tip moves.

Consumes two `coordination.json` snapshots from host/coordination_state.py.
For each branch tip that changed, every current open lane rooted there receives
one event. Only B1 statuses that prove composition (`current`, `disjoint`, or
`contained`) become DISJOINT_OK. Any overlap becomes REBIND_REQUIRED. Missing,
unknown, malformed, or mixed evidence remains UNKNOWN rather than being treated
as safe.

Optional B6 path-move certificates (``attach_path_move_certificates``) annotate
events via ``host.generated_path_move_certificate.build_certificate``. Certificates
never override event.state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict

STATE_SCHEMA = "commons-coordination-state/v1"
OUT_SCHEMA = "commons-root-move-events/v1"
UNKNOWN = "UNKNOWN"
_SAFE_DRIFT = {"current", "disjoint", "contained"}
_KNOWN_DRIFT = _SAFE_DRIFT | {"overlap", "unknown"}


class InputError(ValueError):
    pass


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


def _validate_sha(value, name):
    if value == UNKNOWN:
        return value
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdefABCDEF" for c in value):
        raise InputError("%s must be a 40-hex SHA or UNKNOWN" % name)
    return value.lower()


def _tip_map(doc, name):
    tips = doc.get("tips")
    if not isinstance(tips, dict):
        raise InputError("%s.tips must be an object" % name)
    out = {}
    for branch, sha in tips.items():
        if not isinstance(branch, str) or not branch:
            raise InputError("%s.tips has invalid branch" % name)
        out[branch] = _validate_sha(sha, "%s.tips[%s]" % (name, branch))
    return out


def _validate_snapshot(doc, name):
    if not isinstance(doc, dict) or doc.get("schema") != STATE_SCHEMA:
        raise InputError("%s must use schema %s" % (name, STATE_SCHEMA))
    observed = _parse_time(doc.get("observed_at"), name + ".observed_at")
    tips = _tip_map(doc, name)
    prs = doc.get("prs")
    if not isinstance(prs, list):
        raise InputError("%s.prs must be a list" % name)
    seen = set()
    clean = []
    for i, row in enumerate(prs):
        label = "%s.prs[%d]" % (name, i)
        if not isinstance(row, dict):
            raise InputError(label + " must be an object")
        number = row.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise InputError(label + ".number must be a positive integer")
        if number in seen:
            raise InputError("%s has duplicate PR number %d" % (name, number))
        seen.add(number)
        base_ref = row.get("base_ref")
        if not isinstance(base_ref, str) or not base_ref:
            raise InputError(label + ".base_ref must be a nonempty string")
        lane = row.get("lane")
        if lane is not None and (not isinstance(lane, str) or not lane):
            raise InputError(label + ".lane must be a nonempty string when present")
        drift = row.get("drift")
        if not isinstance(drift, dict):
            drift = {"status": "unknown", "reason": "missing drift object"}
        status = drift.get("status")
        if status not in _KNOWN_DRIFT:
            status = "unknown"
        clean.append({
            "number": number,
            "base_ref": base_ref,
            "lane": lane or "pr-%d" % number,
            "drift_status": status,
            "drift_reason": drift.get("reason") if isinstance(drift.get("reason"), str) else "",
            "head": row.get("head") if isinstance(row.get("head"), str) else UNKNOWN,
        })
    return observed, tips, clean


def _require_complete_open_listing(doc, name):
    """Bind positive lane events to a complete current open-PR census."""
    degraded = doc.get("degraded")
    if not isinstance(degraded, list) or any(type(item) is not str for item in degraded):
        raise InputError("%s.degraded must be a list of strings" % name)
    if "open-listing-partial" in degraded:
        raise InputError("%s open-PR listing is partial" % name)

    counts = doc.get("counts")
    if not isinstance(counts, dict):
        raise InputError("%s.counts must be an object" % name)
    values = {}
    for field in ("open_prs", "listed_open"):
        value = counts.get(field)
        if type(value) is not int or value < 0:
            raise InputError("%s.counts.%s must be a nonnegative exact integer" % (name, field))
        values[field] = value
    if values["open_prs"] != values["listed_open"]:
        raise InputError(
            "%s open-PR listing incomplete: open_prs=%d listed_open=%d"
            % (name, values["open_prs"], values["listed_open"])
        )

    listed_rows = doc.get("prs")
    if not isinstance(listed_rows, list):
        raise InputError("%s.prs must be a list" % name)
    if values["listed_open"] != len(listed_rows):
        raise InputError(
            "%s open-PR listing incomplete: listed_open=%d observed_rows=%d"
            % (name, values["listed_open"], len(listed_rows))
        )


def reduce_root_moves(previous, current):
    prev_at, prev_tips, _prev_prs = _validate_snapshot(previous, "previous")
    cur_at, cur_tips, cur_prs = _validate_snapshot(current, "current")
    _require_complete_open_listing(current, "current")
    if cur_at <= prev_at:
        raise InputError("current.observed_at must be later than previous.observed_at")

    roots = sorted(set(prev_tips) | set(cur_tips))
    moves = []
    for root in roots:
        old = prev_tips.get(root, UNKNOWN)
        new = cur_tips.get(root, UNKNOWN)
        if old == new:
            continue
        # A missing/UNKNOWN endpoint is a root observation problem, not proof of a move.
        if old == UNKNOWN or new == UNKNOWN:
            move_state = UNKNOWN
            move_reason = "root tip missing or UNKNOWN in one snapshot"
        else:
            move_state = "MOVED"
            move_reason = "tip changed"
        moves.append({"base_ref": root, "old_tip": old, "new_tip": new,
                      "state": move_state, "reason": move_reason})

    grouped = defaultdict(list)
    for row in cur_prs:
        grouped[(row["base_ref"], row["lane"])].append(row)

    events = []
    moved_by_root = {m["base_ref"]: m for m in moves}
    for (root, lane), members in sorted(grouped.items()):
        move = moved_by_root.get(root)
        if move is None:
            continue
        statuses = sorted({m["drift_status"] for m in members})
        if move["state"] == UNKNOWN:
            event_state = UNKNOWN
            reason = move["reason"]
        elif "overlap" in statuses:
            event_state = "REBIND_REQUIRED"
            reason = "at least one lane member overlaps the moved root"
        elif all(s in _SAFE_DRIFT for s in statuses):
            event_state = "DISJOINT_OK"
            reason = "all lane members are current/disjoint/contained against the moved root"
        else:
            event_state = UNKNOWN
            reason = "at least one lane member lacks a decisive B1 drift certificate"
        events.append({
            "base_ref": root,
            "old_tip": move["old_tip"],
            "new_tip": move["new_tip"],
            "lane": lane,
            "members": sorted(m["number"] for m in members),
            "member_heads": sorted({m["head"] for m in members}),
            "drift_statuses": statuses,
            "state": event_state,
            "reason": reason,
        })

    return {
        "schema": OUT_SCHEMA,
        "previous_observed_at": previous["observed_at"],
        "current_observed_at": current["observed_at"],
        "roots": moves,
        "events": events,
        "counts": {
            "roots_moved_or_unknown": len(moves),
            "events": len(events),
            "disjoint_ok": sum(e["state"] == "DISJOINT_OK" for e in events),
            "rebind_required": sum(e["state"] == "REBIND_REQUIRED" for e in events),
            "unknown": sum(e["state"] == UNKNOWN for e in events),
        },
    }


def _load_certificate_api():
    """Import B6 certificate builder with repo-root on path (script + package)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from host.generated_path_move_certificate import (  # type: ignore
            SCHEMA as CERT_SCHEMA,
            CertificateError,
            build_certificate,
        )
    except ImportError as exc:  # pragma: no cover
        raise InputError("generated_path_move_certificate unavailable: %s" % exc) from exc
    return CERT_SCHEMA, CertificateError, build_certificate


def attach_path_move_certificates(root_move_doc, paths_by_lane):
    """Attach B6 path-move certificates to root-move events (additive consumer).

    ``paths_by_lane`` maps lane id -> iterable of repository-relative changed
    paths for that lane. Certificates annotate events; they never override
    ``event.state``. Unknown lane keys refuse closed. Lanes omitted from the
    mapping stay unannotated (no ``path_move_certificate`` key).
    """
    if not isinstance(root_move_doc, dict) or root_move_doc.get("schema") != OUT_SCHEMA:
        raise InputError("root_move_doc must use schema %s" % OUT_SCHEMA)
    if not isinstance(paths_by_lane, dict) or isinstance(paths_by_lane, (str, bytes)):
        raise InputError("paths_by_lane must be an object mapping lane -> paths")
    for key in paths_by_lane:
        if type(key) is not str or not key:
            raise InputError("paths_by_lane keys must be nonempty strings")

    events = root_move_doc.get("events")
    if not isinstance(events, list):
        raise InputError("root_move_doc.events must be a list")

    event_lanes = {e.get("lane") for e in events if isinstance(e, dict)}
    unknown = sorted(set(paths_by_lane) - event_lanes)
    if unknown:
        raise InputError("paths_by_lane has unknown lanes: %s" % ", ".join(unknown))

    cert_schema, CertificateError, build_certificate = _load_certificate_api()

    out_events = []
    attached = 0
    for event in events:
        if not isinstance(event, dict):
            raise InputError("root_move_doc.events members must be objects")
        cloned = dict(event)
        lane = cloned.get("lane")
        if lane in paths_by_lane:
            paths = paths_by_lane[lane]
            statuses = cloned.get("drift_statuses")
            drift_status = None
            if isinstance(statuses, list) and len(statuses) == 1 and type(statuses[0]) is str:
                drift_status = statuses[0]
            custody = {
                "lane": lane,
                "members": list(cloned.get("members") or []),
                "root_move_state": cloned.get("state"),
                "source": "coordination_root_move_events",
            }
            try:
                cert = build_certificate(
                    paths,
                    custody=custody,
                    drift_status=drift_status,
                    base_ref=cloned.get("base_ref"),
                    head=cloned.get("new_tip"),
                )
            except CertificateError as exc:
                raise InputError("path certificate refused for lane %s: %s" % (lane, exc)) from exc
            except ValueError as exc:
                raise InputError("path certificate refused for lane %s: %s" % (lane, exc)) from exc
            if cert.get("schema") != cert_schema:
                raise InputError("path certificate schema mismatch for lane %s" % lane)
            cloned["path_move_certificate"] = cert
            attached += 1
        out_events.append(cloned)

    counts = dict(root_move_doc.get("counts") or {})
    counts["path_certificates"] = attached
    out = dict(root_move_doc)
    out["events"] = out_events
    out["counts"] = counts
    return out


def _load(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emit conservative root-move events from two coordination snapshots")
    ap.add_argument("--previous", required=True, help="older coordination.json")
    ap.add_argument("--current", required=True, help="newer coordination.json")
    ap.add_argument(
        "--path-sets",
        default=None,
        help="optional JSON object mapping lane -> changed paths; attaches B6 path-move certificates",
    )
    args = ap.parse_args(argv)
    if args.previous == "-" and args.current == "-":
        ap.error("only one input may use stdin")
    try:
        result = reduce_root_moves(_load(args.previous), _load(args.current))
        if args.path_sets is not None:
            result = attach_path_move_certificates(result, _load(args.path_sets))
    except (InputError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("root-move-events: %s\n" % exc)
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
