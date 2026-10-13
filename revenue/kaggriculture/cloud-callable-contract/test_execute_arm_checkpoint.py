"""Exercise the executor's actual CLI loop and filesystem with synthetic rows.

No engine, policy, game, or seed panel is executed. Extracting the unchanged
function definitions avoids importing the optional simulation dependencies.
"""
import argparse
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(os.environ.get("TITAN_EXECUTOR_SOURCE", str(
    Path(__file__).resolve().parents[1] / "cloud-model-lab" / "execute_arm.py")))


def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"write_checkpoint", "main", "wtl"}
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = dict(argparse=argparse, json=json, os=os, tempfile=tempfile)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


def row(seed, seat, opponent, factory, label, record_path=True):
    return dict(seed=seed, seat=seat, opponent=opponent, arm=label,
                own_cash=101 if label == "candidate" else 100, rival_cash=90,
                margin=11 if label == "candidate" else 10, rounds=719,
                worst_action_s=0.01, error=None,
                executor_timing={"fixture": "retained"})


def invoke(namespace, out, game=row, extra=()):
    namespace["load_callable"] = lambda p, roots: (object(), {"path": p, "label": p, "sha256": p})
    namespace["game"] = game
    argv = ["execute_arm.py", "--candidate", "candidate.py", "--control", "control.py",
            "--seeds", "101", "--seats", "0", "--opponents", "arlene", "--no-path",
            "--out", str(out), *extra]
    with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
        namespace["main"]()


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "out.json"
        self.ns = load_functions()

    def read(self):
        return json.loads(self.out.read_text(encoding="utf-8"))

    def assert_no_temporary(self):
        self.assertEqual(list(self.root.rglob(".execute-arm-*.json.tmp")), [])

    def test_control_is_written_before_candidate_begins(self):
        def fixture(*args):
            if args[4] == "candidate":
                saved = self.read()
                self.assertEqual([r["arm"] for r in saved["rows"]], ["control"])
                self.assertEqual(saved["checkpoint"], dict(complete=False, recorded_rows=1,
                                                           expected_rows=2, failed_rows=0))
            return row(*args)
        invoke(self.ns, self.out, fixture)

    def test_keyboard_interrupt_retains_returned_control(self):
        def fixture(*args):
            if args[4] == "candidate":
                raise KeyboardInterrupt("synthetic interruption")
            return row(*args)
        with self.assertRaises(KeyboardInterrupt):
            invoke(self.ns, self.out, fixture)
        saved = self.read()
        self.assertEqual(len(saved["rows"]), 1)
        self.assertFalse(saved["checkpoint"]["complete"])

    def test_interruption_later_preserves_prior_pair_and_current_control(self):
        def fixture(*args):
            if args[0] == 102 and args[4] == "candidate":
                raise SystemExit("synthetic stop")
            return row(*args)
        with self.assertRaises(SystemExit):
            invoke(self.ns, self.out, fixture, ["--seeds", "101", "102"])
        saved = self.read()
        self.assertEqual([(r["seed"], r["arm"]) for r in saved["rows"]],
                         [(101, "control"), (101, "candidate"), (102, "control")])
        self.assertEqual(saved["checkpoint"]["expected_rows"], 4)
        self.assertFalse(saved["checkpoint"]["complete"])

    def test_failed_game_is_a_retained_row_not_a_win_or_missing_cell(self):
        def fixture(*args):
            result = row(*args)
            if args[4] == "candidate":
                result.update(error="ValueError: synthetic", traceback="original trace",
                              own_cash=None, rival_cash=None, margin=None)
            return result
        invoke(self.ns, self.out, fixture)
        saved = self.read()
        self.assertTrue(saved["checkpoint"]["complete"])
        self.assertEqual(saved["checkpoint"]["failed_rows"], 1)
        self.assertEqual(saved["rows"][1]["traceback"], "original trace")
        self.assertIsNone(saved["rows"][1]["margin"])

    def test_full_grid_keeps_original_order_and_source_identity(self):
        extra = ["--seeds", "101", "102", "--seats", "0", "1",
                 "--opponents", "arlene", "apex"]
        invoke(self.ns, self.out, extra=extra)
        saved = self.read()
        expected = [(s, t, o, a) for s in (101, 102) for t in (0, 1)
                    for o in ("arlene", "apex") for a in ("control", "candidate")]
        self.assertEqual([(r["seed"], r["seat"], r["opponent"], r["arm"])
                          for r in saved["rows"]], expected)
        self.assertEqual(saved["candidate"]["path"], "candidate.py")
        self.assertEqual(saved["control"]["sha256"], "control.py")
        self.assertEqual(saved["checkpoint"], dict(complete=True, recorded_rows=16,
                                                   expected_rows=16, failed_rows=0))
        self.assert_no_temporary()

    def test_diagnostic_failure_does_not_erase_either_returned_game(self):
        def fixture(*args):
            result = row(*args)
            result["path"] = [{"fixture_day": 1}]
            return result
        fake_path = types.ModuleType("market_path")
        fake_path.diff = mock.Mock(side_effect=RuntimeError("synthetic diagnostic"))
        self.ns["load_callable"] = lambda p, roots: (object(), {"label": p})
        self.ns["game"] = fixture
        args = ["execute_arm.py", "--candidate", "c", "--control", "b", "--seeds", "101",
                "--seats", "0", "--opponents", "arlene", "--out", str(self.out)]
        with mock.patch.dict(sys.modules, market_path=fake_path), mock.patch.object(sys, "argv", args), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            self.ns["main"]()
        self.assertEqual(len(self.read()["rows"]), 2)
        self.assertFalse(self.read()["checkpoint"]["complete"])

    def test_partial_json_failure_leaves_previous_destination_byte_identical(self):
        self.out.write_bytes(b'{"prior":"keep me"}\n')
        def broken_dump(payload, handle, **kwargs):
            handle.write('{"truncated":')
            raise ValueError("synthetic serialization failure")
        with mock.patch.object(json, "dump", side_effect=broken_dump), self.assertRaises(ValueError):
            invoke(self.ns, self.out)
        self.assertEqual(self.out.read_bytes(), b'{"prior":"keep me"}\n')
        self.assert_no_temporary()

    def test_replace_failure_leaves_prior_snapshot_and_cleans_temporary(self):
        self.out.write_bytes(b'{"prior":true}')
        with mock.patch.object(os, "replace", side_effect=OSError("synthetic replace failure")), \
                self.assertRaises(OSError):
            invoke(self.ns, self.out)
        self.assertEqual(self.out.read_bytes(), b'{"prior":true}')
        self.assert_no_temporary()

    def test_fsync_failure_does_not_publish_partial_json(self):
        self.out.write_bytes(b'{"prior":true}')
        with mock.patch.object(os, "fsync", side_effect=OSError("synthetic flush failure")), \
                self.assertRaises(OSError):
            invoke(self.ns, self.out)
        self.assertEqual(self.out.read_bytes(), b'{"prior":true}')
        self.assert_no_temporary()

    def test_nested_and_relative_output_paths(self):
        nested = self.root / "a" / "b" / "result.json"
        invoke(self.ns, nested)
        self.assertTrue(json.loads(nested.read_text())["checkpoint"]["complete"])
        previous = os.getcwd()
        try:
            os.chdir(self.root)
            invoke(self.ns, "relative.json")
        finally:
            os.chdir(previous)
        self.assertTrue(json.loads((self.root / "relative.json").read_text())["checkpoint"]["complete"])

    @unittest.skipUnless(os.name == "posix", "SIGTERM returncode check is POSIX-specific")
    def test_real_process_termination_retains_last_returned_game(self):
        script = '''import runpy,sys,os,signal
m=runpy.run_path(sys.argv[1])
ns=m['load_functions']()
def fixture(*args):
    if args[4]=='candidate': os.kill(os.getpid(),signal.SIGTERM)
    return m['row'](*args)
m['invoke'](ns,sys.argv[2],fixture)
'''
        process = subprocess.run([sys.executable, "-B", "-c", script, __file__, str(self.out)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, -signal.SIGTERM, process.stderr)
        saved = self.read()
        self.assertEqual(len(saved["rows"]), 1)
        self.assertFalse(saved["checkpoint"]["complete"])

    def test_failed_final_replacement_keeps_complete_rows_marked_partial(self):
        real_replace = os.replace
        attempts = []
        def replace(src, dest):
            attempts.append(1)
            if len(attempts) == 3:
                raise OSError("synthetic final write failure")
            return real_replace(src, dest)
        with mock.patch.object(os, "replace", side_effect=replace), self.assertRaises(OSError):
            invoke(self.ns, self.out)
        saved = self.read()
        self.assertEqual(saved["checkpoint"]["recorded_rows"], 2)
        self.assertFalse(saved["checkpoint"]["complete"])
        self.assert_no_temporary()

    def test_replacement_observes_parseable_old_and_new_snapshots(self):
        real_replace = os.replace
        counts = []
        def replace(src, dest):
            pending = json.loads(Path(src).read_text())
            previous = json.loads(Path(dest).read_text()) if Path(dest).exists() else None
            counts.append((None if previous is None else len(previous["rows"]), len(pending["rows"])))
            self.assertEqual(Path(src).parent.resolve(), Path(dest).parent.resolve())
            return real_replace(src, dest)
        with mock.patch.object(os, "replace", side_effect=replace):
            invoke(self.ns, self.out)
        self.assertEqual(counts, [(None, 1), (1, 2), (2, 2)])

    def test_original_json_serialization_and_timing_fields_remain(self):
        def fixture(*args):
            result = row(*args)
            result.update(note="fixture café", extra=Path("relative/path"))
            return result
        invoke(self.ns, self.out, fixture)
        for result in self.read()["rows"]:
            self.assertEqual(result["note"], "fixture café")
            self.assertEqual(result["extra"], "relative/path")
            self.assertEqual(result["executor_timing"], {"fixture": "retained"})


if __name__ == "__main__":
    unittest.main()
