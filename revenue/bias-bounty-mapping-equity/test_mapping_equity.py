import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mapping_equity as m


def agg(geoid="04013000100", **kw):
    base = dict(
        GEOID=geoid,
        overture_road_length=80,
        tiger_road_length=100,
        overture_buildings=90,
        microsoft_buildings=100,
        overture_fire=1,
        hifld_fire=2,
        overture_ems=1,
        hifld_ems=1,
        overture_schools=4,
        hifld_schools=4,
        overture_places=80,
        cbp_establishments=100,
    )
    base.update(kw)
    return m.TractAggregate.from_mapping(base)


class ScoreTests(unittest.TestCase):
    def test_deficit_formula(self):
        self.assertAlmostEqual(m.coverage_deficit(3, 4, name="x"), 0.25)
        self.assertEqual(m.coverage_deficit(5, 4, name="x"), 0.0)
        self.assertIsNone(m.coverage_deficit(0, 0, name="x"))

    def test_negative_and_bool_rejected(self):
        with self.assertRaises(m.MappingEquityError):
            m.coverage_deficit(-1, 2, name="x")
        with self.assertRaises(m.MappingEquityError):
            m.coverage_deficit(True, 2, name="x")

    def test_full_component_math(self):
        score = m.score_tract(agg())
        self.assertAlmostEqual(score.transport_gap, 0.2)
        self.assertAlmostEqual(score.building_gap, 0.1)
        self.assertAlmostEqual(score.poi_gap_fire, 0.5)
        self.assertEqual(score.poi_gap_ems, 0.0)
        self.assertEqual(score.poi_gap_schools, 0.0)
        self.assertAlmostEqual(score.poi_gap_hifld, 1 / 6)
        self.assertAlmostEqual(score.poi_gap_cbp, 0.2)
        self.assertAlmostEqual(score.poi_gap, (1 / 6 + 0.2) / 2)
        self.assertAlmostEqual(score.coverage_gap_score, (0.2 + 0.1 + score.poi_gap) / 3)

    def test_hifld_mean_uses_defined_types_only(self):
        score = m.score_tract(agg(hifld_ems=0, hifld_schools=0))
        self.assertAlmostEqual(score.poi_gap_hifld, 0.5)

    def test_poi_cbp_only_when_no_facility_reference(self):
        score = m.score_tract(agg(hifld_fire=0, hifld_ems=0, hifld_schools=0))
        self.assertIsNone(score.poi_gap_hifld)
        self.assertAlmostEqual(score.poi_gap, 0.2)

    def test_poi_hifld_only_when_no_cbp_reference(self):
        score = m.score_tract(agg(cbp_establishments=0))
        self.assertAlmostEqual(score.poi_gap, 1 / 6)

    def test_zero_transport_and_building_reference_excluded(self):
        score = m.score_tract(agg(tiger_road_length=0, microsoft_buildings=0))
        self.assertIsNone(score.transport_gap)
        self.assertIsNone(score.building_gap)
        self.assertAlmostEqual(score.coverage_gap_score, score.poi_gap)

    def test_all_undefined_is_not_scorable(self):
        with self.assertRaisesRegex(m.MappingEquityError, "not scorable"):
            m.score_tract(agg(
                tiger_road_length=0,
                microsoft_buildings=0,
                hifld_fire=0,
                hifld_ems=0,
                hifld_schools=0,
                cbp_establishments=0,
            ))

    def test_geoid_must_be_text_and_keep_leading_zero(self):
        self.assertEqual(agg().geoid, "04013000100")
        for bad in (4013000100, "4013000100", "0401300010x", " 04013000100"):
            row = dict(GEOID=bad,
                overture_road_length=1, tiger_road_length=1,
                overture_buildings=1, microsoft_buildings=1,
                overture_fire=0, hifld_fire=0, overture_ems=0, hifld_ems=0,
                overture_schools=0, hifld_schools=0,
                overture_places=1, cbp_establishments=1)
            with self.assertRaises(m.MappingEquityError):
                m.TractAggregate.from_mapping(row)

    def test_score_all_is_order_invariant_and_rejects_duplicates(self):
        a = agg("04013000100")
        b = agg("35023970000", overture_buildings=50)
        self.assertEqual([x.geoid for x in m.score_all([b, a])], [a.geoid, b.geoid])
        with self.assertRaisesRegex(m.MappingEquityError, "duplicate"):
            m.score_all([a, a])


class SubmissionTests(unittest.TestCase):
    def scores(self):
        return m.score_all([agg("35023970000", overture_buildings=50), agg("04013000100")])

    def test_compiler_preserves_authoritative_order(self):
        csv_text, receipt = m.compile_submission(self.scores(), ["35023970000", "04013000100"])
        lines = csv_text.splitlines()
        self.assertEqual(lines[0], "GEOID,coverage_gap_score")
        self.assertTrue(lines[1].startswith("35023970000,"))
        self.assertTrue(lines[2].startswith("04013000100,"))
        verified = m.verify_submission(csv_text, receipt, ["35023970000", "04013000100"])
        self.assertTrue(verified["verified"])

    def test_deterministic_bytes(self):
        one = m.compile_submission(self.scores(), ["04013000100", "35023970000"])
        two = m.compile_submission(list(reversed(self.scores())), ["04013000100", "35023970000"])
        self.assertEqual(one, two)

    def test_missing_extra_duplicate_universe_rejected(self):
        scores = self.scores()
        with self.assertRaisesRegex(m.MappingEquityError, "missing"):
            m.compile_submission(scores[:1], ["04013000100", "35023970000"])
        with self.assertRaisesRegex(m.MappingEquityError, "extra"):
            m.compile_submission(scores, ["04013000100"])
        with self.assertRaisesRegex(m.MappingEquityError, "duplicate GEOID"):
            m.compile_submission(scores, ["04013000100", "04013000100"])

    def test_csv_tamper_rejected(self):
        csv_text, receipt = m.compile_submission(self.scores(), ["04013000100", "35023970000"])
        tampered = csv_text.replace("0.", "0.9", 1)
        with self.assertRaisesRegex(m.MappingEquityError, "CSV digest"):
            m.verify_submission(tampered, receipt, ["04013000100", "35023970000"])

    def test_receipt_tamper_rejected(self):
        csv_text, receipt = m.compile_submission(self.scores(), ["04013000100", "35023970000"])
        envelope = json.loads(receipt)
        envelope["payload"]["row_count"] = 99
        tampered = json.dumps(envelope)
        with self.assertRaisesRegex(m.MappingEquityError, "payload digest"):
            m.verify_submission(csv_text, tampered, ["04013000100", "35023970000"])

    def test_authoritative_order_tamper_rejected(self):
        csv_text, receipt = m.compile_submission(self.scores(), ["04013000100", "35023970000"])
        with self.assertRaises(m.MappingEquityError):
            m.verify_submission(csv_text, receipt, ["35023970000", "04013000100"])

    def test_receipt_rows_must_match_csv_scores(self):
        csv_text, receipt = m.compile_submission(self.scores(), ["04013000100", "35023970000"])
        envelope = json.loads(receipt)
        envelope["payload"]["rows"][0]["coverage_gap_score"] = 0.123456789
        body = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        import hashlib
        envelope["payload_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(m.MappingEquityError, "receipt/CSV score mismatch"):
            m.verify_submission(csv_text, json.dumps(envelope), ["04013000100", "35023970000"])

    def test_reference_score_column_is_rejected_from_aggregate_input(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "leaky.csv"
            p.write_text(",".join(m.AGGREGATE_COLUMNS) + ",coverage_gap_score\n" +
                         "04013000100,80,100,90,100,1,2,1,1,4,4,80,100,0.0\n", encoding="utf-8")
            with self.assertRaisesRegex(m.MappingEquityError, "columns must exactly match"):
                m.read_aggregate_csv(p)


class CliTests(unittest.TestCase):
    def write_inputs(self, root):
        agg_path = root / "aggregates.csv"
        auth_path = root / "sample.csv"
        agg_path.write_text(
            ",".join(m.AGGREGATE_COLUMNS) + "\n" +
            "04013000100,80,100,90,100,1,2,1,1,4,4,80,100\n" +
            "35023970000,40,100,50,100,0,0,0,0,0,0,20,100\n",
            encoding="utf-8",
        )
        auth_path.write_text("GEOID,coverage_gap_score\n35023970000,0\n04013000100,0\n", encoding="utf-8")
        return agg_path, auth_path

    def test_cli_build_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            aggregates, authoritative = self.write_inputs(root)
            submission = root / "submission.csv"
            receipt = root / "receipt.json"
            cmd = [sys.executable, str(HERE / "mapping_equity.py"), "build",
                   "--aggregates", str(aggregates), "--authoritative", str(authoritative),
                   "--output", str(submission), "--receipt", str(receipt)]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertIn('"verified": true', result.stdout)
            verify = subprocess.run(
                [sys.executable, str(HERE / "mapping_equity.py"), "verify",
                 "--submission", str(submission), "--receipt", str(receipt),
                 "--authoritative", str(authoritative)],
                check=True, capture_output=True, text=True,
            )
            self.assertIn('"row_count": 2', verify.stdout)

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            aggregates, authoritative = self.write_inputs(root)
            submission = root / "submission.csv"
            receipt = root / "receipt.json"
            submission.write_text("occupied", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(HERE / "mapping_equity.py"), "build",
                 "--aggregates", str(aggregates), "--authoritative", str(authoritative),
                 "--output", str(submission), "--receipt", str(receipt)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(submission.read_text(encoding="utf-8"), "occupied")

    def test_blank_aggregate_cell_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.csv"
            p.write_text(",".join(m.AGGREGATE_COLUMNS) + "\n04013000100,,1,1,1,0,0,0,0,0,0,1,1\n", encoding="utf-8")
            with self.assertRaisesRegex(m.MappingEquityError, "blank"):
                m.read_aggregate_csv(p)


if __name__ == "__main__":
    unittest.main()
