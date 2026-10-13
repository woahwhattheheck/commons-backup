from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import sha256_hex

READINESS_SCHEMA = "neighborsignal.competition-readiness/v1"
_REQUIRED = (
    "source_tests_passed",
    "optimized_tests_passed",
    "gloo_live_call_receipt",
    "hackathon_registration_evidence",
    "attendance_evidence",
    "submission_receipt",
)


def compile_readiness(evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object")
    unknown = set(evidence) - set(_REQUIRED)
    if unknown:
        raise ValueError(f"unknown readiness evidence: {sorted(unknown)}")
    normalized = {key: deepcopy(evidence.get(key)) for key in _REQUIRED}
    reasons = []
    for key in _REQUIRED:
        value = normalized[key]
        if key.endswith("_passed"):
            if value is not True:
                reasons.append("MISSING:" + key)
        else:
            if not isinstance(value, str) or len(value) < 8:
                reasons.append("MISSING:" + key)
    state = "SUBMISSION_EVIDENCED" if not reasons else "HOLD"
    out = {
        "schema": READINESS_SCHEMA,
        "state": state,
        "external_submission_authorized": False,
        "prize_or_payment_claimed": False,
        "reasons": reasons,
        "evidence": normalized,
    }
    out["readiness_sha256"] = sha256_hex(out)
    return out
