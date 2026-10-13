from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.swarmops_dossier.cli import MAX_INPUT, read_regular
from revenue.swarmops_dossier.engine import DossierError


class CliIngressCustodyTests(unittest.TestCase):
    def test_stable_regular_file_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "stable.json")
            path.write_text('{"stable":true}\n', encoding="utf-8")
            self.assertEqual('{"stable":true}\n', read_regular(str(path)))

    def test_final_symlink_is_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td, "target.json")
            link = Path(td, "link.json")
            target.write_text("{}", encoding="utf-8")
            os.symlink(target, link)
            with self.assertRaises((DossierError, OSError)):
                read_regular(str(link))

    def test_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(DossierError, "not a regular input file"):
                read_regular(td)

    def test_fifo_is_rejected_without_opening(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO unavailable")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "pipe")
            os.mkfifo(path)
            with mock.patch("revenue.swarmops_dossier.cli.os.open", side_effect=AssertionError("FIFO must not be opened")):
                with self.assertRaisesRegex(DossierError, "not a regular input file"):
                    read_regular(str(path))

    def test_device_is_rejected_without_opening(self):
        path = Path("/dev/null")
        if not path.exists():
            self.skipTest("safe device fixture unavailable")
        with mock.patch("revenue.swarmops_dossier.cli.os.open", side_effect=AssertionError("device must not be opened")):
            with self.assertRaisesRegex(DossierError, "not a regular input file"):
                read_regular(str(path))

    def test_same_size_replacement_between_lstat_and_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "input.json")
            replacement = Path(td, "replacement.json")
            path.write_bytes(b"AAAA")
            replacement.write_bytes(b"BBBB")
            real_open = os.open

            def replace_then_open(target, flags, *args, **kwargs):
                os.replace(replacement, path)
                return real_open(target, flags, *args, **kwargs)

            with mock.patch("revenue.swarmops_dossier.cli.os.open", side_effect=replace_then_open):
                with self.assertRaisesRegex(DossierError, "changed before open"):
                    read_regular(str(path))

    def test_same_size_mutation_during_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "input.bin")
            path.write_bytes(b"A" * (128 * 1024))
            real_read = os.read
            mutated = False

            def mutate_after_first_read(fd, count):
                nonlocal mutated
                chunk = real_read(fd, count)
                if chunk and not mutated:
                    mutated = True
                    with path.open("r+b", buffering=0) as handle:
                        handle.seek(96 * 1024)
                        handle.write(b"B" * 4096)
                    stat_now = path.stat()
                    os.utime(path, ns=(stat_now.st_atime_ns, stat_now.st_mtime_ns + 1_000_000))
                return chunk

            with mock.patch("revenue.swarmops_dossier.cli.os.read", side_effect=mutate_after_first_read):
                with self.assertRaisesRegex(DossierError, "changed during read"):
                    read_regular(str(path))

    def test_oversized_initial_file_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "large.bin")
            with path.open("wb") as handle:
                handle.truncate(MAX_INPUT + 1)
            with mock.patch("revenue.swarmops_dossier.cli.os.open", side_effect=AssertionError("oversized file must not be opened")):
                with self.assertRaisesRegex(DossierError, "input too large"):
                    read_regular(str(path))

    def test_growth_past_max_during_read_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "growing.bin")
            path.write_bytes(b"A" * (128 * 1024))
            real_read = os.read
            grown = False

            def grow_after_first_read(fd, count):
                nonlocal grown
                chunk = real_read(fd, count)
                if chunk and not grown:
                    grown = True
                    with path.open("ab", buffering=0) as handle:
                        handle.write(b"G" * MAX_INPUT)
                return chunk

            with mock.patch("revenue.swarmops_dossier.cli.os.read", side_effect=grow_after_first_read):
                with self.assertRaisesRegex(DossierError, "input too large|changed during read"):
                    read_regular(str(path))


if __name__ == "__main__":
    unittest.main()
