from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from revenue.agent_capability_constraint_registry.core import (
    INPUT_SCHEMA,
    RegistryError,
    compile_registry,
    load_json_bytes,
    normalize_input,
    verify_compiled,
    write_compiled,
)

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture_12_agents.json"


def fixture() -> dict:
    return load_json_bytes(FIXTURE.read_bytes(), "fixture")


class RegistryTests(unittest.TestCase):
    def test_acceptance_counts(self):
        compiled = compile_registry(fixture())
        self.assertEqual(compiled.result["counts"], {"READY": 5, "TOOLING_NEEDED": 3, "OWNER_DECISION": 2, "HOLD": 2})

    def test_deterministic_all_outputs(self):
        a = compile_registry(fixture())
        b = compile_registry(fixture())
        self.assertEqual(a.result_bytes, b.result_bytes)
        self.assertEqual(a.markdown_bytes, b.markdown_bytes)
        self.assertEqual(a.receipt_bytes, b.receipt_bytes)

    def test_input_order_does_not_change_outputs(self):
        source = fixture()
        source["records"].reverse()
        a = compile_registry(fixture())
        b = compile_registry(source)
        self.assertEqual(a.result_bytes, b.result_bytes)
        self.assertEqual(a.markdown_bytes, b.markdown_bytes)
        self.assertEqual(a.receipt_bytes, b.receipt_bytes)

    def test_verifier_accepts_exact_outputs(self):
        source = fixture()
        compiled = compile_registry(source)
        proof = verify_compiled(source, compiled.result_bytes, compiled.markdown_bytes, compiled.receipt_bytes)
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["counts"]["READY"], 5)

    def test_tampered_result_rejected(self):
        source = fixture()
        compiled = compile_registry(source)
        tampered = compiled.result_bytes.replace(b'"READY":5', b'"READY":4', 1)
        with self.assertRaises(RegistryError):
            verify_compiled(source, tampered, compiled.markdown_bytes, compiled.receipt_bytes)

    def test_tampered_markdown_rejected(self):
        source = fixture()
        compiled = compile_registry(source)
        with self.assertRaises(RegistryError):
            verify_compiled(source, compiled.result_bytes, compiled.markdown_bytes + b"tamper\n", compiled.receipt_bytes)

    def test_tampered_receipt_rejected(self):
        source = fixture()
        compiled = compile_registry(source)
        tampered = compiled.receipt_bytes.replace(b'OBSERVATIONAL_ONLY', b'OBSERVATIONAL_ONLy')
        with self.assertRaises(RegistryError):
            verify_compiled(source, compiled.result_bytes, compiled.markdown_bytes, tampered)

    def test_authority_bits_all_false(self):
        authority = compile_registry(fixture()).result["authority"]
        self.assertTrue(authority)
        self.assertTrue(all(value is False for value in authority.values()))

    def test_execution_request_forces_hold(self):
        source = fixture()
        source["records"][0]["execution_requested"] = True
        result = compile_registry(source).result
        row = next(item for item in result["records"] if item["agent_id"] == "agent-ready-1")
        self.assertEqual(row["status"], "HOLD")
        self.assertIn("EXECUTION_REQUESTED_OUTSIDE_REGISTRY_AUTHORITY", row["status_reasons"])

    def test_missing_tool_is_tooling_needed(self):
        result = compile_registry(fixture()).result
        row = next(item for item in result["records"] if item["agent_id"] == "agent-tool-1")
        self.assertEqual(row["status"], "TOOLING_NEEDED")
        self.assertEqual(row["missing_tools"], ["baggage-read"])

    def test_owner_pending_beats_tooling_needed(self):
        source = fixture()
        source["records"][8]["required_tools"].append("extra-read")
        result = compile_registry(source).result
        row = next(item for item in result["records"] if item["agent_id"] == "agent-owner-1")
        self.assertEqual(row["status"], "OWNER_DECISION")

    def test_blocker_beats_owner_pending(self):
        source = fixture()
        rec = source["records"][8]
        rec["blocking_reasons"].append("legal-hold")
        result = compile_registry(source).result
        row = next(item for item in result["records"] if item["agent_id"] == "agent-owner-1")
        self.assertEqual(row["status"], "HOLD")

    def test_duplicate_json_key_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        with self.assertRaises(RegistryError):
            load_json_bytes(raw)

    def test_float_rejected(self):
        with self.assertRaises(RegistryError):
            load_json_bytes(b'{"x":1.5}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(RegistryError):
            load_json_bytes(b'{"x":NaN}')

    def test_bom_rejected(self):
        with self.assertRaises(RegistryError):
            load_json_bytes(b'\xef\xbb\xbf{}')

    def test_bool_as_revision_rejected(self):
        source = fixture()
        source["records"][0]["revision"] = True
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_bool_as_minutes_rejected(self):
        source = fixture()
        source["records"][1]["declared_constraints"][0]["estimated_fix_minutes"] = False
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_changed_duplicate_agent_revision_rejected(self):
        source = fixture()
        dup = deepcopy(source["records"][0])
        dup["provider"] = "different-provider"
        source["records"].append(dup)
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_exact_duplicate_agent_revision_rejected(self):
        source = fixture()
        source["records"].append(deepcopy(source["records"][0]))
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_missing_capability_evidence_rejected(self):
        source = fixture()
        del source["records"][0]["measured_capabilities"][0]["evidence_sha256"]
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_incomplete_constraint_rejected(self):
        source = fixture()
        del source["records"][1]["declared_constraints"][0]["source_sha256"]
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_invalid_owner_verdict_rejected(self):
        source = fixture()
        source["records"][0]["owner_decision"] = "MAYBE"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_invalid_constraint_verdict_rejected(self):
        source = fixture()
        source["records"][1]["declared_constraints"][0]["owner_verdict"] = "MAYBE"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_invalid_capability_condition_rejected(self):
        source = fixture()
        source["records"][0]["measured_capabilities"][0]["condition"] = "UNKNOWN"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_invalid_hash_rejected(self):
        source = fixture()
        source["records"][0]["measured_capabilities"][0]["evidence_sha256"] = "ABC"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_invalid_timestamp_rejected(self):
        source = fixture()
        source["records"][0]["measured_capabilities"][0]["measured_at"] = "2026-09-13"
        with self.assertRaises(RegistryError):
            compile_registry(source)


    def test_unknown_record_field_rejected(self):
        source = fixture()
        source["records"][0]["surprise"] = "value"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_unknown_top_field_rejected(self):
        source = fixture()
        source["surprise"] = "value"
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_duplicate_capability_name_rejected(self):
        source = fixture()
        source["records"][0]["measured_capabilities"].append(deepcopy(source["records"][0]["measured_capabilities"][0]))
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_duplicate_constraint_name_rejected(self):
        source = fixture()
        source["records"][1]["declared_constraints"].append(deepcopy(source["records"][1]["declared_constraints"][0]))
        with self.assertRaises(RegistryError):
            compile_registry(source)

    def test_write_compiled_fails_if_destination_exists(self):
        source = fixture()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out"
            dest.mkdir()
            with self.assertRaises(RegistryError):
                write_compiled(source, dest)

    def test_write_compiled_and_verify_from_disk(self):
        source = fixture()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out"
            write_compiled(source, dest)
            proof = verify_compiled(source, (dest / "registry.json").read_bytes(), (dest / "registry.md").read_bytes(), (dest / "receipt.json").read_bytes())
            self.assertTrue(proof["verified"])

    def test_normalize_schema_constant(self):
        normalized = normalize_input(fixture())
        self.assertEqual(normalized["schema"], INPUT_SCHEMA)

    def test_markdown_has_no_execution_authority(self):
        markdown = compile_registry(fixture()).markdown_bytes.decode("utf-8")
        self.assertIn("no execution, deployment, access, spend, messaging, or model-selection authority", markdown)
        self.assertIn("It is **not** permission to run, deploy, call a tool", markdown)


if __name__ == "__main__":
    unittest.main()
