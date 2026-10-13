from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StrictCliInputTests(unittest.TestCase):
    def _run(self, script: str, args: list[pathlib.Path | str], *, optimized: bool) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable]
        if optimized:
            cmd.append("-O")
        cmd.extend([str(ROOT / script), *(str(arg) for arg in args)])
        env = os.environ.copy()
        env["PYTHONINTMAXSTRDIGITS"] = "4300"
        return subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def _assert_invalid_without_traceback(self, cp: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(cp.returncode, 2, (cp.stdout, cp.stderr))
        self.assertEqual(cp.stdout, "")
        self.assertIn("INVALID:", cp.stderr)
        self.assertNotIn("Traceback", cp.stderr)
        self.assertNotIn("UnicodeEncodeError", cp.stderr)

    def test_lone_surrogate_is_contract_failure_for_both_clis_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)

            decision = json.loads((ROOT / "examples" / "point_trade.json").read_text(encoding="utf-8"))
            decision["title"] = "\ud800"
            decision_path = work / "decision-surrogate.json"
            decision_path.write_text(json.dumps(decision, ensure_ascii=True) + "\n", encoding="ascii")

            qualification = json.loads((ROOT / "qualification.example.json").read_text(encoding="utf-8"))
            qualification["evidence_refs"]["official_topic_source_bound"] = "\ud800"
            qualification_path = work / "qualification-surrogate.json"
            qualification_path.write_text(json.dumps(qualification, ensure_ascii=True) + "\n", encoding="ascii")

            for optimized in (False, True):
                with self.subTest(cli="decision", optimized=optimized):
                    cp = self._run("decision_program.py", ["evaluate", decision_path], optimized=optimized)
                    self._assert_invalid_without_traceback(cp)
                    self.assertIn("scalar Unicode", cp.stderr)
                with self.subTest(cli="qualification", optimized=optimized):
                    cp = self._run("qualification_gate.py", [qualification_path], optimized=optimized)
                    self._assert_invalid_without_traceback(cp)
                    self.assertIn("scalar Unicode", cp.stderr)

    def test_oversized_integer_is_contract_failure_for_both_clis_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            oversized_path = pathlib.Path(td) / "oversized-int.json"
            oversized_path.write_text('{"oversized":' + ("9" * 5000) + "}\n", encoding="ascii")

            for optimized in (False, True):
                with self.subTest(cli="decision", optimized=optimized):
                    cp = self._run("decision_program.py", ["evaluate", oversized_path], optimized=optimized)
                    self._assert_invalid_without_traceback(cp)
                with self.subTest(cli="qualification", optimized=optimized):
                    cp = self._run("qualification_gate.py", [oversized_path], optimized=optimized)
                    self._assert_invalid_without_traceback(cp)


if __name__ == "__main__":
    unittest.main()