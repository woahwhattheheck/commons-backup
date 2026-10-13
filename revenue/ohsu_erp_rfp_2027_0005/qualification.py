from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from typing import Any, Iterable

SCHEMA_NOTICE = "ohsu-erp-public-notice/v1"
SCHEMA_FACTS = "ohsu-erp-bidder-facts/v1"
SCHEMA_PACKET = "ohsu-erp-owner-review-packet/v1"
SCHEMA_INPUT = "ohsu-erp-compile-input/v1"
SCHEMA_VERIFY_INPUT = "ohsu-erp-verify-input/v1"
MAX_STDIN_BYTES = 1_048_576
SHA256_CHARS = frozenset("0123456789abcdef")

OPPORTUNITY_ID = "RFP-2027-0005"
TITLE = "Enterprise Resource Planning (ERP) Assessment and Advisory Services"
SOURCE_URL = "https://www.ohsu.edu/procurement/bids"
ISSUED_DATE = "2026-08-21"
INTENT_DATE = "2026-09-16"
PROPOSAL_DATE = "2026-09-25"
def _fixed_contact() -> dict[str, str]:
    return {
        "name": "Royce Bitter",
        "role": "Senior Sourcing Manager",
        "email": "bitterr@ohsu.edu",
    }


def _public_scope() -> list[str]:
    return [
        "comprehensive current ERP landscape assessment",
        "future-state requirements",
        "ERP modernization roadmap aligned with institutional goals, operational scale, and regulatory obligations",
    ]


def _workshare() -> dict[str, Any]:
    return {
        "commercial_status": "PROPOSED_NOT_ACCEPTED",
        "fixed_price_usd": 12500,
        "delivery_window_status": "TO_NEGOTIATE",
        "scope": [
            "source-bound requirement register across interviews, current-state artifacts, controls, and future-state needs",
            "requirement to evidence to owner to gap/risk traceability with orphan detection",
            "deterministic coverage and contradiction reports across finance, HR, supply-chain, and administrative workflows",
            "decision receipts separating observed current-state evidence, stakeholder assertions, and consultant recommendations",
            "AI/automation opportunity entries with explicit human approval, source provenance, and control requirements",
        ],
    }


def _authority_false() -> dict[str, bool]:
    return {
        "buyer_contact_authorized": False,
        "intent_to_bid_authorized": False,
        "proposal_submission_authorized": False,
        "prime_eligibility_verified_by_ohsu": False,
        "teaming_commitment_accepted": False,
        "contract_accepted": False,
        "payment_verified": False,
        "revenue_recognized": False,
    }


class ContractError(ValueError):
    pass


def _is_exact_bool(value: Any) -> bool:
    return type(value) is bool


def _require_keys(obj: dict[str, Any], *, exact: set[str], where: str) -> None:
    got = set(obj)
    if got != exact:
        missing = sorted(exact - got)
        extra = sorted(got - exact)
        raise ContractError(f"{where} keys mismatch; missing={missing} extra={extra}")


def _require_sha256(value: Any, where: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or len(value) != 64 or any(c not in SHA256_CHARS for c in value):
        raise ContractError(f"{where} must be exact lowercase sha256")
    return value


def _require_iso_date(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{where} must be YYYY-MM-DD")
    try:
        parsed = _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{where} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{where} must be canonical YYYY-MM-DD")
    return value


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _parse_strict_json(raw: bytes, where: str) -> Any:
    if len(raw) > MAX_STDIN_BYTES:
        raise ContractError(f"{where} exceeds {MAX_STDIN_BYTES} bytes")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{where} is not strict UTF-8") from exc

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ContractError(f"{where} duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(token: str) -> Any:
        raise ContractError(f"{where} non-finite JSON number: {token}")

    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=bad_constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError(f"{where} invalid JSON") from exc


def _normalize_notice(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError("notice must be object")
    expected = {
        "schema", "opportunity_id", "title", "source_url", "observed_utc", "issued_date",
        "intent_to_bid_date", "proposal_due_date", "contact", "public_scope",
        "controlling_rfp_pack_materialized",
    }
    _require_keys(obj, exact=expected, where="notice")
    fixed = {
        "schema": SCHEMA_NOTICE,
        "opportunity_id": OPPORTUNITY_ID,
        "title": TITLE,
        "source_url": SOURCE_URL,
        "issued_date": ISSUED_DATE,
        "intent_to_bid_date": INTENT_DATE,
        "proposal_due_date": PROPOSAL_DATE,
        "contact": _fixed_contact(),
        "public_scope": _public_scope(),
        "controlling_rfp_pack_materialized": False,
    }
    for key, value in fixed.items():
        if obj[key] != value:
            raise ContractError(f"notice.{key} differs from reviewed public notice profile")
    observed = obj["observed_utc"]
    if not isinstance(observed, str) or not observed.endswith("Z"):
        raise ContractError("notice.observed_utc must be UTC Z timestamp")
    try:
        dt = _dt.datetime.fromisoformat(observed[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("notice.observed_utc invalid") from exc
    if dt.tzinfo is None or dt.utcoffset() != _dt.timedelta(0):
        raise ContractError("notice.observed_utc must be UTC")
    return json.loads(_canonical(obj))


def _normalize_requirement_registry(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractError("facts.requirements must be list")
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(value):
        where = f"facts.requirements[{idx}]"
        if not isinstance(raw, dict):
            raise ContractError(f"{where} must be object")
        _require_keys(raw, exact={"requirement_id", "mandatory", "state", "evidence_sha256"}, where=where)
        rid = raw["requirement_id"]
        if not isinstance(rid, str) or not rid or len(rid) > 128:
            raise ContractError(f"{where}.requirement_id invalid")
        if rid in seen_ids:
            raise ContractError(f"duplicate requirement_id: {rid}")
        seen_ids.add(rid)
        mandatory = raw["mandatory"]
        if not _is_exact_bool(mandatory):
            raise ContractError(f"{where}.mandatory must be bool")
        state = raw["state"]
        if state not in {"SATISFIED", "MISSING", "UNKNOWN", "NOT_APPLICABLE"}:
            raise ContractError(f"{where}.state invalid")
        evidence = _require_sha256(raw["evidence_sha256"], f"{where}.evidence_sha256", allow_none=True)
        if state == "SATISFIED" and evidence is None:
            raise ContractError(f"{where} SATISFIED requires evidence_sha256")
        if state != "SATISFIED" and evidence is not None:
            raise ContractError(f"{where} non-SATISFIED must not carry evidence_sha256")
        if mandatory and state == "NOT_APPLICABLE":
            raise ContractError(f"{where} mandatory requirement cannot be NOT_APPLICABLE")
        out.append({
            "requirement_id": rid,
            "mandatory": mandatory,
            "state": state,
            "evidence_sha256": evidence,
        })
    out.sort(key=lambda row: row["requirement_id"])
    return out


def _normalize_facts(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError("facts must be object")
    expected = {
        "schema", "route", "controlling_pack_sha256", "requirements", "prime_commitment",
        "intent_receipt", "owner_reviewed",
    }
    _require_keys(obj, exact=expected, where="facts")
    if obj["schema"] != SCHEMA_FACTS:
        raise ContractError("facts.schema invalid")
    route = obj["route"]
    if route not in {"UNKNOWN", "TEAMING", "PRIME"}:
        raise ContractError("facts.route invalid")
    pack = _require_sha256(obj["controlling_pack_sha256"], "facts.controlling_pack_sha256", allow_none=True)
    reqs = _normalize_requirement_registry(obj["requirements"])
    if not _is_exact_bool(obj["owner_reviewed"]):
        raise ContractError("facts.owner_reviewed must be bool")

    pc = obj["prime_commitment"]
    if not isinstance(pc, dict):
        raise ContractError("facts.prime_commitment must be object")
    _require_keys(pc, exact={"status", "evidence_sha256"}, where="facts.prime_commitment")
    if pc["status"] not in {"UNCONFIRMED", "CONFIRMED"}:
        raise ContractError("facts.prime_commitment.status invalid")
    pc_sha = _require_sha256(pc["evidence_sha256"], "facts.prime_commitment.evidence_sha256", allow_none=True)
    if (pc["status"] == "CONFIRMED") != (pc_sha is not None):
        raise ContractError("confirmed prime commitment must have evidence; unconfirmed must not")

    ir = obj["intent_receipt"]
    if ir is not None:
        if not isinstance(ir, dict):
            raise ContractError("facts.intent_receipt must be object or null")
        _require_keys(ir, exact={"provider_event_sha256", "submitted_date"}, where="facts.intent_receipt")
        ir_sha = _require_sha256(ir["provider_event_sha256"], "facts.intent_receipt.provider_event_sha256")
        ir_date = _require_iso_date(ir["submitted_date"], "facts.intent_receipt.submitted_date")
        ir = {"provider_event_sha256": ir_sha, "submitted_date": ir_date}

    if pack is None and reqs:
        raise ContractError("requirements cannot be asserted before controlling pack digest exists")
    return {
        "schema": SCHEMA_FACTS,
        "route": route,
        "controlling_pack_sha256": pack,
        "requirements": reqs,
        "prime_commitment": {"status": pc["status"], "evidence_sha256": pc_sha},
        "intent_receipt": ir,
        "owner_reviewed": obj["owner_reviewed"],
    }


def _mandatory_blockers(reqs: Iterable[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for row in reqs:
        if row["mandatory"] and row["state"] != "SATISFIED":
            blockers.append(f"MANDATORY_{row['state']}:{row['requirement_id']}")
    return blockers


def _compile_at(notice_obj: Any, facts_obj: Any, today: _dt.date) -> dict[str, Any]:
    notice = _normalize_notice(notice_obj)
    facts = _normalize_facts(facts_obj)
    if type(today) is not _dt.date:
        raise ContractError("internal evaluation date invalid")

    intent = _dt.date.fromisoformat(INTENT_DATE)
    proposal = _dt.date.fromisoformat(PROPOSAL_DATE)
    blockers: list[str] = []
    actions: list[str] = []

    if today > proposal:
        status = "CLOSED_DEADLINE"
        blockers.append("PROPOSAL_DATE_PASSED")
        actions.append("ARCHIVE_OR_WAIT_FOR_REISSUE")
    elif today == proposal:
        status = "HOLD_DEADLINE_TIME_UNVERIFIED"
        blockers.append("PUBLIC_NOTICE_HAS_DATE_BUT_NO_VERIFIED_PROPOSAL_TIME")
        actions.append("VERIFY_CONTROLLING_PORTAL_TIME_BEFORE_ANY_ACTION")
    elif facts["intent_receipt"] is None and today > intent:
        status = "HOLD_INTENT_DEADLINE"
        blockers.append("NO_INTENT_RECEIPT_AFTER_PUBLIC_INTENT_DATE")
        actions.append("VERIFY_WITH_PROCUREMENT_WHETHER_BID_REMAINS_ELIGIBLE")
    elif facts["intent_receipt"] is None and today == intent:
        status = "HOLD_INTENT_TIME_UNVERIFIED"
        blockers.append("PUBLIC_NOTICE_HAS_DATE_BUT_NO_VERIFIED_INTENT_TIME")
        actions.append("VERIFY_CONTROLLING_PORTAL_TIME_AND_INTENT_STATUS")
    elif facts["controlling_pack_sha256"] is None:
        status = "HOLD_CONTROLLING_PACK"
        blockers.append("CONTROLLING_RFP_PACK_NOT_MATERIALIZED")
        actions.append("OBTAIN_CONTROLLING_RFP_PACK")
        if facts["route"] in {"UNKNOWN", "TEAMING"}:
            actions.append("QUALIFY_PAID_TEAMING_ROUTE")
    elif not facts["requirements"]:
        status = "HOLD_REQUIREMENT_REGISTRY"
        blockers.append("CONTROLLING_PACK_HAS_NO_REVIEWED_REQUIREMENT_REGISTRY")
        actions.append("EXTRACT_AND_REVIEW_MANDATORY_REQUIREMENTS")
    else:
        blockers.extend(_mandatory_blockers(facts["requirements"]))
        if blockers:
            status = "HOLD_MANDATORY_REQUIREMENTS"
            actions.append("CLOSE_OR_ESCALATE_REQUIREMENT_GAPS")
        elif not facts["owner_reviewed"]:
            status = "HOLD_OWNER_REVIEW"
            blockers.append("FACTS_NOT_OWNER_REVIEWED")
            actions.append("OWNER_REVIEW_REQUIREMENT_EVIDENCE")
        elif facts["route"] == "UNKNOWN":
            status = "HOLD_ROUTE_UNKNOWN"
            blockers.append("PRIME_OR_TEAMING_ROUTE_NOT_SELECTED")
            actions.append("SELECT_PRIME_OR_TEAMING_ROUTE")
        elif facts["route"] == "TEAMING" and facts["prime_commitment"]["status"] != "CONFIRMED":
            status = "TEAMING_CANDIDATE"
            blockers.append("NO_CONFIRMED_PRIME_TEAMING_COMMITMENT")
            actions.append("SEEK_PAID_TEAMING_COMMITMENT")
        elif facts["route"] == "TEAMING":
            status = "READY_FOR_OWNER_TEAMING_REVIEW"
            actions.append("OWNER_REVIEW_PAID_WORKSHARE_WITH_CONFIRMED_PRIME")
        else:
            status = "READY_FOR_OWNER_PRIME_REVIEW"
            actions.append("OWNER_REVIEW_PRIME_ELIGIBILITY_AND_RESPONSE_PLAN")

    if facts["intent_receipt"] is not None:
        if _dt.date.fromisoformat(facts["intent_receipt"]["submitted_date"]) > intent:
            blockers.append("INTENT_RECEIPT_DATE_AFTER_PUBLIC_INTENT_DATE")
            if status.startswith("READY_"):
                status = "HOLD_INTENT_CHRONOLOGY"
            if "VERIFY_INTENT_ACCEPTANCE_WITH_PROCUREMENT" not in actions:
                actions.append("VERIFY_INTENT_ACCEPTANCE_WITH_PROCUREMENT")

    packet = {
        "schema": SCHEMA_PACKET,
        "opportunity": {
            "opportunity_id": OPPORTUNITY_ID,
            "title": TITLE,
            "source_url": SOURCE_URL,
            "notice_sha256": _sha(notice),
            "controlling_pack_sha256": facts["controlling_pack_sha256"],
            "intent_to_bid_date": INTENT_DATE,
            "proposal_due_date": PROPOSAL_DATE,
        },
        "evaluation_date_utc": today.isoformat(),
        "route": facts["route"],
        "status": status,
        "blockers": sorted(set(blockers)),
        "next_actions": actions,
        "facts_sha256": _sha(facts),
        "requirements_sha256": _sha(facts["requirements"]),
        "workshare": _workshare(),
        "authority": _authority_false(),
        "truth_boundary": {
            "public_notice_is_controlling_pack": False,
            "controlling_pack_authenticity_verified": False,
            "requirement_evidence_authenticity_verified": False,
            "strongest_output_is_owner_review_only": True,
        },
    }
    packet["packet_sha256"] = _sha(packet)
    return packet


def _today_utc() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def compile_current(notice_obj: Any, facts_obj: Any) -> dict[str, Any]:
    """Compile a current owner-review packet using process-owned UTC date."""
    return _compile_at(notice_obj, facts_obj, _today_utc())


def verify_current(packet_obj: Any, notice_obj: Any, facts_obj: Any) -> bool:
    """Recompile against process-owned current date and require byte-equivalent semantics."""
    if not isinstance(packet_obj, dict):
        raise ContractError("packet must be object")
    expected = compile_current(notice_obj, facts_obj)
    if _canonical(packet_obj) != _canonical(expected):
        raise ContractError("packet does not match current compilation")
    return True


def _read_stdin() -> bytes:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        raise ContractError(f"stdin exceeds {MAX_STDIN_BYTES} bytes")
    return raw


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["compile"], ["verify"]):
        print("usage: python -m revenue.ohsu_erp_rfp_2027_0005.qualification {compile|verify}", file=sys.stderr)
        return 2
    try:
        obj = _parse_strict_json(_read_stdin(), "stdin")
        if not isinstance(obj, dict):
            raise ContractError("stdin root must be object")
        if args == ["compile"]:
            _require_keys(obj, exact={"schema", "notice", "facts"}, where="compile input")
            if obj["schema"] != SCHEMA_INPUT:
                raise ContractError("compile input schema invalid")
            out = compile_current(obj["notice"], obj["facts"])
        else:
            _require_keys(obj, exact={"schema", "notice", "facts", "packet"}, where="verify input")
            if obj["schema"] != SCHEMA_VERIFY_INPUT:
                raise ContractError("verify input schema invalid")
            verify_current(obj["packet"], obj["notice"], obj["facts"])
            out = {"schema": "ohsu-erp-verification/v1", "valid": True, "packet_sha256": obj["packet"]["packet_sha256"]}
        sys.stdout.buffer.write(_canonical(out) + b"\n")
        return 0
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
