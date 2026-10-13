from __future__ import annotations
import copy
import unittest
from datetime import datetime
from revenue.trusted_claim_policy import policy as policy_module
from revenue.trusted_claim_policy.policy import HOLD_LEVEL, sha256_text
from revenue.trusted_claim_policy.tests.fixtures import BASE, UTC, packet, policy_value, trusted_policy

class TrustedPolicyTimeTests(unittest.TestCase):

    def test_required_claim_missing_holds(self) -> None:
        candidate = packet()
        candidate['claims'] = []
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('MISSING_REQUIRED_CLAIM:deadline', receipt['reasons'])

    def test_optional_claim_may_be_omitted(self) -> None:
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=BASE)
        self.assertEqual(receipt['reasons'], [])

    def test_unknown_claim_holds(self) -> None:
        candidate = packet()
        candidate['claims'].append({'claim_id': 'attacker-claim', 'statement': 'Fabricated.', 'statement_sha256': sha256_text('Fabricated.'), 'source_ids': ['official.notice']})
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('UNKNOWN_CLAIM:attacker-claim', receipt['reasons'])

    def test_before_valid_from_holds(self) -> None:
        at = datetime(2026, 9, 15, 0, 59, 59, tzinfo=UTC)
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=at)
        self.assertIn('POLICY_NOT_YET_VALID', receipt['reasons'])

    def test_deadline_is_exclusive(self) -> None:
        policy = trusted_policy()
        just_before = datetime(2026, 9, 16, 2, 59, 59, 999999, tzinfo=UTC)
        at_deadline = datetime(2026, 9, 16, 3, 0, tzinfo=UTC)
        before_receipt = policy_module._verify_current_at_for_tests(packet(), policy, now=just_before)
        deadline_receipt = policy_module._verify_current_at_for_tests(packet(), policy, now=at_deadline)
        self.assertNotIn('POLICY_EXPIRED', before_receipt['reasons'])
        self.assertIn('POLICY_EXPIRED', deadline_receipt['reasons'])

    def test_period_open_holds(self) -> None:
        at = datetime(2026, 9, 15, 0, 59, 59, tzinfo=UTC)
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=at)
        self.assertIn('PERIOD_OPEN:deadline', receipt['reasons'])

    def test_incomplete_source_holds(self) -> None:
        value = policy_value()
        value['sources'][0]['complete'] = False
        receipt = policy_module._verify_current_at_for_tests(packet(value), trusted_policy(value), now=BASE)
        self.assertIn('INCOMPLETE_SOURCE:deadline:official.notice', receipt['reasons'])

    def test_complete_snapshot_before_period_end_holds(self) -> None:
        value = policy_value()
        value['sources'][0]['captured_at'] = '2026-09-15T00:59:59Z'
        candidate = packet(value)
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(value), now=BASE)
        self.assertIn('SOURCE_CAPTURE_BEFORE_PERIOD_END:deadline:official.notice', receipt['reasons'])

    def test_source_from_future_holds(self) -> None:
        at = datetime(2026, 9, 15, 1, 5, 30, tzinfo=UTC)
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=at)
        self.assertIn('SOURCE_FROM_FUTURE:official.addenda', receipt['reasons'])

    def test_stale_source_holds(self) -> None:
        at = datetime(2026, 9, 15, 2, 6, 1, tzinfo=UTC)
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=at)
        self.assertIn('STALE_SOURCE:official.notice', receipt['reasons'])
        self.assertIn('STALE_SOURCE:official.addenda', receipt['reasons'])

    def test_exact_max_age_boundary_passes(self) -> None:
        at = datetime(2026, 9, 15, 2, 5, tzinfo=UTC)
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=at)
        self.assertNotIn('STALE_SOURCE:official.notice', receipt['reasons'])

    def test_order_permutations_produce_identical_receipts(self) -> None:
        first = packet(include_optional=True)
        second = copy.deepcopy(first)
        second['sources'].reverse()
        second['claims'].reverse()
        for row in second['claims']:
            row['source_ids'].reverse()
        first_receipt = policy_module._verify_current_at_for_tests(first, trusted_policy(), now=BASE)
        second_receipt = policy_module._verify_current_at_for_tests(second, trusted_policy(), now=BASE)
        self.assertEqual(first_receipt, second_receipt)
