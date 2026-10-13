"""Commons host projector for Observatory.

Reads existing bakes and JobStore files. Writes observatory.json as a bake.
Does not mutate p/{id}.md, presence, jobs, or cash ledgers.
"""
from __future__ import annotations

import json
import math
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from protocol.emit import continue_from_observation
from protocol.projector import project

import hub_pages

SNAPSHOT_REL = "observatory.json"


def freshness(snap: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    """Read-time age is separate from the immutable bake and its digest."""
    checked = now or _now()
    age = None
    try:
        observed = datetime.fromisoformat(str(snap.get("now")).replace("Z", "+00:00"))
        current = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        age = (current - observed).total_seconds()
    except (TypeError, ValueError):
        pass
    threshold = snap.get("stale_after_seconds")
    valid = (isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
             and threshold >= 0
             and (not isinstance(threshold, float) or math.isfinite(threshold)))
    state = "UNKNOWN" if age is None or age < 0 or not valid else ("STALE" if age > threshold else "FRESH")
    return {"state": state, "snapshot_at": snap.get("now"), "checked_at": checked,
            "age_seconds": age, "stale_after_seconds": threshold,
            "scope": "snapshot age, not proof that all fleet activity was ingested"}


def _paginate(items: list, arguments: dict[str, Any], *, field: str) -> tuple[list, dict[str, Any]]:
    """Deterministic offset/limit pagination. Unknown values become 0."""
    if not isinstance(items, list):
        items = []
    try:
        raw_off = arguments.get("offset")
        if raw_off in (None, ""):
            raw_off = arguments.get("cursor") or 0
        offset = int(raw_off)
    except (TypeError, ValueError, OverflowError):
        offset = 0
    if offset < 0:
        offset = 0
    try:
        raw_lim = arguments.get("limit")
        limit = int(raw_lim) if raw_lim not in (None, "") else 0
    except (TypeError, ValueError, OverflowError):
        limit = 0
    if limit < 0:
        limit = 0
    meta = {
        "field": field,
        "total": len(items),
        "offset": offset,
        "limit": limit or None,
        "next_cursor": None,
        "deterministic": True,
    }
    if limit <= 0:
        return items[offset:], meta
    sliced = items[offset:offset + limit]
    nxt = offset + limit
    if nxt < len(items):
        meta["next_cursor"] = str(nxt)
    return sliced, meta


def _read_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _observed_json(root: str, rel: str, expected: type) -> tuple[Any, dict[str, Any]]:
    """Describe the same read that supplies the projection, never a second read."""
    status: dict[str, Any] = {"source": rel, "state": "OBSERVED"}
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        status["state"] = "MISSING"
    except (UnicodeError, ValueError) as exc:
        status.update(state="MALFORMED", error=type(exc).__name__)
    except OSError as exc:
        status.update(state="UNREADABLE", error=type(exc).__name__)
    else:
        if isinstance(value, expected):
            return value, status
        status.update(state="MALFORMED", error="unexpected_json_type")
    return expected(), status


def _collection_status(rel: str, observed: int, errors: list[dict[str, Any]]) -> dict[str, Any]:
    # Keep diagnostics bounded while retaining the complete rejected count.
    state = "OBSERVED"
    if errors:
        state = "PARTIAL" if observed else ("UNREADABLE" if any(
            row["state"] in {"UNREADABLE", "MISSING"} for row in errors) else "MALFORMED")
    return {"source": rel, "state": state, "records_observed": observed,
            "records_rejected": len(errors), "errors": errors[:20],
            "errors_truncated": len(errors) > 20}


def _observed_directory(root: str, rel: str, *, jobs: bool = False) -> tuple[list, dict[str, Any]]:
    rows = []
    errors = []
    try:
        names = sorted(os.listdir(os.path.join(root, rel)))
    except FileNotFoundError:
        return rows, {"source": rel, "state": "MISSING"}
    except OSError as exc:
        return rows, {"source": rel, "state": "UNREADABLE", "error": type(exc).__name__}
    for name in names:
        if not name.endswith(".json") or (jobs and name.startswith("_")):
            continue
        row, status = _observed_json(root, rel + "/" + name, dict)
        if status["state"] == "OBSERVED" and jobs and not row.get("job_id"):
            status.update(state="MALFORMED", error="missing_job_id")
        if status["state"] == "OBSERVED":
            rows.append(row)
        else:
            errors.append(status)
    return rows, _collection_status(rel, len(rows), errors)


def _observed_jsonl(root: str, rel: str) -> tuple[list, dict[str, Any]]:
    rows = []
    errors = []
    observed = 0
    try:
        # Decode per line so one bad encoding does not discard other records.
        with open(os.path.join(root, rel), "rb") as handle:
            for number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    line = raw.decode("utf-8").strip()
                    row = json.loads(line)
                except (UnicodeError, ValueError) as exc:
                    errors.append({"source": rel, "line": number,
                                   "state": "MALFORMED", "error": type(exc).__name__})
                    rows.append({"parse_state": "MALFORMED", "source": rel, "line": number})
                    continue
                if not isinstance(row, dict):
                    errors.append({"source": rel, "line": number,
                                   "state": "MALFORMED", "error": "unexpected_json_type"})
                else:
                    observed += 1
                rows.append(row)
    except FileNotFoundError:
        return rows, {"source": rel, "state": "MISSING"}
    except OSError as exc:
        errors.append({"source": rel, "state": "UNREADABLE", "error": type(exc).__name__})
    return rows, _collection_status(rel, observed, errors)


def load_legacy(root: str | None = None) -> dict[str, Any]:
    root = root or ROOT
    legacy: dict[str, Any] = {}
    coverage = []
    for key, rel, expected in (
        ("presence", "presence.json", list), ("lastseen", "lastseen.json", list),
        ("pulse", "pulse.json", dict), ("recent", "recent.json", list),
        ("claims", "claims.json", dict), ("recovery", "revenue/payment_ready/recovery.json", dict),
        ("protocol_events", "protocol/fixtures/live_events.json", list),
    ):
        legacy[key], status = _observed_json(root, rel, expected)
        coverage.append(status)
    for key, rel in (("jobs", "wake_jobs"), ("grok_captures", "artifacts/grok-captures")):
        legacy[key], status = _observed_directory(root, rel, jobs=key == "jobs")
        coverage.append(status)
    events, status = _observed_jsonl(root, "protocol/events.jsonl")
    legacy["protocol_events"].extend(events)
    coverage.append(status)
    legacy["source_coverage"] = coverage
    return legacy


def snapshot(root: str | None = None, *, now: str | None = None, events: list | None = None) -> dict[str, Any]:
    root = root or ROOT
    legacy = load_legacy(root)
    pulse = legacy.get("pulse") if isinstance(legacy.get("pulse"), dict) else {}
    incoming = list(events or [])
    incoming.extend(legacy.get("protocol_events") or [])
    return project(
        incoming,
        now=now or _now(),
        legacy=legacy,
        head_sha=str(pulse.get("head") or ""),
    )


def write_snapshot(root: str | None = None, *, now: str | None = None) -> dict[str, Any]:
    root = root or ROOT
    snap = snapshot(root, now=now)
    path = os.path.join(root, SNAPSHOT_REL)
    # KEEP tip live_cash across observatory remints (protocol projector rebuild
    # drops tip doors landed on observatory.json). Paths only.
    prev = _read_json(path, {})
    snap = hub_pages._preserve_live_cash(prev if isinstance(prev, dict) else {}, snap, root)
    payload = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        mode = 0o644
    # Stage in the destination directory so readers see either complete bake.
    # A failed write leaves the last published snapshot intact.
    fd, staged = tempfile.mkstemp(prefix=".observatory-", suffix=".json.tmp", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(staged, mode)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        try:
            os.unlink(staged)
        except FileNotFoundError:
            pass
    return snap


def read_observatory(root: str | None = None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    root = root or ROOT
    snap, status = _observed_json(root, SNAPSHOT_REL, dict)
    source = SNAPSHOT_REL
    if status["state"] != "OBSERVED":
        snap = snapshot(root)
        source = "host.observatory.snapshot"
    result = select_snapshot(snap, arguments, source=source)
    result["snapshot_source"] = status
    return result


def select_snapshot(snap: dict[str, Any], arguments: dict[str, Any] | None = None, *,
                    source: str = SNAPSHOT_REL, now: str | None = None) -> dict[str, Any]:
    """Select the same canonical bake for filesystem and SHA-pinned MCP readers."""
    arguments = arguments if isinstance(arguments, dict) else {}
    view = str(arguments.get("view") or "snapshot").strip().lower()
    views = {
        "snapshot": snap,
        "census": {"presence": snap.get("presence"), "sessions": snap.get("sessions"), "cockpit": snap.get("cockpit")},
        "work": {"work_map": snap.get("work_map")},
        "collisions": {"collisions": snap.get("collisions")},
        "attention": {"attention": snap.get("attention")},
        "timeline": {"timeline": snap.get("timeline")},
        "briefing": {"briefing": snap.get("briefing")},
        "economy": {"economy": snap.get("economy")},
        "routes": {"routes": snap.get("routes")},
    }
    body = views.get(view, snap)
    body = dict(body)
    page_fields = {
        "census": (("sessions", snap.get("sessions") or []), ("presence", snap.get("presence") or [])),
        "work": (("work_map", snap.get("work_map") or []),),
        "collisions": (("collisions", snap.get("collisions") or []),),
        "attention": (("attention", snap.get("attention") or []),),
        "timeline": (("timeline", snap.get("timeline") or []),),
        "routes": (("routes", snap.get("routes") or []),),
        "snapshot": (("sessions", snap.get("sessions") or []), ("timeline", snap.get("timeline") or [])),
    }
    pagination = []
    for field, items in page_fields.get(view if view in views else "snapshot", ()):
        sliced, meta = _paginate(items, arguments, field=field)
        body[field] = sliced
        pagination.append(meta)
    body["schema"] = snap.get("schema")
    body["protocol"] = snap.get("protocol")
    body["state"] = "BAKE"
    body["view"] = view if view in views else "snapshot"
    body["open_door"] = snap.get("open_door")
    body["pagination"] = pagination
    body["freshness"] = freshness(snap, now)
    body["source_coverage"] = snap.get("source_coverage") or []
    body["coverage_note"] = snap.get("coverage_note") or "Source coverage was not recorded by this bake."
    body["provenance"] = {
        "source": source,
        "grade": "OBSERVED",
        "digest": snap.get("digest"),
    }
    return body


def observe_work(root: str | None = None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    snap = snapshot(root)
    return {
        "schema": snap.get("schema"),
        "protocol": snap.get("protocol"),
        "state": "BAKE",
        "cockpit": snap.get("cockpit"),
        "sessions": snap.get("sessions"),
        "presence": snap.get("presence"),
        "work_map": snap.get("work_map"),
        "collisions": snap.get("collisions"),
        "attention": snap.get("attention"),
        "head": snap.get("head"),
        "source_coverage": snap.get("source_coverage") or [],
        "coverage_note": snap.get("coverage_note"),
        "filter": arguments.get("filter") or {},
    }


def project_live_work(root: str | None = None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    extra = arguments.get("events") if isinstance(arguments.get("events"), list) else []
    return snapshot(root, events=extra)


def continue_from(root: str | None = None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments if isinstance(arguments, dict) else {}
    root = root or ROOT
    snap = snapshot(root)
    result = continue_from_observation(snap, session_id=str(arguments.get("session_id") or ""))

    # SESSION_MEMORY is an explicit, per-session opt-in.  The continuation
    # surface carries only a delta, except for one bounded re-insertion after a
    # caller-reported compaction epoch change.  No binding is the ordinary
    # open-door case and never blocks continuation or posting.
    # Spark Hobby stages an explicit runtime graph (stage_spark_mcp_bundle.py).
    # A missing memory_board.py must not 500 continue_from_observation.
    try:
        import memory_board
    except ModuleNotFoundError:
        result["session_memory"] = {
            "state": "NO_OPT_IN",
            "should_insert": False,
            "posting_gate": False,
            "reason": "MEMORY_BOARD_UNAVAILABLE",
        }
        result["resume_context"] = []
        return result
    memory = memory_board.session_memory_packet(
        root,
        str(arguments.get("session_id") or ""),
        after_entry_id=str(arguments.get("memory_cursor") or ""),
        compaction_epoch=str(arguments.get("compaction_epoch") or ""),
        acknowledged_compaction_epoch=str(
            arguments.get("acknowledged_compaction_epoch") or ""
        ),
    )
    result["session_memory"] = memory
    result["resume_context"] = [memory["context"]] if memory.get("should_insert") else []
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--write" in argv:
        snap = write_snapshot()
        sys.stdout.write("wrote %s digest=%s\n" % (SNAPSHOT_REL, snap.get("digest", "")[:16]))
    else:
        snap = snapshot()
        sys.stdout.write(json.dumps(snap.get("cockpit"), indent=2, sort_keys=True) + "\n")
    degraded = [row for row in snap.get("source_coverage", [])
                if row.get("state") not in {"OBSERVED", "MISSING"}]
    if degraded:
        sys.stderr.write("observatory: incomplete source reads: " + ", ".join(
            str(row.get("source")) + "=" + str(row.get("state")) for row in degraded) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
