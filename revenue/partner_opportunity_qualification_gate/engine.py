from __future__ import annotations

import hashlib
from typing import Any

from revenue.procurement_runway_gate.engine import (
    canonical_json_bytes as runway_bytes,
    compile_gate as compile_runway,
    make_receipt as runway_receipt,
    validate_input as normalize_runway,
    verify_bundle as verify_runway,
)

from .validation import QualificationError, SCHEMA, canonical_json_bytes, digest, normalize_input

OUTPUT_SCHEMA = "partner-opportunity-qualification-output/v1"
RECEIPT_SCHEMA = "partner-opportunity-qualification-receipt/v1"
READY = {"READY_FOR_MUSE_ELECTION_ONLY", "READY_FOR_CAPACITY_MUSE_ELECTION_ONLY"}
AUTHORITY_FALSE = {
    "partner_contact_authorized": False,
    "buyer_contact_authorized": False,
    "muse_election_granted": False,
    "account_registration_authorized": False,
    "eligibility_certified": False,
    "portal_submission_authorized": False,
    "signature_authorized": False,
    "contract_authorized": False,
    "award_inferred": False,
    "payment_authorized": False,
    "cash_received": False,
    "revenue_recognized": False,
}

_AUTHORITY_KEYS = tuple(AUTHORITY_FALSE)

def _fresh_false_authority(_keys=_AUTHORITY_KEYS):
    return {key: False for key in _keys}


def _state(partner, gates, sources, runway, as_of, selected_timing, controls_current):
    timing_status = selected_timing.get(partner["name"])
    if runway["runway_state"] not in {"READY", "ASK_CAPACITY_FIRST"} or timing_status is None:
        return "HOLD_RUNWAY", [f"runway state/selection does not admit partner: {runway['runway_state']}"]
    if timing_status == "EXPLICIT_MISS":
        return "HOLD_RUNWAY", ["candidate upstream timing status is EXPLICIT_MISS"]
    if timing_status not in {"EXPLICIT_FIT", "EXPLICIT_NO_KNOWN_CONFLICT", "UNKNOWN_CAPACITY"}:
        return "HOLD_RUNWAY", [f"candidate upstream timing status is unsupported: {timing_status}"]
    if runway["contact_state"] != "ELIGIBLE_FOR_SEPARATE_MUSE_ELECTION_ONLY":
        return "HOLD_CONTACT_POLICY", [f"upstream contact policy is {runway['contact_state']}"]
    if not controls_current:
        return "HOLD_SOURCE", ["one or more solicitation-control sources are not CURRENT"]
    reg = partner["registration"]
    if reg["state"] in {"UNKNOWN", "CLOSED"}:
        return "HOLD_REGISTRATION", [f"registration state is {reg['state']}"]
    if any(sources[r["source_id"]]["status"] != "CURRENT" for r in reg["requirement_refs"] + reg["evidence_refs"]):
        return "HOLD_REGISTRATION", ["registration evidence is not CURRENT"]
    if reg["state"] == "OPEN" and reg["deadline"] is not None and reg["deadline"] <= as_of:
        return "HOLD_REGISTRATION", [f"registration deadline {reg['deadline']} is not after as_of {as_of}"]

    blocking, later = [], []
    for disp in partner["gate_dispositions"]:
        gate = gates[disp["gate_id"]]
        stale = any(sources[r["source_id"]]["status"] != "CURRENT" for r in disp["evidence_refs"])
        if disp["state"] != "SATISFIED" or stale:
            token = f"{disp['gate_id']}:{'STALE_EVIDENCE' if stale else disp['state']}"
            (blocking if gate["phase"] == "PRE_OUTREACH" else later).append(token)
    later = [f"later:{x}" for x in sorted(later)]
    if blocking:
        return "HOLD_HARD_GATE", sorted(blocking) + later
    if partner["paid_workshare"]["state"] != "DEFINED":
        return "HOLD_NO_PAID_SEAM", ["paid TJLabs workshare is undefined"] + later
    if timing_status == "UNKNOWN_CAPACITY":
        return "READY_FOR_CAPACITY_MUSE_ELECTION_ONLY", ["qualification gates clear; this candidate upstream capacity remains unverified"] + later
    return "READY_FOR_MUSE_ELECTION_ONLY", ["runway, contact policy, registration, pre-outreach gates, and paid seam are bounded"] + later


def _validate_disposition_source_binding(partner: dict[str, Any], gates: dict[str, dict[str, Any]]) -> None:
    for disposition in partner["gate_dispositions"]:
        if disposition["state"] == "UNKNOWN":
            continue
        gate = gates[disposition["gate_id"]]
        gate_sources = {(ref["source_id"], ref["source_sha256"]) for ref in gate["source_refs"]}
        disposition_sources = {(ref["source_id"], ref["source_sha256"]) for ref in disposition["evidence_refs"]}
        if not disposition_sources or not disposition_sources.issubset(gate_sources):
            raise QualificationError(
                f"partner {partner['name']} gate {disposition['gate_id']} disposition evidence "
                "must be wholly bound in that gate's source_refs"
            )


def compile_qualification(raw: Any) -> dict[str, Any]:
    _authority_factory = lambda: {key: False for key in ("partner_contact_authorized","buyer_contact_authorized","muse_election_granted","account_registration_authorized","eligibility_certified","portal_submission_authorized","signature_authorized","contract_authorized","award_inferred","payment_authorized","cash_received","revenue_recognized")}
    doc = normalize_input(raw)
    try:
        runway_doc = normalize_runway(doc["runway_input"])
        upstream = compile_runway(runway_doc)
        upstream_receipt = runway_receipt(upstream)
        verify_runway(runway_doc, upstream, upstream_receipt)
    except Exception as exc:
        raise QualificationError("runway bundle failed semantic recompilation") from exc
    rows = upstream.get("opportunities")
    if type(rows) is not list or len(rows) != 1 or rows[0].get("id") != doc["opportunity_id"] or upstream.get("as_of") != doc["as_of"]:
        raise QualificationError("runway output identity/as_of mismatch")
    runway = rows[0]
    selected_rows = runway.get("selected_partners")
    if type(selected_rows) is not list:
        raise QualificationError("runway selected_partners malformed")
    selected_timing = {}
    for index, row in enumerate(selected_rows):
        if type(row) is not dict or type(row.get("name")) is not str or type(row.get("timing_status")) is not str:
            raise QualificationError(f"runway selected_partners[{index}] malformed")
        if row["name"] in selected_timing:
            raise QualificationError("runway selected_partners contains duplicate partner name")
        selected_timing[row["name"]] = row["timing_status"]
    sources = {s["source_id"]: s for s in doc["sources"]}
    controls = [s for s in doc["sources"] if s["kind"] == "SOLICITATION_CONTROL"]
    if not controls:
        raise QualificationError("at least one SOLICITATION_CONTROL source is required")
    if not all(s["url"] in set(runway.get("source_urls", [])) for s in controls):
        raise QualificationError("solicitation-control source URL is not bound by upstream runway source_urls")
    gates = {g["gate_id"]: g for g in doc["hard_gates"]}
    partner_rows = []
    for partner in doc["partners"]:
        _validate_disposition_source_binding(partner, gates)
        state, reasons = _state(partner, gates, sources, runway, doc["as_of"], selected_timing, all(s["status"] == "CURRENT" for s in controls))
        partner_rows.append({
            "name": partner["name"],
            "state": state,
            "reasons": reasons,
            "registration": partner["registration"],
            "gate_dispositions": partner["gate_dispositions"],
            "paid_workshare": partner["paid_workshare"],
            **_authority_factory(),
        })
    binding = {
        "runway_input_sha256": hashlib.sha256(runway_bytes(runway_doc)).hexdigest(),
        "runway_output_schema": upstream.get("schema"),
        "runway_output_sha256": hashlib.sha256(runway_bytes(upstream)).hexdigest(),
        "runway_receipt_sha256": digest(upstream_receipt),
        "runway_state": runway["runway_state"],
        "contact_state": runway["contact_state"],
    }
    return {
        "schema": OUTPUT_SCHEMA,
        "input_schema": SCHEMA,
        "as_of": doc["as_of"],
        "opportunity_id": doc["opportunity_id"],
        "runway_binding": binding,
        "sources": doc["sources"],
        "hard_gates": doc["hard_gates"],
        "partners": partner_rows,
        "ready_partner_names": sorted((r["name"] for r in partner_rows if r["state"] in READY), key=lambda n: (n.casefold(), n)),
        **_authority_factory(),
    }


def make_receipt(raw_input: Any, output: dict[str, Any]) -> dict[str, Any]:
    _authority_factory = lambda: {key: False for key in ("partner_contact_authorized","buyer_contact_authorized","muse_election_granted","account_registration_authorized","eligibility_certified","portal_submission_authorized","signature_authorized","contract_authorized","award_inferred","payment_authorized","cash_received","revenue_recognized")}
    doc = normalize_input(raw_input)
    semantic = {k: v for k, v in doc.items() if k != "runway_input"}
    semantic["runway_binding"] = output["runway_binding"]
    return {
        "schema": RECEIPT_SCHEMA,
        "semantic_input_sha256": digest(semantic),
        "output_sha256": digest(output),
        "opportunity_id": doc["opportunity_id"],
        "as_of": doc["as_of"],
        "runway_input_sha256": output["runway_binding"]["runway_input_sha256"],
        "runway_output_sha256": output["runway_binding"]["runway_output_sha256"],
        "runway_receipt_sha256": output["runway_binding"]["runway_receipt_sha256"],
        **_authority_factory(),
    }


def verify_bundle(raw_input: Any, output: Any, receipt: Any) -> None:
    names = (
        "partner_contact_authorized", "buyer_contact_authorized",
        "muse_election_granted", "account_registration_authorized",
        "eligibility_certified", "portal_submission_authorized",
        "signature_authorized", "contract_authorized", "award_inferred",
        "payment_authorized", "cash_received", "revenue_recognized",
    )
    if type(output) is not dict or type(receipt) is not dict:
        raise QualificationError("bundle objects must be exact dicts")
    rows = output.get("partners")
    if type(rows) is not list:
        raise QualificationError("output partners must be an exact list")
    for where, row in [("output", output), ("receipt", receipt)] + [
        (f"partner[{index}]", row) for index, row in enumerate(rows)
    ]:
        if type(row) is not dict:
            raise QualificationError(f"{where} must be an exact dict")
        for key in names:
            if key not in row or type(row[key]) is not bool or row[key] is not False:
                raise QualificationError(f"{where} authority {key} must be exact false")
    expected = compile_qualification(raw_input)
    if output != expected:
        raise QualificationError("output does not match deterministic recompilation")
    if receipt != make_receipt(raw_input, expected):
        raise QualificationError("receipt does not match deterministic recompilation")
