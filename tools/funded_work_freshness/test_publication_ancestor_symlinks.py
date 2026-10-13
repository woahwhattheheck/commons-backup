from pathlib import Path
import tempfile
import unittest

from errors import PreflightInputError
from publication import publish_text_bundle, require_distinct_artifacts


class PublicationAncestorSymlinkTests(unittest.TestCase):
    def test_output_under_symlinked_parent_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            outside = root / "outside"
            workspace.mkdir()
            outside.mkdir()
            linked = workspace / "linked-output"
            linked.symlink_to(outside, target_is_directory=True)
            target = linked / "report.json"

            with self.assertRaisesRegex(PreflightInputError, "parent must not traverse a symlink"):
                require_distinct_artifacts({"input": None, "output": target, "cache": None})
            self.assertFalse((outside / "report.json").exists())

    def test_cache_under_symlinked_parent_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            outside = root / "outside"
            workspace.mkdir()
            outside.mkdir()
            linked = workspace / "linked-cache"
            linked.symlink_to(outside, target_is_directory=True)
            target = linked / "cache.json"

            with self.assertRaisesRegex(PreflightInputError, "parent must not traverse a symlink"):
                require_distinct_artifacts({"input": None, "output": None, "cache": target})
            self.assertFalse((outside / "cache.json").exists())

    def test_existing_target_under_symlinked_parent_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            outside = root / "outside"
            workspace.mkdir()
            outside.mkdir()
            outside_target = outside / "report.json"
            outside_target.write_text("old\n", encoding="utf-8")
            linked = workspace / "linked"
            linked.symlink_to(outside, target_is_directory=True)
            target = linked / "report.json"

            with self.assertRaisesRegex(PreflightInputError, "parent must not traverse a symlink"):
                publish_text_bundle({target: "new\n"})
            self.assertEqual("old\n", outside_target.read_text(encoding="utf-8"))
            self.assertEqual([], list(outside.glob(".*.stage.*")))
            self.assertEqual([], list(outside.glob(".*.backup.*")))

    def test_parent_swap_after_preflight_is_rejected_at_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "report-dir"
            outside = root / "outside"
            parent.mkdir()
            outside.mkdir()
            outside_target = outside / "report.json"
            outside_target.write_text("outside-old\n", encoding="utf-8")
            target = parent / "report.json"

            require_distinct_artifacts({"input": None, "output": target, "cache": None})
            parent.rmdir()
            parent.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(PreflightInputError, "parent must not traverse a symlink"):
                publish_text_bundle({target: "new\n"})
            self.assertEqual("outside-old\n", outside_target.read_text(encoding="utf-8"))
            self.assertEqual([], list(outside.glob(".*.stage.*")))
            self.assertEqual([], list(outside.glob(".*.backup.*")))


if __name__ == "__main__":
    unittest.main()
