from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.exact_byte_artifact_set.publisher import (
    PartialPublicationError,
    PublicationError,
    publish_artifact_set,
)


class PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="exact-byte-set-"))
        self.out = self.tmp / "out"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_success_receipt_and_modes(self) -> None:
        receipt = publish_artifact_set(
            self.out, {"b.json": b"{\"b\":2}\n", "a.txt": b"alpha\n"}
        )
        self.assertTrue(receipt["publication_committed"])
        self.assertEqual(receipt["linearization"], "RENAME_NOREPLACE_DIRECTORY_GENERATION")
        self.assertFalse(receipt["post_commit_stability_proven"])
        self.assertEqual([r["name"] for r in receipt["artifacts"]], ["a.txt", "b.json"])
        self.assertEqual((self.out / "a.txt").read_bytes(), b"alpha\n")
        self.assertEqual((self.out / "b.json").read_bytes(), b"{\"b\":2}\n")
        self.assertEqual((self.out / "a.txt").stat().st_mode & 0o777, 0o600)

    def test_receipt_order_invariant(self) -> None:
        first = self.tmp / "first"
        second = self.tmp / "second"
        a = publish_artifact_set(first, {"x": b"1", "y": b"2"})
        b = publish_artifact_set(second, {"y": b"2", "x": b"1"})
        self.assertEqual(a, b)

    def test_existing_target_directory_is_never_replaced(self) -> None:
        self.out.mkdir()
        marker = self.out / "sentinel"
        marker.write_bytes(b"foreign")
        before = sorted(p.name for p in self.tmp.iterdir())
        with self.assertRaises(FileExistsError):
            publish_artifact_set(self.out, {"x": b"owned"})
        self.assertEqual(marker.read_bytes(), b"foreign")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), before)

    def test_existing_target_file_and_symlink_are_refused(self) -> None:
        self.out.write_bytes(b"foreign")
        with self.assertRaises(FileExistsError):
            publish_artifact_set(self.out, {"x": b"owned"})
        self.out.unlink()
        target = self.tmp / "foreign"
        target.mkdir()
        self.out.symlink_to(target, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            publish_artifact_set(self.out, {"x": b"owned"})
        self.assertFalse((target / "x").exists())

    def test_unsafe_artifact_names_rejected(self) -> None:
        for bad in ("../x", "a/b", ".", "..", "", "\\evil"):
            with self.subTest(bad=bad), self.assertRaises(PublicationError):
                publish_artifact_set(self.out, {bad: b"x"})
            self.assertFalse(self.out.exists())

    def test_lexical_parent_traversal_is_rejected_before_normalization(self) -> None:
        lexical_parent = self.tmp / "scope"
        lexical_parent.mkdir()
        escaped_parent = self.tmp / "escaped"
        escaped_parent.mkdir()
        output = lexical_parent / ".." / "escaped" / "out"
        with self.assertRaises(PublicationError):
            publish_artifact_set(output, {"x": b"owned"})
        self.assertFalse((escaped_parent / "out").exists())
        self.assertEqual(list(escaped_parent.iterdir()), [])

    def test_symlink_ancestor_rejected(self) -> None:
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises((PublicationError, OSError)):
            publish_artifact_set(link / "out", {"x": b"x"})
        self.assertFalse((real / "out").exists())

    def test_short_write_is_drained(self) -> None:
        original = os.write

        def short(fd, data):
            if len(data) > 1:
                return original(fd, data[: max(1, len(data) // 2)])
            return original(fd, data)

        with mock.patch("tools.exact_byte_artifact_set.publisher.os.write", side_effect=short):
            publish_artifact_set(self.out, {"x": b"abcdefghijk"})
        self.assertEqual((self.out / "x").read_bytes(), b"abcdefghijk")

    def test_partial_write_failure_preserves_staging_evidence(self) -> None:
        original = os.write
        calls = 0

        def fail_after_fragment(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original(fd, data[:1])
            raise OSError("injected write failure")

        with mock.patch("tools.exact_byte_artifact_set.publisher.os.write", side_effect=fail_after_fragment):
            with self.assertRaises(PartialPublicationError) as caught:
                publish_artifact_set(self.out, {"x": b"abcdef"})
        err = caught.exception
        self.assertFalse(err.publication_committed)
        self.assertEqual(err.created_leaves, ("x",))
        self.assertFalse(self.out.exists())
        stage = self.tmp / err.staging_name
        self.assertTrue(stage.is_dir())
        self.assertEqual((stage / "x").read_bytes(), b"a")

    def test_stage_open_failure_preserves_and_identifies_staging_evidence(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        original = os.open

        def fail_stage_open(path, flags, mode=0o777, *, dir_fd=None):
            if isinstance(path, str) and path.startswith(".exact-byte-stage-"):
                raise OSError("injected stage open failure")
            return original(path, flags, mode, dir_fd=dir_fd)

        with (
            mock.patch.object(
                publisher,
                "_required_platform_flags",
                return_value=(os.O_DIRECTORY, os.O_NOFOLLOW),
            ),
            mock.patch.object(publisher.os, "open", side_effect=fail_stage_open),
        ):
            with self.assertRaises(PartialPublicationError) as caught:
                publish_artifact_set(self.out, {"x": b"owned"})
        err = caught.exception
        self.assertFalse(err.publication_committed)
        self.assertEqual(err.created_leaves, ())
        self.assertFalse(self.out.exists())
        self.assertTrue((self.tmp / err.staging_name).is_dir())

    def test_target_namespace_is_absent_until_one_directory_commit(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        original = publisher._rename_noreplace
        observed = 0

        def observe_commit(src_dir_fd, src_name, dst_dir_fd, dst_name):
            nonlocal observed
            observed += 1
            self.assertFalse(self.out.exists())
            stage = self.tmp / src_name
            self.assertEqual((stage / "a").read_bytes(), b"owned-a")
            self.assertEqual((stage / "b").read_bytes(), b"owned-b")
            original(src_dir_fd, src_name, dst_dir_fd, dst_name)
            self.assertTrue(self.out.is_dir())
            self.assertEqual((self.out / "a").read_bytes(), b"owned-a")
            self.assertEqual((self.out / "b").read_bytes(), b"owned-b")

        with mock.patch.object(publisher, "_rename_noreplace", side_effect=observe_commit):
            publish_artifact_set(self.out, {"a": b"owned-a", "b": b"owned-b"})
        self.assertEqual(observed, 1)

    def test_destination_race_at_commit_cannot_clobber_foreign_generation(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        original = publisher._rename_noreplace

        def race(src_dir_fd, src_name, dst_dir_fd, dst_name):
            self.out.mkdir()
            (self.out / "sentinel").write_bytes(b"foreign")
            return original(src_dir_fd, src_name, dst_dir_fd, dst_name)

        with mock.patch.object(publisher, "_rename_noreplace", side_effect=race):
            with self.assertRaises(PartialPublicationError) as caught:
                publish_artifact_set(self.out, {"a": b"owned"})
        self.assertFalse(caught.exception.publication_committed)
        self.assertEqual((self.out / "sentinel").read_bytes(), b"foreign")
        self.assertFalse((self.out / "a").exists())
        self.assertTrue((self.tmp / caught.exception.staging_name / "a").exists())

    def test_parent_path_replacement_after_precommit_check_fails_closed(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        parent = self.tmp / "container"
        parent.mkdir()
        output = parent / "out"
        moved = self.tmp / "retained-parent"
        original = publisher._rename_noreplace

        def swap_parent_then_commit(src_dir_fd, src_name, dst_dir_fd, dst_name):
            parent.rename(moved)
            parent.mkdir()
            return original(src_dir_fd, src_name, dst_dir_fd, dst_name)

        with mock.patch.object(publisher, "_rename_noreplace", side_effect=swap_parent_then_commit):
            with self.assertRaises(PartialPublicationError) as caught:
                publish_artifact_set(output, {"a": b"owned"})
        self.assertTrue(caught.exception.publication_committed)
        self.assertFalse(output.exists())
        self.assertEqual((moved / "out" / "a").read_bytes(), b"owned")

    def test_post_commit_mutation_is_not_misrepresented_as_stability(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        original = publisher._fsync_directory
        calls = 0

        def mutate_after_commit(dir_fd):
            nonlocal calls
            calls += 1
            original(dir_fd)
            if calls == 2:
                path = self.out / "a"
                with path.open("r+b", buffering=0) as handle:
                    handle.write(b"MUTATED!")
                    handle.flush()
                    os.fsync(handle.fileno())

        with mock.patch.object(publisher, "_fsync_directory", side_effect=mutate_after_commit):
            receipt = publish_artifact_set(self.out, {"a": b"ORIGINAL"})
        self.assertTrue(receipt["publication_committed"])
        self.assertFalse(receipt["post_commit_stability_proven"])
        self.assertEqual((self.out / "a").read_bytes(), b"MUTATED!")

    def test_post_commit_parent_fsync_failure_preserves_committed_generation(self) -> None:
        import tools.exact_byte_artifact_set.publisher as publisher

        original = publisher._fsync_directory
        calls = 0

        def fail_parent_fsync(dir_fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected parent fsync failure")
            return original(dir_fd)

        with mock.patch.object(publisher, "_fsync_directory", side_effect=fail_parent_fsync):
            with self.assertRaises(PartialPublicationError) as caught:
                publish_artifact_set(self.out, {"a": b"owned"})
        self.assertTrue(caught.exception.publication_committed)
        self.assertEqual((self.out / "a").read_bytes(), b"owned")

    def test_type_and_empty_set_guards(self) -> None:
        with self.assertRaises(PublicationError):
            publish_artifact_set(self.out, {"x": bytearray(b"x")})  # type: ignore[arg-type]
        with self.assertRaises(PublicationError):
            publish_artifact_set(self.out, {})
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
