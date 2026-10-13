"""Independent real-input regressions; all fixtures and writes are disposable."""
import copy
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import prioritize as p

HERE = Path(__file__).resolve().parent
INPUT = HERE / "recommendations.synthetic.csv"
WEIGHTS = HERE / "weights.json"


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = json.loads(WEIGHTS.read_text(encoding="utf-8"))
        self.rows = list(csv.reader(io.StringIO(INPUT.read_text(encoding="utf-8"))))

    def csv_file(self, rows):
        path = self.root / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(rows)
        return path

    def config_file(self, config):
        path = self.root / "weights.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def tree_bytes(self, root):
        return {str(x.relative_to(root)): x.read_bytes() for x in root.rglob("*") if x.is_file()}

    def test_config_root_requires_object(self):
        for value in [None, True, 3, [], "profiles"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.validate_weights(value)

    def test_epsilon_requires_finite_json_number(self):
        for value in [float("nan"), float("inf"), -float("inf"), True, False, "0.02", None]:
            cfg = copy.deepcopy(self.config)
            cfg["tie_epsilon"] = value
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                p.validate_weights(cfg)

    def test_each_weight_requires_finite_json_number(self):
        for field in ["quality", "security", "delivery", "complexity"]:
            for value in [float("nan"), float("inf"), True, "0.33", None, 10 ** 400]:
                cfg = copy.deepcopy(self.config)
                cfg["profiles"]["balanced"][field] = value
                with self.subTest(field=field, value=repr(value)), self.assertRaises(ValueError):
                    p.validate_weights(cfg)

    def test_profile_value_requires_object(self):
        for value in [None, True, [], "quality"]:
            cfg = {"profiles": {"example": value}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.validate_weights(cfg)

    def test_unknown_config_and_weight_keys_rejected(self):
        for where in ["config", "weight"]:
            cfg = copy.deepcopy(self.config)
            target = cfg if where == "config" else cfg["profiles"]["balanced"]
            target["securty"] = 0.3
            with self.subTest(where=where), self.assertRaises(ValueError):
                p.validate_weights(cfg)

    def test_profile_names_are_portable_components(self):
        for name in ["", "a/b", "a\\b", "a\nline", "x" * 65, 7]:
            cfg = {"profiles": {name: self.config["profiles"]["balanced"]}}
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.validate_weights(cfg)

    def test_case_insensitive_profile_collision_rejected(self):
        w = self.config["profiles"]["balanced"]
        with self.assertRaises(ValueError):
            p.validate_weights({"profiles": {"Balanced": w, "balanced": w}})

    def test_json_duplicate_keys_rejected(self):
        raw = '{"profiles":{"balanced":{"quality":0.34,"security":0.33,"delivery":0.33,"complexity":0.35}},"tie_epsilon":0.0,"tie_epsilon":1.0}'
        path = self.root / "duplicate.json"
        path.write_text(raw, encoding="utf-8")
        with self.assertRaises(ValueError):
            p.load_weights(path)

    def test_json_nonstandard_constants_rejected(self):
        for value in ["NaN", "Infinity", "-Infinity"]:
            path = self.root / "nonfinite.json"
            path.write_text(json.dumps(self.config).replace('0.02', value, 1), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.load_weights(path)

    def test_csv_duplicate_header_rejected(self):
        rows = [self.rows[0] + ["quality"], self.rows[1] + ["0"]]
        with self.assertRaises(ValueError):
            p.load_recommendations(self.csv_file(rows))

    def test_csv_extra_header_rejected_not_dropped(self):
        rows = [self.rows[0] + ["new_fact"], self.rows[1] + ["retained?"]]
        with self.assertRaises(ValueError):
            p.load_recommendations(self.csv_file(rows))

    def test_csv_long_row_rejected(self):
        with self.assertRaises(ValueError):
            p.load_recommendations(self.csv_file([self.rows[0], self.rows[1] + ["extra"]]))

    def test_csv_short_row_not_confused_with_unknown(self):
        with self.assertRaises(ValueError):
            p.load_recommendations(self.csv_file([self.rows[0], self.rows[1][:-1]]))

    def test_header_only_is_not_successful_assessment(self):
        with self.assertRaises(ValueError):
            p.load_recommendations(self.csv_file([self.rows[0]]))

    def test_malformed_quoted_csv_rejected(self):
        path = self.root / "broken.csv"
        path.write_text(','.join(self.rows[0]) + '\nR001,"unterminated,4,4,4,3,0.7,a,b,c', encoding="utf-8")
        with self.assertRaises(ValueError):
            p.load_recommendations(path)

    def test_utf8_bom_supported(self):
        path = self.root / "bom.csv"
        path.write_bytes(b"\xef\xbb\xbf" + INPUT.read_bytes())
        self.assertEqual(p.load_recommendations(path), p.load_recommendations(INPUT))
        config = self.root / "bom.json"
        config.write_bytes(b"\xef\xbb\xbf" + WEIGHTS.read_bytes())
        self.assertEqual(p.load_weights(config), self.config)

    def test_quoted_multiline_and_unicode_retained(self):
        rows = self.rows[:2]
        rows[1] = rows[1].copy()
        rows[1][1] = 'Finding | café <draft>\r\nsecond line'
        rows[1][-1] = 'An assumption, with "quotes"\nnext line'
        rec = p.load_recommendations(self.csv_file(rows))[0]
        self.assertEqual(rec["title"], rows[1][1])
        self.assertEqual(rec["assumptions"], rows[1][-1])

    def test_explicit_blank_estimate_still_holds(self):
        rows = p.rank_profile(p.load_recommendations(INPUT), "balanced", self.config["profiles"]["balanced"], 0.02)
        missing = next(x for x in rows if x["id"] == "R006")
        self.assertEqual(missing["status"], "HOLD_MISSING_ESTIMATE")
        self.assertIsNone(missing["priority_score"])
        self.assertEqual(missing["rank"], "")

    def test_zero_is_not_missing_and_confidence_not_weighted(self):
        record = p.load_recommendations(INPUT)[0]
        record.update(quality=0, security=0, delivery=0, complexity=0, confidence=0)
        result = p.score_record(record, self.config["profiles"]["balanced"])
        self.assertEqual(result["status"], "RANKED")
        self.assertEqual(result["priority_score"], 0)

    def test_direct_scoring_rejects_invalid_estimates(self):
        for value in [float("nan"), float("inf"), True, "4", 6, -1]:
            record = p.load_recommendations(INPUT)[0]
            record["quality"] = value
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                p.score_record(record, self.config["profiles"]["balanced"])

    def test_direct_ranking_validates_epsilon(self):
        with self.assertRaises(ValueError):
            p.rank_profile(p.load_recommendations(INPUT), "balanced", self.config["profiles"]["balanced"], float("nan"))

    def test_arithmetic_overflow_rejected_before_output(self):
        cfg = copy.deepcopy(self.config)
        cfg["profiles"]["balanced"]["complexity"] = 1e308
        out = self.root / "out"
        with self.assertRaises(ValueError):
            p.run(INPUT, self.config_file(cfg), out)
        self.assertFalse(out.exists())

    def test_invalid_input_creates_no_output(self):
        cfg = copy.deepcopy(self.config)
        cfg["tie_epsilon"] = float("nan")
        out = self.root / "out"
        with self.assertRaises(ValueError):
            p.run(INPUT, self.config_file(cfg), out)
        self.assertFalse(out.exists())

    def test_nonempty_directory_never_overwritten(self):
        out = self.root / "out"
        out.mkdir()
        (out / "report.md").write_text("operator evidence", encoding="utf-8")
        before = self.tree_bytes(out)
        with self.assertRaises((ValueError, OSError)):
            p.run(INPUT, WEIGHTS, out)
        self.assertEqual(before, self.tree_bytes(out))

    def test_rerun_requires_new_or_empty_destination(self):
        out = self.root / "out"
        p.run(INPUT, WEIGHTS, out)
        before = self.tree_bytes(out)
        with self.assertRaises((ValueError, OSError)):
            p.run(INPUT, WEIGHTS, out)
        self.assertEqual(before, self.tree_bytes(out))

    def test_output_directory_symlink_refused(self):
        target = self.root / "target"
        target.mkdir()
        out = self.root / "out"
        out.symlink_to(target, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            p.run(INPUT, WEIGHTS, out)
        self.assertEqual(self.tree_bytes(target), {})

    def test_regular_file_destination_preserved(self):
        out = self.root / "out"
        out.write_bytes(b"source evidence")
        with self.assertRaises((ValueError, OSError)):
            p.run(INPUT, WEIGHTS, out)
        self.assertEqual(out.read_bytes(), b"source evidence")

    def test_render_failure_leaves_destination_empty(self):
        out = self.root / "out"
        out.mkdir()
        with mock.patch.object(p, "render_report", side_effect=ValueError("fixture renderer failure")):
            with self.assertRaises(ValueError):
                p.run(INPUT, WEIGHTS, out)
        self.assertEqual(self.tree_bytes(out), {})

    def test_bundle_manifest_binds_snapshots_and_outputs(self):
        out = self.root / "out"
        p.run(INPUT, WEIGHTS, out)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["source_sha256"]["recommendations"], hashlib.sha256(INPUT.read_bytes()).hexdigest())
        self.assertEqual(manifest["source_sha256"]["weights"], hashlib.sha256(WEIGHTS.read_bytes()).hexdigest())
        self.assertEqual(manifest["record_count"], 7)
        self.assertEqual(manifest["profile_count"], 5)
        self.assertEqual(len(manifest["outputs"]), 7)
        for name, digest in manifest["outputs"].items():
            self.assertEqual(digest, hashlib.sha256((out / name).read_bytes()).hexdigest())
        self.assertFalse((out / ".incomplete").exists())

    def test_input_read_once_per_run(self):
        original = Path.read_bytes
        counts = {INPUT: 0, WEIGHTS: 0}
        def observed(path):
            if path in counts:
                counts[path] += 1
            return original(path)
        with mock.patch.object(Path, "read_bytes", observed):
            p.run(INPUT, WEIGHTS, self.root / "out")
        self.assertEqual(counts, {INPUT: 1, WEIGHTS: 1})

    def test_publish_failure_is_marked_incomplete(self):
        out = self.root / "out"
        original = Path.open
        def fail_one(path, mode='r', *args, **kwargs):
            if path == out / "ranking_balanced.csv" and "x" in mode:
                raise OSError("simulated write failure")
            return original(path, mode, *args, **kwargs)
        with mock.patch.object(Path, "open", fail_one), self.assertRaises(OSError):
            p.run(INPUT, WEIGHTS, out)
        self.assertTrue((out / ".incomplete").exists())
        self.assertFalse((out / "manifest.json").exists())

    def test_cli_bad_input_is_controlled_failure(self):
        cfg = self.config_file({"profiles": []})
        proc = subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), str(HERE / 'prioritize.py'), str(INPUT), str(cfg), '--out-dir', str(self.root / 'out')], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_markdown_escapes_cells_without_changing_csv(self):
        rows = [self.rows[0], self.rows[1].copy()]
        rows[1][1] = 'Finding | café <draft>\r\nsecond line'
        path = self.csv_file(rows)
        out = self.root / "out"
        p.run(path, WEIGHTS, out)
        report = (out / "report.md").read_text(encoding="utf-8")
        self.assertNotIn('<draft>', report)
        self.assertIn('&#124;', report)
        self.assertIn('&lt;draft&gt;', report)
        with (out / "ranking_balanced.csv").open(encoding="utf-8", newline="") as stream:
            exported = list(csv.DictReader(stream))
        self.assertEqual(exported[0]["title"], rows[1][1])

    def test_bundle_outputs_are_reproducible(self):
        first, second = self.root / "first", self.root / "second"
        p.run(INPUT, WEIGHTS, first)
        p.run(INPUT, WEIGHTS, second)
        self.assertEqual(self.tree_bytes(first), self.tree_bytes(second))


if __name__ == "__main__":
    unittest.main()
