"""Compile motifs from real model turns: deterministic export, not live selection.

What this does NOT do: it does not run the model, it does not read the bank digest,
and it does not treat an effect as a prompt. It replays the recorded episode with
the pinned engine, reconstructs the FULL state at each recorded turn, proves the
reconstruction is the state the model actually saw, then decomposes each turn into
per-worker components carrying their own grounded precondition.

Why the replay: `play.py` records the prompt, the action and the ordered effects,
but not the full observation. The full observation is what a grounded precondition
must be read from, so it is rebuilt from the pin -- seed, warm-up agent, opponent
agent, and the recorded action trace -- and then CHECKED against what was recorded:

  clock         day and hour
  cash/stock    money, shed and carried counts at the head of the turn
  constraints   the admissible farmer op list, byte-identical
  class         the recorded situation class
  effects       `constraints.unit_effects` recomputed, deep-equal to the recorded
                ordered effects, which is the strongest check available: the same
                full state produces the same per-op effect chain
  render        the prompt re-rendered from the reconstruction, line-for-line
                against the recorded prompt with only the retrieval block skipped

A row failing any check is left UNCOMPILED with its reason recorded. Nothing is
inferred from a state that could not be proved.
"""

import argparse
import copy
import hashlib
import json
import os
import time

import cards as cards_mod
import codec
import constraints
import native_motifs as NM

# An op is compiled only if the engine ACTED on it and the act was not one of the
# two churn behaviours. `moved` is excluded because navigation is the baseline
# policy's job and a motif for it would carry no local justification.
_SWITCH = "KAG_NO_STRUCTURE_BALANCE"

COMPILE_EFFECTS = ("installed_animal", "harvested", "stored_in_shed",
                   "cleared_weed", "tile_state_change")

# A motif may be PROPOSED only when its precondition is a local sufficient reason
# for its op: the op acts on an asset the seat already holds and completes
# something that asset needed (an unwatered plant wants WATER; an unfed animal
# wants FEED; an empty matching structure and a carried animal want PLACE).
#
# BUILD_COOP, BUILD_PASTURE and PLANT are compiled as evidence but held back from
# proposal: their precondition is `tile: EMPTY`, which is not a reason. The payoff
# depends on something that has not happened yet -- an animal arriving, a crop
# surviving to its window -- so a context-free "build on any empty tile" template
# is exactly the raze-and-rebuild churn the segment measurements charge against
# cash, not a component with a local justification.
LOCAL_PAYOFF_OPS = ("WATER", "FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER",
                    "PLACE", "PICKUP", "DROP")
HOLD_REASON = ("precondition is an empty tile, so the payoff is not local: it "
               "depends on a later fill this template cannot see")


def _load_agent(spec):
    if "::" not in spec:
        return spec, spec
    path, name = spec.split("::", 1)
    import importlib.util
    sp = importlib.util.spec_from_file_location(
        os.path.splitext(os.path.basename(path))[0] + "_ag", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return getattr(mod, name), f"{os.path.basename(path)}::{name}"


def _call(agent, obs, config):
    if isinstance(agent, str):
        from kaggle_environments.envs.kaggriculture import kaggriculture as K
        return {"starter": K.starter_agent, "random": K.random_agent,
                "pass": K.pass_agent}[agent](obs)
    try:
        return agent(obs, config)
    except TypeError:
        return agent(obs)


def _render_matches(fresh, recorded):
    """Every line of the freshly rendered state appears, in order, in the recorded
    prompt, and the lines it skips form at most two contiguous runs -- which is
    exactly the shape of the retrieval block plus its blank separator, the only
    thing the fresh render cannot reproduce.
    """
    F = fresh.split("\n")
    P = recorded.split("\n")
    i = 0
    runs, in_run = 0, False
    for line in P:
        if i < len(F) and line == F[i]:
            i += 1
            in_run = False
        else:
            if not in_run:
                runs += 1
                in_run = True
    info = {"matched": i, "of": len(F), "skip_runs": runs}
    if i < len(F):
        # the exact rendered fact that could not be found, so a mismatch names the
        # state difference instead of a count
        info["first_unmatched"] = F[i][:160]
    return i == len(F) and runs <= 2, info


def reconstruct(trace, deriv_cards=None, eval_cards=None):
    """Replay the episode and return one record per recorded model turn.

    Each record is either {"ok": True, "obs", "config", "effects", ...} or
    {"ok": False, "why": ...}. The replay always advances with the RECORDED action,
    so a verification failure never desynchronises the following turns.
    """
    import driver as driver_mod
    import exemplars
    import farmmap
    import prompt as prompt_mod
    import slots
    import static_prefix
    import exemplar_bank as EB

    seed, seat = int(trace["seed"]), int(trace["seat"])
    from_step = int(trace.get("from_step", 0))
    warm, _ = _load_agent(trace.get("warmup_spec") or trace.get("warmup", "starter"))
    opp, _ = _load_agent(trace.get("opponent_spec") or trace.get("opponent", "starter"))
    head = ""
    if any(t.get("examples_mode") == "pairs" for t in trace["turns"]):
        if deriv_cards is None or eval_cards is None:
            head = None            # cannot be reconstructed; those rows fail the check
        else:
            surfaces, _ = exemplars.build(deriv_cards, eval_cards)
            head = exemplars.composed_pattern(surfaces)

    env = cards_mod.make_env(seed)
    env.reset(2)
    turns = trace["turns"]
    out, k = [], 0
    static = None
    while not env.done and k < len(turns):
        actions = []
        rec, obs_k, cfg_k = None, None, None
        for i in range(2):
            obs = env.state[i].observation
            cfg = env.configuration
            if i == seat:
                step = int(obs.get("step", 0))
                if step >= from_step and k < len(turns):
                    rec = turns[k]
                    obs_k = copy.deepcopy(dict(obs))
                    cfg_k = dict(cfg)
                    actions.append(codec.engine_action(rec["action"]))
                else:
                    actions.append(_call(warm, obs, cfg))
            else:
                actions.append(_call(opp, obs, cfg))
        if rec is None:
            env.step(actions)
            continue

        why = []
        if (int(obs_k["day"]), int(obs_k["hour"])) != (int(rec["day"]), int(rec["hour"])):
            why.append(f"clock {obs_k['day']}/{obs_k['hour']} != {rec['day']}/{rec['hour']}")
        ba = rec.get("before_after") or {}
        money = float(obs_k["farms"][seat]["money"])
        if ba and abs(money - float(ba["money_before"])) > 1e-6:
            why.append(f"money {money} != {ba['money_before']}")
        carried = sum(sum(i.values()) for i in obs_k["private"].get("inventories", []))
        if ba and carried != int(ba["carried_before"]):
            why.append(f"carried {carried} != {ba['carried_before']}")
        shed = {a: b for a, b in obs_k["private"].get("shed", {}).items() if b}
        if ba and shed != ba["shed_before"]:
            why.append(f"shed {shed} != {ba['shed_before']}")

        adm = constraints.admissible(obs_k, cfg_k, seat)
        adm_ops = [" ".join(str(t) for t in o) for o in adm["units"][0]]
        if adm_ops != rec.get("admissible_farmer_ops"):
            why.append("admissible farmer ops differ")
        if rec.get("situation_class"):
            cls = EB.situation_class(obs_k, cfg_k, seat, adm)
            if cls != rec["situation_class"]:
                why.append(f"class {cls} != {rec['situation_class']}")

        eff = constraints.unit_effects(obs_k, cfg_k, seat, rec["action"])
        if rec.get("unit_effects") is None:
            why.append("trace carries no recorded effect chain to check against")
        else:
            if json.loads(json.dumps(eff, default=str)) != \
                    json.loads(json.dumps(rec["unit_effects"], default=str)):
                why.append("recomputed unit_effects differ from the recorded chain")

        # the rendered state the model was actually shown
        rcheck = None
        if head is None and rec.get("examples_mode") == "pairs":
            why.append("render not reconstructible (operator head unavailable)")
        else:
            hz = constraints.horizon(obs_k, cfg_k, seat)
            plan_in = turns[k - 1]["plan"] if k else None
            card = {"observation": obs_k, "configuration": cfg_k, "seat": seat}
            # Render switches live in the environment, not in the observation, so a
            # replay must restore the one the run used or it renders a prompt the
            # model never saw. Recorded from `render_env` when the trace carries it.
            for var, val in (trace.get("render_env") or {}).items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val
            if rec.get("render") == "slots":
                fresh = slots.render(card, adm, hz, plan=plan_in,
                                     bank_block="", head=head or None)
            else:
                if static is None:
                    static = static_prefix.build(cfg_k)
                fresh = prompt_mod.build(card, adm, head or "", hz=hz, plan=plan_in,
                                         static=static,
                                         farm_map=farmmap.build(obs_k, cfg_k, seat),
                                         bank_block="")
            ok_r, rcheck = _render_matches(fresh, rec["prompt"])
            if not ok_r and not (trace.get("render_env") or {}):
                # An older trace predates `render_env`. Resolve the switch by
                # rendering the other way and requiring the SAME exact match --
                # this recovers which setting the run used, it does not relax the
                # check.
                flip = "1" if not os.environ.get(_SWITCH) else None
                if flip is None:
                    os.environ.pop(_SWITCH, None)
                else:
                    os.environ[_SWITCH] = flip
                if rec.get("render") == "slots":
                    fresh = slots.render(card, adm, hz, plan=plan_in,
                                         bank_block="", head=head or None)
                else:
                    fresh = prompt_mod.build(card, adm, head or "", hz=hz,
                                             plan=plan_in, static=static,
                                             farm_map=farmmap.build(obs_k, cfg_k, seat),
                                             bank_block="")
                ok_r, rcheck2 = _render_matches(fresh, rec["prompt"])
                if ok_r:
                    rcheck = dict(rcheck2, resolved_switch={_SWITCH: flip})
            if not ok_r:
                why.append(f"rendered state mismatch {rcheck}")

        out.append({"ok": not why, "why": why, "index": k,
                    "step": int(obs_k.get("step", 0)),
                    "obs": obs_k if not why else None, "config": cfg_k,
                    "seat": seat, "effects": eff, "record": rec,
                    "render_check": rcheck})
        env.step(actions)
        k += 1
    return out


def components(rec, obs, config, seat, effects, source):
    """Decompose one verified turn into role-bound components.

    Each component is ONE worker's op with the grounded facts that op depended on,
    read from the full state at the head of the turn. The other workers' ops, the
    market and the plan are deliberately not part of it: that is what makes three
    WATERs by three workers one reusable motif instead of one eight-part turn.
    """
    farm, priv = obs["farms"][seat], obs["private"]
    outs = []
    for e in effects:
        i = e["unit"]
        op = list(e["action"])
        if op[0] == "PASS" or op[0] in NM.MOVES:
            continue
        if not e["non_no_op"] or e["effect"] not in COMPILE_EFFECTS:
            continue
        facts = NM.unit_facts(farm, priv, config, i)
        when = NM.precondition(op, facts)
        if when is None:
            continue
        # a motif whose own precondition does not hold on the state it came from is
        # a mis-extraction, not evidence
        if not NM.holds(when, op, facts):
            continue
        outs.append({
            "op": op, "when": when, "effect": e["effect"],
            "role": "worker", "observed_role": "farmer" if i == 0 else "hand",
            "proposable": op[0] in LOCAL_PAYOFF_OPS,
            "source": dict(source, step=rec_step(rec), unit=i),
        })
    return outs


def rec_step(rec):
    return int(rec.get("day", 0)) * 24 + int(rec.get("hour", 0))


def _sig(op, when):
    return json.dumps([op, sorted(when.items())], sort_keys=True, default=str)


def compile_traces(paths, provenance="model", deriv_cards=None, eval_cards=None,
                   min_support=1):
    table, skipped, checked = {}, [], []
    kind_disagreements = 0
    for p in paths:
        trace = json.load(open(p))
        recs = reconstruct(trace, deriv_cards, eval_cards)
        for r in recs:
            if not r["ok"]:
                skipped.append({"trace": os.path.basename(p), "index": r["index"],
                                "why": r["why"]})
                continue
            # cross-check: the native classifier must agree with the lab's recorded
            # effect chain, or a proposal would be judged by a different rule than
            # the evidence was
            sim = NM.simulate(NM.engine(), r["obs"], r["config"], r["seat"],
                              [r["record"]["action"]["farmer"]]
                              + list(r["record"]["action"]["hands"]))
            if sim["kinds"] != [e["effect"] for e in r["effects"]]:
                kind_disagreements += 1
                skipped.append({"trace": os.path.basename(p), "index": r["index"],
                                "why": ["native effect classifier disagrees with the "
                                        "recorded chain"]})
                continue
            checked.append(r["index"])
            src = {"trace": os.path.basename(p), "seed": trace["seed"],
                   "provenance": provenance}
            for c in components(r["record"], r["obs"], r["config"], r["seat"],
                                r["effects"], src):
                key = _sig(c["op"], c["when"])
                m = table.setdefault(key, {
                    "op": c["op"], "when": c["when"], "effect": c["effect"],
                    "role": "worker", "observed_roles": set(),
                    "proposable": c["proposable"],
                    "hold_reason": None if c["proposable"] else HOLD_REASON,
                    "support": {"model": 0, "teacher": 0, "total": 0},
                    "provenance": [], "sources": []})
                m["observed_roles"].add(c["observed_role"])
                m["support"][provenance] = m["support"].get(provenance, 0) + 1
                m["support"]["total"] += 1
                if provenance not in m["provenance"]:
                    m["provenance"].append(provenance)
                if len(m["sources"]) < 8:
                    m["sources"].append(c["source"])
    motifs = []
    for i, (key, m) in enumerate(sorted(table.items())):
        if m["support"]["total"] < min_support:
            continue
        m = dict(m)
        m["observed_roles"] = sorted(m["observed_roles"])
        m["id"] = "m%03d" % i
        motifs.append(m)
    motifs.sort(key=lambda m: (-m["support"]["total"], m["id"]))
    return {"motifs": motifs,
            "meta": {"compiled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "engine_pin": cards_mod.ENGINE_PIN,
                     "traces": [os.path.basename(p) for p in paths],
                     "verified_turns": len(checked),
                     "uncompiled_turns": len(skipped),
                     "effect_classifier_disagreements": kind_disagreements,
                     "min_support": min_support,
                     "proposable": sum(1 for m in motifs if m["proposable"]),
                     "held": sum(1 for m in motifs if not m["proposable"]),
                     "provenance": provenance},
            "uncompiled": skipped}


def write_table(table, json_path, py_path):
    with open(json_path, "w") as fh:
        json.dump(table, fh, indent=1, default=str)
    lit = {"motifs": table["motifs"], "meta": table["meta"]}
    body = json.dumps(lit, indent=1, default=str)
    with open(py_path, "w") as fh:
        fh.write('"""Compiled motif table. Generated by compile_motifs.py -- do not '
                 'hand-edit.\n\nA Python literal so the hosted agent reads no disk '
                 'and runs no model at turn time.\n"""\n\nTABLE = ')
        fh.write(body.replace("true", "True").replace("false", "False")
                 .replace("null", "None"))
        fh.write("\n")
    return hashlib.sha256(open(json_path, "rb").read()).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--provenance", default="model", choices=("model", "teacher"))
    ap.add_argument("--deriv-cards", default=None)
    ap.add_argument("--eval-cards", default=None)
    ap.add_argument("--min-support", type=int, default=1)
    ap.add_argument("--out-json", default="results/motifs.json")
    ap.add_argument("--out-py", default="motifs_table.py")
    a = ap.parse_args()
    dc = cards_mod.load(a.deriv_cards) if a.deriv_cards else None
    ec = cards_mod.load(a.eval_cards) if a.eval_cards else None
    t = compile_traces(a.traces, a.provenance, dc, ec, a.min_support)
    os.makedirs(os.path.dirname(a.out_json) or ".", exist_ok=True)
    h = write_table(t, a.out_json, a.out_py)
    print(json.dumps(t["meta"], indent=1))
    print(f"motifs={len(t['motifs'])} sha={h}")
    for m in t["motifs"]:
        print(f"  {'  ' if m['proposable'] else 'HELD'} {m['id']} "
              f"{m['op']!s:26s} {m['effect']:18s} "
              f"support={m['support']['total']} roles={','.join(m['observed_roles'])} "
              f"when={ {k: v for k, v in m['when'].items()} }")
    if t["uncompiled"]:
        print(f"\nuncompiled rows: {len(t['uncompiled'])}")
        for s in t["uncompiled"][:12]:
            print(f"  {s['trace']}#{s['index']}: {'; '.join(s['why'])}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- slot-probe lane

def compile_slot_probe(probe_path, cards_path, min_support=1):
    """Compile motifs from what E4B authored into Arlene's OPEN slots.

    A row is compiled only when the constrained decode accepted it, the op is not
    PASS, the pinned interpreter ACTED on it in context, the effect is not one of
    the forbidden ones, and the merged turn left every working route slot's exact
    outcome unchanged. The precondition is read from the ordered PREFIX state that
    slot actually acted on, so a later slot's facts include the earlier ones.

    Provenance is `model` and nothing else is mixed in. Hand-authored candidates
    live in `engine_derived_controls()` and carry their own provenance.
    """
    probe = json.load(open(probe_path))
    cards = {(c["seed"], c["seat"], c["step"]): c
             for c in json.load(open(cards_path))["cards"]}
    K = NM.engine()
    table, skipped, used = {}, [], 0
    for row in probe["rows"]:
        key = (row["seed"], row["seat"], row["step"])
        card = cards.get(key)
        if card is None:
            skipped.append({"row": key, "why": "no matching card"})
            continue
        if not row.get("slots"):
            skipped.append({"row": key, "why": f"rejected: {row.get('rejected')}"})
            continue
        eng = row.get("engine") or {}
        if eng.get("disturbed_route_slots"):
            skipped.append({"row": key, "why": "merged turn disturbed a route slot"})
            continue
        obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
        merged = eng.get("merged_action")
        units = [list(merged["farmer"])] + [list(h) for h in merged["hands"]]
        for s in eng.get("slots", []):
            op = list(s["op"])
            if op[0] == "PASS":
                continue
            if not s["acted"] or s["effect"] in NM.FORBIDDEN_EFFECTS:
                skipped.append({"row": key, "unit": s["unit"],
                                "why": f"effect {s['effect']}"})
                continue
            i = s["unit"]
            pre = NM.simulate(K, obs, cfg, seat, units, upto=i)
            farm = pre["farm"] if i else obs["farms"][seat]
            priv = pre["priv"] if i else obs["private"]
            facts = NM.unit_facts(farm, priv, cfg, i)
            when = NM.precondition(op, facts)
            if when is None or not NM.holds(when, op, facts):
                skipped.append({"row": key, "unit": i,
                                "why": "precondition does not hold on its own state"})
                continue
            used += 1
            sig = _sig(op, when)
            m = table.setdefault(sig, {
                "op": op, "when": when, "effect": s["effect"], "role": "worker",
                "observed_roles": set(),
                "proposable": op[0] in LOCAL_PAYOFF_OPS,
                "hold_reason": None if op[0] in LOCAL_PAYOFF_OPS else HOLD_REASON,
                "support": {"model": 0, "teacher": 0, "total": 0},
                "provenance": ["model"], "authored": "model", "sources": []})
            m["observed_roles"].add("farmer" if i == 0 else "hand")
            m["support"]["model"] += 1
            m["support"]["total"] += 1
            if len(m["sources"]) < 8:
                m["sources"].append({"seed": row["seed"], "seat": seat,
                                     "step": row["step"], "unit": i,
                                     "plan": row.get("plan"),
                                     "provenance": "model"})
    motifs = []
    for i, (sig, m) in enumerate(sorted(table.items())):
        if m["support"]["total"] < min_support:
            continue
        m = dict(m)
        m["observed_roles"] = sorted(m["observed_roles"])
        m["id"] = "s%03d" % i
        motifs.append(m)
    motifs.sort(key=lambda m: (-m["support"]["total"], m["id"]))
    return {"motifs": motifs,
            "meta": {"compiled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "engine_pin": cards_mod.ENGINE_PIN,
                     "lane": "slot-probe over the intact Arlene baseline",
                     "probe": os.path.basename(probe_path),
                     "cards": os.path.basename(cards_path),
                     "slot_decisions_compiled": used,
                     "rows": len(probe["rows"]),
                     "authored": "model",
                     "provenance": "model"},
            "uncompiled": skipped}


def engine_derived_controls():
    """HAND-AUTHORED candidate controls. NOT model output; never label them so.

    Each is written directly from a pinned engine rule, to give the model-produced
    table something to be discriminated against. They are a control arm, not a
    recommendation, and they carry their own provenance so no measurement can
    confuse the two lanes.
    """
    def m(idx, op, when, effect, why):
        return {"id": "c%03d" % idx, "op": list(op), "when": dict(when),
                "effect": effect, "role": "worker", "observed_roles": ["worker"],
                "proposable": True, "hold_reason": None,
                "support": {"model": 0, "teacher": 0, "hand": 1, "total": 1},
                "provenance": ["engine-derived-control"], "authored": "hand",
                "rule": why, "sources": []}
    return {"motifs": [
        m(0, ["CARE"], {"tile": "ANIMAL", "cared_today": False, "fed_today": True},
          "tile_state_change",
          "the daily refresh pays care only on an animal already fed today "
          "(kaggriculture.py 829-830); this is the fed half of that pair"),
        m(1, ["HARVEST"], {"tile": "ANIMAL", "yield_units>=1": True}, "harvested",
          "HARVEST on an animal takes its held units and leaves the animal in "
          "place (469-472), so it forfeits nothing"),
        m(2, ["COLLECT_FERTILIZER"], {"tile": "ANIMAL", "fertilizer_available": True},
          "tile_state_change",
          "fertilizer standing available on an animal is collected outright"),
        m(3, ["FEED"], {"tile": "ANIMAL", "fed_today": False, "carry.WHEAT>=1": True},
          "tile_state_change",
          "FEED sets fed_today and consumes one carried WHEAT (508-513); it is the "
          "precondition the refresh pays production and care against"),
        m(4, ["WATER"], {"tile": "PLANT", "watered_today": False, "unwatered_run": 1},
          "tile_state_change",
          "an unwatered plant loses growth at the refresh; WATER costs nothing "
          "carried"),
    ], "meta": {"lane": "hand-authored engine-derived controls",
                "authored": "hand", "provenance": "engine-derived-control",
                "engine_pin": cards_mod.ENGINE_PIN,
                "note": "these are NOT model output and must not be reported as "
                        "model-produced"}}
