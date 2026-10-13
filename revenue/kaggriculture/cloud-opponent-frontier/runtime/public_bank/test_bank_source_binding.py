"""Bind the public bank's snapshot to the real official loader's retained code.

Uses the unmodified pinned file loader plus temporary benign policies. Set
T07_BANK_IMPL to exercise the exact predecessor with these same regressions.
"""
from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
IMPL = Path(os.environ.get("T07_BANK_IMPL", str(HERE / "bank.py")))
spec = importlib.util.spec_from_file_location("t07_binding_subject", IMPL)
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)
PACK = Path(os.environ.get("T07_PACK", str(HERE.parents[2] / "cloud-pack")))


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(PACK, self.root / "contract", ignore=shutil.ignore_patterns("__pycache__"))
        self.source = self.root / "policy.py"
        self.original = b'def agent(obs):\n return {"revision": "A"}\n'
        self.replacement = b'def agent(obs):\n return {"revision": "B"}\n'
        self.install(self.original)

    def install(self, data, mode="not_applicable"):
        self.source.write_bytes(data)
        entry = {"source": "policy.py", "source_sha256": hashlib.sha256(data).hexdigest(),
                 "assignment": mode, "dependencies": {}}
        (self.root / "BANK.json").write_text(json.dumps({"entries": {"sample": entry}}))

    def between_reads(self, replacement, preserve_times=False):
        load_module = bank.module
        source = self.source
        def replace_then_load(*args, **kwargs):
            stat = source.stat()
            source.write_bytes(replacement)
            if preserve_times:
                os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return load_module(*args, **kwargs)
        with patch.object(bank, "module", side_effect=replace_then_load):
            return bank.make_agent(self.root, "sample")

    def test_changed_loader_snapshot_is_rejected(self):
        run = self.between_reads(self.replacement)
        with self.assertRaisesRegex(ValueError, "loader source differs"):
            run({})

    def test_same_size_and_timestamp_does_not_hide_replacement(self):
        self.assertEqual(len(self.original), len(self.replacement))
        run = self.between_reads(self.replacement, preserve_times=True)
        with self.assertRaisesRegex(ValueError, "loader source differs"):
            run({})

    def test_mismatch_is_rejected_before_top_level_execution(self):
        marker = self.root / "executed.txt"
        replacement = ('from pathlib import Path\n'
                       f'Path({str(marker)!r}).write_text("local-test-only")\n'
                       'def agent(obs):\n return {}\n').encode()
        run = self.between_reads(replacement)
        with self.assertRaisesRegex(ValueError, "loader source differs"):
            run({})
        self.assertFalse(marker.exists())

    def test_retry_cannot_accept_previously_captured_wrong_source(self):
        run = self.between_reads(self.replacement)
        self.source.write_bytes(self.original)
        for _ in range(2):
            with self.subTest(attempt=_), self.assertRaisesRegex(ValueError, "loader source differs"):
                run({})

    def test_import_function_restored_on_snapshot_mismatch(self):
        previous = builtins.__import__
        run = self.between_reads(self.replacement)
        try:
            with self.assertRaisesRegex(ValueError, "loader source differs"):
                run({})
        finally:
            self.assertIs(builtins.__import__, previous)

    def test_later_edit_does_not_replace_verified_captured_program(self):
        run = bank.make_agent(self.root, "sample")
        self.source.write_bytes(self.replacement)
        self.assertEqual(run({}), {"revision": "A"})
        self.assertEqual(run({}), {"revision": "A"})

    def test_later_deletion_keeps_verified_captured_program(self):
        run = bank.make_agent(self.root, "sample")
        self.source.unlink()
        self.assertEqual(run({}), {"revision": "A"})

    def test_exact_bytes_hash_still_precedes_loader(self):
        self.source.write_bytes(self.replacement)
        with patch.object(bank, "module", side_effect=AssertionError("must not load")):
            with self.assertRaisesRegex(ValueError, "source differs"):
                bank.make_agent(self.root, "sample")

    def test_all_official_universal_newline_forms(self):
        for sep in (b"\n", b"\r\n", b"\r"):
            with self.subTest(newline=repr(sep)):
                self.install(self.original.replace(b"\n", sep))
                self.assertEqual(bank.make_agent(self.root, "sample")({}), {"revision": "A"})

    def test_newline_only_intermediate_change_keeps_same_compiled_program(self):
        run = self.between_reads(self.original.replace(b"\n", b"\r\n"))
        self.assertEqual(run({}), {"revision": "A"})

    def test_nonascii_source_and_mixed_newlines(self):
        self.install('def agent(obs):\r\n return {"text": "caf\u00e9 \u03bb"}\r'.encode())
        self.assertEqual(bank.make_agent(self.root, "sample")({}), {"text": "caf\u00e9 \u03bb"})

    def test_persistent_state_with_two_independent_instances(self):
        self.install(b'n = 0\ndef agent(obs):\n global n\n n += 1\n return {"n": n}\n')
        first = bank.make_agent(self.root, "sample")
        second = bank.make_agent(self.root, "sample")
        self.assertEqual(first({}), {"n": 1})
        self.assertEqual(first({}), {"n": 2})
        self.assertEqual(second({}), {"n": 1})

    def test_last_callable_config_path_and_argument_contract(self):
        self.install(b'def unused():\n return None\ndef agent(obs, cfg):\n return {"path": cfg["__raw_path__"], "value": obs["x"]}\n')
        result = bank.make_agent(self.root, "sample")({"x": 4}, {"untouched": 8})
        self.assertEqual(result, {"path": str(self.source), "value": 4})

    def test_greedy_dependency_branch_and_import_restoration(self):
        self.install(b'try:\n import numpy\n _HUNGARIAN=True\nexcept ImportError:\n _HUNGARIAN=False\ndef agent(obs):\n return {"hungarian":_HUNGARIAN}\n', "greedy")
        previous = builtins.__import__
        self.assertEqual(bank.make_agent(self.root, "sample")({}), {"hungarian": False})
        self.assertIs(builtins.__import__, previous)

    def test_action_cancellation_and_retry_preserve_original_exception(self):
        self.install(b'n=0\ndef agent(obs):\n global n\n n += 1\n if n == 1: raise KeyboardInterrupt("test cancellation")\n return {"n":n}\n')
        previous = builtins.__import__
        run = bank.make_agent(self.root, "sample")
        with self.assertRaisesRegex(KeyboardInterrupt, "test cancellation"):
            run({})
        self.assertIs(builtins.__import__, previous)
        self.assertEqual(run({}), {"n": 2})

    def test_no_source_reread_during_actions(self):
        run = bank.make_agent(self.root, "sample")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected source read")):
            self.assertEqual(run({}), {"revision": "A"})
            self.assertEqual(run({}), {"revision": "A"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
