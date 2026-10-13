"""Executed boundaries for UIOWA-129; no wall clock, network or repository mutation."""
import copy
import csv
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
# Tests work in a full checkout or the retained additive package checkout.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
MODULE = "revenue.uiowa_rfq_18649_timestamps"
a = importlib.import_module(MODULE + ".timestamp_adapter")
b = importlib.import_module(MODULE + ".csv_bridge")
ROOT = Path(a.__file__).parent
NY = "America/New_York"


def zone(value, fold=None, name=NY):
    result = {"value": value, "zone": name}
    if fold is not None:
        result["fold"] = fold
    return result


class TimestampTests(unittest.TestCase):
    def test_equivalent_offsets_and_negative_zero(self):
        values = ["2026-09-19T13:00:00Z", "2026-09-19T13:00:00-00:00",
                  "2026-09-19T18:30:00+05:30", "2026-09-19T09:00:00-04:00"]
        results = [a.normalize(v) for v in values]
        self.assertTrue(all(x["status"] == "resolved" for x in results))
        self.assertEqual({r["instant_utc"] for r in results}, {values[0]})
        self.assertEqual(results[1]["source"], values[1])

    def test_known_utc_with_zone_is_rendered_not_reinterpreted(self):
        for ending in ["Z", "z", "-00:00"]:
            with self.subTest(ending=ending):
                r = a.normalize(zone("2026-09-19T13:00:00" + ending))
                self.assertEqual(r["instant_utc"], "2026-09-19T13:00:00Z")
                self.assertEqual(r["local_in_zone"], "2026-09-19T09:00:00-04:00")
        self.assertEqual(a.normalize(zone("2026-09-19T13:00:00+00:00"))["code"], "offset_zone_mismatch")

    def test_timezone_fingerprint_and_mutation_isolation(self):
        original = zone("2026-09-19T09:00:00")
        r = a.normalize(original)
        digest = r["tzdb"]["tzif_sha256"]
        self.assertEqual(len(digest), 64)
        r["tzdb"]["tzif_sha256"] = "changed"
        r["source"]["value"] = "changed"
        self.assertEqual(a.normalize(original)["tzdb"]["tzif_sha256"], digest)
        self.assertEqual(original["value"], "2026-09-19T09:00:00")

    def test_microseconds_and_pre_epoch(self):
        r = a.elapsed("1969-12-31T23:59:59.999999Z", "1970-01-01T00:00:00Z")
        self.assertEqual(r["duration_microseconds"], 1)
        self.assertEqual(r["start"]["epoch_microseconds"], -1)

    def test_zero_duration_is_not_missing(self):
        self.assertEqual(a.elapsed("2026-09-19T13:00:00Z", "2026-09-19T18:30:00+05:30")["duration_microseconds"], 0)
        self.assertIsNone(a.elapsed(None, None)["duration_microseconds"])

    def test_reversed_timeline(self):
        r = a.elapsed("2026-09-19T14:00:00Z", "2026-09-19T13:00:00Z")
        self.assertEqual(r["code"], "reversed_timeline")
        self.assertIsNone(r["duration_seconds"])
        self.assertEqual(r["signed_microseconds"], -3600000000)

    def test_fall_fold_is_ambiguous(self):
        r = a.normalize(zone("2026-11-01T01:30:00"))
        self.assertEqual((r["status"], r["code"]), ("unresolved", "ambiguous_local_time"))
        self.assertIsNone(r["instant_utc"])
        self.assertEqual([x["instant_utc"] for x in r["candidates"]], ["2026-11-01T05:30:00Z", "2026-11-01T06:30:00Z"])

    def test_fold_interval_uses_utc(self):
        r = a.elapsed(zone("2026-11-01T01:30:00", 0), zone("2026-11-01T01:30:00", 1))
        self.assertEqual(r["duration_seconds"], 3600)

    def test_spring_elapsed_is_one_not_two_hours(self):
        r = a.elapsed(zone("2026-03-08T01:30:00"), zone("2026-03-08T03:30:00"))
        self.assertEqual(r["duration_seconds"], 3600)

    def test_gap_cannot_be_repaired_by_fold(self):
        for fold in [None, 0, 1]:
            self.assertEqual(a.normalize(zone("2026-03-08T02:30:00", fold))["code"], "nonexistent_local_time")

    def test_numeric_offset_disambiguates_fold(self):
        r = a.normalize(zone("2026-11-01T01:30:00-05:00"))
        self.assertEqual(r["instant_utc"], "2026-11-01T06:30:00Z")
        self.assertEqual(a.normalize(zone("2026-11-01T01:30:00-05:00", 0))["code"], "fold_conflict")

    def test_invalid_fold(self):
        for value in [True, "1", 2, -1]:
            self.assertEqual(a.normalize(zone("2026-11-01T01:30:00", value))["code"], "invalid_fold")
        self.assertEqual(a.normalize({"value": "2026-11-01T01:30:00Z", "fold": 1})["code"], "fold_requires_zone")
        self.assertEqual(a.normalize(zone("2026-09-19T09:00:00", 1))["code"], "fold_conflict")

    def test_half_hour_fold(self):
        value = "2026-04-05T01:45:00"
        r = a.elapsed(zone(value, 0, "Australia/Lord_Howe"), zone(value, 1, "Australia/Lord_Howe"))
        self.assertEqual(r["duration_seconds"], 1800)

    def test_skipped_civil_day(self):
        r = a.normalize(zone("2011-12-30T12:00:00", name="Pacific/Apia"))
        self.assertEqual(r["code"], "nonexistent_local_time")

    def test_utc_zone_and_missing_zone(self):
        self.assertEqual(a.normalize(zone("2026-09-19T13:00:00", name="UTC"))["instant_utc"], "2026-09-19T13:00:00Z")
        self.assertEqual(a.normalize("2026-09-19T13:00:00")["code"], "missing_offset_or_zone")

    def test_unavailable_zone_not_guessed(self):
        self.assertEqual(a.normalize(zone("2026-09-19T13:00:00", name="NoSuch/Zone"))["code"], "zone_unavailable")
        with patch.object(a, "_zone", side_effect=LookupError("missing database")):
            self.assertEqual(a.normalize(zone("2026-09-19T13:00:00"))["status"], "unresolved")

    def test_abbreviations_and_paths_refused(self):
        for name in ["EST", "CST", "/etc/localtime", "../UTC", "America//New_York"]:
            self.assertEqual(a.normalize(zone("2026-09-19T13:00:00", name=name))["code"], "invalid_zone")

    def test_bad_formats_dates_offsets_and_precision(self):
        cases = {"2026-09-19": "invalid_format", "2026-09-19 13:00:00Z": "invalid_format",
                 "2026-09-19T13:00:00Z ": "invalid_format", "2026-09-19T13:00:00+24:00": "invalid_offset",
                 "2026-09-19T13:00:00+00:60": "invalid_offset", "2026-09-19T13:00:60Z": "unsupported_leap_second",
                 "2026-09-19T13:00:00.1234567Z": "unsupported_precision", "2026-02-30T13:00:00Z": "invalid_or_out_of_range_time",
                 "0001-01-01T00:00:00+01:00": "invalid_or_out_of_range_time"}
        for value, code in cases.items():
            with self.subTest(value=value):
                self.assertEqual(a.normalize(value)["code"], code)

    def test_missing_and_invalid_values(self):
        for value in [None, "", "  "]:
            self.assertEqual(a.normalize(value)["status"], "missing")
        for value in [1, True, [], {"timestamp": "2026-09-19T13:00:00Z"}, {"value": None, "unknown": True}]:
            self.assertEqual(a.normalize(value)["status"], "invalid")


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.packet = a.read_json(ROOT / "fixtures/timeline_cases.json")

    def test_worked_cases_exact_expectations(self):
        r = a.normalize_packet(self.packet)
        self.assertEqual(r["summary"], {"events": 13, "intervals": 8, "unresolved_events": 5, "unresolved_intervals": 4})
        self.assertEqual([i["duration_seconds"] for i in r["intervals"]], [3600.0, 3600.0, 3600.0, None, None, None, None, 0.0])
        self.assertEqual(r["source_packet"], self.packet)
        self.assertEqual(a.canonical(r), a.canonical(a.normalize_packet(copy.deepcopy(self.packet))))

    def test_duplicate_event_and_interval_ids(self):
        for name in ["events", "intervals"]:
            p = copy.deepcopy(self.packet)
            p[name].append(copy.deepcopy(p[name][0]))
            with self.assertRaises(a.InputError):
                a.normalize_packet(p)

    def test_invalid_packet_shapes(self):
        for p in [None, [], {"schema_version": True, "events": []}, {"schema_version": 1, "events": {}},
                  {"schema_version": 1, "events": [], "synthetic": "yes"}, {"schema_version": 1, "events": [{"id": " "}]}]:
            with self.assertRaises(a.InputError):
                a.normalize_packet(p)

    def test_missing_endpoint_not_silently_joined(self):
        r = a.normalize_packet(self.packet)
        unknown = [i for i in r["intervals"] if i["code"] == "unknown_event"][0]
        self.assertIsNone(unknown["duration_seconds"])
        self.assertTrue(unknown["missing_event_ids"])

    def test_duplicate_json_and_nonfinite_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"bad.json"
            for text in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
                path.write_text(text)
                with self.assertRaises(a.InputError):
                    a.read_json(path)

    def test_cli_exits_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/"result.json"
            cmd = [sys.executable, str(ROOT/"timestamp_adapter.py"), str(ROOT/"fixtures/timeline_cases.json"), "--output", str(out)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            before_report = out.read_bytes()
            # Reports are evidence: repeating a destination is now an I/O error,
            # not permission to replace it. Test unresolved exit 1 on a new path.
            self.assertEqual(subprocess.run(cmd+["--require-resolved"], capture_output=True).returncode, 2)
            self.assertEqual(out.read_bytes(), before_report)
            unresolved_out = Path(td)/"unresolved-result.json"
            cmd[-1] = str(unresolved_out)
            self.assertEqual(subprocess.run(cmd+["--require-resolved"], capture_output=True).returncode, 1)
            self.assertEqual(json.loads(unresolved_out.read_text())["source_packet"], self.packet)
            self.assertEqual(json.loads(out.read_text())["source_packet"], self.packet)
            source = Path(td)/"source.json"
            source.write_text('{"schema_version":1,"events":[]}')
            before = source.read_bytes()
            self.assertEqual(a.main([str(source), "--output", str(source)]), 2)
            self.assertEqual(source.read_bytes(), before)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.headers, self.rows = b.read_rows(ROOT/"fixtures/delivery_dst.csv")

    def test_dst_bridge_preserves_all_source_fields(self):
        r = b.convert_rows(self.rows)
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["source_rows"], self.rows)
        self.assertEqual([r["normalized_rows"][0][f] for f in b.DELIVERY_FIELDS],
                         ["2026-11-01T04:30:00Z", "2026-11-01T05:30:00Z", "2026-11-01T06:30:00Z"])
        self.assertEqual(r["normalized_rows"][0]["notes"], self.rows[0]["notes"])

    def test_ambiguity_blocks_entire_conversion(self):
        self.rows[0]["recovered_at_fold"] = ""
        r = b.convert_rows(self.rows)
        self.assertEqual(r["status"], "unresolved")
        self.assertIsNone(r["normalized_rows"])
        self.assertEqual(r["blocked_fields"], 1)

    def test_optional_vs_required_missing(self):
        for f in b.DELIVERY_FIELDS:
            row = copy.deepcopy(self.rows[0])
            row[f] = ""
            r = b.convert_rows([row])
            self.assertEqual(r["status"], "unresolved" if f == "deployed_at" else "ready")
            if r["status"] == "ready":
                self.assertEqual(r["normalized_rows"][0][f], "")

    def test_invalid_and_duplicate_ids_and_mappings(self):
        with self.assertRaises(a.InputError):
            b.convert_rows(self.rows * 2)
        for fields in [[], [["deployed_at"]], "deployed_at", ("deployed_at", "deployed_at")]:
            with self.assertRaises(a.InputError):
                b.convert_rows(self.rows, timestamp_fields=fields)
        self.rows[0]["deployed_at_fold"] = "true"
        self.assertEqual(b.convert_rows(self.rows)["status"], "invalid")

    def test_general_lifecycle_fields_and_missing_key(self):
        rows = [{"event_id": "join-1", "joined": "2026-09-19T18:30:00+05:30", "retired": None, "context": {"source": "fiction"}}]
        r = b.convert_rows(rows, timestamp_fields=("joined", "retired"), required_fields=("joined",), id_field="event_id")
        self.assertEqual(r["normalized_rows"][0]["joined"], "2026-09-19T13:00:00Z")
        self.assertIsNone(r["normalized_rows"][0]["retired"])
        del rows[0]["joined"]
        r = b.convert_rows(rows, timestamp_fields=("joined",), required_fields=("joined",), id_field="event_id")
        self.assertFalse(r["audit"][0]["source_field_present"])
        self.assertIsNone(r["normalized_rows"])

    def test_csv_header_and_row_width_errors(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"bad.csv"
            for text in ["id,id\na,b\n", "id,value\na\n", "id,value\na,b,c\n", ",value\na,b\n"]:
                p.write_text(text)
                with self.assertRaises(a.InputError):
                    b.read_rows(p)

    def test_bridge_cli_blocked_no_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); src=td/"input.csv"; out=td/"normalized.csv"; audit=td/"audit.json"
            self.rows[0]["recovered_at_fold"] = ""
            with src.open("w", newline="") as f:
                w=csv.DictWriter(f, fieldnames=self.headers); w.writeheader(); w.writerows(self.rows)
            before=src.read_bytes()
            self.assertEqual(b.main([str(src), "--output", str(out), "--audit", str(audit)]), 1)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(audit.read_text())["status"], "unresolved")
            self.assertEqual(b.main([str(src), "--output", str(out), "--audit", str(audit)]), 2)
            self.assertEqual(src.read_bytes(), before)

    def test_bridge_cli_success_and_repeat_protection(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"normalized.csv"; audit=Path(td)/"audit.json"
            cmd=[sys.executable,str(ROOT/"csv_bridge.py"),str(ROOT/"fixtures/delivery_dst.csv"),"--output",str(out),"--audit",str(audit)]
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            before=out.read_bytes()
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
            self.assertEqual(out.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
