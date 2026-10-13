# SPDX-License-Identifier: Apache-2.0
"""Offline transport tests; synthetic tar fixtures are not gameplay evidence."""
import contextlib
import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import verify_fast_clone as runner


class PackageTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'package.tar.gz'
        self.member = 'package/r01_tapes.py'
        # A module that raises on import demonstrates data-only fixture reading.
        self.payload = b'raise RuntimeError("fixture code must not execute")\n'

    def archive(self, entries=None, *, expected_payload=None):
        if entries is None:
            entries = [(self.member, self.payload, 'file')]
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w:gz') as archive:
            for name, content, kind in entries:
                info = tarfile.TarInfo(name)
                if kind == 'file':
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
                else:
                    info.type = tarfile.SYMTYPE
                    info.linkname = 'elsewhere'
                    archive.addfile(info)
        data = raw.getvalue()
        self.path.write_bytes(data)
        expected = self.payload if expected_payload is None else expected_payload
        metadata = {'file_id': 'SYNTHETIC-UNIT-FIXTURE', 'byte_count': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(), 'member': self.member,
                    'member_bytes': len(expected)}
        self.enterContext(mock.patch.dict(runner.SLACK_PACKAGE, metadata, clear=True))
        self.enterContext(mock.patch.dict(runner.PINS, {'r01_tapes.py': runner.git_blob(expected)}))
        return data

    def reject_args(self, *args):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            runner.main(list(args))
        self.assertEqual(error.exception.code, 2)

    def test_read_member_as_data_without_import_or_extraction(self):
        self.archive([(self.member, self.payload, 'file'),
                      ('unrelated.py', b'raise RuntimeError()', 'file')])
        before = sorted(p.name for p in self.path.parent.iterdir())
        with (mock.patch.object(tarfile.TarFile, 'extract', side_effect=AssertionError('extract called')),
              mock.patch.object(tarfile.TarFile, 'extractall', side_effect=AssertionError('extractall called'))):
            self.assertEqual(runner.tape_from_slack_package(self.path), self.payload)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), before)

    def test_truncated_package_rejected_before_tar(self):
        data = self.archive()
        self.path.write_bytes(data[:-1])
        with mock.patch.object(runner.tarfile, 'open') as opened, self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)
        opened.assert_not_called()

    def test_same_size_drift_rejected_before_tar(self):
        data = bytearray(self.archive()); data[-1] ^= 1
        self.path.write_bytes(data)
        with mock.patch.object(runner.tarfile, 'open') as opened, self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)
        opened.assert_not_called()

    def test_appended_package_rejected_before_tar(self):
        self.path.write_bytes(self.archive() + b'extra')
        with mock.patch.object(runner.tarfile, 'open') as opened, self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)
        opened.assert_not_called()

    def test_absent_named_member_rejected(self):
        self.archive([('unrelated.py', self.payload, 'file')])
        with self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)

    def test_duplicate_named_member_rejected(self):
        self.archive([(self.member, self.payload, 'file')] * 2)
        with self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)

    def test_nonregular_named_member_rejected(self):
        self.archive([(self.member, b'', 'symlink')], expected_payload=b'')
        with self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)

    def test_wrong_member_size_rejected(self):
        self.archive([(self.member, self.payload + b'#extra', 'file')])
        with self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)

    def test_wrong_member_digest_rejected(self):
        payload = bytearray(self.payload); payload[-2] ^= 1
        self.archive([(self.member, bytes(payload), 'file')])
        with self.assertRaises(ValueError):
            runner.tape_from_slack_package(self.path)

    def test_missing_package_propagates_io_error(self):
        with self.assertRaises(FileNotFoundError):
            runner.tape_from_slack_package(self.path)

    def test_package_and_tapes_options_are_exclusive(self):
        self.reject_args('--slack-package', str(self.path), '--tapes', 'tape.py')

    def test_generated_only_cannot_silently_ignore_package(self):
        self.reject_args('--generated-only', '--slack-package', str(self.path))

    def test_legacy_still_requires_both_historical_inputs(self):
        self.reject_args('--legacy-port', '--slack-package', str(self.path))

    def test_package_does_not_implicitly_select_legacy_port(self):
        self.reject_args('--slack-package', str(self.path), '--parent-apply', 'apply.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
