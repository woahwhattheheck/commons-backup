"""Read a saved /api/decisions snapshot without contacting any provider."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "commons-deathstar-decisions/v2"
MAX_BYTES = 8 * 1024 * 1024
MODES = ("attention", "blocked", "working", "merged", "all")


def text(value):
    """Keep source values readable without executing terminal control sequences."""
    if value is None or value == "":
        return "unknown"
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value))


def objects(value, field):
    if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
        raise ValueError(f"{field} must be an array of objects")
    return value


def count(value):
    return value if type(value) is int and value >= 0 else None


def load_snapshot(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("non-finite JSON number")

    def finite(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return value

    if path == "-":
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("snapshot exceeds 8 MiB")
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite)
    if isinstance(data, dict) and isinstance(data.get("decisions"), dict):
        data = data["decisions"]
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError(f"expected {SCHEMA} snapshot")
    if data.get("ok") is not True:
        raise ValueError("snapshot does not report ok=true")
    rows = objects(data.get("rows"), "rows")
    seen = set()
    for row in rows:
        operation = row.get("operation")
        if not isinstance(operation, str) or not operation or operation in seen:
            raise ValueError("rows require distinct nonempty operation identifiers")
        seen.add(operation)
        for field in ("agents", "sources", "stages", "receipts"):
            objects(row.get(field, []), field)
    objects(data.get("exceptions", []), "exceptions")
    return data


def select_rows(data, mode, query="", operation=None):
    flagged = {e.get("operation") for e in data.get("exceptions", [])}
    selected = []
    for row in data["rows"]:
        blocked = (any(a.get("state") == "blocked" for a in row.get("agents", []))
                   or str(row.get("publication_state", "")).startswith("held:"))
        working = any(a.get("state") == "active" for a in row.get("agents", []))
        attention = (blocked or row.get("gate_stale") is True
                     or row.get("waiting_on") == "waiting_on_us"
                     or row["operation"] in flagged)
        matches = {"all": True, "attention": attention, "blocked": blocked,
                   "working": working, "merged": (count(row.get("merged_prs")) or 0) > 0}
        if not matches[mode] or (operation is not None and operation != row["operation"]):
            continue
        # Search source-provided operation, owner, worker, next action and receipts.
        haystack = json.dumps({k: row.get(k) for k in
                              ("operation", "owner", "agents", "next_action", "receipts")},
                             ensure_ascii=False).casefold()
        if query.casefold() in haystack:
            selected.append(row)
    return selected


def selection(data, rows, mode, offset, limit):
    operations = data.get("operations")
    active = count(operations.get("active")) if isinstance(operations, dict) else None
    return {
        "mode": mode, "snapshot_generated_at": data.get("generated_at"),
        "source_note": data.get("source_note"),
        "operator_control": data.get("operator_control"),
        "operator_control_source": data.get("operator_control_source"),
        "cache": data.get("cache"),
        "collection": data.get("collection"),
        "exceptions_omitted": data.get("exceptions_omitted"),
        "snapshot_rows": len(data["rows"]), "active_reported": active,
        "unavailable_active_rows": None if active is None else max(0, active - len(data["rows"])),
        "matching_snapshot_rows": len(rows), "offset": offset,
        "returned_rows": len(rows[offset:offset + limit]),
        "remaining_matching_rows": max(0, len(rows) - offset - limit),
        "scope": "Saved observations only; filters do not fetch omitted rows. Merged is not paid or fully delivered.",
    }


def render(data, rows, view, details=False):
    mode = data.get("operator_control", {})
    mode = mode.get("mode") if isinstance(mode, dict) else None
    collection = data.get("collection", {})
    complete = collection.get("complete") if isinstance(collection, dict) else None
    coverage = "complete" if complete is True else "incomplete" if complete is False else "unknown"
    stamp = data.get("generated_at")
    age = "unknown"
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.tzinfo is not None:
            seconds = (datetime.now(timezone.utc) - when).total_seconds()
            age = f"{int(seconds)}s" if seconds >= 0 else "future timestamp"
    except (AttributeError, ValueError, OverflowError):
        pass
    yield f"OPERATOR VIEW | {view['mode']} | control {text(mode)}"
    yield f"Generated {text(stamp)} | snapshot age {age} | collection {coverage}"
    control_source = data.get("operator_control_source")
    control_source = control_source if isinstance(control_source, dict) else {}
    fresh = control_source.get("fresh")
    freshness = "fresh" if fresh is True else "stale or unavailable" if fresh is False else "unknown"
    yield (f"Control evidence at snapshot: {freshness} | "
           f"observed {text(control_source.get('observed_at'))}")
    cache = data.get("cache")
    cache = cache if isinstance(cache, dict) else {}
    hit = "hit" if cache.get("hit") is True else "miss" if cache.get("hit") is False else "unknown"
    yield (f"Projection cache at snapshot: {hit} | age {text(cache.get('age_seconds'))}s | "
           f"TTL {text(cache.get('ttl_seconds'))}s; not provider freshness.")
    if isinstance(data.get("source_note"), str):
        yield "Input scope: " + text(data["source_note"])
    if count(data.get("exceptions_omitted")):
        yield f"Exception records omitted upstream: {data['exceptions_omitted']}; attention filtering is incomplete."
    yield (f"Showing {len(rows)} of {view['matching_snapshot_rows']} matching saved rows; "
           f"{view['snapshot_rows']} saved / {text(view['active_reported'])} active reported.")
    omitted = view["unavailable_active_rows"]
    if omitted is None or omitted:
        yield f"Active rows unavailable in this snapshot: {text(omitted)}. Filtering cannot recover them."
    yield "Working means reported active, not independently verified live. Merged does not mean paid."
    yield "Cost and exact source refs are not supplied by decisions/v2; unknown is not zero."
    if not rows:
        yield "No matching rows in the supplied snapshot; this is not a fleet-wide absence claim."
    for row in rows:
        owner = row.get("owner") or {}
        if not isinstance(owner, dict):
            owner = {}
        yield ""
        yield f"{text(row['operation'])} | {text(row.get('stage'))} / {text(row.get('stage_state'))}"
        yield (f"  Owner: {text(owner.get('owner_account'))} / {text(owner.get('seat'))}; "
               f"merged PRs: {text(row.get('merged_prs'))}; publication: {text(row.get('publication_state'))}")
        yield f"  Waiting: {text(row.get('waiting_on'))} — {text(row.get('waiting_for'))}"
        yield f"  Next: {text(row.get('next_action'))}"
        for agent in row.get("agents", []):
            yield (f"  Worker: {text(agent.get('seat'))} | {text(agent.get('state'))} | "
                   f"heartbeat age {text(agent.get('heartbeat_age_seconds'))}s | {text(agent.get('blocker'))}")
        for event in data.get("exceptions", []):
            if event.get("operation") == row["operation"]:
                yield f"  Attention: {text(event.get('reason'))} | {text(event.get('action'))}"
        if details:
            for source in row.get("sources", []):
                yield (f"  Source: {text(source.get('id'))} | {text(source.get('freshness'))} | "
                       f"coverage {text(source.get('coverage'))} | cooldown {text(source.get('cooldown'))}")
            for receipt in row.get("receipts", []):
                yield (f"  Record: {text(receipt.get('kind'))} / {text(receipt.get('status'))} | "
                       f"{text(receipt.get('title') or receipt.get('item_id'))} | {text(receipt.get('url'))}")
            for stage in row.get("stages", []):
                yield (f"  Stage: {text(stage.get('stage'))} / {text(stage.get('state'))} | "
                       f"{text(stage.get('who_acts'))} | observed {text(stage.get('observed_at'))} | "
                       f"{text(stage.get('evidence'))}")
    if view["remaining_matching_rows"]:
        yield f"\n{view['remaining_matching_rows']} more matching rows: use --offset {view['offset'] + len(rows)}."


def nonnegative(value):
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="saved /api/decisions JSON, or - for stdin")
    parser.add_argument("--mode", choices=MODES, default="attention")
    parser.add_argument("--query", default="", help="case-insensitive source-text search")
    parser.add_argument("--operation", help="exact operation identifier")
    parser.add_argument("--offset", type=nonnegative, default=0)
    parser.add_argument("--limit", type=nonnegative, default=10)
    parser.add_argument("--details", action="store_true", help="include source, stage and record drilldowns")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    try:
        data = load_snapshot(args.snapshot)
        matches = select_rows(data, args.mode, args.query, args.operation)
        view = selection(data, matches, args.mode, args.offset, args.limit)
        rows = matches[args.offset:args.offset + args.limit]
        output = (json.dumps({"view": view, "rows": rows}, ensure_ascii=False, indent=2, allow_nan=False)
                  if args.format == "json" else "\n".join(render(data, rows, view, args.details)))
        print(output)
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"operator view: {text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
