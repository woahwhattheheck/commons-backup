"""Safe concept renderer used by the standalone SOURCE RED closure proof.

The overlay applicator patches the donor's full renderer in place so its historical
bytes remain stable. This compact copy exercises the same authority boundary.
"""
from __future__ import annotations

from typing import Any

from .contracts import normalize_candidate
from .gate import verify_current, verify_report_shape
from .strict import ValidationError, strict_json_loads


def _validated_values(candidate_value: Any, report_value: Any) -> tuple[dict, dict]:
    if isinstance(candidate_value, bytes) and isinstance(report_value, bytes):
        candidate_bytes = bytes(candidate_value)
        report_bytes = bytes(report_value)
        candidate = normalize_candidate(strict_json_loads(candidate_bytes))
        report = verify_report_shape(strict_json_loads(report_bytes))
        if report["mode"] == "CURRENT" and not verify_current(candidate_bytes, report_bytes):
            raise ValidationError("current concept report failed fresh fixed-host verification")
        return candidate, report
    candidate = normalize_candidate(candidate_value)
    report = verify_report_shape(report_value)
    if report["mode"] == "CURRENT":
        raise ValidationError("current concept rendering requires exact candidate/report bytes and fresh verification")
    return candidate, report


def render_concept(candidate_value: Any, report_value: Any) -> str:
    candidate, report = _validated_values(candidate_value, report_value)
    if report["subject_id"] != candidate["subject_id"]:
        raise ValidationError("concept candidate and report subject do not match")
    if report["operation_id"] != candidate["operation_id"]:
        raise ValidationError("concept candidate and report operation do not match")
    headings = (
        "1. Problem Understanding",
        "2. Proposed Concept and Vision",
        "3. High-Level Technical Approach",
        "4. Intellectual Property and Data Rights",
        "5. Risk and Opportunity Spotlight",
        "6. Rough Order of Magnitude",
    )
    body = [
        f"# {candidate['concept_title']}\n\n",
        "> INTERNAL WORKING DRAFT — NOT AUTHORIZED FOR EXTERNAL CONTACT OR SUBMISSION. "
        f"Current qualification state: {report['state']}.\n\n",
    ]
    for heading in headings:
        body.append(f"## {heading}\n\nInternal owner-review content.\n\n")
    body.append("**Authority ceiling:** no contact, submission, signature, pricing, clearance, award, payment, or revenue claim is authorized.\n")
    return "".join(body)
