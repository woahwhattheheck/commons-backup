import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import kylin_memory_bench as bench

DATASET = ROOT / "sample" / "dataset.jsonl"
REFERENCE = ROOT / "sample" / "reference-agent.json"
FORGETFUL = ROOT / "sample" / "forgetful-agent.json"


class ReportFilenameContractTests(unittest.TestCase):
    def _evidence_with_agent(self, source: Path, destination: Path, agent: str) -> Path:
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["agent"] = agent
        destination.write_text(json.dumps(payload), encoding="utf-8")
        return destination

    def _run_main(self, argv):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = bench.main(argv)
        return rc, stderr.getvalue()

    def test_slug_byte_boundary_is_explicit(self):
        accepted = "x" * bench._MAX_REPORT_SLUG_BYTES
        self.assertEqual(bench._validated_report_slug(accepted), accepted)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            bench._validated_report_slug(accepted + "x")

    def test_windows_device_basenames_are_rejected(self):
        names = ["CON", "con.txt", "PRN.", "aux.log", "NUL", "COM1", "com9.json", "LPT1", "lpt9.log"]
        for name in names:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "reserved on Windows"):
                bench._validated_report_slug(name)

    def test_safe_device_lookalikes_remain_valid(self):
        for name in ("console", "COM10", "LPT0", "xCON", "NUL-safe"):
            with self.subTest(name=name):
                self.assertEqual(bench._validated_report_slug(name), name)

    def test_score_rejects_overlong_name_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            evidence = self._evidence_with_agent(
                REFERENCE,
                tmp_path / "long.json",
                "x" * (bench._MAX_REPORT_SLUG_BYTES + 1),
            )
            out = tmp_path / "reports"
            rc, stderr = self._run_main([
                "score", "--dataset", str(DATASET), "--evidence", str(evidence),
                "--out-dir", str(out),
            ])
            self.assertEqual(rc, 2)
            self.assertIn("exceeds", stderr)
            self.assertFalse(out.exists())

    def test_score_rejects_reserved_name_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            evidence = self._evidence_with_agent(REFERENCE, tmp_path / "reserved.json", "CON.txt")
            out = tmp_path / "reports"
            rc, stderr = self._run_main([
                "score", "--dataset", str(DATASET), "--evidence", str(evidence),
                "--out-dir", str(out),
            ])
            self.assertEqual(rc, 2)
            self.assertIn("reserved on Windows", stderr)
            self.assertFalse(out.exists())

    def test_compare_rejects_overlong_second_name_without_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            evidence = self._evidence_with_agent(
                FORGETFUL,
                tmp_path / "long.json",
                "x" * (bench._MAX_REPORT_SLUG_BYTES + 1),
            )
            out = tmp_path / "reports"
            rc, stderr = self._run_main([
                "compare", "--dataset", str(DATASET),
                "--evidence", str(REFERENCE), "--evidence", str(evidence),
                "--out-dir", str(out),
            ])
            self.assertEqual(rc, 2)
            self.assertIn("exceeds", stderr)
            self.assertFalse(out.exists())

    def test_compare_rejects_reserved_second_name_without_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            evidence = self._evidence_with_agent(FORGETFUL, tmp_path / "reserved.json", "LPT9.log")
            out = tmp_path / "reports"
            rc, stderr = self._run_main([
                "compare", "--dataset", str(DATASET),
                "--evidence", str(REFERENCE), "--evidence", str(evidence),
                "--out-dir", str(out),
            ])
            self.assertEqual(rc, 2)
            self.assertIn("reserved on Windows", stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
