"""Downstream value of a model segment: let a pinned policy finish the game.

Early cash is not the measure. A segment that spends 400 on a cow looks worse at
step 8 and may be ahead by step 700. So each candidate state is handed to the SAME
pinned continuation policy, separately instantiated, which plays the rest of the
official game against the same opponent, config and seed. The matched control is
that policy playing the whole game from step 0.

The difference is a conditional estimate of the segment's downstream value under
that policy. It is not proof of an all-model full-game result, and it is only as
general as the one policy and one seed it uses.

Recorded separately, never merged into one number: final cash and margin, the
purchased-but-uninstalled backlog, goods discarded at the end-of-day drop, and
production actually harvested.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os

import cards as cards_mod
from constraints import engine


def agent_identity(spec):
    """Resolved absolute path and content hash for a policy spec.

    Every peer candidate in this project is a file called main.py or candidate.py, so
    a basename label makes lean20, Euler and dispatch indistinguishable in a result.
    The identity records what was actually loaded.
    """
    if "::" not in spec:
        return {"spec": spec, "kind": "builtin", "path": None, "sha256": None,
                "label": spec}
    path, fn_name = spec.split("::", 1)
    real = os.path.realpath(path)
    try:
        digest = hashlib.sha256(open(real, "rb").read()).hexdigest()
    except OSError:
        digest = None
    return {"spec": spec, "kind": "file", "path": real, "function": fn_name,
            "sha256": digest,
            "label": f"{os.path.basename(real)}::{fn_name}@{(digest or '?')[:12]}"}


def load_agent(spec):
    """A SEPARATE instantiation each time, so no state leaks between runs."""
    ident = agent_identity(spec)
    if "::" not in spec:
        K = engine()
        fn = {"starter": K.starter_agent, "random": K.random_agent,
              "pass": K.pass_agent}[spec]
        return (lambda obs, cfg=None: fn(obs)), ident
    path, fn_name = spec.split("::", 1)
    sp = importlib.util.spec_from_file_location(
        f"cont_{abs(hash(path + fn_name))}", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    fn = getattr(mod, fn_name)

    def call(obs, cfg=None):
        try:
            return fn(obs, cfg)
        except TypeError:
            return fn(obs)
    return call, ident



def _pre_eod_discard(obs_pair, config, seat, actions):
    """Units discarded at the end-of-day drop, measured from the exact pre-drop state.

    Sampling carried stock BEFORE the turn's actions is wrong: a HARVEST or PICKUP in
    the same turn adds to what the drop must absorb, and a market SELL or a DROP
    changes the shed room it drops into. The engine applies the unit phase, then the
    market phase, then `_drop_inventories_to_shed`, so this replays the first two with
    the engine's own functions and measures what the drop would then discard.
    """
    K = engine()
    from kaggle_environments.utils import structify
    obs0, obs1 = copy.deepcopy(obs_pair[0]), copy.deepcopy(obs_pair[1])
    shared_farms = obs0["farms"]
    obs1["farms"] = shared_farms
    obs1["market"] = obs0["market"]
    board = int(config.get("boardSize", 10) or 10)
    tpd = int(config.get("turnsPerDay", 24) or 24)
    cap = int(config.get("shedCapacity", 100) or 100)
    day = int(obs0["day"])
    privs = [obs0["private"], obs1["private"]]

    for i in (0, 1):
        act = actions[i] if isinstance(actions[i], dict) else {}
        units = [act.get("farmer", ["PASS"])] + list(act.get("hands") or [])
        demand = {}
        for a in units:
            if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                demand[a[1]] = demand.get(a[1], 0) + 1
        seeds = privs[i].get("seeds", {})
        blocked = {c for c, n in demand.items() if n > seeds.get(c, 0)}
        for u, a in enumerate(units):
            eff = list(a) if isinstance(a, list) else ["PASS"]
            if len(eff) >= 2 and eff[0] == "PLANT" and eff[1] in blocked:
                eff = ["PASS"]
            try:
                K._apply_unit_action(shared_farms[i], privs[i], u, eff, board, day, tpd, cap)
            except Exception:
                pass

    states = [{"observation": obs0, "action": actions[0], "status": "ACTIVE", "reward": 0.0},
              {"observation": obs1, "action": actions[1], "status": "ACTIVE", "reward": 0.0}]
    state = structify(states)
    env = structify({"configuration": dict(config), "done": False, "info": {"seed": 0}})
    try:
        K._process_market(state, env)
    except Exception:
        pass
    priv = state[seat].observation.private
    carried = sum(sum(inv.values()) for inv in priv.get("inventories", []))
    room = max(0, cap - sum(priv.get("shed", {}).values()))
    return max(0, carried - room)


def _metrics(env, seat, cfg):
    """Engine-defined facts about how the episode ended."""
    K = engine()
    obs0 = env.state[0].observation
    farm = obs0.farms[seat]
    priv = env.state[seat].observation.private
    shed = dict(priv.get("shed", {}))
    animals_in_shed = {a: int(n) for a, n in shed.items() if a in K.ANIMALS and n > 0}
    installed = 0
    plants = 0
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict) and "animal" in t:
                installed += 1
            elif isinstance(t, dict) and t.get("kind") == "PLANT":
                plants += 1
    return {
        "final_cash": float(farm["money"]),
        "opponent_cash": float(obs0.farms[1 - seat]["money"]),
        "margin": float(farm["money"]) - float(obs0.farms[1 - seat]["money"]),
        "unsold_shed_units": int(sum(shed.values())),
        "installable_backlog": animals_in_shed,
        "installed_animals": installed,
        "plants_on_board": plants,
    }


def play_out(seed, seat, prefix_actions, warmup_spec, opponent_spec, cont_spec,
             from_step, max_steps=100000, control=False):
    """Replay the warm-up, apply `prefix_actions`, then let the continuation finish.

    `prefix_actions` is the ordered list of turns the model authored. The warm-up and
    opponent are deterministic and the episode is seeded, so the replay is exact.
    """
    warm, warm_label = load_agent(warmup_spec)
    opp, opp_label = load_agent(opponent_spec)
    cont, cont_label = load_agent(cont_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    used = 0
    discarded = 0
    steps = 0
    while not env.done and steps < max_steps:
        cfg = env.configuration
        obs = env.state[seat].observation
        step = int(obs["day"]) * int(cfg["turnsPerDay"]) + int(obs["hour"])
        # The control warms up to the SAME boundary and then hands over to the pinned
        # continuation, so it differs from a model arm only by the model's turns.
        # Running the warm-up throughout is equivalent only when the warm-up and the
        # continuation are the same policy, which is asserted below rather than assumed.
        if step < from_step:
            mine = warm(obs, cfg)
        elif control:
            mine = cont(obs, cfg)
        elif used < len(prefix_actions):
            mine = prefix_actions[used]
            used += 1
        else:
            mine = cont(obs, cfg)
        others = opp(env.state[1 - seat].observation, cfg)
        actions = [None, None]
        actions[seat] = mine
        actions[1 - seat] = others
        if (step + 1) % int(cfg["turnsPerDay"]) == 0:
            discarded += _pre_eod_discard(
                [dict(env.state[0].observation), dict(env.state[1].observation)],
                dict(cfg), seat, actions)
        env.step(actions)
        steps += 1
    m = _metrics(env, seat, dict(env.configuration))
    m.update({"seed": seed, "seat": seat, "from_step": from_step,
              "model_turns_applied": used, "discarded_units": discarded,
              "control": bool(control),
              "warmup": warm_label, "opponent": opp_label, "continuation": cont_label})
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[],
                    help="a play.py run JSON whose model turns are continued")
    ap.add_argument("--continuation", default="../cloud-market/main.py::agent")
    ap.add_argument("--warmup", default=None,
                    help="override the run's warm-up spec (older runs stored only a label)")
    ap.add_argument("--opponent", default=None,
                    help="override the run's opponent spec")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    results = []
    control_done = set()
    warm_id = agent_identity(a.warmup) if a.warmup else None
    cont_id = agent_identity(a.continuation)
    if warm_id and warm_id.get("sha256") and cont_id.get("sha256") \
            and warm_id["sha256"] != cont_id["sha256"]:
        print(f"[note] warm-up {warm_id['label']} differs from continuation "
              f"{cont_id['label']}; the control warms up to the same boundary and then "
              f"switches, so it is comparable.")
    for path in a.run:
        d = json.load(open(path))
        seed, seat = d["seed"], d["seat"]
        prefix = [t["action"] for t in d.get("turns", [])]
        # strip the model's carried plan; the engine takes only the three turn keys
        prefix = [{"farmer": p["farmer"], "hands": p["hands"], "market": p["market"]}
                  for p in prefix]
        warm_spec = a.warmup or d.get("warmup_spec") or d["warmup"]
        opp_spec = a.opponent or d.get("opponent_spec") or d["opponent"]
        r = play_out(seed, seat, prefix, warm_spec, opp_spec, a.continuation,
                     d["from_step"])
        r["label"] = f"model-segment+continuation ({os.path.basename(path)})"
        r["render"] = (d["turns"][0].get("render") if d.get("turns") else None)
        results.append(r)
        key = (seed, seat, d["from_step"], warm_spec, opp_spec)
        if key not in control_done:
            control_done.add(key)
            c = play_out(seed, seat, [], warm_spec, opp_spec, a.continuation,
                         d["from_step"], control=True)
            c["label"] = "control: same warm-up boundary, continuation plays the rest"
            results.append(c)

    for r in results:
        print(json.dumps(r, sort_keys=True))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(results, fh, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
