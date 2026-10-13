"""Cold-import and byte-I/O regressions; no live provider or workflow actions."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci.actions_merge_train import cli, core

ROOT = Path(__file__).resolve().parents[2]
COLD_SCRIPT = r'''
import importlib.machinery
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, sys.argv[1])
mode, fail = sys.argv[2], sys.argv[3] == "fail"
check = unittest.TestCase()
names = ("core", "schema", "truth")
prior = {}
for name in names:
    sys.modules.pop(name, None)
    if mode == "module":
        prior[name] = types.ModuleType(name)
        sys.modules[name] = prior[name]
    elif mode == "none":
        prior[name] = None
        sys.modules[name] = None
original_path = list(sys.path)
original_exec = importlib.machinery.SourceFileLoader.exec_module

def execute(loader, module):
    if fail and loader.name == "_commons_actions_execution_truth_truth":
        raise RuntimeError("injected predecessor load failure")
    return original_exec(loader, module)

with mock.patch.object(importlib.machinery.SourceFileLoader, "exec_module", execute):
    if fail:
        with check.assertRaisesRegex(RuntimeError, "injected predecessor load failure"):
            from ci.actions_merge_train import core
    else:
        from ci.actions_merge_train import core
        check.assertTrue(callable(core.compile_train))
        check.assertFalse(hasattr(core, "RUN_SCHEMA"))

for name in names:
    if mode == "missing":
        check.assertFalse(name in sys.modules, f"unexpected generic module: {name}")
    else:
        check.assertTrue(name in sys.modules, f"missing original generic entry: {name}")
        check.assertIs(sys.modules[name], prior[name])
check.assertEqual(sys.path, original_path)
print("cold-import", mode, "failure" if fail else "success", "optimize", sys.flags.optimize, "PASS")
'''


class BoundaryTests(unittest.TestCase):
    def cold_import(self, mode: str, *, fail: bool = False) -> None:
        for flags in ([], ["-O"]):
            with self.subTest(mode=mode, fail=fail, flags=flags):
                result = subprocess.run(
                    [sys.executable, "-I", "-S", "-B", *flags, "-c", COLD_SCRIPT,
                     str(ROOT), mode, "fail" if fail else "success"],
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("PASS", result.stdout)
                self.assertIn(f"optimize {int(bool(flags))}", result.stdout)

    def test_cold_import_preserves_existing_modules(self):
        self.cold_import("module")

    def test_cold_import_keeps_absent_names_absent(self):
        self.cold_import("missing")

    def test_cold_import_preserves_explicit_none_entries(self):
        self.cold_import("none")

    def test_failed_import_restores_existing_modules(self):
        self.cold_import("module", fail=True)

    def test_failed_import_keeps_absent_names_absent(self):
        self.cold_import("missing", fail=True)

    def test_failed_import_preserves_explicit_none_entries(self):
        self.cold_import("none", fail=True)

    def test_binary_flag_requested_for_input_and_output_when_available(self):
        # This verifies flag construction, not execution on a Windows kernel.
        flag = 1 << 28
        with mock.patch.object(cli.os, "O_BINARY", flag, create=True):
            for operation in ("read", "write"):
                with self.subTest(operation=operation):
                    with mock.patch.object(cli.os, "open", side_effect=OSError(errno.EACCES, "injected")) as opened:
                        with self.assertRaises(core.EvidenceError):
                            if operation == "read":
                                cli.read_regular("unused-input", max_bytes=8, label="test")
                            else:
                                cli.write_exclusive("unused-output", b"x", label="test")
                    self.assertEqual(opened.call_args.args[1] & flag, flag)

    def test_short_writes_preserve_all_bytes(self):
        payload = b"a\r\nb\n\x1a\x00" * 41
        real_write = os.write
        calls = []

        def short_write(fd, data):
            calls.append(len(data))
            return real_write(fd, data[:3])

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.bin"
            with mock.patch.object(cli.os, "write", side_effect=short_write):
                cli.write_exclusive(str(dest), payload, label="short-write")
            self.assertEqual(dest.read_bytes(), payload)
        self.assertGreater(len(calls), 1)

    def test_zero_progress_write_closes_descriptor(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.bin"
            real_open = os.open
            fds = []

            def track_open(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                fds.append(fd)
                return fd

            with mock.patch.object(cli.os, "open", side_effect=track_open):
                with mock.patch.object(cli.os, "write", return_value=0):
                    with self.assertRaisesRegex(core.EvidenceError, "no progress"):
                        cli.write_exclusive(str(dest), b"data", label="zero-write")
            self.assertEqual(len(fds), 1)
            with self.assertRaises(OSError) as error:
                os.fstat(fds[0])
            self.assertEqual(error.exception.errno, errno.EBADF)

    def test_input_limit_is_inclusive_and_excess_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "in.bin"
            source.write_bytes(b"12345678")
            self.assertEqual(cli.read_regular(str(source), max_bytes=8, label="limit"), b"12345678")
            with self.assertRaisesRegex(core.EvidenceError, "exceeds"):
                cli.read_regular(str(source), max_bytes=7, label="limit")

    def test_input_read_error_closes_descriptor(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "in.bin"
            source.write_bytes(b"input")
            real_open = os.open
            fds = []

            def track_open(*args, **kwargs):
                fd = real_open(*args, **kwargs)
                fds.append(fd)
                return fd

            with mock.patch.object(cli.os, "open", side_effect=track_open):
                with mock.patch.object(cli.os, "read", side_effect=OSError(errno.EIO, "injected")):
                    with self.assertRaises(OSError):
                        cli.read_regular(str(source), max_bytes=8, label="read-failure")
            self.assertEqual(len(fds), 1)
            with self.assertRaises(OSError) as error:
                os.fstat(fds[0])
            self.assertEqual(error.exception.errno, errno.EBADF)


if __name__ == "__main__":
    unittest.main(verbosity=2)
