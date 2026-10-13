#!/usr/bin/env python3
import json
import pathlib
import tempfile
import unittest
import counter_ambush as c

class ComebackTests(unittest.TestCase):
    def test_base_prices(self):
        self.assertEqual(c.market_price("STRAWBERRY", 10000), 120)
        self.assertEqual(c.market_price("FERTILIZER", 10000), 100)
    def test_sell_floor_does_not_add_supply(self):
        r = c.sell_units("STRAWBERRY", 10100, 2)
        self.assertEqual(r["prices"], [1, 1])
        self.assertEqual(r["ending_inventory"], 10100)
    def test_buy_uses_post_buy_quote(self):
        self.assertEqual(c.buy_product_units("FERTILIZER", 10000, 1)["prices"], [100])
    def test_town_drain_strawberry_380(self):
        shops=("BRUNCH_SPOT","ICE_CREAM_SHOP","SMOOTHIE_SHOP","FARMERS_MARKET")*2
        self.assertEqual(c.town_drain("STRAWBERRY", 380, shops), 8)
        self.assertEqual(c.town_drain("STRAWBERRY", 402, shops), 0)
    def test_step380_source_real_quantity_is_attenuated_by_town(self):
        shops=("BRUNCH_SPOT","ICE_CREAM_SHOP","SMOOTHIE_SHOP","FARMERS_MARKET")*2
        r=c.predump_counterfactual(item="STRAWBERRY",starting_inventory=10000,own_units=8,rival_units=8,pre_step=380,unlocked_shops=shops)
        self.assertEqual((r["town_drain_after_pre"],r["own_timing_gain"],r["rival_suppression"],r["gross_relative_margin_swing"]),(8,0,193,193))
    def test_step402_source_real_quantity_is_cleaner_boundary(self):
        r=c.predump_counterfactual(item="STRAWBERRY",starting_inventory=10000,own_units=8,rival_units=8,pre_step=402)
        self.assertEqual((r["town_drain_after_pre"],r["own_timing_gain"],r["rival_suppression"],r["gross_relative_margin_swing"]),(0,121,121,242))
    def test_fertilizer_source_real_max_four_discount_is_tiny(self):
        r=c.fertilizer_sponge(starting_inventory=10000,rival_sell_units=4,our_buy_units=4,target_crop="WHEAT",observed_crop_price=25)
        self.assertEqual(r["rival_market_units_added"],4)
        self.assertEqual(r["our_buy_cost_after_dump"],399)
        self.assertEqual(r["our_buy_cost_without_dump"],402)
        self.assertEqual(r["opponent_created_purchase_discount"],3)
        self.assertEqual(r["minimum_crop_sale_price_for_gross_ceiling_break_even"],50)
        self.assertEqual(r["gross_crop_value_ceiling"],200)
        self.assertFalse(r["gross_ceiling_covers_fertilizer_cost"])
    def test_fertilizer_floor_control_has_zero_subsidy(self):
        r=c.fertilizer_sponge(starting_inventory=10493,rival_sell_units=4,our_buy_units=4)
        self.assertEqual(r["rival_market_units_added"],0)
        self.assertEqual(r["opponent_created_purchase_discount"],0)
    def test_fertilizer_timing(self):
        self.assertEqual(c.earliest_fertilize_step(523),525)
        self.assertEqual(c.earliest_fertilize_step(523,3),528)
    def test_bonus_ceilings(self):
        self.assertEqual(c.source_bonus_ceiling_per_fertilizer("WHEAT"),2)
        self.assertEqual(c.source_bonus_ceiling_per_fertilizer("TOMATO"),3)
    def test_report_consumes_authenticated_apex_contract(self):
        r=c.sample_report()
        self.assertTrue(r["schedule_authenticated"])
        self.assertEqual(r["authenticated_apex_schedule"]["FERTILIZER"],(522,))
        self.assertEqual(r["apex_contract"]["events"][-1]["max_sell"],4)
        self.assertNotIn("fert40_buy10_wheat_base", r)
    def test_apex_source_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            apex=root/"main.py"; apex.write_text("x=1\n")
            manifest=root/"REFERENCE-POLICIES.json"
            manifest.write_text(json.dumps({"policies":{"apex_v7":{"files":{"main.py":c.APEX_MAIN_SHA256}}}}))
            with self.assertRaisesRegex(RuntimeError,"Apex source drift"):
                c.verify_apex_source(apex,manifest)
    def test_apex_manifest_pin_fails_closed_after_exact_source_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            apex=root/"main.py"; apex.write_bytes(b"x")
            original=c.APEX_MAIN_SHA256
            try:
                c.APEX_MAIN_SHA256=c._sha256(b"x")
                manifest=root/"REFERENCE-POLICIES.json"
                manifest.write_text(json.dumps({"policies":{"apex_v7":{"files":{"main.py":"wrong"}}}}))
                with self.assertRaisesRegex(RuntimeError,"reference-policy-bank"):
                    c.verify_apex_source(apex,manifest)
            finally:
                c.APEX_MAIN_SHA256=original
    def test_source_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/"engine.py"; p.write_text("x=1\n")
            with self.assertRaisesRegex(RuntimeError,"engine drift"):
                c.verify_engine(p)
    def test_negative_distance_refused(self):
        with self.assertRaises(ValueError): c.earliest_fertilize_step(523,-1)

if __name__ == "__main__": unittest.main()
