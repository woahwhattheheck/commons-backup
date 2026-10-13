"""Full-game standalone protocol for the packaged adapter.

A microbenchmark on one observation does not establish that a hosted archive
works. This runs COMPLETE games in which the agent lives in a separate process
that cannot import `kaggle_environments` at all -- at import or at any turn -- and
speaks to the harness over a pipe. The harness holds the engine; the agent holds
only the bundled transition and quote.

Measured across the whole game, not as an episode total:

  cold start           process launch through the first returned action
  max per-turn action  the worst single decision, which is what a per-step budget
                       actually has to cover
  p50 / p99            the shape of the rest

The action the isolated agent returns is compared turn by turn against the same
agent running in-process, so "it ran" and "it played the same game" are separate
claims.
"""

import argparse
import json
import os
import subprocess
import sys
import time

import cards as cards_mod

CHILD = r'''
import json, os, sys, time
T0 = float(os.environ["T0"])
class _Block:
    def find_module(self, name, path=None):
        if name == "kaggle_environments" or name.startswith("kaggle_environments."):
            raise ImportError("kaggle_environments is not available to the agent")
        return None
sys.meta_path.insert(0, _Block())
sys.path.insert(0, os.environ["LAB"])
import titan_adapter
ready = time.time() - T0
sys.stdout.write(json.dumps({"event": "ready", "import_s": ready,
                             "config": titan_adapter.CONFIG}) + "\n")
sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg.get("event") == "stop":
        break
    t = time.time()
    act = titan_adapter.agent(msg["observation"], msg.get("configuration"))
    dt = time.time() - t
    sys.stdout.write(json.dumps({"event": "action", "action": act,
                                 "action_s": dt,
                                 "since_launch_s": time.time() - T0}) + "\n")
    sys.stdout.flush()
'''


def run_game(seed, seat, opponent, lab, compare_inprocess=True):
    import arlene_arm
    import route_cards
    A, arl_id = route_cards.load_arlene()
    opp, opp_id = arlene_arm.make_opponent(opponent, A)
    env = cards_mod.make_env(seed)
    env.reset(2)

    env2 = dict(os.environ, LAB=lab, T0=repr(time.time()),
                PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, "-c", CHILD], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env2, bufsize=1)
    hello = json.loads(proc.stdout.readline())
    assert hello["event"] == "ready", hello

    mirror = None
    if compare_inprocess:
        import titan_adapter
        mirror = titan_adapter.make_agent()

    times, mismatches, cold = [], [], None
    n = 0
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                payload = {"observation": json.loads(json.dumps(dict(obs),
                                                                default=str)),
                           "configuration": json.loads(json.dumps(
                               dict(env.configuration), default=str))}
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
                rep = json.loads(proc.stdout.readline())
                if cold is None:
                    cold = rep["since_launch_s"]
                times.append(rep["action_s"])
                acts[i] = rep["action"]
                if mirror is not None:
                    want = mirror.act(obs)
                    if json.loads(json.dumps(want, default=str)) != acts[i]:
                        mismatches.append({"step": n, "isolated": acts[i],
                                           "in_process": want})
            else:
                acts[i] = opp(obs, env.configuration)
        env.step(acts)
        n += 1
    proc.stdin.write(json.dumps({"event": "stop"}) + "\n")
    proc.stdin.flush()
    err = proc.stderr.read()
    proc.wait(timeout=30)

    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    times.sort()
    def q(p):
        return times[min(len(times) - 1, int(len(times) * p))] if times else None
    return {"seed": seed, "seat": seat, "opponent": opponent,
            "opponent_id": opp_id, "config": hello["config"],
            "turns": n, "rounds_played": len(times),
            "own_cash": own, "rival_cash": rival, "margin": own - rival,
            "import_s": round(hello["import_s"], 4),
            "cold_start_to_first_action_s": round(cold, 4),
            "max_action_s": round(max(times), 4) if times else None,
            "p99_action_s": round(q(0.99), 4) if times else None,
            "p50_action_s": round(q(0.50), 4) if times else None,
            "mean_action_s": round(sum(times) / len(times), 5) if times else None,
            "action_mismatches_vs_in_process": len(mismatches),
            "first_mismatch": mismatches[0] if mismatches else None,
            "child_stderr_tail": err[-400:] if err else ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--no-compare", action="store_true")
    ap.add_argument("--out", default="results/standalone-protocol.json")
    a = ap.parse_args()
    lab = os.path.dirname(os.path.abspath(__file__))
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                r = run_game(seed, seat, opp, lab, not a.no_compare)
                rows.append(r)
                print(f"seed {seed} seat {seat} vs {opp:7s}  {r['rounds_played']:3d} "
                      f"turns  own {r['own_cash']:9.0f} margin {r['margin']:+9.0f}  "
                      f"cold {r['cold_start_to_first_action_s'] * 1000:6.1f}ms  "
                      f"MAX action {r['max_action_s'] * 1000:6.1f}ms  "
                      f"p99 {r['p99_action_s'] * 1000:5.1f}ms  "
                      f"p50 {r['p50_action_s'] * 1000:4.1f}ms  "
                      f"mismatches {r['action_mismatches_vs_in_process']}", flush=True)
                if r["child_stderr_tail"]:
                    print(f"    child stderr: {r['child_stderr_tail']}", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)
    worst = max((r["max_action_s"] for r in rows), default=0)
    print(f"\nworst single action across {len(rows)} full game(s): "
          f"{worst * 1000:.1f}ms; total mismatches "
          f"{sum(r['action_mismatches_vs_in_process'] for r in rows)}")


if __name__ == "__main__":
    main()
