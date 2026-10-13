from __future__ import annotations

import unittest

from evaluation import _commercial_amount_event, _has_conflicting_symbol_code
from funded_work_freshness import Candidate, preflight
from test_support import NOW, FakeTransport, evidence_routes, open_issue


GH = "https://github.com/acme/widget/issues/12"
STAMP = "2026-09-13T04:00:00Z"


def authority_comment(body: str):
    return {
        "body": body,
        "user": {"login": "maintainer"},
        "author_association": "OWNER",
        "created_at": STAMP,
        "updated_at": STAMP,
    }


class SymbolCodeCaseTests(unittest.TestCase):
    def _receipt(self, body: str, *, currency: str = "USD", amount: str = "200"):
        candidate = Candidate.validated(
            candidate_url=GH,
            platform="fixture-board",
            advertised_amount=amount,
            currency=currency,
            canonical_url=GH,
            max_age_days=30,
        )
        transport = FakeTransport(
            evidence_routes(
                "acme",
                "widget",
                12,
                open_issue(GH),
                [authority_comment(body)],
            )
        )
        return preflight(candidate, transport, observed_at=NOW)

    def test_conflicting_symbol_code_is_case_insensitive_and_fails_closed(self):
        hostiles = (
            "Reward: $200 cad via Algora.",
            "Reward: $200 CaD via Algora.",
            "Reward: cad $200 via Algora.",
            "Reward: cAd $200 via Algora.",
            "Reward: €200 usd via Algora.",
            "Reward: uSd €200 via Algora.",
            "Reward: $200 zwg via Algora.",
            "Reward: CAD: $200 via Algora.",
            "Reward: cAd: $200 via Algora.",
            "Reward: $200 (CAD) via Algora.",
            "Reward: $200 - cad via Algora.",
        )
        for body in hostiles:
            with self.subTest(body=body):
                receipt = self._receipt(body)
                self.assertEqual(receipt["freshness_status"], "ambiguous")
                self.assertEqual(receipt["route"], "reject")
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "ambiguous"
                )
                self.assertIsNone(
                    receipt["checks"]["canonical_current_reward_currency"]
                )
                self.assertIsNone(
                    receipt["checks"]["canonical_current_reward_amount"]
                )
                self.assertEqual(
                    receipt["reasons"], ["canonical_reward_amount_ambiguous"]
                )

    def test_consistent_usd_symbol_code_remains_resolvable_across_case(self):
        forms = (
            "Reward: $200 usd via Algora.",
            "Reward: $200 UsD via Algora.",
            "Reward: usd $200 via Algora.",
            "Reward: uSd $200 via Algora.",
            "Reward: USD: $200 via Algora.",
            "Reward: $200 (usd) via Algora.",
        )
        for body in forms:
            with self.subTest(body=body):
                receipt = self._receipt(body)
                self.assertEqual(receipt["freshness_status"], "actionable")
                self.assertEqual(
                    receipt["route"], "qualified_for_human_claim_decision"
                )
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "resolved"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_currency"], "USD"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_amount"], "200"
                )

    def test_standalone_currency_codes_keep_existing_case_insensitive_grammar(self):
        forms = (
            "Reward: cad 200 via Algora.",
            "Reward: 200 cAd via Algora.",
        )
        for body in forms:
            with self.subTest(body=body):
                receipt = self._receipt(body, currency="CAD")
                self.assertEqual(receipt["freshness_status"], "actionable")
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "resolved"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_currency"], "CAD"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_amount"], "200"
                )

    def test_plain_number_followed_or_preceded_by_prose_is_not_currency(self):
        forms = (
            "Reward: 200 via Algora.",
            "Reward: via 200 after review.",
            "Reward: 200 for each accepted issue.",
            "Reward: per 200 accepted reports.",
        )
        for body in forms:
            with self.subTest(body=body):
                self.assertEqual(
                    _commercial_amount_event(body),
                    {"status": "none", "currency": None, "amount": None},
                )

    def test_unresolved_amount_update_overrides_older_numeric_authority(self):
        hostiles = (
            "Reward changed from $500 to TBD.",
            "Reward was $500, now TBD.",
            "Reward changed to TBD.",
            "Reward amount TBD.",
            "Reward is negotiable.",
            "Reward amount varies by scope.",
            "Reward depends on scope.",
            "Reward amount varies between $100 and $300.",
            "Reward up to $500.",
            "Reward changed from $500.",
        )
        for body in hostiles:
            with self.subTest(body=body):
                receipt = self._receipt(body, amount="500")
                self.assertEqual(receipt["freshness_status"], "ambiguous")
                self.assertEqual(receipt["route"], "reject")
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "ambiguous"
                )
                self.assertIsNone(
                    receipt["checks"]["canonical_current_reward_currency"]
                )
                self.assertIsNone(
                    receipt["checks"]["canonical_current_reward_amount"]
                )
                self.assertEqual(
                    receipt["reasons"], ["canonical_reward_amount_ambiguous"]
                )

    def test_ordinary_three_letter_prose_after_symbol_is_not_a_code(self):
        forms = (
            "Reward: $200 via Algora.",
            "Reward: $200 for each accepted issue.",
            "Reward: $200 per merged fix.",
            "Reward: $200 and expenses.",
        )
        for body in forms:
            with self.subTest(body=body):
                receipt = self._receipt(body)
                self.assertEqual(receipt["freshness_status"], "actionable")
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "resolved"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_currency"], "USD"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_amount"], "200"
                )

    def test_unrelated_non_amount_prose_does_not_invalidate_numeric_authority(self):
        forms = (
            "Reward: $200, acceptance pending.",
            "Reward remains available and test budget is $200.",
            "Reward details pending review.",
        )
        expected = (
            "resolved",
            "none",
            "none",
        )
        for body, status in zip(forms, expected):
            with self.subTest(body=body):
                self.assertEqual(_commercial_amount_event(body)["status"], status)

    def test_identifier_like_suffixes_are_not_currency_codes(self):
        forms = (
            "Reward: $200 cadet via Algora.",
            "Reward: $200 usd_label via Algora.",
        )
        for body in forms:
            with self.subTest(body=body):
                receipt = self._receipt(body)
                self.assertEqual(receipt["freshness_status"], "actionable")
                self.assertEqual(
                    receipt["checks"]["authoritative_amount_state"], "resolved"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_currency"], "USD"
                )
                self.assertEqual(
                    receipt["checks"]["canonical_current_reward_amount"], "200"
                )

    def test_code_fragments_inside_longer_prefixes_are_not_codes(self):
        for text in ("ACAD $200", "USDS $200", "prefixCAD $200"):
            with self.subTest(text=text):
                self.assertFalse(_has_conflicting_symbol_code(text))
        self.assertTrue(_has_conflicting_symbol_code("CAD $200"))
        self.assertTrue(_has_conflicting_symbol_code("cAd $200"))

    def test_unknown_lowercase_prose_is_ignored_but_uppercase_code_fails_closed(self):
        self.assertFalse(_has_conflicting_symbol_code("$200 xyz"))
        self.assertTrue(_has_conflicting_symbol_code("$200 XYZ"))


if __name__ == "__main__":
    unittest.main()
