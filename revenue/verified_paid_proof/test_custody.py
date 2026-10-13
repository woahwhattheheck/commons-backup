import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.verified_paid_proof import compiler, custody
from revenue.verified_paid_proof.core import ProofError
from revenue.verified_paid_proof.test_verified_paid_proof import base_record


class DescriptorCustodyTests(unittest.TestCase):
    def test_public_compiler_facade_uses_descriptor_bound_writer(self):
        self.assertIs(compiler.write_outputs, custody.write_outputs)

    def test_rejects_group_or_other_writable_nonsticky_parent(self):
        compiled = compiler.compile_proof(base_record())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o700)
            unsafe.chmod(0o777)
            try:
                with self.assertRaises(ProofError):
                    compiler.write_outputs(
                        compiled,
                        unsafe / "internal",
                        unsafe / "public",
                    )
            finally:
                unsafe.chmod(0o700)

    def test_partial_write_rolls_back_both_bound_directories(self):
        compiled = compiler.compile_proof(base_record())
        real_write = custody._write_new_text
        calls = 0

        def fail_second(bound, name, text):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic write failure")
            return real_write(bound, name, text)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = root / "internal"
            public = root / "public"
            with mock.patch.object(custody, "_write_new_text", side_effect=fail_second):
                with self.assertRaises(OSError):
                    compiler.write_outputs(compiled, internal, public)
            self.assertFalse(internal.exists())
            self.assertFalse(public.exists())

    def test_mid_write_fsync_failure_removes_partial_file_and_directories(self):
        compiled = compiler.compile_proof(base_record())
        real_fsync = custody.os.fsync
        failed = False

        def fail_first_regular_file(fd):
            nonlocal failed
            mode = os.fstat(fd).st_mode
            if not failed and not __import__("stat").S_ISDIR(mode):
                failed = True
                raise OSError("synthetic file fsync failure")
            return real_fsync(fd)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = root / "internal"
            public = root / "public"
            with mock.patch.object(custody.os, "fsync", side_effect=fail_first_regular_file):
                with self.assertRaises(OSError):
                    compiler.write_outputs(compiled, internal, public)
            self.assertTrue(failed)
            self.assertFalse(internal.exists())
            self.assertFalse(public.exists())

    def test_leaf_substitution_is_detected_and_foreign_successor_survives(self):
        compiled = compiler.compile_proof(base_record())
        real_verify = custody._verify_file_bindings
        attacked = False

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = root / "internal"
            public = root / "public"
            moved = internal / "owned-proof-moved.json"
            foreign = b"foreign-successor-must-survive\n"

            def replace_before_final_file_check(bound):
                nonlocal attacked
                if bound.path == internal and not attacked:
                    attacked = True
                    os.rename(internal / "proof.json", moved)
                    (internal / "proof.json").write_bytes(foreign)
                return real_verify(bound)

            with mock.patch.object(
                custody,
                "_verify_file_bindings",
                side_effect=replace_before_final_file_check,
            ):
                with self.assertRaises(ProofError):
                    compiler.write_outputs(compiled, internal, public)

            self.assertTrue(attacked)
            self.assertEqual((internal / "proof.json").read_bytes(), foreign)
            self.assertFalse(moved.exists())
            self.assertFalse(public.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_path_replacement_after_durability_is_detected(self):
        compiled = compiler.compile_proof(base_record())
        real_verify = custody._verify_dir_binding
        attacked = False

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = root / "internal"
            public = root / "public"
            moved = root / "public-moved"
            redirect = root / "redirect"
            redirect.mkdir()

            def replace_before_final_check(bound):
                nonlocal attacked
                if bound.path == public and not attacked:
                    attacked = True
                    os.rename(public, moved)
                    os.symlink(redirect, public, target_is_directory=True)
                return real_verify(bound)

            with mock.patch.object(
                custody,
                "_verify_dir_binding",
                side_effect=replace_before_final_check,
            ):
                with self.assertRaises(ProofError):
                    compiler.write_outputs(compiled, internal, public)

            self.assertTrue(attacked)
            self.assertTrue(public.is_symlink())
            self.assertEqual(list(redirect.iterdir()), [])
            self.assertTrue(moved.is_dir())
            self.assertEqual(list(moved.iterdir()), [])
            self.assertFalse(internal.exists())


if __name__ == "__main__":
    unittest.main()
