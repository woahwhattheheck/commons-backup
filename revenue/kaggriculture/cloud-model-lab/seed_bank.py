"""Seed the exemplar bank with TEACHER demonstrations from real official games.

The episode is stepped manually so the observation is captured BEFORE the agent is
called; pairing a recorded step's observation with that step's action would be wrong,
because the recorded observation already reflects it.

Only ADVANCING turns are banked -- the engine must have acted on the farmer's op --
which is the port of the source's `pos && m > 0` gate. Every row is labelled
`teacher:<name>`; none is presented as a model success.
"""

import argparse
import copy
import os

import cards as cards_mod
import constraints
import exemplar_bank as EB
import farmmap
import prompt as prompt_mod
from constraints import engine


def teacher_action(name, obs, config):
    K = engine()
    if name in ("starter", "random", "pass"):
        return {"starter": K.starter_agent, "random": K.random_agent,
                "pass": K.pass_agent}[name](obs)
    path, fn = name.split("::", 1)
    import importlib.util
    sp = importlib.util.spec_from_file_location("teach", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    try:
        return getattr(mod, fn)(obs, config)
    except TypeError:
        return getattr(mod, fn)(obs)



def _post_state(obs, config, seat, action):
    """The observation after the real interpreter applies `action` for `seat`."""
    import copy as _copy
    from kaggle_environments.utils import structify
    K = constraints.engine()
    obs_a = _copy.deepcopy(obs)
    obs_a["step"] = constraints.absolute_step(obs, config)
    other = 1 - seat
    obs_b = _copy.deepcopy(obs_a)
    obs_b["player"] = other
    obs_b["private"] = {"shed": {}, "inventories": [{}], "seeds": {}}
    states = [None, None]
    states[seat] = {"observation": obs_a, "action": _copy.deepcopy(action),
                    "status": "ACTIVE", "reward": 0.0}
    states[other] = {"observation": obs_b,
                     "action": {"farmer": ["PASS"], "hands": [], "market": []},
                     "status": "ACTIVE", "reward": 0.0}
    state = structify(states)
    env = structify({"configuration": constraints.visible_config(config),
                     "done": False, "info": {"seed": 0}})
    K.interpreter(state, env)
    post = dict(state[seat].observation)
    post["farms"] = state[0].observation.farms
    return post


def seed(bank_path, seeds, teacher="starter", seat=0, max_steps=400, exclude_seeds=()):
    K = engine()
    # write_path is explicit: EB.Bank without one is read-only, so a seeder that
    # omitted it recorded nothing while still exiting clean.
    bank = EB.Bank(bank_path, write_path=bank_path)
    banked = 0
    for sd in seeds:
        if sd in exclude_seeds:
            continue
        env = cards_mod.make_env(sd)
        env.reset(2)
        step = 0
        while not env.done and step < max_steps:
            obs = env.state[seat].observation
            cfg = dict(env.configuration)
            act = teacher_action(teacher, obs, cfg)
            other = teacher_action(teacher, env.state[1 - seat].observation, cfg)
            farmer = act.get("farmer", ["PASS"])
            if isinstance(farmer, list) and farmer and farmer[0] != "PASS":
                turn0 = {"farmer": list(farmer),
                         "hands": [list(h) for h in (act.get("hands") or [])],
                         "market": [list(m) for m in (act.get("market") or [])]}
                plain = {k: v for k, v in obs.items()}
                # Classify against the REAL post-step state, the same way play.py
                # does: apply the turn through the engine, then judge. Errors are
                # raised, not swallowed -- a silently swallowed AttributeError here
                # once produced a bank of zero rows while the launcher exited clean.
                eff = constraints.unit_effects(plain, cfg, seat, turn0)
                post = _post_state(plain, cfg, seat, turn0)
                advancing, why, detail = constraints.outcome(
                    plain, post, cfg, seat, turn0, eff)
                why = f"{why}: {detail}"
                if advancing:
                    adm = constraints.admissible(obs, cfg, seat)
                    cls = EB.situation_class(obs, cfg, seat, adm)
                    state_text = EB.structured_state(obs, cfg, seat)
                    plan = f"{' '.join(str(t) for t in farmer).lower()}: {why}"
                    bank.record(cls, EB.context_of(obs), state_text, turn0,
                                f"teacher:{teacher}", plan=plan[:120])
                    banked += 1
            actions = [None, None]
            actions[seat] = act
            actions[1 - seat] = other
            env.step(actions)
            step += 1
    return bank, banked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--teacher", default="starter")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--exclude-seeds", default="")
    a = ap.parse_args()
    ex = {int(s) for s in a.exclude_seeds.split(",") if s.strip()}
    bank, n = seed(a.bank, [int(s) for s in a.seeds.split(",")], a.teacher,
                   a.seat, a.max_steps, ex)
    classes = {}
    for r in bank.rows:
        classes[r["cls"]] = classes.get(r["cls"], 0) + 1
    print(f"banked {n} teacher demonstrations; {len(bank.rows)} rows, "
          f"{len(classes)} classes")
    for c, k in sorted(classes.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {k:4d}  {c}")


if __name__ == "__main__":
    main()
