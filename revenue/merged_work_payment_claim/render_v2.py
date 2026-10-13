from __future__ import annotations

from typing import Any


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Merged-work payment request packet", "",
        f"- State: `{report['state']}`",
        f"- Claim: `{report['claim_id']}`",
        f"- Claimant: `{report['claimant_id']}`",
        f"- Counterparty: `{report['counterparty_id']}`",
        f"- Opportunity: `{report['opportunity_id']}`",
        f"- Work: `{report['work_id']}`",
        f"- Evaluated: `{report['evaluation_at']}`",
        f"- Mode: `{report['mode']}`", "",
    ]
    if report["blockers"]:
        lines.extend(["## Hold reasons", ""])
        lines.extend(f"- `{reason}`" for reason in report["blockers"])
        lines.append("")
    request = report["payment_request"]
    if request is not None:
        lines.extend([
            "## Direct payment-request draft", "",
            "Recipient and route are intentionally unresolved. Obtain fresh single-writer authority and a last-inch contact/payment recensus before any external send.", "",
            f"Please process payment for accepted work `{request['work_id']}` (PR #{request['pr_number']} in `{request['repository']}`, merged as `{request['merged_commit_sha']}`).",
        ])
        if request["advertised_amount_minor"] is not None:
            lines.append(f"The retained terms advertise `{request['advertised_amount_minor']}` minor units of `{request['advertised_currency']}` for this exact work.")
        else:
            lines.append(f"The retained compensation terms for this exact work are: {request['advertised_terms_text']}")
        lines.extend([
            f"Compensation evidence: `{request['compensation_source_ref']}`.",
            f"Acceptance evidence: `{request['acceptance_source_ref']}`.", "",
            "This is a draft request artifact only. It does not assert that payment is overdue, create an invoice/receivable, prove payment, move funds, or recognize revenue.", "",
        ])
    lines.extend(["## Authority", ""])
    lines.extend(f"- `{key}`: `{str(value).lower()}`" for key, value in report["authority"].items())
    return "\n".join(lines) + "\n"
