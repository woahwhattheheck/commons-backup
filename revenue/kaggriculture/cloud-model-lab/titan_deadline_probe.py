"""Two direct probes on the archive's guard. Unchanged source; config overlaid.

Root asked four things about the reported 1.56 s RPC. The full-game repro at
jobs=1 answered import/serialization and internal-versus-RPC time. These two
probes answer the other two, and they are the ones that decide whether the guard
is the problem.

  A  DOES THE GUARD ACTUALLY RETURN under a deadline it cannot meet?
     `TitanAgent` is constructed directly with a small budget -- the archive's
     files are not touched, not repacked and not substituted; only the Features
     dataclass the runtime already exposes is overlaid, and the overlay is
     recorded in the output. If the guard is sound it returns a LEGAL action
     within its own budget plus a small overshoot, and the overshoot is the
     number worth knowing.

  B  IS WALL TIME INFLATING WHILE CPU TIME DOES NOT?
     The same actions are replayed against K competing CPU burners, emulating the
     oversubscription of jobs=2 on a 4-core VM. Wall and CPU are recorded per
     action. If CPU is flat and wall inflates, the agent did not get slower --
     it got descheduled, and no policy change can fix that.

This VM is not Kaggle hardware and nothing here claims it is.

  python -B titan_deadline_probe.py --seed 9921012 --seat 1 --opponent cok
"""

import argparse
import json
import os
import subprocess
import sys
import time

import cards as cards_mod

ARCHIVE = "/home/user/work/titan-current"


def _set_root(root):
    """Point the probe at any runtime root -- the frozen archive or the live lane.

    The same measurement has to be runnable against the code that is actually
    shipping, otherwise a before/after on a landed patch is not possible.
    """
    global ARCHIVE
    ARCHIVE = os.path.realpath(root)


def _runtime():
    if ARCHIVE not in sys.path:
        sys.path.insert(0, ARCHIVE)
    import titan_runtime
    return titan_runtime


def legal(action, obs):
    """A returned fallback must still be a well-formed action for this seat."""
    seat = int(obs.get("player", 0))
    hands = obs["farms"][seat].get("hands", [])
    return (isinstance(action, dict) and isinstance(action.get("farmer"), list)
            and isinstance(action.get("hands"), list)
            and len(action["hands"]) == len(hands)
            and isinstance(action.get("market"), list))


def collect_cards(seed, seat, opponent, upto, T):
    """Real observations from a real game, driven by the archive's own default."""
    import arlene_arm, route_cards
    A, _ = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    agent = T.TitanAgent(T.Features(**json.load(open(os.path.join(ARCHIVE, "TITAN-CONFIG.json")))))
    env = cards_mod.make_env(seed)
    env.reset(2)
    cards, n = [], 0
    while not env.done and n <= upto:
        acts = [None, None]
        for i in range(2):
            o = env.state[i].observation
            if i == seat:
                oo = dict(o)
                if oo.get("step") is None:
                    oo["step"] = int(oo["day"]) * 24 + int(oo["hour"])
                oo.setdefault("player", seat)
                cards.append((oo, dict(env.configuration)))
                acts[i] = agent.act(o, env.configuration)
            else:
                acts[i] = opp(o, env.configuration)
        env.step(acts)
        n += 1
    return cards


def probe_a(cards, T, budgets):
    out = []
    for budget in budgets:
        agent = T.TitanAgent(T.Features(consumer="frozen", seed=True, funding=True,
                                        terminal_route=False, committed=True,
                                        budget_seconds=budget,
                                        reserve_seconds=min(0.01, budget / 10)))
        rows = []
        for obs, cfg in cards:
            t = time.perf_counter()
            act = agent.act(obs, cfg)
            el = time.perf_counter() - t
            d = dict(agent.diagnostics or {})
            rows.append({"step": obs["step"], "wall_s": round(el, 6),
                         "status": d.get("status"), "stage": d.get("fallback_stage"),
                         "legal": legal(act, obs)})
        fb = [r for r in rows if r["status"] == "deadline_fallback"]
        over = [r for r in rows if r["wall_s"] > budget]
        out.append({"budget_seconds": budget, "actions": len(rows),
                    "deadline_fallbacks": len(fb),
                    "all_returned_legal": all(r["legal"] for r in rows),
                    "max_wall_s": max(r["wall_s"] for r in rows),
                    "max_overshoot_s": round(max(r["wall_s"] for r in rows) - budget, 6),
                    "actions_over_budget": len(over),
                    "fallback_stages": sorted({r["stage"] for r in fb if r["stage"]})})
    return out


def probe_b(cards, T, loads):
    cfg0 = json.load(open(os.path.join(ARCHIVE, "TITAN-CONFIG.json")))
    out = []
    for k in loads:
        burners = [subprocess.Popen([sys.executable, "-c",
                                     "\nwhile True: pass\n"]) for _ in range(k)]
        try:
            time.sleep(0.4)
            agent = T.TitanAgent(T.Features(**cfg0))
            wall, cpu = [], []
            for obs, cfg in cards:
                w0, c0 = time.perf_counter(), time.process_time()
                agent.act(obs, cfg)
                wall.append(time.perf_counter() - w0)
                cpu.append(time.process_time() - c0)
        finally:
            for b in burners:
                b.kill()
                b.wait()
        wall.sort()
        cpu.sort()
        out.append({"competing_cpu_burners": k, "actions": len(wall),
                    "wall_max_s": round(wall[-1], 6),
                    "wall_p99_s": round(wall[int(0.99 * len(wall)) - 1], 6),
                    "wall_mean_s": round(sum(wall) / len(wall), 6),
                    "cpu_max_s": round(cpu[-1], 6),
                    "cpu_mean_s": round(sum(cpu) / len(cpu), 6),
                    "wall_over_cpu_mean": round((sum(wall) / len(wall)) /
                                                max(1e-9, sum(cpu) / len(cpu)), 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=9921012)
    ap.add_argument("--seat", type=int, default=1)
    ap.add_argument("--opponent", default="cok")
    ap.add_argument("--upto", type=int, default=600)
    ap.add_argument("--sample", type=int, default=120)
    ap.add_argument("--root", default=ARCHIVE,
                    help="runtime root holding main.py/titan_runtime.py/TITAN-CONFIG.json")
    ap.add_argument("--out", default="results/titan-deadline-probe.json")
    a = ap.parse_args()
    _set_root(a.root)
    T = _runtime()
    cards = collect_cards(a.seed, a.seat, a.opponent, a.upto, T)
    cards = cards[-a.sample:]
    print(f"collected {len(cards)} real cards ending at step {cards[-1][0]['step']}",
          flush=True)
    A = probe_a(cards, T, [1.0, 0.05, 0.01, 0.003])
    print("probe A done", flush=True)
    B = probe_b(cards, T, [0, 2, 6])
    res = {"runtime_root": ARCHIVE, "seed": a.seed, "seat": a.seat,
           "opponent": a.opponent,
           "cards": len(cards), "engine_pin": cards_mod.ENGINE_PIN,
           "runtime_files": {n: __import__("hashlib").sha256(
               open(os.path.join(ARCHIVE, n), "rb").read()).hexdigest()
               for n in ("main.py", "titan_runtime.py")},
           "source_modified": False,
           "overlay": "Features(budget_seconds=...) constructed directly; "
                      "archive files unchanged, unrepacked, unsubstituted",
           "not_kaggle_hardware": True,
           "probe_a_guard_under_deadline": A, "probe_b_contention": B}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({"probe_a": A, "probe_b": B}, indent=1))


if __name__ == "__main__":
    main()
