from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

SCHEMA = "tjlabs.umissouri-27-0012-finance-pursuit/v1"
PARTNER_SCHEMA = "tjlabs.umissouri-27-0012-partners/v1"
CASE_SCHEMA = "tjlabs.umissouri-27-0012-reconciliation-case/v1"
BUNDLE_SCHEMA = "tjlabs.umissouri-27-0012-finance-evidence-bundle/v1"

SOLICITATION_ID = "27-0012"
BUYER = "University of Missouri System"
TITLE = "Payables Program and Merchant Services"
DUE_UTC = "2026-09-25T19:00:00Z"
QUESTION_CUTOFF_UTC = "2026-09-10T19:00:00Z"
MAX_SOURCE_AGE_SECONDS = 48 * 60 * 60

AUTHORITY_FALSE = {
    "buyer_contact_authorized": False,
    "partner_contact_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "banking_authorized": False,
    "merchant_acquiring_authorized": False,
    "card_issuance_authorized": False,
    "payment_authorized": False,
    "production_erp_write_authorized": False,
    "compliance_certification_authorized": False,
    "revenue_recognized": False,
}

TERMINAL_DECISIONS = (
    "EVIDENCE_READY",
    "REJECT_SENSITIVE_DATA",
    "HOLD_MISSING_SETTLEMENT",
    "HOLD_MERCHANT_TOTAL_MISMATCH",
    "HOLD_GL_MAPPING",
    "HOLD_CHARGEBACK_EXCEPTION",
    "HOLD_PAYABLES_SUPPLIER",
    "HOLD_FUTURE_ERP",
    "HOLD_AUDIT_CHAIN",
    "HOLD_STALE_EVIDENCE",
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class ContractError(ValueError):
    pass


def _reject_constant(
    value: str,
    _error=ContractError,
) -> None:
    raise _error(f"non-finite JSON constant rejected: {value}")


def strict_loads(
    text: str,
    _json_loads=json.loads,
    _reject_constant_fn=_reject_constant,
    _json_decode_error=json.JSONDecodeError,
    _error=ContractError,
) -> Any:
    # Strict ingress is a reviewed generation: later rebinding of public module
    # names must not weaken duplicate-key or non-finite rejection.
    if type(text) is not str:
        raise _error("JSON input must be str")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise _error(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        return _json_loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=_reject_constant_fn,
        )
    except _error:
        raise
    except (TypeError, ValueError, _json_decode_error) as exc:
        raise _error(f"invalid JSON: {exc}") from exc


def strict_load(
    path,
    _strict_loads_fn=strict_loads,
    _open_fn=open,
) -> Any:
    with _open_fn(path, "r", encoding="utf-8") as handle:
        return _strict_loads_fn(handle.read())


def canonical_json(
    value: Any,
    _json_dumps=json.dumps,
    _error=ContractError,
) -> str:
    try:
        return _json_dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _error(f"not canonicalizable: {exc}") from exc


def sha256_hex(text: str, _sha256=sha256) -> str:
    return _sha256(text.encode("utf-8")).hexdigest()


def _add_receipt(
    value: dict[str, Any],
    _sha256_hex_fn=sha256_hex,
    _canonical_json_fn=canonical_json,
) -> dict[str, Any]:
    base = dict(value)
    base.pop("receipt_sha256", None)
    base["receipt_sha256"] = _sha256_hex_fn(_canonical_json_fn(base))
    return base


def _exact(
    obj: Any,
    keys: set[str],
    label: str,
    _error=ContractError,
) -> dict[str, Any]:
    if type(obj) is not dict:
        raise _error(f"{label}: object required")
    got = set(obj)
    if got != keys:
        raise _error(
            f"{label}: exact keys required; "
            f"missing={sorted(keys - got)} extra={sorted(got - keys)}"
        )
    return obj


def _text(
    value: Any,
    label: str,
    max_len: int = 1024,
    _error=ContractError,
) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise _error(f"{label}: bounded non-empty string required")
    return value


def _id(
    value: Any,
    label: str,
    _text_fn=_text,
    _id_re=_ID,
    _error=ContractError,
) -> str:
    value = _text_fn(value, label, 128)
    if not _id_re.fullmatch(value):
        raise _error(f"{label}: invalid identifier")
    return value


def _bool(
    value: Any,
    label: str,
    _error=ContractError,
) -> bool:
    if type(value) is not bool:
        raise _error(f"{label}: bool required")
    return value


def _int(
    value: Any,
    label: str,
    low: int = 0,
    high: int = 10**15,
    _error=ContractError,
) -> int:
    if type(value) is not int or not (low <= value <= high):
        raise _error(f"{label}: integer in [{low},{high}] required")
    return value


def _utc(
    value: Any,
    label: str,
    _text_fn=_text,
    _datetime_fromisoformat=datetime.fromisoformat,
    _timezone_utc=timezone.utc,
    _error=ContractError,
) -> datetime:
    value = _text_fn(value, label, 40)
    if not value.endswith("Z"):
        raise _error(f"{label}: UTC Z timestamp required")
    try:
        parsed = _datetime_fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label}: invalid timestamp") from exc
    if parsed.tzinfo != _timezone_utc:
        raise _error(f"{label}: UTC required")
    return parsed


def _https(
    value: Any,
    label: str,
    _text_fn=_text,
    _error=ContractError,
) -> str:
    value = _text_fn(value, label, 2048)
    if not value.startswith("https://"):
        raise _error(f"{label}: https URL required")
    return value


def _validate_authority(
    obj: Any,
    label: str,
    _exact_fn=_exact,
    _bool_fn=_bool,
    _error=ContractError,
) -> None:
    # Literal field generation is deliberate: exported AUTHORITY_FALSE is an
    # operator-facing compatibility view, never a production policy root.
    fields = (
        "buyer_contact_authorized",
        "partner_contact_authorized",
        "submission_authorized",
        "contract_acceptance_authorized",
        "banking_authorized",
        "merchant_acquiring_authorized",
        "card_issuance_authorized",
        "payment_authorized",
        "production_erp_write_authorized",
        "compliance_certification_authorized",
        "revenue_recognized",
    )
    authority = _exact_fn(obj, set(fields), label)
    for field in fields:
        if _bool_fn(authority[field], f"{label}.{field}") is not False:
            raise _error(f"{label}.{field}: must remain false")


def validate_manifest(
    manifest: Any,
    trusted_as_of: str,
    _add_receipt_fn=_add_receipt,
    _exact_fn=_exact,
    _utc_fn=_utc,
    _https_fn=_https,
    _bool_fn=_bool,
    _int_fn=_int,
    _text_fn=_text,
    _validate_authority_fn=_validate_authority,
    _error=ContractError,
    _schema=SCHEMA,
) -> dict[str, Any]:
    doc = _exact_fn(
        manifest,
        {
            "schema",
            "solicitation",
            "source_evidence",
            "buyer_packet",
            "requirements",
            "commercial_offer",
            "authority",
        },
        "manifest",
    )
    if doc["schema"] != _schema:
        raise _error("manifest.schema: unsupported")

    sol = _exact_fn(
        doc["solicitation"],
        {"id", "buyer", "title", "due_utc", "question_cutoff_utc"},
        "manifest.solicitation",
    )
    if (
        sol["id"] != "27-0012"
        or sol["buyer"] != "University of Missouri System"
        or sol["title"] != "Payables Program and Merchant Services"
    ):
        raise _error("manifest.solicitation: solicitation identity drift")
    if (
        sol["due_utc"] != "2026-09-25T19:00:00Z"
        or sol["question_cutoff_utc"] != "2026-09-10T19:00:00Z"
    ):
        raise _error("manifest.solicitation: deadline drift")

    as_of = _utc_fn(trusted_as_of, "trusted_as_of")
    source = _exact_fn(
        doc["source_evidence"],
        {"notice", "scope"},
        "manifest.source_evidence",
    )
    source_fresh = True
    for key in ("notice", "scope"):
        row = _exact_fn(
            source[key],
            {"url", "captured_at_utc", "source_class"},
            f"manifest.source_evidence.{key}",
        )
        _https_fn(row["url"], f"manifest.source_evidence.{key}.url")
        if row["source_class"] not in {
            "SECONDARY_PUBLIC_INDEX",
            "PROVIDER_PUBLIC",
            "BUYER_PUBLIC",
        }:
            raise _error(
                f"manifest.source_evidence.{key}.source_class: unsupported"
            )
        captured = _utc_fn(
            row["captured_at_utc"],
            f"manifest.source_evidence.{key}.captured_at_utc",
        )
        if captured > as_of:
            raise _error("manifest.source_evidence: future capture")
        if int((as_of - captured).total_seconds()) > 48 * 60 * 60:
            source_fresh = False

    buyer_packet = _exact_fn(
        doc["buyer_packet"],
        {"retained", "sha256", "authority"},
        "manifest.buyer_packet",
    )
    retained = _bool_fn(
        buyer_packet["retained"], "manifest.buyer_packet.retained"
    )
    digest = buyer_packet["sha256"]
    if retained:
        raise _error(
            "manifest.buyer_packet.retained: verifier-owned packet bytes "
            "are required; caller metadata cannot mint buyer authority"
        )
    if digest is not None or buyer_packet["authority"] != "NOT_RETAINED":
        raise _error(
            "manifest.buyer_packet: absent packet must remain unasserted"
        )

    req = _exact_fn(
        doc["requirements"],
        {
            "merchant_services",
            "payables_program",
            "current_peoplesoft_integration",
            "future_erp_support",
            "reconciliation_reporting",
            "fraud_liability_controls",
            "commercial_card_epayables",
            "security_questionnaires",
            "accessibility_evidence",
        },
        "manifest.requirements",
    )
    for field in req:
        if _bool_fn(req[field], f"manifest.requirements.{field}") is not True:
            raise _error(
                f"manifest.requirements.{field}: requirement cannot be weakened"
            )

    offer = _exact_fn(
        doc["commercial_offer"],
        {
            "state",
            "fixed_fee_usd_cents",
            "optional_cutover_usd_cents",
            "name",
            "external_send_authorized",
        },
        "manifest.commercial_offer",
    )
    if offer["state"] != "PROPOSED_NOT_ACCEPTED":
        raise _error(
            "manifest.commercial_offer.state: must remain PROPOSED_NOT_ACCEPTED"
        )
    if (
        _int_fn(
            offer["fixed_fee_usd_cents"],
            "manifest.commercial_offer.fixed_fee_usd_cents",
            1,
            100_000_000,
        )
        != 1_800_000
    ):
        raise _error(
            "manifest.commercial_offer.fixed_fee_usd_cents: reference fee drift"
        )
    if (
        _int_fn(
            offer["optional_cutover_usd_cents"],
            "manifest.commercial_offer.optional_cutover_usd_cents",
            0,
            100_000_000,
        )
        != 600_000
    ):
        raise _error(
            "manifest.commercial_offer.optional_cutover_usd_cents: reference option drift"
        )
    if (
        _text_fn(offer["name"], "manifest.commercial_offer.name", 180)
        != "Payables and Merchant Reconciliation Acceptance Workshare"
    ):
        raise _error(
            "manifest.commercial_offer.name: exact bounded offer required"
        )
    if (
        _bool_fn(
            offer["external_send_authorized"],
            "manifest.commercial_offer.external_send_authorized",
        )
        is not False
    ):
        raise _error(
            "manifest.commercial_offer.external_send_authorized: must remain false"
        )

    _validate_authority_fn(doc["authority"], "manifest.authority")

    packet = {
        "schema": _schema,
        "solicitation_id": "27-0012",
        "source_authority_state": (
            "BUYER_PACKET_RETAINED"
            if retained
            else "HOLD_BUYER_PACKET_REQUIRED"
        ),
        "teaming_build_state": (
            "HOLD_RESPONSE_WINDOW"
            if as_of >= _utc_fn("2026-09-25T19:00:00Z", "due")
            else (
                "READY_FOR_PARTNER_REVIEW"
                if source_fresh
                else "HOLD_SOURCE_REFRESH_REQUIRED"
            )
        ),
        "direct_prime_state": "HOLD_PRIME_CAPABILITY_REQUIRED",
        "commercial_offer_state": offer["state"],
        "fixed_fee_usd_cents": offer["fixed_fee_usd_cents"],
        "optional_cutover_usd_cents": offer["optional_cutover_usd_cents"],
        "buyer_contact_authorized": False,
        "partner_contact_authorized": False,
        "submission_authorized": False,
        "contract_acceptance_authorized": False,
        "banking_authorized": False,
        "merchant_acquiring_authorized": False,
        "card_issuance_authorized": False,
        "payment_authorized": False,
        "production_erp_write_authorized": False,
        "compliance_certification_authorized": False,
        "revenue_recognized": False,
    }
    return _add_receipt_fn(packet)


def evaluate_partner(
    candidate: Any,
    _add_receipt_fn=_add_receipt,
    _exact_fn=_exact,
    _id_fn=_id,
    _text_fn=_text,
    _https_fn=_https,
    _bool_fn=_bool,
    _error=ContractError,
    _partner_schema=PARTNER_SCHEMA,
) -> dict[str, Any]:
    row = _exact_fn(
        candidate,
        {
            "partner_id",
            "name",
            "evidence_url",
            "evidence_class",
            "public_merchant_capability",
            "public_payables_or_card_capability",
            "public_higher_ed_or_public_sector_fit",
            "peoplesoft_or_erp_fit_confirmed",
            "rfp_participation_confirmed",
            "contact_authorized",
            "evidence_note",
        },
        "partner",
    )
    partner_id = _id_fn(row["partner_id"], "partner.partner_id")
    name = _text_fn(row["name"], "partner.name", 200)
    _https_fn(row["evidence_url"], "partner.evidence_url")
    if row["evidence_class"] not in {"BUYER_PUBLIC", "PROVIDER_PUBLIC"}:
        raise _error("partner.evidence_class: unsupported")
    merchant = _bool_fn(
        row["public_merchant_capability"],
        "partner.public_merchant_capability",
    )
    payables = _bool_fn(
        row["public_payables_or_card_capability"],
        "partner.public_payables_or_card_capability",
    )
    sector = _bool_fn(
        row["public_higher_ed_or_public_sector_fit"],
        "partner.public_higher_ed_or_public_sector_fit",
    )
    erp = _bool_fn(
        row["peoplesoft_or_erp_fit_confirmed"],
        "partner.peoplesoft_or_erp_fit_confirmed",
    )
    rfp = _bool_fn(
        row["rfp_participation_confirmed"],
        "partner.rfp_participation_confirmed",
    )
    if _bool_fn(row["contact_authorized"], "partner.contact_authorized") is not False:
        raise _error("partner.contact_authorized: must remain false")
    _text_fn(row["evidence_note"], "partner.evidence_note", 1000)

    public_fit = merchant and payables and sector
    if not public_fit:
        status = "HOLD_PUBLIC_FIT_GAP"
    elif not erp:
        status = "RESEARCH_ERP_INTEGRATION"
    else:
        status = "QUALIFIED_FOR_HUMAN_PARTNER_REVIEW"

    return _add_receipt_fn(
        {
            "schema": _partner_schema,
            "partner_id": partner_id,
            "name": name,
            "status": status,
            "rfp_participation_confirmed": rfp,
            "contact_authorized": False,
            "selection_authorized": False,
            "external_send_authorized": False,
        }
    )


def evaluate_partners(
    document: Any,
    _evaluate_partner_fn=evaluate_partner,
    _add_receipt_fn=_add_receipt,
    _exact_fn=_exact,
    _error=ContractError,
    _partner_schema=PARTNER_SCHEMA,
) -> dict[str, Any]:
    doc = _exact_fn(document, {"schema", "candidates"}, "partners")
    if doc["schema"] != _partner_schema:
        raise _error("partners.schema: unsupported")
    rows = doc["candidates"]
    if type(rows) is not list or not (3 <= len(rows) <= 12):
        raise _error("partners.candidates: 3..12 candidates required")

    seen = set()
    results = []
    for raw in rows:
        result = _evaluate_partner_fn(raw)
        if result["partner_id"] in seen:
            raise _error("partners: duplicate partner_id")
        seen.add(result["partner_id"])
        results.append(result)

    return _add_receipt_fn(
        {
            "schema": _partner_schema,
            "candidate_count": len(results),
            "candidates": results,
            "selection_authorized": False,
            "external_send_authorized": False,
        }
    )


def evaluate_reconciliation_case(
    case: Any,
    trusted_as_of: str,
    _add_receipt_fn=_add_receipt,
    _exact_fn=_exact,
    _id_fn=_id,
    _bool_fn=_bool,
    _int_fn=_int,
    _utc_fn=_utc,
    _error=ContractError,
    _case_schema=CASE_SCHEMA,
) -> dict[str, Any]:
    row = _exact_fn(
        case,
        {
            "schema",
            "case_id",
            "merchant_id",
            "settlement_file_present",
            "processor_total_cents",
            "erp_total_cents",
            "gl_mapping_complete",
            "unresolved_chargeback_count",
            "payables_supplier_match",
            "future_erp_contract_evidenced",
            "audit_chain_complete",
            "sensitive_cardholder_data_present",
            "observed_at_utc",
        },
        "case",
    )
    if row["schema"] != _case_schema:
        raise _error("case.schema: unsupported")

    case_id = _id_fn(row["case_id"], "case.case_id")
    merchant_id = _id_fn(row["merchant_id"], "case.merchant_id")
    settlement = _bool_fn(
        row["settlement_file_present"], "case.settlement_file_present"
    )
    processor = _int_fn(row["processor_total_cents"], "case.processor_total_cents")
    erp = _int_fn(row["erp_total_cents"], "case.erp_total_cents")
    gl = _bool_fn(row["gl_mapping_complete"], "case.gl_mapping_complete")
    chargebacks = _int_fn(
        row["unresolved_chargeback_count"],
        "case.unresolved_chargeback_count",
        0,
        1_000_000,
    )
    supplier = _bool_fn(
        row["payables_supplier_match"], "case.payables_supplier_match"
    )
    future_erp = _bool_fn(
        row["future_erp_contract_evidenced"],
        "case.future_erp_contract_evidenced",
    )
    audit = _bool_fn(row["audit_chain_complete"], "case.audit_chain_complete")
    sensitive = _bool_fn(
        row["sensitive_cardholder_data_present"],
        "case.sensitive_cardholder_data_present",
    )
    observed = _utc_fn(row["observed_at_utc"], "case.observed_at_utc")
    as_of = _utc_fn(trusted_as_of, "trusted_as_of")
    if observed > as_of:
        raise _error("case.observed_at_utc: future evidence")
    age_seconds = int((as_of - observed).total_seconds())

    if sensitive:
        decision = "REJECT_SENSITIVE_DATA"
    elif age_seconds > 7 * 24 * 3600:
        decision = "HOLD_STALE_EVIDENCE"
    elif not settlement:
        decision = "HOLD_MISSING_SETTLEMENT"
    elif processor != erp:
        decision = "HOLD_MERCHANT_TOTAL_MISMATCH"
    elif not gl:
        decision = "HOLD_GL_MAPPING"
    elif chargebacks:
        decision = "HOLD_CHARGEBACK_EXCEPTION"
    elif not supplier:
        decision = "HOLD_PAYABLES_SUPPLIER"
    elif not future_erp:
        decision = "HOLD_FUTURE_ERP"
    elif not audit:
        decision = "HOLD_AUDIT_CHAIN"
    else:
        decision = "EVIDENCE_READY"

    return _add_receipt_fn(
        {
            "schema": _case_schema,
            "case_id": case_id,
            "merchant_id": merchant_id,
            "decision": decision,
            "variance_cents": processor - erp,
            "unresolved_chargeback_count": chargebacks,
            "evidence_age_seconds": age_seconds,
            "buyer_contact_authorized": False,
            "partner_contact_authorized": False,
            "submission_authorized": False,
            "contract_acceptance_authorized": False,
            "banking_authorized": False,
            "merchant_acquiring_authorized": False,
            "card_issuance_authorized": False,
            "payment_authorized": False,
            "production_erp_write_authorized": False,
            "compliance_certification_authorized": False,
            "revenue_recognized": False,
        }
    )


def evaluate_matrix(
    document: Any,
    trusted_as_of: str,
    _evaluate_case_fn=evaluate_reconciliation_case,
    _add_receipt_fn=_add_receipt,
    _exact_fn=_exact,
    _text_fn=_text,
    _error=ContractError,
    _case_schema=CASE_SCHEMA,
    _terminal_decisions=tuple(TERMINAL_DECISIONS),
) -> dict[str, Any]:
    doc = _exact_fn(document, {"schema", "cases"}, "matrix")
    if doc["schema"] != _case_schema:
        raise _error("matrix.schema: unsupported")
    rows = doc["cases"]
    if type(rows) is not list or len(rows) < len(_terminal_decisions):
        raise _error("matrix.cases: terminal coverage required")

    seen = set()
    counts = {decision: 0 for decision in _terminal_decisions}
    results = []
    for index, raw in enumerate(rows):
        wrap = _exact_fn(
            raw,
            {"expected_decision", "case"},
            f"matrix.cases[{index}]",
        )
        expected = _text_fn(
            wrap["expected_decision"],
            f"matrix.cases[{index}].expected_decision",
            64,
        )
        if expected not in counts:
            raise _error(
                f"matrix.cases[{index}].expected_decision: unsupported"
            )
        result = _evaluate_case_fn(wrap["case"], trusted_as_of)
        if result["case_id"] in seen:
            raise _error("matrix: duplicate case_id")
        seen.add(result["case_id"])
        if result["decision"] != expected:
            raise _error(
                f"matrix.cases[{index}]: expected {expected}, "
                f"got {result['decision']}"
            )
        counts[expected] += 1
        results.append(result)

    missing = [key for key, count in counts.items() if count == 0]
    if missing:
        raise _error(f"matrix: missing terminal decisions {missing}")

    return _add_receipt_fn(
        {
            "schema": _case_schema,
            "case_count": len(results),
            "decision_counts": counts,
            "results": results,
            "buyer_contact_authorized": False,
            "partner_contact_authorized": False,
            "submission_authorized": False,
            "contract_acceptance_authorized": False,
            "banking_authorized": False,
            "merchant_acquiring_authorized": False,
            "card_issuance_authorized": False,
            "payment_authorized": False,
            "production_erp_write_authorized": False,
            "compliance_certification_authorized": False,
            "revenue_recognized": False,
        }
    )


def compile_bundle(
    manifest: Any,
    partners: Any,
    matrix: Any,
    trusted_as_of: str,
    _validate_manifest_fn=validate_manifest,
    _evaluate_partners_fn=evaluate_partners,
    _evaluate_matrix_fn=evaluate_matrix,
    _add_receipt_fn=_add_receipt,
    _bundle_schema=BUNDLE_SCHEMA,
) -> dict[str, Any]:
    pursuit = _validate_manifest_fn(manifest, trusted_as_of)
    partner_result = _evaluate_partners_fn(partners)
    matrix_result = _evaluate_matrix_fn(matrix, trusted_as_of)

    return _add_receipt_fn(
        {
            "schema": _bundle_schema,
            "solicitation_id": "27-0012",
            "pursuit": pursuit,
            "partners": partner_result,
            "reconciliation_matrix": matrix_result,
            "partner_outreach_state": "HOLD_OUTBOUND_CUSTODY_REQUIRED",
            "submission_state": (
                "HOLD_BUYER_PACKET_REQUIRED"
                if pursuit["source_authority_state"]
                != "BUYER_PACKET_RETAINED"
                else "OWNER_REVIEW_REQUIRED"
            ),
            "buyer_contact_authorized": False,
            "partner_contact_authorized": False,
            "submission_authorized": False,
            "contract_acceptance_authorized": False,
            "banking_authorized": False,
            "merchant_acquiring_authorized": False,
            "card_issuance_authorized": False,
            "payment_authorized": False,
            "production_erp_write_authorized": False,
            "compliance_certification_authorized": False,
            "revenue_recognized": False,
        }
    )


def verify_bundle(
    bundle: Any,
    manifest: Any,
    partners: Any,
    matrix: Any,
    trusted_as_of: str,
    _canonical_json_fn=canonical_json,
    _compile_bundle_fn=compile_bundle,
) -> bool:
    if type(bundle) is not dict:
        return False
    return _canonical_json_fn(bundle) == _canonical_json_fn(
        _compile_bundle_fn(manifest, partners, matrix, trusted_as_of)
    )
