"""Synthetic milestone invoice-description drafts. Not live invoices."""

from __future__ import annotations


def invoice_drafts(projection):
    labels = {
        "kickoff": (
            "TJLabs technical assessment workshare — written authorization / "
            "kickoff (40% / $9,600). PROPOSED / NOT ACCEPTED. Not a payment request."
        ),
        "draft": (
            "TJLabs technical assessment workshare — delivery of the draft "
            "technical work package (40% / $9,600). PROPOSED / NOT ACCEPTED. "
            "Delivery-triggered; not an acceptance trigger."
        ),
        "final": (
            "TJLabs technical assessment workshare — written acceptance of the "
            "final technical work package (20% / $4,800). PROPOSED / NOT ACCEPTED. "
            "Only this base milestone is acceptance-triggered."
        ),
        "optional_readout": (
            "Optional final-readout support ($4,000) only if separately "
            "authorized in writing. Never included in the $24,000 base."
        ),
    }
    drafts = []
    for m in projection["milestones"]:
        drafts.append(
            {
                "id": "DRAFT-" + m["id"].upper(),
                "milestone": m["id"],
                "amount_usd": str(m["amount"]),
                "event_week": m["event_week"],
                "invoice_week": m["invoice_week"],
                "cash_week": m["cash_week"],
                "event": m["event"],
                "in_base": m["in_base"],
                "live_invoice": False,
                "description": labels[m["id"]],
            }
        )
    return drafts
