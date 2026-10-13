# SPDX-License-Identifier: MIT
"""Regression tests for real subprocess replay and pinned-input handling."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import verify


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "empty"
        self.cwd.mkdir()

    def agent(self, source, name="agent.py"):
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        return path

    def rows(self, labels, seat=0):
        return [{"step": step, "candidate_seat": seat,
                 "observation": {"step": step, "private": {"value": 10}},
                 "actions": [label, {"rival_secret_label": True}] if seat == 0
                            else [{"rival_secret_label": True}, label],
                 "done": step == len(labels) - 1}
                for step, label in enumerate(labels)]

    def write_trace(self, rows):
        path = self.root / "trace.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row) + "\n")
        return path

    def test_real_actor_isolated_flags_and_sequential_state(self):
        path = self.agent("n=0\ndef agent(obs,cfg):\n global n\n n+=1\n return {'n':n,'value':obs.private.value}\n")
        with verify.Actor(path, self.cwd) as actor:
            self.assertEqual(actor.ready["isolated"], 1)
            self.assertEqual(actor.ready["no_site"], 1)
            self.assertFalse(any("site-packages" in p for p in actor.ready["sys_path"]))
            for step in range(3):
                self.assertEqual(actor.act({"step": step, "private": {"value": 10}}, {}),
                                 {"n": step + 1, "value": 10})
            self.assertEqual(actor.report()["actions"], 3)
        self.assertIsNotNone(actor.process.poll())

    def test_fresh_actor_does_not_inherit_prior_match_state(self):
        path = self.agent("n=0\ndef agent(obs,cfg):\n global n\n n+=1\n return {'n':n}\n")
        for _ in range(2):
            with verify.Actor(path, self.cwd) as actor:
                self.assertEqual(actor.act({"step": 0}, {}), {"n": 1})
                self.assertEqual(actor.act({"step": 1}, {}), {"n": 2})

    def test_agent_stdout_cannot_corrupt_protocol(self):
        path = self.agent("print('import noise')\ndef agent(obs,cfg):\n print('action noise')\n return {'market':[['PASS']]}\n")
        with verify.Actor(path, self.cwd) as actor:
            self.assertEqual(actor.act({}, {}), {"market": [["PASS"]]})

    def test_engine_import_is_unavailable(self):
        path = self.agent("import kaggle_environments\ndef agent(obs,cfg): return {}\n")
        with self.assertRaisesRegex(RuntimeError, "import failed"):
            verify.Actor(path, self.cwd)

    def test_caught_network_attempt_is_still_reported(self):
        path = self.agent("import socket\ndef agent(obs,cfg):\n try: socket.create_connection(('example.invalid',443))\n except RuntimeError: pass\n return {}\n")
        with verify.Actor(path, self.cwd) as actor:
            with self.assertRaisesRegex(RuntimeError, "unavailable network"):
                actor.act({}, {})

    def test_missing_runtime_dependency_fails(self):
        path = self.agent("import nonexistent_titan_dependency\ndef agent(obs,cfg): return {}\n")
        with self.assertRaisesRegex(RuntimeError, "import failed"):
            verify.Actor(path, self.cwd)

    def test_environment_seed_is_not_accepted(self):
        path = self.agent("def agent(obs,cfg): return {}\n")
        with verify.Actor(path, self.cwd) as actor:
            with self.assertRaisesRegex(RuntimeError, "seed must not enter"):
                actor.act({}, {"seed": 9600803})

    def test_non_object_and_non_finite_actions_fail(self):
        for source in ("def agent(obs,cfg): return []\n", "def agent(obs,cfg): return {'x':float('nan')}\n"):
            path = self.agent(source)
            with verify.Actor(path, self.cwd) as actor:
                with self.assertRaises(RuntimeError):
                    actor.act({}, {})

    def test_timeout_reaps_real_process(self):
        path = self.agent("import time\ndef agent(obs,cfg): time.sleep(2); return {}\n")
        actor = verify.Actor(path, self.cwd)
        actor.timeout = .03
        try:
            with self.assertRaises(TimeoutError):
                actor.act({}, {})
        finally:
            actor.close()
        self.assertIsNotNone(actor.process.poll())

    def test_replay_keeps_labels_outside_worker_and_matches_every_action(self):
        source = "def agent(obs,cfg):\n assert set(obs)=={'step','private'}\n assert cfg.get('seed') is None\n return {'step':obs.step,'market':[['SELL','MILK',obs.step]]}\n"
        selected = self.agent(source, "selected.py")
        reference = self.agent(source, "reference.py")
        labels = [{"step": step, "market": [["SELL", "MILK", step]]} for step in range(3)]
        for seat in (0, 1):
            result = verify.replay(selected, reference, self.rows(labels, seat), seat, {"seed": None}, self.cwd, 5)
            self.assertEqual(result["mismatches"], [])
            self.assertEqual(result["selected_action_sha256"], result["recorded_action_sha256"])
            self.assertNotEqual(result["actors"]["selected"]["pid"], result["actors"]["reference"]["pid"])

    def test_replay_retains_ordered_market_mismatch(self):
        selected = self.agent("def agent(obs,cfg): return {'market':[['BUY','WHEAT',1],['SELL','MILK',1]]}\n", "selected.py")
        reference = self.agent("def agent(obs,cfg): return {'market':[['SELL','MILK',1],['BUY','WHEAT',1]]}\n", "reference.py")
        label = {"market": [["SELL", "MILK", 1], ["BUY", "WHEAT", 1]]}
        result = verify.replay(selected, reference, self.rows([label]), 0, {}, self.cwd, 5)
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertEqual(result["mismatches"][0]["step"], 0)

    def test_complete_trace_validation(self):
        rows = self.rows([{}, {}], seat=1)
        self.assertEqual(len(verify.load_rows(self.write_trace(rows), 1, 2)), 2)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify.load_rows(self.write_trace(rows), 1, 3)
        rows[1]["observation"]["step"] = 0
        with self.assertRaisesRegex(ValueError, "discontinuous"):
            verify.load_rows(self.write_trace(rows), 1, 2)

    def test_trace_requires_terminal_transition(self):
        rows = self.rows([{}])
        rows[-1]["done"] = False
        with self.assertRaisesRegex(ValueError, "terminal"):
            verify.load_rows(self.write_trace(rows), 0, 1)

    def test_pin_detects_exact_byte_corruption(self):
        path = self.root / "pinned"
        path.write_bytes(b"exact\n")
        pin = (6, hashlib.sha256(b"exact\n").hexdigest())
        self.assertEqual(verify.verify_pin(path, pin), b"exact\n")
        path.write_bytes(b"exact\r\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            verify.verify_pin(path, pin)

    def test_archive_regular_files_and_path_integrity(self):
        archive = self.root / "runtime.tar.gz"
        with tarfile.open(archive, "w:gz") as out:
            item = tarfile.TarInfo("nested/main.py")
            item.size = 4
            out.addfile(item, io.BytesIO(b"pass"))
        verify.extract_runtime(archive, self.root / "good")
        self.assertEqual((self.root / "good/nested/main.py").read_bytes(), b"pass")
        for name, kind in (("../escape", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)):
            with tarfile.open(archive, "w:gz") as out:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = "elsewhere"
                out.addfile(item)
            with self.assertRaises(ValueError):
                verify.extract_runtime(archive, self.root / ("bad" + str(kind)))


if __name__ == "__main__":
    unittest.main()
