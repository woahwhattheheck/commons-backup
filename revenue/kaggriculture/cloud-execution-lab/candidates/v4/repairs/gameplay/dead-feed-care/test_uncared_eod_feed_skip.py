from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uncared_eod_feed_skip", HERE / "uncared_eod_feed_skip.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CFG = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720}

def tile(species="GOOSE", *, placed=0, units=0, pending=0, unfed=0,
         fed=False, cared=False, fert=False):
    kind = {"GOOSE":"COOP","COW":"PASTURE","SHEEP":"PASTURE"}[species]
    return {"kind":kind,"animal":species,"placed_day":placed,"yield_units":units,
            "pending_care_bonus":pending,"consecutive_unfed":unfed,
            "fed_today":fed,"cared_today":cared,"fertilizer_available":fert}

def world(*, step=23, species="GOOSE", animal=None, wheat=1, hands=None, inventories=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[4][4] = animal if animal is not None else tile(species)
    handpos = copy.deepcopy(hands or [])
    farm0 = {"farmer":[4,4],"hands":handpos,"tiles":tiles}
    farm1 = {"farmer":[4,4],"hands":[],"tiles":[[None for _ in range(10)] for _ in range(10)]}
    invs = copy.deepcopy(inventories) if inventories is not None else [{"WHEAT": wheat}] + [{} for _ in handpos]
    return {"step":step,"player":0,"farms":[farm0,farm1],
            "private":{"inventories":invs,"shed":{},"seeds":{}}}

def action(farmer=("FEED",), hands=()):
    return {"farmer":list(farmer),"hands":[list(r) for r in hands],"market":[]}

class Tests(unittest.TestCase):
    def test_safe_last_hour_feed_suppressed(self):
        obs=world(step=23)
        raw=action()
        got=mod.apply_uncared_eod_feed_skip(raw,obs,CFG,enabled=True)
        self.assertEqual(got["farmer"],["PASS"])
        self.assertEqual(mod.plan_uncared_eod_feed_skip(raw,obs,CFG)[0]["guaranteed_wheat_saved"],1)
        self.assertEqual(raw["farmer"],["FEED"])

    def test_disabled_is_exact_identity_object(self):
        raw=action(); obs=world()
        self.assertIs(mod.apply_uncared_eod_feed_skip(raw,obs,CFG,enabled=False),raw)

    def test_only_hour23(self):
        for step in (22,24,46,718):
            with self.subTest(step=step):
                raw=action(); self.assertIs(mod.apply_uncared_eod_feed_skip(raw,world(step=step),CFG,enabled=True),raw)

    def test_unfed_one_must_feed_to_avoid_escape(self):
        raw=action(); obs=world(animal=tile(unfed=1))
        self.assertEqual(mod.plan_uncared_eod_feed_skip(raw,obs,CFG),[])

    def test_cared_or_already_fed_blocks(self):
        for kwargs in ({"cared":True},{"fed":True}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(mod.plan_uncared_eod_feed_skip(action(),world(animal=tile(**kwargs)),CFG),[])

    def test_pending_bonus_on_production_boundary_blocks(self):
        # Goose placed day0 produces at EOD day3 -> next_day4.
        obs=world(step=3*24+23, animal=tile(pending=1))
        self.assertEqual(mod.plan_uncared_eod_feed_skip(action(),obs,CFG),[])

    def test_pending_bonus_before_production_can_skip(self):
        # Cow placed day0 first produces on next_day8; day6->7 is nonproduction.
        obs=world(step=6*24+23, species="COW", animal=tile("COW",pending=2))
        self.assertEqual(len(mod.plan_uncared_eod_feed_skip(action(),obs,CFG)),1)

    def test_same_site_care_blocks(self):
        obs=world(hands=[[4,4]], inventories=[{"WHEAT":1},{}])
        raw=action(hands=(("CARE",),))
        self.assertEqual(mod.plan_uncared_eod_feed_skip(raw,obs,CFG),[])

    def test_repeated_feed_site_reserved_for_dead_feed_care(self):
        obs=world(hands=[[4,4]], inventories=[{"WHEAT":1},{"WHEAT":1}])
        raw=action(hands=(("FEED",),))
        self.assertEqual(mod.plan_uncared_eod_feed_skip(raw,obs,CFG),[])

    def test_no_physical_wheat_no_rewrite(self):
        self.assertEqual(mod.plan_uncared_eod_feed_skip(action(),world(wheat=0),CFG),[])

    def test_two_distinct_sites_rewrite_without_compaction(self):
        obs=world(hands=[[5,4]], inventories=[{"WHEAT":1},{"WHEAT":1}])
        obs["farms"][0]["tiles"][4][5]=tile("SHEEP")
        raw=action(hands=(("FEED",),))
        got=mod.apply_uncared_eod_feed_skip(raw,obs,CFG,enabled=True)
        self.assertEqual(got,{"farmer":["PASS"],"hands":[["PASS"]],"market":[]})
        self.assertEqual(len(mod.plan_uncared_eod_feed_skip(raw,obs,CFG)),2)

    def test_all_species_block_pending_bonus_on_each_production_boundary(self):
        first_interval = {"GOOSE": (4, 1), "COW": (8, 2), "SHEEP": (6, 3)}
        for species, (first, interval) in first_interval.items():
            for next_day in range(first, 30, interval):
                day = next_day - 1
                step = day * 24 + 23
                if step > 718:
                    continue
                with self.subTest(species=species, next_day=next_day):
                    obs = world(step=step, species=species,
                                animal=tile(species, pending=1))
                    self.assertEqual(mod.plan_uncared_eod_feed_skip(action(), obs, CFG), [])

    def test_all_species_allow_clean_streak0_final_hour(self):
        for species in ("GOOSE", "COW", "SHEEP"):
            with self.subTest(species=species):
                obs = world(step=23, species=species, animal=tile(species))
                changes = mod.plan_uncared_eod_feed_skip(action(), obs, CFG)
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0]["species"], species)

    def test_transform_preserves_market_and_unrelated_rows(self):
        obs = world(step=23, hands=[[5,4]], inventories=[{"WHEAT":1},{}])
        raw = {"farmer":["FEED"], "hands":[["NORTH"]],
               "market":[["SELL","EGG",2],["HIRE"]]}
        snapshot = copy.deepcopy(raw)
        got = mod.apply_uncared_eod_feed_skip(raw, obs, CFG, enabled=True)
        self.assertEqual(got["farmer"], ["PASS"])
        self.assertEqual(got["hands"], [["NORTH"]])
        self.assertEqual(got["market"], snapshot["market"])
        self.assertEqual(raw, snapshot)

    def test_malformed_or_nondefault_fails_closed(self):
        raw=action(); obs=world()
        bad_cfgs=[{}, {**CFG,"turnsPerDay":23}, {**CFG,"boardSize":True}]
        for cfg in bad_cfgs:
            with self.subTest(cfg=cfg):
                self.assertIs(mod.apply_uncared_eod_feed_skip(raw,obs,cfg,enabled=True),raw)
        poisoned=world(animal=tile())
        poisoned["farms"][0]["tiles"][4][4]["consecutive_unfed"]=True
        self.assertIs(mod.apply_uncared_eod_feed_skip(raw,poisoned,CFG,enabled=True),raw)

if __name__ == "__main__": unittest.main()
