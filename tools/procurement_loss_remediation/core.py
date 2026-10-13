#!/usr/bin/env python3
"""Evidence-bound procurement outcome -> remediation compiler.

This layer composes the already-shipped ``tools.procurement_win_loss`` receipt.
It never derives buyer rationale from free text. Buyer-reason categories are
operator-supplied classifications bound to exact rationale statements that the
source receipt already verified; internal hypotheses occupy a separate
namespace and can never become buyer-stated facts.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from tools.procurement_win_loss import VerificationError, normalize_record, verify_record

INPUT_SCHEMA = "procurement-loss-remediation-input/v1"
RECEIPT_SCHEMA = "procurement-loss-remediation-receipt/v1"
BUYER_REASON_CATEGORIES = {
    "QUALIFICATION_EVIDENCE",
    "SCOPE_TECHNICAL_FIT",
    "PRICE_BASIS",
    "PROCESS_COMPLIANCE",
    "SCHEDULE_CAPACITY",
    "PARTNER_WORKSHARE",
    "OTHER_STATED",
}
CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
GAP_KINDS = {"CAPABILITY", "EVIDENCE", "PROCESS", "PARTNER", "SCHEDULE", "PRICING", "OTHER"}
RAILS = {
    "SOLICITATION_EVIDENCE",
    "RESPONSE_MODULE",
    "OPPORTUNITY_QUALIFICATION",
    "PARTNER_WORKSHARE",
    "DELIVERY_PROCESS",
    "PRICING_BASIS",
}
BASIS_TYPES = {"BUYER_REASON", "INTERNAL_HYPOTHESIS"}
MAX_REASONS = 64
MAX_HYPOTHESES = 64
MAX_GAPS = 128
MAX_TEXT = 400
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_EMAILISH_RE = re.compile(r"\S+@\S+")
_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://|\bwww\.")
# Intentionally catches common separator variants including slash/colon. This
# is a conservative private-text fence, not a phone-number parser.
_PHONEISH_RE = re.compile(r"(?<!\w)\+?\d[\d(). /:-]{6,}\d(?!\w)")


class RemediationError(ValueError):
    """Raised when a remediation packet is structurally unsafe."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RemediationError(f"{label} must be an object")
    return value


def _list(value: Any, label: str, maximum: int) -> list[Any]:
    if type(value) is not list:
        raise RemediationError(f"{label} must be a list")
    if len(value) > maximum:
        raise RemediationError(f"{label} exceeds {maximum} entries")
    return value


def _exact(obj: dict[str, Any], fields: set[str], label: str) -> None:
    extra = sorted(set(obj) - fields)
    missing = sorted(fields - set(obj))
    if extra:
        raise RemediationError(f"{label} contains unknown fields: {', '.join(extra)}")
    if missing:
        raise RemediationError(f"{label} is missing fields: {', '.join(missing)}")


def _text(value: Any, label: str, maximum: int = 160, *, private_safe: bool = False) -> str:
    if type(value) is not str:
        raise RemediationError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise RemediationError(f"{label} must not be empty")
    if len(text) > maximum:
        raise RemediationError(f"{label} exceeds {maximum} characters")
    if any(
        ord(ch) < 32
        or ord(ch) == 127
        or unicodedata.category(ch).startswith("C")
        or unicodedata.category(ch) in {"Zl", "Zp"}
        for ch in text
    ):
        raise RemediationError(f"{label} contains control characters")
    if private_safe:
        screened = unicodedata.normalize("NFKC", text)
        if _EMAILISH_RE.search(screened) or _URL_RE.search(screened) or _PHONEISH_RE.search(screened):
            raise RemediationError(f"{label} contains contact/locator-shaped data")
    return text


def _enum(value: Any, allowed: set[str], label: str) -> str:
    text = _text(value, label, 64)
    if text not in allowed:
        raise RemediationError(f"{label} is unsupported")
    return text


def _sha(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    if not _HEX64_RE.fullmatch(text):
        raise RemediationError(f"{label} must be lowercase SHA-256 hex")
    return text


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0 or value > 1_000_000:
        raise RemediationError(f"{label} must be a positive bounded integer")
    return value


def _verify_source(outcome_record: Any, outcome_receipt: Any) -> dict[str, Any]:
    try:
        return verify_record(outcome_record, outcome_receipt)
    except VerificationError as exc:
        raise RemediationError(f"source outcome receipt failed verification: {exc}") from exc


def normalize_input(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "record")
    _exact(
        obj,
        {"schema", "outcome_record", "outcome_receipt", "buyer_reason_mappings", "internal_hypotheses", "remediation_gaps"},
        "record",
    )
    if obj.get("schema") != INPUT_SCHEMA:
        raise RemediationError(f"record.schema must be {INPUT_SCHEMA}")

    raw_outcome_record = _dict(obj.get("outcome_record"), "record.outcome_record")
    outcome_receipt = _dict(obj.get("outcome_receipt"), "record.outcome_receipt")
    verified = _verify_source(raw_outcome_record, outcome_receipt)
    source_receipt_sha = _sha(outcome_receipt.get("receipt_sha256"), "record.outcome_receipt.receipt_sha256")
    if source_receipt_sha != verified["receipt_sha256"]:
        raise RemediationError("verified source receipt digest mismatch")
    # Canonicalize the already-verified source record before binding our own
    # input digest. This preserves order invariance inherited from the source
    # compiler instead of making raw caller evidence order authoritative here.
    outcome_record = normalize_record(raw_outcome_record)

    mappings_raw = _list(obj.get("buyer_reason_mappings"), "record.buyer_reason_mappings", MAX_REASONS)
    mappings: list[dict[str, Any]] = []
    seen_reason_ids: set[str] = set()
    for index, raw_mapping in enumerate(mappings_raw):
        label = f"record.buyer_reason_mappings[{index}]"
        row = _dict(raw_mapping, label)
        _exact(row, {"reason_id", "evidence_id", "source_digest_sha256", "category"}, label)
        reason_id = _text(row.get("reason_id"), f"{label}.reason_id")
        if reason_id in seen_reason_ids:
            raise RemediationError("duplicate buyer reason_id")
        seen_reason_ids.add(reason_id)
        mappings.append(
            {
                "reason_id": reason_id,
                "evidence_id": _text(row.get("evidence_id"), f"{label}.evidence_id"),
                "source_digest_sha256": _sha(row.get("source_digest_sha256"), f"{label}.source_digest_sha256"),
                "category": _enum(row.get("category"), BUYER_REASON_CATEGORIES, f"{label}.category"),
            }
        )
    mappings.sort(key=lambda row: row["reason_id"])

    hypotheses_raw = _list(obj.get("internal_hypotheses"), "record.internal_hypotheses", MAX_HYPOTHESES)
    hypotheses: list[dict[str, Any]] = []
    seen_hypothesis_ids: set[str] = set()
    for index, raw_hypothesis in enumerate(hypotheses_raw):
        label = f"record.internal_hypotheses[{index}]"
        row = _dict(raw_hypothesis, label)
        _exact(row, {"hypothesis_id", "text", "confidence", "evidence_basis"}, label)
        hypothesis_id = _text(row.get("hypothesis_id"), f"{label}.hypothesis_id")
        if hypothesis_id in seen_hypothesis_ids:
            raise RemediationError("duplicate hypothesis_id")
        seen_hypothesis_ids.add(hypothesis_id)
        refs_raw = _list(row.get("evidence_basis"), f"{label}.evidence_basis", 64)
        if not refs_raw:
            raise RemediationError(f"{label}.evidence_basis must not be empty")
        refs: list[dict[str, str]] = []
        seen_evidence_ids: set[str] = set()
        for ref_index, raw_ref in enumerate(refs_raw):
            ref_label = f"{label}.evidence_basis[{ref_index}]"
            ref = _dict(raw_ref, ref_label)
            _exact(ref, {"evidence_id", "source_digest_sha256", "observed_at"}, ref_label)
            evidence_id = _text(ref.get("evidence_id"), f"{ref_label}.evidence_id")
            if evidence_id in seen_evidence_ids:
                raise RemediationError(f"{label}.evidence_basis contains duplicate evidence_id")
            seen_evidence_ids.add(evidence_id)
            refs.append(
                {
                    "evidence_id": evidence_id,
                    "source_digest_sha256": _sha(ref.get("source_digest_sha256"), f"{ref_label}.source_digest_sha256"),
                    # Exact equality to the independently verified source fact
                    # below is the timestamp/currentness trust boundary here.
                    "observed_at": _text(ref.get("observed_at"), f"{ref_label}.observed_at", 64),
                }
            )
        refs.sort(key=lambda item: item["evidence_id"])
        hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "text": _text(row.get("text"), f"{label}.text", MAX_TEXT, private_safe=True),
                "confidence": _enum(row.get("confidence"), CONFIDENCE, f"{label}.confidence"),
                "evidence_basis": refs,
            }
        )
    hypotheses.sort(key=lambda row: row["hypothesis_id"])

    gaps_raw = _list(obj.get("remediation_gaps"), "record.remediation_gaps", MAX_GAPS)
    gaps: list[dict[str, Any]] = []
    seen_gap_versions: set[tuple[str, int]] = set()
    for index, raw_gap in enumerate(gaps_raw):
        label = f"record.remediation_gaps[{index}]"
        row = _dict(raw_gap, label)
        _exact(row, {"gap_id", "version", "gap_kind", "rail", "basis_type", "basis_id", "action"}, label)
        gap_id = _text(row.get("gap_id"), f"{label}.gap_id")
        version = _positive_int(row.get("version"), f"{label}.version")
        key = (gap_id, version)
        if key in seen_gap_versions:
            raise RemediationError("duplicate remediation gap id/version")
        seen_gap_versions.add(key)
        gaps.append(
            {
                "gap_id": gap_id,
                "version": version,
                "gap_kind": _enum(row.get("gap_kind"), GAP_KINDS, f"{label}.gap_kind"),
                "rail": _enum(row.get("rail"), RAILS, f"{label}.rail"),
                "basis_type": _enum(row.get("basis_type"), BASIS_TYPES, f"{label}.basis_type"),
                "basis_id": _text(row.get("basis_id"), f"{label}.basis_id"),
                "action": _text(row.get("action"), f"{label}.action", MAX_TEXT, private_safe=True),
            }
        )
    gaps.sort(key=lambda row: (row["gap_id"], row["version"]))

    return {
        "schema": INPUT_SCHEMA,
        "outcome_record": outcome_record,
        "outcome_receipt": outcome_receipt,
        "buyer_reason_mappings": mappings,
        "internal_hypotheses": hypotheses,
        "remediation_gaps": gaps,
    }


def derive_semantics(normalized: dict[str, Any]) -> dict[str, Any]:
    receipt = normalized["outcome_receipt"]
    source_statements = {row["evidence_id"]: row for row in receipt["rationale"]["statements"]}
    known_facts = {row["evidence_id"]: row for row in receipt["known_facts"]}
    hold_reasons: set[str] = set()
    buyer_reasons: list[dict[str, Any]] = []
    reason_ids: set[str] = set()
    mapped_evidence: set[str] = set()

    for mapping in normalized["buyer_reason_mappings"]:
        statement = source_statements.get(mapping["evidence_id"])
        if statement is None:
            hold_reasons.add(f"buyer_reason_not_source_attributed:{mapping['reason_id']}")
            continue
        if statement["source_digest_sha256"] != mapping["source_digest_sha256"]:
            hold_reasons.add(f"buyer_reason_source_digest_mismatch:{mapping['reason_id']}")
            continue
        if mapping["evidence_id"] in mapped_evidence:
            hold_reasons.add(f"buyer_reason_evidence_mapped_more_than_once:{mapping['evidence_id']}")
            continue
        mapped_evidence.add(mapping["evidence_id"])
        reason_ids.add(mapping["reason_id"])
        buyer_reasons.append(
            {
                "reason_id": mapping["reason_id"],
                "evidence_id": mapping["evidence_id"],
                "source_digest_sha256": mapping["source_digest_sha256"],
                "category": mapping["category"],
                "category_attribution": "OPERATOR_TAXONOMY_CLASSIFICATION",
                "statement": statement["text"],
                "statement_attribution": "BUYER_STATED_SOURCE_BOUND",
            }
        )

    missing_statement_ids = sorted(set(source_statements) - mapped_evidence)

    valid_hypothesis_ids: set[str] = set()
    hypotheses: list[dict[str, Any]] = []
    for hypothesis in normalized["internal_hypotheses"]:
        basis_valid = True
        bound_evidence: list[dict[str, Any]] = []
        for ref in hypothesis["evidence_basis"]:
            fact = known_facts.get(ref["evidence_id"])
            if fact is None:
                basis_valid = False
                hold_reasons.add(f"hypothesis_unknown_evidence:{hypothesis['hypothesis_id']}:{ref['evidence_id']}")
                continue
            if fact["source_digest_sha256"] != ref["source_digest_sha256"] or fact["observed_at"] != ref["observed_at"]:
                basis_valid = False
                hold_reasons.add(f"hypothesis_evidence_binding_mismatch:{hypothesis['hypothesis_id']}:{ref['evidence_id']}")
                continue
            if fact["evidence_status"] != "CURRENT":
                basis_valid = False
                hold_reasons.add(f"hypothesis_noncurrent_evidence:{hypothesis['hypothesis_id']}:{ref['evidence_id']}")
                continue
            if fact["mapped_outcome"] == "UNKNOWN":
                basis_valid = False
                hold_reasons.add(f"hypothesis_nonterminal_evidence:{hypothesis['hypothesis_id']}:{ref['evidence_id']}")
                continue
            bound_evidence.append(
                {
                    "evidence_id": fact["evidence_id"],
                    "source_kind": fact["source_kind"],
                    "source_digest_sha256": fact["source_digest_sha256"],
                    "observed_at": fact["observed_at"],
                    "evidence_status": fact["evidence_status"],
                    "decision_signal": fact["decision_signal"],
                    "mapped_outcome": fact["mapped_outcome"],
                }
            )
        if basis_valid:
            valid_hypothesis_ids.add(hypothesis["hypothesis_id"])
        hypotheses.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "text": hypothesis["text"],
                "confidence": hypothesis["confidence"],
                "evidence_basis": hypothesis["evidence_basis"],
                "bound_evidence": sorted(bound_evidence, key=lambda item: item["evidence_id"]),
                "basis_valid": basis_valid,
                "attribution": "INTERNAL_HYPOTHESIS_NOT_BUYER_FACT",
            }
        )

    gaps: list[dict[str, Any]] = []
    for gap in normalized["remediation_gaps"]:
        valid_basis = (
            gap["basis_id"] in reason_ids
            if gap["basis_type"] == "BUYER_REASON"
            else gap["basis_id"] in valid_hypothesis_ids
        )
        if not valid_basis:
            hold_reasons.add(f"gap_unbound_basis:{gap['gap_id']}@{gap['version']}")
        gaps.append({**gap, "basis_valid": valid_basis})

    source_hold = receipt["outcome"] == "UNKNOWN" or bool(receipt["hold_reasons"])
    if source_hold:
        status = "HOLD_SOURCE"
    elif hold_reasons:
        status = "HOLD_CONTRADICTION"
    elif missing_statement_ids:
        status = "HOLD_UNATTRIBUTED_REASON"
        hold_reasons.add("source_rationale_requires_category_binding")
    elif gaps:
        status = "ACTIONABLE_GAPS"
    else:
        status = "NO_ACTIONABLE_GAP"

    return {
        "status": status,
        "source_outcome": receipt["outcome"],
        "source_hold_reasons": list(receipt["hold_reasons"]),
        "buyer_reasons": sorted(buyer_reasons, key=lambda row: row["reason_id"]),
        "internal_hypotheses": sorted(hypotheses, key=lambda row: row["hypothesis_id"]),
        "remediation_gaps": gaps,
        "unattributed_source_statement_ids": missing_statement_ids,
        "hold_reasons": sorted(hold_reasons),
    }


def compile_plan(raw: Any) -> dict[str, Any]:
    normalized = normalize_input(raw)
    semantics = derive_semantics(normalized)
    source_receipt = normalized["outcome_receipt"]
    source_evidence = [
        {
            "evidence_id": row["evidence_id"],
            "source_kind": row["source_kind"],
            "source_digest_sha256": row["source_digest_sha256"],
            "observed_at": row["observed_at"],
            "evidence_status": row["evidence_status"],
            "decision_signal": row["decision_signal"],
            "mapped_outcome": row["mapped_outcome"],
        }
        for row in source_receipt["known_facts"]
    ]
    unsigned = {
        "schema": RECEIPT_SCHEMA,
        "opportunity_id": source_receipt["opportunity_id"],
        "compiled_at": source_receipt["compiled_at"],
        "source_receipt_sha256": source_receipt["receipt_sha256"],
        "source_outcome": semantics["source_outcome"],
        "source_hold_reasons": semantics["source_hold_reasons"],
        "source_evidence": source_evidence,
        "status": semantics["status"],
        "buyer_reasons": semantics["buyer_reasons"],
        "internal_hypotheses": semantics["internal_hypotheses"],
        "remediation_gaps": semantics["remediation_gaps"],
        "unattributed_source_statement_ids": semantics["unattributed_source_statement_ids"],
        "hold_reasons": semantics["hold_reasons"],
        "authority": {
            "buyer_contact_authorized": False,
            "debrief_request_authorized": False,
            "outbound_authorized": False,
            "provider_mutation_authorized": False,
            "contract_authorized": False,
            "payment_authorized": False,
            "cash_recognized": False,
            "revenue_recognized": False,
            "buyer_causal_inference_authorized": False,
        },
        "normalized_input_sha256": digest(normalized),
    }
    return {**unsigned, "receipt_sha256": digest(unsigned)}
