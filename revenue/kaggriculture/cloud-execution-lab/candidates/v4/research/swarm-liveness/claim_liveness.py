#!/usr/bin/env python3
"""Deterministic TITAN V4 claim-liveness and orphan-recovery auditor.

Consumes normalized JSONL exported from coordination surfaces. This module has
no Slack/GitHub credentials and performs no writes. Its output is routing
evidence only: STALE_CLAIM and collision arbitration are never permission to
overwrite peer work.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA = "titan-v4-claim-liveness/v1"
DEFAULT_CANONICAL_ROOT = (
    "main:revenue/kaggriculture/cloud-execution-lab/candidates/v4"
)
CLAIM = "CLAIM"
HEARTBEAT = "HEARTBEAT"
TERMINAL = {"COMPLETE", "RELEASED", "BLOCKED", "REJECTED", "SUPERSEDED"}
VALID_EVENTS = {CLAIM, HEARTBEAT, *TERMINAL}


class AuditError(ValueError):
    pass


def _timestamp(value: Any) -> float:
    if isinstance(value, bool):
        raise AuditError("timestamp must not be boolean")
    if isinstance(value, (int, float)):
        out = float(value)
        if not math.isfinite(out) or out < 0:
            raise AuditError("timestamp must be a finite nonnegative number")
        return out
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise AuditError("timestamp string is empty")
        try:
            numeric = float(text)
        except ValueError:
            numeric = None
        if numeric is not None:
            if not math.isfinite(numeric) or numeric < 0:
                raise AuditError("timestamp must be a finite nonnegative number")
            return numeric
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError as exc:
            raise AuditError(f"invalid timestamp {value!r}") from exc
        if parsed.tzinfo is None:
            raise AuditError("ISO timestamp must include timezone")
        return parsed.timestamp()
    raise AuditError("timestamp must be numeric or timezone-aware ISO-8601")


def _strict_bool(value: Any, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        raise AuditError(f"{field} must be boolean")
    return value


@dataclass(frozen=True)
class Event:
    index: int
    ts: float
    lane: str
    session: str
    event: str
    event_id: str | None
    canonical_root: str | None
    writes_repo: bool
    requires_artifact: bool
    artifact: str | None
    channel: str | None
    thread_ts: str | None
    scope_key: str | None

    @classmethod
    def parse(cls, raw: Any, index: int) -> "Event":
        if not isinstance(raw, dict):
            raise AuditError(f"event[{index}] must be an object")
        lane = raw.get("lane")
        session = raw.get("session")
        event = raw.get("event")
        if not isinstance(lane, str) or not lane.strip():
            raise AuditError(f"event[{index}].lane must be a nonempty string")
        if not isinstance(session, str) or not session.strip():
            raise AuditError(f"event[{index}].session must be a nonempty string")
        if not isinstance(event, str):
            raise AuditError(f"event[{index}].event must be a string")
        event = event.strip().upper()
        if event not in VALID_EVENTS:
            raise AuditError(f"event[{index}].event unsupported: {event!r}")

        def opt_str(name: str) -> str | None:
            value = raw.get(name)
            if value is None:
                return None
            if not isinstance(value, str) or not value.strip():
                raise AuditError(f"event[{index}].{name} must be a nonempty string")
            return value.strip()

        return cls(
            index=index,
            ts=_timestamp(raw.get("ts")),
            lane=lane.strip(),
            session=session.strip(),
            event=event,
            event_id=opt_str("event_id"),
            canonical_root=opt_str("canonical_root"),
            writes_repo=_strict_bool(raw.get("writes_repo"), "writes_repo"),
            requires_artifact=_strict_bool(
                raw.get("requires_artifact"), "requires_artifact"
            ),
            artifact=opt_str("artifact"),
            channel=opt_str("channel"),
            thread_ts=opt_str("thread_ts"),
            scope_key=opt_str("scope_key"),
        )


def load_jsonl(lines: Iterable[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue

        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            obj: dict[str, Any] = {}
            for key, value in pairs:
                if key in obj:
                    raise AuditError(
                        f"line {line_no}: duplicate JSON object key {key!r}"
                    )
                obj[key] = value
            return obj

        try:
            value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise AuditError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise AuditError(f"line {line_no}: JSON value must be an object")
        out.append(value)
    return out


def _arbitrate_fresh_owners(
    fresh: list[str], owners: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return advisory claim precedence for already-normalized ownership groups.

    Heartbeats never change precedence: the relevant timestamp is the CLAIM
    that opened the currently-active ownership epoch. A later re-CLAIM after a
    terminal event starts a new epoch because CLAIM processing resets claim_ts.
    Equal earliest claim timestamps intentionally fail closed.
    """
    active_claims = sorted(
        (float(owners[session]["claim_ts"]), session) for session in fresh
    )
    if not active_claims:
        return {
            "basis": "earliest_fresh_claim_ts",
            "advisory_only": True,
            "preferred_owner": None,
            "tied_earliest_claimants": [],
            "yield_candidates": [],
        }

    earliest_ts = active_claims[0][0]
    tied = [session for ts, session in active_claims if ts == earliest_ts]
    preferred = tied[0] if len(tied) == 1 else None
    yield_candidates = [
        session for ts, session in active_claims if ts > earliest_ts
    ]
    return {
        "basis": "earliest_fresh_claim_ts",
        "advisory_only": True,
        "preferred_owner": preferred,
        "preferred_claim_ts": earliest_ts if preferred is not None else None,
        "tied_earliest_claimants": tied if len(tied) > 1 else [],
        "yield_candidates": yield_candidates,
    }


def _active_status(fresh: list[str], stale: list[str]) -> str:
    if len(fresh) > 1:
        return "COLLISION"
    if fresh and stale:
        return "ACTIVE_WITH_STALE_OWNER"
    if fresh:
        return "ACTIVE"
    if stale:
        return "STALE_CLAIM"
    return "CLOSED"


def _scope_rows(
    lane_rows: list[dict[str, Any]], *, now: float, ttl_seconds: int
) -> list[dict[str, Any]]:
    """Collapse explicitly declared claim scopes across differently named lanes.

    scope_key is operator-supplied normalization only. This function never
    infers semantic equivalence from lane names or free text.
    """
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for lane_row in lane_rows:
        lane = lane_row["lane"]
        for owner in lane_row["owners"]:
            if owner["state"] != "ACTIVE" or owner.get("scope_key") is None:
                continue
            grouped[str(owner["scope_key"])][owner["session"]].append(
                {
                    "lane": lane,
                    "claim_ts": owner["claim_ts"],
                    "last_ts": owner["last_ts"],
                }
            )

    rows: list[dict[str, Any]] = []
    for scope_key in sorted(grouped):
        owners: dict[str, dict[str, Any]] = {}
        owner_rows: list[dict[str, Any]] = []
        fresh: list[str] = []
        stale: list[str] = []
        all_lanes: set[str] = set()
        for session in sorted(grouped[scope_key]):
            claims = grouped[scope_key][session]
            claim_ts = min(float(row["claim_ts"]) for row in claims)
            last_ts = max(float(row["last_ts"]) for row in claims)
            age = max(0.0, now - last_ts)
            lanes = sorted({str(row["lane"]) for row in claims})
            all_lanes.update(lanes)
            owners[session] = {"claim_ts": claim_ts}
            (stale if age > ttl_seconds else fresh).append(session)
            owner_rows.append(
                {
                    "session": session,
                    "claim_ts": claim_ts,
                    "last_ts": last_ts,
                    "age_seconds": round(age, 6),
                    "lanes": lanes,
                }
            )
        rows.append(
            {
                "scope_key": scope_key,
                "status": _active_status(fresh, stale),
                "lanes": sorted(all_lanes),
                "fresh_active_owners": fresh,
                "stale_active_owners": stale,
                "recovery_candidates": stale if not fresh else [],
                "arbitration": _arbitrate_fresh_owners(fresh, owners),
                "owners": owner_rows,
            }
        )
    return rows


def _epoch_eligibility(
    events: list[Event],
    *,
    now: float,
    canonical_root: str,
    conflicted_event_ids: set[str],
) -> tuple[list[bool], list[bool]]:
    """Classify canonical epoch membership before provider-id authority.

    Provider-id conflicts are excluded from the mirrored epoch state. This lets
    duplicate groups fail closed without allowing a quarantined duplicate CLAIM
    or terminal to open/close an epoch used to classify later rows. Epoch state
    is replayed in the same chronological `(ts,index)` order used by ownership
    application, while masks remain aligned to the caller's original row order.
    """
    epoch_contracts: dict[tuple[str, str], dict[str, Any]] = {}
    eligible: list[bool] = [False] * len(events)
    epoch_root_quarantined: list[bool] = [False] * len(events)

    for position in sorted(
        range(len(events)), key=lambda index: (events[index].ts, events[index].index)
    ):
        ev = events[position]
        future = ev.ts > now
        root_mismatch = (
            ev.canonical_root is not None and ev.canonical_root != canonical_root
        )
        repo_write_unbound = ev.writes_repo and ev.canonical_root != canonical_root
        root_quarantined = root_mismatch or repo_write_unbound

        epoch_key = (ev.lane, ev.session)
        epoch = epoch_contracts.get(epoch_key)
        epoch_quarantined = False
        if (
            not future
            and not root_quarantined
            and ev.event in ({HEARTBEAT} | TERMINAL)
            and epoch is not None
            and bool(epoch.get("active"))
            and bool(epoch.get("writes_repo"))
            and ev.canonical_root != epoch.get("canonical_root")
        ):
            epoch_quarantined = True

        authoritative = (
            not future
            and not root_quarantined
            and not epoch_quarantined
            and ev.event_id not in conflicted_event_ids
        )
        eligible[position] = authoritative
        epoch_root_quarantined[position] = epoch_quarantined
        if not authoritative:
            continue

        if ev.event == CLAIM:
            if epoch is None or not bool(epoch.get("active")):
                epoch_contracts[epoch_key] = {
                    "active": True,
                    "writes_repo": ev.writes_repo,
                    "canonical_root": ev.canonical_root,
                }
        elif ev.event in TERMINAL:
            if epoch is not None and bool(epoch.get("active")):
                epoch["active"] = False

    return eligible, epoch_root_quarantined


def audit_events(
    raw_events: Iterable[dict[str, Any]],
    *,
    as_of: Any,
    ttl_seconds: int = 15 * 60,
    canonical_root: str = DEFAULT_CANONICAL_ROOT,
) -> dict[str, Any]:
    if type(ttl_seconds) is not int or ttl_seconds <= 0:
        raise AuditError("ttl_seconds must be a positive integer")
    if not isinstance(canonical_root, str) or not canonical_root.strip():
        raise AuditError("canonical_root must be a nonempty string")
    now = _timestamp(as_of)
    canonical_root = canonical_root.strip()

    events = [Event.parse(raw, i) for i, raw in enumerate(raw_events)]
    anomalies: list[dict[str, Any]] = []

    # Find provider ids that conflict among rows actually eligible to affect the
    # canonical ownership epoch. Conflict discovery is monotone: once an id is
    # seen twice in an eligible state, its whole group stays quarantined. Each
    # newly quarantined group is removed from mirrored epoch state before the
    # next pass, so duplicate rows cannot manufacture later eligibility.
    conflicted_event_ids: set[str] = set()
    duplicate_evidence: dict[str, list[int]] = {}
    while True:
        candidate, _ = _epoch_eligibility(
            events,
            now=now,
            canonical_root=canonical_root,
            conflicted_event_ids=conflicted_event_ids,
        )
        indexes_by_id: dict[str, list[int]] = defaultdict(list)
        for ev, authoritative in zip(events, candidate):
            if authoritative and ev.event_id:
                indexes_by_id[ev.event_id].append(ev.index)
        newly_conflicted = {
            event_id: indexes
            for event_id, indexes in indexes_by_id.items()
            if len(indexes) > 1 and event_id not in conflicted_event_ids
        }
        if not newly_conflicted:
            break
        duplicate_evidence.update(newly_conflicted)
        conflicted_event_ids.update(newly_conflicted)

    authoritative_mask, epoch_root_quarantined = _epoch_eligibility(
        events,
        now=now,
        canonical_root=canonical_root,
        conflicted_event_ids=conflicted_event_ids,
    )

    for ev, epoch_quarantined in zip(events, epoch_root_quarantined):
        future = ev.ts > now
        if future:
            anomalies.append(
                {"kind": "future_event", "lane": ev.lane, "session": ev.session,
                 "event_id": ev.event_id, "ts": ev.ts}
            )

        root_mismatch = (
            ev.canonical_root is not None and ev.canonical_root != canonical_root
        )
        if root_mismatch:
            anomalies.append(
                {"kind": "noncanonical_root", "lane": ev.lane,
                 "session": ev.session, "observed": ev.canonical_root,
                 "expected": canonical_root, "event_id": ev.event_id}
            )
        if ev.writes_repo and ev.canonical_root is None:
            anomalies.append(
                {"kind": "repo_write_without_root", "lane": ev.lane,
                 "session": ev.session, "event_id": ev.event_id}
            )
        if epoch_quarantined:
            epoch = None
            # Reconstruct the expected root from the active writer epoch using
            # the same classifier semantics for diagnostic evidence only.
            # It is always the audited canonical root because writer CLAIMs are
            # structurally authoritative only when exactly bound to it.
            anomalies.append(
                {
                    "kind": "writer_epoch_followup_root_unbound",
                    "lane": ev.lane,
                    "session": ev.session,
                    "event": ev.event,
                    "event_id": ev.event_id,
                    "observed": ev.canonical_root,
                    "expected": canonical_root,
                }
            )

    for event_id in sorted(duplicate_evidence):
        indexes = duplicate_evidence[event_id]
        first_index = indexes[0]
        for duplicate_index in indexes[1:]:
            anomalies.append(
                {
                    "kind": "duplicate_event_id",
                    "event_id": event_id,
                    "first_index": first_index,
                    "duplicate_index": duplicate_index,
                }
            )

    authoritative_events = [
        ev for ev, authoritative in zip(events, authoritative_mask) if authoritative
    ]

    grouped: dict[str, list[Event]] = defaultdict(list)
    for ev in authoritative_events:
        grouped[ev.lane].append(ev)

    lane_rows: list[dict[str, Any]] = []
    for lane in sorted(grouped):
        lane_events = sorted(grouped[lane], key=lambda e: (e.ts, e.index))
        owners: dict[str, dict[str, Any]] = {}
        claimed_once: set[str] = set()

        for ev in lane_events:
            state = owners.get(ev.session)
            if ev.event == CLAIM:
                claimed_once.add(ev.session)
                if state is not None and state["state"] == "ACTIVE":
                    anomalies.append(
                        {"kind": "repeat_claim_while_active", "lane": lane,
                         "session": ev.session, "event_id": ev.event_id,
                         "opening_claim_ts": state.get("claim_ts")}
                    )
                    if ev.scope_key is not None and ev.scope_key != state.get("scope_key"):
                        anomalies.append(
                            {"kind": "scope_key_drift", "lane": lane,
                             "session": ev.session, "event": ev.event,
                             "claimed_scope_key": state.get("scope_key"),
                             "observed_scope_key": ev.scope_key,
                             "event_id": ev.event_id}
                        )
                    if (
                        ev.requires_artifact != bool(state.get("requires_artifact"))
                        or (
                            ev.artifact is not None
                            and ev.artifact != state.get("artifact")
                        )
                    ):
                        anomalies.append(
                            {"kind": "active_claim_contract_drift", "lane": lane,
                             "session": ev.session, "event_id": ev.event_id}
                        )
                    # CLAIM repetition is not a heartbeat. It cannot refresh
                    # liveness, replace the opening claim timestamp, or mutate
                    # the active claim contract. Only terminal -> CLAIM starts
                    # a new ownership epoch.
                    continue
                owners[ev.session] = {
                    "state": "ACTIVE",
                    "claim_ts": ev.ts,
                    "last_ts": ev.ts,
                    "last_event": CLAIM,
                    "requires_artifact": ev.requires_artifact,
                    "artifact": ev.artifact,
                    "last_event_id": ev.event_id,
                    "scope_key": ev.scope_key,
                    "claim_writes_repo": ev.writes_repo,
                    "claim_canonical_root": ev.canonical_root,
                }
            elif ev.event == HEARTBEAT:
                if state is None or state["state"] != "ACTIVE":
                    anomalies.append(
                        {"kind": "heartbeat_without_active_claim", "lane": lane,
                         "session": ev.session, "event_id": ev.event_id}
                    )
                    continue
                if ev.scope_key is not None and ev.scope_key != state.get("scope_key"):
                    anomalies.append(
                        {"kind": "scope_key_drift", "lane": lane,
                         "session": ev.session, "event": ev.event,
                         "claimed_scope_key": state.get("scope_key"),
                         "observed_scope_key": ev.scope_key,
                         "event_id": ev.event_id}
                    )
                state["last_ts"] = ev.ts
                state["last_event"] = HEARTBEAT
                state["last_event_id"] = ev.event_id
                if ev.artifact:
                    state["artifact"] = ev.artifact
            else:
                if state is None or ev.session not in claimed_once:
                    anomalies.append(
                        {"kind": "terminal_without_claim", "lane": lane,
                         "session": ev.session, "terminal": ev.event,
                         "event_id": ev.event_id}
                    )
                    owners[ev.session] = {
                        "state": ev.event,
                        "claim_ts": None,
                        "last_ts": ev.ts,
                        "last_event": ev.event,
                        "requires_artifact": ev.requires_artifact,
                        "artifact": ev.artifact,
                        "last_event_id": ev.event_id,
                        "scope_key": ev.scope_key,
                        "claim_writes_repo": None,
                        "claim_canonical_root": None,
                    }
                    continue
                if ev.scope_key is not None and ev.scope_key != state.get("scope_key"):
                    anomalies.append(
                        {"kind": "scope_key_drift", "lane": lane,
                         "session": ev.session, "event": ev.event,
                         "claimed_scope_key": state.get("scope_key"),
                         "observed_scope_key": ev.scope_key,
                         "event_id": ev.event_id}
                    )
                required = bool(state.get("requires_artifact")) or ev.requires_artifact
                artifact = ev.artifact or state.get("artifact")
                if ev.event == "COMPLETE" and required and not artifact:
                    anomalies.append(
                        {"kind": "completion_without_required_artifact",
                         "lane": lane, "session": ev.session,
                         "event_id": ev.event_id}
                    )
                state["state"] = ev.event
                state["last_ts"] = ev.ts
                state["last_event"] = ev.event
                state["requires_artifact"] = required
                state["artifact"] = artifact
                state["last_event_id"] = ev.event_id

        fresh: list[str] = []
        stale: list[str] = []
        terminal: dict[str, str] = {}
        owner_rows: list[dict[str, Any]] = []
        for session in sorted(owners):
            state = owners[session]
            age = max(0.0, now - float(state["last_ts"]))
            if state["state"] == "ACTIVE":
                (stale if age > ttl_seconds else fresh).append(session)
            else:
                terminal[session] = str(state["state"])
            owner_rows.append(
                {
                    "session": session,
                    "state": state["state"],
                    "claim_ts": state.get("claim_ts"),
                    "age_seconds": round(age, 6),
                    "last_event": state["last_event"],
                    "last_ts": state["last_ts"],
                    "artifact": state.get("artifact"),
                    "scope_key": state.get("scope_key"),
                    "claim_writes_repo": state.get("claim_writes_repo"),
                    "claim_canonical_root": state.get("claim_canonical_root"),
                }
            )

        lane_rows.append(
            {
                "lane": lane,
                "status": _active_status(fresh, stale),
                "fresh_active_owners": fresh,
                "stale_active_owners": stale,
                "recovery_candidates": stale if not fresh else [],
                "terminal_owners": terminal,
                "arbitration": _arbitrate_fresh_owners(fresh, owners),
                "owners": owner_rows,
            }
        )

    scope_rows = _scope_rows(lane_rows, now=now, ttl_seconds=ttl_seconds)
    summary = {
        "lanes": len(lane_rows),
        "active": sum(r["status"] == "ACTIVE" for r in lane_rows),
        "active_with_stale_owner": sum(
            r["status"] == "ACTIVE_WITH_STALE_OWNER" for r in lane_rows
        ),
        "collisions": sum(r["status"] == "COLLISION" for r in lane_rows),
        "stale_claims": sum(r["status"] == "STALE_CLAIM" for r in lane_rows),
        "closed": sum(r["status"] == "CLOSED" for r in lane_rows),
        "scoped_active_groups": len(scope_rows),
        "scoped_collisions": sum(r["status"] == "COLLISION" for r in scope_rows),
        "cross_lane_scoped_collisions": sum(
            r["status"] == "COLLISION" and len(r["lanes"]) > 1 for r in scope_rows
        ),
        "anomalies": len(anomalies),
    }
    anomalies.sort(
        key=lambda x: (
            x.get("kind", ""),
            x.get("lane", ""),
            x.get("session", ""),
            x.get("event_id") or "",
            x.get("duplicate_index", -1),
        )
    )
    return {
        "schema": SCHEMA,
        "canonical_root": canonical_root,
        "as_of": now,
        "ttl_seconds": ttl_seconds,
        "policy": {
            "stale_is_overwrite_authority": False,
            "fresh_owner_blocks_recovery": True,
            "noncanonical_root_is_anomaly": True,
            "noncanonical_root_events_authoritative": False,
            "repo_writes_require_exact_canonical_root": True,
            "repo_write_without_canonical_root_authoritative": False,
            "read_only_missing_root_authoritative": True,
            "writer_epoch_followups_require_claim_root": True,
            "quarantined_events_reserve_provider_ids": False,
            "future_events_authoritative": False,
            "duplicate_event_id_replays_authoritative": False,
            "repeat_active_claims_authoritative": False,
            "earliest_fresh_claim_precedence_is_advisory": True,
            "equal_earliest_claim_tie_fails_closed": True,
            "scope_keys_are_explicit_only": True,
            "scope_keys_infer_semantic_equivalence": False,
            "arbitration_is_overwrite_authority": False,
        },
        "summary": summary,
        "lanes": lane_rows,
        "scope_groups": scope_rows,
        "anomalies": anomalies,
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", nargs="?", default="-", help="JSONL file or '-' for stdin")
    p.add_argument("--as-of", required=True, help="Unix seconds or timezone-aware ISO-8601")
    p.add_argument("--ttl-seconds", type=int, default=15 * 60)
    p.add_argument("--canonical-root", default=DEFAULT_CANONICAL_ROOT)
    p.add_argument("--output", default="-", help="JSON output path or '-' for stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.input == "-":
            raws = load_jsonl(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                raws = load_jsonl(fh)
        report = audit_events(
            raws,
            as_of=args.as_of,
            ttl_seconds=args.ttl_seconds,
            canonical_root=args.canonical_root,
        )
    except (AuditError, OSError) as exc:
        print(f"claim_liveness: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        try:
            with open(args.output, "x", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"claim_liveness: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
