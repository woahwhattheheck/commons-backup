from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from .acceptance import AS_OF, build_fixture, run_acceptance
from .proof import ProofError, build_proof, loads_strict, read_json_file, validate_spec, verify_receipt


def sha(seed: str) -> str:
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def spec(**overrides):
    value = {
        "schema": "reconciliation-proof/v1",
        "profile": "unit",
        "required_fields": ["name", "amount"],
        "ignored_fields": ["note"],
        "require_evidence_identity": True,
        "require_version_identity": True,
        "max_records_per_side": 50,
    }
    value.update(overrides)
    return value


def rec(record_id="r1", *, version=1, observed="2026-09-13T09:00:00Z", amount=5, evidence=None, note="x"):
    return {
        "record_id": record_id,
        "version": version,
        "observed_at": observed,
        "fields": {"name": record_id, "amount": amount, "note": note},
        "evidence_sha256": evidence or sha(f"e-{record_id}"),
    }


class ReconciliationProofTests(unittest.TestCase):
    def build(self, left=None, right=None, **kwargs):
        left = [rec()] if left is None else left
        right = [deepcopy(left[0])] if right is None else right
        return build_proof(spec(**kwargs), left, right, as_of=AS_OF)

    def test_empty_inputs_hold(self):
        receipt = self.build([], [])
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["counts"]["record_keys"], 0)
        self.assertTrue(verify_receipt(receipt))

    def test_clean_match_is_human_review_ready(self):
        receipt = self.build()
        self.assertEqual(receipt["status"], "RECONCILED_FOR_HUMAN_REVIEW")
        self.assertEqual(receipt["counts"]["matched"], 1)
        self.assertTrue(verify_receipt(receipt))

    def test_ignored_field_can_differ(self):
        left = [rec(note="left")]
        right = [rec(note="right")]
        receipt = self.build(left, right)
        self.assertEqual(receipt["status"], "RECONCILED_FOR_HUMAN_REVIEW")

    def test_field_mismatch_holds(self):
        receipt = self.build([rec(amount=5)], [rec(amount=6)])
        self.assertEqual(receipt["status"], "HOLD")
        self.assertIn("FIELD_MISMATCH", receipt["outcomes"][0]["reasons"])

    def test_missing_left_and_right_hold(self):
        receipt = self.build([rec("left")], [rec("right")])
        reasons = [set(row["reasons"]) for row in receipt["outcomes"]]
        self.assertIn({"MISSING_RIGHT"}, reasons)
        self.assertIn({"MISSING_LEFT"}, reasons)

    def test_version_mismatch_holds(self):
        receipt = self.build([rec(version=1)], [rec(version=2)])
        self.assertIn("VERSION_MISMATCH", receipt["outcomes"][0]["reasons"])

    def test_evidence_mismatch_holds(self):
        receipt = self.build([rec(evidence=sha("a"))], [rec(evidence=sha("b"))])
        self.assertIn("EVIDENCE_MISMATCH", receipt["outcomes"][0]["reasons"])

    def test_exact_replay_collapses(self):
        row = rec()
        receipt = self.build([row, deepcopy(row)], [deepcopy(row), deepcopy(row)])
        self.assertEqual(receipt["counts"]["left_exact_replays"], 1)
        self.assertEqual(receipt["counts"]["right_exact_replays"], 1)
        self.assertEqual(receipt["counts"]["record_keys"], 1)

    def test_changed_same_version_conflicts(self):
        a, b = rec(), rec(amount=9)
        receipt = self.build([a, b], [rec()])
        self.assertIn("LEFT_VERSION_CONFLICT", receipt["outcomes"][0]["reasons"])
        self.assertEqual(receipt["counts"]["conflicted"], 1)

    def test_version_time_regression_conflicts(self):
        left = [rec(version=1, observed="2026-09-13T09:00:00Z"), rec(version=2, observed="2026-09-13T08:59:59Z")]
        right = [rec(version=2, observed="2026-09-13T08:59:59Z")]
        receipt = self.build(left, right)
        self.assertIn("LEFT_VERSION_TIME_REGRESSION", receipt["outcomes"][0]["reasons"])

    def test_future_evidence_rejected(self):
        with self.assertRaisesRegex(ProofError, "future evidence"):
            self.build([rec(observed="2026-09-13T09:16:00Z")], [rec()])

    def test_noncanonical_timestamp_rejected(self):
        with self.assertRaises(ProofError):
            self.build([rec(observed="2026-09-13T09:00:00+00:00")], [rec()])

    def test_required_field_missing_holds(self):
        left = rec(); del left["fields"]["amount"]
        receipt = self.build([left], [rec()])
        self.assertIn("REQUIRED_FIELD_MISSING", receipt["outcomes"][0]["reasons"])

    def test_spec_unknown_field_rejected(self):
        bad = spec(); bad["surprise"] = True
        with self.assertRaises(ProofError): validate_spec(bad)

    def test_required_ignored_overlap_rejected(self):
        with self.assertRaises(ProofError): validate_spec(spec(ignored_fields=["amount"]))

    def test_boolean_max_records_rejected(self):
        with self.assertRaises(ProofError): validate_spec(spec(max_records_per_side=True))

    def test_input_limit_rejected(self):
        with self.assertRaisesRegex(ProofError, "exceeds max_records"):
            build_proof(spec(max_records_per_side=1), [rec("a"), rec("b")], [rec("a")], as_of=AS_OF)

    def test_record_unknown_field_rejected(self):
        row = rec(); row["extra"] = 1
        with self.assertRaises(ProofError): self.build([row], [rec()])

    def test_nonfinite_nested_value_rejected(self):
        row = rec(); row["fields"]["amount"] = float("nan")
        with self.assertRaises(ProofError): self.build([row], [rec()])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ProofError, "duplicate JSON key"):
            loads_strict('{"a":1,"a":2}')

    def test_nonfinite_json_token_rejected(self):
        with self.assertRaises(ProofError): loads_strict('{"x":NaN}')

    def test_receipt_checksum_tamper_rejected(self):
        receipt = self.build(); receipt["status"] = "HOLD"
        with self.assertRaises(ProofError): verify_receipt(receipt)

    def test_receipt_authority_tamper_rejected(self):
        receipt = self.build(); receipt["authority"]["payment"] = True
        unsigned = deepcopy(receipt); unsigned.pop("receipt_sha256")
        from .proof import _sha
        receipt["receipt_sha256"] = _sha(unsigned)
        with self.assertRaisesRegex(ProofError, "cannot grant external authority"):
            verify_receipt(receipt)

    def test_receipt_duplicate_record_key_rejected(self):
        receipt = self.build([rec("a"), rec("b")], [rec("a"), rec("b")])
        receipt["outcomes"][1]["record_key_sha256"] = receipt["outcomes"][0]["record_key_sha256"]
        from .proof import _sha
        unsigned = deepcopy(receipt); unsigned.pop("receipt_sha256")
        receipt["receipt_sha256"] = _sha(unsigned)
        with self.assertRaisesRegex(ProofError, "duplicate record key"):
            verify_receipt(receipt)

    def test_manifest_binds_historical_versions(self):
        a = self.build([rec(version=1), rec(version=2)], [rec(version=2)])
        b = self.build([rec(version=2)], [rec(version=2)])
        self.assertNotEqual(a["input_manifest_sha256"], b["input_manifest_sha256"])

    def test_manifest_binds_exact_replay_count(self):
        row = rec()
        a = self.build([row], [deepcopy(row)])
        b = self.build([row, deepcopy(row)], [deepcopy(row)])
        self.assertNotEqual(a["input_manifest_sha256"], b["input_manifest_sha256"])

    def test_manifest_binds_conflicting_variant(self):
        base = rec(); conflict = rec(amount=77)
        a = self.build([base, conflict], [rec()])
        other = rec(amount=88)
        b = self.build([base, other], [rec()])
        self.assertNotEqual(a["input_manifest_sha256"], b["input_manifest_sha256"])

    def test_record_ids_not_emitted_in_receipt(self):
        receipt = self.build([rec("private-id-123")], [rec("private-id-123")])
        self.assertNotIn("private-id-123", json.dumps(receipt, sort_keys=True))

    def test_deterministic_under_input_order(self):
        left = [rec("a"), rec("b"), rec("c")]
        right = deepcopy(left)
        a = self.build(left, right)
        b = self.build(list(reversed(left)), list(reversed(right)))
        self.assertEqual(a, b)

    def test_read_json_refuses_symlink(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data.json"; target.write_text("{}")
            link = Path(tmp) / "link.json"; os.symlink(target, link)
            with self.assertRaisesRegex(ProofError, "symlink"):
                read_json_file(link)

    def test_read_json_refuses_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.json"; p.write_text('"12345"')
            with self.assertRaisesRegex(ProofError, "exceeds"):
                read_json_file(p, max_bytes=4)

    def test_read_json_handles_short_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.json"; p.write_text('{"ok":true}')
            real_read = os.read
            def short_read(fd, size):
                return real_read(fd, min(size, 2))
            with mock.patch("os.read", side_effect=short_read):
                self.assertEqual(read_json_file(p), {"ok": True})

    def test_read_json_refuses_stat_open_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.json"; p.write_text('{"old":true}')
            replacement = Path(tmp) / "replacement.json"
            replacement.write_text('{"new":true}')
            real_open = os.open
            switched = False
            def racing_open(path, flags, *args, **kwargs):
                nonlocal switched
                if not switched and Path(path) == p:
                    switched = True
                    os.replace(replacement, p)
                return real_open(path, flags, *args, **kwargs)
            with mock.patch("os.open", side_effect=racing_open):
                with self.assertRaisesRegex(ProofError, "changed between stat and open"):
                    read_json_file(p)

    def test_acceptance_fixture(self):
        result = run_acceptance()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["counts"]["record_keys"], 300)
        self.assertEqual(result["reason_distribution"]["LEFT_VERSION_CONFLICT"], 10)


if __name__ == "__main__":
    unittest.main()
