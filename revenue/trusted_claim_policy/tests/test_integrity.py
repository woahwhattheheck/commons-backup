from __future__ import annotations
import copy
import unittest
from revenue.trusted_claim_policy import policy as policy_module
from revenue.trusted_claim_policy.policy import ClaimPolicyError, make_packet, packet_from_text, sha256_text, validate_packet, validate_policy, verify_receipt
from revenue.trusted_evidence_authority.strict_json import canonical_json
from revenue.trusted_claim_policy.tests.fixtures import BASE, claim_packet_rows, packet, policy_value, source_packet_rows, trusted_policy

class TrustedPolicyIntegrityTests(unittest.TestCase):

    def test_receipt_tamper_fails(self) -> None:
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=BASE)
        receipt['reasons'] = ['FABRICATED']
        self.assertFalse(verify_receipt(receipt, packet(), trusted_policy()))

    def test_receipt_reseal_does_not_hide_semantic_tamper(self) -> None:
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=BASE)
        receipt['reasons'] = ['FABRICATED']
        body = dict(receipt)
        body.pop('receipt_sha256')
        receipt['receipt_sha256'] = sha256_text(canonical_json(body))
        self.assertFalse(verify_receipt(receipt, packet(), trusted_policy()))

    def test_current_receipt_recomputes(self) -> None:
        trusted = trusted_policy()
        candidate = packet()
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted, now=BASE)
        self.assertTrue(verify_receipt(receipt, candidate, trusted))

    def test_duplicate_packet_source_rejected(self) -> None:
        candidate = packet()
        candidate['sources'].append(copy.deepcopy(candidate['sources'][0]))
        with self.assertRaisesRegex(ClaimPolicyError, 'duplicate packet source_id'):
            validate_packet(candidate)

    def test_bool_generation_rejected(self) -> None:
        candidate = packet()
        candidate['sources'][0]['generation'] = True
        with self.assertRaisesRegex(ClaimPolicyError, 'positive integer'):
            validate_packet(candidate)

    def test_policy_claim_cannot_bind_unknown_source(self) -> None:
        value = policy_value()
        value['claims'][0]['source_ids'].append('official.unknown')
        with self.assertRaisesRegex(ClaimPolicyError, 'unknown sources'):
            validate_policy(value)

    def test_context_mutation_without_rehash_rejected(self) -> None:
        candidate = packet()
        candidate['context']['authorized'] = True
        with self.assertRaisesRegex(ClaimPolicyError, 'context_sha256 mismatch'):
            validate_packet(candidate)

    def test_float_context_rejected(self) -> None:
        with self.assertRaises(ClaimPolicyError):
            make_packet(policy_id='p', subject_id='s', decision_id='d', context={'rate': 0.1}, sources=source_packet_rows(), claims=claim_packet_rows())

    def test_closed_claim_requires_period_end(self) -> None:
        value = policy_value()
        value['period_end'] = None
        with self.assertRaisesRegex(ClaimPolicyError, 'requires period_end'):
            validate_policy(value)

    def test_period_end_must_leave_valid_window(self) -> None:
        value = policy_value()
        value['period_end'] = value['valid_before']
        with self.assertRaisesRegex(ClaimPolicyError, 'period_end must be before'):
            validate_policy(value)

    def test_source_cannot_postdate_policy_issuance(self) -> None:
        value = policy_value()
        value['sources'][0]['captured_at'] = '2026-09-15T01:11:00Z'
        with self.assertRaisesRegex(ClaimPolicyError, 'captured after policy issuance'):
            validate_policy(value)

    def test_duplicate_json_packet_key_rejected(self) -> None:
        with self.assertRaisesRegex(ClaimPolicyError, 'duplicate key'):
            packet_from_text('{"schema":"x","schema":"y"}')

    def test_receipt_unknown_key_fails(self) -> None:
        trusted = trusted_policy()
        candidate = packet()
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted, now=BASE)
        receipt['forged'] = True
        self.assertFalse(verify_receipt(receipt, candidate, trusted))

    def test_policy_normalization_uses_deterministic_ascii_order(self) -> None:
        value = policy_value()
        value['sources'].reverse()
        value['claims'].reverse()
        normalized = validate_policy(value)
        self.assertEqual([row['source_id'] for row in normalized['sources']], ['official.addenda', 'official.notice'])
        self.assertEqual([row['claim_id'] for row in normalized['claims']], ['deadline', 'split-award'])
