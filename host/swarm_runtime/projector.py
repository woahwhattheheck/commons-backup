"""Deterministic event projection and reconciliation, without provider calls.

The event log is durable input. This projection is disposable. Actor messages
can describe artifacts but only provider facts close shipment. The dispatcher
uses renewable custody; none of this restricts independent direct work.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping

from host import seat_census
from .identity import _repo as _repo_name, key_parts, task_key

UNKNOWN = "UNKNOWN"
SCHEMA = "commons-swarm-runtime/v1"
TERMINAL = {"SHIPPED", "BLOCKED", "SUPERSEDED", "ABANDONED"}
ACTIONS = {"OPEN", "TAKE", "HEARTBEAT", "SHIP", "BLOCK", "SUPERSEDE", "ABANDON", "RECOVER", "RELEASE"}
PROVENANCE_LIMIT = 32
PROVIDER_MAX_AGE_S = 300
_INGEST_FIELDS = {"seq", "sequence", "ingest_seq", "ingestion_seq", "_seq", "ingested_at"}
_COPY_FIELDS = (
    "model", "harness", "artifact", "repo", "base_sha", "head_sha", "branch", "pr",
    "issue", "required_capabilities", "priority", "exact_error", "title", "next_action",
)


def _time(value):
    if isinstance(value, dt.datetime):
        stamp = value
    else:
        try:
            stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else UNKNOWN


def _known(value):
    return value is not None and value != "" and value != UNKNOWN


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _order(event):
    for field in ("ingest_seq", "ingestion_seq", "sequence", "seq", "_seq"):
        value = event.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            return 0, value, "", str(event.get("id", ""))
    cursor = event.get("c") or event.get("ingest_cursor")
    if isinstance(cursor, str) and "|" in cursor:
        return 1, 0, cursor, str(event.get("id", ""))
    stamp = _time(event.get("at", event.get("ts")))
    # ISO text puts fractional seconds before the corresponding whole second.
    # Sequence/cursor order above remains authoritative; only this fallback
    # compares chronology, with undated events still sorted last.
    return 2, 0, stamp or dt.datetime.max.replace(tzinfo=dt.timezone.utc), str(event.get("id", ""))


def _newer_legacy_custody(record, event, now):
    """Recognize an observed claim generation, not an ordinary attempted TAKE."""
    from host.coordination_state import repository_claim_key

    if not record["task_key"].startswith("github:") or not _known(event.get("worker")):
        return False
    parts = key_parts(record["task_key"])
    key = repository_claim_key(parts["kind"], parts["number"], parts["repo"])
    source = "legacy-claim:holdings/" + key + ".json"
    if event.get("source") != source or not re.fullmatch(
            re.escape(source) + r":[0-9a-f]{64}:take", str(event.get("id", ""))):
        return False
    ttl = event.get("legacy_ttl_s")
    if type(ttl) is not int or not 1 <= ttl <= 7200:
        return False
    taken, started = _time(event.get("at")), _time(event.get("started_at"))
    heartbeat = _time(event.get("heartbeat"))
    if taken is None or taken != started or heartbeat is None or heartbeat < taken:
        return False
    if seat_census.heartbeat_ahead_s(taken, now) or seat_census.heartbeat_ahead_s(heartbeat, now):
        return False
    prior = [stamp for field in ("started_at", "heartbeat")
             if (stamp := _time(record.get(field))) is not None]
    return not prior or taken > max(prior)


def _record(key, event):
    parts = key_parts(key)
    record = {field: UNKNOWN for field in (
        "worker", "model", "harness", "source", "started_at", "heartbeat",
        "latest_activity", "last_activity_at", "feed_cursor", "base_sha",
        "head_sha", "branch", "merge_sha", "artifact", "blocker", "next_action",
        "superseded_by", "repo", "issue", "pr", "provider_state", "closed_at",
    )}
    record.update({"task_key": key, "state": "OPEN", "created_at": event.get("at") or UNKNOWN,
                   "source_event_ids": [], "sources": [], "required_capabilities": [],
                   "recoverable": False, "collision_count": 0, "dispatchable": True,
                   "reconciliation_needed": UNKNOWN})
    if parts["kind"] in {"issue", "pr"}:
        record["repo"] = parts["repo"]
        record[parts["kind"]] = parts["number"]
    return record


def _append_bounded(values, value, limit=PROVENANCE_LIMIT):
    if value not in values:
        values.append(value)
        del values[:-limit]


def _provenance(record, event):
    _append_bounded(record["source_event_ids"], event["id"])
    for value in event.get("source_event_ids") or []:
        _append_bounded(record["source_event_ids"], value)
    if _known(event.get("source")):
        record["source"] = event["source"]
        _append_bounded(record["sources"], event["source"], 8)


def _metadata(record, event):
    for field in _COPY_FIELDS:
        if _known(event.get(field)):
            if field == "repo":
                if not record["task_key"].startswith("github:"):
                    try:
                        record[field] = _repo_name(event[field])
                    except ValueError:
                        pass
                continue
            # The issue/PR defining the canonical key cannot be changed by prose.
            if field in {"issue", "pr"} and record["task_key"].endswith(f":{field}:{record[field]}"):
                continue
            if field == "base_sha" and _known(record[field]) and not (
                str(event.get("action", "")).upper() == "TAKE" and record["state"] != "ACTIVE"
            ):
                continue
            record[field] = event[field]
    if _known(event.get("feed_cursor")):
        old = record["feed_cursor"]
        new = str(event["feed_cursor"])
        if old == UNKNOWN or new > old:
            record["feed_cursor"] = new


def _activity(record, at, now, rejected, event_id):
    stamp = _time(at)
    if stamp is None:
        return
    if seat_census.heartbeat_ahead_s(stamp, now):
        rejected.append({"id": event_id, "task_key": record["task_key"], "reason": "heartbeat_future_skew"})
        return
    old = _time(record["heartbeat"])
    if old is None or stamp > old:
        record["heartbeat"] = _iso(stamp)
        record["latest_activity"] = _iso(stamp)
        record["last_activity_at"] = _iso(stamp)


def _seats_by_name(seats):
    if isinstance(seats, Mapping):
        if "seats" in seats or "roster" in seats:
            rows = list(seats.get("roster") or []) + list(seats.get("seats") or [])
        else:
            rows = [dict(row, seat=name) for name, row in seats.items() if isinstance(row, Mapping)]
    else:
        rows = seats or []
    return {str(row.get("seat", row.get("name", ""))): row for row in rows if isinstance(row, Mapping)}


def _lease(record, seat, now):
    declared = seat.get("declared", seat) if seat else {}
    candidates = [record.get("heartbeat"), declared.get("heartbeat"), record.get("provider_activity_at")]
    valid = [stamp for value in candidates if (stamp := _time(value)) is not None
             and not seat_census.heartbeat_ahead_s(stamp, now)]
    heartbeat = max(valid) if valid else None
    liveness, age = seat_census.liveness_at(heartbeat, now)
    # No heartbeat is never interpreted as a permanently held lease. A valid
    # TAKE supplies activity; legacy undated custody can be recovered immediately.
    recoverable = record["state"] == "ACTIVE" and liveness not in {"LIVE", "QUIET"}
    record["recoverable"] = recoverable
    record["owner_liveness"] = liveness
    record["lease"] = {"heartbeat": _iso(heartbeat), "liveness": liveness,
                       "age_s": age if age is not None else UNKNOWN,
                       "reason": "stale_owner" if recoverable else "renewed_activity"}
    for field in ("model", "harness"):
        if record[field] == UNKNOWN and _known(declared.get(field)):
            record[field] = declared[field]
    if _known(declared.get("feed_cursor")):
        cursor = str(declared["feed_cursor"])
        if record["feed_cursor"] == UNKNOWN or cursor > record["feed_cursor"]:
            record["feed_cursor"] = cursor


def _merge_sha(fact):
    for field in ("merge_sha", "merge_commit_sha"):
        if _known(fact.get(field)):
            return fact[field]
    return UNKNOWN


def _merged(fact):
    return (fact.get("merged") is True or str(fact.get("state", "")).upper() == "MERGED") and _known(
        _merge_sha(fact))


def _landed_artifact(fact):
    """A provider-confirmed complete commit artifact; SHIP prose cannot set it."""
    return (
        fact.get("artifact_landed") is True
        and isinstance(fact.get("artifact_sha"), str)
        and re.fullmatch(r"[0-9a-fA-F]{40}", fact["artifact_sha"]) is not None
        and isinstance(fact.get("landed_sha"), str)
        and re.fullmatch(r"[0-9a-fA-F]{40}", fact["landed_sha"]) is not None
        and (fact.get("provider") == "github" or _known(fact.get("source")))
    )


def normalize_equivalent(value):
    """Describe exact-head ancestry as integration, never as a PR merge.

    Older provider snapshots labelled the current main commit ``merge_sha``.
    Reconstruct those records from their retained comparison proof on read so
    a cached observation cannot keep asserting a merge that did not happen.
    Genuine merged-PR equivalents without this ancestry proof are unchanged.
    """
    if not isinstance(value, Mapping):
        return value
    equivalent = dict(value)
    proof = equivalent.get("evidence")
    if not isinstance(proof, Mapping) or proof.get("kind") != "exact_head_ancestry":
        return equivalent
    for field in ("merged", "merge_sha", "merge_commit_sha", "merged_at"):
        equivalent.pop(field, None)
    if str(equivalent.get("state", "")).upper() == "MERGED":
        equivalent.pop("state", None)
    equivalent.update(artifact_landed=True, artifact_sha=proof.get("head_sha", UNKNOWN),
                      landed_sha=proof.get("target_sha", UNKNOWN))
    contained = (proof.get("status") in {"ahead", "identical"}
                 and proof.get("behind_by") == 0
                 and not isinstance(proof.get("behind_by"), bool)
                 and proof.get("merge_base_sha") == proof.get("head_sha")
                 and _landed_artifact(equivalent))
    equivalent["artifact_landed"] = equivalent["integrated"] = contained
    if not contained:
        equivalent["landed_sha"] = UNKNOWN
    return equivalent


def merge_facts(facts, incoming):
    """Fold observed facts without discarding immutable shipment evidence."""
    for key, fact in incoming.items():
        old = copy.deepcopy(facts.get(key, {}))
        fact = copy.deepcopy(fact)
        for row in (old, fact):
            for field in ("equivalent", "superseded_by"):
                if field in row:
                    row[field] = normalize_equivalent(row[field])
        if old:
            facts[key] = old
        # A failed or older refresh cannot erase a landed immutable fact.
        if _merged(old) or _landed_artifact(old):
            continue
        observed, previous = _time(fact.get("observed_at")), _time(old.get("observed_at"))
        # Baked listings deliberately carry UNKNOWN observations. Text ordering
        # would pin those facts forever and misorder equivalent timezone offsets.
        # Confirmed shipment is irreversible even when observed before a stale
        # open listing, or when that listing arrives first in the same batch.
        immutable = _merged(fact) or _landed_artifact(fact)
        if immutable and previous is not None and (observed is None or observed < previous):
            # Keep newer auxiliary details, but retain the shipment fact's own
            # observation/source and immutable merge or ancestry evidence.
            for field in ("head_sha", "branch", "base_sha", "updated_at", "pushed_at",
                          "title", "issue", "issues", "closing_issues"):
                if _known(old.get(field)):
                    fact[field] = old[field]
        if (immutable or previous is None
                or (observed is not None and observed >= previous)):
            for field in ("equivalent", "superseded_by"):
                previous = old.get(field)
                current = fact.get(field)
                if isinstance(previous, dict) and (_merged(previous) or _landed_artifact(previous)):
                    if not isinstance(current, dict) or not (_merged(current) or _landed_artifact(current)):
                        fact[field] = previous
            facts[key] = fact


def _fact_key(fact):
    try:
        return task_key(fact)
    except (ValueError, TypeError):
        return None


def _provider_facts(facts, rejected, needed_keys=None):
    normalized = {}
    items = facts.items() if isinstance(facts, Mapping) else ((_fact_key(f), f) for f in facts or [])
    for key, fact in items:
        if not isinstance(fact, Mapping):
            continue
        try:
            key = task_key(key) if key else task_key(fact)
        except (ValueError, TypeError) as exc:
            rejected.append({"source": "provider", "reason": str(exc)})
            continue
        # Validate every identity, including aliases and unused facts, before
        # limiting defensive copies to coordinates this projection can read.
        if needed_keys is not None and key not in needed_keys:
            continue
        merge_facts(normalized, {key: dict(fact)})
    return normalized


def _reconcile(record, fact, now, exact_task_fact=True):
    for field in ("head_sha", "branch", "artifact", "pr"):
        if _known(fact.get(field)):
            record[field] = fact[field]
    if _known(fact.get("state")):
        record["provider_state"] = fact["state"]
    record["provider_observed_at"] = fact.get("observed_at") or UNKNOWN
    record["provider_source"] = fact.get("source") or UNKNOWN
    if _known(fact.get("reconciliation_pending")):
        record["provider_reconciliation_pending"] = fact["reconciliation_pending"]
    for field in ("updated_at", "pushed_at", "merged_at"):
        stamp = _time(fact.get(field))
        previous = _time(record.get("provider_activity_at"))
        if stamp is not None and not seat_census.heartbeat_ahead_s(stamp, now) and (previous is None or stamp > previous):
            record["provider_activity_at"] = _iso(stamp)
    current_base = fact.get("current_base_sha") or fact.get("main_sha") or fact.get("base_sha")
    if _known(current_base):
        record["current_base_sha"] = current_base
        record["needs_rebase"] = _known(record["base_sha"]) and current_base != record["base_sha"]
    equivalent = fact.get("equivalent") or fact.get("superseded_by")
    if _merged(fact):
        record["state"] = "SHIPPED"
        record["merge_sha"] = _merge_sha(fact)
        record["closed_at"] = fact.get("merged_at") or UNKNOWN
        record["shipment_source"] = "provider"
        record["blocker"] = record["next_action"] = UNKNOWN
        record["superseded_by"] = UNKNOWN
        record["recoverable"] = False
        record["dispatchable"] = False
        record["reconciliation_needed"] = UNKNOWN
    elif exact_task_fact and _landed_artifact(fact):
        record["state"] = "SHIPPED"
        record["artifact_sha"] = fact["artifact_sha"]
        record["landed_sha"] = fact["landed_sha"]
        record["closed_at"] = fact.get("landed_at") or fact.get("observed_at") or UNKNOWN
        record["shipment_source"] = "provider"
        record["shipment_kind"] = "landed_artifact"
        record["provider_freshness"] = "IMMUTABLE"
        record["merge_sha"] = UNKNOWN
        record["blocker"] = record["next_action"] = record["superseded_by"] = UNKNOWN
        record["recoverable"] = record["dispatchable"] = False
        record["reconciliation_needed"] = UNKNOWN
    elif isinstance(equivalent, Mapping) and (
        _merged(equivalent) or (exact_task_fact and _landed_artifact(equivalent))
    ):
        record["state"] = "SUPERSEDED"
        record["superseded_by"] = dict(equivalent)
        record["closed_at"] = (equivalent.get("merged_at") or equivalent.get("landed_at")
                               or equivalent.get("observed_at") or UNKNOWN)
        record["provider_freshness"] = "IMMUTABLE"
        if _landed_artifact(equivalent):
            record["landed_sha"] = equivalent["landed_sha"]
        record["recoverable"] = False
        record["dispatchable"] = False
        record["reconciliation_needed"] = UNKNOWN
    elif fact.get("merged") is True or str(fact.get("state", "")).upper() == "MERGED":
        record["shipment_claim"] = {"source": "provider", "reason": "merge_sha_unknown"}
        record["dispatchable"] = False
        record["reconciliation_needed"] = "merge_sha"


def _dispatch_freshness(record, now):
    """Stale provider state is context, never an automatic work assignment.

    This only controls the dispatcher. OPEN and recoverable remain visible, and
    direct work does not acquire an admission requirement. Confirmed merges are
    immutable facts; mutable GitHub state needs a recent shared observation.
    """
    if not record["task_key"].startswith("github:"):
        return
    observed = _time(record.get("provider_observed_at"))
    _, age = seat_census.liveness_at(observed, now)
    record["provider_age_s"] = age if age is not None else UNKNOWN
    record["provider_freshness"] = (
        "UNKNOWN" if age is None else "CURRENT" if age <= PROVIDER_MAX_AGE_S else "STALE")
    if record["state"] in TERMINAL:
        record["dispatchable"] = False
        if record.get("shipment_source") == "provider" or (
            isinstance(record.get("superseded_by"), Mapping) and (
                _merged(record["superseded_by"]) or _landed_artifact(record["superseded_by"]))
        ):
            record["provider_freshness"] = "IMMUTABLE"
        return
    if record["reconciliation_needed"] == "merge_sha":
        return
    provider_state = str(record.get("provider_state", "")).upper()
    if age is None or age > PROVIDER_MAX_AGE_S or provider_state not in {"OPEN", "CLOSED"}:
        record["dispatchable"] = False
        record["reconciliation_needed"] = "provider_state"
    elif provider_state == "CLOSED":
        record["dispatchable"] = False
        record["reconciliation_needed"] = "closure_evidence"


def project(events, now=None, seats=None, provider_facts=None):
    """Rebuild canonical tasks from replayable events and current provider facts.

    Explicit ingestion sequences win over author timestamps. Input order is not
    authority. Identical event IDs/bodies collapse; conflicting bodies with one ID
    are quarantined together so a retry cannot silently alter history. Provenance
    is bounded here; the complete event history remains in the input log.
    """
    moment = _time(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    if moment is None:
        raise ValueError("now must be an ISO-8601 timestamp")
    tasks, collisions, rejected = {}, [], []
    by_id = {}
    for event in events:
        if not isinstance(event, Mapping) or not _known(event.get("id")):
            rejected.append({"reason": "event requires a stable id"})
            continue
        event = dict(event)
        event["id"] = str(event["id"])
        body = {key: value for key, value in event.items() if key not in _INGEST_FIELDS}
        try:
            digest = hashlib.sha256(_json(body).encode()).hexdigest()
        except (TypeError, ValueError):
            rejected.append({"id": event["id"], "reason": "event is not JSON serializable"})
            continue
        variants = by_id.setdefault(event["id"], {})
        if digest not in variants or _order(event) < _order(variants[digest]):
            variants[digest] = event
    accepted = []
    for event_id, variants in sorted(by_id.items()):
        if len(variants) != 1:
            rejected.append({"id": event_id, "reason": "event_id_conflict", "digests": sorted(variants)})
        else:
            accepted.append(next(iter(variants.values())))
    for event in sorted(accepted, key=_order):
        action = str(event.get("action", "")).upper()
        if action not in ACTIONS:
            rejected.append({"id": event["id"], "reason": "unknown action", "action": action})
            continue
        try:
            key = task_key(event)
        except (ValueError, TypeError) as exc:
            rejected.append({"id": event["id"], "reason": str(exc)})
            continue
        record = tasks.get(key)
        if record is None:
            record = tasks[key] = _record(key, event)
        _provenance(record, event)
        worker = event.get("worker") or UNKNOWN
        if action == "TAKE" and record["state"] == "ACTIVE" and worker != record["worker"]:
            if _newer_legacy_custody(record, event, moment):
                # The claims branch already changed custody. Seat activity on
                # other work cannot keep its former task owner in possession.
                record.update(previous_worker=record["worker"], worker=UNKNOWN,
                              model=UNKNOWN, harness=UNKNOWN, state="OPEN",
                              claim_transferred_at=event["at"])
            else:
                collision = {"task_key": key, "event_id": event["id"], "worker": worker,
                             "existing_worker": record["worker"], "reason": "already_active"}
                collisions.append(collision)
                record["collision_count"] += 1
                continue
        if record["state"] in TERMINAL:
            if action == "TAKE":
                collisions.append({"task_key": key, "event_id": event["id"], "worker": worker,
                                   "reason": "already_terminal", "state": record["state"]})
            continue
        if action == "RELEASE":
            if record["state"] != "ACTIVE":
                continue
            started = _time(record["started_at"])
            expected = _time(event.get("expected_started_at"))
            if worker == UNKNOWN or worker != record["worker"] or started is None or expected is None or expected < started:
                rejected.append({"id": event["id"], "task_key": key, "reason": "custody_changed"})
                continue
            at, heartbeat = _time(event.get("at")), _time(record["heartbeat"])
            if at is None or seat_census.heartbeat_ahead_s(at, moment) or at < started or (heartbeat is not None and at < heartbeat):
                rejected.append({"id": event["id"], "task_key": key, "reason": "release_not_current"})
                continue
            record.update(previous_worker=record["worker"], worker=UNKNOWN,
                          model=UNKNOWN, harness=UNKNOWN, state="OPEN",
                          released_at=_iso(at), recoverable=False)
            continue
        if action == "RECOVER":
            expected = event.get("expected_worker")
            if expected and expected != record["worker"]:
                rejected.append({"id": event["id"], "task_key": key, "reason": "custody_changed"})
                continue
            expected_heartbeat = event.get("expected_heartbeat")
            if expected_heartbeat is not None and expected_heartbeat != record["heartbeat"]:
                rejected.append({"id": event["id"], "task_key": key, "reason": "heartbeat_changed"})
                continue
            at = _time(event.get("at"))
            live, _ = seat_census.liveness_at(record["heartbeat"], at)
            if at is None or seat_census.heartbeat_ahead_s(at, moment) or live in {"LIVE", "QUIET"}:
                rejected.append({"id": event["id"], "task_key": key, "reason": "custody_not_stale"})
                continue
            record["previous_worker"] = record["worker"]
            record["worker"] = UNKNOWN
            record["model"] = record["harness"] = UNKNOWN
            record["state"] = "OPEN"
            record["recovered_at"] = _iso(at)
            record["recoverable"] = False
            continue
        if action in {"TAKE", "HEARTBEAT"} and worker == UNKNOWN:
            rejected.append({"id": event["id"], "task_key": key, "reason": "worker_unknown"})
            continue
        if action in {"HEARTBEAT", "SHIP", "BLOCK", "SUPERSEDE", "ABANDON"} and record["state"] == "ACTIVE" and worker not in {UNKNOWN, record["worker"]}:
            rejected.append({"id": event["id"], "task_key": key, "reason": "different_current_worker"})
            continue
        _metadata(record, event)
        if action == "OPEN":
            continue
        if action == "TAKE":
            if record["state"] != "ACTIVE":
                record["state"] = "ACTIVE"
                record["worker"] = worker
                record["started_at"] = event.get("at") or UNKNOWN
                record["heartbeat"] = UNKNOWN
            _activity(record, event.get("at"), moment, rejected, event["id"])
        elif action == "HEARTBEAT":
            if record["state"] == "ACTIVE":
                _activity(record, event.get("at"), moment, rejected, event["id"])
        elif action == "SHIP":
            record["shipment_claim"] = {"event_id": event["id"], "at": event.get("at") or UNKNOWN,
                                        "merge_sha": event.get("merge_sha") or UNKNOWN}
            _activity(record, event.get("at"), moment, rejected, event["id"])
        elif action == "BLOCK":
            if not _known(event.get("blocker")) or not _known(event.get("next_action")):
                rejected.append({"id": event["id"], "task_key": key, "reason": "block_requires_blocker_and_next_action"})
                continue
            record.update(state="BLOCKED", blocker=event["blocker"], next_action=event["next_action"], closed_at=event.get("at") or UNKNOWN)
        elif action == "SUPERSEDE":
            if not _known(event.get("superseded_by")):
                rejected.append({"id": event["id"], "task_key": key, "reason": "supersede_requires_replacement"})
                continue
            record.update(state="SUPERSEDED", superseded_by=event["superseded_by"], closed_at=event.get("at") or UNKNOWN)
        elif action == "ABANDON":
            record.update(state="ABANDONED", closed_at=event.get("at") or UNKNOWN)
    needed_keys = set(tasks)
    fallback_keys = {}
    for key, record in tasks.items():
        if _known(record["repo"]) and _known(record["pr"]):
            try:
                fallback = task_key(repo=record["repo"], kind="pr", number=record["pr"])
            except ValueError:
                # An exact fact can still reconcile unusable fallback fields.
                continue
            fallback_keys[key] = fallback
            needed_keys.add(fallback)
    facts = _provider_facts(provider_facts, rejected, needed_keys=needed_keys)
    for key, record in sorted(tasks.items()):
        fact = facts.get(key)
        exact_task_fact = fact is not None
        if fact is None:
            fact = facts.get(fallback_keys.get(key))
        if fact is not None:
            _reconcile(record, fact, moment, exact_task_fact=exact_task_fact)
    seat_map = _seats_by_name(seats)
    for record in tasks.values():
        _dispatch_freshness(record, moment)
        _lease(record, seat_map.get(str(record["worker"]), {}), moment)
    return {"schema": SCHEMA, "tasks": dict(sorted(tasks.items())), "collisions": collisions,
            "rejected": rejected, "event_count": len(accepted)}

