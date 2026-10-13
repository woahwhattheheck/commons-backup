#!/usr/bin/env python3
"""Paid Pilot -> Rollout Desk.

Offline, local-first commercial boundary engine for turning a completed bounded
pilot into an evidence-bound rollout candidate without silently converting
follow-on work into free scope.

This module intentionally does NOT contact buyers, accept contracts, charge
payments, or recognize revenue.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "paid-pilot-rollout/v1"
STATE_VERSION = "paid-pilot-rollout-state/v1"
EXPORT_VERSION = "paid-pilot-rollout-export/v1"
MAX_INPUT_BYTES = 2_000_000
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_UTC_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_DISPOSITIONS = {"MET", "HOLD", "NOT_MET"}
_PAYMENT_STATES = {"PAID_EXTERNAL_EVIDENCE", "CONTRACTED_NOT_PAID", "UNVERIFIED"}


class DeskError(ValueError):
    pass


def _dupe_guard(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DeskError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_dupe_guard)
    except DeskError:
        raise
    except Exception as exc:
        raise DeskError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_exact_keys(obj: dict[str, Any], required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    keys = set(obj)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise DeskError(f"missing keys: {sorted(missing)}")
    if extra:
        raise DeskError(f"unexpected keys: {sorted(extra)}")


def _require_obj(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeskError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DeskError(f"{label} must be an array")
    return value


def _require_str(value: Any, label: str, *, allow_empty: bool = False, max_len: int = 500) -> str:
    if not isinstance(value, str):
        raise DeskError(f"{label} must be a string")
    if not allow_empty and not value.strip():
        raise DeskError(f"{label} must not be empty")
    if len(value) > max_len:
        raise DeskError(f"{label} too long")
    return value


def _require_id(value: Any, label: str) -> str:
    value = _require_str(value, label, max_len=128)
    if not _ID_RE.fullmatch(value):
        raise DeskError(f"{label} must be an opaque identifier")
    return value


def _require_opaque_ref(value: Any, label: str) -> str:
    value = _require_id(value, label)
    if "http" in value.lower() or "@" in value:
        raise DeskError(f"{label} must be opaque, not a URL/email")
    return value


def _require_sha(value: Any, label: str) -> str:
    value = _require_str(value, label, max_len=64)
    if not _SHA_RE.fullmatch(value):
        raise DeskError(f"{label} must be lowercase sha256")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0, maximum: int = 10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeskError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise DeskError(f"{label} out of range")
    return value


def _timestamp_key(value: Any, label: str) -> datetime:
    value = _require_str(value, label, max_len=27)
    if not _UTC_TS_RE.fullmatch(value):
        raise DeskError(f"{label} must be strict UTC RFC3339 ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DeskError(f"{label} must be a real UTC timestamp") from exc


def _require_utc_timestamp(value: Any, label: str) -> str:
    _timestamp_key(value, label)
    return value


def _unique_ids(rows: list[dict[str, Any]], key: str, label: str) -> None:
    seen: set[str] = set()
    for row in rows:
        ident = row[key]
        if ident in seen:
            raise DeskError(f"duplicate {label}: {ident}")
        seen.add(ident)


def _validate_scope_row(value: Any, label: str) -> dict[str, Any]:
    obj = _require_obj(value, label)
    _require_exact_keys(obj, {"scope_id", "title"})
    return {
        "scope_id": _require_id(obj["scope_id"], f"{label}.scope_id"),
        "title": _require_str(obj["title"], f"{label}.title", max_len=240),
    }


def _validate_criterion(value: Any, label: str) -> dict[str, Any]:
    obj = _require_obj(value, label)
    _require_exact_keys(obj, {"criterion_id", "statement"})
    return {
        "criterion_id": _require_id(obj["criterion_id"], f"{label}.criterion_id"),
        "statement": _require_str(obj["statement"], f"{label}.statement", max_len=500),
    }


def _validate_commercial_gate(value: Any) -> dict[str, Any]:
    obj = _require_obj(value, "commercial_gate")
    _require_exact_keys(obj, {"pilot_payment_state", "evidence_ref", "evidence_sha256"})
    state = _require_str(obj["pilot_payment_state"], "commercial_gate.pilot_payment_state")
    if state not in _PAYMENT_STATES:
        raise DeskError("commercial_gate.pilot_payment_state invalid")
    return {
        "pilot_payment_state": state,
        "evidence_ref": _require_opaque_ref(obj["evidence_ref"], "commercial_gate.evidence_ref"),
        "evidence_sha256": _require_sha(obj["evidence_sha256"], "commercial_gate.evidence_sha256"),
    }


def _validate_phase2_template(value: Any) -> dict[str, Any]:
    obj = _require_obj(value, "phase2_template")
    _require_exact_keys(obj, {"title", "proposed_price_cents", "proposed_duration_days", "acceptance_criteria", "dependencies"})
    criteria = [
        _validate_criterion(row, f"phase2_template.acceptance_criteria[{i}]")
        for i, row in enumerate(_require_list(obj["acceptance_criteria"], "phase2_template.acceptance_criteria"))
    ]
    if not criteria:
        raise DeskError("phase2_template.acceptance_criteria must not be empty")
    _unique_ids(criteria, "criterion_id", "phase2 acceptance criterion")
    deps = [
        _require_str(dep, f"phase2_template.dependencies[{i}]", max_len=240)
        for i, dep in enumerate(_require_list(obj["dependencies"], "phase2_template.dependencies"))
    ]
    if len(set(deps)) != len(deps):
        raise DeskError("duplicate phase2 dependency")
    return {
        "title": _require_str(obj["title"], "phase2_template.title", max_len=240),
        "proposed_price_cents": _require_int(obj["proposed_price_cents"], "phase2_template.proposed_price_cents", minimum=0),
        "proposed_duration_days": _require_int(obj["proposed_duration_days"], "phase2_template.proposed_duration_days", minimum=1, maximum=3650),
        "acceptance_criteria": criteria,
        "dependencies": deps,
    }


def validate_pilot_spec(value: Any) -> dict[str, Any]:
    obj = _require_obj(value, "pilot_spec")
    _require_exact_keys(obj, {
        "schema_version", "pilot_id", "buyer_ref", "currency", "pilot_price_cents",
        "scope_version", "scope_sha256", "commercial_gate", "included_scope",
        "excluded_scope", "acceptance_criteria", "phase2_template",
    })
    if obj["schema_version"] != SCHEMA_VERSION:
        raise DeskError(f"schema_version must be {SCHEMA_VERSION}")
    currency = _require_str(obj["currency"], "currency", max_len=3)
    if not _CURRENCY_RE.fullmatch(currency):
        raise DeskError("currency must be ISO-like uppercase 3-letter code")
    included = [
        _validate_scope_row(row, f"included_scope[{i}]")
        for i, row in enumerate(_require_list(obj["included_scope"], "included_scope"))
    ]
    excluded = [
        _validate_scope_row(row, f"excluded_scope[{i}]")
        for i, row in enumerate(_require_list(obj["excluded_scope"], "excluded_scope"))
    ]
    if not included:
        raise DeskError("included_scope must not be empty")
    _unique_ids(included, "scope_id", "included scope")
    _unique_ids(excluded, "scope_id", "excluded scope")
    overlap = {r["scope_id"] for r in included} & {r["scope_id"] for r in excluded}
    if overlap:
        raise DeskError(f"scope ids cannot be both included and excluded: {sorted(overlap)}")
    criteria = [
        _validate_criterion(row, f"acceptance_criteria[{i}]")
        for i, row in enumerate(_require_list(obj["acceptance_criteria"], "acceptance_criteria"))
    ]
    if not criteria:
        raise DeskError("acceptance_criteria must not be empty")
    _unique_ids(criteria, "criterion_id", "pilot acceptance criterion")
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": _require_id(obj["pilot_id"], "pilot_id"),
        "buyer_ref": _require_opaque_ref(obj["buyer_ref"], "buyer_ref"),
        "currency": currency,
        "pilot_price_cents": _require_int(obj["pilot_price_cents"], "pilot_price_cents", minimum=0),
        "scope_version": _require_id(obj["scope_version"], "scope_version"),
        "scope_sha256": _require_sha(obj["scope_sha256"], "scope_sha256"),
        "commercial_gate": _validate_commercial_gate(obj["commercial_gate"]),
        "included_scope": included,
        "excluded_scope": excluded,
        "acceptance_criteria": criteria,
        "phase2_template": _validate_phase2_template(obj["phase2_template"]),
    }


def new_state(pilot_spec: Any) -> dict[str, Any]:
    spec = validate_pilot_spec(pilot_spec)
    return seal_state({
        "state_version": STATE_VERSION,
        "revision": 0,
        "pilot_spec": spec,
        "evidence_history": [],
        "followon_requests": [],
        "authority": {
            "buyer_contact_authorized": False,
            "buyer_acceptance_recorded": False,
            "contract_signed": False,
            "charge_authorized": False,
            "payment_mutation_authorized": False,
            "revenue_recognition_authorized": False,
        },
    })


def _state_without_seal(state: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in state.items() if k != "state_integrity_sha256"}


def seal_state(state: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(_state_without_seal(state))
    out["state_integrity_sha256"] = sha256_value(out)
    return out


def _validate_evidence_record(value: Any, valid_criteria: set[str]) -> dict[str, Any]:
    obj = _require_obj(value, "evidence")
    _require_exact_keys(obj, {"criterion_id", "disposition", "evidence_ref", "evidence_sha256", "recorded_at", "note"})
    criterion_id = _require_id(obj["criterion_id"], "evidence.criterion_id")
    if criterion_id not in valid_criteria:
        raise DeskError(f"unknown criterion_id: {criterion_id}")
    disposition = _require_str(obj["disposition"], "evidence.disposition")
    if disposition not in _DISPOSITIONS:
        raise DeskError("evidence.disposition invalid")
    return {
        "criterion_id": criterion_id,
        "disposition": disposition,
        "evidence_ref": _require_opaque_ref(obj["evidence_ref"], "evidence.evidence_ref"),
        "evidence_sha256": _require_sha(obj["evidence_sha256"], "evidence.evidence_sha256"),
        "recorded_at": _require_utc_timestamp(obj["recorded_at"], "evidence.recorded_at"),
        "note": _require_str(obj["note"], "evidence.note", allow_empty=True, max_len=500),
    }


def _validate_commercial_delta(value: Any) -> dict[str, Any]:
    obj = _require_obj(value, "commercial_delta")
    _require_exact_keys(obj, {"proposed_price_cents", "proposed_duration_days", "acceptance_criteria", "dependencies"})
    criteria = [
        _validate_criterion(row, f"commercial_delta.acceptance_criteria[{i}]")
        for i, row in enumerate(_require_list(obj["acceptance_criteria"], "commercial_delta.acceptance_criteria"))
    ]
    if not criteria:
        raise DeskError("commercial_delta.acceptance_criteria must not be empty")
    _unique_ids(criteria, "criterion_id", "commercial delta acceptance criterion")
    deps = [
        _require_str(dep, f"commercial_delta.dependencies[{i}]", max_len=240)
        for i, dep in enumerate(_require_list(obj["dependencies"], "commercial_delta.dependencies"))
    ]
    return {
        "proposed_price_cents": _require_int(obj["proposed_price_cents"], "commercial_delta.proposed_price_cents", minimum=0),
        "proposed_duration_days": _require_int(obj["proposed_duration_days"], "commercial_delta.proposed_duration_days", minimum=1, maximum=3650),
        "acceptance_criteria": criteria,
        "dependencies": deps,
    }


def _classify_scope(scope_refs: list[str], included: set[str], excluded: set[str]) -> str:
    if any(ref in excluded for ref in scope_refs):
        return "OUT_OF_SCOPE"
    if scope_refs and all(ref in included for ref in scope_refs):
        return "INCLUDED"
    return "CHANGE_ORDER_REQUIRED"


def _validate_stored_followon(value: Any, spec: dict[str, Any], seen_ids: set[str]) -> tuple[dict[str, Any], datetime]:
    obj = _require_obj(value, "followon_request")
    _require_exact_keys(obj, {"request_id", "title", "scope_refs", "requested_at", "classification", "commercial_delta"})
    request_id = _require_id(obj["request_id"], "followon_request.request_id")
    if request_id in seen_ids:
        raise DeskError(f"duplicate followon request_id: {request_id}")
    seen_ids.add(request_id)
    scope_refs = [
        _require_id(ref, f"followon_request.scope_refs[{i}]")
        for i, ref in enumerate(_require_list(obj["scope_refs"], "followon_request.scope_refs"))
    ]
    if not scope_refs:
        raise DeskError("followon_request.scope_refs must not be empty")
    if len(set(scope_refs)) != len(scope_refs):
        raise DeskError("duplicate followon scope ref")
    included = {r["scope_id"] for r in spec["included_scope"]}
    excluded = {r["scope_id"] for r in spec["excluded_scope"]}
    classification = _classify_scope(scope_refs, included, excluded)
    if obj["classification"] != classification:
        raise DeskError("stored followon classification does not match source scope")
    commercial_delta = None
    if obj["commercial_delta"] is not None:
        commercial_delta = _validate_commercial_delta(obj["commercial_delta"])
    if classification != "CHANGE_ORDER_REQUIRED" and commercial_delta is not None:
        raise DeskError("commercial_delta is allowed only for CHANGE_ORDER_REQUIRED requests")
    requested_at = _require_utc_timestamp(obj["requested_at"], "followon_request.requested_at")
    return ({
        "request_id": request_id,
        "title": _require_str(obj["title"], "followon_request.title", max_len=300),
        "scope_refs": scope_refs,
        "requested_at": requested_at,
        "classification": classification,
        "commercial_delta": commercial_delta,
    }, _timestamp_key(requested_at, "followon_request.requested_at"))


def validate_state(value: Any) -> dict[str, Any]:
    state = _require_obj(value, "state")
    _require_exact_keys(state, {
        "state_version", "revision", "pilot_spec", "evidence_history",
        "followon_requests", "authority", "state_integrity_sha256",
    })
    if state["state_version"] != STATE_VERSION:
        raise DeskError("state_version invalid")
    revision = _require_int(state["revision"], "revision", minimum=0)
    spec = validate_pilot_spec(state["pilot_spec"])
    authority = _require_obj(state["authority"], "authority")
    required_auth = {
        "buyer_contact_authorized", "buyer_acceptance_recorded", "contract_signed",
        "charge_authorized", "payment_mutation_authorized", "revenue_recognition_authorized",
    }
    _require_exact_keys(authority, required_auth)
    if any(v is not False for v in authority.values()):
        raise DeskError("authority ceiling violated: all authority flags must remain false")
    evidence_history = _require_list(state["evidence_history"], "evidence_history")
    followon_requests = _require_list(state["followon_requests"], "followon_requests")
    if revision != len(evidence_history) + len(followon_requests):
        raise DeskError("revision must equal accepted evidence plus follow-on event count")

    valid_criteria = {r["criterion_id"] for r in spec["acceptance_criteria"]}
    last_evidence_time: dict[str, datetime] = {}
    for index, stored in enumerate(evidence_history):
        row = _validate_evidence_record(stored, valid_criteria)
        if row != stored:
            raise DeskError(f"evidence_history[{index}] is not canonical")
        ts = _timestamp_key(row["recorded_at"], f"evidence_history[{index}].recorded_at")
        prior = last_evidence_time.get(row["criterion_id"])
        if prior is not None and ts <= prior:
            raise DeskError(f"evidence chronology must strictly increase per criterion: {row['criterion_id']}")
        last_evidence_time[row["criterion_id"]] = ts

    seen_ids: set[str] = set()
    last_followon_time: datetime | None = None
    for index, stored in enumerate(followon_requests):
        row, ts = _validate_stored_followon(stored, spec, seen_ids)
        if row != stored:
            raise DeskError(f"followon_requests[{index}] is not canonical")
        if last_followon_time is not None and ts <= last_followon_time:
            raise DeskError("follow-on request chronology must strictly increase")
        last_followon_time = ts

    expected = sha256_value(_state_without_seal(state))
    if _require_sha(state["state_integrity_sha256"], "state_integrity_sha256") != expected:
        raise DeskError("state integrity mismatch")
    return copy.deepcopy(state)


def record_evidence(state: Any, evidence: Any) -> dict[str, Any]:
    current = validate_state(state)
    valid = {r["criterion_id"] for r in current["pilot_spec"]["acceptance_criteria"]}
    row = _validate_evidence_record(evidence, valid)
    ts = _timestamp_key(row["recorded_at"], "evidence.recorded_at")
    for prior in reversed(current["evidence_history"]):
        if prior["criterion_id"] == row["criterion_id"]:
            prior_ts = _timestamp_key(prior["recorded_at"], "existing evidence.recorded_at")
            if ts <= prior_ts:
                raise DeskError(f"evidence chronology must strictly increase per criterion: {row['criterion_id']}")
            break
    current["evidence_history"].append(row)
    current["revision"] += 1
    return seal_state(current)


def add_followon_request(state: Any, request: Any) -> dict[str, Any]:
    current = validate_state(state)
    obj = _require_obj(request, "followon_request")
    _require_exact_keys(obj, {"request_id", "title", "scope_refs", "requested_at"}, {"commercial_delta"})
    request_id = _require_id(obj["request_id"], "followon_request.request_id")
    if any(r["request_id"] == request_id for r in current["followon_requests"]):
        raise DeskError(f"duplicate followon request_id: {request_id}")
    scope_refs = [
        _require_id(ref, f"followon_request.scope_refs[{i}]")
        for i, ref in enumerate(_require_list(obj["scope_refs"], "followon_request.scope_refs"))
    ]
    if not scope_refs:
        raise DeskError("followon_request.scope_refs must not be empty")
    if len(set(scope_refs)) != len(scope_refs):
        raise DeskError("duplicate followon scope ref")
    included = {r["scope_id"] for r in current["pilot_spec"]["included_scope"]}
    excluded = {r["scope_id"] for r in current["pilot_spec"]["excluded_scope"]}
    classification = _classify_scope(scope_refs, included, excluded)
    commercial_delta = None
    if "commercial_delta" in obj:
        commercial_delta = _validate_commercial_delta(obj["commercial_delta"])
    if classification != "CHANGE_ORDER_REQUIRED" and commercial_delta is not None:
        raise DeskError("commercial_delta is allowed only for CHANGE_ORDER_REQUIRED requests")
    requested_at = _require_utc_timestamp(obj["requested_at"], "followon_request.requested_at")
    ts = _timestamp_key(requested_at, "followon_request.requested_at")
    if current["followon_requests"]:
        prior_ts = _timestamp_key(current["followon_requests"][-1]["requested_at"], "existing followon requested_at")
        if ts <= prior_ts:
            raise DeskError("follow-on request chronology must strictly increase")
    current["followon_requests"].append({
        "request_id": request_id,
        "title": _require_str(obj["title"], "followon_request.title", max_len=300),
        "scope_refs": scope_refs,
        "requested_at": requested_at,
        "classification": classification,
        "commercial_delta": commercial_delta,
    })
    current["revision"] += 1
    return seal_state(current)


def _latest_evidence(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in state["evidence_history"]:
        latest[row["criterion_id"]] = row
    return latest


def compile_rollout(state: Any) -> dict[str, Any]:
    current = validate_state(state)
    spec = current["pilot_spec"]
    latest = _latest_evidence(current)
    criteria_projection = []
    missing: list[str] = []
    held: list[str] = []
    failed: list[str] = []
    for criterion in spec["acceptance_criteria"]:
        cid = criterion["criterion_id"]
        evidence = latest.get(cid)
        if evidence is None:
            disposition = "MISSING"
            missing.append(cid)
            evidence_projection = None
        else:
            disposition = evidence["disposition"]
            evidence_projection = {
                "evidence_ref": evidence["evidence_ref"],
                "evidence_sha256": evidence["evidence_sha256"],
                "recorded_at": evidence["recorded_at"],
                "note": evidence["note"],
            }
            if disposition == "HOLD":
                held.append(cid)
            elif disposition == "NOT_MET":
                failed.append(cid)
        criteria_projection.append({
            "criterion_id": cid,
            "statement": criterion["statement"],
            "disposition": disposition,
            "evidence": evidence_projection,
        })

    unresolved_changes = [
        r["request_id"] for r in current["followon_requests"]
        if r["classification"] == "CHANGE_ORDER_REQUIRED" and r["commercial_delta"] is None
    ]
    payment_state = spec["commercial_gate"]["pilot_payment_state"]
    if payment_state != "PAID_EXTERNAL_EVIDENCE":
        decision = "HOLD_FOR_PAYMENT_EVIDENCE"
    elif failed:
        decision = "NO_GO"
    elif missing or held:
        decision = "HOLD_FOR_PILOT_EVIDENCE"
    elif unresolved_changes:
        decision = "HOLD_FOR_COMMERCIAL_SCOPE"
    else:
        decision = "READY_FOR_OWNER_ROLLOUT_REVIEW"

    scope_projection = []
    for row in current["followon_requests"]:
        entry = copy.deepcopy(row)
        entry["free_extension_allowed"] = row["classification"] == "INCLUDED"
        entry["requires_separate_buyer_agreement"] = row["classification"] == "CHANGE_ORDER_REQUIRED"
        scope_projection.append(entry)

    rollout_candidate = {
        "title": spec["phase2_template"]["title"],
        "currency": spec["currency"],
        "proposed_price_cents": spec["phase2_template"]["proposed_price_cents"],
        "proposed_duration_days": spec["phase2_template"]["proposed_duration_days"],
        "acceptance_criteria": copy.deepcopy(spec["phase2_template"]["acceptance_criteria"]),
        "dependencies": copy.deepcopy(spec["phase2_template"]["dependencies"]),
        "included_followon_request_ids": [r["request_id"] for r in current["followon_requests"] if r["classification"] == "INCLUDED"],
        "change_order_candidates": [
            {"request_id": r["request_id"], "commercial_delta": copy.deepcopy(r["commercial_delta"])}
            for r in current["followon_requests"]
            if r["classification"] == "CHANGE_ORDER_REQUIRED" and r["commercial_delta"] is not None
        ],
        "excluded_request_ids": [r["request_id"] for r in current["followon_requests"] if r["classification"] == "OUT_OF_SCOPE"],
        "buyer_acceptance": False,
        "contract_signed": False,
        "charge_authorized": False,
        "payment_received": False,
        "revenue_recognized": False,
    }
    core = {
        "export_version": EXPORT_VERSION,
        "pilot_id": spec["pilot_id"],
        "buyer_ref": spec["buyer_ref"],
        "source_scope_version": spec["scope_version"],
        "source_scope_sha256": spec["scope_sha256"],
        "source_state_revision": current["revision"],
        "source_state_sha256": current["state_integrity_sha256"],
        "commercial_gate": {
            "pilot_payment_state": payment_state,
            "evidence_ref": spec["commercial_gate"]["evidence_ref"],
            "evidence_sha256": spec["commercial_gate"]["evidence_sha256"],
            "payment_verified_by_this_system": False,
        },
        "decision": decision,
        "pilot_criteria": criteria_projection,
        "followon_scope": scope_projection,
        "rollout_candidate": rollout_candidate,
        "authority_ceiling": copy.deepcopy(current["authority"]),
    }
    core["export_sha256"] = sha256_value(core)
    return core


def render_markdown(export: Any) -> str:
    out = _require_obj(export, "export")
    if out.get("export_version") != EXPORT_VERSION:
        raise DeskError("export_version invalid")
    lines = [
        "# Paid Pilot → Rollout Decision", "",
        f"- Pilot: `{out['pilot_id']}`",
        f"- Buyer ref: `{out['buyer_ref']}`",
        f"- Decision: **{out['decision']}**",
        f"- Source state revision: `{out['source_state_revision']}`",
        f"- Source state SHA-256: `{out['source_state_sha256']}`",
        f"- Export SHA-256: `{out['export_sha256']}`", "",
        "## Pilot acceptance evidence", "",
    ]
    for row in out["pilot_criteria"]:
        ev = row["evidence"]
        ref = "—" if ev is None else f"`{ev['evidence_ref']}`"
        lines.append(f"- **{row['criterion_id']}** — {row['disposition']} — {row['statement']} — evidence {ref}")
    lines += ["", "## Follow-on scope", ""]
    if not out["followon_scope"]:
        lines.append("- No follow-on requests recorded.")
    else:
        for row in out["followon_scope"]:
            lines.append(f"- **{row['request_id']}** — {row['classification']} — {row['title']}")
    candidate = out["rollout_candidate"]
    lines += [
        "", "## Phase-2 candidate", "",
        f"- Title: {candidate['title']}",
        f"- Proposed price: {candidate['currency']} {candidate['proposed_price_cents'] / 100:.2f}",
        f"- Proposed duration: {candidate['proposed_duration_days']} days",
        "- Buyer acceptance: false",
        "- Contract signed: false",
        "- Charge authorized: false",
        "- Payment received: false",
        "- Revenue recognized: false", "", "### Acceptance criteria", "",
    ]
    for row in candidate["acceptance_criteria"]:
        lines.append(f"- `{row['criterion_id']}` — {row['statement']}")
    lines += ["", "### Dependencies", ""]
    for dep in candidate["dependencies"]:
        lines.append(f"- {dep}")
    lines += [
        "", "## Commercial boundary", "",
        "This artifact is an owner-review candidate only. It does not contact the buyer, accept an agreement, authorize a charge, mutate a payment provider, or recognize revenue. Follow-on work outside the original included scope must stay excluded or carry separate commercial terms and separate buyer agreement.", "",
    ]
    return "\n".join(lines)


def _read_regular_json(path: Path) -> Any:
    try:
        st = path.lstat()
    except FileNotFoundError as exc:
        raise DeskError(f"missing file: {path}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise DeskError(f"input must be a regular non-symlink file: {path}")
    if st.st_size > MAX_INPUT_BYTES:
        raise DeskError(f"input too large: {path}")
    return loads_strict(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _write_exclusive(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise


def cmd_init(args: argparse.Namespace) -> None:
    spec = _read_regular_json(Path(args.pilot_spec))
    state = new_state(spec)
    path = Path(args.state)
    if path.exists() or path.is_symlink():
        raise DeskError("state output already exists")
    _write_exclusive(path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(f"initialized {path} revision=0 sha256={state['state_integrity_sha256']}")


def cmd_evidence(args: argparse.Namespace) -> None:
    path = Path(args.state)
    state = validate_state(_read_regular_json(path))
    state = record_evidence(state, _read_regular_json(Path(args.evidence)))
    _atomic_write_json(path, state)
    print(f"recorded evidence revision={state['revision']} sha256={state['state_integrity_sha256']}")


def cmd_followon(args: argparse.Namespace) -> None:
    path = Path(args.state)
    state = validate_state(_read_regular_json(path))
    state = add_followon_request(state, _read_regular_json(Path(args.request)))
    _atomic_write_json(path, state)
    row = state["followon_requests"][-1]
    print(f"recorded follow-on {row['request_id']} classification={row['classification']} revision={state['revision']}")


def cmd_compile(args: argparse.Namespace) -> None:
    state = validate_state(_read_regular_json(Path(args.state)))
    export = compile_rollout(state)
    json_path = Path(args.out_json)
    md_path = Path(args.out_md)
    if json_path.exists() or json_path.is_symlink() or md_path.exists() or md_path.is_symlink():
        raise DeskError("compile outputs are create-exclusive")
    _write_exclusive(json_path, json.dumps(export, indent=2, sort_keys=True) + "\n")
    try:
        _write_exclusive(md_path, render_markdown(export))
    except Exception:
        try:
            json_path.unlink()
        except FileNotFoundError:
            pass
        raise
    print(f"decision={export['decision']} export_sha256={export['export_sha256']}")


def cmd_verify(args: argparse.Namespace) -> None:
    state = validate_state(_read_regular_json(Path(args.state)))
    export = compile_rollout(state)
    print(f"valid revision={state['revision']} decision={export['decision']} state_sha256={state['state_integrity_sha256']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("--pilot-spec", required=True)
    p.add_argument("--state", required=True)
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("evidence")
    p.add_argument("--state", required=True)
    p.add_argument("--evidence", required=True)
    p.set_defaults(func=cmd_evidence)
    p = sub.add_parser("followon")
    p.add_argument("--state", required=True)
    p.add_argument("--request", required=True)
    p.set_defaults(func=cmd_followon)
    p = sub.add_parser("compile")
    p.add_argument("--state", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", required=True)
    p.set_defaults(func=cmd_compile)
    p = sub.add_parser("verify")
    p.add_argument("--state", required=True)
    p.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except DeskError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
