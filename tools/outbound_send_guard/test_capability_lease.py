from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from tools.outbound_send_guard.capability_lease import (
    CapabilityLeaseError,
    REF_PREFIX,
    acquire,
    verify_possession,
    verify_receipt,
    _capability_commitment,
    _write_capability_file,
)

ANCHOR = "a" * 40
PREFLIGHT = "b" * 64
TAG = "c" * 40
OTHER = "d" * 40
CAPABILITY = "1f" * 32
OTHER_CAPABILITY = "2e" * 32


def claim(**updates):
    value = {
        "repo": "woahwhattheheck/commons",
        "buyer_scope": "atlab.com",
        "offer_scope": "englewood-rfp-26-031-lims-teaming",
        "claimant": "Z-RiemannForge-2142-C5N7",
        "claim_id": "atl-englewood-zrf-20260913",
        "claim_started_at": "2026-09-14T01:56:07Z",
        "anchor_sha": ANCHOR,
        "preflight_sha256": PREFLIGHT,
    }
    value.update(updates)
    return value


class Store:
    def __init__(self):
        self.tag_payload = None
        self.tag_sha = TAG
        self.ref_sha = TAG
        self.ref_create_status = 201
        self.ref_read_status = 200
        self.tag_read_status = 200
        self.calls = []
        self.tag_overrides = {}

    def __call__(self, method, path, body):
        self.calls.append((method, path, copy.deepcopy(body)))
        if method == "POST" and path.endswith("/git/tags"):
            self.tag_payload = copy.deepcopy(body)
            return 201, {"sha": self.tag_sha}
        if method == "POST" and path.endswith("/git/refs"):
            if self.ref_create_status != 201:
                return self.ref_create_status, None
            return 201, {"object": {"sha": self.ref_sha}}
        if method == "GET" and "/git/ref/" in path:
            if self.ref_read_status != 200:
                return self.ref_read_status, None
            return 200, {"object": {"sha": self.ref_sha}}
        if method == "GET" and "/git/tags/" in path:
            if self.tag_read_status != 200:
                return self.tag_read_status, None
            payload = {
                "sha": self.tag_sha,
                "tag": self.tag_payload["tag"],
                "message": self.tag_payload["message"],
                "object": {
                    "type": self.tag_payload["type"],
                    "sha": self.tag_payload["object"],
                },
                "tagger": copy.deepcopy(self.tag_payload["tagger"]),
            }
            payload.update(copy.deepcopy(self.tag_overrides))
            return 200, payload
        raise AssertionError((method, path))


def make():
    store = Store()
    retained = []
    with mock.patch(
        "tools.outbound_send_guard.capability_lease.secrets.token_hex",
        return_value=CAPABILITY,
    ):
        receipt = acquire(claim(), store, retain_capability=retained.append)
    assert retained == [CAPABILITY]
    store.calls.clear()
    return store, receipt, retained[0]


class CapabilityLeaseTests(unittest.TestCase):
    def test_holder_passes_exact_live_readback(self):
        store, receipt, capability = make()
        self.assertTrue(verify_receipt(receipt))
        self.assertTrue(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )
        self.assertEqual([call[0] for call in store.calls], ["GET", "GET"])

    def test_copied_winner_public_values_do_not_prove_possession(self):
        store, receipt, _ = make()
        public_copy = copy.deepcopy(receipt)
        self.assertFalse(
            verify_possession(
                public_copy,
                claim_capability=OTHER_CAPABILITY,
                transport=store,
            )
        )
        self.assertEqual(store.calls, [])

    def test_malformed_capability_fails_before_provider(self):
        store, receipt, _ = make()
        for bad in ("f" * 40, "F" * 64, "z" * 64):
            with self.subTest(bad=bad), self.assertRaisesRegex(
                CapabilityLeaseError, "64 lowercase hex"
            ):
                verify_possession(receipt, claim_capability=bad, transport=store)
            self.assertEqual(store.calls, [])

    def test_retention_failure_precedes_all_provider_io(self):
        store = Store()

        def fail(_secret):
            raise OSError("disk full")

        with mock.patch(
            "tools.outbound_send_guard.capability_lease.secrets.token_hex",
            return_value=CAPABILITY,
        ):
            with self.assertRaisesRegex(CapabilityLeaseError, "retention failed"):
                acquire(claim(), store, retain_capability=fail)
        self.assertEqual(store.calls, [])

    def test_raw_capability_never_enters_receipt_or_provider_payload(self):
        store = Store()
        retained = []
        with mock.patch(
            "tools.outbound_send_guard.capability_lease.secrets.token_hex",
            return_value=CAPABILITY,
        ):
            receipt = acquire(claim(), store, retain_capability=retained.append)
        self.assertEqual(retained, [CAPABILITY])
        self.assertNotIn(CAPABILITY, json.dumps(receipt, sort_keys=True))
        self.assertNotIn(CAPABILITY, json.dumps(store.calls, sort_keys=True))
        self.assertEqual(
            receipt["claim_capability_sha256"], _capability_commitment(CAPABILITY)
        )

    def test_v2_namespace_is_disjoint_from_v1(self):
        _, receipt, _ = make()
        self.assertTrue(receipt["lease_ref"].startswith(REF_PREFIX))
        self.assertFalse(receipt["lease_ref"].startswith("refs/tags/outbound-lease-v1/"))
        self.assertTrue(receipt["schema"].endswith("/v2"))

    def test_duplicate_key_tag_metadata_fails_closed(self):
        store, receipt, capability = make()
        message = store.tag_payload["message"].strip()
        store.tag_overrides["message"] = message[:-1] + ',"repo":"woahwhattheheck/commons"}\n'
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )

    def test_tag_commitment_drift_fails(self):
        store, receipt, capability = make()
        metadata = json.loads(store.tag_payload["message"])
        metadata["claim_capability_sha256"] = "e" * 64
        store.tag_overrides["message"] = (
            json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )

    def test_receipt_commitment_drift_cannot_be_resealed_into_authority(self):
        store, receipt, capability = make()
        forged = copy.deepcopy(receipt)
        forged["claim_capability_sha256"] = "e" * 64
        material = dict(forged)
        material.pop("receipt_sha256")
        import hashlib

        forged["receipt_sha256"] = hashlib.sha256(
            json.dumps(
                material,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest()
        self.assertTrue(verify_receipt(forged))
        self.assertFalse(
            verify_possession(forged, claim_capability=capability, transport=store)
        )
        self.assertEqual(store.calls, [])

    def test_provider_uncertainty_and_drift_fail_closed(self):
        store, receipt, capability = make()
        store.ref_read_status = 503
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )
        self.assertEqual([call[0] for call in store.calls], ["GET"])

        store, receipt, capability = make()
        store.ref_sha = OTHER
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )
        self.assertEqual([call[0] for call in store.calls], ["GET"])

    def test_target_and_tagger_drift_fail_closed(self):
        store, receipt, capability = make()
        store.tag_overrides["object"] = {"type": "commit", "sha": OTHER}
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )

        store, receipt, capability = make()
        tagger = copy.deepcopy(store.tag_payload["tagger"])
        tagger["name"] = "forged"
        store.tag_overrides["tagger"] = tagger
        self.assertFalse(
            verify_possession(receipt, claim_capability=capability, transport=store)
        )

    def test_other_owner_hold_still_fails_live_possession(self):
        store = Store()
        store.ref_sha = OTHER
        retained = []
        with mock.patch(
            "tools.outbound_send_guard.capability_lease.secrets.token_hex",
            return_value=CAPABILITY,
        ):
            receipt = acquire(claim(), store, retain_capability=retained.append)
        self.assertFalse(receipt["lease_held_by_claimant"])
        store.calls.clear()
        self.assertFalse(
            verify_possession(receipt, claim_capability=CAPABILITY, transport=store)
        )
        self.assertEqual([call[0] for call in store.calls], ["GET"])

    def test_outcome_unknown_hold_recovers_from_later_exact_live_readback(self):
        store = Store()
        store.ref_create_status = 503
        store.ref_read_status = 503
        retained = []
        with mock.patch(
            "tools.outbound_send_guard.capability_lease.secrets.token_hex",
            return_value=CAPABILITY,
        ):
            receipt = acquire(claim(), store, retain_capability=retained.append)
        self.assertFalse(receipt["lease_held_by_claimant"])
        self.assertEqual(receipt["reason"], "READBACK_FAILED_503")
        self.assertEqual(retained, [CAPABILITY])

        store.ref_read_status = 200
        store.ref_sha = TAG
        store.calls.clear()
        self.assertTrue(
            verify_possession(receipt, claim_capability=CAPABILITY, transport=store)
        )
        self.assertEqual([call[0] for call in store.calls], ["GET", "GET"])

    def test_capability_file_is_create_exclusive_and_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lease.cap")
            _write_capability_file(path, CAPABILITY)
            with open(path, "r", encoding="ascii") as fh:
                self.assertEqual(fh.read(), CAPABILITY + "\n")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with self.assertRaisesRegex(CapabilityLeaseError, "new file"):
                _write_capability_file(path, OTHER_CAPABILITY)
            with open(path, "r", encoding="ascii") as fh:
                self.assertEqual(fh.read(), CAPABILITY + "\n")

    def test_capability_directory_sync_failure_blocks_provider(self):
        if not hasattr(os, "O_DIRECTORY"):
            self.skipTest("directory fsync gate is POSIX-only")
        store = Store()
        retained_path = None
        with tempfile.TemporaryDirectory() as tmp:
            retained_path = os.path.join(tmp, "lease.cap")
            real_fsync = os.fsync
            calls = {"count": 0}

            def fail_second(fd):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("directory sync failed")
                return real_fsync(fd)

            with mock.patch(
                "tools.outbound_send_guard.capability_lease.secrets.token_hex",
                return_value=CAPABILITY,
            ), mock.patch(
                "tools.outbound_send_guard.capability_lease.os.fsync",
                side_effect=fail_second,
            ):
                with self.assertRaisesRegex(CapabilityLeaseError, "retention failed"):
                    acquire(
                        claim(),
                        store,
                        retain_capability=lambda secret: _write_capability_file(
                            retained_path, secret
                        ),
                    )
            self.assertFalse(os.path.exists(retained_path))
        self.assertEqual(store.calls, [])

    def test_invalid_claim_fails_before_capability_retention_or_provider(self):
        store = Store()
        retained = []
        with self.assertRaisesRegex(CapabilityLeaseError, "64 lowercase hex"):
            acquire(
                claim(preflight_sha256="b" * 40),
                store,
                retain_capability=retained.append,
            )
        self.assertEqual(retained, [])
        self.assertEqual(store.calls, [])


if __name__ == "__main__":
    unittest.main()
