from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlparse

SCHEMA = "tjlabs.ky-rfi-758-2700000006-fin-reporting/v1"
CASE_SCHEMA = "tjlabs.fin-reporting-discovery-case/v1"
MATRIX_SCHEMA = "tjlabs.fin-reporting-discovery-matrix/v1"
BUNDLE_SCHEMA = "tjlabs.ky-rfi-758-2700000006-response-readiness/v1"

SOLICITATION_ID = "RFI 758 2700000006"
BUYER = "Commonwealth of Kentucky Finance and Administration Cabinet"
OFFICE = "Office of Statewide Accounting Services"
TITLE = "Enterprise Financial Reporting Discovery"
CLOSE_UTC = "2026-10-02T19:30:00Z"
ADDENDUM_QA_TARGET_DATE = "2026-09-23"
MAX_SOURCE_AGE_SECONDS = 48 * 60 * 60

AUTHORITY_FALSE = {
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
}

TERMINALS = (
    "DISCOVERY_EVIDENCE_READY",
    "HOLD_REPORT_SEMANTICS",
    "HOLD_SOURCE_LINEAGE",
    "HOLD_ACCESS_MODEL",
    "HOLD_GCC_COMPATIBILITY",
    "HOLD_ACCESSIBILITY",
    "HOLD_PERFORMANCE",
    "HOLD_DISTRIBUTION",
    "HOLD_MIGRATION_RECONCILIATION",
    "HOLD_OPERABILITY_DR",
    "REJECT_SENSITIVE_PRODUCTION_DATA",
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class ContractError(ValueError):
    pass


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant rejected: {value}")


def strict_loads(text: str) -> Any:
    if type(text) is not str:
        raise ContractError("JSON input must be str")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"not canonicalizable: {exc}") from exc


def receipt(value: dict[str, Any]) -> dict[str, Any]:
    base = dict(value)
    base.pop("receipt_sha256", None)
    base["receipt_sha256"] = sha256(
        canonical_json(base).encode("utf-8")
    ).hexdigest()
    return base


def _exact(obj: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise ContractError(f"{label}: object required")
    got = set(obj)
    if got != keys:
        raise ContractError(
            f"{label}: exact keys required; "
            f"missing={sorted(keys - got)} extra={sorted(got - keys)}"
        )
    return obj


def _text(value: Any, label: str, max_len: int = 1200) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ContractError(f"{label}: bounded non-empty string required")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise ContractError(f"{label}: control character rejected")
    return value


def _identifier(value: Any, label: str) -> str:
    value = _text(value, label, 128)
    if not _ID.fullmatch(value):
        raise ContractError(f"{label}: invalid identifier")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{label}: bool required")
    return value


def _int(value: Any, label: str, low: int = 0, high: int = 10**15) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"{label}: integer in [{low},{high}] required")
    return value


def _utc(value: Any, label: str) -> datetime:
    value = _text(value, label, 40)
    if not value.endswith("Z"):
        raise ContractError(f"{label}: UTC Z timestamp required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{label}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ContractError(f"{label}: UTC required")
    return parsed


def _https(value: Any, label: str) -> str:
    value = _text(value, label, 2048)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ContractError(f"{label}: https URL required")
    if parsed.username or parsed.password or parsed.fragment:
        raise ContractError(f"{label}: credentials/fragments forbidden")
    return value


def _validate_authority(obj: Any, label: str) -> None:
    authority_fields = set({
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
})
    authority = _exact(obj, authority_fields, label)
    for field in authority_fields:
        if _bool(authority[field], f"{label}.{field}") is not False:
            raise ContractError(f"{label}.{field}: must remain false")


def validate_manifest(manifest: Any, trusted_as_of: str) -> dict[str, Any]:
    doc = _exact(
        manifest,
        {
            "schema",
            "solicitation",
            "source_evidence",
            "buyer_packet",
            "research_leads",
            "response_posture",
            "commercial_follow_on",
            "authority",
        },
        "manifest",
    )
    if doc["schema"] != SCHEMA:
        raise ContractError("manifest.schema: unsupported")

    sol = _exact(
        doc["solicitation"],
        {
            "id",
            "buyer",
            "office",
            "title",
            "close_utc",
            "addendum_qa_target_date",
        },
        "manifest.solicitation",
    )
    if (
        sol["id"] != SOLICITATION_ID
        or sol["buyer"] != BUYER
        or sol["office"] != OFFICE
        or sol["title"] != TITLE
        or sol["close_utc"] != CLOSE_UTC
        or sol["addendum_qa_target_date"] != ADDENDUM_QA_TARGET_DATE
    ):
        raise ContractError("manifest.solicitation: identity/deadline drift")

    as_of = _utc(trusted_as_of, "trusted_as_of")
    close = _utc(CLOSE_UTC, "close")
    sources = doc["source_evidence"]
    if type(sources) is not list or not 2 <= len(sources) <= 8:
        raise ContractError("manifest.source_evidence: 2..8 sources required")
    seen_urls = set()
    source_fresh = True
    for index, raw in enumerate(sources):
        row = _exact(
            raw,
            {"url", "captured_at_utc", "source_class", "note"},
            f"manifest.source_evidence[{index}]",
        )
        url = _https(row["url"], f"manifest.source_evidence[{index}].url")
        if url in seen_urls:
            raise ContractError("manifest.source_evidence: duplicate URL")
        seen_urls.add(url)
        if row["source_class"] not in {
            "SECONDARY_PUBLIC_INDEX",
            "PUBLIC_PROCUREMENT_MIRROR",
        }:
            raise ContractError(
                f"manifest.source_evidence[{index}].source_class: unsupported"
            )
        captured = _utc(
            row["captured_at_utc"],
            f"manifest.source_evidence[{index}].captured_at_utc",
        )
        if captured > as_of:
            raise ContractError("manifest.source_evidence: future capture")
        if as_of - captured > timedelta(seconds=MAX_SOURCE_AGE_SECONDS):
            source_fresh = False
        _text(row["note"], f"manifest.source_evidence[{index}].note")

    packet = _exact(
        doc["buyer_packet"],
        {"retained", "sha256", "source_generation", "authority"},
        "manifest.buyer_packet",
    )
    retained = _bool(packet["retained"], "manifest.buyer_packet.retained")
    if retained:
        raise ContractError(
            "manifest.buyer_packet.retained: not supported in this generation"
        )
    if (
        packet["sha256"] is not None
        or packet["source_generation"] is not None
        or packet["authority"] != "NOT_RETAINED"
    ):
        raise ContractError(
            "manifest.buyer_packet: absent packet must stay unasserted"
        )


    leads = doc["research_leads"]
    if type(leads) is not list or not 1 <= len(leads) <= 12:
        raise ContractError("manifest.research_leads: 1..12 leads required")
    seen_leads = set()
    for index, raw in enumerate(leads):
        row = _exact(
            raw,
            {"lead_id", "claim", "status", "source_url"},
            f"manifest.research_leads[{index}]",
        )
        lead_id = _identifier(
            row["lead_id"], f"manifest.research_leads[{index}].lead_id"
        )
        if lead_id in seen_leads:
            raise ContractError("manifest.research_leads: duplicate lead_id")
        seen_leads.add(lead_id)
        _text(row["claim"], f"manifest.research_leads[{index}].claim")
        if row["status"] != "UNVERIFIED_SECONDARY_LEAD":
            raise ContractError(
                f"manifest.research_leads[{index}].status: cannot self-promote"
            )
        _https(
            row["source_url"],
            f"manifest.research_leads[{index}].source_url",
        )

    posture = _exact(
        doc["response_posture"],
        {
            "state",
            "buyer_packet_required",
            "portal_or_submission_authority_required",
            "external_send_authorized",
        },
        "manifest.response_posture",
    )
    if posture["state"] != "INTERNAL_RESPONSE_READINESS":
        raise ContractError("manifest.response_posture.state: drift")
    if (
        _bool(
            posture["buyer_packet_required"],
            "manifest.response_posture.buyer_packet_required",
        )
        is not True
    ):
        raise ContractError("manifest.response_posture: packet gate required")
    if (
        _bool(
            posture["portal_or_submission_authority_required"],
            "manifest.response_posture.portal_or_submission_authority_required",
        )
        is not True
    ):
        raise ContractError("manifest.response_posture: authority gate required")
    if (
        _bool(
            posture["external_send_authorized"],
            "manifest.response_posture.external_send_authorized",
        )
        is not False
    ):
        raise ContractError("manifest.response_posture: send must remain false")

    offer = _exact(
        doc["commercial_follow_on"],
        {"state", "name", "price_usd_cents", "included_in_rfi_response"},
        "manifest.commercial_follow_on",
    )
    if offer["state"] != "INTERNAL_HYPOTHESIS_NOT_SUBMITTED":
        raise ContractError("manifest.commercial_follow_on.state: drift")
    if (
        _text(offer["name"], "manifest.commercial_follow_on.name", 180)
        != "Financial Reporting Discovery Evidence Sprint"
    ):
        raise ContractError("manifest.commercial_follow_on.name: drift")
    if (
        _int(
            offer["price_usd_cents"],
            "manifest.commercial_follow_on.price_usd_cents",
            1,
            100_000_000,
        )
        != 2_500_000
    ):
        raise ContractError("manifest.commercial_follow_on.price: drift")
    if (
        _bool(
            offer["included_in_rfi_response"],
            "manifest.commercial_follow_on.included_in_rfi_response",
        )
        is not False
    ):
        raise ContractError(
            "manifest.commercial_follow_on: hypothesis cannot leak into response"
        )

    _validate_authority(doc["authority"], "manifest.authority")

    state = {
        "schema": SCHEMA,
        "solicitation_id": SOLICITATION_ID,
        "source_authority_state": (
            "BUYER_PACKET_RETAINED"
            if retained
            else "HOLD_BUYER_PACKET_REQUIRED"
        ),
        "response_window_state": (
            "HOLD_CLOSED_WINDOW"
            if as_of >= close
            else (
                "OPEN_INTERNAL_BUILD"
                if source_fresh
                else "HOLD_SOURCE_REFRESH_REQUIRED"
            )
        ),
        "submission_state": "HOLD_OWNER_AND_PORTAL_AUTHORITY",
        "research_lead_count": len(leads),
        "commercial_follow_on_state": offer["state"],
        "commercial_follow_on_price_usd_cents": offer["price_usd_cents"],
        **{
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
},
    }
    return receipt(state)


CASE_KEYS = {
    "schema",
    "case_id",
    "report_id",
    "semantic_parity_evidenced",
    "source_lineage_complete",
    "access_model_mapped",
    "gcc_compatibility_evidenced",
    "accessibility_evidenced",
    "performance_target_met",
    "distribution_contract_evidenced",
    "migration_reconciled",
    "operability_dr_evidenced",
    "sensitive_production_data_present",
    "observed_at_utc",
}


def evaluate_case(case: Any, trusted_as_of: str) -> dict[str, Any]:
    row = _exact(case, CASE_KEYS, "case")
    if row["schema"] != CASE_SCHEMA:
        raise ContractError("case.schema: unsupported")
    case_id = _identifier(row["case_id"], "case.case_id")
    report_id = _identifier(row["report_id"], "case.report_id")
    semantic = _bool(
        row["semantic_parity_evidenced"], "case.semantic_parity_evidenced"
    )
    lineage = _bool(
        row["source_lineage_complete"], "case.source_lineage_complete"
    )
    access = _bool(row["access_model_mapped"], "case.access_model_mapped")
    gcc = _bool(
        row["gcc_compatibility_evidenced"],
        "case.gcc_compatibility_evidenced",
    )
    accessibility = _bool(
        row["accessibility_evidenced"], "case.accessibility_evidenced"
    )
    performance = _bool(
        row["performance_target_met"], "case.performance_target_met"
    )
    distribution = _bool(
        row["distribution_contract_evidenced"],
        "case.distribution_contract_evidenced",
    )
    reconciliation = _bool(
        row["migration_reconciled"], "case.migration_reconciled"
    )
    operability = _bool(
        row["operability_dr_evidenced"], "case.operability_dr_evidenced"
    )
    sensitive = _bool(
        row["sensitive_production_data_present"],
        "case.sensitive_production_data_present",
    )
    observed = _utc(row["observed_at_utc"], "case.observed_at_utc")
    as_of = _utc(trusted_as_of, "trusted_as_of")
    if observed > as_of:
        raise ContractError("case.observed_at_utc: future evidence")
    age_seconds = int((as_of - observed).total_seconds())
    if age_seconds > 14 * 24 * 3600:
        raise ContractError("case.observed_at_utc: stale discovery evidence")

    if sensitive:
        decision = "REJECT_SENSITIVE_PRODUCTION_DATA"
    elif not semantic:
        decision = "HOLD_REPORT_SEMANTICS"
    elif not lineage:
        decision = "HOLD_SOURCE_LINEAGE"
    elif not access:
        decision = "HOLD_ACCESS_MODEL"
    elif not gcc:
        decision = "HOLD_GCC_COMPATIBILITY"
    elif not accessibility:
        decision = "HOLD_ACCESSIBILITY"
    elif not performance:
        decision = "HOLD_PERFORMANCE"
    elif not distribution:
        decision = "HOLD_DISTRIBUTION"
    elif not reconciliation:
        decision = "HOLD_MIGRATION_RECONCILIATION"
    elif not operability:
        decision = "HOLD_OPERABILITY_DR"
    else:
        decision = "DISCOVERY_EVIDENCE_READY"

    return receipt(
        {
            "schema": CASE_SCHEMA,
            "case_id": case_id,
            "report_id": report_id,
            "decision": decision,
            "evidence_age_seconds": age_seconds,
            **{
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
},
        }
    )


def evaluate_matrix(document: Any, trusted_as_of: str) -> dict[str, Any]:
    doc = _exact(document, {"schema", "cases"}, "matrix")
    if doc["schema"] != MATRIX_SCHEMA:
        raise ContractError("matrix.schema: unsupported")
    rows = doc["cases"]
    if type(rows) is not list or len(rows) < len(TERMINALS):
        raise ContractError("matrix.cases: terminal coverage required")

    counts = {decision: 0 for decision in TERMINALS}
    seen = set()
    results = []
    for index, raw in enumerate(rows):
        wrap = _exact(
            raw,
            {"expected_decision", "case"},
            f"matrix.cases[{index}]",
        )
        expected = _text(
            wrap["expected_decision"],
            f"matrix.cases[{index}].expected_decision",
            64,
        )
        if expected not in counts:
            raise ContractError(
                f"matrix.cases[{index}].expected_decision: unsupported"
            )
        result = evaluate_case(wrap["case"], trusted_as_of)
        if result["case_id"] in seen:
            raise ContractError("matrix: duplicate case_id")
        seen.add(result["case_id"])
        if result["decision"] != expected:
            raise ContractError(
                f"matrix.cases[{index}]: expected {expected}, "
                f"got {result['decision']}"
            )
        counts[expected] += 1
        results.append(result)

    missing = [key for key, count in counts.items() if count == 0]
    if missing:
        raise ContractError(f"matrix: missing terminal decisions {missing}")

    return receipt(
        {
            "schema": MATRIX_SCHEMA,
            "case_count": len(results),
            "decision_counts": counts,
            "results": results,
            **{
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
},
        }
    )


def compile_bundle(
    manifest: Any,
    matrix: Any,
    trusted_as_of: str,
) -> dict[str, Any]:
    pursuit = validate_manifest(manifest, trusted_as_of)
    matrix_result = evaluate_matrix(matrix, trusted_as_of)
    return receipt(
        {
            "schema": BUNDLE_SCHEMA,
            "solicitation_id": SOLICITATION_ID,
            "pursuit": pursuit,
            "discovery_matrix": matrix_result,
            "response_content_state": (
                "HOLD_BUYER_PACKET_REQUIRED"
                if pursuit["source_authority_state"]
                != "BUYER_PACKET_RETAINED"
                else "OWNER_REVIEW_REQUIRED"
            ),
            "submission_state": "HOLD_OWNER_AND_PORTAL_AUTHORITY",
            **{
    "buyer_contact_authorized": False,
    "portal_action_authorized": False,
    "vendor_registration_authorized": False,
    "terms_acceptance_authorized": False,
    "signature_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "production_access_authorized": False,
    "production_data_authorized": False,
    "payment_authorized": False,
    "revenue_recognized": False,
},
        }
    )


def verify_bundle(
    bundle: Any,
    manifest: Any,
    matrix: Any,
    trusted_as_of: str,
) -> bool:
    if type(bundle) is not dict:
        return False
    return canonical_json(bundle) == canonical_json(
        compile_bundle(manifest, matrix, trusted_as_of)
    )
