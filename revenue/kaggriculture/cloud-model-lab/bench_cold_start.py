"""Cold start through first action, measured in a fresh process.

A warmed import says nothing about the hosted first turn, where the process starts
cold and the engine's own 1s-per-step budget (with a 60s episode overage) begins at
the first call. This spawns a NEW interpreter per sample and times, inside it:

  t_import    process start -> the motif layer and its bundled transition imported
  t_table     -> the compiled literal imported
  t_first     -> the first proposal returned for a real captured observation
  t_steady    the mean of the next N proposals in the same process

`--no-engine-package` runs the sample with `kaggle_environments` made unimportable,
which is the check that the archive stands on `engine_pin.py` alone.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

CHILD = r'''
import json, os, sys, time
T0 = float(os.environ["T0"])
if os.environ.get("NO_ENGINE_PACKAGE"):
    class _Block:
        def find_module(self, name, path=None):
            if name == "kaggle_environments" or name.startswith("kaggle_environments."):
                raise ImportError("kaggle_environments blocked for this sample")
            return None
    sys.meta_path.insert(0, _Block())
sys.path.insert(0, os.environ["LAB"])
import native_motifs as NM
import run_cards
t_import = time.time() - T0
import motifs_table
t_table = time.time() - T0
card = json.load(open(os.environ["CARD"]))
obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
baseline = json.loads(os.environ["BASELINE"])
p = NM.Proposer(motifs_table.TABLE)
K = NM.engine()
board = len(obs["farms"][seat]["tiles"])
t0 = time.time()
act, notes = p.propose(obs, cfg, seat, baseline)
# Pricing a candidate is part of an action, so the measured action includes it.
tg = run_cards.reachable_targets(obs, seat, tuple(obs["farms"][seat]["farmer"]),
                                 K, board, obs["market"]["prices"])
t_first = time.time() - T0
first_call = time.time() - t0
steady = []
for _ in range(int(os.environ.get("N", "10"))):
    t = time.time()
    p.propose(obs, cfg, seat, baseline)
    run_cards.reachable_targets(obs, seat, tuple(obs["farms"][seat]["farmer"]),
                                K, board, obs["market"]["prices"])
    steady.append(time.time() - t)
print(json.dumps({"t_import": t_import, "t_table": t_table, "t_first": t_first,
                  "first_call_s": first_call,
                  "steady_mean_s": sum(steady) / len(steady),
                  "steady_max_s": max(steady),
                  "transition": NM.engine().__name__,
                  "priced_targets": len(tg),
                  "pricing_module": getattr(run_cards._pricer(K), "__module__", "?"),
                  "changed": act != baseline}))
'''


def sample(lab, card_path, baseline, no_engine, n):
    env = dict(os.environ, LAB=lab, CARD=card_path, N=str(n),
               BASELINE=json.dumps(baseline), T0=repr(time.time()))
    if no_engine:
        env["NO_ENGINE_PACKAGE"] = "1"
    out = subprocess.run([sys.executable, "-c", CHILD], capture_output=True,
                         text=True, env=env)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[-800:])
    return json.loads(out.stdout.strip().split("\n")[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=8080021)
    ap.add_argument("--step", type=int, default=165)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--steady", type=int, default=10)
    ap.add_argument("--baseline", default="../20260907-offline-agent/main.py::agent",
                    help="the real hosted baseline, so the measured turn is the "
                         "shape actually deployed rather than an all-PASS stub")
    ap.add_argument("--out", default="results/cold-start.json")
    a = ap.parse_args()
    lab = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, lab)
    import cards as cards_mod
    import constraints
    card = cards_mod.capture(a.seed, [a.step], seat=0)[0]
    import motif_arm
    base_ag, base_id = motif_arm.load_agent(a.baseline)
    baseline = motif_arm.call(base_ag, card["observation"], card["configuration"])
    baseline = json.loads(json.dumps(baseline, default=str))
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "coldstart-card.json")
    json.dump(card, open(tmp, "w"), default=str)
    rows = {}
    for label, no_engine in (("engine package importable", False),
                             ("engine package blocked", True)):
        got = [sample(lab, tmp, baseline, no_engine, a.steady)
               for _ in range(a.samples)]
        rows[label] = {
            "samples": len(got),
            "transition": got[0]["transition"],
            "workers": len(baseline["hands"]) + 1,
            "baseline": base_id["label"],
            "cold_to_first_action_s": round(statistics.median(
                g["t_first"] for g in got), 3),
            "cold_to_first_action_max_s": round(max(g["t_first"] for g in got), 3),
            "import_s": round(statistics.median(g["t_import"] for g in got), 3),
            "table_import_s": round(statistics.median(
                g["t_table"] - g["t_import"] for g in got), 4),
            "first_call_s": round(statistics.median(g["first_call_s"] for g in got), 4),
            "steady_mean_s": round(statistics.median(g["steady_mean_s"] for g in got), 4),
            "steady_max_s": round(max(g["steady_max_s"] for g in got), 4),
            "max_action_s": round(max(max(g["first_call_s"], g["steady_max_s"])
                                      for g in got), 4),
            "priced_targets": got[0]["priced_targets"],
            "pricing_module": got[0]["pricing_module"],
        }
        r = rows[label]
        print(f"{label:28s} transition={r['transition']:10s} "
              f"pricing={r['pricing_module']:10s} targets={r['priced_targets']:2d}  "
              f"cold->first action {r['cold_to_first_action_s']:.3f}s "
              f"(max {r['cold_to_first_action_max_s']:.3f}s), "
              f"MAX ACTION {r['max_action_s'] * 1000:.1f}ms, "
              f"steady {r['steady_mean_s'] * 1000:.1f}ms")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"seed": a.seed, "step": a.step, "baseline": base_id, "rows": rows},
              open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
