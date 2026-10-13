#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compiler  # noqa: E402
import workshare_read  # noqa: E402
import workshare_write  # noqa: E402


class FilesystemCustodyTests(unittest.TestCase):
    def test_input_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.json"
            link = root / "link.json"
            real.write_text('{"x":1}\n', encoding="utf-8")
            link.symlink_to(real)
            with self.assertRaisesRegex(compiler.ContractError, "cannot open input safely"):
                compiler._load_file(link)

    def test_same_inode_mutation_during_read_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "packet.json"
            path.write_bytes(b'{"x":1}\n')
            before = path.stat()
            original_read = os.read
            mutated = False

            def racing_read(fd: int, size: int) -> bytes:
                nonlocal mutated
                chunk = original_read(fd, size)
                if chunk and not mutated:
                    mutated = True
                    with path.open("r+b") as handle:
                        handle.write(b'{"x":2}\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                return chunk

            with mock.patch.object(workshare_read.os, "read", side_effect=racing_read):
                with self.assertRaisesRegex(compiler.ContractError, "generation changed"):
                    compiler._read_bounded_regular(path)

    def test_path_replacement_does_not_change_open_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "packet.json"
            displaced = root / "opened-generation.json"
            original = b'{"generation":"opened"}\n'
            foreign = b'{"generation":"foreign"}\n'
            path.write_bytes(original)
            original_read = os.read
            replaced = False

            def racing_read(fd: int, size: int) -> bytes:
                nonlocal replaced
                chunk = original_read(fd, size)
                if chunk and not replaced:
                    replaced = True
                    path.rename(displaced)
                    path.write_bytes(foreign)
                return chunk

            with mock.patch.object(workshare_read.os, "read", side_effect=racing_read):
                with self.assertRaisesRegex(compiler.ContractError, "generation changed"):
                    compiler._read_bounded_regular(path)
            self.assertEqual(path.read_bytes(), foreign)
            self.assertEqual(displaced.read_bytes(), original)

    def test_output_symlinked_parent_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(compiler.ContractError, "output parent component"):
                compiler._write_exclusive(link / "report.json", b"x")
            self.assertFalse((real / "report.json").exists())

    def test_existing_output_and_output_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "report.json"
            out.write_bytes(b"owned")
            with self.assertRaisesRegex(compiler.ContractError, "refusing existing"):
                compiler._write_exclusive(out, b"new")
            out.unlink()
            target = root / "target.json"
            target.write_bytes(b"target")
            out.symlink_to(target)
            with self.assertRaisesRegex(compiler.ContractError, "refusing existing"):
                compiler._write_exclusive(out, b"new")
            self.assertEqual(target.read_bytes(), b"target")

    def test_foreign_output_replacement_is_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "report.json"
            displaced = root / "created-generation.json"
            original_fsync = os.fsync
            replaced = False

            def racing_fsync(fd: int) -> None:
                nonlocal replaced
                original_fsync(fd)
                if not replaced:
                    replaced = True
                    out.rename(displaced)
                    out.write_bytes(b"FOREIGN")

            with mock.patch.object(workshare_write.os, "fsync", side_effect=racing_fsync):
                with self.assertRaisesRegex(compiler.ContractError, "no longer names created generation"):
                    compiler._write_exclusive(out, b"OURS")
            self.assertEqual(out.read_bytes(), b"FOREIGN")
            self.assertEqual(displaced.read_bytes(), b"OURS")

    def test_cli_refuses_clock_injection_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            authority = root / "authority.json"
            output = root / "report.json"
            candidate.write_bytes((HERE / "fixtures" / "synthetic_packet.json").read_bytes())
            authority.write_bytes((HERE / "fixtures" / "synthetic_authority.json").read_bytes())
            injected = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "compiler.py"),
                    "compile",
                    str(candidate),
                    str(authority),
                    str(output),
                    "--now",
                    "2020-01-01T00:00:00Z",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(injected.returncode, 2)
            self.assertFalse(output.exists())
            first = subprocess.run(
                [sys.executable, str(HERE / "compiler.py"), "compile", str(candidate), str(authority), str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("HOLD_TRUSTED_AUTHORITY_REQUIRED", first.stdout)
            second = subprocess.run(
                [sys.executable, str(HERE / "compiler.py"), "compile", str(candidate), str(authority), str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(second.returncode, 2)
            self.assertIn("refusing existing output path", second.stderr)

