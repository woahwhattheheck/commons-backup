from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import revenue.multi_framework_evidence_freshness.gate as gate_module
from revenue.multi_framework_evidence_freshness import load_strict_json
from revenue.multi_framework_evidence_freshness.cli import _write_new_set
from revenue.multi_framework_evidence_freshness.gate import GateError
import revenue.multi_framework_evidence_freshness.cli as cli_module


class FreshnessCustodyRecoveryTests(unittest.TestCase):
    def test_same_inode_rewrite_with_restored_mtime_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "input.json"
            original_bytes = b'{"x":1}\n'
            replacement_bytes = b'{"x":2}\n'
            self.assertEqual(len(original_bytes), len(replacement_bytes))
            path.write_bytes(original_bytes)
            before = path.stat()
            inode_before = (before.st_dev, before.st_ino)

            real_read = os.read
            mutated = False

            def hostile_read(fd: int, amount: int) -> bytes:
                nonlocal mutated
                chunk = real_read(fd, amount)
                if chunk and not mutated:
                    mutated = True
                    with path.open("r+b", buffering=0) as handle:
                        handle.seek(0)
                        handle.write(replacement_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    # Reproduce the predecessor bypass attempt: same inode,
                    # same length, and the original mtime restored.
                    os.utime(path, ns=(path.stat().st_atime_ns, before.st_mtime_ns))
                    after_mutation = path.stat()
                    self.assertEqual(inode_before, (after_mutation.st_dev, after_mutation.st_ino))
                    self.assertEqual(before.st_size, after_mutation.st_size)
                    self.assertEqual(before.st_mtime_ns, after_mutation.st_mtime_ns)
                return chunk

            with mock.patch.object(gate_module.os, "read", side_effect=hostile_read):
                with self.assertRaisesRegex(GateError, "input_changed_during_read"):
                    load_strict_json(path)
            self.assertTrue(mutated)

    @unittest.skipIf(os.name == "nt", "open-file rename semantics differ on Windows")
    def test_first_output_substitution_during_second_publication_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            packet_path = root / "packet.json"
            markdown_path = root / "review.md"
            captured_original = root / "packet.original"
            packet_bytes = b'{"packet":"original"}\n'
            markdown_bytes = b"# review\n"
            real_write_all = cli_module._write_all
            calls = 0

            def hostile_write_all(fd: int, data: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    # First artifact has been written but its fd is still
                    # retained. Substitute its visible basename while the
                    # second artifact is being published.
                    os.replace(packet_path, captured_original)
                    packet_path.write_bytes(b"X" * len(packet_bytes))
                real_write_all(fd, data)

            with mock.patch.object(cli_module, "_write_all", side_effect=hostile_write_all):
                with self.assertRaisesRegex(GateError, "output_final_replaced"):
                    _write_new_set(
                        [(packet_path, packet_bytes), (markdown_path, markdown_bytes)]
                    )

            self.assertEqual(calls, 2)
            self.assertEqual(captured_original.read_bytes(), packet_bytes)
            self.assertEqual(packet_path.read_bytes(), b"X" * len(packet_bytes))
            self.assertEqual(markdown_path.read_bytes(), markdown_bytes)

    @unittest.skipIf(os.name == "nt", "open-file rename semantics differ on Windows")
    def test_substitution_on_directory_fsync_boundary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            packet_path = root / "packet.json"
            markdown_path = root / "review.md"
            captured_original = root / "packet.original"
            packet_bytes = b'{"packet":"original"}\n'
            markdown_bytes = b"# review\n"
            real_fsync = os.fsync
            dir_fsyncs = 0
            mutated = False

            def hostile_fsync(fd: int) -> None:
                nonlocal dir_fsyncs, mutated
                mode = os.fstat(fd).st_mode
                if stat.S_ISDIR(mode):
                    dir_fsyncs += 1
                    if dir_fsyncs == 1 and not mutated:
                        mutated = True
                        os.replace(packet_path, captured_original)
                        packet_path.write_bytes(b"X" * len(packet_bytes))
                return real_fsync(fd)

            with mock.patch.object(cli_module.os, "fsync", side_effect=hostile_fsync):
                with self.assertRaisesRegex(GateError, "output_final_replaced"):
                    _write_new_set(
                        [(packet_path, packet_bytes), (markdown_path, markdown_bytes)]
                    )

            self.assertTrue(mutated)
            self.assertGreaterEqual(dir_fsyncs, 1)
            self.assertEqual(captured_original.read_bytes(), packet_bytes)
            self.assertEqual(packet_path.read_bytes(), b"X" * len(packet_bytes))
            self.assertEqual(markdown_path.read_bytes(), markdown_bytes)

    def test_duplicate_final_targets_rejected_before_create(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            same = root / "same.json"
            payload_a = b'{"a":1}\n'
            payload_b = b'{"b":2}\n'
            with self.assertRaisesRegex(GateError, "output_duplicate_target"):
                _write_new_set([(same, payload_a), (same, payload_b)])
            self.assertFalse(same.exists())


if __name__ == "__main__":
    unittest.main()
