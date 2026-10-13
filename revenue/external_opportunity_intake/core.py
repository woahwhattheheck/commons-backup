from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

READY = "READY_FOR_INTERNAL_ROUTING"
STATES = (
    READY,
    "HOLD_DUPLICATE_CUSTODY",
    "HOLD_ALREADY_ACTIONED",
    "HOLD_DNR_OR_RELATIONSHIP",
    "HOLD_EXPIRED",
    "HOLD_STALE_SOURCE",
    "HOLD_FUTURE_EVIDENCE",
    "HOLD_NO_ACCEPTANCE_ROUTE",
    "HOLD_COMPENSATION_UNKNOWN",
    "HOLD_EVIDENCE_CONFLICT",
    "HOLD_INCOMPLETE_EVIDENCE",
)
ACTION_KINDS = {
    "MUSE_ELECTED", "APPLICATION_SENT", "OFFER_SENT", "DECLINED", "EXTERNAL_CLOSED",
    "EXTERNAL_WITHDRAWN", "EXTERNAL_CANCELLED"
}
DNR_KINDS = {"DNR", "RELATIONSHIP_BLOCK"}
COMPENSATION_KINDS = {"FIXED", "NON_FIXED", "UNKNOWN"}
AUTHORITY = {
    "external_send": False,
    "muse_election_or_consume": False,
    "application_or_offer_acceptance": False,
    "competition_entry_or_submission": False,
    "legal_or_contract_commitment": False,
    "provider_or_account_mutation": False,
    "purchase_fee_or_spend": False,
    "payment_or_funds_movement": False,
    "receivable_cash_or_revenue_recognition": False,
}
_SAFE_INT = 2**53 - 1
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3,12}$")


class IntakeError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise IntakeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_float(_: str) -> Any:
    raise IntakeError("floats are not allowed")


def _reject_constant(value: str) -> Any:
    raise IntakeError(f"nonfinite number is not allowed: {value}")


def parse_strict_json(raw: str | bytes) -> Any:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "strict")
        value = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise IntakeError(f"invalid JSON: {exc}") from exc
    try:
        _walk_scalar_safety(value, "$")
    except RecursionError as exc:
        raise IntakeError("JSON nesting is too deep") from exc
    return value


def _walk_scalar_safety(value: Any, where: str) -> None:
    if value is None:
        return
    if type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > _SAFE_INT:
            raise IntakeError(f"{where}: integer outside safe range")
        return
    if type(value) is str:
        _text(value, where, maximum=100_000, allow_empty=True)
        return
    if type(value) is list:
        if len(value) > 500:
            raise IntakeError(f"{where}: array too large")
        for idx, item in enumerate(value):
            _walk_scalar_safety(item, f"{where}[{idx}]")
        return
    if type(value) is dict:
        if len(value) > 500:
            raise IntakeError(f"{where}: object too large")
        for key, item in value.items():
            _text(key, f"{where}.<key>", maximum=200, allow_empty=False)
            _walk_scalar_safety(item, f"{where}.{key}")
        return
    raise IntakeError(f"{where}: unsupported JSON type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact(value: Any, fields: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise IntakeError(f"{where}: object required")
    keys = set(value)
    if keys != fields:
        missing = sorted(fields - keys)
        extra = sorted(keys - fields)
        raise IntakeError(f"{where}: exact fields required; missing={missing} extra={extra}")
    return value


def _text(value: Any, where: str, maximum: int = 1000, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise IntakeError(f"{where}: string required")
    if len(value) > maximum:
        raise IntakeError(f"{where}: too long")
    if not allow_empty and not value:
        raise IntakeError(f"{where}: non-empty string required")
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise IntakeError(f"{where}: lone surrogate forbidden")
        if code < 0x20 and ch not in "\t\n\r":
            raise IntakeError(f"{where}: control character forbidden")
    return value


def _identifier(value: Any, where: str) -> str:
    value = _text(value, where, maximum=200)
    if not _ID_RE.fullmatch(value):
        raise IntakeError(f"{where}: unsafe identifier")
    return value


def _sha(value: Any, where: str) -> str:
    value = _text(value, where, maximum=64)
    if not _SHA_RE.fullmatch(value):
        raise IntakeError(f"{where}: sha256 hex required")
    return value


def _int(value: Any, where: str, minimum: int = 0, maximum: int = _SAFE_INT) -> int:
    if type(value) is not int:
        raise IntakeError(f"{where}: integer required (bool is not an integer)")
    if not minimum <= value <= maximum:
        raise IntakeError(f"{where}: integer out of range")
    return value


def _utc(value: Any, where: str) -> tuple[str, datetime]:
    value = _text(value, where, maximum=40)
    if not value.endswith("Z"):
        raise IntakeError(f"{where}: UTC Z timestamp required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise IntakeError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise IntakeError(f"{where}: UTC required")
    normalized = parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return normalized, parsed


def _opt_utc(value: Any, where: str) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    return _utc(value, where)


def _enum(value: Any, allowed: set[str], where: str) -> str:
    value = _text(value, where, maximum=80)
    if value not in allowed:
        raise IntakeError(f"{where}: unsupported value {value!r}")
    return value


def _source(row: Any, root_id: str, idx: int) -> tuple[dict[str, Any], datetime, datetime | None]:
    where = f"sources[{idx}]"
    row = _exact(row, {
        "opportunity_id", "provider_class", "source_ref", "source_sha256", "generation",
        "observed_at", "published_at", "supersedes_generation", "deadline_at", "deadline_externally_stated"
    }, where)
    if _identifier(row["opportunity_id"], f"{where}.opportunity_id") != root_id:
        raise IntakeError(f"{where}: cross-opportunity transplant")
    observed_s, observed = _utc(row["observed_at"], f"{where}.observed_at")
    published_s, published = _utc(row["published_at"], f"{where}.published_at")
    deadline_s, deadline = _opt_utc(row["deadline_at"], f"{where}.deadline_at")
    supersedes = None if row["supersedes_generation"] is None else _identifier(row["supersedes_generation"], f"{where}.supersedes_generation")
    if type(row["deadline_externally_stated"]) is not bool:
        raise IntakeError(f"{where}.deadline_externally_stated: bool required")
    if published > observed:
        raise IntakeError(f"{where}: publication after observation")
    if deadline is not None and deadline < published and not row["deadline_externally_stated"]:
        raise IntakeError(f"{where}: deadline before publication without external statement")
    normalized = {
        "opportunity_id": root_id,
        "provider_class": _identifier(row["provider_class"], f"{where}.provider_class"),
        "source_ref": _text(row["source_ref"], f"{where}.source_ref", 1000),
        "source_sha256": _sha(row["source_sha256"], f"{where}.source_sha256"),
        "generation": _identifier(row["generation"], f"{where}.generation"),
        "observed_at": observed_s,
        "published_at": published_s,
        "supersedes_generation": supersedes,
        "deadline_at": deadline_s,
        "deadline_externally_stated": row["deadline_externally_stated"],
    }
    return normalized, observed, deadline


def _compensation(row: Any, root_id: str, idx: int) -> dict[str, Any]:
    where = f"compensation[{idx}]"
    row = _exact(row, {"opportunity_id", "source_generation", "kind", "currency", "amount_minor", "terms", "source_ref", "source_sha256"}, where)
    if _identifier(row["opportunity_id"], f"{where}.opportunity_id") != root_id:
        raise IntakeError(f"{where}: cross-opportunity transplant")
    kind = _enum(row["kind"], COMPENSATION_KINDS, f"{where}.kind")
    currency = row["currency"]
    amount = row["amount_minor"]
    terms = row["terms"]
    if kind == "FIXED":
        currency = _text(currency, f"{where}.currency", 12)
        if not _CURRENCY_RE.fullmatch(currency):
            raise IntakeError(f"{where}.currency: uppercase currency code required")
        amount = _int(amount, f"{where}.amount_minor", 0)
        if terms is not None:
            terms = _text(terms, f"{where}.terms", 2000)
    elif kind == "NON_FIXED":
        if currency is not None or amount is not None:
            raise IntakeError(f"{where}: NON_FIXED must not claim fixed currency/amount")
        terms = _text(terms, f"{where}.terms", 2000)
    else:
        if currency is not None or amount is not None or terms is not None:
            raise IntakeError(f"{where}: UNKNOWN must not carry inferred compensation")
    return {
        "opportunity_id": root_id,
        "source_generation": _identifier(row["source_generation"], f"{where}.source_generation"),
        "kind": kind,
        "currency": currency,
        "amount_minor": amount,
        "terms": terms,
        "source_ref": _text(row["source_ref"], f"{where}.source_ref", 1000),
        "source_sha256": _sha(row["source_sha256"], f"{where}.source_sha256"),
    }


def _normalize(document: Any) -> tuple[dict[str, Any], dict[str, datetime], list[datetime]]:
    top = _exact(document, {
        "opportunity_id", "opportunity_class", "active_source_generation", "title", "counterparty", "scope",
        "opportunity_url", "sources", "compensation", "acceptance_route", "policy", "custody", "actions", "blockers"
    }, "document")
    oid = _identifier(top["opportunity_id"], "opportunity_id")
    sources_raw = top["sources"]
    if type(sources_raw) is not list or not 1 <= len(sources_raw) <= 32:
        raise IntakeError("sources: array length 1..32 required")
    sources: list[dict[str, Any]] = []
    source_times: dict[str, datetime] = {}
    deadlines: list[datetime] = []
    for i, raw in enumerate(sources_raw):
        normalized, observed, deadline = _source(raw, oid, i)
        gen = normalized["generation"]
        if gen in source_times:
            raise IntakeError("sources: duplicate generation")
        source_times[gen] = observed
        sources.append(normalized)
        if deadline is not None:
            deadlines.append(deadline)
    active_generation = _identifier(top["active_source_generation"], "active_source_generation")
    if active_generation not in source_times:
        raise IntakeError("active_source_generation: not present in sources")

    comp_raw = top["compensation"]
    if type(comp_raw) is not list or not 1 <= len(comp_raw) <= 16:
        raise IntakeError("compensation: array length 1..16 required")
    compensation = [_compensation(row, oid, i) for i, row in enumerate(comp_raw)]
    for i, row in enumerate(compensation):
        if row["source_generation"] not in source_times:
            raise IntakeError(f"compensation[{i}].source_generation: unknown generation")

    acceptance_raw = top["acceptance_route"]
    acceptance = None
    acceptance_time = None
    if acceptance_raw is not None:
        row = _exact(acceptance_raw, {"opportunity_id", "source_generation", "route", "source_ref", "source_sha256", "observed_at"}, "acceptance_route")
        if _identifier(row["opportunity_id"], "acceptance_route.opportunity_id") != oid:
            raise IntakeError("acceptance_route: cross-opportunity transplant")
        observed_s, acceptance_time = _utc(row["observed_at"], "acceptance_route.observed_at")
        generation = _identifier(row["source_generation"], "acceptance_route.source_generation")
        if generation not in source_times:
            raise IntakeError("acceptance_route.source_generation: unknown generation")
        if acceptance_time < source_times[generation]:
            raise IntakeError("acceptance_route: observation before source generation")
        acceptance = {
            "opportunity_id": oid,
            "source_generation": generation,
            "route": _text(row["route"], "acceptance_route.route", 1000),
            "source_ref": _text(row["source_ref"], "acceptance_route.source_ref", 1000),
            "source_sha256": _sha(row["source_sha256"], "acceptance_route.source_sha256"),
            "observed_at": observed_s,
        }

    policy_raw = _exact(top["policy"], {"max_source_age_seconds", "permitted_classes", "candidate_holder_id"}, "policy")
    permitted = policy_raw["permitted_classes"]
    if type(permitted) is not list or not 1 <= len(permitted) <= 64:
        raise IntakeError("policy.permitted_classes: non-empty bounded array required")
    policy = {
        "max_source_age_seconds": _int(policy_raw["max_source_age_seconds"], "policy.max_source_age_seconds", 1, 31_536_000),
        "permitted_classes": sorted({_identifier(v, "policy.permitted_classes[]") for v in permitted}),
        "candidate_holder_id": _identifier(policy_raw["candidate_holder_id"], "policy.candidate_holder_id"),
    }

    custody_raw = top["custody"]
    if type(custody_raw) is not list or len(custody_raw) > 200:
        raise IntakeError("custody: bounded array required")
    custody: list[dict[str, Any]] = []
    custody_ids: set[str] = set()
    evidence_times: list[datetime] = list(source_times.values())
    for i, raw in enumerate(custody_raw):
        where = f"custody[{i}]"
        row = _exact(raw, {"opportunity_id", "claim_id", "holder_id", "source_generation", "claimed_at", "released_at"}, where)
        if _identifier(row["opportunity_id"], f"{where}.opportunity_id") != oid:
            raise IntakeError(f"{where}: cross-opportunity transplant")
        claim_id = _identifier(row["claim_id"], f"{where}.claim_id")
        if claim_id in custody_ids:
            raise IntakeError("custody: duplicate claim_id")
        custody_ids.add(claim_id)
        source_generation = _identifier(row["source_generation"], f"{where}.source_generation")
        if source_generation not in source_times:
            raise IntakeError(f"{where}.source_generation: unknown generation")
        claimed_s, claimed = _utc(row["claimed_at"], f"{where}.claimed_at")
        released_s, released = _opt_utc(row["released_at"], f"{where}.released_at")
        if claimed < source_times[source_generation]:
            raise IntakeError(f"{where}: claim before source observation")
        if released is not None and released < claimed:
            raise IntakeError(f"{where}: release before claim")
        evidence_times.append(claimed)
        if released is not None:
            evidence_times.append(released)
        custody.append({
            "opportunity_id": oid,
            "claim_id": claim_id,
            "holder_id": _identifier(row["holder_id"], f"{where}.holder_id"),
            "source_generation": source_generation,
            "claimed_at": claimed_s,
            "released_at": released_s,
        })
    custody.sort(key=lambda r: (r["claimed_at"], r["claim_id"]))

    actions_raw = top["actions"]
    if type(actions_raw) is not list or len(actions_raw) > 200:
        raise IntakeError("actions: bounded array required")
    actions: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    semantic_actions: set[tuple[str, str, str, str, str]] = set()
    for i, raw in enumerate(actions_raw):
        where = f"actions[{i}]"
        row = _exact(raw, {"opportunity_id", "action_id", "kind", "source_generation", "provider_ref", "occurred_at"}, where)
        if _identifier(row["opportunity_id"], f"{where}.opportunity_id") != oid:
            raise IntakeError(f"{where}: cross-opportunity transplant")
        action_id = _identifier(row["action_id"], f"{where}.action_id")
        if action_id in action_ids:
            raise IntakeError("actions: duplicate action_id")
        action_ids.add(action_id)
        generation = _identifier(row["source_generation"], f"{where}.source_generation")
        if generation not in source_times:
            raise IntakeError(f"{where}.source_generation: unknown generation")
        occurred_s, occurred = _utc(row["occurred_at"], f"{where}.occurred_at")
        if occurred < source_times[generation]:
            raise IntakeError(f"{where}: action before opportunity observation")
        provider_ref = _text(row["provider_ref"], f"{where}.provider_ref", 1000)
        kind = _enum(row["kind"], ACTION_KINDS, f"{where}.kind")
        semantic = (kind, generation, provider_ref, occurred_s, oid)
        if semantic in semantic_actions:
            raise IntakeError("actions: duplicate semantic action under reminted id")
        semantic_actions.add(semantic)
        evidence_times.append(occurred)
        actions.append({
            "opportunity_id": oid,
            "action_id": action_id,
            "kind": kind,
            "source_generation": generation,
            "provider_ref": provider_ref,
            "occurred_at": occurred_s,
        })
    actions.sort(key=lambda r: (r["occurred_at"], r["action_id"]))

    blockers_raw = top["blockers"]
    if type(blockers_raw) is not list or len(blockers_raw) > 100:
        raise IntakeError("blockers: bounded array required")
    blockers: list[dict[str, Any]] = []
    blocker_ids: set[str] = set()
    for i, raw in enumerate(blockers_raw):
        where = f"blockers[{i}]"
        row = _exact(raw, {"opportunity_id", "blocker_id", "kind", "source_ref", "source_sha256", "observed_at"}, where)
        if _identifier(row["opportunity_id"], f"{where}.opportunity_id") != oid:
            raise IntakeError(f"{where}: cross-opportunity transplant")
        blocker_id = _identifier(row["blocker_id"], f"{where}.blocker_id")
        if blocker_id in blocker_ids:
            raise IntakeError("blockers: duplicate blocker_id")
        blocker_ids.add(blocker_id)
        observed_s, observed = _utc(row["observed_at"], f"{where}.observed_at")
        evidence_times.append(observed)
        blockers.append({
            "opportunity_id": oid,
            "blocker_id": blocker_id,
            "kind": _enum(row["kind"], DNR_KINDS, f"{where}.kind"),
            "source_ref": _text(row["source_ref"], f"{where}.source_ref", 1000),
            "source_sha256": _sha(row["source_sha256"], f"{where}.source_sha256"),
            "observed_at": observed_s,
        })
    blockers.sort(key=lambda r: (r["observed_at"], r["blocker_id"]))

    if acceptance_time is not None:
        evidence_times.append(acceptance_time)

    normalized = {
        "opportunity_id": oid,
        "opportunity_class": _identifier(top["opportunity_class"], "opportunity_class"),
        "active_source_generation": active_generation,
        "title": _text(top["title"], "title", 500),
        "counterparty": _text(top["counterparty"], "counterparty", 300),
        "scope": _text(top["scope"], "scope", 5000),
        "opportunity_url": _text(top["opportunity_url"], "opportunity_url", 1000),
        "sources": sorted(sources, key=lambda r: (r["observed_at"], r["generation"])),
        "compensation": sorted(compensation, key=lambda r: canonical_bytes(r)),
        "acceptance_route": acceptance,
        "policy": policy,
        "custody": custody,
        "actions": actions,
        "blockers": blockers,
    }
    return normalized, source_times, evidence_times


def _state(normalized: dict[str, Any], source_times: dict[str, datetime], evidence_times: list[datetime], now: datetime, historical: bool) -> tuple[str, list[str]]:
    blockers: list[str] = []
    active_gen = normalized["active_source_generation"]
    active = next(row for row in normalized["sources"] if row["generation"] == active_gen)
    active_observed = source_times[active_gen]

    # Future evidence is a stronger currentness failure than ordinary incompleteness.
    if any(ts > now for ts in evidence_times):
        return "HOLD_FUTURE_EVIDENCE", ["future_evidence"]

    if normalized["opportunity_class"] not in normalized["policy"]["permitted_classes"]:
        return "HOLD_INCOMPLETE_EVIDENCE", ["opportunity_class_not_permitted"]

    sources = normalized["sources"]
    by_gen = {row["generation"]: row for row in sources}
    superseded: set[str] = set()
    provider_classes = {row["provider_class"] for row in sources}
    if len(provider_classes) != 1:
        return "HOLD_EVIDENCE_CONFLICT", ["provider_class_changed_across_generations"]
    for row in sources:
        generation = row["generation"]
        sup = row["supersedes_generation"]
        if sup is None:
            continue
        if sup == generation:
            return "HOLD_EVIDENCE_CONFLICT", ["generation_self_supersession"]
        if sup not in by_gen:
            return "HOLD_EVIDENCE_CONFLICT", ["supersedes_unknown_generation"]
        if source_times[sup] >= source_times[generation]:
            return "HOLD_EVIDENCE_CONFLICT", ["supersession_chronology_invalid"]
        superseded.add(sup)
    if len(sources) > 1:
        roots = [row for row in sources if row["supersedes_generation"] is None]
        if len(roots) != 1:
            return "HOLD_EVIDENCE_CONFLICT", ["ambiguous_source_lineage"]
        for row in sources:
            if row["generation"] != roots[0]["generation"] and row["supersedes_generation"] is None:
                return "HOLD_EVIDENCE_CONFLICT", ["changed_generation_without_supersession"]
    terminals = set(by_gen) - superseded
    if terminals != {active_gen}:
        return "HOLD_EVIDENCE_CONFLICT", ["active_generation_not_unique_terminal"]

    if normalized["blockers"]:
        return "HOLD_DNR_OR_RELATIONSHIP", ["dnr_or_relationship_block"]

    if any(a["kind"] in {"EXTERNAL_CLOSED", "EXTERNAL_WITHDRAWN", "EXTERNAL_CANCELLED"} for a in normalized["actions"]):
        return "HOLD_ALREADY_ACTIONED", ["external_closed_or_withdrawn"]
    if any(a["kind"] in {"MUSE_ELECTED", "APPLICATION_SENT", "OFFER_SENT", "DECLINED"} for a in normalized["actions"]):
        return "HOLD_ALREADY_ACTIONED", ["already_actioned"]

    active_other_claims = [c for c in normalized["custody"] if c["released_at"] is None and c["holder_id"] != normalized["policy"]["candidate_holder_id"]]
    if active_other_claims:
        return "HOLD_DUPLICATE_CUSTODY", ["active_other_custody"]

    acceptance = normalized["acceptance_route"]
    if acceptance is None:
        return "HOLD_NO_ACCEPTANCE_ROUTE", ["no_acceptance_route"]
    if acceptance["source_generation"] != active_gen:
        return "HOLD_INCOMPLETE_EVIDENCE", ["acceptance_route_not_bound_to_active_generation"]

    comp = [c for c in normalized["compensation"] if c["source_generation"] == active_gen]
    if not comp:
        return "HOLD_INCOMPLETE_EVIDENCE", ["compensation_not_bound_to_active_generation"]
    semantics = {(c["kind"], c["currency"], c["amount_minor"], c["terms"]) for c in comp}
    if len(semantics) > 1:
        return "HOLD_EVIDENCE_CONFLICT", ["compensation_conflict"]
    if comp[0]["kind"] == "UNKNOWN":
        return "HOLD_COMPENSATION_UNKNOWN", ["compensation_unknown"]

    if active["deadline_at"] is not None:
        _, deadline = _utc(active["deadline_at"], "active.deadline_at")
        assert deadline is not None
        if now > deadline:
            return "HOLD_EXPIRED", ["deadline_expired"]
    else:
        age = (now - active_observed).total_seconds()
        if age > normalized["policy"]["max_source_age_seconds"]:
            return "HOLD_STALE_SOURCE", ["source_stale"]

    if historical:
        return "HOLD_INCOMPLETE_EVIDENCE", ["historical_replay_non_current"]
    return READY, blockers


def compile_document(document: Any, *, clock: Callable[[], datetime] | None = None, historical_at: datetime | None = None) -> dict[str, Any]:
    normalized, source_times, evidence_times = _normalize(document)
    if historical_at is not None:
        if historical_at.tzinfo is None or historical_at.utcoffset() != timezone.utc.utcoffset(historical_at):
            raise IntakeError("historical_at: timezone-aware UTC required")
        now = historical_at.astimezone(timezone.utc)
        historical = True
    else:
        # Current compiler owns the clock and samples only after candidate authentication.
        clock_value = (clock or (lambda: datetime.now(timezone.utc)))()
        if clock_value.tzinfo is None:
            raise IntakeError("clock: timezone-aware time required")
        now = clock_value.astimezone(timezone.utc)
        historical = False
    state, blockers = _state(normalized, source_times, evidence_times, now, historical)
    record = {
        "schema": "commons.external_opportunity_intake.v1",
        "evaluation_mode": "HISTORICAL_REPLAY" if historical else "CURRENT",
        "evaluated_at": now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "state": state,
        "blockers": blockers,
        "opportunity": normalized,
        "authority": dict(AUTHORITY),
    }
    receipt = sha256_hex(canonical_bytes(record))
    return {**record, "receipt_sha256": receipt}


def verify_record(record: Any) -> None:
    if type(record) is not dict:
        raise IntakeError("record: object required")
    expected = set(record) - {"receipt_sha256"}
    required = {"schema", "evaluation_mode", "evaluated_at", "state", "blockers", "opportunity", "authority"}
    if expected != required or "receipt_sha256" not in record:
        raise IntakeError("record: exact fields required")
    if record["schema"] != "commons.external_opportunity_intake.v1":
        raise IntakeError("record: unsupported schema")
    if record["evaluation_mode"] not in {"CURRENT", "HISTORICAL_REPLAY"}:
        raise IntakeError("record: invalid evaluation_mode")
    if record["state"] not in STATES:
        raise IntakeError("record: invalid state")
    if record["authority"] != AUTHORITY:
        raise IntakeError("record: authority ceiling changed")
    supplied = _sha(record["receipt_sha256"], "receipt_sha256")
    body = {k: record[k] for k in required}
    actual = sha256_hex(canonical_bytes(body))
    if supplied != actual:
        raise IntakeError("record: receipt mismatch")

    normalized, source_times, evidence_times = _normalize(record["opportunity"])
    if normalized != record["opportunity"]:
        raise IntakeError("record: opportunity is not canonically normalized")
    evaluated_s, evaluated = _utc(record["evaluated_at"], "evaluated_at")
    if evaluated_s != record["evaluated_at"]:
        raise IntakeError("record: evaluated_at is not canonical")
    historical = record["evaluation_mode"] == "HISTORICAL_REPLAY"
    expected_state, expected_blockers = _state(normalized, source_times, evidence_times, evaluated, historical)
    if record["state"] != expected_state or record["blockers"] != expected_blockers:
        raise IntakeError("record: derived semantic state mismatch")


def render_markdown(record: dict[str, Any]) -> str:
    verify_record(record)
    opp = record["opportunity"]
    comp = next((c for c in opp["compensation"] if c["source_generation"] == opp["active_source_generation"]), None)
    if comp is None:
        comp_text = "NO ACTIVE-GENERATION COMPENSATION EVIDENCE"
    elif comp["kind"] == "FIXED":
        comp_text = f"{comp['amount_minor']} minor units {comp['currency']}"
    elif comp["kind"] == "NON_FIXED":
        comp_text = comp["terms"]
    else:
        comp_text = "UNKNOWN"
    blockers = ", ".join(record["blockers"]) if record["blockers"] else "none"
    return (
        f"# External opportunity intake\n\n"
        f"- ID: `{opp['opportunity_id']}`\n"
        f"- State: `{record['state']}`\n"
        f"- Evaluation: `{record['evaluation_mode']}` at `{record['evaluated_at']}`\n"
        f"- Title: {opp['title']}\n"
        f"- Counterparty: {opp['counterparty']}\n"
        f"- Compensation evidence: {comp_text}\n"
        f"- Blockers: {blockers}\n"
        f"- Receipt: `{record['receipt_sha256']}`\n\n"
        "`READY_FOR_INTERNAL_ROUTING` authorizes internal routing only. It does not authorize contacting, applying, accepting, entering, spending, moving funds, or recognizing revenue.\n"
    )


def write_bundle(document: Any, output_dir: str | os.PathLike[str], *, clock: Callable[[], datetime] | None = None, historical_at: datetime | None = None) -> dict[str, Any]:
    out = Path(output_dir)
    # Validate and render completely before reserving the final destination.
    record = compile_document(document, clock=clock, historical_at=historical_at)
    record_bytes = canonical_bytes(record) + b"\n"
    md = render_markdown(record).encode("utf-8")
    manifest = {
        "schema": "commons.external_opportunity_intake.bundle.v1",
        "record_sha256": sha256_hex(record_bytes),
        "routing_sha256": sha256_hex(md),
        "semantic_receipt_sha256": record["receipt_sha256"],
    }
    manifest_bytes = canonical_bytes(manifest) + b"\n"

    parent = out.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{out.name}.stage-", dir=parent))
    lock = parent / f".{out.name}.publish-lock"
    lock_fd: int | None = None
    try:
        (stage / "record.json").write_bytes(record_bytes)
        (stage / "routing.md").write_bytes(md)
        (stage / "manifest.json").write_bytes(manifest_bytes)
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise IntakeError("output publication is already in progress") from exc
        # Reserve the final destination atomically.  A check-then-rename is
        # insufficient here: POSIX rename may replace an empty directory created
        # by a non-cooperating writer between the existence check and rename.
        try:
            out.mkdir()
        except FileExistsError as exc:
            raise IntakeError("output directory already exists") from exc
        published = False
        try:
            for name in ("record.json", "routing.md", "manifest.json"):
                os.rename(stage / name, out / name)
            published = True
        finally:
            if not published:
                shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(stage)
        stage = Path()
        return record
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
        if stage and stage.exists() and stage != Path():
            shutil.rmtree(stage, ignore_errors=True)

