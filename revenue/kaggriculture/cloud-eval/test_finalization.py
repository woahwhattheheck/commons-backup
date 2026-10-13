"""Final-report transaction tests. CLI rows are fixtures, not competitive games.

Run: python -B -m unittest -v test_finalization
KAG_PROGRESS_EVALUATOR selects an exact evaluator file for negative controls.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

import test_progress as support

ev = support.ev


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing CLI boundary fixture without inheriting/rerunning
        # its TestCase methods or claiming additional independent game samples.
        self.fixture = support.MainTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def run_complete(self):
        with self.fixture.invocation([support.row(), support.row(1)]):
            return ev.main()

    def final(self):
        return json.loads(self.fixture.output.read_text(encoding="utf-8"))

    def progress(self):
        return self.fixture.read_progress()

    def test_success_binds_both_reports_to_one_invocation(self):
        self.assertEqual(self.run_complete(), 0)
        final = self.final()
        self.assertEqual(final, self.progress())
        identifier = final["invocation_id"]
        self.assertEqual(uuid.UUID(hex=identifier).hex, identifier)
        self.assertEqual(final["progress"]["state"], "complete")
        self.assertEqual(len(final["games"]), 2)

    def test_repeated_identical_inputs_receive_distinct_invocation_ids(self):
        self.assertEqual(self.run_complete(), 0)
        first = self.final()["invocation_id"]
        self.assertEqual(self.run_complete(), 0)
        self.assertNotEqual(first, self.final()["invocation_id"])
        self.assertEqual(self.final(), self.progress())

    def test_new_interruption_is_distinguishable_from_preserved_final(self):
        self.assertEqual(self.run_complete(), 0)
        old = self.fixture.output.read_bytes()
        previous = self.final()["invocation_id"]
        with self.fixture.invocation([support.row(), KeyboardInterrupt]):
            self.assertEqual(ev.main(), 130)
        self.assertEqual(self.fixture.output.read_bytes(), old)
        self.assertNotEqual(previous, self.progress()["invocation_id"])
        self.assertEqual(self.progress()["progress"]["state"], "interrupted")
        self.assertEqual(len(self.progress()["games"]), 1)

    def test_before_final_replace_progress_is_still_running(self):
        original = ev.os.replace
        inspected = []
        def replace(src, dst):
            if Path(dst) == self.fixture.output:
                snapshot = self.progress()
                inspected.append(snapshot)
                self.assertEqual(snapshot["progress"]["state"], "running")
                self.assertEqual(snapshot["progress"]["phase"], "finalize")
                self.assertEqual(self.fixture.output.read_bytes(), self.fixture.old)
            return original(src, dst)
        with mock.patch.object(ev.os, "replace", side_effect=replace):
            self.assertEqual(self.run_complete(), 0)
        self.assertEqual(len(inspected), 1)
        self.assertEqual(inspected[0]["invocation_id"], self.final()["invocation_id"])

    def test_complete_sidecar_is_written_only_after_same_run_final(self):
        original = ev.os.replace
        checked = []
        def replace(src, dst):
            candidate = json.loads(Path(src).read_text(encoding="utf-8"))
            if Path(dst) == self.fixture.progress and candidate["progress"]["state"] == "complete":
                final = self.final()
                self.assertEqual(final, candidate)
                checked.append(candidate["invocation_id"])
            return original(src, dst)
        with mock.patch.object(ev.os, "replace", side_effect=replace):
            self.assertEqual(self.run_complete(), 0)
        self.assertEqual(checked, [self.final()["invocation_id"]])

    def test_final_replace_failure_preserves_old_final_and_original_error(self):
        original = ev.os.replace
        failure = OSError("final replacement unavailable")
        def replace(src, dst):
            if Path(dst) == self.fixture.output:
                raise failure
            return original(src, dst)
        with mock.patch.object(ev.os, "replace", side_effect=replace):
            with self.assertRaises(OSError) as caught:
                self.run_complete()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.fixture.output.read_bytes(), self.fixture.old)
        self.assertEqual(self.progress()["progress"]["state"], "error")
        self.assertEqual(self.progress()["progress"]["phase"], "finalize")
        self.assertEqual(len(self.progress()["games"]), 2)

    def test_sidecar_failure_after_final_keeps_same_run_final(self):
        original = ev.os.replace
        failure = OSError("complete sidecar unavailable")
        def replace(src, dst):
            value = json.loads(Path(src).read_text(encoding="utf-8"))
            if Path(dst) == self.fixture.progress and value["progress"]["state"] == "complete":
                raise failure
            return original(src, dst)
        with mock.patch.object(ev.os, "replace", side_effect=replace):
            with self.assertRaises(OSError) as caught:
                self.run_complete()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.final()["progress"]["state"], "complete")
        self.assertEqual(self.progress()["progress"]["state"], "error")
        self.assertEqual(self.final()["invocation_id"], self.progress()["invocation_id"])
        self.assertEqual(self.final()["games"], self.progress()["games"])

    def test_interrupted_finalization_keeps_exact_rows_not_an_extra_sample(self):
        original = ev.os.replace
        def replace(src, dst):
            if Path(dst) == self.fixture.output:
                raise KeyboardInterrupt
            return original(src, dst)
        with mock.patch.object(ev.os, "replace", side_effect=replace):
            self.assertEqual(self.run_complete(), 130)
        self.assertEqual(self.fixture.output.read_bytes(), self.fixture.old)
        self.assertEqual(len(self.progress()["games"]), 2)
        self.assertEqual(self.progress()["progress"]["state"], "interrupted")

    def test_recheck_is_saved_before_final_publication(self):
        original = ev.os.replace
        seen = []
        def replace(src, dst):
            if Path(dst) == self.fixture.output:
                progress = self.progress()
                self.assertEqual(progress["progress"]["state"], "running")
                self.assertTrue(progress["reproducibility"]["same_trace_and_scores"])
                self.assertEqual(len(progress["games"]), 2)
                seen.append(True)
            return original(src, dst)
        with self.fixture.invocation([support.row(), support.row(1), support.row()], ["--recheck-first"]), \
                mock.patch.object(ev.os, "replace", side_effect=replace):
            self.assertEqual(ev.main(), 0)
        self.assertEqual(seen, [True])
        self.assertEqual(self.final(), self.progress())


@unittest.skipUnless(os.name == "posix", "POSIX hard-termination boundary")
class HardTerminationTests(unittest.TestCase):
    def check_boundary(self, position):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = b'{"old_final": true}\n'
            (root / "final.json").write_bytes(old)
            (root / "fixture.py").write_text("# CLI fixture, not an agent execution\n", encoding="utf-8")
            runner = root / "runner.py"
            runner.write_text('''import importlib.util, json, os, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("target", sys.argv[1])
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
root, position = Path(sys.argv[2]), sys.argv[3]
output = root / "final.json"
def play(*args):
    return {"opponent":"r", "seed":17, "candidate_seat":args[5],
            "status":"complete", "scores":[8,3], "failure":None,
            "trace_sha256":"CLI-boundary-fixture", "steps":1,
            "daily_bank":[], "actors":[]}
ev.play = play
ev.get_engine = lambda *args: (object(), {"fixture":"not-a-game"})
replace = ev.os.replace
def boundary(src, dst):
    if Path(dst) == output:
        if position == "after":
            replace(src, dst)
        (root / "boundary").write_text(position)
        # The parent kills us only after the exact final-publication boundary.
        time.sleep(30)
    return replace(src, dst)
ev.os.replace = boundary
sys.argv = [str(ev.__file__), "--candidate", str(root/"fixture.py"),
            "--loader", str(root/"fixture.py"), "--engine-dir", str(root),
            "--opponent", "r=official_starter", "--seeds", "17",
            "--output", str(output)]
raise SystemExit(ev.main())
''', encoding="utf-8")
            with subprocess.Popen([sys.executable, "-B", str(runner), str(support.TARGET), str(root), position],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as process:
                try:
                    deadline = time.monotonic() + 8
                    while not (root / "boundary").exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue((root / "boundary").exists(), "exact final-write boundary was not reached")
                    process.kill()
                    _, stderr = process.communicate(timeout=3)
                    self.assertEqual(process.returncode, -signal.SIGKILL, stderr.decode(errors="replace"))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=3)
            final_bytes = (root / "final.json").read_bytes()
            progress = json.loads((root / "final.json.progress.json").read_text())
            self.assertEqual(progress["progress"]["state"], "running")
            self.assertEqual(progress["progress"]["phase"], "finalize")
            self.assertEqual(progress["progress"]["recorded_games"], 2)
            self.assertEqual(len(progress["games"]), 2)
            if position == "before":
                self.assertEqual(final_bytes, old)
            else:
                final = json.loads(final_bytes)
                self.assertEqual(final["progress"]["state"], "complete")
                self.assertEqual(final["invocation_id"], progress["invocation_id"])
                self.assertEqual(final["games"], progress["games"])

    def test_sigkill_immediately_before_final_replace(self):
        self.check_boundary("before")

    def test_sigkill_immediately_after_final_replace(self):
        self.check_boundary("after")


if __name__ == "__main__":
    unittest.main(verbosity=2)
