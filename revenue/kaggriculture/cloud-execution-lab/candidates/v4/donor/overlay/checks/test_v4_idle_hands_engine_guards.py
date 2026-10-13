# SPDX-License-Identifier: Apache-2.0
"""Mechanism tests against the preserved official engine, not an economics gate.

Set TITAN_RUNTIME_ROOT to a materialized package containing checks/reference.
Run: python -m unittest -v test_v4_idle_hands_engine_guards (also with python -O).
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import unittest
from types import SimpleNamespace

import r04_idle_hands as ih

ROOT = Path(os.environ.get("TITAN_RUNTIME_ROOT", Path(__file__).resolve().parents[1]))
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def load_engine():
    reference = ROOT / "checks" / "reference"
    engine_file = reference / "engine" / "kaggriculture.py"
    raw = engine_file.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != ENGINE_BLOB:
        raise RuntimeError("Pinned official engine mismatch: " + actual)
    path = reference / "evaluator" / "evaluate.py"
    spec = importlib.util.spec_from_file_location("fir_idle_reference_evaluator", path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    engine, hashes = evaluator.get_engine(reference / "engine", reference / "evaluator" / "loader.py")
    return engine, hashes


class IdleHands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.hashes = load_engine()

    def fixture(self, animal="GOOSE", *, day=8, hour=12, player=0, hand=False):
        e = self.engine
        farms = [e._new_farm(10, 3000), e._new_farm(10, 3000)]
        private = e._new_private()
        own = farms[player]
        own["farmer"] = [1, 1]
        own["tiles"][1][1] = e._new_animal(animal, 0)
        private["inventories"] = [{"WHEAT": 2}]
        action = {"farmer": ["PASS"], "hands": [], "market": [[], ["SELL", "WOOL", 2]], "extra": {"n": [7]}}
        if hand:
            own["farmer"] = [0, 0]
            own["hands"] = [[1, 1]]
            private["inventories"] = [{}, {"WHEAT": 2}]
            action["hands"] = [["PASS"]]
        observation = {"step": day * 24 + hour, "day": day, "hour": hour,
                       "player": player, "farms": farms, "private": private,
                       "market": e._new_market()}
        configuration = dict(ih._STANDARD)
        return action, observation, configuration

    def tile(self, observation):
        return observation["farms"][observation["player"]]["tiles"][1][1]

    def wheat(self, *, age=2, day=8, hour=12):
        action, obs, cfg = self.fixture(day=day, hour=hour)
        tile = self.engine._new_plant("WHEAT", day-age, 24)
        tile["consecutive_unwatered"] = 0
        obs["farms"][0]["tiles"][1][1] = tile
        obs["private"]["inventories"] = [{"FERTILIZER": 1}]
        return action, obs, cfg

    def execute(self, observation, action):
        obs = copy.deepcopy(observation)
        farm = obs["farms"][obs["player"]]
        for actor, row in enumerate([action["farmer"], *action["hands"]]):
            self.engine._apply_unit_action(farm, obs["private"], actor, row, 10, obs["day"], 24, 100)
        return obs

    def test_01_engine_identity(self):
        self.assertEqual(self.hashes["kaggriculture.py"], "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e")
        self.assertEqual(self.engine.CROPS["WHEAT"]["max_yield"], 6)

    def test_02_all_off_exact_identity(self):
        a,o,c = self.fixture()
        self.assertIs(ih.apply_all(a,o,c),a)
        self.assertIs(ih.apply_feed(a,o,c),a)
        self.assertIs(ih.apply_care(a,o,c),a)
        self.assertIs(ih.apply_wheat_fertilize(a,o,c),a)

    def test_03_feed_real_engine_all_species_seats_actors(self):
        for animal in self.engine.ANIMALS:
            for player in (0,1):
                for hand in (False,True):
                    with self.subTest(animal=animal,player=player,hand=hand):
                        a,o,c = self.fixture(animal,player=player,hand=hand)
                        r = ih.apply_feed(a,o,c,enabled=True)
                        self.assertEqual(r["hands"][0] if hand else r["farmer"],["FEED"])
                        out = self.execute(o,r)
                        self.assertIs(self.tile(out)["fed_today"],True)
                        self.assertEqual(out["private"]["inventories"][int(hand)]["WHEAT"],1)

    def test_04_feed_preserves_animal_at_escape_boundary(self):
        a,o,c = self.fixture(hour=23)
        self.tile(o)["consecutive_unfed"] = 1
        base, candidate = self.execute(o,a), self.execute(o,ih.apply_feed(a,o,c,enabled=True))
        for obj in (base,candidate):
            self.engine._daily_refresh_animals(obj["farms"][0],obj["day"])
        self.assertNotIn("animal",self.tile(base))
        self.assertEqual(self.tile(candidate)["animal"],"GOOSE")

    def test_05_feed_already_fed(self):
        a,o,c = self.fixture(); self.tile(o)["fed_today"] = True
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_06_feed_requires_carried_not_shed_wheat(self):
        a,o,c = self.fixture(); o["private"]["inventories"] = [{}]; o["private"]["shed"]["WHEAT"] = 99
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_07_same_turn_purchase_is_not_carried_feed(self):
        a,o,c = self.fixture(); o["private"]["inventories"] = [{}]; a["market"] = [["BUY_PRODUCT","WHEAT",2]]
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_08_feed_terminal_partial_day(self):
        for step in (695,696,718):
            a,o,c = self.fixture(day=step//24,hour=step%24)
            self.assertEqual(ih.apply_feed(a,o,c,enabled=True) is a,step>695)

    def test_09_care_all_species(self):
        for animal in self.engine.ANIMALS:
            a,o,c = self.fixture(animal); self.tile(o)["fed_today"] = True
            r = ih.apply_care(a,o,c,enabled=True)
            self.assertEqual(r["farmer"],["CARE"])
            self.assertIs(self.tile(self.execute(o,r))["cared_today"],True)

    def test_10_goose_only_never_cares_cow_or_sheep(self):
        for animal in self.engine.ANIMALS:
            a,o,c = self.fixture(animal); self.tile(o)["fed_today"] = True
            self.assertEqual(ih.apply_care(a,o,c,enabled=True,goose_only=True) is a,animal!="GOOSE")

    def test_11_care_requires_fed_uncared(self):
        for fed,cared in ((False,False),(False,True),(True,True)):
            a,o,c = self.fixture(); self.tile(o).update(fed_today=fed,cared_today=cared)
            self.assertIs(ih.apply_care(a,o,c,enabled=True),a)

    def test_12_care_bonus_is_delayed_not_same_refresh(self):
        a,o,c = self.fixture(); self.tile(o)["fed_today"] = True
        b = self.execute(o,a); r = self.execute(o,ih.apply_care(a,o,c,enabled=True))
        for obj in (b,r): self.engine._daily_refresh_animals(obj["farms"][0],8)
        self.assertEqual(self.tile(b)["yield_units"],1)
        self.assertEqual(self.tile(r)["yield_units"],1)
        self.assertEqual(self.tile(r)["pending_care_bonus"],1)
        for obj in (b,r):
            self.tile(obj)["fed_today"] = True
            self.engine._daily_refresh_animals(obj["farms"][0],9)
        self.assertEqual(self.tile(r)["yield_units"]-self.tile(b)["yield_units"],1)

    def test_13_care_bonus_needs_later_fed_production(self):
        a,o,c = self.fixture(); self.tile(o)["fed_today"] = True
        b = self.execute(o,a); r = self.execute(o,ih.apply_care(a,o,c,enabled=True))
        for obj in (b,r):
            self.engine._daily_refresh_animals(obj["farms"][0],8)
            self.engine._daily_refresh_animals(obj["farms"][0],9)
        self.assertEqual(self.tile(r)["yield_units"],self.tile(b)["yield_units"])

    def test_14_care_terminal_production_horizon(self):
        for animal,day,expected in (("GOOSE",27,True),("GOOSE",28,False),
                                   ("COW",26,True),("COW",27,False),
                                   ("SHEEP",25,True),("SHEEP",26,False)):
            a,o,c = self.fixture(animal,day=day); self.tile(o)["fed_today"] = True
            self.assertEqual(ih.apply_care(a,o,c,enabled=True) is not a,expected,(animal,day))

    def test_15_wheat_fertilize_then_water_real_yield(self):
        for age in (2,3,4):
            a,o,c = self.wheat(age=age)
            r = ih.apply_wheat_fertilize(a,o,c,enabled=True)
            self.assertEqual(r["farmer"],["FERTILIZE"])
            b, f = self.execute(o,a),self.execute(o,r)
            self.assertEqual(self.tile(b)["yield_units"],self.tile(f)["yield_units"])
            for obj in (b,f):
                self.engine._apply_unit_action(obj["farms"][0],obj["private"],0,["WATER"],10,8,24)
            self.assertEqual(self.tile(f)["yield_units"]-self.tile(b)["yield_units"],1)
            self.assertNotIn("FERTILIZER",f["private"]["inventories"][0])
            self.assertEqual(self.tile(f)["fertilized_until_day"],10)

    def test_16_wheat_age_bounds(self):
        for age in (0,1,5,6):
            a,o,c = self.wheat(age=age)
            self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_17_existing_inclusive_fertilizer_coverage(self):
        for until in (8,9,10):
            a,o,c = self.wheat(); self.tile(o)["fertilized_until_day"] = until
            self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_18_wheat_yield_cap(self):
        for units in (5,6):
            a,o,c = self.wheat(); self.tile(o)["yield_units"] = units
            self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_19_wheat_already_watered_age4_is_dead(self):
        a,o,c = self.wheat(age=4); self.tile(o)["watered_today"] = True
        self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_20_watered_age2_can_benefit_tomorrow(self):
        a,o,c = self.wheat(age=2); self.tile(o)["watered_today"] = True
        self.assertEqual(ih.apply_wheat_fertilize(a,o,c,enabled=True)["farmer"],["FERTILIZE"])

    def test_21_wheat_no_remaining_water_callback(self):
        for age,day,hour in ((4,8,23),(2,29,22),(2,29,23)):
            a,o,c = self.wheat(age=age,day=day,hour=hour)
            self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_22_wheat_missed_water_cannot_survive_refresh(self):
        a,o,c = self.wheat(hour=23); self.tile(o)["consecutive_unwatered"] = 1
        self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_23_nonwheat_never_fertilized(self):
        for crop in ("CARROT","TOMATO","STRAWBERRY","MELON"):
            a,o,c = self.wheat(); self.tile(o)["crop"] = crop
            self.assertIs(ih.apply_wheat_fertilize(a,o,c,enabled=True),a)

    def test_24_only_literal_pass(self):
        for row in ([],["PASS",1],["WATER"],["CARE"],["HARVEST"],["FEED"],["COLLECT_FERTILIZER"],["NORTH"]):
            a,o,c = self.fixture(); a["farmer"] = row
            self.assertIs(ih.apply_all(a,o,c,feed_all=True,care_all=True,wheat_fert=True),a)

    def test_25_alloff_callable_identity_and_no_invocation(self):
        def parent(*args): raise AssertionError("must not run")
        self.assertIs(ih.install(parent),parent)
        self.assertIs(ih.install(parent,idle_all=False),parent)

    def test_26_wrapper_calls_parent_once_and_forwards_configuration(self):
        a,o,c = self.fixture(); calls=[]
        def parent(obs,cfg): calls.append((obs,cfg)); return a
        wrapped = ih.install(parent,feed_all=True)
        self.assertEqual(wrapped(o,c)["farmer"],["FEED"])
        self.assertEqual(len(calls),1); self.assertIs(calls[0][0],o); self.assertIs(calls[0][1],c)

    def test_27_only_literal_true_enables(self):
        a,o,c = self.fixture()
        for value in (1,"true",[True],{},None,0):
            self.assertIs(ih.apply_feed(a,o,c,enabled=value),a)

    def test_28_standard_dict_struct_and_attribute_configuration(self):
        a,o,c = self.fixture()
        for cfg in (c,SimpleNamespace(**c)):
            self.assertEqual(ih.apply_feed(a,o,cfg,enabled=True)["farmer"],["FEED"])

    def test_29_configuration_type_poison(self):
        a,o,c = self.fixture()
        for key in c:
            for value in (None,True,str(c[key]),float(c[key]),[],float("inf"),c[key]+1):
                cfg = dict(c); cfg[key]=value
                self.assertIs(ih.apply_feed(a,o,cfg,enabled=True),a,(key,value))
        for cfg in (None,{},42,True,"standard",[],object()):
            self.assertIs(ih.apply_feed(a,o,cfg,enabled=True),a)
        class Broken:
            def __getattribute__(self,name): raise RuntimeError("broken config")
        self.assertIs(ih.apply_feed(a,o,Broken(),enabled=True),a)

    def test_30_player_step_day_hour_custody(self):
        for key,values in (("player",(True,-1,2,1.0,"0")),("step",(True,-1,719,200.0)),
                           ("day",(True,7,8.0)),("hour",(True,11,12.0))):
            for value in values:
                a,o,c = self.fixture(); o[key]=value
                self.assertIs(ih.apply_feed(a,o,c,enabled=True),a,(key,value))

    def test_31_farms_exactly_two(self):
        for n in (0,1,3):
            a,o,c = self.fixture(); o["farms"] = [o["farms"][0]]*n
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_32_actor_cardinality_all_or_nothing(self):
        for field in ("hands","inventories"):
            a,o,c = self.fixture(hand=True)
            if field=="hands": a["hands"] = []
            else: o["private"]["inventories"] = [{}]
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_33_all_geometry_validated_before_mutation(self):
        for pos in ([True,1],[1.0,1],[-1,1],[10,1],(1,1),[1],None):
            a,o,c = self.fixture(hand=True); o["farms"][0]["farmer"] = pos
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)
        a,o,c = self.fixture(); o["farms"][0]["tiles"][9]=[]
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_34_malformed_sibling_commands(self):
        a,o,c = self.fixture(hand=True)
        for row in (None,"PASS",[True],[[]]):
            a["farmer"]=row
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_35_inventory_scalar_poison(self):
        for value in (True,-1,1.0,"1",None,float("nan"),float("inf"),[]):
            a,o,c = self.fixture(); o["private"]["inventories"][0]["WHEAT"] = value
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_36_animal_scalar_poison(self):
        for key in ("placed_day","yield_units","consecutive_unfed","pending_care_bonus",
                    "fed_today","cared_today","fertilizer_available"):
            a,o,c = self.fixture(); self.tile(o)[key] = None
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a,key)
        a,o,c = self.fixture(); self.tile(o)["animal"]=[]
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_37_duplicate_worker_tile_is_not_claimed(self):
        for other_row in (["PASS"],["FEED"],["EAST"]):
            a,o,c = self.fixture(hand=True); o["farms"][0]["farmer"] = [1,1]; a["farmer"]=other_row
            self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_38_incoming_worker_collision(self):
        a,o,c = self.fixture(hand=True); o["farms"][0]["farmer"]=[0,1]; a["farmer"]=["EAST"]
        self.assertIs(ih.apply_feed(a,o,c,enabled=True),a)

    def test_39_input_nonmutation_market_preservation_and_detachment(self):
        a,o,c = self.fixture(); old=copy.deepcopy((a,o,c))
        r=ih.apply_feed(a,o,c,enabled=True)
        self.assertEqual((a,o,c),old); self.assertEqual(r["market"],a["market"])
        self.assertIsNot(r["market"],a["market"]); self.assertIsNot(r["extra"],a["extra"])
        r["market"][1][2]=999; self.assertEqual(a["market"][1][2],2)

    def test_40_combined_independent_tiles_all_three_layers(self):
        a,o,c = self.fixture(); f=o["farms"][0]
        f["hands"]=[[2,1],[3,1]]
        f["tiles"][1][2]=self.engine._new_animal("COW",0); f["tiles"][1][2]["fed_today"]=True
        f["tiles"][1][3]=self.engine._new_plant("WHEAT",6,24)
        o["private"]["inventories"]=[{"WHEAT":1},{},{"FERTILIZER":1}]
        a["hands"]=[["PASS"],["PASS"]]
        r=ih.apply_all(a,o,c,feed_all=True,care_all=True,wheat_fert=True)
        self.assertEqual([r["farmer"],*r["hands"]],[["FEED"],["CARE"],["FERTILIZE"]])
        out=self.execute(o,r)
        self.assertTrue(out["farms"][0]["tiles"][1][1]["fed_today"])
        self.assertTrue(out["farms"][0]["tiles"][1][2]["cared_today"])
        self.assertEqual(out["farms"][0]["tiles"][1][3]["fertilized_until_day"],10)

    def test_41_repeated_call_does_not_spend_observed_cargo(self):
        a,o,c=self.fixture(); old=copy.deepcopy(o)
        r=ih.apply_feed(a,o,c,enabled=True)
        self.assertEqual(ih.apply_feed(a,o,c,enabled=True),r); self.assertEqual(o,old)

    def test_42_second_transform_does_not_replace_new_nonpass(self):
        a,o,c=self.fixture()
        r=ih.apply_all(a,o,c,feed_all=True,care_all=True,wheat_fert=True)
        self.assertIs(ih.apply_all(r,o,c,feed_all=True,care_all=True,wheat_fert=True),r)

    def test_43_seeded_mechanism_property_panel(self):
        rng=random.Random(20260911)
        for _ in range(256):
            species=rng.choice(list(self.engine.ANIMALS)); day=rng.randrange(0,30)
            a,o,c=self.fixture(species,day=day,hour=rng.randrange(24),player=rng.randrange(2),hand=bool(rng.randrange(2)))
            self.tile(o)["fed_today"]=bool(rng.randrange(2)); self.tile(o)["cared_today"]=bool(rng.randrange(2))
            old=copy.deepcopy((a,o,c))
            r=ih.apply_all(a,o,c,feed_all=True,care_all=True,care_goose=True,wheat_fert=True)
            self.assertEqual((a,o,c),old)
            self.assertEqual(r["market"],a["market"])
            self.assertEqual(len(r["hands"]),len(a["hands"]))
            out=self.execute(o,r)
            for actor,(before,after) in enumerate(zip([a["farmer"],*a["hands"]],[r["farmer"],*r["hands"]])):
                if before != after:
                    self.assertEqual(before,["PASS"])
                    self.assertIn(after[0],("FEED","CARE","FERTILIZE"))
                    self.assertEqual(sum(o["private"]["inventories"][actor].values()) - sum(out["private"]["inventories"][actor].values()),int(after[0] in ("FEED","FERTILIZE")))


    def test_44_master_preserves_independent_three_arm_behavior(self):
        a,o,c = self.fixture(); f=o["farms"][0]
        f["hands"]=[[2,1],[3,1]]
        f["tiles"][1][2]=self.engine._new_animal("COW",0); f["tiles"][1][2]["fed_today"]=True
        f["tiles"][1][3]=self.engine._new_plant("WHEAT",6,24)
        o["private"]["inventories"]=[{"WHEAT":1},{},{"FERTILIZER":1}]
        a["hands"]=[["PASS"],["PASS"]]
        master=ih.apply_all(a,o,c,idle_all=True)
        individual=ih.apply_all(a,o,c,feed_all=True,care_all=True,wheat_fert=True)
        self.assertEqual(master,individual)
        self.assertEqual([master["farmer"],*master["hands"]],[["FEED"],["CARE"],["FERTILIZE"]])

    def test_45_individual_arms_do_not_need_master(self):
        for arm,expected in (("feed_all","FEED"),("care_all","CARE"),("care_goose","CARE"),("wheat_fert","FERTILIZE")):
            a,o,c=self.wheat() if arm=="wheat_fert" else self.fixture()
            if arm.startswith("care"):
                self.tile(o)["fed_today"]=True
            result=ih.apply_all(a,o,c,idle_all=False,**{arm:True})
            self.assertEqual(result["farmer"],[expected],arm)

    def test_46_master_only_literal_true(self):
        a,o,c=self.fixture()
        def parent(*_): return a
        for value in (1,"true",[],None):
            self.assertIs(ih.apply_all(a,o,c,idle_all=value),a)
            self.assertIs(ih.install(parent,idle_all=value),parent)

    def test_47_incumbent_telemetry_names_preserved(self):
        ih.telemetry.clear()
        a,o,c=self.fixture(); ih.apply_feed(a,o,c,enabled=True)
        self.tile(o)["fed_today"]=True; ih.apply_care(a,o,c,enabled=True)
        a,o,c=self.wheat(); ih.apply_wheat_fertilize(a,o,c,enabled=True)
        self.assertEqual(ih.telemetry["feed_rows"],1)
        self.assertEqual(ih.telemetry["care_rows"],1)
        self.assertEqual(ih.telemetry["wheat_fertilize_rows"],1)
        self.assertEqual(ih.telemetry["activations"],3)

    def test_48_incumbent_public_keyword_contract_preserved(self):
        import inspect
        expected={
            "apply_feed":("action","observation","configuration","enabled"),
            "apply_care":("action","observation","configuration","enabled","goose_only"),
            "apply_wheat_fertilize":("action","observation","configuration","enabled"),
            "apply_all":("action","observation","configuration","idle_all","feed_all","care_all","care_goose","wheat_fert"),
            "install":("parent","idle_all","feed_all","care_all","care_goose","wheat_fert"),
        }
        for name,params in expected.items():
            sig=inspect.signature(getattr(ih,name))
            self.assertEqual(tuple(sig.parameters),params)
            for parameter in list(sig.parameters.values())[1 if name=="install" else 3:]:
                self.assertIs(parameter.default,False)
                self.assertEqual(parameter.kind,inspect.Parameter.KEYWORD_ONLY)



if __name__ == "__main__":
    unittest.main(verbosity=2)
