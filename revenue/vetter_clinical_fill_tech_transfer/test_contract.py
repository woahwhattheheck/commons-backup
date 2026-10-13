from __future__ import annotations

import json
import unittest
from pathlib import Path

import engine


ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "contract.json"
README = ROOT / "README.md"
RECOVERY = ROOT / "RECOVERY.md"


class TrustContractTests(unittest.TestCase):
    def _contract(self) -> dict[str, object]:
        return json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_truthfully_excludes_same_process_monkeypatch_resistance(self) -> None:
        contract = self._contract()
        self.assertEqual(
            contract["schema"],
            "vetter-clinical-fill-tech-transfer.contract/v4",
        )
        self.assertFalse(contract["same_process_python_mutation_resistant"])
        self.assertFalse(contract["same_process_private_helper_mutation_in_scope"])
        self.assertEqual(
            contract["recommended_operational_boundary"],
            "controlled_fresh_interpreter_cli",
        )
        self.assertIn(
            "python_runtime_and_private_module_state",
            contract["trusted_host_requirements"],
        )
        self.assertFalse(contract["truth_contract"]["runtime_integrity_is_attested_by_sha_receipts"])

    def test_reviewed_mutable_globals_fact_is_part_of_the_executable_contract(self) -> None:
        cells = dict(
            zip(
                engine.compile_transfer.__code__.co_freevars,
                (cell.cell_contents for cell in engine.compile_transfer.__closure__ or ()),
            )
        )
        raw_compile = cells.get("raw_compile")
        self.assertIsNotNone(raw_compile)
        self.assertIsInstance(raw_compile.__globals__, dict)
        contract = self._contract()
        self.assertFalse(contract["same_process_python_mutation_resistant"])
        self.assertTrue(contract["truth_contract"]["same_process_arbitrary_monkeypatching_is_excluded"])

    def test_docs_bind_current_authority_to_the_trusted_runtime_boundary(self) -> None:
        readme = README.read_text(encoding="utf-8")
        recovery = RECOVERY.read_text(encoding="utf-8")
        for text in (readme, recovery):
            self.assertIn("controlled fresh interpreter", text.lower())
            self.assertIn("same-process", text.lower())
            self.assertIn("trusted", text.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
