"""Loader rejection tests; real canonical execution is a separate CLI receipt."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cirrus_adapter_loading_tested", ROOT / "lodestone_adapter.py")
A = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = A
SPEC.loader.exec_module(A)


class LoaderTests(unittest.TestCase):
    def test_bad_pin_rejects_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.py"
            target.write_text("raise RuntimeError('must never execute')\n")
            with self.assertRaisesRegex(ValueError, "source pin mismatch"):
                A.load_module(target, "cirrus_bad_pin", "0" * 40)

    def test_matching_pin_returns_actual_bytes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.py"
            raw = b"VALUE = 103\n"
            target.write_bytes(raw)
            pin = hashlib.sha1(b"blob 12\0" + raw).hexdigest()
            module, observed = A.load_module(target, "cirrus_good_pin", pin)
            self.assertEqual(module.VALUE, 103)
            self.assertEqual(observed, pin)

    def test_missing_target_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(A.main(["--mapper", str(Path(directory) / "missing.py")]), 2)

    def test_failed_import_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.py"
            raw = b"raise RuntimeError('target-error')\n"
            target.write_bytes(raw)
            pin = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            with self.assertRaisesRegex(RuntimeError, "target-error"):
                A.load_module(target, "cirrus_failed_import", pin)
            self.assertNotIn("cirrus_failed_import_" + pin, sys.modules)


if __name__ == "__main__":
    unittest.main()
