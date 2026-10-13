#!/usr/bin/env python3
"""Independent UIOWA-129 evidence-preservation and timestamp regressions.

Only disposable synthetic files are modified. Select an exact component with
UIOWA129_COMPONENT; the suite never searches for modules elsewhere on sys.path.
"""
from __future__ import annotations
import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(os.environ.get("UIOWA129_COMPONENT", str(Path(__file__).resolve().parents[1]))).resolve()
PKG = "_hemlock84_uiowa129_review"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT)]
sys.modules[PKG] = package

def load(name):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

ta = load("timestamp_adapter")
cb = load("csv_bridge")
PACKET = {"schema_version": 1, "synthetic": True, "events": [{"id": "synthetic-event", "timestamp": "2026-09-19T12:00:00Z"}]}
CSV = b'deployment_id,commit_at,deployed_at,recovered_at,notes\r\nSYN-A,2026-09-19T11:00:00Z,2026-09-19T12:00:00Z,,"fiction: quoted, value"\r\n'

class EvidenceIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="uiowa129-hemlock84-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packet = self.root / "source.json"
        self.packet.write_text(json.dumps(PACKET), encoding="utf-8")
        self.csv = self.root / "source.csv"
        self.csv.write_bytes(CSV)
        self.output = self.root / "normalized.csv"
        self.audit = self.root / "audit.json"

    def call(self, function, argv):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return function(argv)

    def csvargs(self):
        return [str(self.csv), "--output", str(self.output), "--audit", str(self.audit)]

    def test_packet_new_report_preserves_source(self):
        before = self.packet.read_bytes()
        output = self.root / "report.json"
        self.assertEqual(self.call(ta.main, [str(self.packet), "--output", str(output)]), 0)
        self.assertEqual(self.packet.read_bytes(), before)
        self.assertEqual(json.loads(output.read_text())["source_packet"], PACKET)

    def test_packet_exact_source_output_is_refused(self):
        before = self.packet.read_bytes()
        self.assertEqual(self.call(ta.main, [str(self.packet), "--output", str(self.packet)]), 2)
        self.assertEqual(self.packet.read_bytes(), before)

    def test_packet_source_symlink_alias_is_refused(self):
        alias = self.root / "alias.json"
        alias.symlink_to(self.packet)
        before = self.packet.read_bytes()
        self.assertEqual(self.call(ta.main, [str(self.packet), "--output", str(alias)]), 2)
        self.assertEqual(self.packet.read_bytes(), before)

    def test_packet_source_hardlink_alias_is_refused(self):
        alias = self.root / "alias.json"
        os.link(self.packet, alias)
        before = self.packet.read_bytes()
        code = self.call(ta.main, [str(self.packet), "--output", str(alias)])
        self.assertEqual((code, self.packet.read_bytes() == before), (2, True))

    def test_packet_existing_report_is_preserved(self):
        output = self.root / "report.json"
        output.write_bytes(b"previous synthetic review")
        code = self.call(ta.main, [str(self.packet), "--output", str(output)])
        self.assertEqual((code, output.read_bytes()), (2, b"previous synthetic review"))

    def test_packet_dangling_output_alias_is_refused(self):
        target = self.root / "not-yet-created.json"
        output = self.root / "report.json"
        output.symlink_to(target)
        code = self.call(ta.main, [str(self.packet), "--output", str(output)])
        self.assertEqual((code, target.exists()), (2, False))

    def test_packet_new_report_optimized_cli_preserves_source(self):
        before = self.packet.read_bytes()
        output = self.root / "report.json"
        result = subprocess.run([sys.executable, "-O", str(ROOT / "timestamp_adapter.py"), str(self.packet), "--output", str(output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.packet.read_bytes(), before)
        self.assertEqual(json.loads(output.read_text())["source_packet"], PACKET)

    def test_csv_standard_conversion_keeps_hash_and_rows(self):
        self.assertEqual(self.call(cb.main, self.csvargs()), 0)
        report = json.loads(self.audit.read_text())
        self.assertEqual(report["input_file_sha256"], hashlib.sha256(CSV).hexdigest())
        self.assertEqual(report["source_rows"][0]["notes"], "fiction: quoted, value")
        self.assertEqual(report["normalized_rows"][0]["recovered_at"], "")
        self.assertEqual(self.csv.read_bytes(), CSV)

    def test_csv_hash_matches_parsed_snapshot_after_source_refresh(self):
        real_convert = cb.convert_rows
        changed = CSV.replace(b"SYN-A", b"SYN-B")
        def convert_then_refresh(*args, **kwargs):
            report = real_convert(*args, **kwargs)
            self.csv.write_bytes(changed)
            return report
        with mock.patch.object(cb, "convert_rows", side_effect=convert_then_refresh):
            self.assertEqual(self.call(cb.main, self.csvargs()), 0)
        report = json.loads(self.audit.read_text())
        self.assertEqual(report["source_rows"][0]["deployment_id"], "SYN-A")
        self.assertEqual(self.csv.read_bytes(), changed)
        self.assertEqual(report["input_file_sha256"], hashlib.sha256(CSV).hexdigest())

    def test_csv_snapshot_remains_usable_if_original_path_is_removed(self):
        real_convert = cb.convert_rows
        def convert_then_remove(*args, **kwargs):
            report = real_convert(*args, **kwargs)
            self.csv.unlink()
            return report
        with mock.patch.object(cb, "convert_rows", side_effect=convert_then_remove):
            code = self.call(cb.main, self.csvargs())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.audit.read_text())["input_file_sha256"], hashlib.sha256(CSV).hexdigest())

    def test_csv_existing_output_is_preserved(self):
        self.output.write_bytes(b"existing synthetic review")
        self.assertEqual(self.call(cb.main, self.csvargs()), 2)
        self.assertEqual(self.output.read_bytes(), b"existing synthetic review")
        self.assertFalse(self.audit.exists())

    def test_csv_existing_audit_is_preserved(self):
        self.audit.write_bytes(b"existing synthetic audit")
        self.assertEqual(self.call(cb.main, self.csvargs()), 2)
        self.assertEqual(self.audit.read_bytes(), b"existing synthetic audit")
        self.assertFalse(self.output.exists())

    def test_csv_source_output_hardlink_is_refused(self):
        os.link(self.csv, self.output)
        self.assertEqual(self.call(cb.main, self.csvargs()), 2)
        self.assertEqual(self.csv.read_bytes(), CSV)

    def test_csv_unresolved_field_never_writes_normalized_output(self):
        self.csv.write_bytes(CSV.replace(b"2026-09-19T12:00:00Z", b"2026-09-19T12:00:00"))
        self.assertEqual(self.call(cb.main, self.csvargs()), 1)
        self.assertFalse(self.output.exists())
        report = json.loads(self.audit.read_text())
        self.assertEqual(report["status"], "unresolved")
        self.assertIsNone(report["normalized_rows"])

    def test_csv_bad_row_width_creates_no_outputs(self):
        self.csv.write_bytes(CSV + b"extra,column\n")
        self.assertEqual(self.call(cb.main, self.csvargs()), 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.audit.exists())

    def test_csv_bad_encoding_creates_no_outputs(self):
        self.csv.write_bytes(CSV + b"\xff")
        self.assertEqual(self.call(cb.main, self.csvargs()), 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.audit.exists())

    def test_csv_read_rows_api_preserves_embedded_newlines_and_header_order(self):
        raw = b'deployment_id,commit_at,deployed_at,recovered_at,notes\r\nSYN-A,,2026-09-19T12:00:00Z,,"fiction\r\ncontinued"\r\n'
        self.csv.write_bytes(raw)
        headers, rows = cb.read_rows(self.csv)
        self.assertEqual(headers, ["deployment_id", "commit_at", "deployed_at", "recovered_at", "notes"])
        self.assertEqual(rows[0]["notes"], "fiction\r\ncontinued")

    def test_packet_duplicate_json_keys_are_rejected(self):
        self.packet.write_text('{"schema_version":1,"events":[],"events":[]}', encoding="utf-8")
        self.assertEqual(self.call(ta.main, [str(self.packet)]), 2)

class TimestampCompatibility(unittest.TestCase):
    def test_equivalent_offsets_produce_zero_elapsed(self):
        self.assertEqual(ta.elapsed("2026-09-19T12:00:00Z", "2026-09-19T08:00:00-04:00")["duration_microseconds"], 0)

    def test_fractional_microseconds_are_exact(self):
        self.assertEqual(ta.elapsed("2026-09-19T12:00:00.123456Z", "2026-09-19T12:00:00.123457Z")["duration_microseconds"], 1)

    def test_missing_and_invalid_remain_distinct(self):
        self.assertEqual(ta.normalize(None)["status"], "missing")
        self.assertEqual(ta.normalize("2026-02-30T12:00:00Z")["status"], "invalid")
        self.assertEqual(ta.normalize("2026-09-19T12:00:00")["status"], "unresolved")

    def test_repeated_hour_requires_fold(self):
        spec = {"value": "2026-11-01T01:30:00", "zone": "America/New_York"}
        self.assertEqual(ta.normalize(spec)["code"], "ambiguous_local_time")
        result = ta.elapsed(dict(spec, fold=0), dict(spec, fold=1))
        self.assertEqual(result["duration_seconds"], 3600)

    def test_spring_gap_stays_invalid(self):
        self.assertEqual(ta.normalize({"value": "2026-03-08T02:30:00", "zone": "America/New_York"})["code"], "nonexistent_local_time")

    def test_numeric_offset_zone_mismatch_is_rejected(self):
        self.assertEqual(ta.normalize({"value": "2026-07-01T12:00:00-05:00", "zone": "America/New_York"})["code"], "offset_zone_mismatch")

    def test_unknown_zone_stays_unresolved(self):
        self.assertEqual(ta.normalize({"value": "2026-09-19T12:00:00", "zone": "Synthetic/Unavailable"})["status"], "unresolved")

    def test_half_hour_fold_not_assumed_one_hour(self):
        spec = {"value": "2026-04-05T01:45:00", "zone": "Australia/Lord_Howe"}
        self.assertEqual(ta.elapsed(dict(spec, fold=0), dict(spec, fold=1))["duration_seconds"], 1800)

    def test_civil_day_gap_stays_invalid(self):
        self.assertEqual(ta.normalize({"value": "2011-12-30T12:00:00", "zone": "Pacific/Apia"})["code"], "nonexistent_local_time")

    def test_reversed_timeline_has_no_positive_duration(self):
        result = ta.elapsed("2026-09-19T13:00:00Z", "2026-09-19T12:00:00Z")
        self.assertEqual(result["code"], "reversed_timeline")
        self.assertIsNone(result["duration_microseconds"])

    def test_conversion_copies_original_source(self):
        rows = [{"deployment_id": "SYN-A", "deployed_at": "2026-09-19T08:00:00-04:00", "commit_at": "", "recovered_at": ""}]
        before = copy.deepcopy(rows)
        result = cb.convert_rows(rows)
        self.assertEqual(rows, before)
        self.assertEqual(result["normalized_rows"][0]["deployed_at"], "2026-09-19T12:00:00Z")

    def test_partial_ready_rows_are_not_released(self):
        rows = [{"deployment_id": "SYN-A", "deployed_at": "2026-09-19T12:00:00Z"}, {"deployment_id": "SYN-B", "deployed_at": "2026-09-19T12:00:00"}]
        result = cb.convert_rows(rows)
        self.assertEqual(result["status"], "unresolved")
        self.assertIsNone(result["normalized_rows"])
        self.assertEqual(result["input_row_count"], 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
