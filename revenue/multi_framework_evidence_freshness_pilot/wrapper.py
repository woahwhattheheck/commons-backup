"""Buyer-safe fixed diagnostic wrapper for the merged #13908 engine."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from revenue.multi_framework_evidence_freshness.gate import (
    GateError,
    compile_packet,
    verify_packet,
)

SCHEMA = "commons.multi-framework-evidence-freshness-pilot-diagnostic/v1"
MAX_EVIDENCE_OBJECTS = 500
ENGINE_PR = 13908
ENGINE_CREDIT = "Z-ApolloniusForge-914000-M7Q2 (ZAF-M7Q2)"
COMMERCIAL_CREDIT = "Z-CantorSpindle-913946-W7M2 (ZCS-W7M2)"
DIAGNOSTIC_CENTS = 350000
INTEGRATION_CENTS = 1000000
PRICE_STATUS = "PROPOSED_NOT_ACCEPTED"
STATES = ("REUSABLE", "STALE", "SCOPE_MISMATCH", "MISSING_OWNER", "INCOMPLETE")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DiagnosticError(ValueError):
    pass


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _counts_from_packet(packet: dict[str, Any]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    projection = packet.get("projection")
    if type(projection) is dict:
        raw_counts = projection.get("counts")
        if type(raw_counts) is dict:
            for state in STATES:
                value = raw_counts.get(state, 0)
                if type(value) is int:
                    counts[state] = value
            return counts
        rows = projection.get("results") or projection.get("rows")
        if type(rows) is list:
            for row in rows:
                if type(row) is dict and row.get("state") in counts:
                    counts[str(row["state"])] += 1
            return counts
    raw_counts = packet.get("counts")
    if type(raw_counts) is dict:
        for state in STATES:
            value = raw_counts.get(state, 0)
            if type(value) is not int or value < 0:
                raise DiagnosticError("engine:bad_counts")
            counts[state] = value
        return counts
    results = packet.get("results")
    if type(results) is list:
        for row in results:
            if type(row) is dict and row.get("state") in counts:
                counts[str(row["state"])] += 1
    return counts


def _reasons_from_packet(packet: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    projection = packet.get("projection") if type(packet.get("projection")) is dict else {}
    rows = None
    if type(projection) is dict:
        rows = projection.get("results") or projection.get("rows")
    if rows is None:
        rows = packet.get("results")
    if type(rows) is not list:
        return out
    for row in rows:
        if type(row) is not dict:
            continue
        state = row.get("state")
        if state == "REUSABLE":
            continue
        eid = row.get("evidence_id") or row.get("id") or ""
        reasons = row.get("reasons")
        if type(reasons) is list and reasons:
            for reason in reasons:
                if type(reason) is not str or not reason:
                    raise DiagnosticError("engine:bad_reason")
                out.append({"evidence_id": str(eid), "state": str(state), "reason": reason})
            continue
        reason = row.get("reason") or row.get("reason_code") or row.get("code") or "UNSPECIFIED"
        out.append({"evidence_id": str(eid), "state": str(state), "reason": str(reason)})
    return out


def _diagnostic_body(raw: Any, packet: dict[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict:
        raise DiagnosticError("root:object_required")
    evidence = raw.get("evidence")
    if type(evidence) is not list:
        raise DiagnosticError("evidence:list_required")
    if len(evidence) > MAX_EVIDENCE_OBJECTS:
        raise DiagnosticError("evidence:max_500")
    counts = _counts_from_packet(packet)
    objects_evaluated = sum(counts.values())
    if objects_evaluated != len(evidence):
        raise DiagnosticError("engine:count_mismatch")
    reasons = _reasons_from_packet(packet)
    engine_receipt = packet.get("receipt_sha256")
    input_sha = packet.get("input_sha256") or packet.get("normalized_input_sha256")
    projection_sha = packet.get("projection_sha256")
    for label, value in (("receipt", engine_receipt), ("input", input_sha), ("projection", projection_sha)):
        if type(value) is not str or not _SHA256_RE.fullmatch(value):
            raise DiagnosticError(f"engine:{label}_missing")
    return {
        "schema": SCHEMA,
        "authority": {
            "audit_opinion": False,
            "certification": False,
            "control_effectiveness": False,
            "customer_contact": False,
            "evidence_mutation": False,
            "outbound": False,
            "payment": False,
            "provider_mutation": False,
            "revenue_recognition": False,
        },
        "binding": {
            "engine_packet_schema": packet.get("schema"),
            "engine_pr": ENGINE_PR,
            "engine_receipt_sha256": engine_receipt,
            "input_sha256": input_sha,
            "projection_sha256": projection_sha,
        },
        "credit": {
            "commercial": COMMERCIAL_CREDIT,
            "engine": ENGINE_CREDIT,
        },
        "offer": {
            "diagnostic_cents": DIAGNOSTIC_CENTS,
            "integration_sprint_cents": INTEGRATION_CENTS,
            "integration_sprint_condition": "ONLY_AFTER_PAID_DIAGNOSTIC_ESTABLISHES_VALUE_AND_ACTUAL_ADAPTER_SCOPE",
            "free_custom_adapter": False,
            "status": PRICE_STATUS,
        },
        "scope": {
            "max_evidence_objects": MAX_EVIDENCE_OBJECTS,
            "objects_submitted": len(evidence),
            "objects_evaluated": objects_evaluated,
        },
        "summary": {
            "counts": counts,
            "non_reusable": reasons,
        },
    }


def compile_diagnostic(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise DiagnosticError("root:object_required")
    evidence = raw.get("evidence")
    if type(evidence) is not list:
        raise DiagnosticError("evidence:list_required")
    if len(evidence) > MAX_EVIDENCE_OBJECTS:
        raise DiagnosticError("evidence:max_500")
    try:
        packet = compile_packet(raw)
        verify_packet(packet)
    except GateError as exc:
        raise DiagnosticError(str(exc)) from exc
    body = _diagnostic_body(raw, packet)
    return {"diagnostic": body, "diagnostic_sha256": _sha(body), "engine_packet": packet}


def render_buyer_page(envelope: dict[str, Any]) -> str:
    if type(envelope) is not dict or "diagnostic" not in envelope:
        raise DiagnosticError("envelope:diagnostic_required")
    d = envelope["diagnostic"]
    counts = d["summary"]["counts"]
    lines = [
        "# Evidence Freshness Diagnostic",
        "",
        "Fixed-scope pre-assessment QA. Not an audit opinion, certification, or control-effectiveness rating.",
        "",
        f"- Objects evaluated: {d['scope']['objects_evaluated']} (ceiling {d['scope']['max_evidence_objects']})",
        f"- REUSABLE: {counts.get('REUSABLE', 0)}",
        f"- STALE: {counts.get('STALE', 0)}",
        f"- SCOPE_MISMATCH: {counts.get('SCOPE_MISMATCH', 0)}",
        f"- MISSING_OWNER: {counts.get('MISSING_OWNER', 0)}",
        f"- INCOMPLETE: {counts.get('INCOMPLETE', 0)}",
        f"- Engine receipt: `{d['binding']['engine_receipt_sha256']}`",
        f"- Diagnostic digest: `{envelope['diagnostic_sha256']}`",
        f"- Offer: $3,500 diagnostic / optional $10,000 integration sprint ({d['offer']['status']})",
        "- Integration sprint only after the paid diagnostic establishes value and actual adapter scope; no free custom adapter.",
        "",
        "## Non-reusable reasons",
    ]
    reasons = d["summary"]["non_reusable"]
    if not reasons:
        lines.append("- none")
    else:
        aggregate: dict[tuple[str, str], int] = {}
        for row in reasons:
            key = (row["state"], row["reason"])
            aggregate[key] = aggregate.get(key, 0) + 1
        for (state, reason), count in sorted(aggregate.items()):
            lines.append(f"- {state}: {reason} — {count}")
    lines.append("")
    lines.append("Credit: commercial ZCS-W7M2; engine ZAF-M7Q2 / #13908.")
    lines.append("")
    return "\n".join(lines)


def verify_diagnostic(envelope: Any) -> str:
    if type(envelope) is not dict:
        raise DiagnosticError("envelope:object_required")
    diagnostic = envelope.get("diagnostic")
    digest = envelope.get("diagnostic_sha256")
    packet = envelope.get("engine_packet")
    if type(diagnostic) is not dict or type(digest) is not str:
        raise DiagnosticError("envelope:fields")
    if _sha(diagnostic) != digest:
        raise DiagnosticError("diagnostic_digest_mismatch")
    if diagnostic.get("schema") != SCHEMA:
        raise DiagnosticError("schema")
    if diagnostic.get("offer", {}).get("status") != PRICE_STATUS:
        raise DiagnosticError("price_status")
    if diagnostic.get("offer", {}).get("diagnostic_cents") != DIAGNOSTIC_CENTS:
        raise DiagnosticError("diagnostic_price")
    if diagnostic.get("offer", {}).get("integration_sprint_cents") != INTEGRATION_CENTS:
        raise DiagnosticError("integration_price")
    if diagnostic.get("scope", {}).get("max_evidence_objects") != MAX_EVIDENCE_OBJECTS:
        raise DiagnosticError("scope_ceiling")
    auth = diagnostic.get("authority")
    if type(auth) is not dict or any(auth.values()):
        raise DiagnosticError("authority_escalation")
    if type(packet) is not dict:
        raise DiagnosticError("engine_packet_missing")
    try:
        verify_packet(packet)
    except GateError as exc:
        raise DiagnosticError(f"engine:{exc}") from exc
    bound = diagnostic.get("binding", {}).get("engine_receipt_sha256")
    if bound != packet.get("receipt_sha256"):
        raise DiagnosticError("receipt_binding")
    expected = _diagnostic_body(packet.get("input"), packet)
    if diagnostic != expected:
        raise DiagnosticError("diagnostic_packet_mismatch")
    return digest
