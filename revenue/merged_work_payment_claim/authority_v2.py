from __future__ import annotations


def authority() -> dict[str, bool]:
    return {
        "send_authorized": False,
        "single_writer_authorized": False,
        "provider_action_authorized": False,
        "invoice_created": False,
        "legal_demand_authorized": False,
        "payment_authorized": False,
        "payment_proven": False,
        "funds_moved": False,
        "cash_received": False,
        "receivable_asserted": False,
        "revenue_recognized": False,
        "accounting_conclusion": False,
    }
