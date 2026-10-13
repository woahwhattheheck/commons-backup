from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "tjlabs.lacsd-04252-ap-evidence/v1"
CASE_SCHEMA = "tjlabs.ap-automation-acceptance-case/v1"
RESULT_SCHEMA = "tjlabs.ap-automation-acceptance-result/v1"
MATRIX_SCHEMA = "tjlabs.ap-automation-acceptance-matrix/v1"
SOLICITATION_ID = "04252"
BUYER = "Los Angeles County Sanitation Districts"
TITLE = "AUTOMATED ACCOUNTS PAYABLE INVOICE PROCESSING SYSTEM"
DETAIL_URL = "https://www.lacsd.org/Home/Components/RFP/RFP/954/488?selsta=4"
CURRENT_LIST_URL = "https://www.lacsd.org/about-us/advanced-components/list-detail-pages/rfp-posts-list"
SUBMISSION_RULES_URL = "https://www.lacsd.org/opportunities/bids-purchasing/purchasing-section-projects"
BID_DUE_UTC = "2026-10-15T18:00:00Z"
TARGET_ACCURACY_BPS = 9900
TARGET_CYCLE_SECONDS = 48 * 60 * 60

AUTHORITY_FALSE = {
    "oracle_write_authorized": False,
    "payment_authorized": False,
    "buyer_contact_authorized": False,
    "prime_contact_authorized": False,
    "submission_authorized": False,
    "contract_acceptance_authorized": False,
    "revenue_recognized": False,
}

TERMINAL_DECISIONS = (
    "ACCEPT_EVIDENCE_READY",
    "REJECT_DUPLICATE",
    "HOLD_EXTRACTION_ACCURACY",
    "HOLD_MISSING_PO",
    "HOLD_VENDOR_MISMATCH",
    "HOLD_AMOUNT_VARIANCE",
    "HOLD_APPROVAL",
    "HOLD_CYCLE_TIME",
    "HOLD_ORACLE_SYNC",
    "HOLD_AUDIT_TRAIL",
    "HOLD_DASHBOARD_FRESHNESS",
)

CASE_KEYS = {
    "schema",
    "case_id",
    "invoice_id",
    "extraction_fields_total",
    "extraction_fields_correct",
    "received_at_utc",
    "ready_at_utc",
    "po_required",
    "po_present",
    "vendor_match",
    "invoice_total_cents",
    "po_total_cents",
    "tolerance_cents",
    "duplicate",
    "routing_signoff_needed",
    "routing_signoff_present",
    "oracle_sync_evidenced",
    "audit_trail_complete",
    "dashboard_fresh",
}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_pairs_no_dupes,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ContractError(f"non-finite number: {token}")
        ),
    )


def strict_load(path: str | Path) -> Any:
    return strict_loads(Path(path).read_text(encoding="utf-8"))


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_keys(obj: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise ContractError(f"{where}: object required")
    if set(obj) != keys:
        missing = sorted(keys - set(obj))
        extra = sorted(set(obj) - keys)
        raise ContractError(f"{where}: key mismatch missing={missing} extra={extra}")
    return obj


def _text(value: Any, where: str, *, max_len: int = 500) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ContractError(f"{where}: bounded non-empty string required")
    if any(ord(ch) < 32 and ch not in "\t\n" for ch in value):
        raise ContractError(f"{where}: control characters forbidden")
    return value


def _ident(value: Any, where: str) -> str:
    text = _text(value, where, max_len=96)
    if not ID_RE.fullmatch(text):
        raise ContractError(f"{where}: safe identifier required")
    return text


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{where}: bool required")
    return value


def _int(value: Any, where: str, lo: int = 0, hi: int = 10**15) -> int:
    if type(value) is not int or value < lo or value > hi:
        raise ContractError(f"{where}: integer in [{lo}, {hi}] required")
    return value


def _utc(value: Any, where: str) -> datetime:
    text = _text(value, where, max_len=32)
    if not text.endswith("Z"):
        raise ContractError(f"{where}: canonical UTC Z timestamp required")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{where}: invalid timestamp") from exc
    if dt.tzinfo != timezone.utc:
        raise ContractError(f"{where}: UTC required")
    return dt


def _https(value: Any, where: str) -> str:
    text = _text(value, where, max_len=500)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ContractError(f"{where}: canonical HTTPS URL required")
    if parsed.fragment:
        raise ContractError(f"{where}: URL fragment forbidden")
    return text


def _add_receipt(packet: dict[str, Any]) -> dict[str, Any]:
    out = dict(packet)
    out["receipt_sha256"] = sha256_hex(canonical_json(packet))
    return out


def evaluate_case(case: Any) -> dict[str, Any]:
    row = _exact_keys(case, CASE_KEYS, "case")
    if row["schema"] != CASE_SCHEMA:
        raise ContractError("case.schema: unsupported")

    case_id = _ident(row["case_id"], "case.case_id")
    invoice_id = _ident(row["invoice_id"], "case.invoice_id")
    total_fields = _int(row["extraction_fields_total"], "case.extraction_fields_total", 1, 10000)
    correct_fields = _int(row["extraction_fields_correct"], "case.extraction_fields_correct", 0, total_fields)
    received = _utc(row["received_at_utc"], "case.received_at_utc")
    ready = _utc(row["ready_at_utc"], "case.ready_at_utc")
    if ready < received:
        raise ContractError("case.ready_at_utc: cannot precede receipt")

    po_required = _bool(row["po_required"], "case.po_required")
    po_present = _bool(row["po_present"], "case.po_present")
    vendor_match = _bool(row["vendor_match"], "case.vendor_match")
    duplicate = _bool(row["duplicate"], "case.duplicate")
    routing_signoff_needed = _bool(row["routing_signoff_needed"], "case.routing_signoff_needed")
    routing_signoff_present = _bool(row["routing_signoff_present"], "case.routing_signoff_present")
    oracle_sync_evidenced = _bool(row["oracle_sync_evidenced"], "case.oracle_sync_evidenced")
    audit_trail_complete = _bool(row["audit_trail_complete"], "case.audit_trail_complete")
    dashboard_fresh = _bool(row["dashboard_fresh"], "case.dashboard_fresh")

    invoice_total = _int(row["invoice_total_cents"], "case.invoice_total_cents")
    po_total = _int(row["po_total_cents"], "case.po_total_cents")
    tolerance = _int(row["tolerance_cents"], "case.tolerance_cents")

    accuracy_bps = (correct_fields * 10000) // total_fields
    cycle_seconds = int((ready - received).total_seconds())
    variance_cents = abs(invoice_total - po_total)

    if duplicate:
        decision = "REJECT_DUPLICATE"
    elif accuracy_bps < TARGET_ACCURACY_BPS:
        decision = "HOLD_EXTRACTION_ACCURACY"
    elif po_required and not po_present:
        decision = "HOLD_MISSING_PO"
    elif not vendor_match:
        decision = "HOLD_VENDOR_MISMATCH"
    elif po_required and variance_cents > tolerance:
        decision = "HOLD_AMOUNT_VARIANCE"
    elif routing_signoff_needed and not routing_signoff_present:
        decision = "HOLD_APPROVAL"
    elif cycle_seconds >= TARGET_CYCLE_SECONDS:
        decision = "HOLD_CYCLE_TIME"
    elif not oracle_sync_evidenced:
        decision = "HOLD_ORACLE_SYNC"
    elif not audit_trail_complete:
        decision = "HOLD_AUDIT_TRAIL"
    elif not dashboard_fresh:
        decision = "HOLD_DASHBOARD_FRESHNESS"
    else:
        decision = "ACCEPT_EVIDENCE_READY"

    packet = {
        "schema": RESULT_SCHEMA,
        "case_id": case_id,
        "invoice_id": invoice_id,
        "decision": decision,
        "accuracy_bps": accuracy_bps,
        "cycle_seconds": cycle_seconds,
        "variance_cents": variance_cents,
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def evaluate_matrix(document: Any) -> dict[str, Any]:
    matrix = _exact_keys(document, {"schema", "cases"}, "matrix")
    if matrix["schema"] != MATRIX_SCHEMA:
        raise ContractError("matrix.schema: unsupported")
    rows = matrix["cases"]
    if type(rows) is not list or len(rows) < len(TERMINAL_DECISIONS):
        raise ContractError("matrix.cases: one or more cases per terminal decision required")

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    counts = {decision: 0 for decision in TERMINAL_DECISIONS}

    for index, raw in enumerate(rows):
        row = _exact_keys(raw, {"expected_decision", "case"}, f"matrix.cases[{index}]")
        expected = _text(row["expected_decision"], f"matrix.cases[{index}].expected_decision", max_len=64)
        if expected not in counts:
            raise ContractError(f"matrix.cases[{index}].expected_decision: unknown decision")
        result = evaluate_case(row["case"])
        if result["case_id"] in seen_ids:
            raise ContractError(f"matrix.cases[{index}]: duplicate case_id")
        seen_ids.add(result["case_id"])
        if result["decision"] != expected:
            raise ContractError(
                f"matrix.cases[{index}]: expected {expected}, got {result['decision']}"
            )
        counts[expected] += 1
        results.append(result)

    missing = sorted(decision for decision, count in counts.items() if count == 0)
    if missing:
        raise ContractError(f"matrix: terminal coverage missing {missing}")

    packet = {
        "schema": MATRIX_SCHEMA,
        "case_count": len(results),
        "decision_counts": counts,
        "results": results,
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def validate_manifest(manifest: Any, trusted_as_of: str) -> dict[str, Any]:
    doc = _exact_keys(
        manifest,
        {
            "schema",
            "solicitation",
            "sources",
            "submission_evidence",
            "requirements",
            "commercial_offer",
            "authority",
        },
        "manifest",
    )
    if doc["schema"] != SCHEMA:
        raise ContractError("manifest.schema: unsupported")

    solicitation = _exact_keys(doc["solicitation"], {"id", "buyer", "title"}, "manifest.solicitation")
    if solicitation["id"] != SOLICITATION_ID:
        raise ContractError("manifest.solicitation.id: wrong solicitation")
    if solicitation["buyer"] != BUYER:
        raise ContractError("manifest.solicitation.buyer: exact buyer required")
    if solicitation["title"] != TITLE:
        raise ContractError("manifest.solicitation.title: exact title required")

    sources = _exact_keys(
        doc["sources"], {"detail", "current_list", "submission_rules"}, "manifest.sources"
    )
    detail = _exact_keys(
        sources["detail"], {"url", "captured_at_utc", "due_utc"}, "manifest.sources.detail"
    )
    listing = _exact_keys(
        sources["current_list"],
        {"url", "captured_at_utc", "due_utc"},
        "manifest.sources.current_list",
    )
    submission_rules = _exact_keys(
        sources["submission_rules"],
        {
            "url",
            "captured_at_utc",
            "authorized_distributor",
            "proper_download_required_for_planholder",
            "planholder_required_to_submit",
            "submission_route",
        },
        "manifest.sources.submission_rules",
    )
    if _https(detail["url"], "manifest.sources.detail.url") != DETAIL_URL:
        raise ContractError("manifest.sources.detail.url: controlling URL drift")
    if _https(listing["url"], "manifest.sources.current_list.url") != CURRENT_LIST_URL:
        raise ContractError("manifest.sources.current_list.url: controlling URL drift")
    if _https(submission_rules["url"], "manifest.sources.submission_rules.url") != SUBMISSION_RULES_URL:
        raise ContractError("manifest.sources.submission_rules.url: controlling URL drift")
    if detail["due_utc"] != BID_DUE_UTC:
        raise ContractError("manifest.sources.detail.due_utc: detail deadline drift")
    if listing["due_utc"] != BID_DUE_UTC:
        raise ContractError("manifest.sources.current_list.due_utc: current-list deadline drift")
    if submission_rules["authorized_distributor"] != "QuestCDN":
        raise ContractError("manifest.sources.submission_rules.authorized_distributor: must remain QuestCDN")
    if _bool(
        submission_rules["proper_download_required_for_planholder"],
        "manifest.sources.submission_rules.proper_download_required_for_planholder",
    ) is not True:
        raise ContractError("manifest.sources.submission_rules: proper-download rule must remain true")
    if _bool(
        submission_rules["planholder_required_to_submit"],
        "manifest.sources.submission_rules.planholder_required_to_submit",
    ) is not True:
        raise ContractError("manifest.sources.submission_rules: planholder rule must remain true")
    if submission_rules["submission_route"] != "QUESTCDN_ONLY":
        raise ContractError("manifest.sources.submission_rules.submission_route: must remain QUESTCDN_ONLY")

    as_of = _utc(trusted_as_of, "trusted_as_of")
    capture_values = (
        _utc(detail["captured_at_utc"], "manifest.sources.detail.captured_at_utc"),
        _utc(listing["captured_at_utc"], "manifest.sources.current_list.captured_at_utc"),
        _utc(
            submission_rules["captured_at_utc"],
            "manifest.sources.submission_rules.captured_at_utc",
        ),
    )
    if any(capture > as_of for capture in capture_values):
        raise ContractError("manifest.sources: future source generation")

    submission_evidence = _exact_keys(
        doc["submission_evidence"],
        {"authorized_packet_retained", "proper_download_evidenced", "planholder_status"},
        "manifest.submission_evidence",
    )
    if _bool(
        submission_evidence["authorized_packet_retained"],
        "manifest.submission_evidence.authorized_packet_retained",
    ) is not False:
        raise ContractError("manifest.submission_evidence.authorized_packet_retained: retained authority absent")
    if _bool(
        submission_evidence["proper_download_evidenced"],
        "manifest.submission_evidence.proper_download_evidenced",
    ) is not False:
        raise ContractError("manifest.submission_evidence.proper_download_evidenced: retained authority absent")
    if submission_evidence["planholder_status"] != "NOT_ESTABLISHED":
        raise ContractError("manifest.submission_evidence.planholder_status: must remain NOT_ESTABLISHED")

    requirements = _exact_keys(
        doc["requirements"],
        {
            "zero_template_ai_extraction",
            "target_accuracy_bps",
            "target_cycle_seconds",
            "automated_matching",
            "approval_routing",
            "oracle_ebs_realtime_integration",
            "complete_audit_trail",
            "realtime_bi_visibility",
        },
        "manifest.requirements",
    )
    if _bool(requirements["zero_template_ai_extraction"], "manifest.requirements.zero_template_ai_extraction") is not True:
        raise ContractError("manifest.requirements.zero_template_ai_extraction: must remain true")
    if _int(requirements["target_accuracy_bps"], "manifest.requirements.target_accuracy_bps") != TARGET_ACCURACY_BPS:
        raise ContractError("manifest.requirements.target_accuracy_bps: buyer target drift")
    if _int(requirements["target_cycle_seconds"], "manifest.requirements.target_cycle_seconds") != TARGET_CYCLE_SECONDS:
        raise ContractError("manifest.requirements.target_cycle_seconds: buyer target drift")
    for field in (
        "automated_matching",
        "approval_routing",
        "oracle_ebs_realtime_integration",
        "complete_audit_trail",
        "realtime_bi_visibility",
    ):
        if _bool(requirements[field], f"manifest.requirements.{field}") is not True:
            raise ContractError(f"manifest.requirements.{field}: buyer requirement drift")

    offer = _exact_keys(
        doc["commercial_offer"],
        {"state", "name", "price_usd_cents", "acceptance", "external_send_authorized"},
        "manifest.commercial_offer",
    )
    if offer["state"] != "PROPOSED_NOT_ACCEPTED":
        raise ContractError("manifest.commercial_offer.state: must remain PROPOSED_NOT_ACCEPTED")
    if _text(offer["name"], "manifest.commercial_offer.name", max_len=160) != "AP Automation Validation/UAT Evidence Workshare":
        raise ContractError("manifest.commercial_offer.name: exact bounded offer required")
    if _int(offer["price_usd_cents"], "manifest.commercial_offer.price_usd_cents", 1, 10_000_000) != 500000:
        raise ContractError("manifest.commercial_offer.price_usd_cents: reference price drift")
    _text(offer["acceptance"], "manifest.commercial_offer.acceptance", max_len=1200)
    if _bool(offer["external_send_authorized"], "manifest.commercial_offer.external_send_authorized") is not False:
        raise ContractError("manifest.commercial_offer.external_send_authorized: must remain false")

    authority = _exact_keys(doc["authority"], set(AUTHORITY_FALSE), "manifest.authority")
    for field in AUTHORITY_FALSE:
        if _bool(authority[field], f"manifest.authority.{field}") is not False:
            raise ContractError(f"manifest.authority.{field}: must remain false")

    source_facts = {
        "id": SOLICITATION_ID,
        "buyer": BUYER,
        "title": TITLE,
        "detail_url": DETAIL_URL,
        "current_list_url": CURRENT_LIST_URL,
        "submission_rules_url": SUBMISSION_RULES_URL,
        "bid_due_utc": BID_DUE_UTC,
        "authorized_distributor": "QuestCDN",
        "submission_route": "QUESTCDN_ONLY",
    }
    latest_public_due = _utc(BID_DUE_UTC, "bid due")
    packet = {
        "schema": SCHEMA,
        "solicitation_id": SOLICITATION_ID,
        "buyer": BUYER,
        "source_facts_sha256": sha256_hex(canonical_json(source_facts)),
        "deadline_conflict": False,
        "deadline_state": "CURRENT_BUYER_PAGES_AGREE",
        "bid_due_utc": BID_DUE_UTC,
        "detail_due_utc": BID_DUE_UTC,
        "list_due_utc": BID_DUE_UTC,
        "submission_control_state": "QUESTCDN_PACKET_DOWNLOAD_AND_PLANHOLDER_NOT_ESTABLISHED",
        "submission_state": "HOLD_QUESTCDN_PACKET_AND_PLANHOLDER",
        "teaming_build_state": "READY" if as_of < latest_public_due else "HOLD_RESPONSE_WINDOW",
        "commercial_offer_state": offer["state"],
        "commercial_offer_price_usd_cents": offer["price_usd_cents"],
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def compile_evidence(manifest: Any, matrix: Any, trusted_as_of: str) -> dict[str, Any]:
    pursuit = validate_manifest(manifest, trusted_as_of)
    matrix_result = evaluate_matrix(matrix)
    packet = {
        "schema": "tjlabs.lacsd-04252-ap-evidence-bundle/v1",
        "solicitation_id": SOLICITATION_ID,
        "pursuit": pursuit,
        "acceptance_matrix": matrix_result,
        "teaming_review_verdict": (
            "READY_FOR_PAID_TEAMING_REVIEW"
            if pursuit["teaming_build_state"] == "READY"
            else "HOLD_RESPONSE_WINDOW"
        ),
        "submission_verdict": pursuit["submission_state"],
        **AUTHORITY_FALSE,
    }
    return _add_receipt(packet)


def verify_evidence(bundle: Any, manifest: Any, matrix: Any, trusted_as_of: str) -> bool:
    if type(bundle) is not dict:
        return False
    return canonical_json(bundle) == canonical_json(compile_evidence(manifest, matrix, trusted_as_of))
