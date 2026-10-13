"""Deterministic dispatch and bounded context over the existing task/seat facts.

This module never contacts providers, creates work, or authorizes a session.
The runtime calls ``route`` inside its claim transaction. Direct work remains
possible; these decisions govern only automatic assignment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re

from host import seat_census
from .projector import _time

UNKNOWN = "UNKNOWN"
TERMINALS = {"SHIPPED", "BLOCKED", "SUPERSEDED", "ABANDONED"}
LIVE = {"LIVE", "QUIET"}
LIMIT = 20
TASK_STATES = {"OPEN", "ACTIVE", *TERMINALS}
FAILURES = {
    "not_discovered": "not_discovered", "tool_not_discovered": "not_discovered",
    "unknown": "not_discovered", "unauthenticated": "unauthenticated",
    "connector_not_authenticated": "unauthenticated", "connector_unauthenticated": "unauthenticated",
    "permission": "permission", "permission_denied": "permission",
    "account_lacks_permission": "permission", "policy": "policy",
    "policy_refusal": "policy", "policy_blocked": "policy", "repository_policy_refusal": "policy",
    "provider_failure": "provider_failure", "provider_error": "provider_failure",
    "absent": "capability_absent", "unavailable": "capability_absent",
}


def _text(value):
    return str(value).strip() if value is not None else ""


def _known(value):
    return value is not None and value != "" and value != UNKNOWN


def _sort_time(value, *, missing_last=False):
    missing = datetime.max if missing_last else datetime.min
    return _time(value) or missing.replace(tzinfo=timezone.utc)


def _names(value):
    if isinstance(value, str):
        return {value} if _known(value) else set()
    if isinstance(value, (list, tuple, set)):
        return {_text(v) for v in value if isinstance(v, str) and _known(v)}
    return set()


def _clock(now):
    try:
        datetime.fromisoformat(now.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("routing requires a parseable current read clock") from exc


def _tasks(tasks):
    rows = tasks.get("tasks", tasks) if isinstance(tasks, dict) else {}
    return {str(key): dict(task, task_key=task.get("task_key") or str(key))
            for key, task in rows.items() if isinstance(task, dict)}


def select_tasks(tasks, *, limit=100, task=None, states=None, owner=None, after=None):
    """Select a bounded status page without provider reads or projection changes.

    ``task`` and ``after`` accept canonical identities (or an exact GitHub URL).
    States are exact lifecycle names; owner matches the current worker exactly.
    ``matched`` counts filtered tasks before the exclusive cursor, while ``total``
    remains the whole canonical task count. A next cursor exists only when more
    matching rows remain. Limits retain status's existing 1..1000 clamping.
    """
    from .identity import task_key

    if isinstance(limit, bool):
        raise ValueError("limit must be an integer")
    try:
        page_size = max(1, min(1000, int(limit)))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("limit must be an integer") from exc

    def identity(value, name):
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(name + " must be a nonempty task identity")
        return task_key(value)

    exact = identity(task, "task")
    cursor = identity(after, "after")
    if owner is not None and (not isinstance(owner, str) or not owner.strip()):
        raise ValueError("owner must be a nonempty worker name")
    if states is None:
        states = []
    elif isinstance(states, str):
        states = [states]
    if not isinstance(states, (list, tuple, set)) or any(
            not isinstance(state, str) or state not in TASK_STATES for state in states):
        raise ValueError("states must contain only " + ", ".join(sorted(TASK_STATES)))
    wanted = set(states)
    # Index retained records without copying every task for a bounded page.
    # Returned rows remain independent shallow copies, as with _tasks().
    source = tasks.get("tasks", tasks) if isinstance(tasks, dict) else {}
    rows = {str(key): row for key, row in source.items() if isinstance(row, dict)}
    matched, remaining, page = 0, 0, []
    for key in sorted(rows):
        row = rows[key]
        if exact is not None and key != exact:
            continue
        if wanted and row.get("state") not in wanted:
            continue
        if owner is not None and row.get("worker") != owner:
            continue
        matched += 1
        if cursor is not None and key <= cursor:
            continue
        remaining += 1
        if len(page) < page_size:
            page.append(dict(row, task_key=row.get("task_key") or key))
    truncated = remaining > len(page)
    return {"rows": page, "matched": matched, "total": len(rows),
            "next_cursor": page[-1]["task_key"] if truncated else None,
            "truncated": truncated}


def _seats(seats, now):
    if not isinstance(seats, dict):
        seats = {}
    if "seats" in seats or "roster" in seats:
        payload = seats
    else:
        rows = []
        for name, rec in seats.items():
            if isinstance(rec, dict):
                rows.append(dict(rec, seat=rec.get("seat") or name,
                                 declared=rec.get("declared", rec)))
        payload = {"seats": rows}
    current = seat_census.recompute(payload, now)
    out = {}
    for row in current.get("roster", []):
        if isinstance(row, dict) and row.get("seat"):
            out[row["seat"]] = dict(row, declared={}, derived={
                "liveness": row.get("liveness", UNKNOWN),
                "heartbeat_age_s": row.get("heartbeat_age_s", UNKNOWN)})
    for row in current.get("seats", []):
        if isinstance(row, dict) and row.get("seat"):
            out[row["seat"]] = row
    return out


def _field(seat, key):
    for block in (seat.get("declared", {}), seat.get("extra", {}), seat):
        if isinstance(block, dict) and key in block and _known(block[key]):
            return block[key]
    return UNKNOWN


def _seat_summary(seat, worker):
    derived = seat.get("derived", {})
    return {"seat": worker, "liveness": derived.get("liveness", UNKNOWN),
            "heartbeat_age_s": derived.get("heartbeat_age_s", UNKNOWN),
            **{key: _field(seat, key) for key in
               ("heartbeat", "feed_cursor", "model", "harness", "roads",
                "tools", "roles", "capabilities", "cants")}}


def _recoverable(task, seats, now):
    if task.get("state") != "ACTIVE":
        return False
    owner = seats.get(task.get("worker"), {})
    if owner.get("derived", {}).get("liveness") in LIVE:
        return False
    # Meaningful task activity also renews custody; observation of an unchanged
    # provider snapshot does not. Invalid future clocks cannot extend a lease.
    stamps = [_field(owner, "heartbeat"), (task.get("lease") or {}).get("heartbeat")]
    stamps += [task.get(key) for key in
               ("heartbeat", "latest_activity", "last_activity_at", "started_at",
                "provider_progress_at", "provider_activity_at")]
    bands = [seat_census.liveness_at(stamp, now)[0] for stamp in stamps]
    if any(band in LIVE for band in bands):
        return False
    return task.get("recoverable") is True or any(
        band in {"STALE", "COLD"} for band in bands)


def _capabilities(seat):
    roads = _names(_field(seat, "roads"))
    raw_tools = _field(seat, "tools")
    tools = _names(raw_tools)
    if isinstance(raw_tools, dict):
        for key in ("names", "names_sample", "available"):
            tools |= _names(raw_tools.get(key))
    groups = {"roads": roads, "tools": tools,
              "roles": _names(_field(seat, "roles")),
              "capabilities": _names(_field(seat, "capabilities"))}
    groups["any"] = set().union(*groups.values())
    # Explicit write roads or actual write primitives establish this alias.
    # A plain github/read road never establishes publishing capability.
    write_roads = {"github-git-data", "github-push", "github-write", "github-publish"}
    tool_names = {name.rsplit("__", 1)[-1] for name in tools}
    tool_names |= {name.removeprefix("github_") for name in tool_names}
    if roads & write_roads or {"create_commit", "update_ref"} <= tool_names or \
            tool_names & {"merge_pull_request", "github_merge_pull_request"}:
        groups["any"].add("github-publish")
        groups["capabilities"].add("github-publish")
    return groups


def _requirements(required):
    if isinstance(required, dict):
        pairs = []
        for group in ("roads", "tools", "roles", "capabilities", "all"):
            pairs.extend(("any" if group == "all" else group, name)
                         for name in sorted(_names(required.get(group))))
        # Also accept a compact {capability: true} requirement map.
        pairs.extend(("any", str(name)) for name, value in required.items()
                     if name not in {"roads", "tools", "roles", "capabilities", "all"}
                     and value is True)
        return pairs
    return [("any", name) for name in sorted(_names(required))]


def _capability_failure(seat, capability, repo=None):
    for field in ("capability_states", "capability_status", "discovery", "connectors"):
        states = _field(seat, field)
        if not isinstance(states, dict):
            continue
        provider = "github" if capability.startswith("github") else \
                   "slack" if capability.startswith("slack") else capability
        for key in (capability, provider):
            entry = states.get(key)
            if isinstance(entry, dict):
                # A repo-specific refusal must not poison other repositories.
                if entry.get("repo") and entry["repo"] != repo:
                    continue
                entry = entry.get("state", entry.get("status", entry.get("error_state")))
            reason = FAILURES.get(_text(entry).lower().replace("-", "_"))
            if reason:
                return reason
    cants = _field(seat, "cants")
    for entry in cants if isinstance(cants, list) else []:
        if not isinstance(entry, dict):
            continue
        named = set().union(*(_names(entry.get(k)) for k in
                            ("capability", "capabilities", "road", "tool")))
        if capability not in named or (entry.get("repo") and entry["repo"] != repo):
            continue
        return FAILURES.get(_text(entry.get("state")).lower(), "capability_unavailable")
    return None


def _compatible(task, seat, required, *, groups=None):
    if groups is None:
        groups = _capabilities(seat)
    needs = _requirements(task.get("required_capabilities", task.get("required")))
    needs += _requirements(required)
    missing = []
    for group, name in sorted(set(needs)):
        failure = _capability_failure(seat, name, task.get("repo"))
        if failure or name not in groups[group]:
            missing.append({"capability": name, "kind": group,
                            "reason": failure or "not_discovered"})
    return missing


def _rank(task, recoverable):
    priority = task.get("priority", 0)
    try:
        priority = float(priority)
        if not math.isfinite(priority):
            priority = 0
    except (TypeError, ValueError):
        priority = 0
    return (0 if recoverable else 1, -priority,
            _sort_time(task.get("created_at"), missing_last=True), task["task_key"])


def route(tasks: dict, worker: str, seats: dict, now: str, required=None):
    """Select one canonical OPEN/recoverable task without mutating any inputs.

    Requirements are exact road/tool/role/capability names, a list, or a map of
    those plural groups. ``github-publish`` is the documented write-road alias.
    Selection is recovery first, priority descending, creation time, task key.
    The caller must atomically append TAKE (or RECOVER) with this decision.
    """
    _clock(now)
    return _route_prepared(_tasks(tasks), worker, _seats(seats, now), now, required)


def _iter_routes(tasks, workers, seats, now, required=None):
    """Read-only batch choices over one private routing snapshot.

    Prepare lazily so an empty batch does no census work. Remove each suggested
    task only from this batch; the caller still reconciles and claims at dispatch.
    This iterator is internal: consumers read choices without changing them.
    """
    rows = census = None
    for worker in workers:
        if rows is None:
            _clock(now)
            rows, census = _tasks(tasks), _seats(seats, now)
        choice = _route_prepared(rows, worker, census, now, required)
        if choice.get("task_key"):
            rows.pop(choice["task_key"])
        yield choice


def _route_prepared(rows, worker, census, now, required=None):
    """Apply the unchanged selection rules to caller-owned prepared inputs."""
    seat = census.get(worker, {})
    result = {"task_key": None, "reason": "no_eligible_work", "eligible": [],
              "seat": _seat_summary(seat, worker), "exclusions": []}
    if worker not in census:
        result["reason"] = "worker_unknown"
        return result
    if seat.get("derived", {}).get("liveness") not in LIVE:
        result["reason"] = "worker_not_live"
        return result
    held = sorted(key for key, task in rows.items()
                  if task.get("state") == "ACTIVE" and task.get("worker") == worker
                  and not _recoverable(task, census, now))
    if held:
        result.update(reason="worker_active", active=held[:LIMIT])
        return result
    # Capabilities are unchanged across candidates in this routing decision.
    groups = _capabilities(seat)
    candidates = []
    for key, task in rows.items():
        recovery = _recoverable(task, census, now)
        if task.get("state") != "OPEN" and not recovery:
            continue
        if task.get("dispatchable") is False:
            result["exclusions"].append({
                "task_key": key, "reason": "provider_reconciliation_needed",
                "next_action": task.get("reconciliation_needed", UNKNOWN)})
            continue
        missing = _compatible(task, seat, required, groups=groups)
        if missing:
            result["exclusions"].append({"task_key": key,
                                         "reason": missing[0]["reason"],
                                         "missing": missing})
            continue
        candidates.append((task, recovery))
    candidates.sort(key=lambda pair: _rank(*pair))
    result["eligible"] = [task["task_key"] for task, _ in candidates[:LIMIT]]
    result["eligible_count"] = len(candidates)
    result["exclusions"].sort(key=lambda row: row["task_key"])
    result["excluded_count"] = len(result["exclusions"])
    result["exclusions"] = result["exclusions"][:LIMIT]
    if candidates:
        task, recovery = candidates[0]
        result.update(task_key=task["task_key"], reason="recoverable" if recovery else "open")
    elif result["exclusions"]:
        result["reason"] = result["exclusions"][0]["reason"]
    return result


def _bounded(value, limit=1000, depth=0):
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if depth >= 3:
        return "[nested content omitted]"
    if isinstance(value, list):
        return [_bounded(v, limit, depth + 1) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k): _bounded(v, limit, depth + 1) for k, v in list(value.items())[:20]}
    return _text(value)[:limit]


def _related(event, task, ids):
    event_id = _text(event.get("event_id", event.get("id")))
    if event_id and event_id in ids:
        return True
    if event.get("task_key") == task.get("task_key") and task.get("task_key"):
        return True
    payload = event.get("data", event.get("payload", {}))
    if isinstance(payload, dict) and payload.get("task_key") == task.get("task_key") \
            and task.get("task_key"):
        return True
    repo = task.get("repo")
    if _known(repo) and event.get("repo") == repo:
        if any(_known(task.get(key)) and _text(event.get(key)) == _text(task[key])
               for key in ("issue", "pr")):
            return True
    prose = [_text(event.get(key)) for key in ("text", "excerpt", "body")]
    if not any(prose):
        return False
    text = "\n".join(prose)
    needles = [task.get("task_key")]
    if _known(repo):
        for key, path in (("issue", "issues"), ("pr", "pull")):
            if _known(task.get(key)):
                needles.append("https://github.com/%s/%s/%s" % (repo, path, task[key]))
    return any(_known(needle) and re.search(re.escape(str(needle)) + r"(?![\w:/.-])", text)
               for needle in needles)


def context_bundle(task, events=None, max_events=8):
    """Bounded identifiers plus recent exact matches; never a provider search."""
    keys = ("task_key", "title", "repo", "issue", "pr", "state", "worker", "model", "harness",
            "base_sha", "head_sha", "branch", "merge_sha", "feed_cursor", "artifact",
            "artifact_sha", "landed_sha", "shipment_kind", "shipment_source", "closed_at",
            "provider_freshness", "provider_observed_at", "reconciliation_needed",
            "started_at", "latest_activity", "blocker", "next_action", "superseded_by",
            "required_capabilities")
    bundle = {key: _bounded(task.get(key, UNKNOWN)) for key in keys}
    ids = _names(task.get("source_event_ids"))
    bundle["source_event_ids"] = sorted(ids)[:32]
    bundle["source_event_count"] = len(ids)
    bundle["source"] = _bounded(task.get("source", UNKNOWN))
    error = task.get("exact_error", task.get("error", UNKNOWN))
    bundle["exact_error"] = _bounded(error, 2000)
    if isinstance(error, str) and len(error) > 2000:
        bundle["error_truncated"] = True
    rows = events.get("events", []) if isinstance(events, dict) else events or []
    matches = [event for event in rows if isinstance(event, dict) and _related(event, task, ids)]
    def chronology(event):
        cursor = _text(event.get("c"))
        observed = cursor.split("|", 1)[0] if cursor else event.get("at", event.get("timestamp", event.get("ts")))
        return (_sort_time(observed), cursor, _text(event.get("event_id", event.get("id"))))

    matches.sort(key=chronology)
    cap = max(0, min(int(max_events), 20))
    bundle["events"] = [{key: _bounded(event[key], 400) for key in
                          ("event_id", "id", "c", "at", "timestamp", "ts", "kind", "action", "task_key",
                           "repo", "issue", "pr", "text", "excerpt", "source", "url")
                          if key in event} for event in (matches[-cap:] if cap else [])]
    return bundle


def status(tasks, seats, now):
    """Cheap operator view, with ages always measured against the read clock."""
    _clock(now)
    rows, census = _tasks(tasks), _seats(seats, now)
    counts = {state: 0 for state in ("OPEN", "ACTIVE", "SHIPPED", "BLOCKED", "SUPERSEDED", "ABANDONED")}
    recoverable, occupied, shipped, collisions = [], set(), [], []
    collision_count = 0
    for key, task in sorted(rows.items()):
        state = task.get("state", UNKNOWN)
        counts[state] = counts.get(state, 0) + 1
        if _recoverable(task, census, now):
            recoverable.append(key)
        elif state == "ACTIVE":
            occupied.add(task.get("worker"))
        if state == "SHIPPED":
            shipped.append(task)
        collision_count += task.get("collision_count", 0) if isinstance(task.get("collision_count"), int) else 0
        for collision in task.get("collisions", []) if isinstance(task.get("collisions"), list) else []:
            collisions.append({"task_key": key, "collision": _bounded(collision, 300)})
    stale, idle, pools = [], [], {}
    for name, seat in sorted(census.items()):
        summary = _seat_summary(seat, name)
        if summary["liveness"] not in LIVE:
            stale.append({key: summary[key] for key in ("seat", "liveness", "heartbeat_age_s")})
        elif name not in occupied:
            idle.append(name)
            groups = _capabilities(seat)
            for capability in sorted(groups["any"]):
                if not _capability_failure(seat, capability):
                    pools.setdefault(capability, []).append(name)
    # Completion defines shipment recency; worker activity may be absent or later.
    shipped.sort(key=lambda task: (_time(task.get("closed_at"))
                                  or _time(task.get("latest_activity"))
                                  or _sort_time(task.get("last_activity_at")),
                                  task["task_key"]), reverse=True)
    return {"counts": counts, "recoverable": recoverable[:LIMIT],
            "recoverable_count": len(recoverable), "stale_seats": stale[:LIMIT],
            "stale_seat_count": len(stale), "idle_seats": idle[:LIMIT],
            "idle_seat_count": len(idle),
            "idle_capabilities": {key: names[:LIMIT] for key, names in sorted(pools.items())[:50]},
            "idle_capability_count": len(pools),
            "recently_shipped": [context_bundle(task, max_events=0) for task in shipped[:LIMIT]],
            "collisions": collisions[-LIMIT:], "collision_count": max(collision_count, len(collisions)),
            "liveness_basis": "read", "observed_at": now}
