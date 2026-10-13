from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from underwriter import Config, UnderwriterInputError, underwrite  # noqa: E402

NOW = datetime(2026, 9, 13, 7, 30, tzinfo=timezone.utc)


def receipt_hash(receipt: dict) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def freshness(*, status="actionable", state="open", claims=0, prs=0, amount="2000", currency="USD") -> dict:
    receipt = {
        "schema": "commons-funded-work-freshness/v1",
        "generated_at": "2026-09-13T07:20:00Z",
        "candidate": {
            "url": "https://board.example.test/item/42",
            "platform": "example",
            "advertised_amount": amount,
            "currency": currency,
            "canonical_url_hint": "https://github.com/org/repo/issues/42",
        },
        "authority": "canonical_github_state",
        "financial_status": "advertised_not_accepted_awarded_or_paid",
        "provider_requests": "read_only",
        "canonical": {"url": "https://github.com/org/repo/issues/42", "state": state},
        "checks": {
            "evidence_complete": True,
            "canonical_state_open": state == "open",
            "visible_claim_count": claims,
            "active_competing_pr_count": prs,
        },
        "freshness_status": status,
        "route": "qualified_for_human_claim_decision" if status == "actionable" else "reject",
        "reasons": [],
    }
    receipt["receipt_sha256"] = receipt_hash(receipt)
    return receipt


def packet() -> dict:
    return {
        "candidate_id": "org/repo#42",
        "canonical_url": "https://github.com/org/repo/issues/42",
        "currency": "USD",
        "advertised_amount": "2000",
        "freshness_receipt": freshness(),
        "payout_history": [
            {
                "source_url": "https://rewards.example.test/org",
                "source_class": "marketplace",
                "observed_at": "2026-09-13T07:15:00Z",
                "currency": "USD",
                "paid_total": "12000",
                "award_count": 12,
                "completed_count": 12,
                "open_pool": "5000",
            }
        ],
    }


class UnderwriterTests(unittest.TestCase):
    def test_repeated_payer_is_pursue(self):
        result = underwrite(packet(), observed_at=NOW)
        self.assertEqual(result["disposition"], "pursue")
        self.assertEqual(result["expected_cash_planning_range"], {"lower": "300.00", "upper": "1000.00"})
        self.assertFalse(result["booking_authority"])
        self.assertFalse(result["external_action_authority"])

    def test_closed_canonical_rejects_even_with_payout_history(self):
        value = packet()
        value["freshness_receipt"] = freshness(state="closed")
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("canonical_state_closed", result["reasons"])

    def test_stale_freshness_status_rejects(self):
        value = packet()
        value["freshness_receipt"] = freshness(status="stale")
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("freshness_stale", result["reasons"])

    def test_tampered_freshness_receipt_rejected(self):
        value = packet()
        value["freshness_receipt"]["checks"]["visible_claim_count"] = 99
        with self.assertRaisesRegex(UnderwriterInputError, "hash mismatch"):
            underwrite(value, observed_at=NOW)

    def test_freshness_amount_mismatch_rejected(self):
        value = packet()
        value["freshness_receipt"] = freshness(amount="1999")
        with self.assertRaisesRegex(UnderwriterInputError, "advertised amount"):
            underwrite(value, observed_at=NOW)

    def test_zero_paid_high_competition_pool_rejects(self):
        value = packet()
        value["freshness_receipt"] = freshness(claims=3)
        value["payout_history"][0].update(paid_total="0", award_count=0, completed_count=0)
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("zero_paid_high_competition_pool", result["reasons"])

    def test_zero_paid_low_competition_is_watch(self):
        value = packet()
        value["freshness_receipt"] = freshness(claims=1)
        value["payout_history"][0].update(paid_total="0", award_count=0, completed_count=0)
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "watch")
        self.assertEqual(result["expected_cash_planning_range"]["lower"], "0.00")

    def test_competition_dilutes_planning_range(self):
        value = packet()
        value["freshness_receipt"] = freshness(claims=2, prs=1)
        result = underwrite(value, observed_at=NOW, config=Config(min_pursue_cash=Decimal("1")))
        self.assertEqual(result["expected_cash_planning_range"], {"lower": "75.00", "upper": "250.00"})
        self.assertEqual(result["disposition"], "pursue")

    def test_threshold_boundary_is_pursue(self):
        value = packet()
        value["advertised_amount"] = "1000"
        value["freshness_receipt"] = freshness(amount="1000")
        result = underwrite(value, observed_at=NOW, config=Config(min_pursue_cash=Decimal("150")))
        self.assertEqual(result["expected_cash_planning_range"]["lower"], "150.00")
        self.assertEqual(result["disposition"], "pursue")

    def test_below_threshold_is_watch(self):
        value = packet()
        value["advertised_amount"] = "1000"
        value["freshness_receipt"] = freshness(amount="1000")
        result = underwrite(value, observed_at=NOW, config=Config(min_pursue_cash=Decimal("150.01")))
        self.assertEqual(result["disposition"], "watch")
        self.assertIn("planning_floor_below_pursue_threshold", result["reasons"])

    def test_currency_mismatch_rejected_as_invalid_input(self):
        value = packet()
        value["payout_history"][0]["currency"] = "EUR"
        with self.assertRaisesRegex(UnderwriterInputError, "does not match"):
            underwrite(value, observed_at=NOW)

    def test_negative_and_non_integer_fields_rejected(self):
        for field, bad in (("paid_total", "-1"), ("award_count", -1), ("award_count", 1.5)):
            with self.subTest(field=field, bad=bad):
                value = packet()
                value["payout_history"][0][field] = bad
                with self.assertRaises(UnderwriterInputError):
                    underwrite(value, observed_at=NOW)

    def test_paid_total_requires_award(self):
        value = packet()
        value["payout_history"][0]["award_count"] = 0
        value["payout_history"][0]["completed_count"] = 0
        with self.assertRaisesRegex(UnderwriterInputError, "paid_total is positive"):
            underwrite(value, observed_at=NOW)

    def test_completed_cannot_exceed_awards(self):
        value = packet()
        value["payout_history"][0]["completed_count"] = 13
        with self.assertRaisesRegex(UnderwriterInputError, "completed_count exceeds"):
            underwrite(value, observed_at=NOW)

    def test_regressing_same_source_history_rejected(self):
        value = packet()
        earlier = deepcopy(value["payout_history"][0])
        earlier.update(observed_at="2026-09-12T07:15:00Z", paid_total="13000", award_count=13, completed_count=13)
        value["payout_history"].insert(0, earlier)
        with self.assertRaisesRegex(UnderwriterInputError, "paid_total regressed"):
            underwrite(value, observed_at=NOW)

    def test_distinct_provider_sources_can_disagree_at_same_instant(self):
        value = packet()
        other = deepcopy(value["payout_history"][0])
        other["source_url"] = "https://other.example.test/org"
        other["paid_total"] = "9000"
        value["payout_history"].append(other)
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["realized_payout_evidence"]["source_count"], 2)

    def test_conflicting_same_source_snapshot_is_rejected(self):
        value = packet()
        other = deepcopy(value["payout_history"][0])
        other["open_pool"] = "4000"
        value["payout_history"].append(other)
        with self.assertRaisesRegex(UnderwriterInputError, "conflicting simultaneous payout snapshots"):
            underwrite(value, observed_at=NOW)

    def test_stale_payout_history_rejects(self):
        value = packet()
        value["payout_history"][0]["observed_at"] = "2026-01-01T00:00:00Z"
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("payout_history_stale", result["reasons"])

    def test_future_payout_history_rejects(self):
        value = packet()
        value["payout_history"][0]["observed_at"] = "2026-09-13T08:00:00Z"
        result = underwrite(value, observed_at=NOW)
        self.assertEqual(result["disposition"], "reject")
        self.assertIn("payout_history_in_future", result["reasons"])

    def test_credentials_in_evidence_url_rejected(self):
        value = packet()
        value["payout_history"][0]["source_url"] = "https://user:secret@example.test/history"
        with self.assertRaisesRegex(UnderwriterInputError, "must not contain credentials"):
            underwrite(value, observed_at=NOW)

    def test_invalid_url_port_is_clean_input_error(self):
        value = packet()
        value["payout_history"][0]["source_url"] = "https://example.test:bad/history"
        with self.assertRaisesRegex(UnderwriterInputError, "invalid port"):
            underwrite(value, observed_at=NOW)

    def test_deterministic_hash_and_replay(self):
        first = underwrite(packet(), observed_at=NOW)
        second = underwrite(packet(), observed_at=NOW)
        self.assertEqual(first, second)
        self.assertEqual(len(first["input_sha256"]), 64)
        self.assertEqual(len(first["receipt_sha256"]), 64)

    def test_input_order_does_not_change_input_hash(self):
        value = packet()
        reversed_value = dict(reversed(list(value.items())))
        first = underwrite(value, observed_at=NOW)
        second = underwrite(reversed_value, observed_at=NOW)
        self.assertEqual(first["input_sha256"], second["input_sha256"])

    def test_cli_replay_and_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "input.json"
            output_path = Path(temporary) / "receipt.json"
            input_path.write_text(json.dumps(packet()), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(HERE / "underwriter.py"), str(input_path), "--observed-at", "2026-09-13T07:30:00Z", "--output", str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["disposition"], "pursue")


if __name__ == "__main__":
    unittest.main()
