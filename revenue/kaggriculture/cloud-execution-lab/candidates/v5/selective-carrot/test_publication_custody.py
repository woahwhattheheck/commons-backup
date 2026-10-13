# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import publication_custody as pc


class PublicationCustodyTests(unittest.TestCase):
    def test_success_publishes_exact_pair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            archive = b'archive-prefix\x1aarchive-after-dos-eof\x00\xff\n'
            receipt = b'{"ok":true}\n'
            pc.publish_exclusive([(a, archive), (b, receipt)])
            self.assertEqual(a.read_bytes(), archive)
            self.assertEqual(b.read_bytes(), receipt)

    def test_success_publishes_paths_beyond_windows_max_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / ('component-' + 'x' * 120)
            a = root / ('a' * 120 + '.bin')
            b = root / ('b' * 120 + '.json')
            self.assertGreater(len(str(a.resolve(strict=False))), 260)
            pc.publish_exclusive([(a, b'A\x1aB'), (b, b'{}\n')])
            observed = []
            for path in (a, b):
                fd = os.open(
                    pc._os_path(path),
                    os.O_RDONLY | getattr(os, 'O_BINARY', 0),
                )
                try:
                    observed.append(os.read(fd, 1024))
                finally:
                    os.close(fd)
            self.assertEqual(observed, [b'A\x1aB', b'{}\n'])
            # Standard-library TemporaryDirectory cleanup on Windows cannot
            # address the long final names, so remove those exact paths first.
            for path in (a, b):
                os.unlink(pc._os_path(path))

    def test_alias_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root/'candidate'
            with self.assertRaises(ValueError):
                pc.publish_exclusive([(a, b'a'), (root/'.'/'candidate', b'b')])
            self.assertFalse(a.exists())

    def test_preexisting_second_path_rolls_back_first_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            b.write_bytes(b'sentinel')
            with self.assertRaises(FileExistsError):
                pc.publish_exclusive([(a, b'archive'), (b, b'receipt')])
            self.assertFalse(a.exists())
            self.assertEqual(b.read_bytes(), b'sentinel')

    def test_second_write_failure_rolls_back_both(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            original = pc._write_all
            calls = 0

            def fail_second(fd, payload):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('injected second write failure')
                return original(fd, payload)

            with mock.patch.object(pc, '_write_all', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'injected'):
                    pc.publish_exclusive([(a, b'archive'), (b, b'receipt')])
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())

    def test_rollback_identity_checks_keep_reservation_fds_live(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            original_write = pc._write_all
            original_unlink = pc._unlink_if_owned
            writes = 0
            rollback_fd_live = []

            def fail_second(fd, payload):
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError('injected second write failure')
                return original_write(fd, payload)

            def inspect_live_fd(item):
                try:
                    os.fstat(item.fd)
                except OSError:
                    rollback_fd_live.append(False)
                else:
                    rollback_fd_live.append(True)
                return original_unlink(item)

            with mock.patch.object(pc, '_write_all', side_effect=fail_second), \
                    mock.patch.object(pc, '_unlink_if_owned', side_effect=inspect_live_fd):
                with self.assertRaisesRegex(OSError, 'injected'):
                    pc.publish_exclusive([(a, b'archive'), (b, b'receipt')])
            self.assertEqual(
                rollback_fd_live,
                [False, False] if os.name == 'nt' else [True, True],
            )
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())

    def test_cleanup_error_does_not_mask_publication_error_or_leak_fds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            original_write = pc._write_all
            writes = 0
            seen_fds = []

            def fail_second(fd, payload):
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError('authoritative publication failure')
                return original_write(fd, payload)

            def fail_cleanup(item):
                seen_fds.append(item.fd)
                os.fstat(item.fd)
                raise PermissionError('injected cleanup failure')

            with mock.patch.object(pc, '_write_all', side_effect=fail_second), \
                    mock.patch.object(pc, '_unlink_if_owned', side_effect=fail_cleanup):
                with self.assertRaisesRegex(OSError, 'authoritative publication failure'):
                    pc.publish_exclusive([(a, b'archive'), (b, b'receipt')])
            self.assertEqual(len(seen_fds), 2)
            for fd in seen_fds:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_foreign_replacement_before_verify_is_detected_and_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root/'candidate.tar.gz', root/'candidate.json'
            original = pc._verify_final
            calls = 0

            def replace_before_verify(item):
                nonlocal calls
                calls += 1
                if calls == 1:
                    if os.name == 'nt':
                        # Windows normally locks an open reservation against
                        # replacement. Close it to inject the foreign-path case.
                        os.close(item.fd)
                    item.path.unlink()
                    item.path.write_bytes(b'foreign')
                return original(item)

            with mock.patch.object(pc, '_verify_final', side_effect=replace_before_verify):
                with self.assertRaisesRegex(OSError, 'identity changed'):
                    pc.publish_exclusive([(a, b'archive'), (b, b'receipt')])
            self.assertEqual(a.read_bytes(), b'foreign')
            self.assertFalse(b.exists())

    def test_single_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td)/'one'
            with self.assertRaises(ValueError):
                pc.publish_exclusive([(a, b'x')])
            self.assertFalse(a.exists())


if __name__ == '__main__':
    unittest.main()
