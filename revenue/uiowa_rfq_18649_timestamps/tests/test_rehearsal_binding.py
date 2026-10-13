"""Exercise the real calculator in disposable copies; no caller sources are edited."""
from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
import py_compile
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
r = importlib.import_module("revenue.uiowa_rfq_18649_timestamps.rehearse_delivery")
REAL_COMPONENT = Path(r.__file__).resolve().parent
REAL_DEPENDENCY = REAL_COMPONENT.parent / "uiowa_rfq_18649_delivery_metrics"
PRIVATE_MODULE = "_uiowa129_real_delivery_calculator"


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class RehearsalBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uiowa129-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.component = self.root / "uiowa_rfq_18649_timestamps"
        self.dependency = self.root / "uiowa_rfq_18649_delivery_metrics"
        (self.component / "fixtures").mkdir(parents=True)
        (self.dependency / "fixtures").mkdir(parents=True)
        self.calculator = self.dependency / "calculator.py"
        self.fixture = self.dependency / "fixtures/synthetic_deployments.csv"
        self.dst = self.component / "fixtures/delivery_dst.csv"
        self.calculator.write_bytes((REAL_DEPENDENCY / "calculator.py").read_bytes())
        self.fixture.write_bytes((REAL_DEPENDENCY / "fixtures/synthetic_deployments.csv").read_bytes())
        self.dst.write_bytes((REAL_COMPONENT / "fixtures/delivery_dst.csv").read_bytes())
        for field, value in [("ROOT", self.component), ("DEPENDENCY", self.dependency)]:
            replacement = patch.object(r, field, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def instrument(self, marker: str) -> bytes:
        """Append a benign, observable marker without replacing the real metric engine."""
        data = (REAL_DEPENDENCY / "calculator.py").read_bytes()
        data += ("\n_original_calculate = calculate\n"
                 "def calculate(*args, **kwargs):\n"
                 "    report = _original_calculate(*args, **kwargs)\n"
                 f"    report['interpretation_boundary']['synthetic_source_marker'] = {marker!r}\n"
                 "    report['interpretation_boundary']['synthetic_source_file'] = __file__\n"
                 "    return report\n").encode("utf-8")
        self.calculator.write_bytes(data)
        return data

    def marker(self, report):
        return report["native_original_report"]["interpretation_boundary"]["synthetic_source_marker"]

    def test_current_source_not_valid_timestamp_bytecode_is_executed(self):
        old = self.instrument("OLD")
        old_stat = self.calculator.stat()
        py_compile.compile(str(self.calculator), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        new = old.replace(b"'OLD'", b"'NEW'")
        self.assertEqual(len(old), len(new))
        self.calculator.write_bytes(new)
        os.utime(self.calculator, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        report = r.rehearse()
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_delivery_metrics/calculator.py"], blob(new))
        self.assertEqual(self.marker(report), "NEW")
        self.assertTrue(all(report["checks"].values()))

    def test_source_refresh_after_capture_does_not_change_executed_bytes(self):
        old = self.instrument("OLD")
        real_read = Path.read_bytes
        refreshed = []
        def read_then_refresh(path):
            data = real_read(path)
            if path == self.calculator and not refreshed:
                self.calculator.write_bytes(old.replace(b"'OLD'", b"'NEW'"))
                refreshed.append(True)
            return data
        with patch.object(Path, "read_bytes", read_then_refresh):
            report = r.rehearse()
        self.assertEqual(refreshed, [True])
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_delivery_metrics/calculator.py"], blob(old))
        self.assertEqual(self.marker(report), "OLD")

    def test_fixture_refresh_after_capture_does_not_change_native_metrics(self):
        old = self.fixture.read_bytes()
        changed = old.replace(b"2026-09-01T12:00:00Z", b"2026-09-01T13:00:00Z")
        self.assertNotEqual(changed, old)
        real_read = Path.read_bytes
        refreshed = []
        def read_then_refresh(path):
            data = real_read(path)
            if path == self.fixture and not refreshed:
                self.fixture.write_bytes(changed)
                refreshed.append(True)
            return data
        with patch.object(Path, "read_bytes", read_then_refresh):
            report = r.rehearse()
        self.assertEqual(refreshed, [True])
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv"], blob(old))
        self.assertEqual(report["native_original_report"]["metrics"]["change_lead_time"]["mean"], 14.875)

    def test_captured_fixture_is_usable_after_source_path_disappears(self):
        old = self.fixture.read_bytes()
        real_read = Path.read_bytes
        removed = []
        def read_then_remove(path):
            data = real_read(path)
            if path == self.fixture and not removed:
                self.fixture.unlink()
                removed.append(True)
            return data
        with patch.object(Path, "read_bytes", read_then_remove):
            report = r.rehearse()
        self.assertEqual(removed, [True])
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv"], blob(old))

    def test_dst_fixture_is_bound_to_receipt_too(self):
        data = self.dst.read_bytes()
        report = r.rehearse()
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_timestamps/fixtures/delivery_dst.csv"], blob(data))

    def test_original_inputs_are_not_modified_by_rehearsal(self):
        paths = [self.calculator, self.fixture, self.dst]
        before = {str(p): p.read_bytes() for p in paths}
        r.rehearse()
        self.assertEqual({str(p): p.read_bytes() for p in paths}, before)

    def test_wrong_source_pin_rejects_before_dependency_execution(self):
        self.calculator.write_bytes(b"raise RuntimeError('synthetic source must not execute')\n")
        with self.assertRaisesRegex(r.InputError, "revision drift"):
            r.rehearse("0" * 40)

    def test_bad_source_syntax_is_an_explicit_dependency_error(self):
        self.calculator.write_bytes(b"def invalid(\n")
        with self.assertRaisesRegex(r.InputError, "dependency source"):
            r.rehearse()

    def test_caller_module_binding_restored_after_success_and_failure(self):
        sentinel = object()
        old = sys.modules.get(PRIVATE_MODULE)
        sys.modules[PRIVATE_MODULE] = sentinel
        try:
            r.rehearse()
            self.assertIs(sys.modules[PRIVATE_MODULE], sentinel)
            self.calculator.write_bytes(b"raise ValueError('synthetic failure')\n")
            with self.assertRaises(ValueError):
                r.rehearse()
            self.assertIs(sys.modules[PRIVATE_MODULE], sentinel)
        finally:
            if old is None:
                sys.modules.pop(PRIVATE_MODULE, None)
            else:
                sys.modules[PRIVATE_MODULE] = old

    def test_explicit_none_module_binding_is_restored(self):
        absent = object()
        previous = sys.modules.get(PRIVATE_MODULE, absent)
        sys.modules[PRIVATE_MODULE] = None
        try:
            r.rehearse()
            self.assertIn(PRIVATE_MODULE, sys.modules)
            self.assertIsNone(sys.modules[PRIVATE_MODULE])
        finally:
            if previous is absent:
                sys.modules.pop(PRIVATE_MODULE, None)
            else:
                sys.modules[PRIVATE_MODULE] = previous

    def test_incompatible_dependency_api_is_explicit(self):
        self.calculator.write_bytes(b"calculate = 42\nload_deployments = None\n")
        with self.assertRaisesRegex(r.InputError, "dependency source must provide"):
            r.rehearse()

    def test_missing_dependency_import_is_explicit(self):
        self.calculator.write_bytes(b"import _uiowa129_absent_synthetic_module\n")
        with self.assertRaisesRegex(r.InputError, "dependency source"):
            r.rehearse()

    def test_each_original_input_is_read_exactly_once(self):
        reads = {p: 0 for p in (self.calculator, self.fixture, self.dst)}
        real_read = Path.read_bytes
        def counted_read(path):
            if path in reads:
                reads[path] += 1
            return real_read(path)
        with patch.object(Path, "read_bytes", counted_read):
            report = r.rehearse()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(list(reads.values()), [1, 1, 1])

    def test_dst_refresh_after_capture_does_not_change_checks(self):
        before = self.dst.read_bytes()
        real_read = Path.read_bytes
        refreshed = []
        def read_then_refresh(path):
            data = real_read(path)
            if path == self.dst and not refreshed:
                self.dst.write_bytes(b"synthetic invalid replacement\n")
                refreshed.append(True)
            return data
        with patch.object(Path, "read_bytes", read_then_refresh):
            report = r.rehearse()
        self.assertEqual(refreshed, [True])
        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["dependency_blobs"]["uiowa_rfq_18649_timestamps/fixtures/delivery_dst.csv"], blob(before))

    def test_dependency_keeps_real_source_location(self):
        self.instrument("LOC")
        report = r.rehearse()
        self.assertEqual(report["native_original_report"]["interpretation_boundary"]["synthetic_source_file"], str(self.calculator))


if __name__ == "__main__":
    unittest.main(verbosity=2)
