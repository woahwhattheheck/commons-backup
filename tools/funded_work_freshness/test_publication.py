import os
from pathlib import Path
import tempfile
import unittest

from errors import PreflightInputError
from publication import paths_alias, publish_text_bundle, require_distinct_artifacts


class PublicationTests(unittest.TestCase):
    def test_direct_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.json"
            path.write_text("input\n", encoding="utf-8")
            with self.assertRaises(PreflightInputError):
                require_distinct_artifacts({"input": path, "output": path, "cache": None})

    def test_symlink_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            alias = root / "report.json"
            source.write_text("input\n", encoding="utf-8")
            alias.symlink_to(source.name)
            self.assertTrue(paths_alias(source, alias))
            with self.assertRaises(PreflightInputError):
                require_distinct_artifacts({"input": source, "output": alias})

    def test_hardlink_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            alias = root / "cache.json"
            source.write_text("input\n", encoding="utf-8")
            os.link(source, alias)
            self.assertTrue(paths_alias(source, alias))
            with self.assertRaises(PreflightInputError):
                require_distinct_artifacts({"input": source, "cache": alias})

    def test_existing_symlink_publication_target_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "real.json"
            target = root / "report.json"
            destination.write_text("old\n", encoding="utf-8")
            target.symlink_to(destination.name)
            with self.assertRaises(PreflightInputError):
                publish_text_bundle({target: "new\n"})
            self.assertEqual("old\n", destination.read_text(encoding="utf-8"))
            self.assertTrue(target.is_symlink())

    def test_successful_bundle_replaces_all_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            cache = root / "cache.json"
            report.write_text("old-report\n", encoding="utf-8")
            cache.write_text("old-cache\n", encoding="utf-8")
            publish_text_bundle({report: "new-report\n", cache: "new-cache\n"})
            self.assertEqual("new-report\n", report.read_text(encoding="utf-8"))
            self.assertEqual("new-cache\n", cache.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob(".*.stage.*")))
            self.assertEqual([], list(root.glob(".*.backup.*")))

    def test_second_replace_failure_restores_preexisting_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            cache = root / "cache.json"
            report.write_text("old-report\n", encoding="utf-8")
            cache.write_text("old-cache\n", encoding="utf-8")
            calls = 0

            def fail_second(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second publication failure")
                os.replace(source, destination)

            with self.assertRaisesRegex(OSError, "injected second publication failure"):
                publish_text_bundle(
                    {report: "new-report\n", cache: "new-cache\n"}, replace=fail_second
                )
            self.assertEqual("old-report\n", report.read_text(encoding="utf-8"))
            self.assertEqual("old-cache\n", cache.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob(".*.stage.*")))
            self.assertEqual([], list(root.glob(".*.backup.*")))

    def test_second_replace_failure_removes_newly_created_first_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            cache = root / "cache.json"
            cache.write_text("old-cache\n", encoding="utf-8")
            calls = 0

            def fail_second(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second publication failure")
                os.replace(source, destination)

            with self.assertRaises(OSError):
                publish_text_bundle(
                    {report: "new-report\n", cache: "new-cache\n"}, replace=fail_second
                )
            self.assertFalse(report.exists())
            self.assertEqual("old-cache\n", cache.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob(".*.stage.*")))
            self.assertEqual([], list(root.glob(".*.backup.*")))


if __name__ == "__main__":
    unittest.main()
