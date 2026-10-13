"""Hardened source and UAT evidence compiler for UNC AP automation pursuit.

Public source readiness is rooted in the checked-in ledger plus retained bytes.
The legacy ledger is admitted only in its existing fail-closed form.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

__all__ = [
    "SOLICITATION_ID", "BUYER", "FIRST_PARTY_URL",
    "COMMERCIAL_HYPOTHESIS_USD", "COMMERCIAL_STATE",
    "SOURCE_SCHEMA", "SOURCE_MANIFEST_SCHEMA", "REQUEST_SCHEMA", "ACK_SCHEMA",
    "ContractError", "load_strict_json", "canonical_bytes", "receipt",
    "load_source_ledger", "compile_source", "_compile_source_at",
    "expected_integration_evidence", "evaluate_invoice_case",
    "compile_partner", "compile_bundle", "_compile_bundle_at",
]

SOLICITATION_ID = "65-RFP062926KJM"
BUYER = "University of North Carolina at Chapel Hill"
FIRST_PARTY_URL = (
    "https://evp.nc.gov/solicitations/details/"
    "?id=9c0cbdc8-f373-f111-ab0d-001dd800b811"
)
COMMERCIAL_HYPOTHESIS_USD = 12_000
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"

SOURCE_SCHEMA = "commons.unc-ap-ai-source-ledger/v2"
SOURCE_MANIFEST_SCHEMA = "commons.unc-ap-ai-source-manifest/v1"
REQUEST_SCHEMA = "commons.unc-ap-ai-peoplesoft-request/v1"
ACK_SCHEMA = "commons.unc-ap-ai-peoplesoft-ack/v1"
_SOURCE_LEDGER_PATH = Path(__file__).with_name("source_ledger.json")
_MAX_LEDGER_BYTES = 131_072
_MAX_DOCUMENTS = 64
_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DOC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,159}$")
_REQUIRED_AUDIT = (
    "received", "extracted", "validated", "matched",
    "routing_started", "routing_completed", "erp_staged",
)


class ContractError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def _reject_float(value: str) -> None:
    raise ContractError(f"floating-point JSON is not admitted: {value}")


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_strict_json(raw: str | bytes) -> Any:
    if type(raw) is bytes:
        if len(raw) > _MAX_LEDGER_BYTES:
            raise ContractError("JSON input exceeds byte limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("JSON input must be UTF-8") from exc
    elif type(raw) is str:
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("JSON input contains invalid Unicode") from exc
        if len(encoded) > _MAX_LEDGER_BYTES:
            raise ContractError("JSON input exceeds byte limit")
        text = raw
    else:
        raise ContractError("JSON input must be exact str or bytes")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("invalid JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractError(f"not canonical-json encodable: {exc}") from exc


def receipt(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _is_exact_int(value: Any) -> bool:
    return type(value) is int


def _is_exact_bool(value: Any) -> bool:
    return type(value) is bool


def _require_exact_keys(obj: Any, required: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise ContractError(f"{label} must be object")
    missing = required - set(obj)
    extra = set(obj) - required
    if missing or extra:
        raise ContractError(
            f"{label} keys mismatch missing={sorted(missing)} extra={sorted(extra)}"
        )
    return obj


def _require_text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{label} must be non-empty string")
    return value


def _require_hash(value: Any, label: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ContractError(f"{label} must be lowercase sha256")
    return value


def _parse_time(value: Any, label: str) -> datetime:
    text = _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


_SOURCE_KEYS = {
    "schema", "buyer", "solicitation_id", "first_party_url", "status",
    "observed_at", "offer_due_at", "source_generation", "required_documents",
}
_LEGACY_SOURCE_KEYS = {
    "buyer", "solicitation_id", "first_party_url", "status",
    "observed_at", "offer_due_at", "exact_current_bytes_sha256",
    "addenda_complete",
}
_DOCUMENT_KEYS = {"name", "sha256"}


def _validate_source_ledger(ledger: Any) -> dict[str, Any]:
    ledger = _require_exact_keys(ledger, _SOURCE_KEYS, "source_ledger")
    if ledger["schema"] != SOURCE_SCHEMA:
        raise ContractError("source ledger schema drift")
    if ledger["buyer"] != BUYER:
        raise ContractError("buyer identity drift")
    if ledger["solicitation_id"] != SOLICITATION_ID:
        raise ContractError("solicitation identity drift")
    if ledger["first_party_url"] != FIRST_PARTY_URL:
        raise ContractError("first-party URL drift")
    _require_text(ledger["status"], "status")
    observed = _parse_time(ledger["observed_at"], "observed_at")
    due = _parse_time(ledger["offer_due_at"], "offer_due_at")
    if due <= observed:
        raise ContractError("offer_due_at must be after observed_at")

    generation = ledger["source_generation"]
    documents = ledger["required_documents"]
    if generation is None or documents is None:
        if generation is not None or documents is not None:
            raise ContractError("source_generation and required_documents bind together")
        return ledger

    _require_hash(generation, "source_generation")
    if type(documents) is not list or not 1 <= len(documents) <= _MAX_DOCUMENTS:
        raise ContractError("required_documents must be a non-empty bounded list")
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    for index, item in enumerate(documents):
        item = _require_exact_keys(item, _DOCUMENT_KEYS, f"required_documents[{index}]")
        name = item["name"]
        if type(name) is not str or _DOC_NAME.fullmatch(name) is None:
            raise ContractError("document name has invalid shape")
        if name in names:
            raise ContractError(f"duplicate required document: {name}")
        names.add(name)
        digest = _require_hash(item["sha256"], f"required_documents[{index}].sha256")
        normalized.append({"name": name, "sha256": digest})
    normalized.sort(key=lambda row: row["name"])
    expected_generation = receipt(
        {"schema": SOURCE_MANIFEST_SCHEMA, "documents": normalized}
    )
    if generation != expected_generation:
        raise ContractError("source_generation does not bind required_documents")
    return ledger


def load_source_ledger() -> dict[str, Any]:
    """Load fixed repo metadata; legacy form is accepted only fail-closed."""
    try:
        raw = _SOURCE_LEDGER_PATH.read_bytes()
    except OSError as exc:
        raise ContractError("cannot read checked-in source ledger") from exc
    if len(raw) > _MAX_LEDGER_BYTES:
        raise ContractError("source ledger exceeds byte limit")
    value = load_strict_json(raw)
    if type(value) is dict and set(value) == _LEGACY_SOURCE_KEYS:
        if value["exact_current_bytes_sha256"] is not None:
            raise ContractError("legacy ledger digest cannot promote source readiness")
        if value["addenda_complete"] is not False:
            raise ContractError("legacy addenda flag cannot promote source readiness")
        value = {
            "schema": SOURCE_SCHEMA,
            "buyer": value["buyer"],
            "solicitation_id": value["solicitation_id"],
            "first_party_url": value["first_party_url"],
            "status": value["status"],
            "observed_at": value["observed_at"],
            "offer_due_at": value["offer_due_at"],
            "source_generation": None,
            "required_documents": None,
        }
    return _validate_source_ledger(value)


def _validate_retained_documents(value: Any) -> dict[str, bytes]:
    if type(value) is not dict:
        raise ContractError("retained_documents must be an object of exact bytes")
    if len(value) > _MAX_DOCUMENTS:
        raise ContractError("too many retained documents")
    out: dict[str, bytes] = {}
    total = 0
    for name, raw in value.items():
        if type(name) is not str or _DOC_NAME.fullmatch(name) is None:
            raise ContractError("retained document name has invalid shape")
        if type(raw) is not bytes:
            raise ContractError("retained document values must be exact bytes")
        total += len(raw)
        if len(raw) > _MAX_DOCUMENT_BYTES or total > _MAX_DOCUMENT_BYTES:
            raise ContractError("retained document byte limit exceeded")
        out[name] = raw
    return out


def _compile_source_at(
    ledger: Any, retained_documents: Any, *, as_of: datetime
) -> dict[str, Any]:
    ledger = _validate_source_ledger(ledger)
    documents = _validate_retained_documents(retained_documents)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ContractError("as_of must be timezone-aware datetime")
    now = as_of.astimezone(timezone.utc)
    observed = _parse_time(ledger["observed_at"], "observed_at")
    due = _parse_time(ledger["offer_due_at"], "offer_due_at")
    if now < observed:
        raise ContractError("as_of predates source observation")

    state = "SOURCE_CANDIDATE" if ledger["status"] == "OPEN" else "HOLD_NOT_OPEN"
    manifest = ledger["required_documents"]
    generation = ledger["source_generation"]
    computed_documents: list[dict[str, str]] = []

    if now >= due:
        state = "HOLD_DEADLINE"
    elif manifest is None:
        state = "HOLD_SOURCE_BYTES"
    else:
        expected_names = {item["name"] for item in manifest}
        if set(documents) != expected_names:
            state = "HOLD_SOURCE_BYTES"
        else:
            for item in sorted(manifest, key=lambda row: row["name"]):
                digest = hashlib.sha256(documents[item["name"]]).hexdigest()
                computed_documents.append({"name": item["name"], "sha256": digest})
                if digest != item["sha256"]:
                    state = "HOLD_SOURCE_BYTES"
            if state == "SOURCE_CANDIDATE":
                state = "SOURCE_BOUND"

    compiled = {
        "buyer": BUYER,
        "solicitation_id": SOLICITATION_ID,
        "first_party_url": FIRST_PARTY_URL,
        "status": ledger["status"],
        "observed_at": ledger["observed_at"],
        "offer_due_at": ledger["offer_due_at"],
        "evaluated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_generation": generation,
        "computed_documents": computed_documents,
        "state": state,
        "authority": {
            "buyer_contact": False, "partner_contact": False,
            "evp_mutation": False, "submission": False,
            "peoplesoft_write": False, "payment": False,
            "contract_acceptance": False, "revenue_recognition": False,
        },
    }
    compiled["receipt_sha256"] = receipt(compiled)
    return compiled


def compile_source(retained_documents: Any) -> dict[str, Any]:
    """Current-time public gate: fixed ledger + retained bytes + process clock."""
    return _compile_source_at(
        load_source_ledger(),
        retained_documents,
        as_of=datetime.now(timezone.utc),
    )


_INTEGRATION_KEYS = {
    "request_sha256", "ack_sha256", "effect_key", "retry_effect_key",
    "effect_count", "retry_count",
}
_CASE_KEYS = {
    "invoice_id", "supplier_id", "extracted_supplier_id",
    "expected_amount_cents", "extracted_amount_cents", "match_mode",
    "purchase_order_amount_cents", "receipt_amount_cents",
    "routing_signoff_needed", "routing_signoff_present",
    "extraction_fields_total", "extraction_fields_correct", "duplicate_seen",
    "integration", "audit_events",
}


def _ordered_contains(events: list[str], required: tuple[str, ...]) -> bool:
    position = 0
    for event in events:
        if position < len(required) and event == required[position]:
            position += 1
    return position == len(required)


def _request_semantics(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "invoice_id": case["invoice_id"],
        "supplier_id": case["supplier_id"],
        "extracted_supplier_id": case["extracted_supplier_id"],
        "expected_amount_cents": case["expected_amount_cents"],
        "extracted_amount_cents": case["extracted_amount_cents"],
        "match_mode": case["match_mode"],
        "purchase_order_amount_cents": case["purchase_order_amount_cents"],
        "receipt_amount_cents": case["receipt_amount_cents"],
        "routing_signoff_needed": case["routing_signoff_needed"],
        "routing_signoff_present": case["routing_signoff_present"],
        "extraction_fields_total": case["extraction_fields_total"],
        "extraction_fields_correct": case["extraction_fields_correct"],
        "duplicate_seen": case["duplicate_seen"],
    }


def expected_integration_evidence(case: Mapping[str, Any]) -> dict[str, Any]:
    """Build synthetic correlation fields; this is not provider authentication."""
    if type(case) is not dict:
        raise ContractError("case must be object")
    needed = _CASE_KEYS - {"integration"}
    if not needed.issubset(case):
        raise ContractError("case is missing fields required for request binding")
    # The business identity is supplier + invoice, not invoice number alone.
    # Canonical structured encoding avoids delimiter aliases. Amount changes do
    # not create a new effect identity for the same business invoice.
    effect_key = "invoice:" + receipt({
        "supplier_id": _require_text(case["supplier_id"], "supplier_id"),
        "invoice_id": _require_text(case["invoice_id"], "invoice_id"),
    })
    request_sha = receipt(_request_semantics(case))
    ack_sha = receipt(
        {
            "schema": ACK_SCHEMA,
            "request_sha256": request_sha,
            "effect_key": effect_key,
            "result": "ACCEPTED",
        }
    )
    return {
        "request_sha256": request_sha,
        "ack_sha256": ack_sha,
        "effect_key": effect_key,
        "retry_effect_key": effect_key,
        "effect_count": 1,
        "retry_count": 1,
    }


def evaluate_invoice_case(
    case: Any, *, extraction_threshold_basis_points: int
) -> dict[str, Any]:
    case = _require_exact_keys(case, _CASE_KEYS, "case")
    invoice_id = _require_text(case["invoice_id"], "invoice_id")
    supplier_id = _require_text(case["supplier_id"], "supplier_id")
    extracted_supplier = _require_text(
        case["extracted_supplier_id"], "extracted_supplier_id"
    )
    for name in (
        "expected_amount_cents", "extracted_amount_cents",
        "extraction_fields_total", "extraction_fields_correct",
    ):
        if not _is_exact_int(case[name]):
            raise ContractError(f"{name} must be int")
    if case["expected_amount_cents"] < 0 or case["extracted_amount_cents"] < 0:
        raise ContractError("amount cents must be non-negative")
    if case["extraction_fields_total"] <= 0:
        raise ContractError("extraction_fields_total must be positive")
    if not 0 <= case["extraction_fields_correct"] <= case["extraction_fields_total"]:
        raise ContractError("extraction_fields_correct out of range")
    if not _is_exact_int(extraction_threshold_basis_points):
        raise ContractError("extraction threshold must be int")
    if not 0 <= extraction_threshold_basis_points <= 10_000:
        raise ContractError("extraction threshold out of range")
    for name in (
        "routing_signoff_needed", "routing_signoff_present", "duplicate_seen",
    ):
        if not _is_exact_bool(case[name]):
            raise ContractError(f"{name} must be bool")

    mode = case["match_mode"]
    if mode not in {"NONE", "TWO_WAY", "THREE_WAY"}:
        raise ContractError("match_mode unsupported")
    for name in ("purchase_order_amount_cents", "receipt_amount_cents"):
        value = case[name]
        if value is not None and (not _is_exact_int(value) or value < 0):
            raise ContractError(f"{name} must be null or non-negative int")

    integration = _require_exact_keys(case["integration"], _INTEGRATION_KEYS, "integration")
    request_sha = _require_hash(integration["request_sha256"], "request_sha256")
    ack_sha = _require_hash(integration["ack_sha256"], "ack_sha256")
    effect_key = _require_text(integration["effect_key"], "effect_key")
    retry_effect_key = integration["retry_effect_key"]
    if retry_effect_key is not None and (
        type(retry_effect_key) is not str or not retry_effect_key
    ):
        raise ContractError("retry_effect_key must be null or non-empty string")
    for name in ("effect_count", "retry_count"):
        if not _is_exact_int(integration[name]) or integration[name] < 0:
            raise ContractError(f"{name} must be non-negative int")

    events = case["audit_events"]
    if type(events) is not list or not all(type(event) is str for event in events):
        raise ContractError("audit_events must be list[str]")
    if len(set(events)) != len(events):
        raise ContractError("audit_events must not contain duplicates")

    accuracy_bp = (
        case["extraction_fields_correct"] * 10_000 // case["extraction_fields_total"]
    )
    expected = expected_integration_evidence(case)

    disposition = "PASS"
    if case["duplicate_seen"]:
        disposition = "HOLD_DUPLICATE"
    elif accuracy_bp < extraction_threshold_basis_points:
        disposition = "HOLD_EXTRACTION"
    elif supplier_id != extracted_supplier:
        disposition = "HOLD_SUPPLIER"
    elif case["expected_amount_cents"] != case["extracted_amount_cents"]:
        disposition = "HOLD_AMOUNT"
    elif mode == "TWO_WAY" and (
        case["purchase_order_amount_cents"] is None
        or case["purchase_order_amount_cents"] != case["expected_amount_cents"]
    ):
        disposition = "HOLD_MATCH"
    elif mode == "THREE_WAY" and (
        case["purchase_order_amount_cents"] is None
        or case["receipt_amount_cents"] is None
        or case["purchase_order_amount_cents"] != case["expected_amount_cents"]
        or case["receipt_amount_cents"] != case["expected_amount_cents"]
    ):
        disposition = "HOLD_MATCH"
    elif case["routing_signoff_needed"] and not case["routing_signoff_present"]:
        disposition = "HOLD_ROUTING_SIGNOFF"
    elif (
        effect_key != expected["effect_key"]
        or request_sha != expected["request_sha256"]
        or ack_sha != expected["ack_sha256"]
        or integration["effect_count"] != 1
        or (integration["retry_count"] == 0 and retry_effect_key is not None)
        or (integration["retry_count"] > 0 and retry_effect_key != expected["effect_key"])
    ):
        disposition = "HOLD_INTEGRATION"
    elif not _ordered_contains(events, _REQUIRED_AUDIT):
        disposition = "HOLD_AUDIT"

    result = {
        "case_input_sha256": receipt(case),
        "supplier_id": supplier_id,
        "invoice_id": invoice_id,
        "match_mode": mode,
        "extraction_accuracy_basis_points": accuracy_bp,
        "internal_threshold_basis_points": extraction_threshold_basis_points,
        "disposition": disposition,
        "people_soft_effect_key": expected["effect_key"],
        "request_binding_sha256": expected["request_sha256"],
        "ack_binding_sha256": expected["ack_sha256"],
        "provider_ack_independently_authenticated": False,
        "audit_sequence_complete": _ordered_contains(events, _REQUIRED_AUDIT),
    }
    result["receipt_sha256"] = receipt(result)
    return result


_PARTNER_KEYS = {
    "name", "ap_automation_evidence", "peoplesoft_evidence",
    "route", "researched_at",
}


def compile_partner(candidate: Any) -> dict[str, Any]:
    candidate = _require_exact_keys(candidate, _PARTNER_KEYS, "partner")
    name = _require_text(candidate["name"], "partner.name")
    ap = _require_text(candidate["ap_automation_evidence"], "ap_automation_evidence")
    ps = _require_text(candidate["peoplesoft_evidence"], "peoplesoft_evidence")
    route = _require_text(candidate["route"], "partner.route")
    _parse_time(candidate["researched_at"], "partner.researched_at")
    result = {
        "partner_input_sha256": receipt(candidate),
        "researched_at": candidate["researched_at"],
        "name": name,
        "qualification_state": "RESEARCH_CANDIDATE",
        "ap_automation_evidence": ap,
        "peoplesoft_evidence": ps,
        "route": route,
        "outbound_authorized": False,
        "outreach_lease_required": True,
    }
    result["receipt_sha256"] = receipt(result)
    return result


def _compile_bundle_at(
    ledger: Any,
    retained_documents: Any,
    cases: Any,
    partners: Any,
    *,
    as_of: datetime,
    extraction_threshold_basis_points: int = 9_900,
) -> dict[str, Any]:
    if type(cases) is not list or not cases:
        raise ContractError("cases must be non-empty list")
    if type(partners) is not list or not partners:
        raise ContractError("partners must be non-empty list")
    source_result = _compile_source_at(
        ledger, retained_documents, as_of=as_of
    )
    case_results = [
        evaluate_invoice_case(
            case,
            extraction_threshold_basis_points=extraction_threshold_basis_points,
        )
        for case in cases
    ]
    partner_results = [compile_partner(candidate) for candidate in partners]
    # A self-reported duplicate flag is not a batch-level uniqueness proof.
    # Preserve all cases, and report every repeated business identity rather
    # than silently deduplicating or netting conflicting amount generations.
    identities: dict[tuple[str, str], int] = {}
    for case in cases:
        identity = (case["supplier_id"], case["invoice_id"])
        identities[identity] = identities.get(identity, 0) + 1
    conflicts = [
        {"supplier_id": supplier, "invoice_id": invoice, "case_count": count}
        for (supplier, invoice), count in sorted(identities.items())
        if count > 1
    ]
    if source_result["state"] != "SOURCE_BOUND":
        state = source_result["state"]
    elif conflicts:
        state = "HOLD_DUPLICATE"
    elif any(case["disposition"] != "PASS" for case in case_results):
        state = "HOLD_UAT"
    else:
        state = "INTERNAL_WORKSHARE_READY"
    bundle = {
        "batch_input_sha256": receipt({
            "cases": cases, "partners": partners,
            "extraction_threshold_basis_points": extraction_threshold_basis_points,
        }),
        "batch_conflicts": conflicts,
        "pursuit": "UNC_AP_AI_PEOPLESOFT",
        "commercial_hypothesis_usd": COMMERCIAL_HYPOTHESIS_USD,
        "commercial_state": COMMERCIAL_STATE,
        "booked_revenue_usd": 0,
        "cash_received_usd": 0,
        "source": source_result,
        "cases": case_results,
        "partners": partner_results,
        "state": state,
        "authority": {
            "buyer_contact": False, "partner_contact": False,
            "submission": False, "peoplesoft_write": False,
            "payment": False, "contract_acceptance": False,
            "revenue_recognition": False,
        },
    }
    bundle["receipt_sha256"] = receipt(bundle)
    return bundle


def compile_bundle(
    retained_documents: Any,
    cases: Any,
    partners: Any,
    *,
    extraction_threshold_basis_points: int = 9_900,
) -> dict[str, Any]:
    return _compile_bundle_at(
        load_source_ledger(),
        retained_documents,
        cases,
        partners,
        as_of=datetime.now(timezone.utc),
        extraction_threshold_basis_points=extraction_threshold_basis_points,
    )
