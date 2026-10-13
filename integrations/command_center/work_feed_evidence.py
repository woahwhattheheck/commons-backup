"""Read-only work-feed evidence composition; routing stays in swarm_channel_dispatch.

Normalized exports are caller-supplied observations, NOT authenticated provider truth.
There is no network client, scheduler, claim mutation, or automatic dispatch here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from host.swarm_channel_dispatch import compile_dispatch

SCHEMA = "commons.work_feed_evidence/v1"
REPORT_SCHEMA = "commons.work_feed_evidence.report/v1"
PROVIDERS = {"slack", "github", "claims"}
KINDS = {"slack": {"MESSAGE", "DEMAND", "SHIP"},
         "github": {"OPEN", "CLOSED"}, "claims": {"CLAIM", "RENEW", "RELEASE"}}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}\Z")
MAX_BYTES = 4 * 1024 * 1024
AUTHORITY = {key: False for key in (
    "claim_authority", "send_authority", "merge_authority", "provider_authority",
    "payment_authority", "source_authenticity_attested",
    "source_completeness_independently_proven")}


class EvidenceError(ValueError):
    """Malformed, ambiguous or out-of-range observation input."""


def _canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise EvidenceError("not canonical JSON data") from exc


def _digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _bounded(obj: Any) -> None:
    stack = [(obj, 0)]; count = 0
    while stack:
        value, depth = stack.pop(); count += 1
        if depth > 24 or count > 200000:
            raise EvidenceError("JSON depth/node limit exceeded")
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise EvidenceError("object keys must be strings")
            stack.extend((key, depth + 1) for key in value)
            stack.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is str:
            if len(value) > 2048:
                raise EvidenceError("string limit exceeded")
            try:
                value.encode("utf-8")
            except UnicodeError as exc:
                raise EvidenceError("invalid Unicode") from exc
        elif value is None or type(value) is bool:
            pass
        elif type(value) is int and -(2**63) <= value < 2**63:
            pass
        else:
            raise EvidenceError("only bounded integer JSON is supported")
    if len(_canonical(obj)) > MAX_BYTES:
        raise EvidenceError("input byte limit exceeded")


def load_json(data: bytes | str) -> Any:
    """Strict, bounded ingress shared by CLI and the command-center preview route."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceError("duplicate JSON key")
            result[key] = value
        return result
    try:
        if isinstance(data, bytes):
            if len(data) > MAX_BYTES:
                raise EvidenceError("input byte limit exceeded")
            data = data.decode("utf-8")
        if not isinstance(data, str) or len(data.encode("utf-8")) > MAX_BYTES:
            raise EvidenceError("input byte limit exceeded")
        result = json.loads(data, object_pairs_hook=pairs)
        _bounded(result)
        return result
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EvidenceError("invalid JSON") from exc


def _fields(obj, names, where):
    if type(obj) is not dict or set(obj) != set(names.split()):
        raise EvidenceError(f"{where}: unexpected or missing fields")
    return obj


def _token(value):
    if type(value) is not str or TOKEN.fullmatch(value) is None:
        raise EvidenceError("invalid identifier")
    return value


def _integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise EvidenceError("integer out of range")
    return value


def _rows(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise EvidenceError("invalid or oversized row list")
    return value


def _time(value):
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None:
        raise EvidenceError("timestamp must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError("invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise EvidenceError("timestamp is not UTC")
    return parsed


def _stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _tags(value, empty=False):
    rows = _rows(value, 64)
    if (not rows and not empty) or any(not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,63}", str(t)) or type(t) is not str for t in rows):
        raise EvidenceError("invalid tags")
    if len(set(rows)) != len(rows):
        raise EvidenceError("duplicate tags")
    return sorted(rows)


def _normalize(packet):
    """Validate exports and collapse exact duplicated records before aggregation."""
    _bounded(packet)
    root = _fields(packet, "schema snapshot_id max_source_age_seconds channels sources events aliases", "packet")
    if root["schema"] != SCHEMA:
        raise EvidenceError("unsupported schema")
    result = {"schema": SCHEMA, "snapshot_id": _token(root["snapshot_id"]),
              "max_source_age_seconds": _integer(root["max_source_age_seconds"], 1, 3600)}
    channels = {}; names = set()
    for raw in _rows(root["channels"], 512):
        row = dict(_fields(raw, "channel_id name specialty_tags capacity paused required_sources", "channel"))
        cid = _token(row["channel_id"])
        if cid in channels or row["name"] in names:
            raise EvidenceError("duplicate channel")
        if type(row["name"]) is not str or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", row["name"]) is None:
            raise EvidenceError("invalid channel name")
        names.add(row["name"])
        row["specialty_tags"] = _tags(row["specialty_tags"])
        _integer(row["capacity"], 0, 100000)
        if type(row["paused"]) is not bool:
            raise EvidenceError("paused must be boolean")
        _fields(row["required_sources"], "slack github claims", "required_sources")
        row["required_sources"] = dict(row["required_sources"])
        for sid in row["required_sources"].values():
            _token(sid)
        channels[cid] = row
    if not channels:
        raise EvidenceError("at least one channel required")
    sources = {}
    for raw in _rows(root["sources"], 1536):
        row = dict(_fields(raw, "source_id provider scope observed_at window_start complete", "source"))
        sid = _token(row["source_id"])
        if sid in sources or row["provider"] not in PROVIDERS or type(row["complete"]) is not bool:
            raise EvidenceError("duplicate or invalid source")
        scopes = _rows(row["scope"], 512)
        if not scopes or any(cid not in channels for cid in scopes) or len(set(scopes)) != len(scopes):
            raise EvidenceError("invalid source scope")
        row["scope"] = sorted(scopes)
        row["observed_at"] = _stamp(_time(row["observed_at"]))
        row["window_start"] = _stamp(_time(row["window_start"]))
        if _time(row["window_start"]) > _time(row["observed_at"]):
            raise EvidenceError("reversed source window")
        sources[sid] = row
    events = {}; repeats = 0
    for raw in _rows(root["events"], 16384):
        row = dict(_fields(raw, "source_id event_id at channel_id operation_id kind tags priority holder claim_id lease_until ref", "event"))
        sid = _token(row["source_id"]); eid = _token(row["event_id"])
        source = sources.get(sid)
        if not source or row["channel_id"] not in source["scope"] or row["kind"] not in KINDS[source["provider"]]:
            raise EvidenceError("event outside provider/scope")
        row["at"] = _stamp(_time(row["at"]))
        if not _time(source["window_start"]) <= _time(row["at"]) <= _time(source["observed_at"]):
            raise EvidenceError("event outside declared source window")
        message = row["kind"] == "MESSAGE"
        if message:
            if row["operation_id"] != "":
                raise EvidenceError("MESSAGE does not declare an operation")
        else:
            _token(row["operation_id"])
        row["tags"] = _tags(row["tags"], empty=message or source["provider"] == "claims")
        _integer(row["priority"], 0, 100)
        if type(row["ref"]) is not str or not row["ref"] or len(row["ref"]) > 1024 or any(ord(c) < 32 for c in row["ref"]):
            raise EvidenceError("invalid source reference")
        if source["provider"] == "claims":
            _token(row["holder"]); _token(row["claim_id"])
            if row["kind"] != "RELEASE":
                row["lease_until"] = _stamp(_time(row["lease_until"]))
                if _time(row["lease_until"]) <= _time(row["at"]):
                    raise EvidenceError("lease must extend beyond its event")
            elif row["lease_until"] is not None:
                raise EvidenceError("RELEASE cannot set a lease")
        elif row["holder"] != "" or row["claim_id"] != "" or row["lease_until"] is not None:
            raise EvidenceError("non-ledger event cannot claim or release work")
        key = (sid, eid)
        if key in events:
            if events[key] != row:
                raise EvidenceError("same source event identity has different bytes")
            repeats += 1
        events[key] = row
    aliases = {}
    for raw in _rows(root["aliases"], 4096):
        row = _fields(raw, "alias operation_id ref", "alias")
        alias = _token(row["alias"]); target = _token(row["operation_id"])
        if alias == target or alias in aliases or type(row["ref"]) is not str or not row["ref"]:
            raise EvidenceError("invalid or repeated alias")
        aliases[alias] = dict(row)
    roots = {}
    def resolve(op):
        seen = set(); trail = []
        while op in aliases and op not in roots:
            if op in seen:
                raise EvidenceError("alias cycle")
            seen.add(op); trail.append(op); op = aliases[op]["operation_id"]
        op = roots.get(op, op)
        for alias in trail:
            roots[alias] = op
        return op
    for alias in aliases:
        resolve(alias)
    claim_ops = {}; provider_events = {}
    for row in events.values():
        provider = sources[row["source_id"]]["provider"]
        pkey = (provider, row["channel_id"], row["event_id"])
        meaning = {k: v for k, v in row.items() if k not in {"source_id", "ref"}}
        if pkey in provider_events and provider_events[pkey] != meaning:
            raise EvidenceError("provider event identity contradicts another export")
        provider_events[pkey] = meaning
        if provider == "claims":
            op = resolve(row["operation_id"]); claim = row["claim_id"]
            if claim in claim_ops and claim_ops[claim] != op:
                raise EvidenceError("claim identity transplanted across operations")
            claim_ops[claim] = op
    result.update(channels=sorted(channels.values(), key=lambda r: r["channel_id"]),
                  sources=sorted(sources.values(), key=lambda r: r["source_id"]),
                  events=sorted(events.values(), key=lambda r: (r["source_id"], r["event_id"])),
                  aliases=sorted(aliases.values(), key=lambda r: r["alias"]))
    return result, resolve, repeats


def normalize(packet):
    """Return detached normalized values; malformed types fail as EvidenceError."""
    try:
        return _normalize(packet)
    except (TypeError, KeyError, OverflowError) as exc:
        raise EvidenceError("invalid structured field type") from exc


def _compile(packet, at, mode):
    data, resolve, repeats = normalize(packet)
    now = _time(at); channels = {r["channel_id"]: r for r in data["channels"]}
    sources = {r["source_id"]: r for r in data["sources"]}
    start = now - timedelta(seconds=900)
    source_reasons = {}
    for sid, row in sources.items():
        observed = _time(row["observed_at"])
        if observed > now:
            raise EvidenceError("future source observation")
        reasons = []
        if not row["complete"]:
            reasons.append("DECLARED_PARTIAL")
        if (now - observed).total_seconds() > data["max_source_age_seconds"]:
            reasons.append("STALE_SOURCE")
        if row["provider"] == "slack" and _time(row["window_start"]) > start:
            reasons.append("TRAFFIC_WINDOW_INCOMPLETE")
        source_reasons[sid] = reasons
    diagnostics = {}
    for cid, row in channels.items():
        reasons = []
        for provider, sid in sorted(row["required_sources"].items()):
            source = sources.get(sid)
            if not source:
                reasons.append(f"MISSING_SOURCE:{sid}")
            elif source["provider"] != provider or cid not in source["scope"]:
                reasons.append(f"SOURCE_SCOPE_MISMATCH:{sid}")
            else:
                reasons.extend(f"{reason}:{sid}" for reason in source_reasons[sid])
        diagnostics[cid] = {"channel_id": cid, "reasons": sorted(reasons),
                            "messages_observed_15m": 0, "unreleased_claim_slots": 0,
                            "stale_claim_slots": 0, "candidate_operations": 0}
    grouped = defaultdict(list); traffic_seen = set()
    # Slack messages are deduplicated by source/event ID before this count.
    for event in data["events"]:
        if sources[event["source_id"]]["provider"] == "slack" and start <= _time(event["at"]) <= now:
            traffic_key = (event["channel_id"], event["event_id"])
            if traffic_key not in traffic_seen:
                diagnostics[event["channel_id"]]["messages_observed_15m"] += 1
                traffic_seen.add(traffic_key)
        if event["operation_id"]:
            grouped[resolve(event["operation_id"])].append(event)
    if len(grouped) > 4096:
        raise EvidenceError("operation limit exceeded")
    operations = []; pending = []; slots = set(); stale_slots = set()
    for op, rows in sorted(grouped.items()):
        reasons = set(); latest = {}; claims = defaultdict(list)
        tags = set(); priorities = set(); refs = set(); origins = set()
        for row in rows:
            refs.add(row["ref"]); origins.add(row["operation_id"])
            sid = row["source_id"]
            if source_reasons[sid] or diagnostics[row["channel_id"]]["reasons"]:
                reasons.add("SOURCE_COVERAGE_DEGRADED")
            if row["kind"] in {"CLAIM", "RENEW", "RELEASE"}:
                claims[row["claim_id"]].append(row)
            else:
                key = sid
                old = latest.get(key)
                if old is None or row["at"] > old["at"]:
                    latest[key] = row
                elif row["at"] == old["at"] and (row["kind"], row["tags"], row["priority"]) != (old["kind"], old["tags"], old["priority"]):
                    reasons.add("SIMULTANEOUS_WORK_STATE_CONFLICT")
        for row in latest.values():
            tags.add(tuple(row["tags"])); priorities.add(row["priority"])
        if len(tags) > 1:
            reasons.add("TAG_CONFLICT")
        if len(priorities) > 1:
            reasons.add("PRIORITY_CONFLICT")
        active = set(); expired = set()
        for claim_id, history in sorted(claims.items()):
            history.sort(key=lambda r: (r["at"], r["source_id"], r["event_id"]))
            identity = {(r["holder"], r["channel_id"], resolve(r["operation_id"])) for r in history}
            if len(identity) != 1:
                reasons.add("CLAIM_IDENTITY_CONFLICT")
                # Preserve every possibly occupied slot; ambiguity is never idle capacity.
                active.update((holder, cid) for holder, cid, _ in identity)
                continue
            claim_problems = set()
            holder, cid, _ = next(iter(identity)); released = False; seen = False; lease = None; last_at = None; last_semantic = None
            for row in history:
                semantic = (row["kind"], row["lease_until"])
                if row["at"] == last_at:
                    if semantic != last_semantic:
                        claim_problems.add("SIMULTANEOUS_CLAIM_CONFLICT")
                    continue
                last_at, last_semantic = row["at"], semantic
                kind = row["kind"]
                if kind == "CLAIM":
                    if seen:
                        claim_problems.add("CLAIM_ID_REUSED")
                    seen = True; released = False; lease = _time(row["lease_until"])
                elif kind == "RENEW":
                    if not seen or released:
                        claim_problems.add("ORPHAN_OR_RELEASED_RENEWAL")
                    new_lease = _time(row["lease_until"])
                    if lease is not None and new_lease < lease:
                        claim_problems.add("LEASE_REGRESSION")
                    lease = new_lease; seen = True; released = False
                else:
                    if not seen:
                        claim_problems.add("ORPHAN_RELEASE")
                    released = True
            reasons.update(claim_problems)
            if not released or claim_problems:
                active.add((holder, cid))
                if lease is None or lease <= now:
                    expired.add((holder, cid))
        if len({holder for holder, _ in active}) > 1:
            reasons.add("MULTI_HOLDER")
        if expired:
            reasons.add("STALE_UNRELEASED_CLAIM")
        states = {r["kind"] in {"SHIP", "CLOSED"} for r in latest.values()}
        if len(states) > 1:
            reasons.add("WORK_STATE_CONFLICT")
        if not latest:
            reasons.add("ORPHAN_CLAIM")
        terminal = states == {True}
        if terminal and active:
            reasons.add("TERMINAL_WITH_UNRELEASED_CLAIM")
        tags_out = list(next(iter(tags))) if len(tags) == 1 else []
        priority = next(iter(priorities)) if len(priorities) == 1 else 0
        status = "HOLD" if reasons else "TERMINAL" if terminal else "CLAIMED" if active else "AVAILABLE"
        for holder, cid in active:
            slots.add((op, holder, cid))
        for holder, cid in expired:
            stale_slots.add((op, holder, cid))
        item = {"operation_id": op, "status": status, "tags": tags_out, "priority": priority,
                "holders": sorted({h for h, _ in active}), "reasons": sorted(reasons),
                "source_refs": sorted(refs), "observed_ids": sorted(origins)}
        operations.append(item)
        if status == "AVAILABLE":
            pending.append({"work_id": op, "tags": tags_out, "priority": priority})
    for op, holder, cid in slots:
        diagnostics[cid]["unreleased_claim_slots"] += 1
    for op, holder, cid in stale_slots:
        diagnostics[cid]["stale_claim_slots"] += 1
    dispatch_channels = []
    for cid, channel in sorted(channels.items()):
        diag = diagnostics[cid]
        diag["candidate_operations"] = sum(bool(set(w["tags"]) & set(channel["specialty_tags"])) for w in pending)
        diag["coverage"] = "DEGRADED" if diag["reasons"] else "COMPLETE_AS_DECLARED"
        dispatch_channels.append({"channel_id": cid, "name": channel["name"],
            "specialty_tags": channel["specialty_tags"], "capacity": channel["capacity"],
            "active_claims": diag["unreleased_claim_slots"],
            "messages_15m": diag["messages_observed_15m"],
            "verified_targets": diag["unreleased_claim_slots"] + diag["candidate_operations"],
            "paused": channel["paused"] or bool(diag["reasons"])})
    normalized = {"schema": "commons.swarm_channel_dispatch/v1",
                  "snapshot_id": data["snapshot_id"], "channels": dispatch_channels, "work_items": pending}
    dispatch = compile_dispatch(normalized)
    result = {"schema": REPORT_SCHEMA, "snapshot_id": data["snapshot_id"], "mode": mode,
        "evaluated_at": _stamp(now), "source_sha256": _digest(data),
        "authority": dict(AUTHORITY), "advisory_only": True,
        "source_observations": data["sources"], "alias_evidence": data["aliases"],
        "legacy_verified_targets_semantics": "OBSERVED_CANDIDATES_PLUS_OCCUPIED_SLOTS_NOT_PROVIDER_AUTHENTICATION",
        "input_posture": "CALLER_SUPPLIED_NORMALIZED_EXPORTS_NOT_PROVIDER_AUTHENTICATION",
        "duplicate_events_collapsed": repeats, "channel_diagnostics": list(diagnostics.values()),
        "operations": operations, "dispatch_snapshot": normalized, "dispatch": dispatch}
    result["report_sha256"] = _digest(result)
    return result


def _now():
    return _stamp(datetime.now(timezone.utc))


def compile_current(packet):
    """Sample process UTC. Does not fetch, authenticate or claim provider freshness."""
    return _compile(packet, _now(), "CURRENT_OBSERVATION")


def compile_historical(packet, at):
    """Deterministic offline replay; never a present-tense availability claim."""
    return _compile(packet, at, "HISTORICAL_REPLAY")


def verify_report(packet, report, *, current=False):
    """Verify report consistency, then optionally recompute time-sensitive decisions."""
    if type(current) is not bool:
        raise EvidenceError("current must be boolean")
    _bounded(report)
    if type(report) is not dict or report.get("mode") not in {"CURRENT_OBSERVATION", "HISTORICAL_REPLAY"}:
        raise EvidenceError("invalid report mode")
    expected = _compile(packet, report.get("evaluated_at"), report["mode"])
    if _canonical(report) != _canonical(expected):
        return {"ok": False, "verdict": "REPORT_MISMATCH", "authority": dict(AUTHORITY)}
    if not current:
        return {"ok": True, "verdict": "MATCHES_RECORDED_EVALUATION_ONLY", "authority": dict(AUTHORITY)}
    now = _now()
    if report["mode"] != "CURRENT_OBSERVATION" or _time(report["evaluated_at"]) > _time(now):
        return {"ok": False, "verdict": "NOT_CURRENT", "authority": dict(AUTHORITY)}
    fresh = _compile(packet, now, "CURRENT_OBSERVATION")
    fields = ("channel_diagnostics", "operations", "dispatch_snapshot", "dispatch")
    same = all(_canonical(report[k]) == _canonical(fresh[k]) for k in fields)
    return {"ok": same, "verdict": "DECISIONS_UNCHANGED_AT_PROCESS_TIME" if same else "TIME_SENSITIVE_STATE_CHANGED",
            "checked_at": now, "authority": dict(AUTHORITY)}


def render_markdown(report):
    def cell(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("`", "'").replace("\n", " ").replace("\r", " ")
    lines = ["# Work-feed evidence preview", "", f"Mode: **{cell(report['mode'])}**; evaluated {cell(report['evaluated_at'])}.",
        "Caller-supplied exports; no source authentication, claim, send, merge or payment authority.", "",
        "| Operation | State | Hold reasons |", "|---|---|---|"]
    lines += [f"| `{cell(r['operation_id'])}` | {cell(r['status'])} | {cell(', '.join(r['reasons']) or 'None')} |" for r in report["operations"]]
    lines += ["", "## Routing suggestions", ""]
    lines += [f"- `{cell(r['work_id'])}` → `{cell(r['channel_name'])}` (advisory only)." for r in report["dispatch"]["assignments"]]
    lines += [f"- `{cell(r['work_id'])}`: {cell(r['reason'])}." for r in report["dispatch"]["holds"]]
    lines += ["", "## Coverage", ""]
    lines += [f"- `{cell(r['channel_id'])}`: {cell(r['coverage'])}; observed messages {r['messages_observed_15m']}; unreleased slots {r['unreleased_claim_slots']}; {cell(', '.join(r['reasons']) or 'no declared-coverage gaps')}." for r in report["channel_diagnostics"]]
    lines += ["", "## Source references (not fetched by this tool)", ""]
    lines += [f"- `{cell(r['operation_id'])}`: " + "; ".join(f"`{cell(ref)}`" for ref in r["source_refs"]) for r in report["operations"]]
    lines += ["", "## Declared alias lineage", ""]
    lines += [f"- `{cell(r['alias'])}` → `{cell(r['operation_id'])}`: `{cell(r['ref'])}`." for r in report["alias_evidence"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("current", "replay", "verify"):
        cmd = sub.add_parser(command); cmd.add_argument("packet")
        if command == "replay":
            cmd.add_argument("--at", required=True)
        if command == "verify":
            cmd.add_argument("report"); cmd.add_argument("--current", action="store_true")
        else:
            cmd.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        def read(path):
            with open(path, "rb") as handle:
                return load_json(handle.read(MAX_BYTES + 1))
        packet = read(args.packet)
        if args.command == "verify":
            result = verify_report(packet, read(args.report), current=args.current)
        else:
            result = compile_current(packet) if args.command == "current" else compile_historical(packet, args.at)
        print(render_markdown(result) if getattr(args, "markdown", False) else _canonical(result).decode("utf-8"))
        return 0 if result.get("ok", True) else 1
    except (EvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
