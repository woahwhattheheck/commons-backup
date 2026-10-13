from __future__ import annotations

import copy
import unittest

from tools.outbound_send_guard.atomic_lease import LeaseError, acquire, verify_receipt

ANCHOR = "a" * 40
PREFLIGHT = "b" * 64
TAG = "c" * 40
OTHER = "d" * 40


def claim(**updates):
    value = {
        "repo": "woahwhattheheck/commons",
        "buyer_scope": "atlab.com",
        "offer_scope": "englewood-rfp-26-031-lims-teaming",
        "claimant": "Z-Meridian-913506-L91",
        "claim_id": "atl-englewood-zmer-20260913",
        "claim_started_at": "2026-09-13T09:26:20Z",
        "anchor_sha": ANCHOR,
        "preflight_sha256": PREFLIGHT,
    }
    value.update(updates)
    return value


class Fake:
    def __init__(self, *, tag_status=201, tag_sha=TAG, ref_status=201, ref_sha=TAG, read_status=200, read_sha=TAG):
        self.tag_status = tag_status
        self.tag_sha = tag_sha
        self.ref_status = ref_status
        self.ref_sha = ref_sha
        self.read_status = read_status
        self.read_sha = read_sha
        self.calls = []

    def __call__(self, method, path, body):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.endswith("/git/tags"):
            return self.tag_status, {"sha": self.tag_sha} if self.tag_sha else {}
        if path.endswith("/git/refs"):
            payload = {"object": {"sha": self.ref_sha}} if self.ref_sha else {}
            return self.ref_status, payload
        if "/git/ref/" in path:
            payload = {"object": {"sha": self.read_sha}} if self.read_sha else {}
            return self.read_status, payload
        raise AssertionError(path)


class LeaseTests(unittest.TestCase):
    def test_create_201_exact_object_acquires(self):
        fake = Fake()
        out = acquire(claim(), fake)
        self.assertTrue(out["lease_held_by_claimant"])
        self.assertEqual(out["decision"], "LEASE_HELD")
        self.assertEqual(out["reason"], "ACQUIRED_CREATE_201")
        self.assertFalse(out["external_send_authorized"])
        self.assertEqual([c[0] for c in fake.calls], ["POST", "POST"])

    def test_same_seam_has_same_ref_across_claimants(self):
        a = acquire(claim(claimant="Z-Meridian-913506-L91"), Fake())
        b = acquire(claim(claimant="Z-Other-999"), Fake())
        self.assertEqual(a["lease_ref"], b["lease_ref"])
        self.assertEqual(a["seam_sha256"], b["seam_sha256"])
        self.assertNotEqual(a["tag_object_sha"], None)

    def test_different_offer_has_different_ref(self):
        a = acquire(claim(), Fake())
        b = acquire(claim(offer_scope="different-offer"), Fake())
        self.assertNotEqual(a["lease_ref"], b["lease_ref"])

    def test_422_readback_other_holds(self):
        fake = Fake(ref_status=422, ref_sha=None, read_sha=OTHER)
        out = acquire(claim(), fake)
        self.assertFalse(out["lease_held_by_claimant"])
        self.assertEqual(out["reason"], "HELD_BY_OTHER")
        self.assertEqual([c[0] for c in fake.calls], ["POST", "POST", "GET"])

    def test_422_readback_self_recovers_retry(self):
        fake = Fake(ref_status=422, ref_sha=None, read_sha=TAG)
        out = acquire(claim(), fake)
        self.assertTrue(out["lease_held_by_claimant"])
        self.assertEqual(out["reason"], "ACQUIRED_READBACK_SELF")

    def test_indeterminate_create_self_recovers(self):
        for status in (0, 408, 500, 502, 503, 504):
            with self.subTest(status=status):
                out = acquire(claim(), Fake(ref_status=status, ref_sha=None, read_sha=TAG))
                self.assertTrue(out["lease_held_by_claimant"])
                self.assertEqual(out["reason"], "ACQUIRED_READBACK_SELF")

    def test_indeterminate_create_other_holds(self):
        out = acquire(claim(), Fake(ref_status=502, ref_sha=None, read_sha=OTHER))
        self.assertEqual(out["decision"], "HOLD")
        self.assertEqual(out["reason"], "HELD_BY_OTHER")

    def test_indeterminate_create_404_holds(self):
        out = acquire(claim(), Fake(ref_status=502, ref_sha=None, read_status=404, read_sha=None))
        self.assertEqual(out["reason"], "ACQUIRE_OUTCOME_UNPROVEN")

    def test_readback_failure_holds(self):
        out = acquire(claim(), Fake(ref_status=422, ref_sha=None, read_status=503, read_sha=None))
        self.assertEqual(out["reason"], "READBACK_FAILED_503")

    def test_success_body_mismatch_forces_readback(self):
        fake = Fake(ref_status=201, ref_sha=OTHER, read_sha=TAG)
        out = acquire(claim(), fake)
        self.assertTrue(out["lease_held_by_claimant"])
        self.assertEqual(out["reason"], "ACQUIRED_READBACK_SELF")
        self.assertEqual([c[0] for c in fake.calls], ["POST", "POST", "GET"])

    def test_definitive_ref_rejection_holds_without_readback(self):
        fake = Fake(ref_status=403, ref_sha=None)
        out = acquire(claim(), fake)
        self.assertFalse(out["lease_held_by_claimant"])
        self.assertEqual(out["reason"], "ACQUIRE_REJECTED_403")
        self.assertEqual([c[0] for c in fake.calls], ["POST", "POST"])

    def test_tag_object_failure_is_hard_error(self):
        with self.assertRaisesRegex(LeaseError, "TAG_OBJECT_CREATE_FAILED_502"):
            acquire(claim(), Fake(tag_status=502, tag_sha=None))

    def test_machine_tokens_require_lowercase_ascii(self):
        with self.assertRaisesRegex(LeaseError, "lowercase ASCII"):
            acquire(claim(buyer_scope="ATL.com"), Fake())

    def test_exact_fields_required(self):
        c = claim(); c["extra"] = 1
        with self.assertRaisesRegex(LeaseError, "exact fields"):
            acquire(c, Fake())

    def test_invalid_anchor_rejected_before_network(self):
        fake = Fake()
        with self.assertRaisesRegex(LeaseError, "anchor_sha"):
            acquire(claim(anchor_sha="abc"), fake)
        self.assertEqual(fake.calls, [])

    def test_preflight_digest_bound_into_receipt(self):
        out = acquire(claim(), Fake())
        self.assertEqual(out["preflight_sha256"], PREFLIGHT)

    def test_claimant_does_not_change_seam(self):
        a = acquire(claim(claimant="Seat-One"), Fake())
        b = acquire(claim(claimant="Seat-Two"), Fake())
        self.assertEqual(a["seam_sha256"], b["seam_sha256"])

    def test_claim_metadata_changes_tag_payload_not_lease_ref(self):
        f1, f2 = Fake(), Fake()
        a = acquire(claim(claim_id="claim-one"), f1)
        b = acquire(claim(claim_id="claim-two"), f2)
        self.assertEqual(a["lease_ref"], b["lease_ref"])
        self.assertNotEqual(f1.calls[0][2]["message"], f2.calls[0][2]["message"])

    def test_valid_receipt_verifies(self):
        self.assertTrue(verify_receipt(acquire(claim(), Fake())))

    def test_receipt_tamper_rejected(self):
        out = acquire(claim(), Fake())
        out["claimant"] = "Seat-Tampered"
        with self.assertRaisesRegex(LeaseError, "digest mismatch"):
            verify_receipt(out)

    def test_receipt_cannot_claim_send_authority(self):
        out = acquire(claim(), Fake())
        out["external_send_authorized"] = True
        material = dict(out); material.pop("receipt_sha256")
        import hashlib, json
        out["receipt_sha256"] = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        with self.assertRaisesRegex(LeaseError, "never authorize"):
            verify_receipt(out)

    def test_receipt_held_requires_exact_observed_object(self):
        out = acquire(claim(), Fake())
        out["observed_ref_sha"] = OTHER
        material = dict(out); material.pop("receipt_sha256")
        import hashlib, json
        out["receipt_sha256"] = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        with self.assertRaisesRegex(LeaseError, "prove exact ref object"):
            verify_receipt(out)

    def test_receipt_ref_must_bind_seam(self):
        out = acquire(claim(), Fake())
        out["lease_ref"] = "refs/tags/outbound-lease-v1/" + ("f" * 64)
        material = dict(out); material.pop("receipt_sha256")
        import hashlib, json
        out["receipt_sha256"] = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        with self.assertRaisesRegex(LeaseError, "lease_ref/seam mismatch"):
            verify_receipt(out)


if __name__ == "__main__":
    unittest.main()
