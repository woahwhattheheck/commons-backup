"""Deterministic UArk historical replay and process-time current checks."""
from __future__ import annotations

import copy
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CORE_PATH = Path(__file__).with_name("_qualifier_core.py").resolve()
_SPEC = importlib.util.spec_from_file_location(
    "uark_rfp09112026_qualifier_historical_core", _CORE_PATH
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load UArk qualifier core from {_CORE_PATH}")
_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)

InputError = _core.InputError
canonical_json = _core.canonical_json
sha256_obj = _core.sha256_obj
read_json_file = _core.read_json_file

CURRENT_VERIFICATION_SCHEMA = "uark-rfp09112026-current-verification/v1"
CURRENT_AUTHORITY_MODE = "ISOLATED_CLI_PROCESS_UTC"
ADDENDUM_RECHECK_BOUNDARY_UTC = "2026-10-06T05:00:00Z"

# The historical core stays byte-for-byte intact. A second instance evaluates
# the acquired October 3 generation using the same qualification rules.
CURRENT_SOURCE_GENERATION = {
    "rfp_number": "09112026",
    "hogbid_url": "https://hogbid.uark.edu/",
    "rfp_url": "https://hogbid.uark.edu/RFP09112026_Document.pdf",
    "rfp_content_acquired": True,
    "rfp_page_count": 31,
    "standard_terms_state": "ACQUIRED",
    "addenda_state": "ALL_LISTED_ACQUIRED",
    "hogbid_checked_at_utc": "2026-10-03T18:00:04Z",
    "standard_terms_url": "https://hogbid.uark.edu/RFP09112026_TsCs.docx",
    "standard_terms_sha256": "8fdf1f123a75b6c018b6a56a3a9439e521ab17389251fa22686bd1470a6fa7df",
    "addendum_1_url": "https://hogbid.uark.edu/Addendum_1.docx",
    "addendum_1_sha256": "e63bcfd9ebc65afb7df738275c563c7c2d1a260b8642f551558d9a064d551480",
    "rfp_word_url": "https://hogbid.uark.edu/WORD_RFP09112026_docx.docx",
    "rfp_word_sha256": "4b86951433a8f6e20e21ab3770a6f403257ac87adf6cfeaa9198dca2dc348c5a"
}
_CURRENT_SPEC = importlib.util.spec_from_file_location(
    "uark_rfp09112026_qualifier_current_core", _CORE_PATH
)
if _CURRENT_SPEC is None or _CURRENT_SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load UArk qualifier core from {_CORE_PATH}")
_current_core = importlib.util.module_from_spec(_CURRENT_SPEC)
_CURRENT_SPEC.loader.exec_module(_current_core)
_current_core.InputError = InputError
_current_core.EXPECTED_SOURCE_GENERATION = copy.deepcopy(CURRENT_SOURCE_GENERATION)
_current_core.SOURCE_FIELDS = frozenset(CURRENT_SOURCE_GENERATION)
_PACKET_FIELDS = frozenset({
    "schema", "operation", "owner", "model", "evaluated_at_utc", "buyer",
    "rfp_number", "question_deadline_utc", "proposal_deadline_utc",
    "last_planned_addendum_date", "internal_workshare_target_usd",
    "price_boundary", "source_generation", "candidate", "decision",
    "packet_receipt_sha256",
})


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InputError("current authority clock must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _refresh_receipts(packet: dict[str, Any]) -> dict[str, Any]:
    decision = packet["decision"]
    decision.pop("decision_receipt_sha256", None)
    decision["decision_receipt_sha256"] = sha256_obj(decision)
    packet.pop("packet_receipt_sha256", None)
    packet["packet_receipt_sha256"] = sha256_obj(packet)
    return packet


def _apply_temporal_policy(packet: dict[str, Any]) -> dict[str, Any]:
    evaluated = _dt(packet["evaluated_at_utc"])
    source_checked = _dt(packet["source_generation"]["hogbid_checked_at_utc"])
    recheck_boundary = _dt(ADDENDUM_RECHECK_BOUNDARY_UTC)
    blockers: list[str] = []
    if evaluated < source_checked:
        blockers.append("EVALUATION_PRECEDES_SOURCE_CAPTURE")
    if (
        evaluated >= recheck_boundary
        and source_checked < recheck_boundary
    ):
        blockers.append("POST_ADDENDUM_SOURCE_RECHECK_REQUIRED")
    decision = packet["decision"]
    risks = list(decision["risks"])
    if (
        packet["source_generation"] == CURRENT_SOURCE_GENERATION
        and source_checked < recheck_boundary
    ):
        risks.append("ADDENDA_MAY_STILL_ISSUE_THROUGH_2026_10_05_RECHECK_REQUIRED")
    if not blockers and sorted(set(risks)) == decision["risks"]:
        return packet
    decision["risks"] = sorted(set(risks))
    merged = list(decision["blockers"])
    for blocker in blockers:
        if blocker not in merged:
            merged.append(blocker)
    decision["blockers"] = merged
    if blockers:
        if decision["status"] != "NO_BID":
            decision["status"] = "HOLD"
        decision["submission_ready"] = False
    return _refresh_receipts(packet)


def compile_historical(intake: Any) -> dict[str, Any]:
    """Explicit-time deterministic replay; never CURRENT authority."""
    core = (
        _current_core
        if isinstance(intake, dict)
        and intake.get("source_generation") == CURRENT_SOURCE_GENERATION
        else _core
    )
    return _apply_temporal_policy(core.compile_qualification(intake))


def verify_packet_historical(packet: Any) -> bool:
    """Verify bytes and semantics at the packet's declared replay instant."""
    if not isinstance(packet, dict) or set(packet) != _PACKET_FIELDS:
        raise InputError("packet schema mismatch")
    receipt = packet.get("packet_receipt_sha256")
    if not isinstance(receipt, str) or not _core.SHA_RE.fullmatch(receipt):
        raise InputError("packet receipt invalid")
    unsigned = copy.deepcopy(packet)
    unsigned.pop("packet_receipt_sha256")
    if sha256_obj(unsigned) != receipt:
        raise InputError("packet receipt mismatch")
    expected = compile_historical({
        "schema": _core.SCHEMA,
        "evaluated_at_utc": packet["evaluated_at_utc"],
        "source_generation": packet["source_generation"],
        "candidate": packet["candidate"],
    })
    if packet != expected:
        raise InputError("packet semantic verification failed")
    return True


def _decision_body(decision: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(decision)
    value.pop("decision_receipt_sha256", None)
    return value


def _compile_at_now(intake: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(intake, dict):
        raise InputError("intake must be an object")
    if intake.get("source_generation") != CURRENT_SOURCE_GENERATION:
        raise InputError(
            "CURRENT source generation superseded or unreviewed; use current_candidate.json"
        )
    stamped = copy.deepcopy(intake)
    stamped["evaluated_at_utc"] = utc_text(now)
    return compile_historical(stamped)


def _verify_at_now(packet: Any, now: datetime) -> dict[str, Any]:
    verify_packet_historical(packet)
    if packet["source_generation"] != CURRENT_SOURCE_GENERATION:
        raise InputError("packet source generation is no longer current")
    if _dt(packet["evaluated_at_utc"]) > now:
        raise InputError("packet evaluation time is ahead of process UTC")
    current = compile_historical({
        "schema": _core.SCHEMA,
        "evaluated_at_utc": utc_text(now),
        "source_generation": packet["source_generation"],
        "candidate": packet["candidate"],
    })
    if _decision_body(packet["decision"]) != _decision_body(current["decision"]):
        raise InputError("packet decision is no longer current")
    verification = {
        "schema": CURRENT_VERIFICATION_SCHEMA,
        "authority_mode": CURRENT_AUTHORITY_MODE,
        "verified_at_utc": utc_text(now),
        "packet_receipt_sha256": packet["packet_receipt_sha256"],
        "current_decision_receipt_sha256": current["decision"][
            "decision_receipt_sha256"
        ],
        "decision_status": current["decision"]["status"],
        "current": True,
        "external_actions_authorized": False,
    }
    verification["verification_receipt_sha256"] = sha256_obj(verification)
    return verification
