from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from underwriter import Config, underwrite  # noqa: E402

NOW = datetime(2026, 9, 13, 7, 30, tzinfo=timezone.utc)


def receipt_hash(receipt: dict) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def freshness(*, claims: int = 0, prs: int = 0) -> dict:
    receipt = {
        "schema": "commons-funded-work-freshness/v1",
        "generated_at": "2026-09-13T07:20:00Z",
        "candidate": {
            "url": "https://board.example.test/item/42",
            "platform": "example",
            "advertised_amount": "2000",
            "currency": "USD",
            "canonical_url_hint": "https://github.com/org/repo/issues/42",
        },
        "authority": "canonical_github_state",
        "financial_status": "advertised_not_accepted_awarded_or_paid",
        "provider_requests": "read_only",
        "canonical": {"url": "https://github.com/org/repo/issues/42", "state": "open"},
        "checks": {
            "evidence_complete": True,
            "canonical_state_open": True,
            "visible_claim_count": claims,
            "active_competing_pr_count": prs,
        },
        "freshness_status": "actionable",
        "route": "qualified_for_human_claim_decision",
        "reasons": [],
    }
    receipt["receipt_sha256"] = receipt_hash(receipt)
    return receipt


def packet(*, claims: int = 0, prs: int = 0) -> dict:
    return {
        "candidate_id": "org/repo#42",
        "canonical_url": "https://github.com/org/repo/issues/42",
        "currency": "USD",
        "advertised_amount": "2000",
        "freshness_receipt": freshness(claims=claims, prs=prs),
        "payout_history": [],
    }


def history_row(
    source_url: str,
    source_class: str,
    *,
    paid_total: str,
    award_count: int,
    completed_count: int,
) -> dict:
    return {
        "source_url": source_url,
        "source_class": source_class,
        "observed_at": "2026-09-13T07:15:00Z",
        "currency": "USD",
        "paid_total": paid_total,
        "award_count": award_count,
        "completed_count": completed_count,
        "open_pool": "0",
    }


class CoherentPayoutSourceTests(unittest.TestCase):
    def test_cross_source_maxima_cannot_upgrade_watch_to_pursue(self):
        value = packet()
        value["payout_history"] = [
            history_row(
                "https://market.example.test/org",
                "marketplace",
                paid_total="4000",
                award_count=1,
                completed_count=1,
            ),
            history_row(
                "https://ledger.example.test/org",
                "payment_ledger",
                paid_total="100",
                award_count=10,
                completed_count=10,
            ),
        ]

        result = underwrite(
            value,
            observed_at=NOW,
            config=Config(min_pursue_cash=Decimal("150")),
        )

        self.assertEqual(result["disposition"], "watch")
        self.assertEqual(
            result["expected_cash_planning_range"],
            {"lower": "100.00", "upper": "400.00"},
        )
        self.assertEqual(
            result["assumptions"]["history_basis"],
            "limited_realized_payout_history",
        )
        self.assertIn("planning_floor_below_pursue_threshold", result["reasons"])

    def test_zero_paid_high_competition_source_cannot_be_erased_by_positive_sibling(self):
        value = packet(claims=3)
        value["payout_history"] = [
            history_row(
                "https://market.example.test/org",
                "marketplace",
                paid_total="12000",
                award_count=12,
                completed_count=12,
            ),
            history_row(
                "https://ledger.example.test/org",
                "payment_ledger",
                paid_total="0",
                award_count=0,
                completed_count=0,
            ),
        ]

        result = underwrite(value, observed_at=NOW)

        self.assertEqual(result["disposition"], "reject")
        self.assertIn("zero_paid_high_competition_pool", result["reasons"])
        self.assertEqual(
            result["expected_cash_planning_range"],
            {"lower": "0.00", "upper": "25.00"},
        )
        self.assertEqual(
            result["assumptions"]["history_basis"],
            "conservative_multi_source_history",
        )


if __name__ == "__main__":
    unittest.main()
