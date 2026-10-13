# SPDX-License-Identifier: Apache-2.0
"""Public-clock consumer checks; optional native cases use an existing engine.

TITAN_SEED_SOURCE selects the existing runtime file (default: adjacent source).
KAG_ENGINE_DIR and TITAN_ENGINE_LOADER opt into offline pinned-engine cases.
No actor, full game, provider request, or alternative clock/engine is constructed.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("TITAN_SEED_SOURCE", HERE / "selected_seed_budget.py")).resolve()
ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}


def captured_module(path, name):
    """Execute captured test dependencies, never an unrelated cached .pyc."""
    module = types.ModuleType(name)
    module.__file__ = str(path)
    before = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(Path(path).read_bytes(), str(path), "exec"), module.__dict__)
    finally:
        if before is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = before
    return module


seed = captured_module(SOURCE, "seed_public_clock_subject")
PASS = {"farmer": ["PASS"], "hands": [], "market": []}
WITNESSES = []


def case(step=100, period=24, final=102, position=0):
    obs = {"step": step, "day": step // period, "hour": step % period,
           "player": position, "farms": [{"money": 1000}, {"money": 1000}],
           "private": {"seeds": {"WHEAT": 0}},
           "market": {"inventory": {"WHEAT": 10000}}, "town": {"unlocked_shops": []}}
    cfg = {"episodeSteps": final + 2, "turnsPerDay": period, "maxMarketOrdersPerTurn": 10}
    selected = {"farmer": ["PASS"], "hands": [],
                "market": [["BUY_SEED", "WHEAT", 9, "retained"], [], ["HIRE"]],
                "metadata": {"caller": "clock-check"}}
    rows = [{"step": s, "action": deepcopy(PASS)} for s in range(step + 1, final + 1)]
    if rows:
        rows[0]["action"]["farmer"] = ["PLANT", "WHEAT"]
    return obs, cfg, selected, {"WHEAT": 0}, {"selected": rows}


def shaped(obs, form):
    result = deepcopy(obs)
    if form == "missing":
        result.pop("step", None)
    elif form == "null":
        result["step"] = None
    return result


def compile_case(items, form="explicit", complete=True):
    obs, cfg, selected, stock, branches = items
    return seed.compile_demand(shaped(obs, form), cfg, selected, post_unit_seeds=stock,
                               continuations=branches, complete=complete)


def apply_case(items, contract, form="explicit"):
    obs, cfg, selected, stock, _ = items
    return seed.transform(shaped(obs, form), cfg, selected,
                          post_unit_seeds=stock, contract=contract)


class ClockTests(unittest.TestCase):
    def test_missing_step_compiles_same_contract(self):
        items = case()
        self.assertEqual(asdict(compile_case(items)), asdict(compile_case(items, "missing")))

    def test_null_step_compiles_same_contract(self):
        items = case()
        self.assertEqual(asdict(compile_case(items)), asdict(compile_case(items, "null")))

    def test_all_nine_representation_joins_preserve_proposal(self):
        items = case()
        expected = apply_case(items, compile_case(items))
        for cf in ("explicit", "missing", "null"):
            for tf in ("explicit", "missing", "null"):
                with self.subTest(compile=cf, transform=tf):
                    self.assertEqual(apply_case(items, compile_case(items, cf), tf), expected)
        self.assertEqual(expected["action"]["market"],
                         [["BUY_SEED", "WHEAT", 1, "retained"], [], ["HIRE"]])

    def test_custom_period_and_day_rollover(self):
        for period in (1, 7, 24, 31):
            for step in (0, period - 1, period, 2 * period + 1):
                with self.subTest(period=period, step=step):
                    items = case(step, period, step + 2)
                    c = compile_case(items, "missing")
                    self.assertEqual(c.observed_step, step)
                    self.assertEqual(asdict(c), asdict(compile_case(items)))

    def test_zero_explicit_step_is_not_treated_as_missing(self):
        items = case(0, final=2)
        items[0].update(day=9, hour=5)
        self.assertEqual(compile_case(items).observed_step, 0)

    def test_explicit_precedence_and_optional_day_hour(self):
        items = case()
        items[0].pop("day"); items[0].pop("hour")
        self.assertEqual(compile_case(items).observed_step, 100)
        items[0].update(day="unused", hour=None)
        self.assertEqual(compile_case(items).observed_step, 100)

    def test_nonnull_invalid_explicit_step_does_not_use_valid_day_hour(self):
        for value in (True, False, -1, 1.0, "100"):
            items = case(); good = compile_case(items); items[0]["step"] = value
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    compile_case(items)
                self.assertEqual(apply_case(items, good)["reason"], "invalid_current_context")

    def test_sparse_invalid_components_do_not_become_zero(self):
        invalid = [("day", -1), ("day", True), ("day", 4.0), ("day", "4"),
                   ("hour", -1), ("hour", None), ("hour", False), ("hour", 4.0),
                   ("hour", 24), ("hour", 25)]
        for key, value in invalid:
            items = case(); good = compile_case(items); items[0][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises((ValueError, KeyError)):
                    compile_case(items, "missing")
                self.assertEqual(apply_case(items, good, "missing")["reason"], "invalid_current_context")

    def test_sparse_period_must_be_positive_integer(self):
        for value in (0, -1, True, 24.0, "24", None):
            items = case(); good = compile_case(items); items[1]["turnsPerDay"] = value
            with self.subTest(period=value):
                with self.assertRaises((ValueError, KeyError)):
                    compile_case(items, "missing")
                self.assertEqual(apply_case(items, good, "missing")["reason"], "invalid_current_context")

    def test_missing_day_or_hour_has_no_guessed_clock(self):
        for key in ("day", "hour"):
            items = case(); good = compile_case(items); items[0].pop(key)
            with self.subTest(key=key):
                with self.assertRaises((ValueError, KeyError)):
                    compile_case(items, "missing")
                self.assertEqual(apply_case(items, good, "missing")["action"], items[2])

    def test_none_configuration_uses_normal_defaults(self):
        items = list(case(717, final=718)); items[1] = {}
        expected = asdict(compile_case(items))
        items[1] = None
        for form in ("explicit", "missing", "null"):
            with self.subTest(form=form):
                c = compile_case(items, form)
                self.assertEqual(asdict(c), expected)
                self.assertEqual(apply_case(items, c, form)["status"], "TRANSFORMED")

    def test_malformed_configuration_has_controlled_failure(self):
        items = list(case()); good = compile_case(items)
        for cfg in ([], "bad", False):
            items[1] = cfg
            with self.subTest(configuration=cfg):
                with self.assertRaises((ValueError, TypeError)):
                    compile_case(items)
                self.assertEqual(apply_case(items, good)["reason"], "invalid_current_context")

    def test_next_sparse_clock_is_stale_not_same_match(self):
        items = case(); c = compile_case(items)
        items[0]["hour"] += 1
        out = apply_case(items, c, "missing")
        self.assertEqual(out["reason"], "stale_or_different_context")
        self.assertEqual(out["action"], items[2])

    def test_changed_period_changes_inferred_context(self):
        items = case(); c = compile_case(items, "missing")
        items[1]["turnsPerDay"] = 25
        self.assertEqual(apply_case(items, c, "missing")["reason"], "stale_or_different_context")

    def test_same_step_different_actor_or_private_stays_stale(self):
        for key in ("player", "private"):
            items = case(); c = compile_case(items)
            if key == "player": items[0][key] = 1
            else: items[0][key]["seeds"]["WHEAT"] = 1
            with self.subTest(key=key):
                self.assertEqual(apply_case(items, c, "null")["reason"], "stale_or_different_context")

    def test_final_sparse_decision_excludes_current_units(self):
        items = case(718, final=718)
        items[2]["farmer"] = ["PLANT", "WHEAT"]
        for form in ("missing", "null"):
            with self.subTest(form=form):
                c = compile_case(items, form)
                self.assertTrue(c.complete)
                self.assertEqual(c.bounds()["WHEAT"], 0)
                self.assertEqual(apply_case(items, c, form)["action"]["market"][0], [])

    def test_beyond_final_sparse_clock_is_not_executable(self):
        items = case(719, final=718)
        with self.assertRaises(ValueError):
            compile_case(items, "missing")

    def test_sparse_incomplete_contract_preserves_action(self):
        items = case()
        c = compile_case(items, "missing", complete=False)
        self.assertFalse(c.complete)
        self.assertEqual(apply_case(items, c, "missing")["action"], items[2])
        items[4]["selected"].pop()
        c = compile_case(items, "null")
        self.assertFalse(c.complete)
        self.assertEqual(apply_case(items, c, "null")["action"], items[2])

    def test_inputs_and_returned_action_do_not_alias(self):
        items = case(); before = deepcopy(items)
        c = compile_case(items, "missing")
        out = apply_case(items, c, "null")
        out["action"]["metadata"]["caller"] = "mutated"
        self.assertEqual(items, before)
        self.assertEqual(seed._context(shaped(items[0], "missing"), items[1])[0]["step"], 100)

    def test_real_cli_sparse_null_and_none_configuration(self):
        for form in ("missing", "null"):
            items = list(case(717, final=718)); items[1] = None
            payload = {"observation": shaped(items[0], form), "configuration": None,
                       "selected_action": items[2], "post_unit_seeds": items[3],
                       "continuations": items[4], "complete": True}
            with self.subTest(form=form), tempfile.TemporaryDirectory() as tmp:
                inp, out = Path(tmp)/"in.json", Path(tmp)/"out.json"
                inp.write_text(json.dumps(payload), encoding="utf-8")
                p = subprocess.run([sys.executable, "-B", str(SOURCE), str(inp), "--output", str(out)],
                                   capture_output=True, text=True, timeout=20)
                self.assertEqual(p.returncode, 0, p.stderr)
                result = json.loads(out.read_text(encoding="utf-8"))
                self.assertEqual(result["contract"]["observed_step"], 717)
                self.assertEqual(result["action"], apply_case(items, compile_case(items), form)["action"])


class NativeClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = os.environ.get("KAG_ENGINE_DIR")
        loader = os.environ.get("TITAN_ENGINE_LOADER")
        if directory is None and loader is None:
            raise unittest.SkipTest("Provide existing KAG_ENGINE_DIR and TITAN_ENGINE_LOADER for native cases")
        if not directory or not loader:
            raise ValueError("Both engine directory and existing loader are required")
        cache = Path(directory).resolve()
        for name, expected in ENGINE_HASHES.items():
            actual = hashlib.sha256((cache/name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Wrong pinned engine bytes: {name}")
        names = ("kaggle_environments", "kaggle_environments.utils", "official_kaggriculture")
        before = {name: sys.modules.get(name) for name in names}
        def restore():
            for name, prior in before.items():
                if prior is None: sys.modules.pop(name, None)
                else: sys.modules[name] = prior
        cls.addClassCleanup(restore)
        cls.ev = captured_module(Path(loader), "seed_clock_existing_loader")
        cls.engine, hashes = cls.ev.get_engine(cache)
        if hashes != ENGINE_HASHES:
            raise ValueError("Loader did not report the pinned engine")

    def state(self, position, step=100, period=24, final=102, cash=1000, hires=1):
        m, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in m.specification["configuration"].items()})
        cfg.update(episodeSteps=final+2, turnsPerDay=period)
        farms = [m._new_farm(10, cash), m._new_farm(10, cash)]
        market, town = m._new_market(), m._new_town()
        states = []
        for i in (0, 1):
            farms[i].update(farmer=[0,0], hands=[[1,0]], hires_today=hires)
            private = m._new_private(); private["inventories"].append({})
            obs = S(player=i, step=step, day=step//period, hour=step%period,
                    farms=farms, market=market, town=town, private=private)
            states.append(S(observation=obs, action=deepcopy(PASS), status="ACTIVE", reward=0))
        return states, S(configuration=cfg, info={}, done=False)

    def items(self, states, env, position, selected, rows, stock=None):
        obs = deepcopy(states[position].observation)
        return (obs, env.configuration, selected,
                deepcopy(obs["private"]["seeds"] if stock is None else stock), {"selected": rows})

    def market(self, states, env, position, action):
        state, e = deepcopy((states, env))
        state[position].action = deepcopy(action)
        self.engine._process_market(state, e)
        return state

    def test_sparse_two_worker_continuation_executes_same_plants(self):
        for position in (0, 1):
            state, env = self.state(position, final=101)
            base = deepcopy(PASS); base["market"] = [["BUY_SEED", "WHEAT", 9]]
            plants = {"farmer":["PLANT","WHEAT"], "hands":[["PLANT","WHEAT"]], "market":[]}
            items = self.items(state, env, position, base, [{"step":101,"action":plants}])
            explicit = apply_case(items, compile_case(items))
            out = apply_case(items, compile_case(items, "missing"), "null")
            self.assertEqual(out, explicit)
            old, new = self.market(state,env,position,base), self.market(state,env,position,out["action"])
            for s in (old, new):
                obs = s[position].observation
                for i,a in enumerate([plants["farmer"], *plants["hands"]]):
                    self.engine._apply_unit_action(obs.farms[position],obs.private,i,a,10,4,24,100)
            self.assertEqual(old[position].observation.farms[position]["tiles"],new[position].observation.farms[position]["tiles"])
            delta = new[position].observation.farms[position]["money"] - old[position].observation.farms[position]["money"]
            self.assertEqual(delta,70)
            self.assertEqual(new[position].observation.private["seeds"]["WHEAT"],0)
            WITNESSES.append({"case":"sparse_two_plants","position":position,"cash_delta":delta,"buy":out["action"]["market"]})

    def test_custom_period_uses_native_post_unit_seed_stock(self):
        for position in (0, 1):
            state, env = self.state(position, step=17, period=7, final=19)
            obs = state[position].observation; obs.private["seeds"]["WHEAT"] = 1
            base = deepcopy(PASS); base.update(farmer=["PLANT","WHEAT"],market=[["BUY_SEED","WHEAT",9]])
            farm, private = deepcopy((obs.farms[position],obs.private))
            self.engine._apply_unit_action(farm,private,0,base["farmer"],10,2,7,100)
            self.assertEqual(private["seeds"]["WHEAT"],0)
            rows = [{"step":18,"action":deepcopy(PASS)},
                    {"step":19,"action":{"farmer":["PASS"],"hands":[["PLANT","WHEAT"]],"market":[]}}]
            items = self.items(state,env,position,base,rows,private["seeds"])
            out = apply_case(items,compile_case(items,"null"),"missing")
            self.assertEqual(out,apply_case(items,compile_case(items)))
            self.assertEqual(out["action"]["market"],[["BUY_SEED","WHEAT",1]])
            post = deepcopy(state);post[position].observation.farms[position]=farm;post[position].observation.private=private
            result=self.market(post,env,position,out["action"])
            self.assertEqual(result[position].observation.private["seeds"]["WHEAT"],1)
            self.assertEqual(result[position].observation.farms[position]["money"],990)
            WITNESSES.append({"case":"custom_period_post_units","position":position,"step":17,"seeds":1,"cash":990})

    def test_sparse_terminal_only_market_keeps_executable_slot(self):
        for position in (0,1):
            state,env=self.state(position,step=718,final=718)
            state[position].observation.private["shed"]["CARROT"]=1
            base=deepcopy(PASS);base["market"]=[["BUY_SEED","WHEAT",9],[],["SELL","CARROT",1]]
            items=self.items(state,env,position,base,[])
            out=apply_case(items,compile_case(items,"missing"),"missing")
            self.assertEqual(out["action"]["market"],[[],[],["SELL","CARROT",1]])
            old=self.market(state,env,position,base);new=self.market(state,env,position,out["action"])
            self.assertEqual(new[position].observation.farms[position]["money"]-old[position].observation.farms[position]["money"],90)
            self.assertEqual(new[position].observation.private["shed"]["CARROT"],0)
            WITNESSES.append({"case":"terminal_sparse","position":position,"cash_delta":90})

    def test_existing_cash_coupling_negative_is_not_changed(self):
        for position in (0,1):
            state,env=self.state(position,step=100,final=101,cash=233,hires=12)
            base=deepcopy(PASS);base["market"]=[["BUY_SEED","WHEAT",9],["HIRE"]]
            items=self.items(state,env,position,base,[{"step":101,"action":deepcopy(PASS)}])
            out=apply_case(items,compile_case(items,"missing"),"null")
            self.assertEqual(out,apply_case(items,compile_case(items)))
            old=self.market(state,env,position,base);new=self.market(state,env,position,out["action"])
            self.assertEqual(old[position].observation.farms[position]["money"],143)
            self.assertEqual(new[position].observation.farms[position]["money"],0)
            self.assertEqual(len(new[position].observation.farms[position]["hands"]),2)
            WITNESSES.append({"case":"retained_enabled_hire","position":position,"old_cash":143,"new_cash":0,"cash_delta":-143})


if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report=os.environ.get("TITAN_CLOCK_REPORT")
    if report:
        body={"schema":1,"source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "tests":result.testsRun,"failures":[str(t) for t,_ in result.failures],
              "errors":[str(t) for t,_ in result.errors],"skipped":[[str(t),r] for t,r in result.skipped],
              "witnesses":WITNESSES,"engine_hashes":ENGINE_HASHES if WITNESSES else None,
              "scope":"Public-clock interface and native component fixtures; no full games"}
        Path(report).write_text(json.dumps(body,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    raise SystemExit(not result.wasSuccessful())
