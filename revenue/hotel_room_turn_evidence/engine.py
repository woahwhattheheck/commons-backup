#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hmac
from typing import Any, Mapping, Sequence

try:
    from .contracts import (
        AUTHORITY,
        DURATION_DAYS,
        KINDS,
        PILOT_ID,
        PRICE_USD,
        REPORT_SCHEMA,
        RETAINED_POLICY_SHA256,
        STATES,
        ContractError,
        _arr,
        _exact_keys,
        _fmt_time,
        _hex64,
        _int,
        _machine,
        _obj,
        _text,
        _time,
        canon,
        load_retained_policy,
        parse_evidence,
        parse_policy,
        sha256_bytes,
    )
except ImportError:  # direct execution from this directory
    from contracts import (  # type: ignore
        AUTHORITY,
        DURATION_DAYS,
        KINDS,
        PILOT_ID,
        PRICE_USD,
        REPORT_SCHEMA,
        RETAINED_POLICY_SHA256,
        STATES,
        ContractError,
        _arr,
        _exact_keys,
        _fmt_time,
        _hex64,
        _int,
        _machine,
        _obj,
        _text,
        _time,
        canon,
        load_retained_policy,
        parse_evidence,
        parse_policy,
        sha256_bytes,
    )

def _cell_for_kind(
    *,
    room: Mapping[str, str],
    kind: str,
    events: Sequence[dict[str, Any]],
    policy: Mapping[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    same_room = [
        event
        for event in events
        if event["room_id"] == room["room_id"] and event["kind"] == kind
    ]
    current = [
        event for event in same_room if event["turn_id"] == room["turn_id"]
    ]
    wrong_turn_count = len(same_room) - len(current)
    base: dict[str, Any] = {
        "kind": kind,
        "latest_event_ids": [],
        "state": None,
        "actor_id": None,
        "observed_at": None,
        "age_minutes": None,
    }
    if not current:
        reasons = [f"MISSING_{kind.upper()}"]
        if wrong_turn_count:
            reasons.append(f"WRONG_TURN_{kind.upper()}:{wrong_turn_count}")
        return {**base, "clear": False, "reasons": reasons}

    latest_time = max(
        _time(event["observed_at"], "event.observed_at") for event in current
    )
    latest = [
        event
        for event in current
        if _time(event["observed_at"], "event.observed_at") == latest_time
    ]
    latest.sort(key=lambda event: event["event_id"])
    base["latest_event_ids"] = [event["event_id"] for event in latest]
    base["observed_at"] = _fmt_time(latest_time)

    fingerprints = {
        (
            event["state"],
            event["actor_id"],
            event["detail_code"],
            event["source_ref_sha256"],
        )
        for event in latest
    }
    if len(fingerprints) > 1:
        return {
            **base,
            "clear": False,
            "reasons": [f"CONFLICT_{kind.upper()}"],
        }

    chosen = latest[0]
    base["state"] = chosen["state"]
    base["actor_id"] = chosen["actor_id"]
    age_seconds = (now - latest_time).total_seconds()
    if age_seconds >= 0:
        base["age_minutes"] = int(age_seconds // 60)
    if age_seconds < 0:
        return {
            **base,
            "clear": False,
            "reasons": [f"FUTURE_{kind.upper()}"],
        }
    if age_seconds > policy["max_age_minutes"][kind] * 60:
        return {
            **base,
            "clear": False,
            "reasons": [f"STALE_{kind.upper()}"],
        }
    if (
        kind == "manager_release"
        and chosen["actor_id"] not in set(policy["allowed_managers"])
    ):
        return {
            **base,
            "clear": False,
            "reasons": ["UNAUTHORIZED_MANAGER"],
        }
    if chosen["state"] != "CLEAR":
        return {
            **base,
            "clear": False,
            "reasons": [f"BLOCK_{kind.upper()}:{chosen['detail_code']}"],
        }
    return {**base, "clear": True, "reasons": []}


def compile_report(
    policy_raw: Any,
    evidence_raw: Any,
    *,
    expected_policy_sha256: str,
    now: dt.datetime,
) -> dict[str, Any]:
    if type(now) is not dt.datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ContractError("now must be timezone-aware datetime")
    now = now.astimezone(dt.timezone.utc)
    policy = parse_policy(policy_raw, expected_policy_sha256)
    events, _normalized_evidence, evidence_sha256 = parse_evidence(
        evidence_raw, policy
    )

    known_rooms = {room["room_id"] for room in policy["rooms"]}
    unknown_rooms = sorted(
        {event["room_id"] for event in events} - known_rooms
    )
    if unknown_rooms:
        raise ContractError(f"evidence references unknown rooms: {unknown_rooms}")

    room_results: list[dict[str, Any]] = []
    for room in policy["rooms"]:
        checks = [
            _cell_for_kind(
                room=room,
                kind=kind,
                events=events,
                policy=policy,
                now=now,
            )
            for kind in KINDS
        ]
        reasons = [
            reason for check in checks for reason in check["reasons"]
        ]
        status = "READY" if all(check["clear"] for check in checks) else "BLOCKED"
        room_results.append(
            {
                "room_id": room["room_id"],
                "turn_id": room["turn_id"],
                "status": status,
                "reasons": reasons,
                "checks": checks,
            }
        )

    ready = sum(room["status"] == "READY" for room in room_results)
    core = {
        "schema_version": REPORT_SCHEMA,
        "pilot_id": PILOT_ID,
        "property_id": policy["property_id"],
        "policy_sha256": policy["policy_sha256"],
        "evidence_sha256": evidence_sha256,
        "generated_at": _fmt_time(now),
        "commercial": {
            "price_usd": PRICE_USD,
            "duration_days": DURATION_DAYS,
        },
        "rooms": room_results,
        "summary": {
            "ready": ready,
            "blocked": len(room_results) - ready,
            "total": len(room_results),
        },
        "authority": dict(AUTHORITY),
    }
    return {**core, "report_sha256": sha256_bytes(canon(core))}


def report_receipt(report: Mapping[str, Any]) -> str:
    return sha256_bytes(canon(dict(report)))


def _validate_check(raw: Any, where: str) -> dict[str, Any]:
    check = _obj(raw, where)
    _exact_keys(
        check,
        {
            "kind",
            "latest_event_ids",
            "state",
            "actor_id",
            "observed_at",
            "age_minutes",
            "clear",
            "reasons",
        },
        where,
    )
    kind = _machine(check["kind"], f"{where}.kind")
    if kind not in KINDS:
        raise ContractError(f"{where}.kind unknown")
    ids_raw = _arr(check["latest_event_ids"], f"{where}.latest_event_ids")
    ids = [_machine(value, f"{where}.latest_event_ids[]") for value in ids_raw]
    if ids != sorted(set(ids)):
        raise ContractError(f"{where}.latest_event_ids must be sorted unique")
    state = check["state"]
    if state is not None and state not in STATES:
        raise ContractError(f"{where}.state invalid")
    actor = check["actor_id"]
    if actor is not None:
        actor = _machine(actor, f"{where}.actor_id")
    observed = check["observed_at"]
    if observed is not None:
        observed = _fmt_time(_time(observed, f"{where}.observed_at"))
    age = check["age_minutes"]
    if age is not None:
        age = _int(age, f"{where}.age_minutes", 0, 50_000_000)
    if type(check["clear"]) is not bool:
        raise ContractError(f"{where}.clear must be bool")
    reasons_raw = _arr(check["reasons"], f"{where}.reasons")
    reasons = [_text(reason, f"{where}.reasons[]", max_len=256) for reason in reasons_raw]
    if check["clear"] and reasons:
        raise ContractError(f"{where}.clear cannot carry reasons")
    if not check["clear"] and not reasons:
        raise ContractError(f"{where}.blocked check must carry reasons")
    return {
        "kind": kind,
        "latest_event_ids": ids,
        "state": state,
        "actor_id": actor,
        "observed_at": observed,
        "age_minutes": age,
        "clear": check["clear"],
        "reasons": reasons,
    }


def verify_report_history(
    report_raw: Any,
    *,
    expected_policy_sha256: str,
    expected_report_sha256: str,
) -> dict[str, Any]:
    expected_policy_sha256 = _hex64(
        expected_policy_sha256, "expected_policy_sha256"
    )
    expected_report_sha256 = _hex64(
        expected_report_sha256, "expected_report_sha256"
    )
    report = _obj(report_raw, "report")
    _exact_keys(
        report,
        {
            "schema_version",
            "pilot_id",
            "property_id",
            "policy_sha256",
            "evidence_sha256",
            "generated_at",
            "commercial",
            "rooms",
            "summary",
            "authority",
            "report_sha256",
        },
        "report",
    )
    if report["schema_version"] != REPORT_SCHEMA:
        raise ContractError("report.schema_version drift")
    if report["pilot_id"] != PILOT_ID:
        raise ContractError("report.pilot_id drift")
    _machine(report["property_id"], "report.property_id")
    report_policy_sha = _hex64(
        report["policy_sha256"], "report.policy_sha256"
    )
    if not hmac.compare_digest(report_policy_sha, expected_policy_sha256):
        raise ContractError("report policy root mismatch")
    _hex64(report["evidence_sha256"], "report.evidence_sha256")
    _fmt_time(_time(report["generated_at"], "report.generated_at"))

    commercial = _obj(report["commercial"], "report.commercial")
    _exact_keys(commercial, {"price_usd", "duration_days"}, "report.commercial")
    if _int(commercial["price_usd"], "report.commercial.price_usd", 0, 1_000_000) != PRICE_USD:
        raise ContractError("report commercial price drift")
    if _int(commercial["duration_days"], "report.commercial.duration_days", 1, 30) != DURATION_DAYS:
        raise ContractError("report commercial duration drift")

    authority = _obj(report["authority"], "report.authority")
    if authority != AUTHORITY:
        raise ContractError("report authority drift")

    rooms_raw = _arr(report["rooms"], "report.rooms")
    if not rooms_raw:
        raise ContractError("report.rooms must not be empty")
    seen_rooms: set[str] = set()
    seen_turns: set[str] = set()
    normalized_rooms: list[dict[str, Any]] = []
    for idx, item in enumerate(rooms_raw):
        where = f"report.rooms[{idx}]"
        room = _obj(item, where)
        _exact_keys(
            room,
            {"room_id", "turn_id", "status", "reasons", "checks"},
            where,
        )
        room_id = _machine(room["room_id"], f"{where}.room_id")
        turn_id = _machine(room["turn_id"], f"{where}.turn_id")
        if room_id in seen_rooms or turn_id in seen_turns:
            raise ContractError("report room/turn identifiers must be unique")
        seen_rooms.add(room_id)
        seen_turns.add(turn_id)
        status = _text(room["status"], f"{where}.status", max_len=16)
        if status not in {"READY", "BLOCKED"}:
            raise ContractError(f"{where}.status invalid")
        reasons_raw = _arr(room["reasons"], f"{where}.reasons")
        reasons = [
            _text(reason, f"{where}.reasons[]", max_len=256)
            for reason in reasons_raw
        ]
        checks_raw = _arr(room["checks"], f"{where}.checks")
        checks = [
            _validate_check(check, f"{where}.checks[{check_idx}]")
            for check_idx, check in enumerate(checks_raw)
        ]
        if [check["kind"] for check in checks] != list(KINDS):
            raise ContractError(f"{where}.checks order/scope drift")
        derived_reasons = [
            reason for check in checks for reason in check["reasons"]
        ]
        derived_status = (
            "READY" if all(check["clear"] for check in checks) else "BLOCKED"
        )
        if reasons != derived_reasons or status != derived_status:
            raise ContractError(f"{where} status/reason derivation mismatch")
        normalized_rooms.append(
            {
                "room_id": room_id,
                "turn_id": turn_id,
                "status": status,
                "reasons": reasons,
                "checks": checks,
            }
        )
    if normalized_rooms != sorted(
        normalized_rooms, key=lambda room: room["room_id"]
    ):
        raise ContractError("report.rooms must be sorted by room_id")

    summary = _obj(report["summary"], "report.summary")
    _exact_keys(summary, {"ready", "blocked", "total"}, "report.summary")
    ready = _int(summary["ready"], "report.summary.ready", 0, len(normalized_rooms))
    blocked = _int(
        summary["blocked"], "report.summary.blocked", 0, len(normalized_rooms)
    )
    total = _int(summary["total"], "report.summary.total", 1, len(normalized_rooms))
    if (
        total != len(normalized_rooms)
        or ready != sum(room["status"] == "READY" for room in normalized_rooms)
        or blocked != total - ready
    ):
        raise ContractError("report.summary mismatch")

    embedded = _hex64(report["report_sha256"], "report.report_sha256")
    core = dict(report)
    del core["report_sha256"]
    if not hmac.compare_digest(embedded, sha256_bytes(canon(core))):
        raise ContractError("report embedded hash mismatch")
    actual_receipt = report_receipt(report)
    if not hmac.compare_digest(actual_receipt, expected_report_sha256):
        raise ContractError("report retained receipt mismatch")
    return report


def replay_current(
    historical_report_raw: Any,
    evidence_raw: Any,
    *,
    expected_report_sha256: str,
    now: dt.datetime,
    retained_policy_raw: Any | None = None,
) -> dict[str, Any]:
    """Authenticate history, bind the same evidence, then recompute current readiness."""
    if retained_policy_raw is None:
        retained_policy_raw, retained_policy = load_retained_policy()
    else:
        retained_policy = parse_policy(
            retained_policy_raw, RETAINED_POLICY_SHA256
        )
    history = verify_report_history(
        historical_report_raw,
        expected_policy_sha256=RETAINED_POLICY_SHA256,
        expected_report_sha256=expected_report_sha256,
    )
    _events, _normalized, evidence_sha256 = parse_evidence(
        evidence_raw, retained_policy
    )
    if not hmac.compare_digest(
        evidence_sha256, history["evidence_sha256"]
    ):
        raise ContractError("current evidence does not match historical evidence binding")
    expected_scope = [
        (room["room_id"], room["turn_id"]) for room in retained_policy["rooms"]
    ]
    historical_scope = [
        (room["room_id"], room["turn_id"]) for room in history["rooms"]
    ]
    if history["property_id"] != retained_policy["property_id"]:
        raise ContractError("historical report property differs from retained policy")
    if historical_scope != expected_scope:
        raise ContractError("historical report room/turn scope differs from retained policy")
    return compile_report(
        retained_policy_raw,
        evidence_raw,
        expected_policy_sha256=RETAINED_POLICY_SHA256,
        now=now,
    )


def render_current_markdown(
    current_report: Mapping[str, Any], *, historical_report_sha256: str
) -> bytes:
    historical_report_sha256 = _hex64(
        historical_report_sha256, "historical_report_sha256"
    )
    lines = [
        "# Hotel Room-Turn Current Readiness",
        "",
        f"- Current evaluation time: `{current_report['generated_at']}`",
        f"- Retained policy: `{current_report['policy_sha256']}`",
        f"- Bound evidence: `{current_report['evidence_sha256']}`",
        f"- Authenticated historical receipt: `{historical_report_sha256}`",
        f"- Current READY: **{current_report['summary']['ready']}**",
        f"- Current BLOCKED: **{current_report['summary']['blocked']}**",
        "",
        "| Room | Turn | Current status | Reasons |",
        "|---|---|---|---|",
    ]
    for room in current_report["rooms"]:
        reasons = ", ".join(room["reasons"]) if room["reasons"] else "—"
        lines.append(
            f"| {room['room_id']} | {room['turn_id']} | {room['status']} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "> This is a current replay, not a perpetual certificate. "
            "Re-run verify/render before operational use; evidence freshness ages continuously.",
            "",
            "No PMS write, guest-data access, staff dispatch, guest charge, "
            "payment, or revenue-recognition authority is granted.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")
