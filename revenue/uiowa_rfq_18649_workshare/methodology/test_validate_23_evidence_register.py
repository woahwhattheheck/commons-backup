#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTER = HERE / "23-synthetic-evidence-register.csv"
VALIDATOR_PATH = HERE / "validate_23_evidence_register.py"

spec = importlib.util.spec_from_file_location("uiowa23_validator", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class EvidenceRegisterTests(unittest.TestCase):
    def test_published_register_passes(self):
        self.assertEqual(validator.validate(REGISTER), [])

    def _mutated_copy(self, mutate):
        with REGISTER.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        mutate(rows)
        tmp = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", suffix=".csv", delete=False
        )
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return Path(tmp.name)

    def test_missing_evidence_cannot_be_high_confidence(self):
        path = self._mutated_copy(lambda rows: rows[-1].update(confidence="HIGH"))
        errors = validator.validate(path)
        self.assertTrue(any("NO_EVIDENCE_OBSERVED must use NOT_EVIDENCED" in e for e in errors))

    def test_conflict_requires_unresolved_and_group(self):
        def mutate(rows):
            rows[3]["confidence"] = "MODERATE"
            rows[3]["conflict_group"] = ""
        path = self._mutated_copy(mutate)
        errors = validator.validate(path)
        self.assertTrue(any("must be UNRESOLVED" in e for e in errors))
        self.assertTrue(any("requires conflict_group" in e for e in errors))

    def test_absence_requires_bounded_universe(self):
        path = self._mutated_copy(lambda rows: rows[5].update(universe_definition=""))
        errors = validator.validate(path)
        self.assertTrue(any("requires universe_definition" in e for e in errors))

    def test_stale_evidence_cannot_be_high(self):
        path = self._mutated_copy(lambda rows: rows[2].update(confidence="HIGH"))
        errors = validator.validate(path)
        self.assertTrue(any("stale evidence cannot be HIGH" in e for e in errors))

    def test_custodian_or_owner_cannot_be_blank(self):
        path = self._mutated_copy(lambda rows: rows[0].update(custodian_or_owner=""))
        errors = validator.validate(path)
        self.assertTrue(any("custodian_or_owner must not be blank" in e for e in errors))

    def test_content_digest_cannot_be_blank(self):
        path = self._mutated_copy(lambda rows: rows[0].update(content_digest=""))
        errors = validator.validate(path)
        self.assertTrue(any("content_digest must not be blank" in e for e in errors))

    def test_content_digest_rejects_unverified_hash_shape(self):
        path = self._mutated_copy(lambda rows: rows[0].update(content_digest="sha256:not-a-digest"))
        errors = validator.validate(path)
        self.assertTrue(any("content_digest must be sha256:<64 hex>" in e for e in errors))

    def test_content_digest_accepts_real_sha256_shape(self):
        digest = "sha256:" + "a" * 64
        path = self._mutated_copy(lambda rows: rows[0].update(content_digest=digest))
        self.assertEqual(validator.validate(path), [])


if __name__ == "__main__":
    unittest.main()
