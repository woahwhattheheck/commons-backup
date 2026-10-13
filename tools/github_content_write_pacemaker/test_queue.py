from __future__ import annotations
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from tools.github_content_write_pacemaker.github_write_pacemaker import (
    AmbiguousOutcome, COMMITTED, COOLDOWN, IntentConflict,
    NoDispatchableMutation, PacemakerStore, QUEUED, RECONCILE_REQUIRED,
    StoreInvariantError,
)

UTC = dt.timezone.utc
DIGEST = "a" * 64


class Clock:
    def __init__(self):
        self.value = dt.datetime(2026, 9, 14, 7, 0, tzinfo=UTC)
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += dt.timedelta(seconds=seconds)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.store = PacemakerStore(Path(self.tmp.name) / "state.db", clock=self.clock)

    def intent(self, key="one", body=None, path="/provider/path"):
        return {"schema": "commons-github-content-write-intent/v2",
                "mutationKey": key, "method": "POST", "apiPath": path,
                "description": "test mutation",
                "body": {"value": 1} if body is None else body}

    def test_replay_and_conflict(self):
        first, replay = self.store.enqueue(self.intent())
        second, replay_two = self.store.enqueue(self.intent("two"))
        self.assertFalse(replay)
        self.assertTrue(replay_two)
        self.assertEqual(first["mutationKey"], second["mutationKey"])
        with self.assertRaises(IntentConflict):
            self.store.enqueue(self.intent(body={"value": 2}))

    def test_claim_and_commit(self):
        self.store.enqueue(self.intent())
        claim = self.store.claim_next(0)
        self.assertEqual(claim.body, {"value": 1})
        receipt = self.store.record_result(
            claim.mutation_key, attempt=1, classification="committed",
            reason="connector success", provider_status=201,
            provider_receipt_sha256=DIGEST)
        self.assertEqual(receipt["state"], COMMITTED)

    def test_ambiguous_blocks_then_retry(self):
        self.store.enqueue(self.intent())
        claim = self.store.claim_next(0)
        receipt = self.store.record_result(
            claim.mutation_key, attempt=1, classification="ambiguous",
            reason="outcome unknown")
        self.assertEqual(receipt["state"], RECONCILE_REQUIRED)
        with self.assertRaises(AmbiguousOutcome):
            self.store.claim_next(0)
        receipt = self.store.reconcile(
            claim.mutation_key, outcome="retry", observation_ref="readback",
            observation_sha256=DIGEST)
        self.assertEqual(receipt["state"], QUEUED)
        self.clock.advance(1)
        self.assertEqual(self.store.claim_next(0).attempt, 2)

    def test_rate_limit_global_cooldown(self):
        self.store.enqueue(self.intent("a", path="/a"))
        self.store.enqueue(self.intent("b", path="/b"))
        claim = self.store.claim_next(0)
        retry = "2026-09-14T07:01:00Z"
        receipt = self.store.record_result(
            claim.mutation_key, attempt=1, classification="rate_limited",
            reason="cooldown", provider_status=429, retry_at=retry)
        self.assertEqual(receipt["state"], COOLDOWN)
        with self.assertRaises(NoDispatchableMutation):
            self.store.claim_next(0)
        self.clock.advance(60)
        self.assertEqual(self.store.claim_next(0).mutation_key, "a")

    def test_interval_and_attempt_fence(self):
        self.store.enqueue(self.intent("a", path="/a"))
        self.store.enqueue(self.intent("b", path="/b"))
        claim = self.store.claim_next(0)
        with self.assertRaises(StoreInvariantError):
            self.store.record_result(
                claim.mutation_key, attempt=2, classification="rejected",
                reason="wrong attempt")
        self.store.record_result(
            claim.mutation_key, attempt=1, classification="rejected",
            reason="terminal")
        with self.assertRaises(NoDispatchableMutation):
            self.store.claim_next(2)
        self.clock.advance(2)
        self.assertEqual(self.store.claim_next(2).mutation_key, "b")


if __name__ == "__main__":
    unittest.main()
