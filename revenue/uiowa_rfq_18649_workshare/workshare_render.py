#!/usr/bin/env python3
"""Human-readable projection with an explicit non-authorizing boundary."""
from __future__ import annotations

from typing import Any

from workshare_verify import verify_report_integrity

def render_markdown(report: dict[str, Any]) -> str:
    integrity = verify_report_integrity(report)
    lines = [
        "# University of Iowa RFQ 18649 — TJLabs technical workshare",
        "",
        f"- Packet mode: `{report['mode']}`",
        f"- State: `{report['aggregate_state']}`",
        f"- Evaluated at: `{report['evaluated_at']}`",
        f"- Current evidence-review authority encoded: `{str(report['trust']['current_evidence_review_authority']).lower()}`",
        "- Public renderer verified semantic integrity only; it did **not** independently authenticate the authority root.",
        f"- Base fixed fee: **${report['commercial_terms']['base_fee_usd']:,}**",
        f"- Optional final-readout support: **${report['commercial_terms']['optional_readout_support_usd']:,}**",
        f"- Authority root: `{report['authority_root_sha256']}`",
        f"- Receipt: `{integrity['receipt_sha256']}`",
        "",
        "## Assessment matrix",
        "",
        "| Group | Dimension | State | Maturity | Confidence (bp) |",
        "|---|---|---|---:|---:|",
    ]
    for row in report["assessment_matrix"]:
        maturity = "—" if row["maturity"] is None else str(row["maturity"])
        confidence = "—" if row["confidence_bp"] is None else str(row["confidence_bp"])
        lines.append(f"| {row['group']} | {row['dimension']} | {row['status']} | {maturity} | {confidence} |")
    lines.extend(
        [
            "",
            "## Authority boundary",
            "",
            "The source authority root must be retained independently by a trusted host. Computing a digest from caller-supplied authority bytes does not authenticate external provenance.",
            "",
            "The prime retains University communication, proposal submission, references, insurance, contracting, final professional judgment, staffing/travel commitments, and final recommendations.",
            "",
            "No award, buyer acceptance, payment, cash, invoice, or recognized revenue is claimed by this packet.",
            "",
        ]
    )
    return "\n".join(lines)


