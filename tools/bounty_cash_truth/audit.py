"""Read-only evidence reconciler for paid contributions.

This consumes caller-supplied point-in-time provider evidence. It NEVER contacts
providers, posts claims, changes payout details, or estimates cash from offered
amounts. 'Received' is reserved for independently documented cash settlement.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

CASH_CURRENCIES = frozenset({"USD", "EUR", "GBP", "CAD", "AUD", "USDC"})
RECEIPT_ISSUERS = frozenset({"processor", "bank", "chain"})
CLAIM_ISSUERS = frozenset({"marketplace"})
MERGE_ISSUERS = frozenset({"github"})
AWARD_ISSUERS = frozenset({"marketplace", "sponsor"})
SETUP_ISSUERS = frozenset({"marketplace", "processor"})
GITHUB_PR = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$")


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        out = Decimal(str(value))
    except InvalidOperation:
        return None
    return out if out.is_finite() and out >= 0 else None


def _valid_web_link(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("https://"):
        return False
    parsed = urlsplit(value)
    return bool(parsed.netloc and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)


def _trusted_gate(data: Any, status: str, issuers: frozenset[str], snapshot: datetime) -> bool:
    if not isinstance(data, dict) or data.get("status") != status:
        return False
    if data.get("source_kind") not in issuers or not _valid_web_link(data.get("source_url")):
        return False
    observed = _utc(data.get("observed_at"))
    return observed is not None and observed <= snapshot


def _verified_receipt(payment: Any, snapshot: datetime) -> tuple[Decimal, str] | None:
    if not _trusted_gate(payment, "received", RECEIPT_ISSUERS, snapshot):
        return None
    amount = _money(payment.get("amount"))
    currency = payment.get("currency")
    receipt = payment.get("receipt_id")
    # A line in a GitHub issue, internal accounting estimate, or a non-redeemable
    # credit is not evidence that cash has been received.
    if amount is None or amount <= 0 or currency not in CASH_CURRENCIES:
        return None
    if not isinstance(receipt, str) or not receipt.strip() or len(receipt) > 256:
        return None
    return amount, currency


def audit(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Determine next actions without conflating advertised, awarded and received."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("records"), list):
        raise ValueError("snapshot must contain a records array")
    at = _utc(snapshot.get("snapshot_at"))
    if at is None:
        raise ValueError("snapshot_at must be an offset-aware ISO-8601 timestamp")

    records = []
    seen = set()
    cash_totals: dict[str, Decimal] = {}
    advertised_total = Decimal("0")

    for i, entry in enumerate(snapshot["records"]):
        if not isinstance(entry, dict):
            raise ValueError(f"records[{i}] must be an object")
        rid, pr = entry.get("id"), entry.get("pr_url")
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError(f"records[{i}] id missing or duplicated")
        seen.add(rid)
        if not isinstance(pr, str) or not GITHUB_PR.fullmatch(pr):
            raise ValueError(f"records[{i}] has no canonical GitHub PR URL")

        amount = _money(entry.get("advertised_usd"))
        if amount is None:
            raise ValueError(f"records[{i}] advertised_usd must be nonnegative")
        advertised_total += amount

        claim = entry.get("claim")
        merged = entry.get("merge")
        award = entry.get("award")
        setup = entry.get("payment_setup")
        payment = entry.get("payment")

        # A marketplace claim must point to this exact original sponsor PR.
        registered = (
            _trusted_gate(claim, "registered", CLAIM_ISSUERS, at)
            and claim.get("pr_url") == pr
        )
        is_merged = (
            _trusted_gate(merged, "merged", MERGE_ISSUERS, at)
            and merged.get("pr_url") == pr
        )
        awarded = _trusted_gate(award, "awarded", AWARD_ISSUERS, at)
        setup_verified = _trusted_gate(setup, "verified", SETUP_ISSUERS, at)
        received = _verified_receipt(payment, at)
        awarded_amount = _money(award.get("amount")) if awarded else None
        award_currency = award.get("currency") if awarded else None

        # Cash-received status is not inferred from merge, sponsor approval or
        # a pending marketplace balance. Require a processor/bank/chain receipt.
        if received:
            state, action = "CASH_RECEIPT_RECORDED", "reconcile_statement"
            cash_totals[received[1]] = cash_totals.get(received[1], Decimal(0)) + received[0]
        elif awarded:
            state = "AWARD_RECORDED_NOT_PAID"
            action = "verify_payment_setup" if not setup_verified else "reconcile_settlement"
        elif is_merged and registered:
            state, action = "MERGED_REGISTERED_NO_AWARD", "request_award_decision"
        elif is_merged:
            state, action = "MERGED_CLAIM_UNVERIFIED", "request_eligibility_decision"
        elif registered:
            state, action = "CLAIM_REGISTERED_NOT_MERGED", "maintainer_review"
        else:
            state, action = "SUBMISSION_NOT_VERIFIED", "reconcile_claim_registration"

        # A blocked payout setup is important even while technical acceptance
        # is still pending; never silently describe this as payment-ready.
        warnings = []
        if not setup_verified:
            warnings.append("payment_setup_not_verified")
        if isinstance(claim, dict) and claim.get("status") == "registered" and not registered:
            warnings.append("claim_not_verified_for_exact_pr")
        if isinstance(payment, dict) and payment.get("status") == "received" and not received:
            warnings.append("cash_receipt_evidence_insufficient")
        if awarded and (awarded_amount is None or award_currency is None):
            warnings.append("award_value_unverified")

        records.append({
            "id": rid,
            "pr_url": pr,
            "advertised_usd": str(amount),
            "claim_verified": registered,
            "merge_verified": is_merged,
            "award_verified": awarded,
            "payment_setup_verified": setup_verified,
            "cash_receipt_recorded": bool(received),
            "state": state,
            "next_action": action,
            "warnings": warnings,
        })

    return {
        "schema": "commons.bounty_cash_truth.v1",
        "snapshot_at": at.isoformat(),
        "count": len(records),
        "advertised_usd_not_receivables": str(advertised_total),
        "cash_receipts_by_currency": {k: str(v) for k, v in sorted(cash_totals.items())},
        "records": records,
        "disclaimer": "Provider evidence is caller-supplied, not independently authenticated. This tool never asserts escrow, award, tax treatment, or payout without an eligible receipt.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline bounty cash evidence reconciliation")
    parser.add_argument("snapshot", type=Path, help="JSON evidence snapshot file")
    args = parser.parse_args()
    report = audit(json.loads(args.snapshot.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
