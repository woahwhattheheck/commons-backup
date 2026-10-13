import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rights_export as e
import rights_ops as r
from test_rights_ops import manifest


@unittest.skipUnless(e._secure_export_supported(), "secure descriptor-relative export unsupported")
class ExportCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "desk.sqlite3"
        r.import_manifest(self.db, manifest(), "2026-09-15T06:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_intermediate_symlink_component_is_refused_without_writes(self):
        real_parent = self.root / "real-parent"
        target = real_parent / "bundle"
        target.mkdir(parents=True)
        alias = self.root / "alias-parent"
        try:
            os.symlink(real_parent, alias, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink unavailable")

        with self.assertRaisesRegex(r.RightsError, "real directory"):
            r.publish_export(self.db, alias / "bundle", "2026-12-10T00:00:00Z")

        self.assertEqual(list(target.iterdir()), [])

    def test_failure_never_unlinks_foreign_leaf_successor(self):
        out = self.root / "bundle"
        out.mkdir(mode=0o700)
        orphan = self.root / "owned-orphan"
        real_write = e.os.write
        fired = False
        successor_name = None

        def racing_write(fd, data):
            nonlocal fired, successor_name
            n = real_write(fd, data)
            if not fired:
                visible = list(out.iterdir())
                self.assertEqual(len(visible), 1)
                owned = visible[0]
                successor_name = owned.name
                os.rename(owned, orphan)
                owned.write_bytes(b"foreign-successor")
                fired = True
                raise OSError("injected post-substitution failure")
            return n

        with mock.patch.object(e.os, "unlink") as unlink, mock.patch.object(e.os, "write", side_effect=racing_write):
            with self.assertRaisesRegex(OSError, "post-substitution"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")

        self.assertTrue(fired)
        unlink.assert_not_called()
        self.assertIsNotNone(successor_name)
        self.assertEqual((out / successor_name).read_bytes(), b"foreign-successor")
        self.assertTrue(orphan.is_file())
        self.assertEqual(orphan.stat().st_size, 0)

    def test_leaf_fstat_failure_closes_descriptor_without_unlink(self):
        out = self.root / "bundle"
        out.mkdir(mode=0o700)
        real_fstat = e.os.fstat
        captured_fd = None
        fired = False
        proc_fd = Path("/proc/self/fd")
        fd_count_before = len(list(proc_fd.iterdir())) if proc_fd.is_dir() else None

        def failing_leaf_fstat(fd):
            nonlocal captured_fd, fired
            current = real_fstat(fd)
            if not fired and stat.S_ISREG(current.st_mode):
                fired = True
                captured_fd = fd
                raise OSError("injected leaf fstat failure")
            return current

        with mock.patch.object(e.os, "unlink") as unlink, mock.patch.object(
            e.os, "fstat", side_effect=failing_leaf_fstat
        ):
            with self.assertRaisesRegex(OSError, "leaf fstat failure"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")

        self.assertTrue(fired)
        self.assertIsNotNone(captured_fd)
        unlink.assert_not_called()
        with self.assertRaises(OSError) as closed:
            os.fstat(captured_fd)
        self.assertEqual(closed.exception.errno, errno.EBADF)
        visible = list(out.iterdir())
        self.assertEqual(len(visible), 1)
        self.assertTrue(visible[0].is_file())
        self.assertEqual(visible[0].stat().st_size, 0)
        if fd_count_before is not None:
            self.assertLessEqual(len(list(proc_fd.iterdir())), fd_count_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
