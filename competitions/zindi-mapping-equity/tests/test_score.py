import csv,math,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from score import SCHOOL_CATEGORIES,ScoreInputError,ratio_gap,score_aggregate,write_submission

def row(**changes):
    base={"GEOID":"04013010101","overture_road_m":50,"tiger_road_m":100,"overture_buildings":80,"microsoft_buildings":100,"overture_pois":90,"cbp_establishments":100,"overture_fire":4,"hifld_fire":5,"overture_ems":3,"hifld_ems":3,"overture_schools":8,"hifld_schools":10}; base.update(changes); return base
class ScoreContractTests(unittest.TestCase):
    def test_overcoverage_is_capped_at_zero_gap(self): self.assertEqual(ratio_gap(11,10),0.0); self.assertEqual(ratio_gap(10,10),0.0)
    def test_zero_reference_is_undefined(self): self.assertIsNone(ratio_gap(0,0)); self.assertIsNone(ratio_gap(50,0))
    def test_variable_divisor_excludes_undefined_component(self):
        r=score_aggregate(row(tiger_road_m=0,overture_road_m=999,microsoft_buildings=100,overture_buildings=50,hifld_fire=0,hifld_ems=0,hifld_schools=0,cbp_establishments=100,overture_pois=75)); self.assertIsNone(r.transport_gap); self.assertAlmostEqual(r.building_gap,.5); self.assertAlmostEqual(r.poi_gap,.25); self.assertAlmostEqual(r.coverage_gap_score,.375)
    def test_facility_half_means_only_defined_types(self):
        r=score_aggregate(row(hifld_fire=10,overture_fire=5,hifld_ems=0,overture_ems=999,hifld_schools=10,overture_schools=10,cbp_establishments=0,overture_pois=999)); self.assertAlmostEqual(r.poi_gap_fire,.5); self.assertIsNone(r.poi_gap_ems); self.assertAlmostEqual(r.poi_gap_schools,0); self.assertAlmostEqual(r.poi_gap_hifld,.25); self.assertIsNone(r.poi_gap_cbp); self.assertAlmostEqual(r.poi_gap,.25)
    def test_poi_is_mean_of_two_halves_not_four_raw_terms(self):
        r=score_aggregate(row(hifld_fire=10,overture_fire=0,hifld_ems=10,overture_ems=10,hifld_schools=10,overture_schools=10,cbp_establishments=10,overture_pois=0)); self.assertAlmostEqual(r.poi_gap_hifld,1/3); self.assertAlmostEqual(r.poi_gap_cbp,1); self.assertAlmostEqual(r.poi_gap,2/3)
    def test_geoid_leading_zero_survives_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"submission.csv"; write_submission([score_aggregate(row())],p); parsed=list(csv.DictReader(p.open(newline="",encoding="utf-8")))
        self.assertEqual(parsed[0]["GEOID"],"04013010101")
    def test_integer_or_short_geoid_fails_closed(self):
        with self.assertRaises(ScoreInputError): score_aggregate(row(GEOID=4013010101))
        with self.assertRaises(ScoreInputError): score_aggregate(row(GEOID="4013010101"))
    def test_negative_nan_and_infinity_fail_closed(self):
        for value in (-1,math.nan,math.inf,-math.inf):
            with self.assertRaises(ScoreInputError): score_aggregate(row(overture_pois=value))
    def test_all_components_undefined_fails_closed(self):
        with self.assertRaises(ScoreInputError): score_aggregate(row(tiger_road_m=0,microsoft_buildings=0,hifld_fire=0,hifld_ems=0,hifld_schools=0,cbp_establishments=0))
    def test_school_category_set_matches_challenge(self): self.assertEqual(SCHOOL_CATEGORIES,{"elementary_school","middle_school","high_school","school","private_school","public_school"})
if __name__=="__main__": unittest.main()
