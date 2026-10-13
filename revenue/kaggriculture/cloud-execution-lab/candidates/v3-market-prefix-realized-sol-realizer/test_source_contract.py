# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from source_contract import load_json, verify_source_contract

HERE = Path(__file__).resolve().parent
README_DRIFT = "runtime/variants/v1/reference/decision/README.md"


class SourceContractTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text('{"x":1,"x":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_json(path)

    def test_source_contract_declares_action_excluding_state_phase(self):
        data = load_json(HERE / "SOURCE.json")
        self.assertEqual(
            data["invariants"]["state_receipt_phase"],
            "post interpreter with submitted actions excluded",
        )
        self.assertEqual(data["invariants"]["expected_candidate_actions"], 719)

    def test_live_source_contract_passes_with_named_readme_drift(self):
        receipt = verify_source_contract()
        self.assertEqual(len(receipt["frozen_files"]), 11)
        self.assertEqual(receipt["inherited_frozen_docs_drift"], [README_DRIFT])
        python_members = [
            relative
            for relative in receipt["frozen_files"]
            if relative.endswith(".py")
        ]
        self.assertGreaterEqual(len(python_members), 5)
        for relative in python_members:
            self.assertNotIn(
                "inherited_docs_drift", receipt["frozen_files"][relative]
            )
        self.assertTrue(
            receipt["frozen_files"][README_DRIFT]["inherited_docs_drift"]
        )

    def test_unrecorded_frozen_drift_is_still_rejected(self):
        contract = load_json(HERE / "SOURCE.json")
        contract.pop("inherited_frozen_docs_drift")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SOURCE.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frozen V1 drift at " + README_DRIFT):
                verify_source_contract(path)

    def test_python_inherited_drift_is_rejected(self):
        contract = load_json(HERE / "SOURCE.json")
        contract["inherited_frozen_docs_drift"] = {
            "runtime/variants/v1/candidate.py": {
                "kind": "illegal",
                "freeze_sha256": "0" * 64,
                "freeze_bytes": 1,
                "observed_sha256": "0" * 64,
                "observed_bytes": 1,
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SOURCE.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Markdown"):
                verify_source_contract(path)


if __name__ == "__main__":
    unittest.main()
