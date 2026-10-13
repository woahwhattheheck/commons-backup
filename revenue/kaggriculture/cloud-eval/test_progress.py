"""CLI checkpoint/file/process tests; fixture rows are NOT competitive games.

Run: python -B -m unittest -v test_progress
KAG_PROGRESS_EVALUATOR may name an exact baseline file for negative controls.
"""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
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

TARGET = Path(os.environ.get("KAG_PROGRESS_EVALUATOR", Path(__file__).with_name("evaluate.py"))).resolve()
spec = importlib.util.spec_from_file_location("progress_target", TARGET)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def row(seat=0, scores=None, status="complete", trace="fixture-trace"):
    return {"seed": 17, "candidate_seat": seat, "status": status,
            "scores": ([8, 3] if scores is None else scores) if status == "complete" else None,
            "failure": None if status == "complete" else {"kind": "timeout", "seat": seat},
            "trace_sha256": trace, "steps": 1, "daily_bank": [], "actors": []}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "report.json"
        self.old = b'{"previous": "keep"}\n'
        self.path.write_bytes(self.old)

    def assert_old_only(self):
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_roundtrip_and_sync_before_replace(self):
        calls = []
        fsync, replace = ev.os.fsync, ev.os.replace
        def sync(fd):
            calls.append("sync")
            return fsync(fd)
        def rename(src, dst):
            calls.append("replace")
            self.assertEqual(self.path.read_bytes(), self.old)
            self.assertEqual(json.loads(Path(src).read_text()), {"label": "μ", "values": [1, 2]})
            return replace(src, dst)
        with mock.patch.object(ev.os, "fsync", side_effect=sync), mock.patch.object(ev.os, "replace", side_effect=rename):
            ev.write_report(self.path, {"label": "μ", "values": [1, 2]})
        self.assertEqual(calls, ["sync", "replace"])
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_nested_output(self):
        destination = self.path.parent / "nested" / "report.json"
        ev.write_report(destination, {"ok": True})
        self.assertEqual(json.loads(destination.read_text()), {"ok": True})
        self.assertEqual(self.path.read_bytes(), self.old)

    def test_invalid_value_preserves_previous_snapshot(self):
        with self.assertRaises(ValueError):
            ev.write_report(self.path, {"bad": float("nan")})
        self.assert_old_only()

    def test_fsync_failure_preserves_previous_snapshot(self):
        with mock.patch.object(ev.os, "fsync", side_effect=OSError("injected fsync")):
            with self.assertRaisesRegex(OSError, "injected fsync"):
                ev.write_report(self.path, {"new": True})
        self.assert_old_only()

    def test_replace_failure_preserves_previous_snapshot(self):
        with mock.patch.object(ev.os, "replace", side_effect=OSError("injected replace")):
            with self.assertRaisesRegex(OSError, "injected replace"):
                ev.write_report(self.path, {"new": True})
        self.assert_old_only()

    def test_interrupted_write_cleans_temporary_file(self):
        with mock.patch.object(ev.os, "fsync", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                ev.write_report(self.path, {"new": True})
        self.assert_old_only()

    def test_partial_write_failure_cleans_temporary_file(self):
        factory = ev.tempfile.NamedTemporaryFile
        @contextmanager
        def broken_file(*args, **kwargs):
            with factory(*args, **kwargs) as stream:
                class BrokenWriter:
                    name = stream.name
                    def write(self, data):
                        stream.write(data[:5])
                        stream.flush()
                        raise OSError("injected short write")
                yield BrokenWriter()
        with mock.patch.object(ev.tempfile, "NamedTemporaryFile", side_effect=broken_file):
            with self.assertRaisesRegex(OSError, "injected short write"):
                ev.write_report(self.path, {"new": True})
        self.assert_old_only()


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.output = root / "tournament.json"
        self.progress = root / "tournament.json.progress.json"
        self.old = b'{"old_final": true}\n'
        self.output.write_bytes(self.old)
        self.agent = root / "agent.py"
        self.agent.write_text('def agent(obs):\n    return {}\n')
        self.loader = root / "loader.py"
        self.loader.write_text('# checkpoint fixture; no engine execution\n')
        self.argv = [str(TARGET), "--candidate", str(self.agent), "--loader", str(self.loader),
                     "--engine-dir", str(root), "--opponent", "r=official_starter", "--seeds", "17",
                     "--output", str(self.output)]
        self.stdout, self.stderr = io.StringIO(), io.StringIO()

    @contextmanager
    def invocation(self, effects, extra=()):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", self.argv + list(extra)))
            stack.enter_context(mock.patch.object(ev, "get_engine", return_value=(object(), {"fixture": "not-a-game"})))
            played = stack.enter_context(mock.patch.object(ev, "play", side_effect=effects))
            stack.enter_context(redirect_stdout(self.stdout))
            stack.enter_context(redirect_stderr(self.stderr))
            yield played

    def read_progress(self):
        return json.loads(self.progress.read_text())

    def test_complete_preserves_summary_and_final_format(self):
        with self.invocation([row(), row(1)]):
            self.assertEqual(ev.main(), 0)
        report = json.loads(self.output.read_text())
        self.assertEqual(report, self.read_progress())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"]["r"]["wins"], 1)
        self.assertEqual(report["summary"]["r"]["losses"], 1)
        self.assertEqual(report["progress"]["state"], "complete")
        self.assertEqual(report["progress"]["recorded_games"], 2)
        self.assertIsNone(report["reproducibility"])

    def test_interrupt_after_one_preserves_row_and_old_final(self):
        first = row()
        with self.invocation([first, KeyboardInterrupt]) as play:
            self.assertEqual(ev.main(), 130)
        report = self.read_progress()
        self.assertEqual(report["games"], [first])
        self.assertEqual(play.call_count, 2)
        self.assertEqual(report["progress"], {"state": "interrupted", "phase": "games", "planned_games": 2,
                         "recorded_games": 1, "active_game": {"opponent": "r", "seed": 17, "candidate_seat": 1},
                         "recheck_requested": False, "error_type": "KeyboardInterrupt"})
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_interrupt_before_first_has_no_fabricated_row(self):
        with self.invocation([KeyboardInterrupt]):
            self.assertEqual(ev.main(), 130)
        report = self.read_progress()
        self.assertEqual(report["games"], [])
        self.assertEqual(report["summary"], {})
        self.assertEqual(report["progress"]["recorded_games"], 0)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_unexpected_error_keeps_original_exception_and_row(self):
        with self.invocation([row(), RuntimeError("fixture-private-detail")]):
            with self.assertRaisesRegex(RuntimeError, "fixture-private-detail"):
                ev.main()
        report = self.read_progress()
        self.assertEqual(report["progress"]["state"], "error")
        self.assertEqual(report["progress"]["error_type"], "RuntimeError")
        self.assertNotIn("fixture-private-detail", self.progress.read_text())
        self.assertEqual(len(report["games"]), 1)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_failed_game_stays_failed_not_a_win(self):
        with self.invocation([row(status="failed"), row(1)]):
            self.assertEqual(ev.main(), 1)
        report = self.read_progress()
        self.assertEqual(report["progress"]["state"], "complete")
        self.assertIsNone(report["games"][0]["scores"])
        self.assertEqual(report["summary"]["r"]["failed"], 1)
        self.assertEqual(report["summary"]["r"]["wins"], 0)

    def test_legitimate_losses_do_not_fail_cli(self):
        with self.invocation([row(scores=[1, 2]), row(1, scores=[2, 1])]):
            self.assertEqual(ev.main(), 0)
        self.assertEqual(self.read_progress()["summary"]["r"]["losses"], 2)

    def test_recheck_does_not_duplicate_aggregate(self):
        with self.invocation([row(), row(1), row()], ["--recheck-first"]) as played:
            self.assertEqual(ev.main(), 0)
        report = self.read_progress()
        self.assertEqual(played.call_count, 3)
        self.assertEqual(len(report["games"]), 2)
        self.assertTrue(report["reproducibility"]["same_trace_and_scores"])

    def test_recheck_mismatch_remains_failure(self):
        with self.invocation([row(), row(1), row(trace="different")], ["--recheck-first"]):
            self.assertEqual(ev.main(), 1)
        self.assertFalse(self.read_progress()["reproducibility"]["same_trace_and_scores"])

    def test_interrupted_recheck_retains_all_original_rows(self):
        with self.invocation([row(), row(1), KeyboardInterrupt], ["--recheck-first"]):
            self.assertEqual(ev.main(), 130)
        report = self.read_progress()
        self.assertEqual(report["progress"]["phase"], "recheck")
        self.assertEqual(report["progress"]["state"], "interrupted")
        self.assertEqual(report["progress"]["recorded_games"], 2)
        self.assertIsNone(report["reproducibility"])
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_saved_before_next_game_is_started(self):
        calls = []
        def game(*args):
            current = self.read_progress()
            self.assertEqual(len(current["games"]), len(calls))
            self.assertEqual(current["progress"]["state"], "running")
            calls.append(args[5])
            return row(args[5])
        with self.invocation(game):
            self.assertEqual(ev.main(), 0)
        self.assertEqual(calls, [0, 1])

    def test_final_replace_failure_keeps_old_final_and_recoverable_rows(self):
        replace = ev.os.replace
        def fail_final(src, dst):
            if Path(dst) == self.output:
                raise OSError("injected final replace")
            return replace(src, dst)
        with self.invocation([row(), row(1)]), mock.patch.object(ev.os, "replace", side_effect=fail_final):
            with self.assertRaisesRegex(OSError, "injected final replace"):
                ev.main()
        report = self.read_progress()
        self.assertEqual(report["progress"]["state"], "error")
        self.assertEqual(report["progress"]["phase"], "finalize")
        self.assertEqual(len(report["games"]), 2)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_checkpoint_failure_does_not_mask_original_error(self):
        writer = getattr(ev, "write_report", None)
        def fail_error(path, report):
            if report["progress"]["state"] == "error":
                raise OSError("injected stop write")
            return writer(path, report)
        with self.invocation([row(), RuntimeError("original-error")]), mock.patch.object(ev, "write_report", side_effect=fail_error):
            with self.assertRaisesRegex(RuntimeError, "original-error"):
                ev.main()
        self.assertEqual(len(self.read_progress()["games"]), 1)
        self.assertEqual(self.read_progress()["progress"]["state"], "running")
        self.assertIn("OSError", self.stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_original_roster_seed_seat_order_is_unchanged(self):
        calls = []
        def game(*args):
            calls.append((args[4], args[5], list(args[1])))
            value = row(args[5])
            value["seed"] = args[4]
            return value
        with self.invocation(game, ["--opponent", "s=official_starter", "--seeds", "17,19"]):
            self.assertEqual(ev.main(), 0)
        expected = [(seed, seat) for _ in ("r", "s") for seed in (17, 19) for seat in (0, 1)]
        self.assertEqual([(seed, seat) for seed, seat, _ in calls], expected)
        for _, seat, pair in calls:
            self.assertEqual(pair[seat], str(self.agent))
            self.assertEqual(pair[1-seat], "official_starter")
        self.assertEqual(self.read_progress()["progress"]["planned_games"], 8)


@unittest.skipUnless(os.name == "posix", "POSIX process signals")
class ProcessTests(unittest.TestCase):
    def run_signal_case(self, sig):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output, marker = root / "final.json", root / "second-game.started"
            old = b'{"old_final":true}\n'
            output.write_bytes(old)
            fixture = root / "fixture.py"
            fixture.write_text("# fixture only\n")
            script = root / "runner.py"
            script.write_text('''import importlib.util, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("ev", sys.argv[1])
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
root = Path(sys.argv[2])
calls = 0
def fixture_play(*args):
    global calls
    calls += 1
    if calls == 2:
        (root / "second-game.started").write_text("ready")
        while True:
            time.sleep(0.05)
    return {"seed":17,"candidate_seat":0,"status":"complete","scores":[8,3],"failure":None,"trace_sha256":"fixture"}
ev.get_engine = lambda *args: (object(), {"fixture":"not-a-game"})
ev.play = fixture_play
sys.argv = [str(Path(sys.argv[1])), "--candidate", str(root / "fixture.py"),
            "--loader", str(root / "fixture.py"), "--engine-dir", str(root),
            "--opponent", "r=official_starter", "--seeds", "17", "--output", str(root / "final.json")]
raise SystemExit(ev.main())
''')
            proc = subprocess.Popen([sys.executable, "-B", str(script), str(TARGET), str(root)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "CLI did not reach second fixture game")
                proc.send_signal(sig)
                stdout, stderr = proc.communicate(timeout=5)
                progress = root / "final.json.progress.json"
                self.assertTrue(progress.exists(), "Completed game was never checkpointed")
                report = json.loads(progress.read_text())
                self.assertEqual(len(report["games"]), 1)
                self.assertEqual(report["games"][0]["scores"], [8, 3])
                self.assertEqual(report["progress"]["planned_games"], 2)
                self.assertEqual(report["progress"]["recorded_games"], 1)
                self.assertEqual(output.read_bytes(), old)
                if sig == signal.SIGINT:
                    self.assertEqual(proc.returncode, 130, stderr.decode())
                    self.assertEqual(report["progress"]["state"], "interrupted")
                else:
                    self.assertEqual(proc.returncode, -sig)
                    self.assertEqual(report["progress"]["state"], "running")
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.communicate(timeout=5)

    def test_sigint_retains_previous_game(self):
        self.run_signal_case(signal.SIGINT)

    def test_sigkill_retains_previous_game(self):
        self.run_signal_case(signal.SIGKILL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
