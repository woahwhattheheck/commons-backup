# SPDX-License-Identifier: Apache-2.0
import copy
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pq.pinning import canonical_json, sha256_bytes
from pq.receipts import ReceiptStore, receipt_digest


def _pin_manifest():
    inputs = {
        "candidate_artifact": {"sha256": "a" * 64, "bytes": 10},
        "candidate_games": {"sha256": "b" * 64, "bytes": 20},
        "policy": {"sha256": "c" * 64, "bytes": 30},
    }
    return {
        "pin_id": "pq-20260910-deadbeefcafe",
        "input_digest": sha256_bytes(
            canonical_json({n: r["sha256"] for n, r in inputs.items()})
        ),
        "inputs": inputs,
    }


def _receipt(store, **overrides):
    kwargs = dict(
        submission_id="pq-20260910-deadbeefcafe",
        attempt_n=1,
        policy_version="promotion-policy/v1",
        pin_manifest=_pin_manifest(),
        predecessors={
            "frozen_control": {
                "name": "frozen-control",
                "artifact_sha256": "d" * 64,
                "games_sha256": "e" * 64,
                "contract_sha256": "f" * 64,
                "evidence_sha256": "0" * 64,
                "panel_id": "pq-20260910-deadbeefcafe-vs-frozen_control",
            }
        },
        comparisons=[
            {
                "slot": "frozen_control",
                "verdict": "PROMOTE",
                "exit_code": 0,
                "report_sha256": "1" * 64,
            }
        ],
        verdict="PROMOTE",
        timings={"started_at": "t", "finished_at": "t", "duration_ms": 5},
        prev_receipt_digest=None,
    )
    kwargs.update(overrides)
    return store.build(**kwargs)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.td.name))

    def tearDown(self):
        self.td.cleanup()

    def test_build_and_verify_roundtrip(self):
        receipt = _receipt(self.store)
        ok, reason = self.store.verify(receipt)
        self.assertTrue(ok, reason)
        self.assertEqual(receipt["receipt_type"], "titan-promotion-queue-receipt/v1")
        self.assertEqual(receipt["policy_version"], "promotion-policy/v1")

    def test_receipt_covers_inputs_results_and_policy_version(self):
        receipt = _receipt(self.store)
        digest_before = receipt["integrity"]["digest"]
        # the digest must change when any covered field changes
        for mutate in (
            lambda r: r["queue_pin"]["inputs"].__setitem__(
                "candidate_games", {"sha256": "9" * 64, "bytes": 20}
            ),
            lambda r: r["comparisons"][0].__setitem__("verdict", "REJECT"),
            lambda r: r.__setitem__("policy_version", "promotion-policy/v2"),
            lambda r: r["timings"].__setitem__("duration_ms", 999),
        ):
            tampered = copy.deepcopy(receipt)
            mutate(tampered)
            self.assertNotEqual(receipt_digest(tampered), digest_before)
            ok, _ = self.store.verify(tampered)
            self.assertFalse(ok)

    def test_tampered_receipt_fails_verify(self):
        receipt = _receipt(self.store)
        receipt["verdict"] = "REJECT"
        ok, reason = self.store.verify(receipt)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_digest_is_deterministic(self):
        first = _receipt(self.store)
        second = _receipt(self.store)
        self.assertEqual(first["integrity"]["digest"], second["integrity"]["digest"])

    def test_attempt_chain_links_prev_digest(self):
        first = _receipt(self.store)
        second = _receipt(
            self.store,
            attempt_n=2,
            prev_receipt_digest=first["integrity"]["digest"],
        )
        self.assertEqual(
            second["integrity"]["prev_receipt_digest"], first["integrity"]["digest"]
        )
        ok, _ = self.store.verify(second)
        self.assertTrue(ok)

    def test_save_and_load_roundtrip(self):
        receipt = _receipt(self.store)
        path = self.store.save(receipt)
        loaded = self.store.load(receipt["receipt_id"])
        self.assertEqual(loaded, receipt)
        self.assertTrue(path.is_file())

    def test_missing_digest_fails_verify(self):
        receipt = _receipt(self.store)
        del receipt["integrity"]["digest"]
        ok, _ = self.store.verify(receipt)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
