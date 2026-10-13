#!/usr/bin/env python3
"""Deterministic reconciliation core for a donor-intent-to-project outcome portfolio.

This module is network-free and stdlib-only. It validates a frozen portfolio ledger,
keeps money/metric/evidence lineage explicit, and emits a deterministic SHA-256 receipt.
It does not select grants, disburse funds, judge partner performance, or assert impact.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FORBIDDEN_PII_KEYS = {
    "beneficiary",
    "beneficiary_name",
    "beneficiary_id",
    "email",
    "phone",
    "ssn",
    "date_of_birth",
    "dob",
    "first_name",
    "last_name",
    "full_name",
    "street_address",
}


class LedgerError(ValueError):
    """Raised when input is ambiguous, structurally invalid, or unsafe to reconcile."""


def _require_keys(obj: dict[str, Any], *, required: set[str], optional: set[str], where: str) -> None:
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing:
        raise LedgerError(f"{where}: missing keys: {', '.join(sorted(missing))}")
    if unknown:
        raise LedgerError(f"{where}: unknown keys: {', '.join(sorted(unknown))}")


def _require_str(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{where}: expected non-empty string")
    return value


def _require_int(value: Any, *, where: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(f"{where}: expected integer")
    if minimum is not None and value < minimum:
        raise LedgerError(f"{where}: must be >= {minimum}")
    return value


def _require_bool(value: Any, *, where: str) -> bool:
    if not isinstance(value, bool):
        raise LedgerError(f"{where}: expected boolean")
    return value


def _sha(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where)
    if not SHA256_RE.fullmatch(text):
        raise LedgerError(f"{where}: expected 64-hex SHA-256")
    return text.lower()


def _date(value: Any, *, where: str) -> date:
    text = _require_str(value, where=where)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise LedgerError(f"{where}: expected ISO date YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise LedgerError(f"{where}: date must use canonical YYYY-MM-DD")
    return parsed


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _reject_pii_keys(value: Any, *, where: str = "root") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise LedgerError(f"{where}: object key must be a string")
            lowered = key.lower()
            if lowered in FORBIDDEN_PII_KEYS or lowered.startswith("beneficiary_"):
                raise LedgerError(f"{where}: beneficiary/PII field is forbidden: {key}")
            _reject_pii_keys(nested, where=f"{where}.{key}")
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            _reject_pii_keys(nested, where=f"{where}[{idx}]")


def _unique_event(event_id: str, *, where: str, seen: dict[str, str]) -> None:
    prior = seen.get(event_id)
    if prior is not None:
        raise LedgerError(f"duplicate event_id {event_id!r}: {prior} and {where}")
    seen[event_id] = where


def _parse_funds(items: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(items, list) or not items:
        raise LedgerError("root.funds: expected non-empty list")
    out: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(items):
        where = f"root.funds[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"fund_id", "authorized_cents", "restriction"}, optional=set(), where=where)
        fund_id = _require_str(raw["fund_id"], where=f"{where}.fund_id")
        if fund_id in by_id:
            raise LedgerError(f"root.funds: duplicate fund_id {fund_id!r}")
        authorized = _require_int(raw["authorized_cents"], where=f"{where}.authorized_cents", minimum=1)
        restriction = raw["restriction"]
        if not isinstance(restriction, dict):
            raise LedgerError(f"{where}.restriction: expected object")
        _require_keys(restriction, required={"kind"}, optional={"allowed_project_ids"}, where=f"{where}.restriction")
        kind = _require_str(restriction["kind"], where=f"{where}.restriction.kind")
        if kind not in {"unrestricted", "project_ids"}:
            raise LedgerError(f"{where}.restriction.kind: expected unrestricted or project_ids")
        allowed: list[str] = []
        if kind == "project_ids":
            if "allowed_project_ids" not in restriction:
                raise LedgerError(f"{where}.restriction: project_ids restriction requires allowed_project_ids")
            raw_allowed = restriction["allowed_project_ids"]
            if not isinstance(raw_allowed, list) or not raw_allowed:
                raise LedgerError(f"{where}.restriction.allowed_project_ids: expected non-empty list")
            seen_allowed: set[str] = set()
            for j, candidate in enumerate(raw_allowed):
                project_id = _require_str(candidate, where=f"{where}.restriction.allowed_project_ids[{j}]")
                if project_id in seen_allowed:
                    raise LedgerError(f"{where}.restriction.allowed_project_ids: duplicate {project_id!r}")
                seen_allowed.add(project_id)
                allowed.append(project_id)
            allowed.sort()
        elif "allowed_project_ids" in restriction:
            raise LedgerError(f"{where}.restriction: unrestricted fund must not define allowed_project_ids")
        normalized = {
            "fund_id": fund_id,
            "authorized_cents": authorized,
            "restriction": {"kind": kind, "allowed_project_ids": allowed},
        }
        out.append(normalized)
        by_id[fund_id] = normalized
    out.sort(key=lambda x: x["fund_id"])
    return out, by_id


def _parse_project(raw: Any, *, idx: int, global_events: dict[str, str]) -> dict[str, Any]:
    where = f"root.projects[{idx}]"
    if not isinstance(raw, dict):
        raise LedgerError(f"{where}: expected object")
    _require_keys(
        raw,
        required={
            "project_id",
            "partner_id",
            "milestones",
            "metric_definitions",
            "outcome_observations",
            "attestations",
            "corrections",
        },
        optional=set(),
        where=where,
    )
    project_id = _require_str(raw["project_id"], where=f"{where}.project_id")
    partner_id = _require_str(raw["partner_id"], where=f"{where}.partner_id")
    holds: list[str] = []

    milestones_raw = raw["milestones"]
    if not isinstance(milestones_raw, list):
        raise LedgerError(f"{where}.milestones: expected list")
    milestones: list[dict[str, Any]] = []
    seen_milestones: set[str] = set()
    for j, item in enumerate(milestones_raw):
        mwhere = f"{where}.milestones[{j}]"
        if not isinstance(item, dict):
            raise LedgerError(f"{mwhere}: expected object")
        _require_keys(item, required={"milestone_id", "status", "evidence_sha256"}, optional=set(), where=mwhere)
        milestone_id = _require_str(item["milestone_id"], where=f"{mwhere}.milestone_id")
        if milestone_id in seen_milestones:
            raise LedgerError(f"{where}.milestones: duplicate milestone_id {milestone_id!r}")
        seen_milestones.add(milestone_id)
        status = _require_str(item["status"], where=f"{mwhere}.status")
        if status not in {"pending", "complete", "waived"}:
            raise LedgerError(f"{mwhere}.status: expected pending, complete, or waived")
        if status == "pending":
            holds.append("MILESTONE_PENDING")
        milestones.append({"milestone_id": milestone_id, "status": status, "evidence_sha256": _sha(item["evidence_sha256"], where=f"{mwhere}.evidence_sha256")})
    milestones.sort(key=lambda x: x["milestone_id"])

    defs_raw = raw["metric_definitions"]
    if not isinstance(defs_raw, list) or not defs_raw:
        raise LedgerError(f"{where}.metric_definitions: expected non-empty list")
    definitions: list[dict[str, Any]] = []
    defs_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    defs_by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for j, item in enumerate(defs_raw):
        dwhere = f"{where}.metric_definitions[{j}]"
        if not isinstance(item, dict):
            raise LedgerError(f"{dwhere}: expected object")
        _require_keys(
            item,
            required={"metric_id", "revision", "unit", "scale", "effective_from", "effective_to", "donor_safe", "causal_claim"},
            optional=set(),
            where=dwhere,
        )
        metric_id = _require_str(item["metric_id"], where=f"{dwhere}.metric_id")
        revision = _require_int(item["revision"], where=f"{dwhere}.revision", minimum=1)
        key = (metric_id, revision)
        if key in defs_by_key:
            raise LedgerError(f"{where}.metric_definitions: duplicate metric/revision {metric_id!r}/{revision}")
        effective_from = _date(item["effective_from"], where=f"{dwhere}.effective_from")
        effective_to_raw = item["effective_to"]
        effective_to: date | None
        if effective_to_raw is None:
            effective_to = None
        else:
            effective_to = _date(effective_to_raw, where=f"{dwhere}.effective_to")
            if effective_to < effective_from:
                raise LedgerError(f"{dwhere}: effective_to precedes effective_from")
        donor_safe = _require_bool(item["donor_safe"], where=f"{dwhere}.donor_safe")
        causal_claim = _require_bool(item["causal_claim"], where=f"{dwhere}.causal_claim")
        normalized = {
            "metric_id": metric_id,
            "revision": revision,
            "unit": _require_str(item["unit"], where=f"{dwhere}.unit"),
            "scale": _require_int(item["scale"], where=f"{dwhere}.scale", minimum=1),
            "effective_from": effective_from.isoformat(),
            "effective_to": effective_to.isoformat() if effective_to else None,
            "donor_safe": donor_safe,
            "causal_claim": causal_claim,
        }
        definitions.append(normalized)
        defs_by_key[key] = normalized
        defs_by_metric[metric_id].append(normalized)
    for metric_id, defs in defs_by_metric.items():
        spans = sorted(defs, key=lambda d: (d["effective_from"], d["revision"]))
        prior_end: date | None = None
        prior_open = False
        for pos, d in enumerate(spans):
            start = date.fromisoformat(d["effective_from"])
            end = date.fromisoformat(d["effective_to"]) if d["effective_to"] else None
            if pos and (prior_open or prior_end is not None and start <= prior_end):
                raise LedgerError(f"{where}.metric_definitions: overlapping effective windows for metric {metric_id!r}")
            prior_end = end
            prior_open = end is None
    definitions.sort(key=lambda x: (x["metric_id"], x["revision"]))

    obs_raw = raw["outcome_observations"]
    if not isinstance(obs_raw, list):
        raise LedgerError(f"{where}.outcome_observations: expected list")
    observations: list[dict[str, Any]] = []
    obs_by_id: dict[str, dict[str, Any]] = {}
    for j, item in enumerate(obs_raw):
        owhere = f"{where}.outcome_observations[{j}]"
        if not isinstance(item, dict):
            raise LedgerError(f"{owhere}: expected object")
        _require_keys(
            item,
            required={"event_id", "metric_id", "definition_revision", "period_start", "period_end", "observed_at", "value_scaled", "evidence_sha256", "corrects_event_id"},
            optional=set(),
            where=owhere,
        )
        event_id = _require_str(item["event_id"], where=f"{owhere}.event_id")
        _unique_event(event_id, where=owhere, seen=global_events)
        if event_id in obs_by_id:
            raise LedgerError(f"{where}.outcome_observations: duplicate event_id {event_id!r}")
        metric_id = _require_str(item["metric_id"], where=f"{owhere}.metric_id")
        revision = _require_int(item["definition_revision"], where=f"{owhere}.definition_revision", minimum=1)
        if (metric_id, revision) not in defs_by_key:
            raise LedgerError(f"{owhere}: unknown metric definition {metric_id!r}/{revision}")
        period_start = _date(item["period_start"], where=f"{owhere}.period_start")
        period_end = _date(item["period_end"], where=f"{owhere}.period_end")
        observed_at = _date(item["observed_at"], where=f"{owhere}.observed_at")
        if period_end < period_start:
            raise LedgerError(f"{owhere}: period_end precedes period_start")
        if observed_at < period_end:
            raise LedgerError(f"{owhere}: observed_at precedes period_end")
        corrects_raw = item["corrects_event_id"]
        corrects = None if corrects_raw is None else _require_str(corrects_raw, where=f"{owhere}.corrects_event_id")
        normalized = {
            "event_id": event_id,
            "metric_id": metric_id,
            "definition_revision": revision,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "observed_at": observed_at.isoformat(),
            "value_scaled": _require_int(item["value_scaled"], where=f"{owhere}.value_scaled", minimum=0),
            "evidence_sha256": _sha(item["evidence_sha256"], where=f"{owhere}.evidence_sha256"),
            "corrects_event_id": corrects,
        }
        observations.append(normalized)
        obs_by_id[event_id] = normalized

    corrections_raw = raw["corrections"]
    if not isinstance(corrections_raw, list):
        raise LedgerError(f"{where}.corrections: expected list")
    corrections: list[dict[str, Any]] = []
    withdrawn: set[str] = set()
    for j, item in enumerate(corrections_raw):
        cwhere = f"{where}.corrections[{j}]"
        if not isinstance(item, dict):
            raise LedgerError(f"{cwhere}: expected object")
        _require_keys(item, required={"event_id", "target_event_id", "action", "observed_at", "evidence_sha256"}, optional=set(), where=cwhere)
        event_id = _require_str(item["event_id"], where=f"{cwhere}.event_id")
        _unique_event(event_id, where=cwhere, seen=global_events)
        target = _require_str(item["target_event_id"], where=f"{cwhere}.target_event_id")
        if target not in obs_by_id:
            raise LedgerError(f"{cwhere}: unknown target_event_id {target!r}")
        action = _require_str(item["action"], where=f"{cwhere}.action")
        if action != "withdraw":
            raise LedgerError(f"{cwhere}.action: only withdraw is supported")
        observed_at = _date(item["observed_at"], where=f"{cwhere}.observed_at")
        target_date = date.fromisoformat(obs_by_id[target]["observed_at"])
        if observed_at < target_date:
            raise LedgerError(f"{cwhere}: correction precedes target observation")
        if target in withdrawn:
            raise LedgerError(f"{cwhere}: observation {target!r} already withdrawn")
        withdrawn.add(target)
        corrections.append({"event_id": event_id, "target_event_id": target, "action": action, "observed_at": observed_at.isoformat(), "evidence_sha256": _sha(item["evidence_sha256"], where=f"{cwhere}.evidence_sha256")})

    for obs in observations:
        target = obs["corrects_event_id"]
        if target is None:
            continue
        if target not in obs_by_id:
            raise LedgerError(f"{where}: observation {obs['event_id']!r} corrects unknown event {target!r}")
        old = obs_by_id[target]
        if old["metric_id"] != obs["metric_id"]:
            raise LedgerError(f"{where}: corrected observation must keep metric_id")
        if date.fromisoformat(obs["observed_at"]) < date.fromisoformat(old["observed_at"]):
            raise LedgerError(f"{where}: corrected observation precedes original")
        if target not in withdrawn:
            holds.append("CORRECTION_WITHOUT_WITHDRAWAL")

    attest_raw = raw["attestations"]
    if not isinstance(attest_raw, list):
        raise LedgerError(f"{where}.attestations: expected list")
    attestations: list[dict[str, Any]] = []
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for j, item in enumerate(attest_raw):
        awhere = f"{where}.attestations[{j}]"
        if not isinstance(item, dict):
            raise LedgerError(f"{awhere}: expected object")
        _require_keys(item, required={"event_id", "subject_event_id", "partner_id", "status", "observed_at", "evidence_sha256"}, optional=set(), where=awhere)
        event_id = _require_str(item["event_id"], where=f"{awhere}.event_id")
        _unique_event(event_id, where=awhere, seen=global_events)
        subject = _require_str(item["subject_event_id"], where=f"{awhere}.subject_event_id")
        if subject not in obs_by_id:
            raise LedgerError(f"{awhere}: unknown subject_event_id {subject!r}")
        att_partner = _require_str(item["partner_id"], where=f"{awhere}.partner_id")
        if att_partner != partner_id:
            raise LedgerError(f"{awhere}: attestation partner_id does not match project")
        status = _require_str(item["status"], where=f"{awhere}.status")
        if status not in {"confirmed", "withdrawn"}:
            raise LedgerError(f"{awhere}.status: expected confirmed or withdrawn")
        observed_at = _date(item["observed_at"], where=f"{awhere}.observed_at")
        if observed_at < date.fromisoformat(obs_by_id[subject]["observed_at"]):
            raise LedgerError(f"{awhere}: attestation precedes observation")
        normalized = {"event_id": event_id, "subject_event_id": subject, "partner_id": att_partner, "status": status, "observed_at": observed_at.isoformat(), "evidence_sha256": _sha(item["evidence_sha256"], where=f"{awhere}.evidence_sha256")}
        attestations.append(normalized)
        by_subject[subject].append(normalized)

    publishable: list[dict[str, Any]] = []
    for obs in observations:
        if obs["event_id"] in withdrawn:
            continue
        definition = defs_by_key[(obs["metric_id"], obs["definition_revision"])]
        period_start = date.fromisoformat(obs["period_start"])
        period_end = date.fromisoformat(obs["period_end"])
        def_start = date.fromisoformat(definition["effective_from"])
        def_end = date.fromisoformat(definition["effective_to"]) if definition["effective_to"] else None
        if period_start < def_start or (def_end is not None and period_end > def_end):
            holds.append("STALE_OR_INAPPLICABLE_METRIC_DEFINITION")
            continue
        if not definition["donor_safe"]:
            holds.append("OUTCOME_NOT_DONOR_SAFE")
            continue
        if definition["causal_claim"]:
            holds.append("CAUSAL_IMPACT_CLAIM_NOT_ALLOWED")
            continue
        subject_atts = by_subject.get(obs["event_id"], [])
        if not subject_atts:
            holds.append("OUTCOME_ATTESTATION_MISSING")
            continue
        latest_date = max(a["observed_at"] for a in subject_atts)
        latest = [a for a in subject_atts if a["observed_at"] == latest_date]
        statuses = {a["status"] for a in latest}
        if len(statuses) != 1:
            raise LedgerError(f"{where}: conflicting latest attestation states for {obs['event_id']!r}")
        if next(iter(statuses)) != "confirmed":
            holds.append("OUTCOME_ATTESTATION_WITHDRAWN")
            continue
        publishable.append({
            "event_id": obs["event_id"],
            "metric_id": obs["metric_id"],
            "definition_revision": obs["definition_revision"],
            "period_start": obs["period_start"],
            "period_end": obs["period_end"],
            "value_scaled": obs["value_scaled"],
            "unit": definition["unit"],
            "scale": definition["scale"],
            "observation_evidence_sha256": obs["evidence_sha256"],
            "attestation_evidence_sha256": sorted(latest, key=lambda a: a["event_id"])[-1]["evidence_sha256"],
        })

    observations.sort(key=lambda x: x["event_id"])
    attestations.sort(key=lambda x: x["event_id"])
    corrections.sort(key=lambda x: x["event_id"])
    publishable.sort(key=lambda x: x["event_id"])
    holds = sorted(set(holds))
    return {
        "project_id": project_id,
        "partner_id": partner_id,
        "status": "PASS" if not holds else "HOLD",
        "holds": holds,
        "milestones": milestones,
        "metric_definitions": definitions,
        "outcome_observations": observations,
        "attestations": attestations,
        "corrections": corrections,
        "publishable_outcomes": publishable,
    }


def reconcile(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LedgerError("root: expected object")
    _reject_pii_keys(payload)
    _require_keys(
        payload,
        required={"schema_version", "portfolio_id", "expected_portfolio_award_cents", "require_full_disbursement", "funds", "awards", "projects"},
        optional=set(),
        where="root",
    )
    schema_version = _require_int(payload["schema_version"], where="root.schema_version", minimum=1)
    if schema_version != SCHEMA_VERSION:
        raise LedgerError(f"root.schema_version: unsupported version {schema_version}")
    portfolio_id = _require_str(payload["portfolio_id"], where="root.portfolio_id")
    expected_total = _require_int(payload["expected_portfolio_award_cents"], where="root.expected_portfolio_award_cents", minimum=1)
    require_full = _require_bool(payload["require_full_disbursement"], where="root.require_full_disbursement")

    funds, funds_by_id = _parse_funds(payload["funds"])
    global_events: dict[str, str] = {}

    projects_raw = payload["projects"]
    if not isinstance(projects_raw, list) or not projects_raw:
        raise LedgerError("root.projects: expected non-empty list")
    projects: list[dict[str, Any]] = []
    projects_by_id: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(projects_raw):
        project = _parse_project(raw, idx=idx, global_events=global_events)
        project_id = project["project_id"]
        if project_id in projects_by_id:
            raise LedgerError(f"root.projects: duplicate project_id {project_id!r}")
        projects.append(project)
        projects_by_id[project_id] = project

    awards_raw = payload["awards"]
    if not isinstance(awards_raw, list) or not awards_raw:
        raise LedgerError("root.awards: expected non-empty list")
    awards: list[dict[str, Any]] = []
    seen_awards: set[str] = set()
    allocated_by_fund: dict[str, int] = defaultdict(int)
    project_award_owner: dict[str, str] = {}
    project_allocated: dict[str, int] = defaultdict(int)
    portfolio_total = 0
    paid_total = 0
    pending_total = 0
    portfolio_holds: list[str] = []

    for idx, raw in enumerate(awards_raw):
        where = f"root.awards[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"award_id", "partner_id", "award_cents", "project_allocations", "disbursements"}, optional=set(), where=where)
        award_id = _require_str(raw["award_id"], where=f"{where}.award_id")
        if award_id in seen_awards:
            raise LedgerError(f"root.awards: duplicate award_id {award_id!r}")
        seen_awards.add(award_id)
        partner_id = _require_str(raw["partner_id"], where=f"{where}.partner_id")
        award_cents = _require_int(raw["award_cents"], where=f"{where}.award_cents", minimum=1)
        award_holds: list[str] = []

        alloc_raw = raw["project_allocations"]
        if not isinstance(alloc_raw, list) or not alloc_raw:
            raise LedgerError(f"{where}.project_allocations: expected non-empty list")
        allocations: list[dict[str, Any]] = []
        allocation_sum = 0
        for j, item in enumerate(alloc_raw):
            awhere = f"{where}.project_allocations[{j}]"
            if not isinstance(item, dict):
                raise LedgerError(f"{awhere}: expected object")
            _require_keys(item, required={"allocation_id", "project_id", "fund_id", "amount_cents"}, optional=set(), where=awhere)
            allocation_id = _require_str(item["allocation_id"], where=f"{awhere}.allocation_id")
            _unique_event(allocation_id, where=awhere, seen=global_events)
            project_id = _require_str(item["project_id"], where=f"{awhere}.project_id")
            fund_id = _require_str(item["fund_id"], where=f"{awhere}.fund_id")
            amount = _require_int(item["amount_cents"], where=f"{awhere}.amount_cents", minimum=1)
            if project_id not in projects_by_id:
                raise LedgerError(f"{awhere}: unknown project_id {project_id!r}")
            if projects_by_id[project_id]["partner_id"] != partner_id:
                raise LedgerError(f"{awhere}: project partner does not match award partner")
            existing_owner = project_award_owner.get(project_id)
            if existing_owner is not None and existing_owner != award_id:
                raise LedgerError(f"{awhere}: project {project_id!r} allocated by multiple awards")
            project_award_owner[project_id] = award_id
            if fund_id not in funds_by_id:
                raise LedgerError(f"{awhere}: unknown fund_id {fund_id!r}")
            fund = funds_by_id[fund_id]
            restriction = fund["restriction"]
            if restriction["kind"] == "project_ids" and project_id not in restriction["allowed_project_ids"]:
                award_holds.append("FUND_RESTRICTION_VIOLATION")
            allocation_sum += amount
            project_allocated[project_id] += amount
            allocated_by_fund[fund_id] += amount
            allocations.append({"allocation_id": allocation_id, "project_id": project_id, "fund_id": fund_id, "amount_cents": amount})
        if allocation_sum != award_cents:
            award_holds.append("AWARD_ALLOCATION_MISMATCH")

        disb_raw = raw["disbursements"]
        if not isinstance(disb_raw, list):
            raise LedgerError(f"{where}.disbursements: expected list")
        disbursements: list[dict[str, Any]] = []
        paid = 0
        pending = 0
        for j, item in enumerate(disb_raw):
            dwhere = f"{where}.disbursements[{j}]"
            if not isinstance(item, dict):
                raise LedgerError(f"{dwhere}: expected object")
            _require_keys(item, required={"event_id", "amount_cents", "status", "evidence_sha256"}, optional=set(), where=dwhere)
            event_id = _require_str(item["event_id"], where=f"{dwhere}.event_id")
            _unique_event(event_id, where=dwhere, seen=global_events)
            amount = _require_int(item["amount_cents"], where=f"{dwhere}.amount_cents", minimum=0)
            status = _require_str(item["status"], where=f"{dwhere}.status")
            if status not in {"pending", "paid", "void"}:
                raise LedgerError(f"{dwhere}.status: expected pending, paid, or void")
            if status == "paid":
                paid += amount
            elif status == "pending":
                pending += amount
            disbursements.append({"event_id": event_id, "amount_cents": amount, "status": status, "evidence_sha256": _sha(item["evidence_sha256"], where=f"{dwhere}.evidence_sha256")})
        if paid > award_cents:
            award_holds.append("DISBURSEMENT_EXCEEDS_AWARD")
        if paid + pending > award_cents:
            award_holds.append("COMMITTED_DISBURSEMENT_EXCEEDS_AWARD")
        if require_full and paid != award_cents:
            award_holds.append("AWARD_NOT_FULLY_DISBURSED")
        allocations.sort(key=lambda x: x["allocation_id"])
        disbursements.sort(key=lambda x: x["event_id"])
        award_holds = sorted(set(award_holds))
        awards.append({
            "award_id": award_id,
            "partner_id": partner_id,
            "status": "PASS" if not award_holds else "HOLD",
            "holds": award_holds,
            "award_cents": award_cents,
            "allocated_cents": allocation_sum,
            "paid_cents": paid,
            "pending_cents": pending,
            "project_allocations": allocations,
            "disbursements": disbursements,
        })
        portfolio_total += award_cents
        paid_total += paid
        pending_total += pending
        portfolio_holds.extend(award_holds)

    if portfolio_total != expected_total:
        portfolio_holds.append("PORTFOLIO_AWARD_TOTAL_MISMATCH")
    for fund_id, allocated in allocated_by_fund.items():
        if allocated > funds_by_id[fund_id]["authorized_cents"]:
            portfolio_holds.append("FUND_OVERALLOCATED")
    for project_id in projects_by_id:
        if project_id not in project_award_owner or project_allocated[project_id] <= 0:
            portfolio_holds.append("PROJECT_WITHOUT_AWARD_ALLOCATION")
            projects_by_id[project_id]["holds"] = sorted(set(projects_by_id[project_id]["holds"] + ["PROJECT_WITHOUT_AWARD_ALLOCATION"]))
            projects_by_id[project_id]["status"] = "HOLD"

    for project in projects:
        portfolio_holds.extend(project["holds"])

    awards.sort(key=lambda x: x["award_id"])
    projects.sort(key=lambda x: x["project_id"])
    portfolio_holds = sorted(set(portfolio_holds))
    fund_usage = [
        {
            "fund_id": fund["fund_id"],
            "authorized_cents": fund["authorized_cents"],
            "allocated_cents": allocated_by_fund.get(fund["fund_id"], 0),
            "remaining_cents": fund["authorized_cents"] - allocated_by_fund.get(fund["fund_id"], 0),
        }
        for fund in funds
    ]
    publishable_count = sum(len(p["publishable_outcomes"]) for p in projects)
    held_projects = sum(1 for p in projects if p["status"] == "HOLD")
    held_awards = sum(1 for a in awards if a["status"] == "HOLD")

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "portfolio_id": portfolio_id,
        "policy": {
            "expected_portfolio_award_cents": expected_total,
            "require_full_disbursement": require_full,
            "beneficiary_pii_allowed": False,
            "causal_impact_claims_allowed": False,
        },
        "summary": {
            "status": "PASS" if not portfolio_holds else "HOLD",
            "holds": portfolio_holds,
            "fund_count": len(funds),
            "award_count": len(awards),
            "project_count": len(projects),
            "held_award_count": held_awards,
            "held_project_count": held_projects,
            "portfolio_award_cents": portfolio_total,
            "paid_disbursement_cents": paid_total,
            "pending_disbursement_cents": pending_total,
            "publishable_outcome_count": publishable_count,
        },
        "funds": funds,
        "fund_usage": fund_usage,
        "awards": awards,
        "projects": projects,
    }
    result["receipt_sha256"] = hashlib.sha256(_canonical_bytes(result)).hexdigest()
    return result


def verify_receipt(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    claimed = result.get("receipt_sha256")
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        return False
    unsigned = dict(result)
    del unsigned["receipt_sha256"]
    expected = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    return hmac.compare_digest(claimed.lower(), expected)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LedgerError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid JSON in {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="portfolio ledger JSON")
    parser.add_argument("--output", type=Path, help="write pretty JSON receipt")
    parser.add_argument("--require-pass", action="store_true", help="exit 3 if receipt status is HOLD")
    parser.add_argument("--verify", type=Path, help="verify an emitted receipt without source input")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            result = _load_json(args.verify)
            ok = verify_receipt(result)
            print("VALID" if ok else "INVALID")
            return 0 if ok else 4
        if args.input is None:
            parser.error("input is required unless --verify is used")
        result = reconcile(_load_json(args.input))
    except LedgerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    if args.require_pass and result["summary"]["status"] != "PASS":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
