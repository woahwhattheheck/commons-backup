from __future__ import annotations
import copy
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from revenue.trusted_claim_policy import policy as policy_module
from revenue.trusted_claim_policy.policy import AUTHORITY_CEILING, CURRENT_LEVEL, HISTORICAL_LEVEL, HOLD_LEVEL, ClaimPolicyError, load_trusted_policy, sha256_bytes, sha256_text, validate_packet, validate_policy, verify_current, verify_historical, verify_receipt
from revenue.trusted_evidence_authority.strict_json import canonical_json
from revenue.trusted_claim_policy.tests.fixtures import BASE, packet, policy_value, trusted_policy

class TrustedPolicyTrustTests(unittest.TestCase):

    def test_valid_current_authority(self) -> None:
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted_policy(), now=BASE)
        self.assertEqual(receipt['evidence_level'], CURRENT_LEVEL)
        self.assertTrue(receipt['current_claim_authority'])
        self.assertEqual(receipt['reasons'], [])
        self.assertEqual(receipt['authority_ceiling'], AUTHORITY_CEILING)

    def test_public_current_api_has_no_clock_parameter(self) -> None:
        self.assertEqual(list(inspect.signature(verify_current).parameters), ['packet', 'policy'])

    def test_historical_never_upgrades_to_current(self) -> None:
        receipt = verify_historical(packet(), trusted_policy(), as_of=BASE)
        self.assertEqual(receipt['evidence_level'], HISTORICAL_LEVEL)
        self.assertFalse(receipt['current_claim_authority'])
        self.assertTrue(verify_receipt(receipt, packet(), trusted_policy()))

    def test_policy_pin_mismatch_rejected(self) -> None:
        raw = json.dumps(policy_value(), separators=(',', ':')).encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            path.write_bytes(raw)
            with self.assertRaisesRegex(ClaimPolicyError, 'independently pinned'):
                load_trusted_policy(path, expected_file_sha256='0' * 64)

    def test_exposed_policy_raw_is_a_defensive_copy(self) -> None:
        trusted = trusted_policy()
        exposed = trusted.raw
        exposed['claims'][0]['statement'] = 'Fabricated after load.'
        receipt = policy_module._verify_current_at_for_tests(packet(), trusted, now=BASE)
        self.assertEqual(receipt['evidence_level'], CURRENT_LEVEL)

    def test_private_snapshot_mutation_is_detected_before_decision(self) -> None:
        trusted = trusted_policy()
        trusted._raw['claims'][0]['statement'] = 'Fabricated after load.'
        with self.assertRaisesRegex(ClaimPolicyError, 'mutated after pin validation'):
            policy_module._verify_current_at_for_tests(packet(), trusted, now=BASE)

    def test_direct_policy_construction_is_rejected(self) -> None:
        normalized = validate_policy(policy_value())
        digest = sha256_text(canonical_json(normalized))
        with self.assertRaisesRegex(ClaimPolicyError, 'constructed by load_trusted_policy'):
            policy_module.TrustedClaimPolicy(_raw=normalized, canonical_sha256=digest, pin_sha256=digest, _construction_token=object())

    def test_support_map_mutation_cannot_self_upgrade_under_old_pin(self) -> None:
        original = json.dumps(policy_value(), separators=(',', ':'), sort_keys=True).encode()
        mutated_value = policy_value()
        mutated_value['claims'][0]['source_ids'] = ['official.notice']
        mutated = json.dumps(mutated_value, separators=(',', ':'), sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            path.write_bytes(mutated)
            with self.assertRaisesRegex(ClaimPolicyError, 'independently pinned'):
                load_trusted_policy(path, expected_file_sha256=sha256_bytes(original))

    def test_duplicate_policy_key_rejected(self) -> None:
        text = '{"schema":"trusted-claim-policy/v1","schema":"trusted-claim-policy/v1"}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            path.write_text(text)
            with self.assertRaisesRegex(ClaimPolicyError, 'duplicate key'):
                load_trusted_policy(path, expected_file_sha256=sha256_bytes(text.encode()))

    def test_attacker_added_source_holds(self) -> None:
        candidate = packet()
        forged = copy.deepcopy(candidate['sources'][0])
        forged['source_id'] = 'official.forged'
        forged['provider'] = 'attacker.example'
        candidate['sources'].append(forged)
        candidate = validate_packet(candidate)
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('UNKNOWN_SOURCE:official.forged', receipt['reasons'])
        self.assertEqual(receipt['evidence_level'], HOLD_LEVEL)

    def test_missing_source_holds(self) -> None:
        candidate = packet()
        candidate['sources'] = candidate['sources'][:1]
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('MISSING_SOURCE:official.notice', receipt['reasons'])

    def test_source_identity_drift_holds(self) -> None:
        candidate = packet()
        candidate['sources'][0]['content_sha256'] = 'c' * 64
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertTrue(any((reason.endswith(':content_sha256') for reason in receipt['reasons'])))

    def test_claim_statement_drift_holds_even_when_rehashed(self) -> None:
        candidate = packet()
        candidate['claims'][0]['statement'] = 'A fabricated deadline.'
        candidate['claims'][0]['statement_sha256'] = sha256_text('A fabricated deadline.')
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('CLAIM_MISMATCH:deadline:statement', receipt['reasons'])

    def test_claim_support_drift_holds(self) -> None:
        candidate = packet()
        candidate['claims'][0]['source_ids'] = ['official.notice']
        receipt = policy_module._verify_current_at_for_tests(candidate, trusted_policy(), now=BASE)
        self.assertIn('CLAIM_MISMATCH:deadline:source_ids', receipt['reasons'])
