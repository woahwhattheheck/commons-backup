from __future__ import annotations

from typing import Any
from .common import (
    INPUT_SCHEMA, CURRENCY, SUPPORT_MAX_AGE_SECONDS, PAYMENT_MAX_AGE_SECONDS, ROUTE_MAX_AGE_SECONDS, MILESTONE_MAX_AGE_SECONDS, BASELINE_STATES, CHANGE_STATES, MILESTONE_STATES, PAYMENT_STATES, PAYMENT_CLASSES, SUPPORT_SEVERITIES, FINDING_STATES, GAP_STATES, ROUTE_STATES, HYPOTHESIS_BASES, GateError, _keys, _string, _bool, _int, _enum, _sha, _ts, _dt, _age, _source
)

def _normalize(packet: dict[str, Any], now: str) -> dict[str, Any]:
    _keys(packet, {
        "schema", "case_id", "baseline", "change_orders", "milestones", "payment",
        "support_findings", "renewal_window", "security_data_gaps",
        "expansion_hypotheses", "route_control",
    }, "input")
    if packet["schema"] != INPUT_SCHEMA:
        raise GateError("input: unsupported schema")
    case_id = _string(packet["case_id"], "case_id", token=True)

    baseline = packet["baseline"]
    _keys(baseline, {
        "baseline_id", "generation", "status", "currency", "accepted_total_cents",
        "scope_sha256", "accepted_at", "source"
    }, "baseline")
    baseline_status = _enum(baseline["status"], BASELINE_STATES, "baseline.status")
    accepted_at = _ts(baseline["accepted_at"], "baseline.accepted_at")
    _age(now, accepted_at, "baseline.accepted_at")
    currency = _string(baseline["currency"], "baseline.currency", max_len=3)
    if not CURRENCY.fullmatch(currency):
        raise GateError("baseline.currency: ISO-style currency required")
    baseline_n = {
        "baseline_id": _string(baseline["baseline_id"], "baseline.baseline_id", token=True),
        "generation": _int(baseline["generation"], "baseline.generation", 1, 2**53 - 1),
        "status": baseline_status,
        "currency": currency,
        "accepted_total_cents": _int(baseline["accepted_total_cents"], "baseline.accepted_total_cents", 0),
        "scope_sha256": _sha(baseline["scope_sha256"], "baseline.scope_sha256"),
        "accepted_at": accepted_at,
        "source": _source(baseline["source"], "baseline.source", now),
    }

    if not isinstance(packet["change_orders"], list) or len(packet["change_orders"]) > 64:
        raise GateError("change_orders: list required")
    change_orders = []
    seen_change_ids: set[str] = set()
    seen_change_generations: set[int] = set()
    for i, row in enumerate(packet["change_orders"]):
        where = f"change_orders[{i}]"
        _keys(row, {
            "change_order_id", "generation", "status", "currency", "delta_cents",
            "scope_sha256", "decided_at", "source"
        }, where)
        cid = _string(row["change_order_id"], f"{where}.change_order_id", token=True)
        gen = _int(row["generation"], f"{where}.generation", baseline_n["generation"] + 1, 2**53 - 1)
        if cid in seen_change_ids or gen in seen_change_generations:
            raise GateError(f"{where}: duplicate id/generation")
        seen_change_ids.add(cid); seen_change_generations.add(gen)
        if row["currency"] != currency:
            raise GateError(f"{where}.currency: baseline mismatch")
        decided = _ts(row["decided_at"], f"{where}.decided_at")
        _age(now, decided, f"{where}.decided_at")
        if _dt(decided) < _dt(accepted_at):
            raise GateError(f"{where}.decided_at: predates baseline acceptance")
        change_orders.append({
            "change_order_id": cid,
            "generation": gen,
            "status": _enum(row["status"], CHANGE_STATES, f"{where}.status"),
            "currency": currency,
            "delta_cents": _int(row["delta_cents"], f"{where}.delta_cents", -10**12, 10**12),
            "scope_sha256": _sha(row["scope_sha256"], f"{where}.scope_sha256"),
            "decided_at": decided,
            "source": _source(row["source"], f"{where}.source", now),
        })
    change_orders.sort(key=lambda x: (x["generation"], x["change_order_id"]))
    if change_orders:
        generations = [x["generation"] for x in change_orders]
        expected_generations = list(range(baseline_n["generation"] + 1, max(generations) + 1))
        if generations != expected_generations:
            raise GateError("change_orders: generation gap/reorder")

    if not isinstance(packet["milestones"], list) or not packet["milestones"] or len(packet["milestones"]) > 128:
        raise GateError("milestones: non-empty bounded list required")
    milestones = []
    seen_milestones: set[str] = set()
    for i, row in enumerate(packet["milestones"]):
        where = f"milestones[{i}]"
        _keys(row, {
            "milestone_id", "commercial_generation", "status", "delivered_at",
            "accepted_at", "acceptance_actor", "source"
        }, where)
        mid = _string(row["milestone_id"], f"{where}.milestone_id", token=True)
        if mid in seen_milestones:
            raise GateError(f"{where}: duplicate milestone_id")
        seen_milestones.add(mid)
        delivered = _ts(row["delivered_at"], f"{where}.delivered_at")
        _age(now, delivered, f"{where}.delivered_at", MILESTONE_MAX_AGE_SECONDS)
        accepted = row["accepted_at"]
        if accepted is not None:
            accepted = _ts(accepted, f"{where}.accepted_at")
            _age(now, accepted, f"{where}.accepted_at", MILESTONE_MAX_AGE_SECONDS)
            if _dt(accepted) < _dt(delivered):
                raise GateError(f"{where}.accepted_at: predates delivery")
        actor = _string(row["acceptance_actor"], f"{where}.acceptance_actor", token=True)
        milestones.append({
            "milestone_id": mid,
            "commercial_generation": _int(row["commercial_generation"], f"{where}.commercial_generation", 1, 2**53 - 1),
            "status": _enum(row["status"], MILESTONE_STATES, f"{where}.status"),
            "delivered_at": delivered,
            "accepted_at": accepted,
            "acceptance_actor": actor,
            "source": _source(row["source"], f"{where}.source", now, max_age=MILESTONE_MAX_AGE_SECONDS),
        })
    milestones.sort(key=lambda x: x["milestone_id"])

    payment = packet["payment"]
    _keys(payment, {
        "payment_id", "commercial_generation", "state", "evidence_class", "currency",
        "settled_cents", "refunded_cents", "disputed", "observed_at", "source"
    }, "payment")
    if payment["currency"] != currency:
        raise GateError("payment.currency: baseline mismatch")
    pay_observed = _ts(payment["observed_at"], "payment.observed_at")
    _age(now, pay_observed, "payment.observed_at", PAYMENT_MAX_AGE_SECONDS)
    payment_n = {
        "payment_id": _string(payment["payment_id"], "payment.payment_id", token=True),
        "commercial_generation": _int(payment["commercial_generation"], "payment.commercial_generation", 1, 2**53 - 1),
        "state": _enum(payment["state"], PAYMENT_STATES, "payment.state"),
        "evidence_class": _enum(payment["evidence_class"], PAYMENT_CLASSES, "payment.evidence_class"),
        "currency": currency,
        "settled_cents": _int(payment["settled_cents"], "payment.settled_cents", 0),
        "refunded_cents": _int(payment["refunded_cents"], "payment.refunded_cents", 0),
        "disputed": _bool(payment["disputed"], "payment.disputed"),
        "observed_at": pay_observed,
        "source": _source(payment["source"], "payment.source", now, max_age=PAYMENT_MAX_AGE_SECONDS),
    }

    if not isinstance(packet["support_findings"], list) or len(packet["support_findings"]) > 128:
        raise GateError("support_findings: list required")
    findings = []
    seen_findings: set[str] = set()
    for i, row in enumerate(packet["support_findings"]):
        where = f"support_findings[{i}]"
        _keys(row, {"finding_id", "severity", "status", "observed_at", "summary_sha256", "source"}, where)
        fid = _string(row["finding_id"], f"{where}.finding_id", token=True)
        if fid in seen_findings:
            raise GateError(f"{where}: duplicate finding_id")
        seen_findings.add(fid)
        observed = _ts(row["observed_at"], f"{where}.observed_at")
        _age(now, observed, f"{where}.observed_at", SUPPORT_MAX_AGE_SECONDS)
        findings.append({
            "finding_id": fid,
            "severity": _enum(row["severity"], SUPPORT_SEVERITIES, f"{where}.severity"),
            "status": _enum(row["status"], FINDING_STATES, f"{where}.status"),
            "observed_at": observed,
            "summary_sha256": _sha(row["summary_sha256"], f"{where}.summary_sha256"),
            "source": _source(row["source"], f"{where}.source", now, max_age=SUPPORT_MAX_AGE_SECONDS),
        })
    findings.sort(key=lambda x: x["finding_id"])

    window = packet["renewal_window"]
    _keys(window, {"window_id", "opens_at", "closes_at", "source"}, "renewal_window")
    opens = _ts(window["opens_at"], "renewal_window.opens_at")
    closes = _ts(window["closes_at"], "renewal_window.closes_at")
    if _dt(closes) <= _dt(opens):
        raise GateError("renewal_window: closes_at must follow opens_at")
    window_n = {
        "window_id": _string(window["window_id"], "renewal_window.window_id", token=True),
        "opens_at": opens,
        "closes_at": closes,
        "source": _source(window["source"], "renewal_window.source", now),
    }

    if not isinstance(packet["security_data_gaps"], list) or len(packet["security_data_gaps"]) > 128:
        raise GateError("security_data_gaps: list required")
    gaps = []
    seen_gaps: set[str] = set()
    for i, row in enumerate(packet["security_data_gaps"]):
        where = f"security_data_gaps[{i}]"
        _keys(row, {"gap_id", "status", "blocking", "evidence_sha256", "source"}, where)
        gid = _string(row["gap_id"], f"{where}.gap_id", token=True)
        if gid in seen_gaps:
            raise GateError(f"{where}: duplicate gap_id")
        seen_gaps.add(gid)
        gaps.append({
            "gap_id": gid,
            "status": _enum(row["status"], GAP_STATES, f"{where}.status"),
            "blocking": _bool(row["blocking"], f"{where}.blocking"),
            "evidence_sha256": _sha(row["evidence_sha256"], f"{where}.evidence_sha256"),
            "source": _source(row["source"], f"{where}.source", now, max_age=SUPPORT_MAX_AGE_SECONDS),
        })
    gaps.sort(key=lambda x: x["gap_id"])

    if not isinstance(packet["expansion_hypotheses"], list) or len(packet["expansion_hypotheses"]) > 64:
        raise GateError("expansion_hypotheses: list required")
    hypotheses = []
    seen_hyp: set[str] = set()
    for i, row in enumerate(packet["expansion_hypotheses"]):
        where = f"expansion_hypotheses[{i}]"
        _keys(row, {
            "hypothesis_id", "basis", "summary_sha256", "commercial_state",
            "buyer_interest_claimed", "roi_claimed", "savings_claimed", "usage_claimed",
            "urgency_claimed", "expansion_approved_claimed", "source"
        }, where)
        hid = _string(row["hypothesis_id"], f"{where}.hypothesis_id", token=True)
        if hid in seen_hyp:
            raise GateError(f"{where}: duplicate hypothesis_id")
        seen_hyp.add(hid)
        flags = {
            key: _bool(row[key], f"{where}.{key}")
            for key in (
                "buyer_interest_claimed", "roi_claimed", "savings_claimed", "usage_claimed",
                "urgency_claimed", "expansion_approved_claimed"
            )
        }
        hypotheses.append({
            "hypothesis_id": hid,
            "basis": _enum(row["basis"], HYPOTHESIS_BASES, f"{where}.basis"),
            "summary_sha256": _sha(row["summary_sha256"], f"{where}.summary_sha256"),
            "commercial_state": _string(row["commercial_state"], f"{where}.commercial_state", token=True),
            **flags,
            "source": _source(row["source"], f"{where}.source", now, max_age=SUPPORT_MAX_AGE_SECONDS),
        })
    hypotheses.sort(key=lambda x: x["hypothesis_id"])

    route = packet["route_control"]
    _keys(route, {"route_id", "collision_key", "muse_key", "state", "observed_at", "source"}, "route_control")
    route_observed = _ts(route["observed_at"], "route_control.observed_at")
    _age(now, route_observed, "route_control.observed_at", ROUTE_MAX_AGE_SECONDS)
    route_n = {
        "route_id": _string(route["route_id"], "route_control.route_id", token=True),
        "collision_key": _string(route["collision_key"], "route_control.collision_key", token=True),
        "muse_key": _string(route["muse_key"], "route_control.muse_key", token=True),
        "state": _enum(route["state"], ROUTE_STATES, "route_control.state"),
        "observed_at": route_observed,
        "source": _source(route["source"], "route_control.source", now, max_age=ROUTE_MAX_AGE_SECONDS),
    }

    return {
        "schema": INPUT_SCHEMA,
        "case_id": case_id,
        "baseline": baseline_n,
        "change_orders": change_orders,
        "milestones": milestones,
        "payment": payment_n,
        "support_findings": findings,
        "renewal_window": window_n,
        "security_data_gaps": gaps,
        "expansion_hypotheses": hypotheses,
        "route_control": route_n,
    }
