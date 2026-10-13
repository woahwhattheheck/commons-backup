#!/usr/bin/env python3
"""AquaTrace Work Order B — production-foundation runner.

Working program, not a mock SKU or docs-only matrix.

intake → roster lookup → deny-by-default RBAC → attributable audit →
sample / custody / QC transitions → device-contract check →
HOLD on violations → named-human release.

Synthetic only. No live LIMS. No production writes. No automatic
release. No City / customer data. No readiness or certification claim.
State remains NOT_READY. HOLD / BUILD-AND-VERIFY. cash_usd=0.

python3 aquatrace_work_order_b_production_foundation.py
python3 revenue/aquatrace_work_order_b_production_foundation/runner.py
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK = Path(__file__).resolve().parent
FIXTURE_PATH = PACK / "fixture.json"

DEMAND_ID = "aquatrace-work-order-b-production-foundation-20260831-01"
SCHEMA = "commons-aquatrace-work-order-b-production-foundation/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
PROGRAM_STATE = "NOT_READY"
COMMAND = "python3 aquatrace_work_order_b_production_foundation.py"

ROLE_CAPS: dict[str, frozenset[str]] = {
    "COLLECTOR": frozenset({"INTAKE", "CUSTODY_COLLECT", "CUSTODY_TRANSFER"}),
    "ANALYST": frozenset({"RECORD_RESULT", "PROPOSE_QC"}),
    "QA": frozenset({"APPROVE_QC", "HOLD_QC", "RECONCILE"}),
    "REPORTING_APPROVER": frozenset({"RELEASE_PACKET"}),
    "INTEGRATION": frozenset({"DEVICE_HANDSHAKE"}),
    "SUPPORT": frozenset({"SUPPORT_READ"}),
}

SYSTEM_ACTORS = frozenset({"SYSTEM", "AUTONOMOUS"})


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_ts(raw: str) -> datetime:
    stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def device_export_hash(device_id: str, model: str, software: str) -> str:
    return sha256_hex(
        {
            "device_id": device_id,
            "model": model,
            "software": software,
            "synthetic": True,
            "demand_id": DEMAND_ID,
        }
    )


def registered_devices(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for device_id, row in fixture["devices"].items():
        record = deepcopy(row)
        record["device_id"] = device_id
        record["export_hash"] = device_export_hash(device_id, row["model"], row["software"])
        out[device_id] = record
    return out


def empty_journal(fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "program_state": PROGRAM_STATE,
        "truth_gate": TRUTH_GATE,
        "epoch": spec["epoch"],
        "actors": deepcopy(spec["actors"]),
        "devices": registered_devices(spec),
        "samples": {},
        "audit": [],
        "effect_keys": [],
        "applied_effects": {},
        "production_writes": 0,
        "live_lims": False,
        "automatic_releases": 0,
        "readiness_claims": 0,
        "interface_live": False,
        "cash_usd": 0,
    }


def _effect_key(
    actor_id: str,
    action: str,
    sample_id: str | None,
    payload: dict[str, Any] | None,
    pre_state: dict[str, Any] | None,
) -> str:
    return sha256_hex(
        {
            "actor_id": actor_id,
            "action": action,
            "sample_id": sample_id,
            "payload": payload or {},
            "pre_state": pre_state,
        }
    )


def _audit(
    journal: dict[str, Any],
    *,
    actor_id: str,
    role: str | None,
    action: str,
    decision: str,
    code: str,
    sample_id: str | None,
    effect_key: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "seq": len(journal["audit"]) + 1,
        "actor_id": actor_id,
        "role": role,
        "action": action,
        "decision": decision,
        "code": code,
        "sample_id": sample_id,
        "effect_key": effect_key,
        "detail": deepcopy(detail or {}),
        "program_state": PROGRAM_STATE,
    }
    journal["audit"].append(event)
    return event


def identify(journal: dict[str, Any], actor_id: str, action: str) -> tuple[dict[str, Any] | None, str | None]:
    if actor_id in SYSTEM_ACTORS:
        if action == "RELEASE_PACKET":
            return None, "AUTONOMOUS_RELEASE_DENIED"
        if action == "RECORD_RESULT":
            return None, "NO_NAMED_HUMAN"
        return None, "UNKNOWN_ACTOR"
    actor = journal["actors"].get(actor_id)
    if actor is None:
        return None, "UNKNOWN_ACTOR"
    if not actor.get("enabled"):
        return None, "ACTOR_DISABLED"
    return actor, None


def _support_window_open(actor: dict[str, Any], now: datetime) -> bool:
    start = actor.get("window_start")
    end = actor.get("window_end")
    if not start or not end:
        return False
    return _parse_ts(start) <= now <= _parse_ts(end)


def authorize(
    actor: dict[str, Any],
    actor_id: str,
    action: str,
    now: datetime,
) -> str | None:
    role = actor["role"]
    if role == "SUPPORT":
        if not _support_window_open(actor, now):
            return "SUPPORT_WINDOW_CLOSED"
        if action == "ELEVATE":
            return "SUPPORT_NO_ELEVATE"
    caps = ROLE_CAPS.get(role, frozenset())
    if action in caps:
        return None
    if action == "ADMIN_USER" and role == "INTEGRATION":
        return "INTEGRATION_NO_ADMIN"
    if action == "ERASE_AUDIT" and role == "QA":
        return "QA_NO_ERASE_AUDIT"
    if action == "ELEVATE":
        return "SUPPORT_NO_ELEVATE" if role == "SUPPORT" else "RBAC_DENIED"
    if action == "RELEASE_PACKET" and actor_id in SYSTEM_ACTORS:
        return "AUTONOMOUS_RELEASE_DENIED"
    return "RBAC_DENIED"


def _refuse(
    journal: dict[str, Any],
    *,
    actor_id: str,
    role: str | None,
    action: str,
    code: str,
    sample_id: str | None,
    effect_key: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = _audit(
        journal,
        actor_id=actor_id,
        role=role,
        action=action,
        decision="REFUSED",
        code=code,
        sample_id=sample_id,
        effect_key=effect_key,
        detail=detail,
    )
    return {"ok": False, "code": code, "decision": "REFUSED", "event": event, "replay": False}


def _apply_effect(journal: dict[str, Any], effect_key: str, payload: dict[str, Any]) -> None:
    journal["effect_keys"].append(effect_key)
    journal["applied_effects"][effect_key] = payload


def act(
    journal: dict[str, Any],
    *,
    actor_id: str,
    action: str,
    sample_id: str | None = None,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
    act_id: str | None = None,
) -> dict[str, Any]:
    body = deepcopy(payload or {})
    stamp = now or _parse_ts(journal["epoch"])
    effect_key = act_id or _effect_key(actor_id, action, sample_id, body, None)
    if effect_key in journal["applied_effects"]:
        _audit(
            journal,
            actor_id=actor_id,
            role=journal["actors"].get(actor_id, {}).get("role"),
            action=action,
            decision="REPLAY_NOOP",
            code="REPLAY_NOOP",
            sample_id=sample_id,
            effect_key=effect_key,
        )
        return {
            "ok": True,
            "code": "REPLAY_NOOP",
            "decision": "REPLAY_NOOP",
            "replay": True,
            "effect_key": effect_key,
        }

    actor, ident_code = identify(journal, actor_id, action)
    if ident_code:
        result = _refuse(
            journal,
            actor_id=actor_id,
            role=None if actor_id in SYSTEM_ACTORS else (journal["actors"].get(actor_id) or {}).get("role"),
            action=action,
            code=ident_code,
            sample_id=sample_id,
            effect_key=effect_key,
        )
        _apply_effect(journal, effect_key, {"decision": "REFUSED", "code": ident_code})
        return result

    assert actor is not None
    if action in {"APPROVE_QC", "RELEASE_PACKET"} and sample_id:
        record = _sample(journal, sample_id)
        if record and record.get("qc_proposed_by") == actor_id:
            result = _refuse(
                journal,
                actor_id=actor_id,
                role=actor["role"],
                action=action,
                code="SELF_APPROVE",
                sample_id=sample_id,
                effect_key=effect_key,
            )
            _apply_effect(journal, effect_key, {"decision": "REFUSED", "code": "SELF_APPROVE"})
            return result
    auth_code = authorize(actor, actor_id, action, stamp)
    if auth_code:
        result = _refuse(
            journal,
            actor_id=actor_id,
            role=actor["role"],
            action=action,
            code=auth_code,
            sample_id=sample_id,
            effect_key=effect_key,
        )
        _apply_effect(journal, effect_key, {"decision": "REFUSED", "code": auth_code})
        return result

    outcome = _dispatch(journal, actor_id=actor_id, actor=actor, action=action, sample_id=sample_id, payload=body)
    if not outcome["ok"]:
        result = _refuse(
            journal,
            actor_id=actor_id,
            role=actor["role"],
            action=action,
            code=outcome["code"],
            sample_id=sample_id,
            effect_key=effect_key,
            detail=outcome.get("detail"),
        )
        _apply_effect(journal, effect_key, {"decision": "REFUSED", "code": outcome["code"]})
        return result

    event = _audit(
        journal,
        actor_id=actor_id,
        role=actor["role"],
        action=action,
        decision="ALLOWED",
        code=outcome["code"],
        sample_id=sample_id,
        effect_key=effect_key,
        detail=outcome.get("detail"),
    )
    _apply_effect(journal, effect_key, {"decision": "ALLOWED", "code": outcome["code"]})
    return {
        "ok": True,
        "code": outcome["code"],
        "decision": "ALLOWED",
        "event": event,
        "replay": False,
        "effect_key": effect_key,
    }


def _sample(journal: dict[str, Any], sample_id: str | None) -> dict[str, Any] | None:
    if not sample_id:
        return None
    return journal["samples"].get(sample_id)


def _require_sample(journal: dict[str, Any], sample_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not sample_id:
        return None, "UNKNOWN_SAMPLE"
    record = _sample(journal, sample_id)
    if record is None:
        return None, "UNKNOWN_SAMPLE"
    return record, None


def _dispatch(
    journal: dict[str, Any],
    *,
    actor_id: str,
    actor: dict[str, Any],
    action: str,
    sample_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if action == "SUPPORT_READ":
        return {"ok": True, "code": "SUPPORT_READ", "detail": {"elevated": False}}
    if action == "INTAKE":
        return _do_intake(journal, actor_id=actor_id, sample_id=sample_id, payload=payload)
    if action == "CUSTODY_COLLECT":
        return _do_collect(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "CUSTODY_TRANSFER":
        return _do_transfer(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "DEVICE_HANDSHAKE":
        return _do_handshake(journal, actor_id=actor_id, sample_id=sample_id, payload=payload)
    if action == "RECORD_RESULT":
        return _do_record_result(journal, actor_id=actor_id, sample_id=sample_id, payload=payload)
    if action == "PROPOSE_QC":
        return _do_propose_qc(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "APPROVE_QC":
        return _do_approve_qc(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "HOLD_QC":
        return _do_hold_qc(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "RECONCILE":
        return _do_reconcile(journal, actor_id=actor_id, sample_id=sample_id)
    if action == "RELEASE_PACKET":
        return _do_release(journal, actor_id=actor_id, actor=actor, sample_id=sample_id)
    return {"ok": False, "code": "RBAC_DENIED"}


def _do_intake(
    journal: dict[str, Any],
    *,
    actor_id: str,
    sample_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not sample_id:
        return {"ok": False, "code": "UNKNOWN_SAMPLE"}
    if sample_id in journal["samples"]:
        return {"ok": False, "code": "DUPLICATE_SAMPLE"}
    journal["samples"][sample_id] = {
        "sample_id": sample_id,
        "plan": payload.get("plan"),
        "device_id": payload.get("device_id"),
        "analyte": payload.get("analyte"),
        "method": payload.get("method"),
        "value": payload.get("value"),
        "spec_lo": payload.get("spec_lo"),
        "spec_hi": payload.get("spec_hi"),
        "state": "INTAKE",
        "custody": [{"actor_id": actor_id, "step": "INTAKE"}],
        "custody_complete": False,
        "device_known": False,
        "handshake": None,
        "result": None,
        "result_by": None,
        "qc_proposed_by": None,
        "qc_state": None,
        "qc_approved_by": None,
        "reconciled": False,
        "reconciled_by": None,
        "released": False,
        "released_by": None,
        "hold_code": None,
    }
    return {"ok": True, "code": "INTAKE", "detail": {"state": "INTAKE"}}


def _do_collect(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["state"] not in {"INTAKE"}:
        return {"ok": False, "code": "CUSTODY_STEP_INVALID"}
    record["custody"].append({"actor_id": actor_id, "step": "COLLECTED"})
    record["state"] = "COLLECTED"
    return {"ok": True, "code": "COLLECTED", "detail": {"state": "COLLECTED"}}


def _do_transfer(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["state"] != "COLLECTED":
        return {"ok": False, "code": "CUSTODY_STEP_INVALID"}
    record["custody"].append({"actor_id": actor_id, "step": "TRANSFERRED"})
    record["custody_complete"] = True
    record["state"] = "IN_LAB"
    return {"ok": True, "code": "IN_LAB", "detail": {"state": "IN_LAB", "custody_complete": True}}


def _do_handshake(
    journal: dict[str, Any],
    *,
    actor_id: str,
    sample_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if not record["custody_complete"]:
        record["hold_code"] = "HOLD_INCOMPLETE_CUSTODY"
        record["state"] = "HOLD"
        return {"ok": False, "code": "HOLD_INCOMPLETE_CUSTODY"}
    device_id = payload.get("device_id") or record["device_id"]
    known = journal["devices"].get(device_id)
    presented = {
        "device_id": device_id,
        "model": payload.get("model") or (known or {}).get("model"),
        "software": payload.get("software") or (known or {}).get("software"),
        "export_hash": payload.get("export_hash") or (known or {}).get("export_hash"),
        "actor_id": actor_id,
    }
    if known is None:
        record["handshake"] = {**presented, "known": False}
        record["device_known"] = False
        record["hold_code"] = "HOLD_UNKNOWN_DEVICE"
        record["state"] = "HOLD"
        return {
            "ok": True,
            "code": "HOLD_UNKNOWN_DEVICE",
            "detail": {"device_id": device_id, "known": False},
        }
    if (
        presented["model"] != known["model"]
        or presented["software"] != known["software"]
        or presented["export_hash"] != known["export_hash"]
    ):
        record["handshake"] = {**presented, "known": False, "mismatch": True}
        record["device_known"] = False
        record["hold_code"] = "HOLD_UNKNOWN_DEVICE"
        record["state"] = "HOLD"
        return {
            "ok": True,
            "code": "HOLD_UNKNOWN_DEVICE",
            "detail": {"device_id": device_id, "known": False, "mismatch": True},
        }
    record["handshake"] = {**presented, "known": True, "cites": known.get("cites")}
    record["device_known"] = True
    record["state"] = "DEVICE_OK"
    return {"ok": True, "code": "DEVICE_OK", "detail": {"device_id": device_id, "known": True}}


def _do_record_result(
    journal: dict[str, Any],
    *,
    actor_id: str,
    sample_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record.get("hold_code") == "HOLD_UNKNOWN_DEVICE" or not record["device_known"]:
        if record.get("hold_code") == "HOLD_UNKNOWN_DEVICE":
            return {"ok": False, "code": "HOLD_UNKNOWN_DEVICE"}
    if not record["custody_complete"]:
        record["hold_code"] = "HOLD_INCOMPLETE_CUSTODY"
        record["state"] = "HOLD"
        return {"ok": False, "code": "HOLD_INCOMPLETE_CUSTODY"}
    if not record["device_known"]:
        record["hold_code"] = "HOLD_UNKNOWN_DEVICE"
        record["state"] = "HOLD"
        return {"ok": False, "code": "HOLD_UNKNOWN_DEVICE"}
    value = payload.get("value", record["value"])
    spec_lo = record["spec_lo"]
    spec_hi = record["spec_hi"]
    in_spec = spec_lo <= value <= spec_hi
    record["result"] = {
        "value": value,
        "in_spec": in_spec,
        "analyte": record["analyte"],
        "method": record["method"],
    }
    record["result_by"] = actor_id
    record["state"] = "RESULTED"
    return {"ok": True, "code": "RESULTED", "detail": {"in_spec": in_spec, "result_by": actor_id}}


def _do_propose_qc(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["result"] is None or not record["result_by"]:
        return {"ok": False, "code": "NO_NAMED_HUMAN"}
    record["qc_proposed_by"] = actor_id
    record["qc_state"] = "PROPOSED"
    record["state"] = "QC_PROPOSED"
    return {"ok": True, "code": "QC_PROPOSED", "detail": {"proposed_by": actor_id}}


def _do_approve_qc(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["qc_state"] != "PROPOSED":
        return {"ok": False, "code": "QC_NOT_PROPOSED"}
    if record["qc_proposed_by"] == actor_id:
        return {"ok": False, "code": "SELF_APPROVE"}
    if record["result"] and not record["result"]["in_spec"]:
        return {"ok": False, "code": "QC_OUT_OF_SPEC"}
    record["qc_state"] = "APPROVED"
    record["qc_approved_by"] = actor_id
    record["state"] = "QC_APPROVED"
    return {"ok": True, "code": "QC_APPROVED", "detail": {"approved_by": actor_id}}


def _do_hold_qc(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["qc_state"] != "PROPOSED":
        return {"ok": False, "code": "QC_NOT_PROPOSED"}
    record["qc_state"] = "HELD"
    record["hold_code"] = "HOLD_QC"
    record["state"] = "HOLD"
    return {"ok": True, "code": "HOLD_QC", "detail": {"held_by": actor_id}}


def _do_reconcile(journal: dict[str, Any], *, actor_id: str, sample_id: str | None) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["qc_state"] != "APPROVED":
        return {"ok": False, "code": "QC_NOT_APPROVED"}
    record["reconciled"] = True
    record["reconciled_by"] = actor_id
    record["state"] = "RECONCILED"
    return {"ok": True, "code": "RECONCILED", "detail": {"reconciled_by": actor_id}}


def _do_release(
    journal: dict[str, Any],
    *,
    actor_id: str,
    actor: dict[str, Any],
    sample_id: str | None,
) -> dict[str, Any]:
    record, err = _require_sample(journal, sample_id)
    if err:
        return {"ok": False, "code": err}
    assert record is not None
    if record["released"]:
        return {"ok": False, "code": "ALREADY_RELEASED"}
    if record.get("hold_code") == "HOLD_QC" or record.get("qc_state") == "HELD":
        return {"ok": False, "code": "HOLD_QC"}
    if record.get("hold_code") == "HOLD_UNKNOWN_DEVICE":
        return {"ok": False, "code": "HOLD_UNKNOWN_DEVICE"}
    if not record["custody_complete"]:
        return {"ok": False, "code": "HOLD_INCOMPLETE_CUSTODY"}
    if record["result"] is None or not record["result_by"]:
        return {"ok": False, "code": "NO_NAMED_HUMAN"}
    if record["qc_state"] != "APPROVED":
        return {"ok": False, "code": "QC_NOT_APPROVED"}
    if not record["reconciled"]:
        return {"ok": False, "code": "NOT_RECONCILED"}
    if actor["role"] != "REPORTING_APPROVER":
        return {"ok": False, "code": "RBAC_DENIED"}
    if record["qc_proposed_by"] == actor_id:
        return {"ok": False, "code": "SELF_APPROVE"}
    record["released"] = True
    record["released_by"] = actor_id
    record["state"] = "RELEASED"
    return {"ok": True, "code": "RELEASED", "detail": {"released_by": actor_id}}


def _handshake_payload(journal: dict[str, Any], device_id: str) -> dict[str, Any]:
    known = journal["devices"].get(device_id)
    if known is None:
        return {"device_id": device_id, "model": None, "software": None, "export_hash": None}
    return {
        "device_id": device_id,
        "model": known["model"],
        "software": known["software"],
        "export_hash": known["export_hash"],
    }


def _intake_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan": plan["plan"],
        "device_id": plan["device_id"],
        "analyte": plan["analyte"],
        "method": plan["method"],
        "value": plan["value"],
        "spec_lo": plan["spec_lo"],
        "spec_hi": plan["spec_hi"],
    }


def process_sample(journal: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    sid = plan["sample_id"]
    kind = plan["plan"]

    def step(
        actor_id: str,
        action: str,
        payload: dict[str, Any] | None = None,
        act_id: str | None = None,
    ) -> dict[str, Any]:
        result = act(
            journal,
            actor_id=actor_id,
            action=action,
            sample_id=sid,
            payload=payload,
            act_id=act_id,
        )
        effects.append(result)
        return result

    step("collector-1", "INTAKE", _intake_payload(plan))
    if kind == "INCOMPLETE_CUSTODY":
        step("analyst-1", "RECORD_RESULT", {"value": plan["value"]})
        step("reporting-1", "RELEASE_PACKET")
        return effects

    step("collector-1", "CUSTODY_COLLECT")
    step("collector-2", "CUSTODY_TRANSFER")
    step("integration-1", "DEVICE_HANDSHAKE", _handshake_payload(journal, plan["device_id"]))

    if kind == "UNKNOWN_DEVICE":
        step("analyst-1", "RECORD_RESULT", {"value": plan["value"]})
        step("reporting-1", "RELEASE_PACKET")
        return effects

    if kind == "NO_NAMED_HUMAN":
        step("SYSTEM", "RECORD_RESULT", {"value": plan["value"]})
        step("reporting-1", "RELEASE_PACKET")
        return effects

    step("analyst-1", "RECORD_RESULT", {"value": plan["value"]})
    step("analyst-1", "PROPOSE_QC")

    if kind == "QC_FAIL":
        step("qa-1", "HOLD_QC")
        step("reporting-1", "RELEASE_PACKET")
        return effects

    if kind == "CLEAN":
        if sid == "SYN-ATB-S01":
            step("analyst-1", "APPROVE_QC")
            step("collector-1", "RELEASE_PACKET")
        step("qa-1", "APPROVE_QC")
        step("qa-2", "RECONCILE")
        step("reporting-1", "RELEASE_PACKET")
        return effects

    if kind == "CLEAN_UNRECONCILED_PROBE":
        step("qa-1", "APPROVE_QC")
        step("reporting-1", "RELEASE_PACKET", act_id="%s:release-unreconciled" % sid)
        step("qa-2", "RECONCILE")
        step("reporting-1", "RELEASE_PACKET", act_id="%s:release-final" % sid)
        return effects

    raise RuntimeError("unknown sample plan: %s" % kind)


def run_probes(journal: dict[str, Any]) -> list[dict[str, Any]]:
    probes = [
        act(journal, actor_id="unknown-actor", action="INTAKE", sample_id="SYN-ATB-S01", payload={"probe": True}),
        act(journal, actor_id="disabled-analyst-1", action="RECORD_RESULT", sample_id="SYN-ATB-S01"),
        act(journal, actor_id="support-expired-1", action="SUPPORT_READ"),
        act(journal, actor_id="support-1", action="ELEVATE"),
        act(journal, actor_id="integration-1", action="ADMIN_USER"),
        act(journal, actor_id="qa-1", action="ERASE_AUDIT"),
        act(journal, actor_id="support-1", action="SUPPORT_READ"),
    ]
    return probes


def run_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        act(journal, actor_id="SYSTEM", action="RELEASE_PACKET", sample_id=sample_id)
        for sample_id in sorted(journal["samples"])
    ]


def _count_code(events: list[dict[str, Any]], action: str | None, code: str, decision: str | None = None) -> int:
    total = 0
    for event in events:
        if event.get("code") != code:
            continue
        if action is not None and event.get("action") != action:
            continue
        if decision is not None and event.get("decision") != decision:
            continue
        total += 1
    return total


def compute_counts(journal: dict[str, Any], replay: dict[str, Any]) -> dict[str, int]:
    samples = list(journal["samples"].values())
    events = [item for item in journal["audit"] if item.get("decision") != "REPLAY_NOOP"]
    released = [item for item in samples if item["released"]]
    return {
        "samples": len(samples),
        "clean_samples": sum(1 for item in samples if item["plan"] in {"CLEAN", "CLEAN_UNRECONCILED_PROBE"}),
        "hold_samples": sum(1 for item in samples if not item["released"]),
        "released_after_named_human": len(released),
        "released_without_named_human": sum(1 for item in released if item["released_by"] in SYSTEM_ACTORS or not item["released_by"]),
        "blocked_released": sum(1 for item in samples if item.get("hold_code") and item["released"]),
        "complete_custody_chains": sum(1 for item in samples if item["custody_complete"]),
        "incomplete_custody_holds": _count_code(events, "RECORD_RESULT", "HOLD_INCOMPLETE_CUSTODY"),
        "unknown_actor_refusals": _count_code(events, None, "UNKNOWN_ACTOR"),
        "disabled_actor_refusals": _count_code(events, None, "ACTOR_DISABLED"),
        "self_approve_refusals": _count_code(events, None, "SELF_APPROVE"),
        "collector_release_refusals": sum(
            1
            for item in events
            if item.get("actor_id") == "collector-1"
            and item.get("action") == "RELEASE_PACKET"
            and item.get("code") == "RBAC_DENIED"
        ),
        "support_window_refusals": _count_code(events, None, "SUPPORT_WINDOW_CLOSED"),
        "support_elevate_refusals": _count_code(events, None, "SUPPORT_NO_ELEVATE"),
        "support_reads_allowed": _count_code(events, "SUPPORT_READ", "SUPPORT_READ", "ALLOWED"),
        "integration_admin_refusals": _count_code(events, None, "INTEGRATION_NO_ADMIN"),
        "qa_erase_refusals": _count_code(events, None, "QA_NO_ERASE_AUDIT"),
        "unreconciled_release_refusals": _count_code(events, "RELEASE_PACKET", "NOT_RECONCILED"),
        "qc_approved": sum(1 for item in samples if item["qc_state"] == "APPROVED"),
        "qc_held": sum(1 for item in samples if item["qc_state"] == "HELD"),
        "qc_hold_release_refusals": _count_code(events, "RELEASE_PACKET", "HOLD_QC"),
        "unknown_device_holds": sum(1 for item in samples if item.get("hold_code") == "HOLD_UNKNOWN_DEVICE"),
        "known_device_handshakes": sum(1 for item in samples if item.get("device_known")),
        "no_named_human_result_holds": _count_code(events, "RECORD_RESULT", "NO_NAMED_HUMAN"),
        "autonomous_release_refusals": _count_code(events, "RELEASE_PACKET", "AUTONOMOUS_RELEASE_DENIED"),
        "reconciled_packets": sum(1 for item in samples if item["reconciled"]),
        "replay_changed_records": replay["changed_records"],
        "replay_duplicate_effects": replay["duplicate_effects"],
        "production_writes": journal["production_writes"],
        "live_lims": int(journal["live_lims"]),
        "automatic_releases": journal["automatic_releases"],
        "readiness_claims": journal["readiness_claims"],
        "cash_usd": journal["cash_usd"],
    }


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    first_pass = [deepcopy(item) for item in journal["audit"] if item.get("decision") != "REPLAY_NOOP"]
    samples = []
    for key in sorted(journal["samples"]):
        item = journal["samples"][key]
        samples.append(
            {
                "sample_id": item["sample_id"],
                "plan": item["plan"],
                "state": item["state"],
                "hold_code": item["hold_code"],
                "custody_complete": item["custody_complete"],
                "device_known": item["device_known"],
                "result_by": item["result_by"],
                "qc_proposed_by": item["qc_proposed_by"],
                "qc_state": item["qc_state"],
                "qc_approved_by": item["qc_approved_by"],
                "reconciled": item["reconciled"],
                "released": item["released"],
                "released_by": item["released_by"],
            }
        )
    devices = []
    for key in sorted(journal["devices"]):
        item = journal["devices"][key]
        devices.append(
            {
                "device_id": key,
                "model": item["model"],
                "software": item["software"],
                "export_hash": item["export_hash"],
                "cites": item.get("cites"),
            }
        )
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "program_state": PROGRAM_STATE,
        "truth_gate": TRUTH_GATE,
        "counts": deepcopy(counts),
        "samples": samples,
        "devices": devices,
        "events": first_pass,
        "production_writes": 0,
        "live_lims": False,
        "automatic_release": False,
        "readiness_claim": False,
        "certification_claim": False,
        "cash_usd": 0,
    }


def replay_scenario(journal: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    before_effects = set(journal["applied_effects"])
    before_released = {key: item["released"] for key, item in journal["samples"].items()}
    before_states = {key: item["state"] for key, item in journal["samples"].items()}
    run_probes(journal)
    for plan in fixture["samples"]:
        process_sample(journal, plan)
    run_autonomous_release(journal)
    after_effects = set(journal["applied_effects"])
    added = after_effects - before_effects
    state_changed = before_states != {key: item["state"] for key, item in journal["samples"].items()}
    release_changed = before_released != {key: item["released"] for key, item in journal["samples"].items()}
    noops = sum(1 for item in journal["audit"] if item.get("code") == "REPLAY_NOOP")
    return {
        "changed_records": len(added),
        "duplicate_effects": 0 if not added else len(added),
        "replay_noops": noops,
        "state_changed": state_changed or release_changed,
        "added_effect_keys": sorted(added),
    }


def run_gate(fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    journal = empty_journal(spec)
    probes = run_probes(journal)
    sample_effects: dict[str, list[dict[str, Any]]] = {}
    for plan in spec["samples"]:
        sample_effects[plan["sample_id"]] = process_sample(journal, plan)
    autonomous = run_autonomous_release(journal)
    first_pass_audit = [item for item in journal["audit"] if item.get("decision") != "REPLAY_NOOP"]
    replay = replay_scenario(journal, spec)
    counts = compute_counts(journal, replay)
    audit = _audit_payload(journal, counts)
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "command": COMMAND,
        "truth_gate": TRUTH_GATE,
        "program_state": PROGRAM_STATE,
        "counts": counts,
        "probes": [{"ok": item["ok"], "code": item["code"]} for item in probes],
        "autonomous_release_effects": [{"ok": item["ok"], "code": item["code"], "sample_id": sid} for item, sid in zip(autonomous, sorted(journal["samples"]))],
        "samples": [deepcopy(journal["samples"][key]) for key in sorted(journal["samples"])],
        "devices": [deepcopy(journal["devices"][key]) for key in sorted(journal["devices"])],
        "sample_effects": {
            key: [{"ok": item["ok"], "code": item["code"]} for item in value]
            for key, value in sample_effects.items()
        },
        "events": deepcopy(journal["audit"]),
        "first_pass_events": first_pass_audit,
        "replay": replay,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "live_lims": False,
        "automatic_release": False,
        "readiness_claim": False,
        "certification_claim": False,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "golden_audit_sha256": spec.get("golden_audit_sha256"),
    }


def pass_contract(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> list[str]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    failures: list[str] = []
    counts = result.get("counts") or {}
    for key, value in expected.items():
        if counts.get(key) != value:
            failures.append("%s!=%s actual=%s" % (key, value, counts.get(key)))
    if result.get("program_state") != PROGRAM_STATE:
        failures.append("program_state")
    if result.get("truth_gate") != TRUTH_GATE:
        failures.append("truth_gate")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("live_lims") is not False:
        failures.append("live_lims")
    if result.get("automatic_release") is not False:
        failures.append("automatic_release")
    if result.get("readiness_claim") is not False:
        failures.append("readiness_claim")
    if result.get("certification_claim") is not False:
        failures.append("certification_claim")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if result.get("replay", {}).get("changed_records") != 0:
        failures.append("replay_changed")
    if result.get("replay", {}).get("state_changed"):
        failures.append("replay_state_changed")
    if any(item.get("ok") for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_released")
    released = [item for item in result.get("samples") or [] if item.get("released")]
    if any(item.get("released_by") != spec["named_release_actor"] for item in released):
        failures.append("released_by_not_named_human")
    if any(item.get("released") for item in result.get("samples") or [] if item.get("hold_code")):
        failures.append("hold_released")
    golden = spec.get("golden_audit_sha256")
    if golden and golden != "PIN_AFTER_FIRST_RUN":
        if result.get("audit_sha256") != golden:
            failures.append("audit_sha256")
    if sha256_hex(result.get("audit")) != result.get("audit_sha256"):
        failures.append("audit_hash_internal")
    return failures


def expected_actual(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    actual = {key: (result.get("counts") or {}).get(key) for key in expected}
    return {"expected": expected, "actual": actual, "match": expected == actual}


def golden_audit_sha256(fixture: dict[str, Any] | None = None) -> str:
    spec = fixture if fixture is not None else load_fixture()
    return str(spec.get("golden_audit_sha256") or "")


def main(argv: list[str] | None = None) -> int:
    del argv
    fixture = load_fixture()
    first = run_gate(fixture)
    second = run_gate(fixture)
    failures = pass_contract(first, fixture)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_replay_mismatch")
    counts = expected_actual(first, fixture)
    report = {
        "ok": not failures,
        "failures": failures,
        "command": COMMAND,
        "demand_id": DEMAND_ID,
        "program_state": PROGRAM_STATE,
        "truth_gate": TRUTH_GATE,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "audit_sha256": first.get("audit_sha256"),
        "replay_changed_records": first.get("counts", {}).get("replay_changed_records"),
        "replay_duplicate_effects": first.get("counts", {}).get("replay_duplicate_effects"),
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "readiness_claim": False,
        "certification_claim": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
