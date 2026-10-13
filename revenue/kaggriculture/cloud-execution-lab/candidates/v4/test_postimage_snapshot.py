from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path

import postimage_trust as trust
import run_composed_postimage as front


class FakeMaterializationError(ValueError):
    pass


class SnapshotLoaderTests(unittest.TestCase):
    def _runner(self):
        def under(root: Path, rel: str, *, must_exist: bool = True):
            path = Path(root) / rel
            if must_exist and not path.is_file():
                raise FakeMaterializationError("regular file required")
            return path

        return types.SimpleNamespace(
            MaterializationError=FakeMaterializationError,
            _under=under,
        )

    def _bind(self, root: Path):
        manifest_path = root / trust.MANIFEST_NAME
        checker_path = root / trust.CHECKER_NAME
        manifest_bytes = b'{"schema":"safe"}\n'
        checker_bytes = (
            b"def validate_manifest(manifest, root):\n"
            b"    return {'ok': True, 'marker': 'authenticated-checker'}\n"
        )
        adapter_bytes = b"VALUE = 'authenticated-adapter'\n"
        support_bytes = b"VALUE = 'authenticated-support'\n"
        manifest_path.write_bytes(manifest_bytes)
        checker_path.write_bytes(checker_bytes)
        adapter = root / "adapter.py"
        support = root / "helper.py"
        adapter.write_bytes(adapter_bytes)
        support.write_bytes(support_bytes)

        runner = self._runner()
        front._bind_snapshot_loaders(
            runner,
            workspace=root,
            canonical_manifest=manifest_path,
            manifest={"schema": "safe"},
            manifest_bytes=manifest_bytes,
            checker_bytes=checker_bytes,
            entrypoint_bytes={
                ("adapter.py", trust.git_blob(adapter_bytes)): adapter_bytes,
            },
            support_source_bytes={
                ("workspace:helper.py", trust.git_blob(support_bytes)): support_bytes,
            },
        )
        return runner, manifest_path, checker_path, adapter, support, adapter_bytes, support_bytes

    def test_manifest_disk_swap_cannot_change_consumed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, manifest_path, *_ = self._bind(root)
            manifest_path.write_text('{"schema":"tampered"}\n', encoding="utf-8")
            manifest, raw = runner.load_json(manifest_path)
            self.assertEqual(manifest, {"schema": "safe"})
            self.assertEqual(raw, b'{"schema":"safe"}\n')

    def test_checker_disk_swap_cannot_change_executed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, _manifest, checker_path, *_ = self._bind(root)
            checker_path.write_text("raise RuntimeError('tampered checker executed')\n", encoding="utf-8")
            checker = runner._load_checker(root)
            self.assertEqual(
                checker.validate_manifest({}, root)["marker"],
                "authenticated-checker",
            )

    def test_checker_receipt_reads_remain_bound_after_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (
                runner,
                _manifest,
                checker_path,
                _adapter,
                _support,
                adapter_bytes,
                _support_bytes,
            ) = self._bind(root)
            checker = runner._load_checker(root)
            self.assertEqual(
                checker.validate_manifest({}, root)["marker"],
                "authenticated-checker",
            )
            authenticated = runner._under(root, trust.CHECKER_NAME).read_bytes()
            checker_path.write_text("VALUE = 'post-validation-disk-swap'\n", encoding="utf-8")
            receipt_path = runner._under(root, trust.CHECKER_NAME)
            first = receipt_path.read_bytes()
            checker_path.write_text("VALUE = 'between-receipt-hashes'\n", encoding="utf-8")
            second = receipt_path.read_bytes()
            self.assertEqual(first, authenticated)
            self.assertEqual(second, authenticated)
            self.assertNotEqual(checker_path.read_bytes(), authenticated)
            self.assertEqual(trust.git_blob(first), trust.git_blob(second))
            self.assertEqual(runner._under(root, "adapter.py").read_bytes(), adapter_bytes)

    def test_adapter_disk_swap_cannot_change_executed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, _manifest, _checker, adapter, _support, adapter_bytes, _support_bytes = self._bind(root)
            adapter.write_text("VALUE = 'tampered-adapter'\n", encoding="utf-8")
            expected = trust.git_blob(adapter_bytes)
            module = runner._load_module(adapter, expected, "lane:adapter.py")
            self.assertEqual(module.VALUE, "authenticated-adapter")

    def test_support_disk_swap_cannot_change_consumed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, _manifest, _checker, _adapter, support, _adapter_bytes, support_bytes = self._bind(root)
            support.write_text("VALUE = 'tampered-support'\n", encoding="utf-8")
            expected = trust.git_blob(support_bytes)
            data = runner._load_support_source(root, root, "workspace:helper.py", expected)
            self.assertEqual(data, support_bytes)

    def test_snapshot_rejects_identity_not_captured(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, _manifest, _checker, adapter, *_ = self._bind(root)
            with self.assertRaisesRegex(FakeMaterializationError, "not captured"):
                runner._load_module(adapter, "0" * 40, "lane:adapter.py")

    def test_snapshot_rejects_alternate_manifest_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner, manifest_path, *_ = self._bind(root)
            alt = root / "ALT.json"
            alt.write_bytes(manifest_path.read_bytes())
            with self.assertRaisesRegex(FakeMaterializationError, "canonical COMPOSITION"):
                runner.load_json(alt)


class SnapshotCaptureTests(unittest.TestCase):
    def test_runner_swap_after_prior_verification_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / trust.RUNNER_NAME
            safe = b"class MaterializationError(ValueError):\n    pass\nMARKER = 'safe'\n"
            path.write_bytes(b"class MaterializationError(ValueError):\n    pass\nMARKER = 'tampered'\n")
            old = trust.PINNED_CONTROL_BLOBS[trust.RUNNER_NAME]
            trust.PINNED_CONTROL_BLOBS[trust.RUNNER_NAME] = trust.git_blob(safe)
            try:
                with self.assertRaisesRegex(trust.TrustError, "source drift while snapshotting"):
                    front._load_runner(path)
            finally:
                trust.PINNED_CONTROL_BLOBS[trust.RUNNER_NAME] = old

    def test_capture_expected_detects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.py"
            safe = b"VALUE = 1\n"
            path.write_bytes(b"VALUE = 2\n")
            with self.assertRaisesRegex(trust.TrustError, "source drift while snapshotting"):
                front._capture_expected(path, trust.git_blob(safe), "x.py")


if __name__ == "__main__":
    unittest.main()
