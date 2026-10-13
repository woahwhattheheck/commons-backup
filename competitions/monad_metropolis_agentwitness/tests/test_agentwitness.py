from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentwitness import (
    AgentWitnessError,
    AlreadyClaimed,
    AlreadyFinalized,
    DuplicateKeyError,
    InMemoryRegistry,
    NotClaimant,
    NotReconcilable,
    Outcome,
    Resolution,
    event_key,
    intent_hash,
    make_receipt,
    outcome_hash,
    receipt_digest,
    strict_loads,
)

A = "0x" + "11" * 20
B = "0x" + "22" * 20


def event(event_id: str = "msg-1", **overrides):
    value = {
        "version": "agentwitness-event-v1",
        "network": "monad",
        "namespace": "gmail/reply",
        "provider": "gmail",
        "event_id": event_id,
    }
    value.update(overrides)
    return value


class KeyTests(unittest.TestCase):
    def test_deterministic_key_independent_of_json_order(self):
        a = event()
        b = dict(reversed(list(a.items())))
        self.assertEqual(event_key(a), event_key(b))

    def test_new_external_event_gets_new_key(self):
        self.assertNotEqual(event_key(event("msg-1")), event_key(event("msg-2")))

    def test_network_and_namespace_domain_separate(self):
        base = event()
        self.assertNotEqual(event_key(base), event_key(event(network="ethereum")))
        self.assertNotEqual(event_key(base), event_key(event(namespace="payment/charge")))

    def test_draft_worker_price_not_in_event_schema(self):
        with self.assertRaises(AgentWitnessError):
            event_key({**event(), "draft": "hello"})
        with self.assertRaises(AgentWitnessError):
            event_key({**event(), "worker": "seat-a"})
        with self.assertRaises(AgentWitnessError):
            event_key({**event(), "price": 199})

    def test_bool_string_aliases_fail(self):
        bad = event()
        bad["event_id"] = True
        with self.assertRaises(AgentWitnessError):
            event_key(bad)

    def test_provider_alias_not_silently_normalized(self):
        self.assertNotEqual(event_key(event(provider="gmail")), event_key(event(provider="googlemail")))

    def test_invalid_caseful_provider_rejected(self):
        with self.assertRaises(AgentWitnessError):
            event_key(event(provider="Gmail"))

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"version":"agentwitness-event-v1","network":"monad","namespace":"x","provider":"gmail","event_id":"a","event_id":"b"}'
        with self.assertRaises(DuplicateKeyError):
            strict_loads(raw)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(AgentWitnessError):
            strict_loads('{"x":NaN}')


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.registry = InMemoryRegistry()
        self.key = event_key(event())
        self.intent = intent_hash(b"private draft")

    def test_one_claim_only_even_with_different_intent(self):
        self.registry.claim(self.key, A, self.intent)
        with self.assertRaises(AlreadyClaimed):
            self.registry.claim(self.key, B, intent_hash(b"other draft"))

    def test_only_claimant_can_finalize(self):
        self.registry.claim(self.key, A, self.intent)
        with self.assertRaises(NotClaimant):
            self.registry.finalize(self.key, B, Outcome.COMPLETED, outcome_hash(b"sent"))

    def test_second_finalization_fails(self):
        self.registry.claim(self.key, A, self.intent)
        self.registry.finalize(self.key, A, Outcome.REJECTED, outcome_hash(b"rejected"))
        with self.assertRaises(AlreadyFinalized):
            self.registry.finalize(self.key, A, Outcome.COMPLETED, outcome_hash(b"late sent"))

    def test_unknown_can_reconcile_once(self):
        self.registry.claim(self.key, A, self.intent)
        self.registry.finalize(self.key, A, Outcome.OUTCOME_UNKNOWN, outcome_hash(b"timeout"))
        self.registry.reconcile(self.key, A, Resolution.COMPLETED, outcome_hash(b"provider sent id=123"))
        self.assertEqual("RECONCILED_COMPLETED", self.registry.effective_outcome(self.key))
        with self.assertRaises(NotReconcilable):
            self.registry.reconcile(self.key, A, Resolution.REJECTED, outcome_hash(b"no"))

    def test_known_outcome_cannot_reconcile(self):
        self.registry.claim(self.key, A, self.intent)
        self.registry.finalize(self.key, A, Outcome.COMPLETED, outcome_hash(b"sent"))
        with self.assertRaises(NotReconcilable):
            self.registry.reconcile(self.key, A, Resolution.HELD, outcome_hash(b"hold"))

    def test_zero_digests_rejected(self):
        with self.assertRaises(AgentWitnessError):
            self.registry.claim("0x" + "0" * 64, A, self.intent)
        with self.assertRaises(AgentWitnessError):
            self.registry.claim(self.key, A, "0x" + "0" * 64)

    def test_concurrent_race_exactly_one_winner(self):
        n = 48
        barrier = threading.Barrier(n)
        winners = []
        lock = threading.Lock()

        def runner(i: int):
            claimant = "0x" + f"{i + 1:040x}"
            barrier.wait()
            try:
                self.registry.claim(self.key, claimant, intent_hash(f"draft-{i}".encode()))
                with lock:
                    winners.append(claimant)
            except AlreadyClaimed:
                pass

        threads = [threading.Thread(target=runner, args=(i,)) for i in range(n)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len(winners))

    def test_receipt_tamper_changes_digest(self):
        self.registry.claim(self.key, A, self.intent)
        claim = self.registry.read(self.key)
        assert claim is not None
        receipt = make_receipt(self.key, claim)
        digest = receipt_digest(receipt)
        tampered = dict(receipt)
        tampered["claimant"] = B
        self.assertNotEqual(digest, receipt_digest(tampered))

    def test_private_body_not_present_in_receipt(self):
        private = b"secret customer body: please do not publish"
        registry = InMemoryRegistry()
        registry.claim(self.key, A, intent_hash(private))
        claim = registry.read(self.key)
        assert claim is not None
        rendered = json.dumps(make_receipt(self.key, claim))
        self.assertNotIn("secret customer body", rendered)


class SoliditySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "contracts" / "AgentWitnessRegistry.sol").read_text(encoding="utf-8")

    def test_contract_has_no_generic_external_call_surface(self):
        lowered = self.source.lower()
        self.assertNotIn("delegatecall", lowered)
        self.assertNotIn("selfdestruct", lowered)
        self.assertNotIn(".call{", lowered)

    def test_contract_exposes_required_transitions(self):
        for signature in (
            "function claim(bytes32 eventKey, bytes32 intentHash)",
            "function finalize(bytes32 eventKey, Outcome outcome, bytes32 outcomeHash)",
            "function reconcile(bytes32 eventKey, Resolution resolution, bytes32 resolutionHash)",
        ):
            self.assertIn(signature, self.source)

    def test_contract_rejects_zero_hashes(self):
        self.assertGreaterEqual(self.source.count("bytes32(0)"), 4)


if __name__ == "__main__":
    unittest.main()
