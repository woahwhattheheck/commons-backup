from __future__ import annotations

from datetime import datetime
from typing import Any

from .gate import (
    AdmissionError,
    Evaluation,
    READY,
    _evaluate_at,
    _utc,
    digest,
    evaluate as _evaluate_current,
    verify as _verify_current,
)

AUDIT_RECEIPT_SCHEMA = "paid-pilot-admission-audit-receipt/v1"
AUDIT_READY = "AUDIT_WOULD_HAVE_BEEN_READY"


def evaluate_current(packet: Any) -> Evaluation:
    """Evaluate current admission using only the host process UTC clock."""
    return _evaluate_current(packet)


def evaluate(packet: Any) -> Evaluation:
    """Compatibility alias for evaluate_current; caller clocks are not accepted."""
    return evaluate_current(packet)


def _audit_status(decision_status: str) -> str:
    if decision_status == READY:
        return AUDIT_READY
    return f"AUDIT_{decision_status}"


def audit_at(packet: Any, *, at: datetime) -> Evaluation:
    """Replay a packet at an explicit historical instant without current authority."""
    historical = _evaluate_at(packet, at=at)
    decision_status = historical.status

    core = dict(historical.receipt)
    core.pop("receipt_sha256", None)
    core["schema"] = AUDIT_RECEIPT_SCHEMA
    core["evaluation_kind"] = "HISTORICAL_AUDIT"
    core["decision_status_at_time"] = decision_status
    core["current_work_admission_authority"] = False
    core["status"] = _audit_status(decision_status)

    receipt = dict(core)
    receipt["receipt_sha256"] = digest(core)
    return Evaluation(status=receipt["status"], reasons=historical.reasons, receipt=receipt)


def verify(packet: Any, receipt: Any) -> bool:
    """Verify receipt integrity only; this function never emits admission authority."""
    if type(receipt) is not dict:
        raise AdmissionError("receipt must be an object")
    if receipt.get("schema") != AUDIT_RECEIPT_SCHEMA:
        return _verify_current(packet, receipt)

    evaluated_at = _utc(receipt.get("evaluated_at"), "receipt.evaluated_at")
    expected = audit_at(packet, at=evaluated_at).receipt
    return receipt == expected
