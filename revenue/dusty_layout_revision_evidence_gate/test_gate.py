from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dusty_gate", HERE / "gate.py")
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)
fspec = importlib.util.spec_from_file_location("dusty_fixture", HERE / "acceptance_fixture.py")
fixture = importlib.util.module_from_spec(fspec)
assert fspec.loader is not None
fspec.loader.exec_module(fixture)


class DustyGateTests(unittest.TestCase):
    def test_acceptance_corpus_exact_counts_and_reasons(self):
        payload = fixture.build_fixture()
        receipt = gate.evaluate(payload)
        self.assertEqual(receipt["jobs_total"], 120)
        self.assertEqual(receipt["clean_count"], 96)
        self.assertEqual(receipt["exception_count"], 24)
        self.assertEqual(len(receipt["clean_packets"]), 96)
        self.assertEqual(len(receipt["exceptions"]), 24)
        self.assertEqual(len({item["job_id"] for item in receipt["exceptions"]}), 24)
        self.assertEqual(receipt["control_commands"], [])
        self.assertEqual(set(receipt["reason_counts"]), set(gate.REASONS))
        self.assertTrue(all(receipt["reason_counts"][reason] == 3 for reason in gate.REASONS))
        self.assertEqual(len(receipt["receipt_sha256"]), 64)

    def test_replay_is_byte_identical(self):
        payload = fixture.build_fixture()
        a = gate.evaluate(copy.deepcopy(payload))
        b = gate.evaluate(copy.deepcopy(payload))
        self.assertEqual(json.dumps(a, sort_keys=True, separators=(",", ":")), json.dumps(b, sort_keys=True, separators=(",", ":")))

    def test_uppercase_hash_is_rejected_not_normalized(self):
        payload = {"schema_version": 1, "jobs": [fixture.clean_job(1)]}
        payload["jobs"][0]["prejob"]["design"]["sha256"] = payload["jobs"][0]["prejob"]["design"]["sha256"].upper()
        with self.assertRaises(gate.GateInputError):
            gate.evaluate(payload)

    def test_valid_alternate_hash_emits_exact_reason(self):
        job = fixture.clean_job(1)
        job["postjob"]["final_report"]["design_sha256"] = fixture.h("different-design")
        receipt = gate.evaluate({"schema_version": 1, "jobs": [job]})
        self.assertEqual(receipt["exceptions"], [{"job_id": "PRINT-001", "reason": "DESIGN_HASH_MISMATCH"}])

    def test_multiple_independent_faults_emit_multiple_exact_reasons(self):
        job = fixture.clean_job(1)
        job["prejob"]["station_verification"]["passed"] = False
        job["postjob"]["final_report"]["portal_qr_sha256"] = fixture.h("bad-qr")
        receipt = gate.evaluate({"schema_version": 1, "jobs": [job]})
        self.assertEqual(
            receipt["exceptions"],
            [
                {"job_id": "PRINT-001", "reason": "PORTAL_QR_MISMATCH"},
                {"job_id": "PRINT-001", "reason": "STATION_VERIFICATION_FAILED"},
            ],
        )

    def test_duplicate_job_id_rejected(self):
        job = fixture.clean_job(1)
        with self.assertRaises(gate.GateInputError):
            gate.evaluate({"schema_version": 1, "jobs": [job, copy.deepcopy(job)]})

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":1,"jobs":[]}', encoding="utf-8")
            with self.assertRaises(gate.GateInputError):
                gate.load_json(path)

    def test_atomic_output_and_input_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"schema_version": 1, "jobs": [fixture.clean_job(1)]}
            source = Path(tmp) / "input.json"
            output = Path(tmp) / "receipt.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            receipt = gate.evaluate(payload)
            gate.write_atomic(output, receipt, input_path=source)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["receipt_sha256"], receipt["receipt_sha256"])
            with self.assertRaises(gate.GateInputError):
                gate.write_atomic(source, receipt, input_path=source)

    def test_boolean_schema_version_rejected(self):
        with self.assertRaises(gate.GateInputError):
            gate.evaluate({"schema_version": True, "jobs": [fixture.clean_job(1)]})

    def test_nonfinite_scale_rejected(self):
        job = fixture.clean_job(1)
        job["prejob"]["layout"]["scale"] = float("nan")
        with self.assertRaises(gate.GateInputError):
            gate.evaluate({"schema_version": 1, "jobs": [job]})

    def test_unexpected_keys_fail_closed(self):
        job = fixture.clean_job(1)
        job["prejob"]["robot_command"] = "PRINT"
        with self.assertRaises(gate.GateInputError):
            gate.evaluate({"schema_version": 1, "jobs": [job]})


if __name__ == "__main__":
    unittest.main()
