"""Exact provider exits reconnect the existing operation and canonical journals.

Provider completion closes delivery, never the task. Observations survive the
submit-receipt race in source_events; ordinary callbacks/reads retry deferred
reconciliation. There is no timer, separate queue, or provider-text storage.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone

from .schema import _json

PROVIDERS = {"gemini": ("gemini_submit", "request_id"),
             "grokbot": ("grokbot_submit", "run_id")}
TOOLS = {"gemini_submit": "gemini", "gemini_get_request": "gemini",
         "gemini_events": "gemini", "grokbot_submit": "grokbot",
         "grokbot_inspect": "grokbot", "grokbot_events": "grokbot"}
TERMINAL = {"completed", "error", "cancelled", "interrupted"}
_active = threading.local()


def _identifier(value):
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,180}", value) else None


def _time(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (AttributeError, ValueError, TypeError, OverflowError, OSError):
        return None


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _prefix(runtime_id, provider, handle):
    return "provider-terminal:" + _hash([runtime_id, provider, handle]) + ":"


def _normalize(provider, event, runtime_id):
    if provider not in PROVIDERS or not isinstance(event, dict) or not _identifier(runtime_id):
        return None
    handle_key = PROVIDERS[provider][1]
    handle = _identifier(event.get(handle_key))
    status = str(event.get("status", "")).lower()
    if not handle or status not in TERMINAL:
        return None
    # Neither a stopped observer nor a local cancellation proves upstream exit.
    confirmed = status == "completed" or event.get("upstream_terminal") is True
    row = {"provider": provider, "runtime_id": runtime_id, handle_key: handle,
           "status": status, "confirmed_terminal": confirmed}
    for key in ("event_id", "session_id", "pool_id", "peer", "seat", "upstream_request_id"):
        if _identifier(event.get(key)) is not None:
            row[key] = _identifier(event[key])
    if type(event.get("upstream_terminal")) is bool:
        row["upstream_terminal"] = event["upstream_terminal"]
    if type(event.get("worker_available")) is bool:
        row["worker_available"] = event["worker_available"]
    if event.get("execution_road") in {"configured_handler", "unconfigured"}:
        row["execution_road"] = event["execution_road"]
    retry = _time(event.get("retry_not_before"))
    if retry is not None:
        row["retry_not_before"] = _iso(retry)
    seconds = event.get("retry_after")
    if type(seconds) in (int, float) and 0 <= seconds <= 3153600000:
        row["retry_after"] = seconds
    stamp = next((_time(event.get(key)) for key in ("ts", "updated_at", "activity_at")
                  if _time(event.get(key)) is not None), None)
    if stamp is not None:
        row["activity_at"] = _iso(stamp)
    # Hash selected facts only. The same callback and later provider read are
    # the same observation even when their transport envelopes differ.
    row["id"] = _prefix(runtime_id, provider, handle) + _hash(row)[:32]
    return row


def _persist(center, observations):
    added = 0
    now = _iso(datetime.now(timezone.utc))
    with center._db() as db:
        for row in observations:
            item = {"id": row["id"], "kind": "provider-terminal", "observed_at": now,
                    "title": row["provider"] + " delivery " + row["status"],
                    "body": "Confirmed upstream exit" if row["confirmed_terminal"] else "Upstream exit unconfirmed",
                    "source_ref": row[PROVIDERS[row["provider"]][1]], "summary": row}
            added += db.execute("INSERT OR IGNORE INTO source_events(id,observed_at,data) VALUES(?,?,?)",
                                (item["id"], now, _json(item))).rowcount
    return added


def _binding_matches(operation, observation):
    provider = observation["provider"]
    name, key = PROVIDERS[provider]
    summary = operation.get("summary") or {}
    binding = summary.get("swarm") or {}
    if (operation.get("name") != name or operation.get("runtime") != observation["runtime_id"]
            or binding.get("status") != "assigned" or not binding.get("task_key")
            or not binding.get("worker")):
        return False
    # Worker labels are a consistency check only, never correlation evidence.
    worker = observation.get("peer" if provider == "gemini" else "seat")
    if worker and worker != binding["worker"]:
        return False
    return any(ref.get("key") == key and ref.get("value") == observation[key]
               for ref in summary.get("provider_refs", []) if isinstance(ref, dict))


def _matching_operations(center, observation):
    name, key = PROVIDERS[observation["provider"]]
    with center._db() as db:
        # Exact handle prefilter narrows the retained journal, not a newest-page
        # heuristic. Parsed provider_refs remain the correlation authority.
        rows = db.execute("SELECT * FROM operations WHERE kind='tool' AND name=? AND runtime=? AND instr(summary,?)>0",
                          (name, observation["runtime_id"], observation[key])).fetchall()
    return [center._operation(row) for row in rows
            if _binding_matches(center._operation(row), observation)]


def observe_terminal(center, provider, event, runtime_id="shared-equipment", consume=True):
    row = _normalize(provider, event, runtime_id)
    if row is None:
        return {"status": "ignored", "reason": "not_terminal_metadata"}
    inserted = _persist(center, [row])
    result = {"status": "observed", "event_id": row["id"], "inserted": bool(inserted),
              "confirmed_terminal": row["confirmed_terminal"]}
    matches = _matching_operations(center, row) if consume else []
    if len(matches) == 1:
        result["consumed"] = consume_operation(center, matches[0]["id"])
    elif len(matches) > 1:
        result.update(status="deferred", reason="ambiguous_provider_binding")
    elif consume:
        result["reason"] = "binding_not_observed"
    return result


def observe_result(center, name, result, runtime_id="shared-equipment"):
    """Observe only metadata already returned by the six existing peer tools."""
    provider = TOOLS.get(name)
    if provider is None:
        return {"status": "ignored", "reason": "unrelated_tool"}
    observations, seen = [], set()
    pending = [(result, 0)]
    visited = 0
    while pending and visited < 512 and len(observations) < 200:
        value, depth = pending.pop(0)
        visited += 1
        if not isinstance(value, dict) or depth > 6:
            continue
        row = _normalize(provider, value, runtime_id)
        if row and row["id"] not in seen:
            observations.append(row)
            seen.add(row["id"])
        for key in ("result", "structuredContent", "data", "event"):
            if isinstance(value.get(key), dict):
                pending.append((value[key], depth + 1))
        events = value.get("events")
        for event in events[:200] if isinstance(events, list) else []:
            if isinstance(event, dict):
                pending.append((event, depth + 1))
        contents = value.get("content")
        for content in contents[:10] if isinstance(contents, list) else []:
            text = content.get("text") if isinstance(content, dict) else None
            if isinstance(text, str) and len(text) <= 131072:
                try:
                    pending.append((json.loads(text), depth + 1))
                except ValueError:
                    pass
    inserted = _persist(center, observations) if observations else 0
    output = {"status": "observed", "observations": len(observations), "inserted": inserted,
              "truncated": bool(pending)}
    # Persist the whole delivered bounded batch before at most one continuation.
    for row in observations:
        if not row["confirmed_terminal"]:
            continue
        matches = _matching_operations(center, row)
        if len(matches) == 1:
            prior = (matches[0].get("summary") or {}).get("swarm_lifecycle") or {}
            if prior.get("observation_id") == row["id"] and prior.get("reason") in {
                "no_worker_road", "provider_execution_failed", "provider_execution_cancelled",
                "worker_activity_not_current", "worker_availability_unknown",
            }:
                # These exact observations cannot acquire missing exit/road/
                # activity evidence by being replayed. A richer new callback
                # has another identity and is still eligible for consumption.
                output["unchanged_deferrals"] = output.get("unchanged_deferrals", 0) + 1
                continue
            consumed = consume_operation(center, matches[0]["id"])
            if consumed.get("replayed") and consumed.get("next_operation_id"):
                output["already_continued"] = output.get("already_continued", 0) + 1
                continue
            output["consumed"] = consumed
            break
        if len(matches) > 1:
            output["ambiguous_bindings"] = output.get("ambiguous_bindings", 0) + 1
    return output


def _observations(center, operation):
    provider = next((p for p, (name, _) in PROVIDERS.items() if name == operation["name"]), None)
    if provider is None:
        return []
    key = PROVIDERS[provider][1]
    prefixes = {_prefix(operation["runtime"], provider, ref["value"])
                for ref in (operation.get("summary") or {}).get("provider_refs", [])
                if isinstance(ref, dict) and ref.get("key") == key and _identifier(ref.get("value"))}
    result = []
    with center._db() as db:
        for prefix in prefixes:
            for stored in db.execute("SELECT data FROM source_events WHERE id>=? AND id<?", (prefix, prefix + "~")):
                row = json.loads(stored["data"]).get("summary", {})
                if _binding_matches(operation, row):
                    result.append(row)
    return sorted(result, key=lambda row: (row.get("confirmed_terminal", False),
                  row.get("activity_at", ""), "worker_available" in row,
                  "execution_road" in row, row.get("upstream_terminal") is True,
                  row["id"]), reverse=True)


def _record(center, operation_id, outcome, observation=None):
    with center._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        summary = json.loads(row["summary"] or "{}")
        outcome = {**(summary.get("swarm_lifecycle") or {}), **outcome}
        summary["swarm_lifecycle"] = outcome
        status, finished = row["status"], row["finished_at"]
        if observation is not None and observation["confirmed_terminal"]:
            summary["provider_terminal"] = observation
            summary["execution_complete"] = True
            status = "succeeded" if observation["status"] == "completed" else (
                "cancelled" if observation["status"] == "cancelled" else "failed")
            finished = observation.get("activity_at") or finished
        db.execute("UPDATE operations SET summary=?,status=?,finished_at=? WHERE id=?",
                   (_json(summary), status, finished, operation_id))
    return outcome


def consume_operation(center, operation_id):
    """Reconcile one exact bound delivery, then launch at most one next job."""
    if not _identifier(operation_id):
        return {"status": "ignored", "reason": "invalid_operation_id"}
    if getattr(_active, "consuming", False):
        return {"status": "deferred", "reason": "continuation_budget"}
    from host.swarm_runtime.locks import held
    path = center.state_dir / ("swarm-terminal-" + _hash(operation_id)[:32] + ".lock")
    with held(path) as lock:
        if lock != "acquired":
            return {"status": "deferred", "reason": "terminal_observer_" + lock}
        _active.consuming = True
        try:
            return _consume(center, operation_id)
        except Exception as exc:
            # Never store provider exception text or undo the original receipt.
            outcome = {"status": "deferred", "reason": getattr(exc, "kind", type(exc).__name__)}
            if getattr(exc, "retry_after", None) is not None:
                outcome["retry_after"] = exc.retry_after
            return _record(center, operation_id, outcome)
        finally:
            _active.consuming = False


def _consume(center, operation_id):
    with center._db() as db:
        row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
    if row is None:
        return {"status": "ignored", "reason": "operation_not_found"}
    operation = center._operation(row)
    summary = operation.get("summary") or {}
    if not (summary.get("swarm") or {}).get("task_key"):
        return {"status": "ignored", "reason": "not_bound_dispatch"}
    prior = summary.get("swarm_lifecycle") or {}
    if prior.get("next_operation_id"):
        with center._db() as db:
            child = db.execute("SELECT status FROM operations WHERE id=?", (prior["next_operation_id"],)).fetchone()
        if child is not None:
            # Even an uncertain child is already delivered-or-unknown. Its own
            # journal, never a replayed parent observation, owns that outcome.
            return _record(center, operation_id, {**prior, "replayed": True,
                           "status": "continued", "next_status": child["status"]})
    observations = _observations(center, operation)
    if not observations:
        return {"status": "pending", "reason": "terminal_not_observed"}
    observed = observations[0]
    if not observed["confirmed_terminal"]:
        return _record(center, operation_id, {"status": "deferred", "reason": "upstream_exit_unconfirmed",
                       "observation_id": observed["id"]})
    if len(_matching_operations(center, observed)) != 1:
        return _record(center, operation_id, {"status": "deferred", "reason": "ambiguous_provider_binding"})
    outcome = {**prior, "status": "reconciling", "observation_id": observed["id"], "delivery_released": True}
    _record(center, operation_id, outcome, observed)

    from .swarm_tasks import runtime, _feed
    from host.swarm_runtime.providers import enrich
    from host.swarm_runtime.runtime import _append, _merge_facts, _project, _seats, now_iso
    from host.swarm_runtime.routing import route
    from host import seat_census
    engine = runtime(center)
    moment = now_iso()
    binding = summary["swarm"]
    key, worker = binding["task_key"], binding["worker"]
    _, state = engine.store.read(refresh=False)
    task = _project(state, moment)["tasks"].get(key)
    if task is None:
        return _record(center, operation_id, {**outcome, "status": "deferred", "reason": "canonical_task_unknown"})
    fresh = enrich({key: task}, engine.state_dir, max_calls=4, now=moment)
    activity = _time(observed.get("activity_at"))
    clock = _time(moment)
    started = _time(operation["started_at"])
    valid_activity = activity is not None and started is not None and started <= activity <= clock

    def mutation(current):
        _merge_facts(current, fresh.get("provider_facts", {}))
        view = _project(current, moment)
        row = view["tasks"].get(key, {})
        claim = current.get("operations", {}).get(binding.get("claim_operation_id"), {}).get("result", {})
        generation = next((item.get("started_at") for item in (claim.get("task"), claim.get("next"))
                           if isinstance(item, dict) and item.get("task_key") == key
                           and item.get("worker") == worker), None)
        # A real provider timestamp can renew an already known seat. It cannot
        # create capabilities or refresh a dead historical session to now.
        if valid_activity and worker in _seats(current):
            descriptor = current.setdefault("workers", {}).setdefault(worker, {})
            previous = _time(descriptor.get("heartbeat"))
            if previous is None or activity > previous:
                descriptor.update(seat=worker, heartbeat=observed["activity_at"])
        release_id = "provider-release:" + _hash([operation_id, observed[PROVIDERS[observed["provider"]][1]]])
        old_release = next((event for event in current.get("events", []) if event.get("id") == release_id), None)
        released = bool(old_release and row.get("state") == "OPEN")
        heartbeat = _time(row.get("heartbeat"))
        if (valid_activity and generation and row.get("state") == "ACTIVE"
                and row.get("worker") == worker and row.get("started_at") == generation
                and (heartbeat is None or heartbeat <= activity)):
            _append(current, [old_release or {"id": release_id,
                              "action": "RELEASE", "task_key": key, "worker": worker,
                              "at": observed["activity_at"], "expected_started_at": generation,
                              "source": observed["id"]}])
            view = _project(current, moment)
            released = view["tasks"].get(key, {}).get("state") == "OPEN"
        candidates = {k: v for k, v in view["tasks"].items()
                      if not (k == key and v.get("state") != "ACTIVE")}
        choice = route(candidates, worker, _seats(current), moment)
        if prior.get("next_task_key") and choice.get("reason") != "worker_active":
            # Resume the exact planned child after a crash before its journal
            # reservation. Do not silently choose a different operation body.
            target = prior["next_task_key"]
            choice = route({target: candidates[target]} if target in candidates else {},
                           worker, _seats(current), moment)
        return {"task_state": view["tasks"].get(key, {}).get("state", "UNKNOWN"),
                "released": released, "choice": choice}

    reconciled = engine.store.update(mutation)
    if reconciled.get("ok") is not True or reconciled.get("published") is not True:
        return _record(center, operation_id, {**outcome, "status": "deferred",
                       "reason": reconciled.get("error", "canonical_publication_unconfirmed")})
    result = reconciled.get("result") or {}
    outcome.update(task_state=result.get("task_state"), released=result.get("released", False),
                   claim_tip=reconciled.get("tip"), provider_calls=fresh.get("calls", 0))
    try:
        _feed(center, engine)
    except Exception:
        outcome["feed_sync"] = "deferred"
    choice = result.get("choice") or {}
    next_key = choice.get("task_key")
    reason = None
    retry_at = _time(observed.get("retry_not_before"))
    retry_seconds = observed.get("retry_after")
    timed_retry = bool(activity and isinstance(retry_seconds, (int, float))
                       and activity.timestamp() + retry_seconds > clock.timestamp())
    if (retry_at is not None and retry_at > clock) or timed_retry:
        reason = "provider_retry_boundary"
    elif observed["status"] != "completed":
        reason = "provider_execution_cancelled" if observed["status"] == "cancelled" else "provider_execution_failed"
    elif observed.get("execution_road") == "unconfigured":
        reason = "no_worker_road"
    elif not valid_activity or seat_census.liveness_at(observed["activity_at"], clock)[0] not in {"LIVE", "QUIET"}:
        reason = "worker_activity_not_current"
    elif observed.get("worker_available") is not True:
        reason = "worker_availability_unknown"
    elif not next_key:
        reason = "no_other_eligible_work" if result.get("released") and choice.get("reason") == "no_eligible_work" else choice.get("reason", "no_eligible_work")
    provider = observed["provider"]
    if provider == "gemini":
        arguments = {"peer": observed.get("peer"), "message": "Continue the canonical assignment using its bounded context and current provider facts."}
        if observed.get("peer") != worker:
            reason = "provider_route_unknown"
    else:
        arguments = {"pool_id": observed.get("pool_id"), "seat": worker, "async": True,
                     "prompt": "Continue the canonical assignment using its bounded context and current provider facts."}
        if not observed.get("pool_id") or observed.get("seat") != worker:
            reason = "provider_route_unknown"
    if reason:
        outcome.update(status="deferred", reason=reason)
        for field in ("retry_not_before", "retry_after"):
            if field in observed:
                outcome[field] = observed[field]
        if fresh.get("deferred"):
            outcome["provider_deferred"] = [{k: item[k] for k in ("task_key", "reason", "retry_not_before") if k in item}
                                            for item in fresh["deferred"][:4]]
        return _record(center, operation_id, outcome)
    child_id = prior.get("next_operation_id") or "continue-" + _hash([operation_id, provider, observed[PROVIDERS[provider][1]], next_key])[:48]
    # Persist chosen identity before crossing the provider boundary. Its own
    # existing operation journal decides whether delivery happened or is unknown.
    outcome.update(status="dispatching", next_task_key=next_key, next_operation_id=child_id)
    _record(center, operation_id, outcome)
    delivered = center.call_tool({"operation_id": child_id, "runtime_id": operation["runtime"],
                                 "name": PROVIDERS[provider][0], "arguments": arguments,
                                 "swarm": {"task_key": next_key, "worker": worker}})
    outcome.update(status="continued", next_status=delivered.get("status"))
    return _record(center, operation_id, outcome)
