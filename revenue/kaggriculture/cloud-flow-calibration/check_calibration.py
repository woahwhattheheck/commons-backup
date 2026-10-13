# SPDX-License-Identifier: MIT
"""Real T12/official-market consumer tests and reproducible synthetic fixtures."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

from calibration import CausalWindowEnsemble, experts_from_prediction, interval_label, predict_history, summarize
from replay import replay

FLOW_BLOB = "7b3c1c383e98ce1eb5bf539caddf0ab4351f8633"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
FLOW_COMMIT = "4d7fd6d4d4e1f71941f7fe76b8e10274f1bfc1a6"
ENGINE_COMMIT = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
FLOW = ENGINE = None
MARKET_STAGES = 0
WITNESSES, EVENTS, TIMINGS = [], [], []


def git_blob(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_engine(path):
    # Only satisfy an unused framework import. Market and consumption are the
    # unchanged official functions. Seed resolution / initialization is not run.
    saved = {k: sys.modules.get(k) for k in ("kaggle_environments", "kaggle_environments.utils")}
    package = types.ModuleType("kaggle_environments"); utils = types.ModuleType("kaggle_environments.utils")
    def unused(*args, **kwargs):
        raise RuntimeError("this market-only consumer does not initialize episodes")
    utils.resolve_episode_seed = unused
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    try:
        return load(path, "quill_pinned_engine")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def prediction(now=25, end=27, streams=None, ready=True):
    if streams is None:
        streams = [((now, 6),), ((now, 6),), ((now + 1, 6),)]
    windows = [{"lag": i + 1, "stream": s, "total": sum(q for _, q in s),
                "training_start": now - 24 * (i + 1), "training_end": end - 24 * (i + 1)}
               for i, s in enumerate(streams)]
    # Synthetic default timestamps must all remain nonnegative.
    for i, w in enumerate(windows):
        w["training_start"] = i * 3
        w["training_end"] = i * 3 + end - now
    return {"now": now, "end": end, "ready": ready, "support": len(windows), "windows": windows}


def row(step=25, lo=0, hi=0, product="CARROT"):
    return {"step": step, "product": product, "lower": lo, "upper": hi}


def forecast(model=None, **kwargs):
    model = model or CausalWindowEnsemble("fixture", "CARROT")
    args = {"now": 25, "end": 27, "cutoff": 25, "threshold": 5}; args.update(kwargs)
    return model, model.predict(prediction(args["now"], args["end"]), **args)


def market_interval(step, own_seat, rival_quantity, *, floor=False, hidden_stock=None):
    global MARKET_STAGES
    e = ENGINE
    market = e._new_market(); town = e._new_town()
    if floor:
        market["inventory"]["CARROT"] = 1000000
        e._refresh_prices(market)
    farms = [e._new_farm(10, 1000) for _ in range(2)]
    private = [e._new_private() for _ in range(2)]
    private[own_seat]["shed"]["CARROT"] = 2
    private[1 - own_seat]["shed"]["CARROT"] = rival_quantity if hidden_stock is None else hidden_stock
    actions = [{"market": []}, {"market": []}]
    actions[own_seat]["market"] = [["SELL", "CARROT", 2]]
    actions[1 - own_seat]["market"] = [["SELL", "CARROT", rival_quantity]]
    state = [types.SimpleNamespace(observation=types.SimpleNamespace(market=market, farms=farms,
              town=town, private=private[i]), action=actions[i]) for i in range(2)]
    cfg = {"boardSize": 10, "maxMarketOrdersPerTurn": 10, "shedCapacity": 100,
           "townShopSellInterval": 4, "townCenterSellInterval": 24}
    env = types.SimpleNamespace(configuration=cfg)
    before = {"step": step, "market": copy.deepcopy(market), "town": copy.deepcopy(town)}
    start_stock = private[own_seat]["shed"]["CARROT"]
    e._process_market(state, env); MARKET_STAGES += 1
    own_fill = start_stock - private[own_seat]["shed"]["CARROT"]
    before_consume = market["inventory"]["CARROT"]
    e._town_consume(env, state, step)
    consumed = before_consume - market["inventory"]["CARROT"]
    after = {"step": step + 1, "market": copy.deepcopy(market), "town": copy.deepcopy(town)}
    iv = FLOW.infer_flow(before, after, {"CARROT": own_fill}, "CARROT", cfg, e,
                         lambda product, t, shops, config: consumed)
    return iv, {"step": step, "own_seat": own_seat, "rival_requested": rival_quantity,
                "floor": floor, "inferred": iv.as_dict(), "own_fill": own_fill,
                "cash_by_seat": [f["money"] for f in farms],
                "public_before": before, "public_after": after}


class IntervalTests(unittest.TestCase):
    def label(self, rows, **kw):
        args = dict(product="CARROT", now=25, cutoff=25, threshold=5); args.update(kw)
        return interval_label(rows, **args)

    def test_exact_threshold_true_and_false(self):
        self.assertEqual(self.label([row(lo=5, hi=5)])["label"], 1)
        self.assertEqual(self.label([row(lo=4, hi=4)])["label"], 0)

    def test_censored_interval_not_zero(self):
        self.assertIsNone(self.label([row(lo=0, hi=100)])["label"])

    def test_censored_interval_can_identify_threshold(self):
        self.assertEqual(self.label([row(lo=7, hi=100)])["label"], 1)
        self.assertEqual(self.label([row(lo=1, hi=4)])["label"], 0)

    def test_missing_dates_unknown_except_proven_positive(self):
        self.assertIsNone(self.label([row(lo=4, hi=4)], cutoff=26)["label"])
        out = self.label([row(lo=5, hi=5)], cutoff=26)
        self.assertEqual(out["label"], 1); self.assertIsNone(out["upper"])

    def test_duplicate_product_date_and_bad_bounds(self):
        for rows in ([row(), row()], [row(product="MILK")], [row(step=26)], [row(lo=7, hi=6)]):
            with self.assertRaises(ValueError): self.label(rows)

    def test_boolean_fraction_nan_quantities_rejected(self):
        for x in (True, 1.2, float("nan"), -1):
            with self.assertRaises(ValueError): self.label([row(lo=x, hi=8)])

    def test_actual_t12_object_protocol(self):
        iv = FLOW.FlowInterval(25, "CARROT", 6, 6, 6, 6, "identified")
        self.assertEqual(self.label([iv])["label"], 1)


class LearnerTests(unittest.TestCase):
    def test_intact_stream_components_and_mass(self):
        m, f = forecast()
        same = [c["stream"] for c in f["components"] if c["expert"] == "same_phase"]
        self.assertEqual(same, [((25, 6),), ((25, 6),), ((26, 6),)])
        self.assertAlmostEqual(sum(c["mass"] for c in f["components"]), 1)
        self.assertEqual(f["components"][-1]["stream"], None)
        self.assertEqual(f["unknown_mass"], .25)
        self.assertEqual(f["recommended_alpha"], 0)

    def test_shift_clamping_preserves_whole_quantities(self):
        p = prediction(streams=[((25, 2), (26, 4), (27, 3))])
        ex = experts_from_prediction(p, now=25, end=27)
        self.assertEqual(ex["shift_early"]["streams"], (((25, 6), (26, 3)),))
        self.assertEqual(ex["shift_late"]["streams"], (((26, 2), (27, 7)),))

    def test_sparse_support_is_all_unknown(self):
        m = CausalWindowEnsemble("cold", "CARROT")
        f = m.predict(prediction(ready=False), now=25, end=27, cutoff=25, threshold=5)
        self.assertEqual(f["probability_interval"], [0, 1])
        self.assertEqual(f["diagnostic_midpoint"], .5)
        self.assertEqual(f["unknown_mass"], 1)

    def test_reject_future_training_or_mismatched_total(self):
        for change in ("future", "total", "duration", "duplicate"):
            p = prediction()
            if change == "future": p["windows"][0].update(training_start=25, training_end=27)
            if change == "total": p["windows"][0]["total"] = 2
            if change == "duration": p["windows"][0]["training_end"] = 1
            if change == "duplicate": p["windows"][0]["stream"] = [(25, 3), (25, 3)]
            with self.assertRaises(ValueError): experts_from_prediction(p, now=25, end=27)

    def test_predictions_are_frozen_and_retries_idempotent(self):
        m, f = forecast(); original = copy.deepcopy(f)
        f["expert_probabilities"]["same_phase"] = 0
        f["components"][0]["mass"] = 900
        self.assertEqual(forecast(m)[1], original)
        r = m.resolve(original["ticket"], [row(lo=6, hi=6)], observed_at=28)
        self.assertEqual(r["scores"]["same_phase"]["prediction"], 2 / 3)

    def test_reject_early_repeat_forged_and_overlapping(self):
        m, f = forecast(); initial = m.state()
        with self.assertRaises(ValueError): m.resolve(f["ticket"], [row()], observed_at=27)
        with self.assertRaises(ValueError): m.resolve("forged", [row()], observed_at=28)
        with self.assertRaises(ValueError): forecast(m, now=26, end=28, cutoff=26)
        self.assertEqual(m.state(), initial)
        m.resolve(f["ticket"], [row()], observed_at=28)
        with self.assertRaises(ValueError): m.resolve(f["ticket"], [row()], observed_at=28)
        with self.assertRaises(ValueError): forecast(m, now=27, end=29, cutoff=27)

    def test_censor_does_not_update_weights_or_prior(self):
        m, f = forecast(); before = m.state()["weights"]
        r = m.resolve(f["ticket"], [row(lo=0, hi=100)], observed_at=28)
        self.assertEqual(r["scores"], {}); self.assertEqual(m.state()["weights"], before)
        self.assertEqual(m.state()["identified"], 0)
        self.assertEqual(m.state()["censored"], 1)
        g = forecast(m, now=49, end=51, cutoff=49)[1]
        self.assertEqual(g["prior_rate_control"], .5)

    def test_weight_update_uses_exact_stored_brier(self):
        m, f = forecast()
        m.resolve(f["ticket"], [row(lo=6, hi=6)], observed_at=28)
        actual = m.state()["weights"]
        expected = {k: math.exp(-2 * (p - 1) ** 2) for k, p in f["expert_probabilities"].items()}
        total = sum(expected.values())
        for k in expected: self.assertAlmostEqual(actual[k], expected[k] / total)
        self.assertGreater(actual["shift_early"], actual["zero"])

    def test_unconditional_control_is_prior_not_current_label(self):
        m, f = forecast()
        r = m.resolve(f["ticket"], [row(lo=6, hi=6)], observed_at=28)
        self.assertEqual(r["scores"]["prior_rate_control"]["prediction"], .5)
        g = forecast(m, now=49, end=51, cutoff=49)[1]
        self.assertAlmostEqual(g["prior_rate_control"], 2 / 3)

    def test_event_families_and_compute_bounds(self):
        m, f = forecast(); m.resolve(f["ticket"], [row()], observed_at=28)
        with self.assertRaises(ValueError): forecast(m, now=49, end=51, cutoff=50)
        with self.assertRaises(ValueError): forecast(CausalWindowEnsemble("small", "CARROT", max_streams=1))
        with self.assertRaises(ValueError): forecast(CausalWindowEnsemble("short", "CARROT", max_window=2))

    def test_extreme_eta_stays_finite(self):
        m = CausalWindowEnsemble("large", "CARROT", eta=1e6, gamma=.9)
        for i in range(8):
            now = 25 + i * 24
            f = forecast(m, now=now, end=now+2, cutoff=now)[1]
            m.resolve(f["ticket"], [row(now, 6 * (i % 2), 6 * (i % 2))], observed_at=now+3)
            self.assertTrue(all(math.isfinite(w) and w > 0 for w in m.state()["weights"].values()))

    def test_invalid_parameters(self):
        for kw in ({"eta":0}, {"eta":float("inf")}, {"gamma":1.1}, {"unknown_mass":0}, {"max_streams":True}):
            with self.assertRaises(ValueError): CausalWindowEnsemble("x", "CARROT", **kw)

    def test_discounted_update_matches_equation(self):
        m = CausalWindowEnsemble("discount", "CARROT", eta=1.25, gamma=.5)
        m, f = forecast(m)
        m.resolve(f["ticket"], [row(lo=6, hi=6)], observed_at=28)
        before = m.state()["weights"]
        f = forecast(m, now=49, end=51, cutoff=49)[1]
        m.resolve(f["ticket"], [row(49)], observed_at=52)
        raw = {k: before[k]**.5 * math.exp(-1.25*p*p) for k,p in f["expert_probabilities"].items()}
        total = sum(raw.values())
        for k,v in raw.items(): self.assertAlmostEqual(m.state()["weights"][k],v/total)

    def test_shuffled_history_cannot_invent_complete_windows(self):
        h = FLOW.FlowHistory(period=4, window=3, minimum=2)
        for t in reversed(range(1,9)):
            h.add(FLOW.FlowInterval(t,"CARROT",6,6,6,6,"identified"))
        f = predict_history(CausalWindowEnsemble("shuffled","CARROT"),h,now=9,end=11,cutoff=9,threshold=5)
        self.assertEqual(f["unknown_mass"],1)
        self.assertEqual(f["support"],0)

    def test_nonboolean_history_readiness_rejected(self):
        p = prediction(); p["ready"] = "false"
        with self.assertRaises(ValueError): experts_from_prediction(p,now=25,end=27)

    def test_actual_history_excludes_missing_and_future(self):
        h = FLOW.FlowHistory(period=4, window=3, minimum=2)
        for t in range(1, 9):
            h.add(FLOW.FlowInterval(t, "CARROT", 6 if t % 4 == 1 else 0,
                                   6 if t % 4 == 1 else 0, 0, 0, "identified"))
        m = CausalWindowEnsemble("history", "CARROT")
        f = predict_history(m, h, now=9, end=11, cutoff=9, threshold=5)
        self.assertEqual(f["support"], 2)
        self.assertEqual(f["expert_probabilities"]["same_phase"], 1)
        h.add(FLOW.FlowInterval(9, "CARROT", 9, 9, 9, 9, "identified"))
        with self.assertRaises(ValueError): predict_history(m, h, now=9, end=11, cutoff=9, threshold=5)


class EngineTests(unittest.TestCase):
    def test_normal_and_floor_receipts_both_seats(self):
        for seat in (0, 1):
            iv, detail = market_interval(25, seat, 6)
            self.assertEqual((iv.lower, iv.upper, iv.reason), (6, 6, "identified"))
            WITNESSES.append(detail)
            iv, detail = market_interval(25, seat, 6, floor=True)
            self.assertEqual(iv.reason, "floor_censored")
            self.assertEqual(interval_label([iv], product="CARROT", now=25, cutoff=25, threshold=5)["label"], None)
            WITNESSES.append(detail)

    def test_same_public_history_different_hidden_stock(self):
        a, da = market_interval(25, 0, 0, hidden_stock=6)
        b, db = market_interval(25, 0, 0, hidden_stock=80)
        self.assertEqual(da["public_before"], db["public_before"])
        self.assertEqual(da["public_after"], db["public_after"])
        ha, hb = FLOW.FlowHistory(minimum=1), FLOW.FlowHistory(minimum=1)
        ha.add(a); hb.add(b)
        fa = predict_history(CausalWindowEnsemble("same", "CARROT"), ha, now=49,end=49,cutoff=49,threshold=5)
        fb = predict_history(CausalWindowEnsemble("same", "CARROT"), hb, now=49,end=49,cutoff=49,threshold=5)
        self.assertEqual(fa, fb)

    def test_prequential_cadence_switch_and_censoring(self):
        for seat in (0, 1):
            game = f"synthetic-market-seat{seat}"
            learner = CausalWindowEnsemble(game, "CARROT")
            h = FLOW.FlowHistory(period=4, window=5, minimum=2)
            EVENTS.append({"kind":"start", "game_id":game,"product":"CARROT",
                           "split":"synthetic-development","opponent_family":"manufactured-cadence"})
            for k in range(14):
                now = 1 + 4*k; end = now+2
                p = h.window_prediction("CARROT", now, end)
                start = time.perf_counter_ns()
                f = learner.predict(p, now=now,end=end,cutoff=now,threshold=5)
                TIMINGS.append((time.perf_counter_ns()-start)/1e6)
                EVENTS.append({"kind":"forecast","game_id":game,"product":"CARROT","prediction":p,
                               "now":now,"end":end,"cutoff":now,"threshold":5})
                old_weights = learner.state()["weights"]
                ivs = []
                for j in range(3):
                    q = 6 if (j == 0 if k < 6 else j == 1) else 0
                    iv, _ = market_interval(now+j, seat, q, floor=k>=12)
                    ivs.append(iv); h.add(iv)
                # Window is complete before the target subwindow is resolved.
                r = learner.resolve(f["ticket"], ivs[:1], observed_at=end+1)
                EVENTS.append({"kind":"outcome","game_id":game,"product":"CARROT","ticket":f["ticket"],
                               "observed_at":end+1,"intervals":[ivs[0].as_dict()]})
                if k>=12:
                    self.assertIsNone(r["label"])
                    self.assertEqual(learner.state()["weights"], old_weights)
                else:
                    self.assertEqual(r["label"], int(k < 6))
            self.assertEqual(learner.state()["identified"], 12)
            self.assertEqual(learner.state()["censored"], 2)
        result = replay(EVENTS)
        self.assertEqual(len(result["outcomes"]),28)
        self.assertFalse(result["pending"])
        self.assertEqual(sum(r["label"] is None for r in result["outcomes"]),4)
        # Cadence-change prediction errors remain in the output; no performance claim.
        self.assertTrue(any(r["scores"].get("model",{}).get("brier",0) > .5
                            for r in result["outcomes"]))


class ReportingTests(unittest.TestCase):
    def test_reliability_and_complete_game_split(self):
        m, f = forecast(); r=m.resolve(f["ticket"],[row()],observed_at=28)
        r.update(split="dev",opponent_family="one")
        out=summarize([r]); self.assertEqual(out["game_count"],1)
        self.assertAlmostEqual(out["groups"][0]["scores"]["zero_control"]["mean_brier"],0)
        changed=copy.deepcopy(r); changed["split"]="held"
        with self.assertRaises(ValueError): summarize([r,changed])

    def test_event_families_have_distinct_tickets_and_groups(self):
        a, fa = forecast(CausalWindowEnsemble("same-game", "CARROT"))
        b, fb = forecast(CausalWindowEnsemble("same-game", "CARROT"), threshold=7)
        self.assertNotEqual(fa["ticket"],fb["ticket"])
        ra=a.resolve(fa["ticket"],[row(lo=6,hi=6)],observed_at=28)
        rb=b.resolve(fb["ticket"],[row(lo=6,hi=6)],observed_at=28)
        self.assertEqual({g["threshold"] for g in summarize([ra,rb])["groups"]},{5,7})

    def test_ticket_string_components_cannot_alias(self):
        a=CausalWindowEnsemble("g/CARROT","MILK")
        b=CausalWindowEnsemble("g","CARROT/MILK")
        fa=forecast(a)[1]; fb=forecast(b)[1]
        self.assertNotEqual(fa["ticket"],fb["ticket"])

    def test_duplicate_diagnostic_ticket_rejected(self):
        m,f=forecast(); r=m.resolve(f["ticket"],[row()],observed_at=28)
        with self.assertRaisesRegex(ValueError,"duplicate outcome"):
            summarize([r,copy.deepcopy(r)])

    def test_cli_real_fixture_and_readback(self):
        # EngineTests alphabetically precedes ReportingTests in the loaded suite.
        self.assertTrue(EVENTS)
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"input.jsonl"; out=Path(temp)/"output.json"
            src.write_text("".join(json.dumps(e)+"\n" for e in EVENTS),encoding="utf-8")
            p=subprocess.run([sys.executable,str(Path(__file__).with_name("replay.py")),str(src),"--output",str(out)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            expected=json.loads(json.dumps(replay(EVENTS)))
            self.assertEqual(json.loads(out.read_text()),expected)

    def test_cli_preserves_pending_and_rejects_reuse(self):
        events=[{"kind":"start","game_id":"g","product":"CARROT"}]
        events.append({"kind":"forecast","game_id":"g","product":"CARROT","prediction":prediction(),
                       "now":25,"end":27,"cutoff":25,"threshold":5})
        out=replay(events); self.assertEqual(len(out["pending"]),1)
        with self.assertRaisesRegex(ValueError,"event 3"):
            replay(events+[events[0]])

    def test_cli_game_group_independence(self):
        records=[]
        for gid, split in (("dev-game","dev"),("held-game","held")):
            m,f=forecast(CausalWindowEnsemble(gid,"CARROT"))
            r=m.resolve(f["ticket"],[row(lo=6,hi=6)],observed_at=28)
            r.update(split=split,opponent_family="fixture")
            self.assertEqual(r["forecast"]["prior_rate_control"],.5)
            records.append(r)
        self.assertEqual(summarize(records)["game_count"],2)


def main():
    global FLOW, ENGINE
    p=argparse.ArgumentParser(description=__doc__)
    root=Path(__file__).resolve().parents[1]
    p.add_argument("--flow-file",type=Path,default=root/"cloud-market-response"/"flow.py")
    p.add_argument("--engine-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path)
    args=p.parse_args()
    FLOW=load(args.flow_file,"quill_existing_flow")
    ENGINE=load_engine(args.engine_dir/"kaggriculture.py")
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if args.output_dir:
        args.output_dir.mkdir(parents=True,exist_ok=True)
        blobs={"flow.py":git_blob(args.flow_file),"kaggriculture.py":git_blob(args.engine_dir/"kaggriculture.py")}
        files={q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in Path(__file__).parent.glob("*.py")}
        report={"tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
                "engine_market_stages":MARKET_STAGES,
                "official_engine_blob_matched":blobs["kaggriculture.py"]==ENGINE_BLOB,"full_games":0,"seeds_consumed":[],
                "input_blobs":blobs,"runtime_sha256":files,
                "flow_source_commit":FLOW_COMMIT if blobs["flow.py"]==FLOW_BLOB else None,
                "engine_source_commit":ENGINE_COMMIT if blobs["kaggriculture.py"]==ENGINE_BLOB else None,
                "synthetic_forecasts":len(TIMINGS),"max_warm_predict_ms":max(TIMINGS,default=None),
                "observed_failures_retained": "cadence-switch errors remain in forecast scores",
                "validation_scope":"manufactured public market stages and actual FlowHistory, not full games or calibration validation"}
        (args.output_dir/"check-results.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        (args.output_dir/"public-market-fixture.jsonl").write_text("".join(json.dumps(e,sort_keys=True)+"\n" for e in EVENTS))
        (args.output_dir/"market-witnesses.json").write_text(json.dumps(WITNESSES,indent=2,sort_keys=True)+"\n")
        (args.output_dir/"prequential-results.json").write_text(json.dumps(replay(EVENTS),indent=2,sort_keys=True)+"\n")
    return 0 if result.wasSuccessful() else 1


if __name__=="__main__":
    raise SystemExit(main())
