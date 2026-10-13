from __future__ import annotations

import ast
import hashlib
import json
import tempfile
import threading
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import revenue.organization_outbound_lease.core as core
from revenue.organization_outbound_lease.core import (
    PRESSURE_DOMAIN,
    RSA_SHA256_DIGESTINFO_PREFIX,
    RsaPublicKey,
    acquire_lease,
    canonical_json,
    finalize_lease,
    fingerprint_organization,
    holder_capability_commitment,
    pressure_attestation_body,
    verify_lease_document,
)
from revenue.organization_outbound_lease.stores import (
    FileLeaseStore,
    GitHubContentsLeaseStore,
    StoreConflict,
    StoreUncertain,
)
from revenue.organization_outbound_lease.strict import parse_json_strict, write_exclusive

K1 = b"f" * 32
K3 = b"n" * 32
CAP_A = bytes.fromhex("a1" * 32)
CAP_B = bytes.fromhex("b2" * 32)
H = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64
RSA_N_HEX = "c84c36f5cde2a671b68bdc88e055e20254ce63483ee8aa66bb0dc4a73ba17e57eea7d3dd78e8b11af57d5ccdab9e3759c507c448a6664de0228b3b47e98c1ce52a3791b3dbdfa697b314b0c9013335e5b0fa11bff3699cdd6cfd4b05f9e870b4ade9f1afa491207180cec7e3da920da2f97fec6cf3c592d03be7f82195c6eb906aa3dd6edc95072d2ca1ee791dcc3bb7611f721e4bdc851f88e043d673b47d145cddfa98207a9edd0a7a96cbcbccdd1739845fa2f1a4730295db8d447a4cc6ce8ee93e970d120431a2c3034d744e1705a709db23d4344b2bd5729ed977b3d007b460296241f69e1b83097b06d033fec98776b7a34dbcafb1a1a45a431bc6a725"
RSA_D_HEX = "17628a922530fe94cd26c41f38edddfebeaefff969dad936384591bda2a126b2967b02a9db59737ffdc45ea6e69008cf52c926da028f742d246b5406ffd5eb73b7fb97e7c35677c9434fb99a262937f432b6e7869d2129fed2203a779ea74c2d5416b9b0738abc1a745af00c82b2c5a3cef468028a6d7948158e6e32619dc157bc9ff28b377e499f8f41ff6c1e08ff5eee70634b0d97be036d94ba6cc69c7ce8f7bddfd98db7369cf60ed8b525b60f381fa949a74397ffbab8701fb5eb8a0a8187bcea23e3b641f7e7e4f84ada0182f6a332dc835231496d3e8e69241f0388fb541a4d4d5e5317ecd9c323ea9594ac0e34ed8c3d33d992efe3d95316f3a600ab"
RSA_N = int(RSA_N_HEX, 16)
RSA_D = int(RSA_D_HEX, 16)
RSA_E = 65537
VERIFIER = RsaPublicKey.from_hex(key_id="pressure-test-2026", modulus_hex=RSA_N_HEX, exponent=RSA_E)


def ts(offset_seconds=0):
    return (datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rsa_sign_test(message: bytes) -> str:
    k = (RSA_N.bit_length() + 7) // 8
    digest_info = RSA_SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    pad_len = k - len(digest_info) - 3
    em = b"\x00\x01" + (b"\xff" * pad_len) + b"\x00" + digest_info
    sig = pow(int.from_bytes(em, "big"), RSA_D, RSA_N)
    return sig.to_bytes(k, "big").hex()


def pressure(org, at=None, state="READY_FOR_SINGLE_WRITER_REVIEW"):
    body = pressure_attestation_body({
        "schema": "commons.organization-pressure-attestation/v2",
        "organizationFingerprint": org,
        "pressureReceiptSha256": H,
        "authorityCommitment": H2,
        "ledgerCommitment": H3,
        "verifiedState": state,
        "verifiedAt": at or ts(-2),
    })
    return {
        "body": body,
        "algorithm": "RS256-PKCS1-v1_5",
        "keyId": VERIFIER.key_id,
        "signatureHex": _rsa_sign_test(PRESSURE_DOMAIN + canonical_json(body)),
    }


def req(org, claim="claim-a", prospect=H4, route="5"*64, opp="6"*64, cap=CAP_A, requested_at=None, pressure_at=None):
    return {
        "schema": "commons.organization-outbound-acquire/v2",
        "claimId": claim,
        "organizationFingerprint": org,
        "prospectFingerprint": prospect,
        "routeCommitment": route,
        "opportunityCommitment": opp,
        "holderCapabilityCommitment": holder_capability_commitment(cap),
        "requestedAt": requested_at or ts(-1),
        "pressureAttestation": pressure(org, at=pressure_at or ts(-2)),
    }


def fin(lease, outcome="UNSENT_RELEASED", oid="outcome-a", at=None, cap=CAP_A):
    return {
        "schema": "commons.organization-outbound-finalize/v2",
        "organizationFingerprint": lease["organizationFingerprint"],
        "leaseId": lease["leaseId"],
        "leaseNonce": lease["leaseNonce"],
        "claimId": lease["claimId"],
        "outcomeId": oid,
        "outcome": outcome,
        "observedAt": at or ts(0),
        "evidenceCommitment": "8"*64,
        "holderCapability": cap.hex(),
    }


class DeleteCommittedThenUncertainStore(FileLeaseStore):
    def delete_active(self, org_fingerprint: str, expected_generation: str) -> None:
        super().delete_active(org_fingerprint, expected_generation)
        raise StoreUncertain("simulated lost DELETE response")


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.store = FileLeaseStore(self.td.name)
        self.org = fingerprint_organization(b"example-inc", K1)
        self.org2 = fingerprint_organization(b"other-inc", K1)

    def acquire(self, request=None, store=None):
        return acquire_lease(store or self.store, request or req(self.org), pressure_verifier=VERIFIER, lease_nonce_key=K3)

    def test_fingerprint_privacy_and_determinism(self):
        a = fingerprint_organization(b"Example Inc canonical", K1)
        self.assertEqual(a, fingerprint_organization(b"Example Inc canonical", K1))
        self.assertNotIn("Example", a)
        self.assertNotEqual(a, fingerprint_organization(b"Example Inc canonical", b"x"*32))

    def test_holder_capability_must_be_exactly_32_bytes(self):
        with self.assertRaises(ValueError): holder_capability_commitment(b"x" * 31)
        with self.assertRaises(ValueError): holder_capability_commitment(b"x" * 33)
        self.assertEqual(len(holder_capability_commitment(b"x" * 32)), 64)

    def test_pressure_verifier_has_no_signing_secret_or_mint_helper(self):
        self.assertFalse(hasattr(core, "mint_pressure_attestation_for_host"))
        self.assertEqual(set(VERIFIER.__dict__), {"key_id", "modulus", "exponent"})
        r = req(self.org)
        r["pressureAttestation"]["signatureHex"] = "00" * 256
        with self.assertRaises(ValueError):
            self.acquire(r)

    def test_pressure_signature_mutation_rejected(self):
        r = req(self.org)
        r["pressureAttestation"]["body"]["ledgerCommitment"] = "c" * 64
        with self.assertRaises(ValueError):
            self.acquire(r)

    def test_cross_org_attestation_rejected(self):
        r = req(self.org)
        r["pressureAttestation"] = pressure(self.org2)
        with self.assertRaises(ValueError):
            self.acquire(r)

    def test_wrong_pressure_key_id_rejected(self):
        r = req(self.org)
        r["pressureAttestation"]["keyId"] = "other-key"
        with self.assertRaises(ValueError):
            self.acquire(r)

    def test_happy_acquire_and_exact_replay(self):
        r = req(self.org)
        one = self.acquire(r)
        two = self.acquire(r)
        self.assertEqual(one.state, "LEASE_ACQUIRED")
        self.assertFalse(one.replay)
        self.assertTrue(two.replay)
        self.assertEqual(one.lease["leaseSha256"], two.lease["leaseSha256"])
        self.assertFalse(one.lease["externalSendAuthorized"])

    def test_stale_exact_active_replay_recovers_without_new_authority(self):
        r = req(self.org)
        one = self.acquire(r)
        future = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=900)
        with patch("revenue.organization_outbound_lease.core._process_now", return_value=future):
            replay = self.acquire(r)
        self.assertTrue(replay.replay)
        self.assertEqual(replay.lease["leaseId"], one.lease["leaseId"])
        self.assertEqual(replay.active_generation, one.active_generation)

    def test_same_org_different_prospect_route_and_opportunity_collide(self):
        first = self.acquire()
        for variant in [
            req(self.org, claim="claim-b", prospect="9"*64, cap=CAP_B),
            req(self.org, claim="claim-c", route="a"*64, cap=CAP_B),
            req(self.org, claim="claim-d", opp="b"*64, cap=CAP_B),
        ]:
            result = self.acquire(variant)
            self.assertEqual(result.state, "ORGANIZATION_ALREADY_LEASED")
            self.assertEqual(result.lease["leaseId"], first.lease["leaseId"])

    def test_different_organizations_independent(self):
        a = self.acquire(req(self.org, claim="a"))
        b = self.acquire(req(self.org2, claim="b", cap=CAP_B))
        self.assertEqual(a.state, "LEASE_ACQUIRED")
        self.assertEqual(b.state, "LEASE_ACQUIRED")
        self.assertNotEqual(a.lease["organizationFingerprint"], b.lease["organizationFingerprint"])

    def test_changed_upstream_generation_remains_blocked(self):
        first = self.acquire()
        r = req(self.org, claim="claim-new", cap=CAP_B)
        body = deepcopy(r["pressureAttestation"]["body"])
        body["ledgerCommitment"] = "c"*64
        r["pressureAttestation"] = pressure(self.org)
        r["pressureAttestation"]["body"] = body
        r["pressureAttestation"]["signatureHex"] = _rsa_sign_test(PRESSURE_DOMAIN + canonical_json(body))
        blocked = self.acquire(r)
        self.assertEqual(blocked.state, "ORGANIZATION_ALREADY_LEASED")
        self.assertEqual(blocked.lease["leaseId"], first.lease["leaseId"])

    def test_thread_race_exactly_one_distinct_claim_winner(self):
        barrier = threading.Barrier(8)
        results = []
        errors = []
        lock = threading.Lock()
        caps = [bytes([i + 1]) * 32 for i in range(8)]
        def worker(i):
            try:
                barrier.wait()
                out = self.acquire(req(self.org, claim="claim-%d" % i, prospect=("%x" % (i+1))*64, cap=caps[i]))
                with lock: results.append(out)
            except BaseException as exc:
                with lock: errors.append(exc)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [], "worker exceptions: %r" % errors)
        self.assertEqual(len(results), 8)
        wins = [r for r in results if r.state == "LEASE_ACQUIRED" and not r.replay]
        self.assertEqual(len(wins), 1)
        self.assertEqual(len({r.lease["leaseId"] for r in results}), 1)

    def test_loser_with_full_public_lease_cannot_finalize_winner(self):
        first = self.acquire(req(self.org, cap=CAP_A))
        public_copy = deepcopy(first.lease)
        self.assertNotIn("holderCapability", public_copy)
        for outcome in ("SENT", "OUTCOME_UNKNOWN", "REJECTED", "HELD_AUTHORITY", "UNSENT_RELEASED"):
            with self.subTest(outcome=outcome):
                attack = fin(public_copy, outcome=outcome, oid="attack-" + outcome.lower(), cap=CAP_B)
                with self.assertRaises(ValueError):
                    finalize_lease(self.store, attack)
        current_raw, _ = self.store.get_active(self.org)
        self.assertEqual(json.loads(current_raw)["leaseId"], first.lease["leaseId"])
        self.assertIsNone(self.store.get_outcome(self.org, first.lease["leaseId"]))

    def test_finalize_unsent_persists_outcome_before_release_and_allows_new_identity(self):
        first = self.acquire()
        result = finalize_lease(self.store, fin(first.lease, "UNSENT_RELEASED"))
        self.assertTrue(result.active_released)
        self.assertIsNone(self.store.get_active(self.org))
        self.assertIsNotNone(self.store.get_outcome(self.org, first.lease["leaseId"]))
        second = self.acquire(req(self.org, claim="claim-second", prospect="9"*64, cap=CAP_B))
        self.assertEqual(second.state, "LEASE_ACQUIRED")
        self.assertNotEqual(first.lease["leaseId"], second.lease["leaseId"])

    def test_exact_same_acquire_after_release_is_terminal_not_aba_successor(self):
        original = req(self.org)
        first = self.acquire(original)
        release = fin(first.lease, "UNSENT_RELEASED", oid="release-aba")
        finalize_lease(self.store, release)
        again = self.acquire(original)
        self.assertEqual(again.state, "LEASE_FINALIZED_UNSENT_RELEASED")
        self.assertEqual(again.terminal_outcome, "UNSENT_RELEASED")
        self.assertIsNone(self.store.get_active(self.org))
        replay = finalize_lease(self.store, release)
        self.assertTrue(replay.replay)
        self.assertIsNone(self.store.get_active(self.org))

    def test_blocking_terminals_make_exact_acquire_replay_nonaffirmative_even_when_stale(self):
        for outcome in ("SENT", "OUTCOME_UNKNOWN", "REJECTED", "HELD_AUTHORITY"):
            with self.subTest(outcome=outcome):
                root = tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
                store = FileLeaseStore(root.name)
                r = req(self.org, claim="c-" + outcome.lower())
                first = self.acquire(r, store=store)
                finalize_lease(store, fin(first.lease, outcome=outcome, oid="o-" + outcome.lower()))
                future = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=900)
                with patch("revenue.organization_outbound_lease.core._process_now", return_value=future):
                    replay = self.acquire(r, store=store)
                self.assertEqual(replay.state, "LEASE_FINALIZED_%s" % outcome)
                self.assertNotEqual(replay.state, "LEASE_ACQUIRED")

    def test_unsent_finalize_exact_replay_after_release_is_idempotent(self):
        first = self.acquire()
        request = fin(first.lease, "UNSENT_RELEASED", oid="release-replay")
        one = finalize_lease(self.store, request)
        future = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1200)
        with patch("revenue.organization_outbound_lease.core._process_now", return_value=future):
            two = finalize_lease(self.store, request)
        self.assertFalse(one.replay)
        self.assertTrue(two.replay)
        self.assertTrue(two.active_released)
        self.assertEqual(two.outcome["outcomeSha256"], one.outcome["outcomeSha256"])

    def test_delete_committed_response_lost_reconciles(self):
        root = tempfile.TemporaryDirectory(); self.addCleanup(root.cleanup)
        store = DeleteCommittedThenUncertainStore(root.name)
        first = self.acquire(store=store)
        result = finalize_lease(store, fin(first.lease, "UNSENT_RELEASED", oid="lost-delete-response"))
        self.assertTrue(result.active_released)
        self.assertIsNone(store.get_active(self.org))
        replay = finalize_lease(store, fin(first.lease, "UNSENT_RELEASED", oid="lost-delete-response"))
        self.assertTrue(replay.replay)

    def test_old_unsent_finalize_replay_never_deletes_distinct_successor(self):
        first = self.acquire()
        request = fin(first.lease, "UNSENT_RELEASED", oid="release-before-successor")
        finalize_lease(self.store, request)
        successor = self.acquire(req(self.org, claim="successor", prospect="9"*64, cap=CAP_B))
        replay = finalize_lease(self.store, request)
        self.assertTrue(replay.replay)
        current_raw, _ = self.store.get_active(self.org)
        current = json.loads(current_raw)
        self.assertEqual(current["leaseId"], successor.lease["leaseId"])

    def test_released_outcome_mutation_conflicts_on_replay(self):
        first = self.acquire()
        request = fin(first.lease, "UNSENT_RELEASED", oid="release-mutation")
        finalize_lease(self.store, request)
        changed = deepcopy(request); changed["evidenceCommitment"] = "d"*64
        with self.assertRaises(ValueError): finalize_lease(self.store, changed)

    def test_wrong_capability_cannot_replay_real_terminal(self):
        first = self.acquire()
        request = fin(first.lease, "SENT", oid="sent-once")
        finalize_lease(self.store, request)
        attack = deepcopy(request); attack["holderCapability"] = CAP_B.hex()
        with self.assertRaises(ValueError): finalize_lease(self.store, attack)

    def test_cross_lease_finalization_rejected(self):
        first = self.acquire()
        f = fin(first.lease); f["leaseId"] = "0"*64
        with self.assertRaises(ValueError): finalize_lease(self.store, f)

    def test_outcome_before_acquire_rejected(self):
        first = self.acquire()
        with self.assertRaises(ValueError): finalize_lease(self.store, fin(first.lease, at=ts(-30)))

    def test_outcome_id_mutation_conflicts(self):
        first = self.acquire()
        f = fin(first.lease, outcome="SENT", oid="same")
        one = finalize_lease(self.store, f)
        self.assertFalse(one.replay)
        changed = deepcopy(f); changed["evidenceCommitment"] = "d"*64
        with self.assertRaises(ValueError): finalize_lease(self.store, changed)

    def test_stale_and_future_preflight_rejected_for_new_authority(self):
        with self.assertRaises(ValueError):
            self.acquire(req(self.org, claim="stale", requested_at=ts(-301), pressure_at=ts(-302)))
        with self.assertRaises(ValueError):
            self.acquire(req(self.org, claim="future", requested_at=ts(10), pressure_at=ts(9)))

    def test_pressure_cannot_postdate_acquire(self):
        with self.assertRaises(ValueError):
            self.acquire(req(self.org, claim="reverse", requested_at=ts(-2), pressure_at=ts(-1)))

    def test_stale_new_outcome_rejected(self):
        first = self.acquire()
        with self.assertRaises(ValueError): finalize_lease(self.store, fin(first.lease, at=ts(-601)))

    def test_lease_digest_tamper_rejected(self):
        first = self.acquire()
        bad = deepcopy(first.lease); bad["routeCommitment"] = "e"*64
        with self.assertRaises(ValueError): verify_lease_document(bad)

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError): parse_json_strict('{"a":1,"a":2}')
        with self.assertRaises(ValueError): parse_json_strict('{"a":NaN}')

    def test_unknown_fields_rejected(self):
        r = req(self.org); r["unexpected"] = True
        with self.assertRaises(ValueError): self.acquire(r)

    def test_exclusive_output_refuses_overwrite_and_symlink(self):
        p = Path(self.td.name) / "receipt.json"
        write_exclusive(p, b"one")
        with self.assertRaises(FileExistsError): write_exclusive(p, b"two")
        target = Path(self.td.name) / "target"; target.write_text("x")
        link = Path(self.td.name) / "link"
        try: link.symlink_to(target)
        except (OSError, NotImplementedError): self.skipTest("symlink unavailable")
        with self.assertRaises(FileExistsError): write_exclusive(link, b"bad")

    def test_source_syntax_is_python39_compatible(self):
        root = Path(__file__).parents[1] / "revenue" / "organization_outbound_lease"
        for path in list(root.glob("*.py")) + [Path(__file__)]:
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), filename=str(path), feature_version=(3, 9))


class FakeGitHubTests(unittest.TestCase):
    def test_create_conflict_and_conditional_delete_payload(self):
        calls = []
        def opener(request):
            body = request.data.decode() if request.data else None
            calls.append((request.method, request.full_url, body))
            if request.method == "PUT": return 201, b'{"content":{"sha":"blob123"}}'
            if request.method == "DELETE": return 200, b'{}'
            raise AssertionError(request.method)
        store = GitHubContentsLeaseStore(repository="o/r", branch="leases", token="t", opener=opener)
        sha = store.create_active("1"*64, b"{}")
        self.assertEqual(sha, "blob123")
        store.delete_active("1"*64, "blob123")
        delete_payload = json.loads(calls[-1][2])
        self.assertEqual(delete_payload["sha"], "blob123")
        self.assertEqual(delete_payload["branch"], "leases")

    def test_get_uses_ref_query_not_encoded_path(self):
        seen = []
        payload = {"type":"file","sha":"abc","content":"e30="}
        def opener(request):
            seen.append(request.full_url)
            return 200, json.dumps(payload).encode()
        store = GitHubContentsLeaseStore(repository="o/r", branch="lease/branch", token="t", opener=opener)
        self.assertEqual(store.get_active("1"*64), (b"{}", "abc"))
        self.assertIn("?ref=lease%2Fbranch", seen[0])
        self.assertNotIn("%3Fref", seen[0])

    def test_conflict_status_maps_to_store_conflict(self):
        def opener(request): return 422, b'{"message":"exists"}'
        store = GitHubContentsLeaseStore(repository="o/r", branch="leases", token="t", opener=opener)
        with self.assertRaises(StoreConflict): store.create_active("1"*64, b"{}")


if __name__ == "__main__":
    unittest.main()
