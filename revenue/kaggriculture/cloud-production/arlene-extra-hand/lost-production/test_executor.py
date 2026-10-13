import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


alloc = load(HERE / "dated_allocation.py", "dated_allocation")
spec = importlib.util.spec_from_file_location("overlay", HERE / "overlay.py")
overlay = importlib.util.module_from_spec(spec)
overlay.agent = lambda obs: {"farmer": ["PASS"], "hands": [], "market": []}
overlay.select_optional_jobs = alloc.select_optional_jobs
overlay.MAX_ORDERS = 10; overlay.SHED_CAP = 100
spec.loader.exec_module(overlay)


class DatedAllocationTest(unittest.TestCase):
    def test_stock_is_shared_not_reserved_per_worker(self):
        req = [(10, "WHEAT", 6, "old-hand"), (10, "WHEAT", 6, "new-hand")]
        out = alloc.allocate_dated_stock(req, [(9, "WHEAT", 10, "shed")])
        self.assertEqual(sum(out["shorts"].values()), 2)

    def test_market_buy_cannot_fund_earlier_same_turn_pickup(self):
        req = [(10, "WHEAT", 1, "feed")]
        self.assertEqual(sum(alloc.allocate_dated_stock(req, [(11, "WHEAT", 1, "market")])["shorts"].values()), 1)

    def test_pipeline_counted_once(self):
        req = [(5, "WHEAT", 4, "a"), (7, "WHEAT", 4, "b")]
        out = alloc.allocate_dated_stock(req, [(4, "WHEAT", 6, "shed")])
        self.assertEqual(out["allocated"][("a", "WHEAT", 5)], 4)
        self.assertEqual(out["allocated"][("b", "WHEAT", 7)], 2)

    def test_optional_jobs_obey_worker_non_overlap(self):
        jobs = [{"id":"a","start_step":1,"end_step":4,"value":9},
                {"id":"b","start_step":3,"end_step":5,"value":20},
                {"id":"c","start_step":6,"end_step":7,"value":4}]
        self.assertEqual([j["id"] for j in alloc.select_optional_jobs(jobs, max_jobs=2)], ["b", "c"])


class LostProductionTest(unittest.TestCase):
    def observation(self, tile, step=215):
        tiles = [[None]*10 for _ in range(10)]; tiles[0][0] = tile
        return {"player":0,"step":step,"day":step//24,
                "farms":[{"farmer":[4,4],"hands":[],"tiles":tiles}],
                "private":{"shed":{},"inventories":[{}]}}

    def test_only_actual_animal_cap_overflow_is_incremental(self):
        tile = {"animal":"COW","placed_day":0,"yield_units":6,"fed_today":True,
                "consecutive_unfed":0,"pending_care_bonus":1}
        jobs = overlay._eh_incremental_jobs(self.observation(tile, step=239), 239)
        self.assertEqual((jobs[0]["economic_units"], jobs[0]["harvest_units"]), (2, 6))
        tile["yield_units"] = 3
        self.assertEqual(overlay._eh_incremental_jobs(self.observation(tile, step=239), 239), [])

    def test_escape_prevents_false_overflow_job(self):
        tile = {"animal":"COW","placed_day":0,"yield_units":6,"fed_today":False,
                "consecutive_unfed":1,"pending_care_bonus":1}
        self.assertEqual(overlay._eh_incremental_jobs(self.observation(tile), 215), [])

    def test_crop_job_is_limited_to_next_decay_unit(self):
        tile = {"kind":"PLANT","crop":"WHEAT","yield_units":4,"max_lifespan_step":218}
        jobs = overlay._eh_incremental_jobs(self.observation(tile), 239)
        self.assertEqual((jobs[0]["deadline"], jobs[0]["economic_units"], jobs[0]["harvest_units"]), (218,1,4))

    def test_base_harvest_action_order_precedes_same_step_decay(self):
        tile = {"kind":"PLANT","crop":"WHEAT","yield_units":4,"max_lifespan_step":218}
        job = overlay._eh_incremental_jobs(self.observation(tile), 239)[0]
        base_step = 218
        last_decay = min(239, base_step - 1)
        self.assertLess(last_decay, job["deadline"])

    def test_harvested_inventory_waits_for_eod_anywhere(self):
        overlay._EH_RESERVATIONS[0] = [{"day":8,"hand_index":0,"target":(0,0),"product":"MILK"}]
        obs = self.observation({"animal":"COW","yield_units":0}, step=215)
        obs["farms"][0]["hands"] = [[0,0]]; obs["private"]["inventories"] = [{}, {"MILK":3}]
        self.assertEqual(overlay._eh_action(obs, 0), ["PASS"])

    def test_sale_value_reprices_units_and_floor_does_not_advance_inventory(self):
        market = {"inventory":{"EGG":0}, "params":{}}
        prices = []
        old = overlay._eh_price
        try:
            overlay._eh_price = lambda item, inventory, market: {0:3, 1:1}.get(inventory, 1)
            self.assertEqual(overlay._eh_sale_value("EGG", 3, market), 5)
        finally:
            overlay._eh_price = old

    def test_future_base_harvest_reserves_shed_capacity(self):
        obs = self.observation({"animal":"GOOSE", "yield_units":4}, step=215)
        obs["farms"][0]["hands"] = [[0,0]]
        base = {"farmer":["PASS"], "hands":[["HARVEST"]], "market":[]}
        old = getattr(overlay, "_A", None)
        try:
            overlay._A = SimpleNamespace(
                R=[[{"farmer":["PASS"], "hands":[["PASS"]], "market":[]} for _ in range(216)]],
                cur=0)
            self.assertEqual(overlay._eh_base_harvest_commitment(obs, base, 215), 4)
        finally:
            if old is None:
                del overlay._A
            else:
                overlay._A = old


if __name__ == "__main__":
    unittest.main()
