"""Independent repro of the reported full-game runtime failure, jobs=1.

WIDEFIELD reported, on this same VM: seed 9921012 versus COK10, candidate seat 1,
step 569, RPC 1.56202 s against a 1 s limit, with a prior maximum RETURNED agent
execution of 0.49109 s, engine 28b6d8af, jobs 2. Their outcome is retained as
theirs; this is a separate independent run at jobs=1 and it does not replace it.

The point of separating the clocks. The archive's guard starts its budget at
`TitanAgent.act` entry and stops when it returns, so what it can bound is only
the middle of the round trip. What a tournament RPC is judged on is

    transport in + deserialize + [ agent.act ] + serialize + transport out

so a returned-execution maximum of 0.49 s and an RPC of 1.56 s are not in
contradiction: they measure different intervals. This harness records all of
them per step so the difference is a measurement, not an inference:

  call_s        wall time around the agent call, in-process (no transport)
  internal_s    the guard's own elapsed_seconds from its diagnostics
  marshal_s     pickle round trip of the observation and the returned action,
                a lower bound on the RPC marshalling the guard cannot see
  status        completed | deadline_fallback, and the stage it fell back from

It also records whether the guard RETURNED under its own budget, which is the
question root actually asked: does the guard return under an external deadline.

  python -B titan_deadline_repro.py --seed 9921012 --seat 1 --opponent cok
"""

import argparse
import json
import os
import pickle
import resource
import sys
import time

import cards as cards_mod

ARCHIVE = "/home/user/work/titan-current"


def load_titan():
    """The archive's own canonical entrypoint, unmodified, from its own root."""
    import importlib.util
    if ARCHIVE not in sys.path:
        sys.path.insert(0, ARCHIVE)
    spec = importlib.util.spec_from_file_location(
        f"titan_main_{time.time_ns()}", os.path.join(ARCHIVE, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=9921012)
    ap.add_argument("--seat", type=int, default=1)
    ap.add_argument("--opponent", default="cok")
    ap.add_argument("--focus-step", type=int, default=569)
    ap.add_argument("--out", default="results/titan-deadline-repro.json")
    a = ap.parse_args()

    import arlene_arm
    import route_cards
    A, _ = route_cards.load_arlene()
    opp, opp_id = arlene_arm.make_opponent(a.opponent, A)

    t0 = time.perf_counter()
    titan = load_titan()
    import_s = time.perf_counter() - t0

    env = cards_mod.make_env(a.seed)
    env.reset(2)
    rows = []
    inst = None
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i != a.seat:
                acts[i] = opp(obs, env.configuration)
                continue
            # marshalling the guard never sees: what an RPC pays either side
            m0 = time.perf_counter()
            payload = pickle.dumps(dict(obs), protocol=pickle.HIGHEST_PROTOCOL)
            _ = pickle.loads(payload)
            obs_marshal = time.perf_counter() - m0
            c0 = time.perf_counter()
            out = titan.agent(obs, env.configuration)
            call_s = time.perf_counter() - c0
            m1 = time.perf_counter()
            back = pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL)
            _ = pickle.loads(back)
            act_marshal = time.perf_counter() - m1
            inst = titan._INSTANCE
            d = dict(getattr(inst, "diagnostics", {}) or {})
            rows.append({
                "step": int(obs.get("step") or (int(obs["day"]) * 24 + int(obs["hour"]))),
                "call_s": round(call_s, 6),
                "internal_s": round(float(d.get("elapsed_seconds", 0.0)), 6),
                "marshal_s": round(obs_marshal + act_marshal, 6),
                "obs_bytes": len(payload), "action_bytes": len(back),
                "status": d.get("status"), "fallback_stage": d.get("fallback_stage"),
                "consumer": d.get("consumer"), "parent_calls": d.get("parent_calls"),
            })
            acts[i] = out
        env.step(acts)

    farms = env.state[0].observation.farms
    own, rival = float(farms[a.seat]["money"]), float(farms[1 - a.seat]["money"])
    calls = sorted(r["call_s"] for r in rows)
    over = [r for r in rows if r["call_s"] + r["marshal_s"] > 1.0]
    fb = [r for r in rows if r["status"] == "deadline_fallback"]
    focus = [r for r in rows if r["step"] == a.focus_step]
    budget = 1.0 - 0.01
    breached = [r for r in rows if r["internal_s"] > budget]
    out = {
        "seed": a.seed, "seat": a.seat, "opponent": a.opponent,
        "opponent_id": opp_id, "jobs": 1, "engine_pin": cards_mod.ENGINE_PIN,
        "archive_sha256": "70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb",
        "import_s": round(import_s, 6), "actions": len(rows),
        "own_cash": own, "rival_cash": rival,
        "call_s": {"max": calls[-1], "p999": calls[int(0.999 * len(calls)) - 1],
                   "p99": calls[int(0.99 * len(calls)) - 1],
                   "p50": calls[len(calls) // 2], "mean": round(sum(calls) / len(calls), 6)},
        "max_internal_s": max(r["internal_s"] for r in rows),
        "max_marshal_s": max(r["marshal_s"] for r in rows),
        "max_obs_bytes": max(r["obs_bytes"] for r in rows),
        "deadline_fallbacks": len(fb),
        "guard_budget_breaches_internal": len(breached),
        "cells_over_1s_including_marshal": [r["step"] for r in over],
        "focus_step": focus,
        "slowest_10": sorted(rows, key=lambda r: -r["call_s"])[:10],
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"summary": out, "rows": rows}, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
