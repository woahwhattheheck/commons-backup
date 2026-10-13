"""Bounded model-driven play inside a real episode.

The episode is real and official from step 0. A cheap warm-up agent plays the seat
up to `--from-step`, then E4B drives the seat for `--turns` real turns while the
opponent plays throughout. Every model turn records its prompt, raw generation,
timing and legality.

This is the model-to-game loop, not a simulation of one: the actions the model
authors are the actions the official interpreter executes.
"""

import argparse
import copy
import json
import os
import shutil
import tempfile
import time

import constraints

import cards as cards_mod
import driver as driver_mod
import exemplars
import runner as runner_mod


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


def play(model_path, seed, seat, from_step, turns, warmup_spec, opponent_spec,
         deriv_cards, eval_cards, max_market=3, out=None, examples="pairs",
         bank_path=None, render="verbose", freeze_bank=False, bank_out=None):
    warm, warm_label = _load_agent(warmup_spec)
    opp, opp_label = _load_agent(opponent_spec)
    surfaces, prov = exemplars.build(deriv_cards, eval_cards)

    if examples == "control":
        # No inference: the warm-up agent plays the same window, so the segment's
        # cash change is attributable to the model turns rather than to the window.
        env2 = cards_mod.make_env(seed)
        env2.reset(2)
        n = 0
        while not env2.done and n < turns + max(0, from_step):
            acts = []
            for i in range(2):
                o = env2.state[i].observation
                acts.append(_call(warm if i == seat else opp, o, env2.configuration))
            step_now = int(env2.state[seat].observation.get("step", 0) or 0)
            env2.step(acts)
            n += 1
            if step_now >= from_step + turns - 1:
                break
        money = float(env2.state[0].observation.farms[seat]["money"])
        opp_money = float(env2.state[0].observation.farms[1 - seat]["money"])
        r_cfg = {"control": True}
        return {"seed": seed, "seat": seat, "from_step": from_step,
                "model_turns": 0, "warmup": warm_label, "opponent": opp_label,
                "money": money, "opponent_money": opp_money,
                "margin": money - opp_money, "settings": r_cfg, "turns": [],
                "summary": {"control": True, "model_turns": 0}}
    env = cards_mod.make_env(seed)
    env.reset(2)
    r = runner_mod.Runner(model_path)
    bank, bank_info = None, None
    if examples == "bank":
        import exemplar_bank as EB
        # READ and WRITE are separate paths. Without bank_out the bank is read-only,
        # so a comparison arm cannot append rows a later arm would retrieve. A run
        # that should learn names its output file explicitly.
        # Stage the output OUTSIDE the working tree and publish it on completion, the
        # same reason run_seed.sh does: a file the repository tracks must not be
        # rewritten continuously by a long run, or every git operation races it.
        write_to = None
        if not freeze_bank and bank_out:
            staging_dir = tempfile.mkdtemp(prefix="bankout-")
            write_to = os.path.join(staging_dir, os.path.basename(bank_out))
        bank = EB.Bank(bank_path, write_path=write_to)
        bank_info = {"read": EB.describe(bank_path), "write": bank_out,
                     "staged_at": write_to}
    d = driver_mod.ModelDriver(r, surfaces, max_market=max_market,
                               examples=examples, bank=bank, render=render)
    model_turns = 0
    t_start = time.time()
    try:
        while not env.done and model_turns < turns:
            actions = []
            for i in range(2):
                obs = env.state[i].observation
                cfg = env.configuration
                if i == seat:
                    step = int(obs.get("step", 0))
                    if step >= from_step and model_turns < turns and examples != "control":
                        a = d.act(obs, dict(cfg), seat)
                        model_turns += 1
                        last = d.log[-1]
                        _hands = "+".join(" ".join(str(t) for t in h)
                                          for h in last["action"]["hands"]) or "-"
                        print(f"step{step:4d} day{last['day']:2d} h{last['hour']:2d} "
                              f"{last['action']['farmer']!s:22s} hands[{_hands}] "
                              f"mkt={last['action']['market']!s:28s} "
                              f"{'legal' if last['legal'] else 'ILLEGAL'} "
                              f"{last['timing_s']['model_inference']:5.2f}s"
                              + (f" REJECT[{last['rejected']}]" if last["rejected"] else ""), flush=True)
                        if last.get("examples_used"):
                            for e in last["examples_used"]:
                                print(f"        example[{e['provenance']}] {e['action'][:96]}", flush=True)
                        print(f"        plan: {(last.get('plan') or '')[:150]}", flush=True)
                    else:
                        a = _call(warm, obs, cfg)
                else:
                    a = _call(opp, obs, cfg)
                actions.append(a)
            # POST-INTERPRETER RECORD HOOK. A model turn is banked only after the real
            # step, classified by what the engine actually did, with before/after facts
            # and joint causal attribution. Provenance is `model`; a rejected outcome is
            # recorded in the trace with its reason and NOT banked.
            pre_obs = copy.deepcopy(dict(env.state[seat].observation))
            pre_cfg = dict(env.configuration)
            model_turn = d.log[-1] if (d.log and d.log[-1].get("_pending")) else None
            # Per-op attribution comes from the seat's own unit-phase replay, taken
            # BEFORE the step; the outcome itself is read from the state the real
            # interpreter produces, with the real opponent and the real market.
            pre_effects = None
            if model_turn is not None:
                try:
                    pre_effects = constraints.unit_effects(
                        pre_obs, pre_cfg, seat, model_turn["action"])
                except Exception:
                    pre_effects = None
            env.step(actions)
            if model_turn is not None:
                model_turn.pop("_pending", None)
                post_obs = copy.deepcopy(dict(env.state[seat].observation))
                post_obs["farms"] = copy.deepcopy(env.state[0].observation.farms)
                try:
                    ok, label, detail = constraints.outcome(
                        pre_obs, post_obs, pre_cfg, seat, model_turn["action"], pre_effects)
                except Exception as exc:
                    ok, label, detail = False, "error", str(exc)
                model_turn["outcome"] = {"bankable": ok, "label": label, "detail": detail}
                model_turn["unit_effects"] = pre_effects
                model_turn["before_after"] = {
                    "money_before": float(pre_obs["farms"][seat]["money"]),
                    "money_after": float(post_obs["farms"][seat]["money"]),
                    "shed_before": {k: v for k, v in pre_obs["private"].get("shed", {}).items() if v},
                    "shed_after": {k: v for k, v in post_obs["private"].get("shed", {}).items() if v},
                    "carried_before": sum(sum(i.values()) for i in pre_obs["private"].get("inventories", [])),
                    "carried_after": sum(sum(i.values()) for i in post_obs["private"].get("inventories", [])),
                }
                writable = d.bank is not None and getattr(d.bank, "write_path", None)
                print(f"        outcome: {label} -- {detail}"
                      + ("  [BANKED]" if ok and writable else
                         "  [bankable, bank read-only]" if ok else ""), flush=True)
                if ok and writable:
                    import exemplar_bank as EB
                    cls = model_turn.get("situation_class")
                    state_text = EB.structured_state(pre_obs, pre_cfg, seat)
                    d.bank.record(cls, EB.context_of(pre_obs), state_text,
                                  model_turn["action"], "model",
                                  plan=model_turn["action"].get("plan")
                                  or f"{label}: {detail}")
    finally:
        r.close()
        if bank is not None and getattr(bank, "write_path", None) and bank_out:
            # publish the staged bank into the repository once, at the end
            try:
                if os.path.exists(bank.write_path):
                    os.makedirs(os.path.dirname(bank_out) or ".", exist_ok=True)
                    shutil.copyfile(bank.write_path, bank_out)
                shutil.rmtree(os.path.dirname(bank.write_path), ignore_errors=True)
            except Exception as exc:
                print(f"[warn] could not publish staged bank: {exc}", flush=True)

    final = env.state
    money = float(final[seat].observation.farms[seat]["money"])
    opp_money = float(final[1 - seat].observation.farms[1 - seat]["money"])
    payload = {
        "seed": seed, "seat": seat, "from_step": from_step,
        "model_turns": model_turns, "warmup": warm_label, "opponent": opp_label,
        # the full specs, so a later continuation can re-instantiate these agents
        "warmup_spec": warmup_spec, "opponent_spec": opponent_spec,
        "wall_total_s": round(time.time() - t_start, 1),
        "money": money, "opponent_money": opp_money, "margin": money - opp_money,
        "settings": r.cfg, "provenance": prov, "bank": bank_info, "turns": d.log,
        # Render switches that change the prompt but live outside the payload.
        # Without them a later replay renders a DIFFERENT prompt than the model saw
        # and cannot prove its state reconstruction (compile_motifs.py).
        "render_env": {k: os.environ.get(k) for k in ("KAG_NO_STRUCTURE_BALANCE",)},
    }
    n = len(d.log)
    legal = sum(1 for x in d.log if x["legal"])
    rej = sum(1 for x in d.log if x["rejected"])
    infer = [x["timing_s"]["model_inference"] for x in d.log]
    nonpass = sum(1 for x in d.log if x["action"]["farmer"][0] != "PASS")
    mkt = sum(len(x["action"]["market"]) for x in d.log)
    payload["summary"] = {
        "model_turns": n, "legal": legal, "syntax_rejections": rej,
        "non_pass_farmer": nonpass, "market_orders_authored": mkt,
        "mean_inference_s": round(sum(infer) / n, 2) if n else None,
        "total_inference_s": round(sum(infer), 1),
    }
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w") as fh:
            json.dump(payload, fh, indent=1, default=str)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--from-step", type=int, default=0)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--warmup", default="starter")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--deriv-cards", required=True)
    ap.add_argument("--eval-cards", required=True)
    ap.add_argument("--max-market", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--examples", default="pairs",
                    choices=("pairs", "bank", "control"))
    ap.add_argument("--bank", default=None)
    ap.add_argument("--render", default="verbose", choices=("verbose", "slots"))
    ap.add_argument("--freeze-bank", action="store_true",
                    help="read the bank but never write to it (for comparison runs)")
    ap.add_argument("--bank-out", default=None,
                    help="file this run's banked model rows are written to; omit to "
                         "run read-only")
    a = ap.parse_args()
    p = play(a.model, a.seed, a.seat, a.from_step, a.turns, a.warmup, a.opponent,
             cards_mod.load(a.deriv_cards), cards_mod.load(a.eval_cards),
             max_market=a.max_market, out=a.out, examples=a.examples, bank_path=a.bank,
             render=a.render, freeze_bank=a.freeze_bank, bank_out=a.bank_out)
    print("\n=== summary ===")
    print(json.dumps(p["summary"], indent=1))
    print(f"money={p['money']:.0f} opponent={p['opponent_money']:.0f} margin={p['margin']:+.0f}")


if __name__ == "__main__":
    main()
