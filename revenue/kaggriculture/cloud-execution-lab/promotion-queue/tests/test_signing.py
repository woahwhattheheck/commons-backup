# SPDX-License-Identifier: Apache-2.0
"""Tests for key-based receipt signing and run-input pinning gaps.

- Receipts seal with a tamper-evident digest by default; with a signing key
  they additionally carry an HMAC-SHA256 signature the promotion gate can
  verify for attribution.
- The predecessor config file itself is pinned at run time (config_sha256
  lands in the receipt extra), and extract_grid enforces the full
  identical-seeds-both-seats grid.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pq.pinning import PinStore
from pq.receipts import ReceiptStore
from pq.runner import extract_grid, RunError
from pq.signing import (
    SigningError,
    load_key,
    sign_receipt,
    verify_signature,
)


def _receipt(store, key=None):
    return store.build(
        submission_id="pq-20260910-test",
        attempt_n=1,
        policy_version="promotion-policy/v1",
        pin_manifest={
            "pin_id": "pq-20260910-test",
            "input_digest": "0" * 64,
            "inputs": {
                "candidate_artifact": {"sha256": "a" * 64, "bytes": 10},
                "candidate_games": {"sha256": "b" * 64, "bytes": 20},
                "policy": {"sha256": "c" * 64, "bytes": 30},
            },
        },
        predecessors={},
        comparisons=[{"slot": "frozen_control", "verdict": "PROMOTE"}],
        verdict="PROMOTE",
        timings={"duration_ms": 5},
        prev_receipt_digest=None,
        extra={"config_sha256": "d" * 64},
        signing_key=key,
    )


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.store = ReceiptStore(Path(self.td.name))

    def tearDown(self):
        self.td.cleanup()

    def _keyfile(self, data: bytes) -> Path:
        path = Path(self.td.name) / "key.bin"
        path.write_bytes(data)
        return path

    def test_sign_verify_roundtrip(self):
        key = load_key(self._keyfile(b"k" * 32))
        receipt = _receipt(self.store, key=key)
        self.assertIn("signature", receipt["integrity"])
        self.assertEqual(
            receipt["integrity"]["algorithm"], "hmac-sha256-v1"
        )
        ok, reason = self.store.verify(receipt, signing_key=key)
        self.assertTrue(ok, reason)

    def test_unsigned_receipt_verifies_digest_only(self):
        receipt = _receipt(self.store)
        self.assertNotIn("signature", receipt["integrity"])
        ok, reason = self.store.verify(receipt)
        self.assertTrue(ok, reason)

    def test_tamper_invalidates_signature_and_digest(self):
        key = load_key(self._keyfile(b"k" * 32))
        receipt = _receipt(self.store, key=key)
        tampered = copy.deepcopy(receipt)
        tampered["verdict"] = "REJECT"
        ok, _ = self.store.verify(tampered)
        self.assertFalse(ok)
        ok, _ = self.store.verify(tampered, signing_key=key)
        self.assertFalse(ok)

    def test_wrong_key_rejected(self):
        receipt = _receipt(self.store, key=load_key(self._keyfile(b"k" * 32)))
        other = load_key(self._keyfile(b"z" * 32))
        ok, reason = verify_signature(receipt, other)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_missing_signature_fails_closed(self):
        receipt = _receipt(self.store)  # unsigned
        ok, reason = verify_signature(receipt, load_key(self._keyfile(b"k" * 32)))
        self.assertFalse(ok)
        self.assertIn("no integrity.signature", reason)

    def test_load_key_rejects_missing_and_short(self):
        with self.assertRaises(SigningError):
            load_key(Path(self.td.name) / "nope.bin")
        with self.assertRaises(SigningError):
            load_key(self._keyfile(b"short"))
        with self.assertRaises(SigningError):
            sign_receipt(_receipt(self.store), b"")

    def test_signature_is_deterministic(self):
        key = load_key(self._keyfile(b"k" * 32))
        first = _receipt(self.store, key=key)
        # same body bytes -> same signature (created_at excluded by rebuild)
        body = copy.deepcopy(first)
        self.assertEqual(
            sign_receipt(body, key), first["integrity"]["signature"]
        )


class ConfigPinningTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.pins = PinStore(Path(self.td.name) / "pin-store")

    def tearDown(self):
        self.td.cleanup()

    def test_config_file_pinned_and_verifiable(self):
        cfg = Path(self.td.name) / "predecessors.json"
        cfg.write_text(json.dumps({"schema_version": 1}))
        record = self.pins.put_blob(cfg)
        self.assertEqual(len(record["sha256"]), 64)
        self.assertTrue(self.pins.verify_blob(record["sha256"]))
        # tamper with the stored blob -> detected
        blob = self.pins.blob_path(record["sha256"])
        blob.write_bytes(b"tampered")
        self.assertFalse(self.pins.verify_blob(record["sha256"]))

    def test_config_sha256_recorded_in_receipt_extra(self):
        cfg = Path(self.td.name) / "predecessors.json"
        cfg.write_text(json.dumps({"schema_version": 1}))
        record = self.pins.put_blob(cfg)
        store = ReceiptStore(Path(self.td.name))
        receipt = _receipt(store)
        self.assertEqual(receipt["extra"]["config_sha256"], "d" * 64)
        # real wiring: the sha that lands in extra is the pinned blob's sha
        self.assertEqual(
            self.pins.blob_path(record["sha256"]).read_bytes(),
            cfg.read_bytes(),
        )


def _games_panel(path: Path, seeds, opponents, seats):
    with open(path, "w", encoding="utf-8") as handle:
        for seed in seeds:
            for opp in opponents:
                for seat in seats:
                    handle.write(
                        json.dumps(
                            {
                                "seed": seed,
                                "opponent": opp,
                                "candidate_seat": seat,
                            }
                        )
                        + "\n"
                    )


class GridEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.td.cleanup()

    def _panel(self, name, seeds, opponents, seats):
        path = Path(self.td.name) / name
        _games_panel(path, seeds, opponents, seats)
        return path

    def test_full_grid_accepted(self):
        grid = extract_grid(
            self._panel("full.jsonl", [1, 2], ["opp-a"], [0, 1])
        )
        self.assertEqual(grid["expected_cells"], 4)
        self.assertEqual(grid["seats"], [0, 1])

    def test_single_seat_panel_rejected(self):
        with self.assertRaises(RunError):
            extract_grid(self._panel("one-seat.jsonl", [1, 2], ["opp-a"], [0]))

    def test_row_count_drift_rejected(self):
        path = Path(self.td.name) / "drift.jsonl"
        _games_panel(path, [1, 2], ["opp-a"], [0, 1])
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"seed": 1, "opponent": "opp-a", "candidate_seat": 0}
                )
                + "\n"
            )
        with self.assertRaises(RunError):
            extract_grid(path)

    def test_non_integer_seed_rejected(self):
        path = Path(self.td.name) / "bad.jsonl"
        path.write_text(
            json.dumps({"seed": "x", "opponent": "o", "candidate_seat": 0}) + "\n"
        )
        with self.assertRaises(RunError):
            extract_grid(path)


if __name__ == "__main__":
    unittest.main()
