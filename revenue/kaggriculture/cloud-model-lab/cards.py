"""Observation cards taken from the official Kaggriculture harness.

A "card" is one real, NONTERMINAL turn: the observation dict the engine hands an
agent, plus the configuration and the seat. Cards are captured by running the
official interpreter -- never hand-built -- so the engine stays the authority on
game state, and every legality answer downstream is checked against the engine
itself rather than against a re-implementation.

Engine pin: Kaggle/kaggle-environments 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c
  kaggriculture.py   sha256 bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e
  kaggriculture.json sha256 a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867
  utils.py           sha256 537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b
"""

import copy
import json
import os

ENGINE_PIN = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"


def make_env(seed, **overrides):
    """A fresh official kaggriculture env at `seed`."""
    from kaggle_environments import make
    cfg = {"seed": int(seed)}
    cfg.update(overrides)
    return make("kaggriculture", configuration=cfg, debug=False)


def _obs_of(step, seat):
    """The observation the engine handed `seat` at this step (seat-private included)."""
    return step[seat]["observation"]


def capture(seed, at_steps, seat=0, agent="starter", **overrides):
    """Run one real episode and return cards at the requested step indices.

    `at_steps` are engine step indices (turn numbers). A card is returned only if
    the seat's status is ACTIVE at that step, i.e. the position is NONTERMINAL and
    the engine is genuinely asking that seat for an action.
    """
    env = make_env(seed, **overrides)
    env.run([agent, agent])
    cards = []
    for idx in at_steps:
        if idx < 0 or idx >= len(env.steps):
            continue
        step = env.steps[idx]
        if step[seat]["status"] != "ACTIVE":
            continue          # terminal / inactive: not a decision point, skip
        obs = copy.deepcopy(_obs_of(step, seat))
        cards.append({
            "card_id": f"s{seed}-t{idx}-p{seat}",
            "seed": int(seed),
            "step": int(idx),
            "seat": int(seat),
            "agent": getattr(agent, "__name__", str(agent)),
            "observation": obs,
            "configuration": dict(env.configuration),
            "status": step[seat]["status"],
        })
    return cards


def save(cards, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(cards, fh, indent=1, sort_keys=True)
    return path


def load(path):
    with open(path) as fh:
        return json.load(fh)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--steps", required=True, help="comma-separated step indices")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cs = capture(a.seed, [int(s) for s in a.steps.split(",")], seat=a.seat)
    save(cs, a.out)
    for c in cs:
        o = c["observation"]
        print(f"{c['card_id']}  day={o['day']} hour={o['hour']} money={o['farms'][c['seat']]['money']} status={c['status']}")


def hiring_agent(obs, config=None):
    """Capture-only agent that hires early so multi-hand cards exist.

    This is NOT a policy under study: it exists so the card set contains real
    official-harness observations with several hands, since the starter agent never
    hires and a one-farmer card cannot exercise the joint PLANT budget.
    """
    day, hour = int(obs["day"]), int(obs["hour"])
    me = obs["farms"][int(obs["player"])]
    orders = []
    if hour < 3 and len(me["hands"]) < 3:
        orders = [["HIRE"]] * (3 - len(me["hands"]))
    return {"farmer": ["PASS"], "hands": [["PASS"]] * len(me["hands"]), "market": orders}


def capture_multi_hand(seed, at_steps, seat=0, **overrides):
    """Cards from an episode where the seat has hired hands."""
    return capture(seed, at_steps, seat=seat, agent=hiring_agent, **overrides)
