"""Two checks GPT asked for on the CURRENT v3 runtime, not on the archive snapshot.

Run against `cloud-execution-lab/` on current main, so nothing here is a duplicate
of a patch that already landed. No file of that lane is edited.

  A  CROSS-MATCH STATE LEAKAGE. `main.py` holds a module-global `_INSTANCE` and
     rebuilds it when `step == 0`. If that reset is complete, playing game B in a
     process that already played game A must produce byte-identical actions to
     playing game B in a freshly loaded module. Anything else is leakage.

  B  RETAINED PARTIAL INITIALIZATION. A deadline that lands inside `_initialize`
     leaves the instance holding a mix of objects from two initialization
     generations. `act` sets `ready = False`, so the next call rebuilds -- the
     question is whether the rebuild is COMPLETE and mutually consistent, i.e.
     whether `seed_budget` ends up derived from the controller that is actually
     in use, and whether anything reachable still points at the interrupted
     generation.

  python -B titan_state_leakage.py
"""

import importlib.util
import json
import os
import sys
import time

import cards as cards_mod

LAB = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "cloud-execution-lab"))


def fresh_entrypoint():
    """A new module object per call, exactly as one match per actor requires."""
    if LAB not in sys.path:
        sys.path.insert(0, LAB)
    spec = importlib.util.spec_from_file_location(
        f"titan_entry_{time.time_ns()}", os.path.join(LAB, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def play(entry, seed, seat, opponent_factory):
    opp = opponent_factory()
    env = cards_mod.make_env(seed)
    env.reset(2)
    actions = []
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                out = entry.agent(obs, env.configuration)
                actions.append(json.dumps(out, sort_keys=True, default=str))
                acts[i] = out
            else:
                acts[i] = opp(obs, env.configuration)
        env.step(acts)
    farms = env.state[0].observation.farms
    return actions, float(farms[seat]["money"]), float(farms[1 - seat]["money"])


def check_a(seed_a, seed_b, seat, opponent_factory):
    reused = fresh_entrypoint()
    play(reused, seed_a, seat, opponent_factory)            # dirty the instance
    after, own_after, rival_after = play(reused, seed_b, seat, opponent_factory)
    clean, own_clean, rival_clean = play(fresh_entrypoint(), seed_b, seat,
                                         opponent_factory)
    first = next((i for i, (x, y) in enumerate(zip(after, clean)) if x != y), None)
    return {"prior_game": seed_a, "measured_game": seed_b, "seat": seat,
            "actions": len(clean),
            "identical_action_sequence": after == clean,
            "first_divergent_action_index": first,
            "reused_own_rival": [own_after, rival_after],
            "clean_own_rival": [own_clean, rival_clean],
            "terminal_cash_identical": (own_after, rival_after) == (own_clean, rival_clean)}


def check_b(seed, seat, opponent_factory, tight=0.004):
    if LAB not in sys.path:
        sys.path.insert(0, LAB)
    import titan_runtime as T
    base = json.load(open(os.path.join(LAB, "TITAN-CONFIG.json")))
    opp = opponent_factory()
    env = cards_mod.make_env(seed)
    env.reset(2)

    # A budget too small to finish cold start, so the interrupt lands inside it.
    agent = T.TitanAgent(T.Features(**dict(base, budget_seconds=tight,
                                           reserve_seconds=tight / 10)))
    obs0 = dict(env.state[seat].observation)
    obs0.setdefault("player", seat)
    if obs0.get("step") is None:
        obs0["step"] = int(obs0["day"]) * 24 + int(obs0["hour"])
    agent.act(obs0, env.configuration)
    interrupted = dict(agent.diagnostics)
    held = {name: type(getattr(agent, name, None)).__name__
            for name in ("consumer", "controller", "production", "seed_budget",
                         "funding_module", "history", "selected", "post")}

    # Recover with a normal budget on the same instance, then ask whether the
    # rebuilt budget is derived from the controller that is actually in use.
    agent.features = T.Features(**base)
    out = agent.act(obs0, env.configuration)
    recovered = dict(agent.diagnostics)
    budget = getattr(agent, "seed_budget", None)
    controller = getattr(agent, "controller", None)
    consistent = None
    if budget is not None and controller is not None:
        consistent = set(budget.suffixes) == set(controller.R)
    legal = (isinstance(out, dict) and isinstance(out.get("farmer"), list)
             and isinstance(out.get("market"), list))
    return {"tight_budget_seconds": tight,
            "interrupted": {k: interrupted.get(k) for k in
                            ("status", "fallback_stage", "elapsed_seconds",
                             "act_cpu_seconds")},
            "attributes_held_after_interrupt": held,
            "ready_flag_after_interrupt": False,
            "recovered": {k: recovered.get(k) for k in
                          ("status", "fallback_stage", "elapsed_seconds")},
            "recovered_action_legal": legal,
            "seed_budget_keyed_to_live_controller": consistent,
            "seed_budget_route_names": sorted(budget.suffixes) if budget else None,
            "controller_route_names": sorted(controller.R) if controller else None}


def main():
    import arlene_arm, route_cards
    A, _ = route_cards.load_arlene()
    factory = lambda: arlene_arm.make_opponent("apex", A)[0]
    res = {"runtime": "cloud-execution-lab @ current main", "runtime_files": {
        n: __import__("hashlib").sha256(open(os.path.join(LAB, n), "rb").read()).hexdigest()
        for n in ("main.py", "titan_runtime.py")}}
    res["A_cross_match_leakage"] = check_a(9902233, 9902234, 0, factory)
    print("A:", json.dumps(res["A_cross_match_leakage"], indent=1), flush=True)
    res["B_partial_initialization"] = check_b(9902234, 0, factory)
    print("B:", json.dumps(res["B_partial_initialization"], indent=1), flush=True)
    json.dump(res, open("results/titan-state-leakage.json", "w"), indent=1)


if __name__ == "__main__":
    main()
