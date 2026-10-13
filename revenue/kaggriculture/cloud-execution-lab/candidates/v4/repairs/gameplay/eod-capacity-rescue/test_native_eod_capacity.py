# SPDX-License-Identifier: Apache-2.0
"""Source-pinned native EOD port and full official-turn differential checks.

TITAN_PACKAGE must name a standalone native package with checks/reference.
No network access, legacy materializer, production writes, or synthetic market
transition implementation. Runtime-seam tests use the actual class with clearly
labelled collaborator probes; interpreter tests execute complete real turns.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest

from port_native_eod_capacity import DONOR_BLOB, RUNTIME_BLOB, git_blob, native_source, wire_runtime

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("TITAN_PACKAGE", "")).resolve()
PINS = {
    "titan_runtime.py": RUNTIME_BLOB,
    "mechanics.py": "044a4f9c0a4a44dde10ada57563238bcaf82075d",
    "checks/reference/engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "checks/reference/engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "checks/reference/engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
    "checks/reference/evaluator/evaluate.py": "1fb6b655bb4ca1e1684be165a8ef513e2e6c2325",
    "checks/reference/evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
}
RECEIPT = {"source_pins": PINS, "engine_cells": [], "limitations": [
    "Not a whole-current-package or leaderboard test; artifact entrypoint is older.",
    "H3c whole-router execution and full-game economics are not run here.",
    "Runtime placement is source-pinned, OFF by default, and tested with collaborator probes.",
]}


def load_source(name, source, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    sys.modules[name] = module
    exec(compile(source, str(filename), "exec"), module.__dict__)
    return module


def plain_action(hands=0):
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": []}


class NativeEodCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for rel, pin in PINS.items():
            if git_blob((ROOT / rel).read_bytes()) != pin:
                raise ValueError(f"Source mismatch: {rel}")
        donor_path = Path(os.environ.get("EOD_DONOR", str(HERE.parents[2] / "donor/overlay/r04_eod_capacity_rescue.py")))
        donor = donor_path.read_text()
        if git_blob(donor.encode()) != DONOR_BLOB:
            raise ValueError("Donor mismatch")
        sys.path.insert(0, str(ROOT))
        cls.donor = donor
        cls.source = native_source(donor)
        cls.lane = load_source("native_eod_capacity_rescue", cls.source,
                               HERE / "native_eod_capacity_rescue.py")
        ev_path = ROOT / "checks/reference/evaluator/evaluate.py"
        spec = importlib.util.spec_from_file_location("granary_official_evaluator", ev_path)
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.hashes = cls.ev.get_engine(
            ROOT / "checks/reference/engine", ROOT / "checks/reference/evaluator/loader.py")
        runtime_path = ROOT / "titan_runtime.py"
        cls.runtime_source = runtime_path.read_text()
        cls.original = load_source("granary_runtime_original", cls.runtime_source, runtime_path)
        cls.wired = load_source("granary_runtime_wired", wire_runtime(cls.runtime_source), runtime_path)
        RECEIPT["materialized_helper_blob"] = git_blob(cls.source.encode())
        RECEIPT["materialized_runtime_blob"] = git_blob(wire_runtime(cls.runtime_source).encode())

    def fixture(self, seat=0, item="MILK", *, step=119, inventory=10000,
                shed_units=99, carry=(2, 1), market=(), rival=(), cash=20000):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        farms = [e._new_farm(10, cash), e._new_farm(10, cash)]
        m = e._new_market()
        m["inventory"][item] = inventory
        e._refresh_prices(m)
        town = {"unlocked_shops": ["BAKERY", "YARN_STORE"]}
        state = []
        for p in range(2):
            private = e._new_private()
            if p == seat:
                farms[p]["hands"] = [[5, 4] for _ in carry[1:]]
                private["inventories"] = [{item: q} if q else {} for q in carry]
                private["shed"][item] = shed_units - 1
                other = "CARROT" if item != "CARROT" else "MILK"
                private["shed"][other] = 1
            else:
                private["shed"][item] = 20
            state.append(S(observation=S(player=p, step=step, day=step//24,
                                         hour=step%24, farms=farms, private=private,
                                         market=m, town=town),
                           action=plain_action(len(farms[p]["hands"])),
                           status="ACTIVE", reward=0))
        state[seat].action["market"] = copy.deepcopy(list(market))
        state[1-seat].action["market"] = copy.deepcopy(list(rival))
        env = S(configuration=cfg, done=False, info={"seed": 9600803})
        return state, env

    def transform(self, state, env, seat=0, enabled=True):
        return self.lane.apply_eod_capacity_rescue(state[seat].action,
            state[seat].observation, env.configuration, enabled=enabled)

    def floor_inventory(self, item):
        lo, hi = 10000, 10001
        for _ in range(64):
            if self.engine.market_price(item, hi) == 1:
                break
            hi = 10000 + 2 * (hi - 10000)
        else:
            raise ValueError(f"No floor in bounded exponential search: {item}")
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.engine.market_price(item, mid) == 1:
                hi = mid
            else:
                lo = mid
        return hi

    def paired(self, *, seat=0, item="MILK", **kwargs):
        baseline, be = self.fixture(seat, item, **kwargs)
        candidate, ce = copy.deepcopy((baseline, be))
        before = copy.deepcopy(candidate[seat].action)
        proposed = self.transform(candidate, ce, seat)
        self.assertIsNot(proposed, candidate[seat].action)
        self.assertEqual(candidate[seat].action, before)
        self.assertEqual(proposed["market"][:-1], before["market"])
        candidate[seat].action = proposed
        self.engine.interpreter(baseline, be)
        self.engine.interpreter(candidate, ce)
        self.assertEqual(baseline[seat].observation.private, candidate[seat].observation.private)
        delta = (candidate[seat].observation.farms[seat]["money"]
                 - baseline[seat].observation.farms[seat]["money"])
        self.assertGreater(delta, 0)
        return baseline, candidate, delta, proposed["market"][-1][2]

    def test_01_source_pin_and_no_legacy_imports(self):
        self.assertEqual(git_blob(self.donor.encode()), DONOR_BLOB)
        with self.assertRaises(ValueError):
            native_source(self.donor + "\n")
        with self.assertRaises(ValueError):
            wire_runtime(self.runtime_source + "\n")
        imports = [n for n in ast.walk(ast.parse(self.source)) if isinstance(n, ast.Import)]
        names = [a.name for n in imports for a in n.names]
        self.assertNotIn("r04_full_router", names)
        self.assertNotIn("h3c_goose_eod_cap_rescue", names)
        self.assertIn("mechanics", names)

    def test_02_default_off_exact_identity_and_install(self):
        state, env = self.fixture()
        parent = state[0].action
        self.assertIs(self.lane.apply_eod_capacity_rescue(parent, state[0].observation,
                                                         env.configuration), parent)
        wrapped = self.lane.install(lambda o, c: parent)
        self.assertIs(wrapped(state[0].observation, env.configuration), parent)
        self.assertFalse(self.wired.Features().r04_eod_capacity_rescue)

    def test_03_full_turn_all_products_both_seats_floor_and_above(self):
        for seat in (0, 1):
            for item in self.engine.PRODUCTS:
                for floor in (False, True):
                    with self.subTest(seat=seat, item=item, floor=floor):
                        inv = self.floor_inventory(item) if floor else 10000
                        base, cand, cash, units = self.paired(seat=seat, item=item, inventory=inv)
                        RECEIPT["engine_cells"].append({"family": "base", "seat": seat,
                            "item": item, "floor": floor, "cash_delta": cash, "rescued_units": units,
                            "market_equal": base[0].observation.market == cand[0].observation.market})
                        if floor:
                            self.assertEqual(cash, units)
                            self.assertEqual(base[0].observation.market, cand[0].observation.market)

    def test_04_multiactor_capacity_edges_and_neutral_market_prefix(self):
        prefixes = [[], [[]]*9, [["HIRE"]], [["BUY_SEED", "WHEAT", 2]],
                    [["BUY_LAND"]], [["HIRE"], [], ["BUY_SEED", "CARROT", 1]]]
        for seat in (0, 1):
            for carry, shed in (((3,), 99), ((1, 1, 1, 1), 98), ((4, 0, 0), 100)):
                for prefix in prefixes:
                    with self.subTest(seat=seat, carry=carry, shed=shed, prefix=prefix):
                        _, _, cash, units = self.paired(seat=seat, inventory=11000,
                            carry=carry, shed_units=shed, market=prefix)
                        self.assertEqual(cash, units)
                        RECEIPT["engine_cells"].append({"family": "prefix_capacity", "seat":seat,
                            "carry":carry,"shed":shed,"prefix":prefix,"cash_delta":cash})

    def test_05_sale_only_floor_rival_sales_preserve_state_except_cash(self):
        sale_only = [p for p in self.engine.PRODUCTS if p not in ("WHEAT", "FERTILIZER")]
        for seat in (0, 1):
            for item in sale_only:
                for padding in (0, 4, 9):
                    with self.subTest(seat=seat, item=item, padding=padding):
                        base, cand, cash, units = self.paired(seat=seat, item=item,
                            inventory=self.floor_inventory(item), market=[[]]*padding,
                            rival=[["SELL",item,10], ["HIRE"], ["SELL",item,10]])
                        bobs, cobs = copy.deepcopy((base[0].observation, cand[0].observation))
                        cobs.farms[seat]["money"] -= cash
                        self.assertEqual(bobs, cobs)
                        self.assertEqual(base[1].observation.private, cand[1].observation.private)
                        self.assertEqual(cash, units)
                        RECEIPT["engine_cells"].append({"family":"sale_only_floor_rival", "seat":seat,
                            "item":item,"prefix_padding":padding,"cash_delta":cash})

    def test_06_floor_quote_alone_is_not_public_state_neutral_for_buyables(self):
        witnesses=[]
        for seat in (0, 1):
            for item in ("WHEAT", "FERTILIZER"):
                base, cand, cash, units = self.paired(seat=seat, item=item,
                    inventory=self.floor_inventory(item), carry=(10,), shed_units=100,
                    rival=[["BUY_PRODUCT",item,20]])
                self.assertNotEqual(base[0].observation.market, cand[0].observation.market)
                rival_delta = (cand[0].observation.farms[1-seat]["money"]
                               - base[0].observation.farms[1-seat]["money"])
                if item == "FERTILIZER":
                    self.assertEqual((cash, rival_delta, cash-rival_delta), (19, 23, -4))
                witnesses.append({"seat":seat,"item":item,"start_inventory":self.floor_inventory(item),
                    "rescued_units":units,"cash_delta":cash,"margin_delta":cash-rival_delta,
                    "scope":"plausible_inventory" if item=="FERTILIZER" else "structural_extreme_inventory_only",
                    "baseline_end_inventory":base[0].observation.market["inventory"][item],
                    "candidate_end_inventory":cand[0].observation.market["inventory"][item],
                    "baseline_rival_cash":base[0].observation.farms[1-seat]["money"],
                    "candidate_rival_cash":cand[0].observation.farms[1-seat]["money"]})
        RECEIPT["buyable_floor_counterexamples"]=witnesses

    def test_07_cargo_changing_commands_and_h3c_harvest_are_identity(self):
        # A post-H3c HARVEST is a tested seam contract, NOT whole H3c execution.
        for op in ("HARVEST", "COLLECT_FERTILIZER", "FEED", "DROP", "PICKUP", "FERTILIZE"):
            state, env = self.fixture()
            state[0].action["farmer"] = [op]
            self.assertIs(self.transform(state, env), state[0].action)
        for command in ([[]], [{}], [], "PASS", None):
            state, env = self.fixture()
            state[0].action["farmer"] = command
            self.assertIs(self.transform(state, env), state[0].action)

    def test_08_stock_changing_or_opaque_market_and_full_budget_are_identity(self):
        for market in ([["SELL","MILK",1]], [["BUY_PRODUCT","WHEAT",1]],
                       [["BUY_ANIMAL","COW",1]], [["BOGUS"]], [[{}]], [[]]*10,
                       [[]]*10 + [["HIRE"]]):
            state, env = self.fixture(market=market)
            self.assertIs(self.transform(state, env), state[0].action)

    def test_09_mixed_cargo_roomy_stock_and_bad_price_are_identity(self):
        for mode in ("mixed", "roomy", "insufficient", "bool_quantity", "price"):
            state, env = self.fixture()
            obs=state[0].observation
            if mode=="mixed": obs.private["inventories"][1]={"EGG":1}
            if mode=="roomy": obs.private["shed"]["MILK"]=90
            if mode=="insufficient": obs.private["shed"]={"WHEAT":100}
            if mode=="bool_quantity": obs.private["inventories"][1]={"MILK":True}
            if mode=="price": obs.market["prices"]["MILK"]="160"
            self.assertIs(self.transform(state, env), state[0].action)

    def test_10_time_season_configuration_and_actor_schema_fail_closed(self):
        for step in (0,118,696,718,719,True,-1):
            state, env = self.fixture()
            state[0].observation["step"]=step
            self.assertIs(self.transform(state, env), state[0].action)
        for key,value in (("episodeSteps",696),("shedCapacity",101),("maxMarketOrdersPerTurn",12),
                          ("townShopSellInterval",1),("townCenterSellInterval",1),("boardSize",True)):
            state, env = self.fixture()
            env.configuration[key]=value
            self.assertIs(self.transform(state, env), state[0].action)
        for mode in ("farms", "player", "inventories", "hands"):
            state, env = self.fixture()
            obs=state[0].observation
            if mode=="farms":obs.farms.append(copy.deepcopy(obs.farms[0]))
            if mode=="player":obs.player=True
            if mode=="inventories":obs.private["inventories"].pop()
            if mode=="hands":state[0].action["hands"]=[]
            self.assertIs(self.transform(state, env), state[0].action)

    def test_11_last_valid_eod_and_unit_neutral_operations(self):
        for seat in (0,1):
            for op in ("PASS","NORTH","SOUTH","EAST","WEST","WATER","DIG","CARE",
                       "BUILD_COOP","BUILD_PASTURE","PLANT"):
                base,be=self.fixture(seat,step=695,inventory=11000)
                base[seat].action["farmer"]=[op,"WHEAT"] if op=="PLANT" else [op]
                cand,ce=copy.deepcopy((base,be))
                out=self.transform(cand,ce,seat)
                self.assertIsNot(out,cand[seat].action)
                cand[seat].action=out
                self.engine.interpreter(base,be)
                self.engine.interpreter(cand,ce)
                self.assertEqual(base[seat].observation.private,cand[seat].observation.private)
                bobs,cobs=copy.deepcopy((base[0].observation,cand[0].observation))
                delta=cobs.farms[seat]["money"]-bobs.farms[seat]["money"]
                cobs.farms[seat]["money"]-=delta
                self.assertEqual(bobs,cobs)
                self.assertEqual(delta,2)
                RECEIPT["engine_cells"].append({"family":"last_eod_neutral_unit","seat":seat,"op":op,"cash_delta":delta})

    def test_12_native_actual_finalizer_off_identity_and_on_rescue(self):
        state,env=self.fixture()
        for consumer in ("frozen","ordered","parent"):
            original=self.original.TitanAgent(self.original.Features(consumer=consumer))
            off=self.wired.TitanAgent(self.wired.Features(consumer=consumer))
            on=self.wired.TitanAgent(self.wired.Features(consumer=consumer,r04_eod_capacity_rescue=True))
            parent=state[0].action;obs=state[0].observation
            self.assertIs(original._finish_production(obs,parent,env.configuration),parent)
            self.assertIs(off._finish_production(obs,parent,env.configuration),parent)
            self.assertEqual(on._finish_production(obs,parent,env.configuration)["market"],[["SELL","MILK",2]])

    def test_13_finalizer_admits_only_after_both_guards_and_records_returned_action(self):
        state,env=self.fixture()
        owner=self.wired.TitanAgent(self.wired.Features(r04_eod_capacity_rescue=True))
        events=[]
        owner._selected_snapshot=lambda obs,a: None
        owner._feed_stock_selected=lambda obs,cfg,a: (events.append("feed") or a)
        owner._early_capital_selected=lambda obs,cfg,a: (events.append("capital") or a)
        class History:
            diagnostics={}
            def remember(self,obs,cfg,a,post):
                events.append(copy.deepcopy(a["market"]))
        owner.history=History()
        out=owner._finish_production(state[0].observation,state[0].action,env.configuration)
        self.assertEqual(events,["feed","capital",[["SELL","MILK",2]]])
        self.assertEqual(out["market"],events[-1])
        guarded=copy.deepcopy(state[0].action)
        guarded["market"]=[["SELL","MILK",1]]
        owner._early_capital_selected=lambda obs,cfg,a: guarded
        self.assertIs(owner._finish_production(state[0].observation,state[0].action,env.configuration),guarded)

    def test_14_source_placement_has_single_hook_and_unchanged_nonfinalizer_methods(self):
        old=ast.parse(self.runtime_source);new=ast.parse(wire_runtime(self.runtime_source))
        def methods(tree):
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="TitanAgent")
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
        a,b=methods(old),methods(new)
        self.assertEqual(set(a),set(b))
        for name in a:
            if name!="_finish_production": self.assertEqual(a[name],b[name],name)
        self.assertEqual(wire_runtime(self.runtime_source).count("returned = apply_eod_capacity_rescue("),1)


    def test_15_current_whole_vector_mixed_cargo_and_raw_budget(self):
        for seat in (0, 1):
            for prefix_len in (0, 8):
                base, be = self.fixture(seat, market=[[]]*prefix_len)
                private = base[seat].observation.private
                private["shed"] = {"MILK": 50, "EGG": 50}
                private["inventories"] = [{"MILK": 3, "EGG": 2}, {}]
                cand, ce = copy.deepcopy((base, be))
                proposed = self.transform(cand, ce, seat)
                self.assertEqual(proposed["market"][-2:], [["SELL", "EGG", 2], ["SELL", "MILK", 3]])
                cand[seat].action = proposed
                self.engine.interpreter(base, be)
                self.engine.interpreter(cand, ce)
                self.assertEqual(base[seat].observation.private, cand[seat].observation.private)
                RECEIPT["engine_cells"].append({"family":"current_whole_vector", "seat":seat,
                    "prefix_len":prefix_len,"own_private_equal":True})
        for mode in ("partial_mixed_actor", "only_one_free_slot"):
            state, env = self.fixture()
            state[0].observation.private["shed"] = {"MILK":50,"EGG":50}
            state[0].observation.private["inventories"] = [{"MILK":3,"EGG":2},{}]
            if mode == "partial_mixed_actor":
                state[0].observation.private["shed"]["MILK"] = 49
            else:
                state[0].action["market"] = [[]]*9
            self.assertIs(self.transform(state, env), state[0].action)

    def test_16_transplanted_current_policy_ast_is_unchanged(self):
        # Dependency names are the only semantic AST differences allowed.
        class Normalize(ast.NodeTransformer):
            def visit_Attribute(self,node):
                if isinstance(node.value,ast.Name) and node.value.id=="h3c":
                    return ast.copy_location(ast.Name(id=node.attr,ctx=node.ctx),node)
                return self.generic_visit(node)
            def visit_Import(self,node):
                for alias in node.names:
                    if alias.name=="r04_full_router":alias.name="mechanics"
                return node
        expected = Normalize().visit(ast.parse(self.donor))
        actual = ast.parse(self.source)
        donor_functions={n.name:ast.dump(n,include_attributes=False) for n in expected.body
                         if isinstance(n,ast.FunctionDef)}
        native_functions={n.name:ast.dump(n,include_attributes=False) for n in actual.body
                          if isinstance(n,ast.FunctionDef)}
        for name,body in donor_functions.items():self.assertEqual(body,native_functions[name],name)


if __name__ == "__main__":
    result=unittest.main(exit=False,verbosity=2).result
    RECEIPT.update({"tests_run":result.testsRun,"failures":len(result.failures),
                    "errors":len(result.errors),"optimized":not __debug__})
    output=os.environ.get("EOD_RECEIPT")
    if output: Path(output).write_text(json.dumps(RECEIPT,indent=2,sort_keys=True)+"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
