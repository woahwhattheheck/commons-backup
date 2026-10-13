from __future__ import annotations

import hashlib
import json
import threading
import unittest
from typing import Any, Mapping

from revenue.outbound_send_consumer.consume import ConsumerError, ProviderRejected, consume_once


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


class FakeGit:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tags: dict[str, dict[str, Any]] = {}
        self.refs: dict[str, str] = {}
        self.fail_next_ref_create_status: int | None = None
        self.fail_outcome_ref = False

    @staticmethod
    def _path_ref(path: str) -> str:
        prefix = "/git/ref/"
        tail = path[path.index(prefix) + len(prefix):]
        from urllib.parse import unquote
        return "refs/" + unquote(tail)

    def __call__(self, method: str, path: str, body: Mapping[str, Any] | None):
        with self._lock:
            if method == "POST" and path.endswith("/git/tags"):
                assert body is not None
                sha = hashlib.sha256(canon(body)).hexdigest()
                self.tags[sha] = {"sha": sha, **dict(body)}
                return 201, {"sha": sha}
            if method == "POST" and path.endswith("/git/refs"):
                assert body is not None
                ref = body["ref"]
                sha = body["sha"]
                if self.fail_outcome_ref and ref.startswith("refs/tags/outbound-consume-outcome-v1/"):
                    return 500, None
                if self.fail_next_ref_create_status is not None:
                    status = self.fail_next_ref_create_status
                    self.fail_next_ref_create_status = None
                    return status, None
                if ref in self.refs:
                    return 422, {"message": "Reference already exists"}
                self.refs[ref] = sha
                return 201, {"object": {"sha": sha}}
            if method == "GET" and "/git/ref/" in path:
                ref = self._path_ref(path)
                if ref not in self.refs:
                    return 404, None
                return 200, {"object": {"sha": self.refs[ref]}}
            if method == "GET" and "/git/tags/" in path:
                sha = path.rsplit("/", 1)[-1]
                tag = self.tags.get(sha)
                return (200, tag) if tag is not None else (404, None)
            raise AssertionError((method, path, body))


def fixture(claimant: str = "Z-Test-A"):
    host = {
        "repo": "woahwhattheheck/commons",
        "buyer_scope": "acme.example",
        "opportunity_scope": "pilot-2026",
        "event_kind": "initial",
        "event_key": "initial:acme-pilot-2026",
        "provider_request_sha256": "1" * 64,
        "authority_sha256": "2" * 64,
        "anchor_sha": "3" * 40,
    }
    intent = {
        "repo": host["repo"],
        "buyer_scope": host["buyer_scope"],
        "opportunity_scope": host["opportunity_scope"],
        "event_kind": host["event_kind"],
        "event_key": host["event_key"],
        "provider_request_sha256": host["provider_request_sha256"],
        "anchor_sha": host["anchor_sha"],
        "claimant": claimant,
    }
    return host, intent


class ConsumerTests(unittest.TestCase):
    def test_exact_winner_sends_once_and_persists(self):
        git = FakeGit()
        host, intent = fixture()
        calls = []
        receipt = consume_once(
            intent,
            host_raw=host,
            transport=git,
            authority_probe=lambda: host["authority_sha256"],
            provider_callback=lambda key: calls.append(key),
        )
        self.assertEqual(receipt["decision"], "SENT")
        self.assertTrue(receipt["external_send_completed"])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("tjlabs-outbound-v1:"))
        self.assertFalse(receipt["external_send_authorized"])

    def test_two_threads_same_event_only_one_provider_call(self):
        git = FakeGit()
        host, ia = fixture("Z-Thread-A")
        _, ib = fixture("Z-Thread-B")
        barrier = threading.Barrier(2)
        calls: list[str] = []
        lock = threading.Lock()
        receipts: list[dict[str, Any]] = []

        def provider(key: str):
            with lock:
                calls.append(key)
            return None

        def worker(intent):
            barrier.wait()
            r = consume_once(
                intent,
                host_raw=host,
                transport=git,
                authority_probe=lambda: host["authority_sha256"],
                provider_callback=provider,
            )
            with lock:
                receipts.append(r)

        ta = threading.Thread(target=worker, args=(ia,))
        tb = threading.Thread(target=worker, args=(ib,))
        ta.start(); tb.start(); ta.join(); tb.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(r["external_send_completed"] for r in receipts), 1)
        self.assertEqual({r["decision"] for r in receipts}, {"SENT", "SUPPRESSED"})

    def test_draft_price_worker_aliases_collide_by_same_host_seam(self):
        git = FakeGit()
        host, first = fixture("Z-Alias-A")
        _, second = fixture("Z-Alias-B")
        # Caller request digest can differ only by changing the host binding; a
        # same host event does not admit worker/draft/price aliases into seam.
        calls = []
        r1 = consume_once(first, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append("a"))
        r2 = consume_once(second, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append("b"))
        self.assertEqual(r1["decision"], "SENT")
        self.assertEqual(r2["decision"], "SUPPRESSED")
        self.assertEqual(calls, ["a"])
        self.assertTrue(r2["prior_send_observed"])
        self.assertFalse(r2["external_send_completed"])

    def test_host_intent_mismatch_zero_provider_call(self):
        git = FakeGit()
        host, intent = fixture()
        intent["event_key"] = "initial:different"
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["reason"], "HOST_INTENT_MISMATCH")
        self.assertEqual(calls, [])

    def test_authority_absent_before_reservation_zero_provider_call(self):
        git = FakeGit()
        host, intent = fixture()
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: None,
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["reason"], "AUTHORITY_NOT_CURRENT")
        self.assertEqual(calls, [])
        self.assertFalse(git.refs)

    def test_authority_loss_after_reservation_burns_seam(self):
        git = FakeGit()
        host, intent = fixture()
        states = iter([host["authority_sha256"], None])
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: next(states),
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["decision"], "HELD_AUTHORITY")
        self.assertEqual(r["terminal_state"], "HELD_AUTHORITY")
        self.assertEqual(calls, [])
        # Same event can no longer be retried automatically.
        r2 = consume_once(intent, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append(key))
        self.assertEqual(r2["decision"], "SUPPRESSED")
        self.assertEqual(calls, [])

    def test_provider_exception_is_unknown_and_no_retry(self):
        git = FakeGit()
        host, intent = fixture()
        calls = []
        def boom(key):
            calls.append(key)
            raise TimeoutError("timeout")
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=boom)
        self.assertEqual(r["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r["terminal_state"], "OUTCOME_UNKNOWN")
        self.assertEqual(len(calls), 1)
        r2 = consume_once(intent, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append(key))
        self.assertEqual(r2["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r2["reason"], "PRIOR_OUTCOME_UNKNOWN")
        self.assertEqual(len(calls), 1)

    def test_hard_crash_after_reservation_forces_reconcile(self):
        git = FakeGit()
        host, intent = fixture()
        calls = []
        class HardCrash(BaseException):
            pass
        def crash(key):
            calls.append(key)
            raise HardCrash()
        with self.assertRaises(HardCrash):
            consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=crash)
        self.assertEqual(len(calls), 1)
        r2 = consume_once(intent, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append(key))
        self.assertEqual(r2["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r2["reason"], "RESERVATION_HELD_OUTCOME_UNPROVEN")
        self.assertEqual(len(calls), 1)

    def test_known_provider_rejection(self):
        git = FakeGit()
        host, intent = fixture()
        def reject(key):
            raise ProviderRejected("provider_policy_reject")
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=reject)
        self.assertEqual(r["decision"], "REJECTED")
        self.assertFalse(r["external_send_completed"])
        self.assertTrue(r["provider_attempted"])

    def test_arbitrary_callback_result_is_never_repr_or_serialized(self):
        git = FakeGit()
        host, intent = fixture()
        class Hostile:
            def __repr__(self):
                raise AssertionError("repr forbidden")
            def __str__(self):
                raise AssertionError("str forbidden")
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: Hostile())
        self.assertEqual(r["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r["reason"], "PROVIDER_RETURN_CONTRACT_VIOLATION")

    def test_outcome_persistence_uncertainty_never_retries(self):
        git = FakeGit()
        git.fail_outcome_ref = True
        host, intent = fixture()
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r["reason"], "OUTCOME_PERSIST_UNCERTAIN")
        self.assertTrue(r["external_send_completed"])
        self.assertEqual(len(calls), 1)
        git.fail_outcome_ref = False
        r2 = consume_once(intent, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append(key))
        self.assertEqual(r2["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r2["reason"], "RESERVATION_HELD_OUTCOME_UNPROVEN")
        self.assertEqual(len(calls), 1)

    def test_malformed_prior_outcome_forces_reconcile(self):
        git = FakeGit()
        host, intent = fixture()
        calls = []
        first = consume_once(intent, host_raw=host, transport=git,
                             authority_probe=lambda: host["authority_sha256"],
                             provider_callback=lambda key: calls.append(key))
        self.assertEqual(first["decision"], "SENT")
        outcome_ref = first["outcome_ref"]
        tag_sha = git.refs[outcome_ref]
        meta = json.loads(git.tags[tag_sha]["message"])
        meta["reservation_tag_sha"] = "f" * 64
        git.tags[tag_sha]["message"] = canon(meta).decode("ascii") + "\n"
        r2 = consume_once(intent, host_raw=host, transport=git,
                          authority_probe=lambda: host["authority_sha256"],
                          provider_callback=lambda key: calls.append(key))
        self.assertEqual(r2["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r2["reason"], "RESERVATION_HELD_OUTCOME_UNPROVEN")
        self.assertFalse(r2["prior_send_observed"])
        self.assertEqual(len(calls), 1)

    def test_ambiguous_reservation_create_readback_self_recovers(self):
        class AmbiguousOnce(FakeGit):
            def __init__(self):
                super().__init__()
                self.did = False
            def __call__(self, method, path, body):
                if method == "POST" and path.endswith("/git/refs") and body and body["ref"].startswith("refs/tags/outbound-consume-v1/") and not self.did:
                    self.did = True
                    with self._lock:
                        self.refs[body["ref"]] = body["sha"]
                    return 0, None
                return super().__call__(method, path, body)
        git = AmbiguousOnce()
        host, intent = fixture()
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["decision"], "SENT")
        self.assertEqual(len(calls), 1)

    def test_ambiguous_reservation_missing_readback_requires_reconcile(self):
        git = FakeGit()
        git.fail_next_ref_create_status = 0
        host, intent = fixture()
        calls = []
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: calls.append(key))
        self.assertEqual(r["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(r["terminal_state"], "OUTCOME_UNKNOWN")
        self.assertEqual(calls, [])

    def test_receipt_digest_changes_on_truth_change(self):
        git = FakeGit()
        host, intent = fixture()
        r = consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: None)
        copy = dict(r)
        digest = copy.pop("receipt_sha256")
        self.assertEqual(hashlib.sha256(canon(copy)).hexdigest(), digest)
        copy["external_send_completed"] = False
        self.assertNotEqual(hashlib.sha256(canon(copy)).hexdigest(), digest)

    def test_rejects_noncanonical_host_digest(self):
        git = FakeGit()
        host, intent = fixture()
        host["authority_sha256"] = "A" * 64
        with self.assertRaises(ConsumerError):
            consume_once(intent, host_raw=host, transport=git,
                         authority_probe=lambda: host["authority_sha256"],
                         provider_callback=lambda key: None)


if __name__ == "__main__":
    unittest.main()
