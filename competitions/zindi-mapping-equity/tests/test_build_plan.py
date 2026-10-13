import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_submission import BASE,OVERTURE_RELEASE,REGIONS,region_sql
class BuildPlanTests(unittest.TestCase):
    def test_every_region_plan_uses_only_raw_layers(self):
        for region in REGIONS:
            sql=region_sql(region); self.assertIn(BASE,sql); self.assertIn("sample-submission.csv",sql); self.assertNotIn("-coverage-gap.",sql); self.assertNotIn("coverage_gap_score",sql)
    def test_exact_scored_road_classes_are_present(self):
        sql=region_sql("eastern-ok")
        for value in ("motorway","trunk","primary","secondary","S1100","S1200"): self.assertIn(value,sql)
        self.assertNotIn("tertiary",sql); self.assertNotIn("residential",sql)
    def test_exact_poi_categories_and_no_hospitals(self):
        sql=region_sql("maricopa-az")
        for value in ("fire_department","ambulance_and_ems_services","elementary_school","middle_school","high_school","school","private_school","public_school"): self.assertIn(value,sql)
        self.assertNotIn("hospital",sql)
    def test_projected_length_has_explicit_axis_order(self):
        sql=region_sql("northern-ca"); self.assertGreaterEqual(sql.count("always_xy := true"),2); self.assertGreaterEqual(sql.count("EPSG:5070"),2)
    def test_point_features_have_one_tract_boundary_tiebreak(self):
        sql=region_sql("northern-ca"); self.assertEqual(sql.count("QUALIFY ROW_NUMBER() OVER (PARTITION BY p.feature_id ORDER BY t.GEOID)=1"),4)
    def test_building_assignment_policy_is_explicit(self):
        self.assertIn("ST_Centroid(b.geometry)",region_sql("south-central-tx","centroid")); self.assertNotIn("ST_Centroid(b.geometry)",region_sql("south-central-tx","intersects"))
    def test_overture_release_is_pinned_as_metadata(self): self.assertEqual(OVERTURE_RELEASE,"2026-08-19.0")
if __name__=="__main__": unittest.main()
