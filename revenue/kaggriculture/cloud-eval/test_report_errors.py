"""Preserve primary report errors while retaining secondary cleanup evidence.

Real temporary reports and injected filesystem failures; no game evaluation.
Run: python -B -m unittest -v test_report_errors
KAG_PROGRESS_EVALUATOR selects an exact baseline through test_progress.
"""
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_progress as support

ev = support.ev


class ReportErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "report.json"
        self.old = b'{"old":true}\n'
        self.output.write_bytes(self.old)

    def assert_primary_survives(self, stage, primary):
        cleanup = PermissionError("private cleanup detail")
        attempted = []
        unlink = Path.unlink
        factory = ev.tempfile.NamedTemporaryFile
        def fail_cleanup(path, *args, **kwargs):
            if path.parent == self.output.parent and path != self.output:
                attempted.append(path)
                raise cleanup
            return unlink(path, *args, **kwargs)
        @contextmanager
        def fail_write(*args, **kwargs):
            with factory(*args, **kwargs) as stream:
                class PartialWriter:
                    name = stream.name
                    def write(self, data):
                        stream.write(data[:7])
                        stream.flush()
                        raise primary
                yield PartialWriter()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(Path, "unlink", fail_cleanup))
            if stage == "write":
                stack.enter_context(mock.patch.object(ev.tempfile, "NamedTemporaryFile", side_effect=fail_write))
            else:
                stack.enter_context(mock.patch.object(ev.os, stage, side_effect=primary))
            with self.assertRaises(BaseException) as caught:
                ev.write_report(self.output, {"new": "fixture"})
        self.assertIs(caught.exception, primary)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(len(attempted), 1)
        self.assertTrue(attempted[0].is_file(), "failed cleanup must not be claimed successful")
        notes = getattr(primary, "__notes__", [])
        self.assertTrue(any("PermissionError" in n for n in notes))
        self.assertFalse(any("private cleanup detail" in n for n in notes))
        attempted[0].unlink()
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_sync_error_survives_cleanup_error(self):
        self.assert_primary_survives("fsync", OSError("original sync error"))

    def test_replace_error_survives_cleanup_error(self):
        self.assert_primary_survives("replace", FileExistsError("original replace error"))

    def test_partial_write_error_survives_cleanup_error(self):
        self.assert_primary_survives("write", OSError("original partial write error"))

    def test_keyboard_interrupt_is_not_converted_to_cleanup_error(self):
        self.assert_primary_survives("fsync", KeyboardInterrupt("original cancellation"))

    def test_system_exit_code_survives_cleanup_error(self):
        primary = SystemExit(23)
        self.assert_primary_survives("fsync", primary)
        self.assertEqual(primary.code, 23)

    def test_existing_cause_and_notes_are_retained(self):
        primary = RuntimeError("original replace failure")
        cause = ValueError("existing cause")
        primary.__cause__ = cause
        primary.add_note("existing note")
        self.assert_primary_survives("replace", primary)
        self.assertIs(primary.__cause__, cause)
        self.assertEqual(primary.__notes__[0], "existing note")
        self.assertEqual(len(primary.__notes__), 2)

    def test_cleanup_only_failure_still_raises_after_publication(self):
        cleanup = PermissionError("cleanup after successful replacement")
        unlink = Path.unlink
        def fail_cleanup(path, *args, **kwargs):
            if path.parent == self.output.parent and path != self.output:
                raise cleanup
            return unlink(path, *args, **kwargs)
        with mock.patch.object(Path, "unlink", fail_cleanup):
            with self.assertRaises(PermissionError) as caught:
                ev.write_report(self.output, {"new": True})
        self.assertIs(caught.exception, cleanup)
        self.assertEqual(json.loads(self.output.read_bytes()), {"new": True})
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_successful_cleanup_leaves_primary_exception_without_extra_note(self):
        primary = OSError("single sync error")
        with mock.patch.object(ev.os, "fsync", side_effect=primary):
            with self.assertRaises(OSError) as caught:
                ev.write_report(self.output, {"new": True})
        self.assertIs(caught.exception, primary)
        self.assertFalse(getattr(primary, "__notes__", []))
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])


if __name__ == "__main__":
    unittest.main(verbosity=2)
