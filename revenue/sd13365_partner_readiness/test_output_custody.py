from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import assemble_requirements
import matrix
import safe_output


_POSIX_DIRFD = (
    os.name == "posix"
    and isinstance(getattr(os, "O_DIRECTORY", None), int)
    and bool(getattr(os, "O_DIRECTORY", 0))
    and isinstance(getattr(os, "O_NOFOLLOW", None), int)
    and bool(getattr(os, "O_NOFOLLOW", 0))
    and hasattr(os, "symlink")
)


class OutputPrimitiveAvailabilityTests(unittest.TestCase):
    def test_missing_odirectory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "receipt.json"
            with mock.patch.object(safe_output.os, "O_DIRECTORY", None, create=True):
                with self.assertRaisesRegex(
                    safe_output.OutputCustodyError,
                    "platform lacks O_DIRECTORY",
                ):
                    safe_output.atomic_write_bytes(output, b"{}\n")
            self.assertFalse(output.exists())

    def test_missing_nofollow_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "receipt.json"
            with mock.patch.object(safe_output.os, "O_NOFOLLOW", None, create=True):
                with self.assertRaisesRegex(
                    safe_output.OutputCustodyError,
                    "platform lacks O_NOFOLLOW",
                ):
                    safe_output.atomic_write_bytes(output, b"{}\n")
            self.assertFalse(output.exists())


@unittest.skipUnless(_POSIX_DIRFD, "requires POSIX no-follow retained-dirfd output")
class OutputCustodyTests(unittest.TestCase):
    @staticmethod
    def _swap_parent_once(parent: Path, held: Path, attacker: Path):
        real_verify = safe_output._verify_parent_identity
        swapped = False

        def swap_then_verify(path: Path, expected: tuple[int, int]) -> None:
            nonlocal swapped
            if not swapped:
                os.rename(parent, held)
                attacker.mkdir()
                parent.symlink_to(attacker, target_is_directory=True)
                swapped = True
            real_verify(path, expected)

        return swap_then_verify

    @staticmethod
    def _swap_inside_replace(parent: Path, held: Path, attacker: Path):
        real_replace = safe_output.os.replace
        swapped = False

        def swap_then_replace(
            src: str,
            dst: str,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
        ) -> None:
            nonlocal swapped
            if not swapped:
                os.rename(parent, held)
                attacker.mkdir()
                parent.symlink_to(attacker, target_is_directory=True)
                swapped = True
            real_replace(
                src,
                dst,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )

        return swap_then_replace

    def test_missing_parent_is_never_created_by_authority_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "new-parent"
            output = missing / "receipt.json"
            with self.assertRaisesRegex(
                safe_output.OutputCustodyError,
                "does not already exist",
            ):
                safe_output.atomic_write_bytes(output, b'{"ok":true}\n')
            self.assertFalse(missing.exists())
            self.assertFalse(output.exists())

    def test_materializer_parent_swap_fails_closed_without_redirected_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "live"
            parent.mkdir()
            held = root / "held"
            attacker = root / "attacker"
            output = parent / "requirements.json"
            hook = self._swap_parent_once(parent, held, attacker)

            with mock.patch.object(safe_output, "_verify_parent_identity", side_effect=hook):
                with self.assertRaisesRegex(
                    assemble_requirements.AssemblyError,
                    "unsafe output custody",
                ):
                    assemble_requirements.write_atomic(output, b'{"reviewed":true}\n')

            self.assertFalse((attacker / output.name).exists())
            self.assertFalse((held / output.name).exists())
            self.assertEqual(list(held.glob(f".{output.name}.*.tmp")), [])

    def test_receipt_parent_swap_fails_closed_without_redirected_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "live"
            parent.mkdir()
            held = root / "held"
            attacker = root / "attacker"
            output = parent / "receipt.json"
            hook = self._swap_parent_once(parent, held, attacker)

            with mock.patch.object(safe_output, "_verify_parent_identity", side_effect=hook):
                with self.assertRaisesRegex(matrix.MatrixError, "unsafe receipt output custody"):
                    matrix.write_receipt(output, {"classification": "UNKNOWN"})

            self.assertFalse((attacker / output.name).exists())
            self.assertFalse((held / output.name).exists())
            self.assertEqual(list(held.glob(f".{output.name}.*.tmp")), [])

    def test_materializer_swap_after_precommit_fence_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "live"
            parent.mkdir()
            held = root / "held"
            attacker = root / "attacker"
            output = parent / "requirements.json"
            hook = self._swap_inside_replace(parent, held, attacker)
            payload = b'{"reviewed":true}\n'

            with mock.patch.object(safe_output.os, "replace", side_effect=hook):
                with self.assertRaisesRegex(
                    assemble_requirements.AssemblyError,
                    "unsafe output custody",
                ):
                    assemble_requirements.write_atomic(output, payload)

            self.assertFalse((attacker / output.name).exists())
            self.assertEqual((held / output.name).read_bytes(), payload)
            self.assertEqual(list(held.glob(f".{output.name}.*.tmp")), [])

    def test_receipt_swap_after_precommit_fence_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "live"
            parent.mkdir()
            held = root / "held"
            attacker = root / "attacker"
            output = parent / "receipt.json"
            hook = self._swap_inside_replace(parent, held, attacker)

            with mock.patch.object(safe_output.os, "replace", side_effect=hook):
                with self.assertRaisesRegex(matrix.MatrixError, "unsafe receipt output custody"):
                    matrix.write_receipt(output, {"classification": "UNKNOWN"})

            self.assertFalse((attacker / output.name).exists())
            self.assertTrue((held / output.name).is_file())
            self.assertEqual(list(held.glob(f".{output.name}.*.tmp")), [])

    def test_ancestor_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attacker = root / "attacker"
            attacker.mkdir()
            link = root / "link"
            link.symlink_to(attacker, target_is_directory=True)
            with self.assertRaisesRegex(
                safe_output.OutputCustodyError,
                "not a safe ordinary directory",
            ):
                safe_output.atomic_write_bytes(link / "nested" / "receipt.json", b"{}\n")
            self.assertFalse((attacker / "nested" / "receipt.json").exists())

    def test_safe_nested_output_commits_through_retained_dirfd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "a" / "b"
            parent.mkdir(parents=True)
            output = parent / "receipt.json"
            safe_output.atomic_write_bytes(output, b'{"ok":true}\n')
            self.assertEqual(output.read_bytes(), b'{"ok":true}\n')


if __name__ == "__main__":
    unittest.main()
