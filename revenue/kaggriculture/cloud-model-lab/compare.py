"""E4B arm comparison on frozen observations: baseline / formal / pattern / codec.

Arms differ ONLY in the head of the prompt and, for `codec`, in whether decoding is
constrained. Cards, settings, sampler, max output tokens and engine instance are
identical across arms, and the arms are run card-major so no arm gets a warmer
engine than another.

Four results are kept apart and never merged into one number:
  syntax    did the emission decode against the turn grammar
  legality  will the engine act on every entry (violations / joint blocks)
  effect    how many emitted unit ops were non-no-ops in the engine
  economics realized cash delta for the turn

Timing is broken out by phase: state projection, constraint calculation, prompt
build, prefill (the engine's time-to-first-token), decode (wall minus prefill), and
decode/validation. Counters the engine does not populate stay None.
"""

import argparse
import json
import os
import time

import cards as cards_mod
import codec
import constraints
import exemplars
import operators
import prompt as prompt_mod
import runner as runner_mod

ARMS = ("baseline", "formal", "pattern", "codec")


def head_for(arm, surfaces):
    if arm == "baseline":
        return operators.BASELINE_INSTRUCTION
    if arm == "formal":
        return exemplars.composed_formal()
    return exemplars.composed_pattern(surfaces)


def score(card, action):
    """Engine effect + economics for a decoded turn. Separate from syntax/legality."""
    r = constraints.evaluate_turn(card["observation"], card["configuration"],
                                  card["seat"], action)
    return {
        "non_no_op_units": sum(1 for e in r["unit_effects"] if e["non_no_op"]),
        "emitted_units": len(r["unit_effects"]),
        "plant_blocked": r["plant_blocked"],
        "money_delta": r["money_delta"],
        "hands_after": r["hands_after"],
    }


def run(model_path, eval_cards, deriv_cards, arms=ARMS, max_output_tokens=192, out=None):
    surfaces, prov = exemplars.build(deriv_cards, eval_cards)
    r = runner_mod.Runner(model_path, max_output_tokens=max_output_tokens)
    records = []
    try:
        for card in eval_cards:
            # State projection + constraint calculation are timed once per card and
            # shared by every arm, since the arms see the same frozen observation.
            t0 = time.perf_counter()
            hz = constraints.horizon(card["observation"], card["configuration"], card["seat"])
            t_proj = time.perf_counter() - t0
            t0 = time.perf_counter()
            adm = constraints.admissible(card["observation"], card["configuration"], card["seat"])
            t_constr = time.perf_counter() - t0

            for arm in arms:
                t0 = time.perf_counter()
                text = prompt_mod.build(card, adm, head_for(arm, surfaces), hz=hz)
                t_prompt = time.perf_counter() - t0

                res = r.ask(text, constrained=(arm == "codec"))

                t0 = time.perf_counter()
                syntax_ok, reason, action, legal = True, None, None, None
                try:
                    action = codec.decode_turn(res["output"])
                except codec.Rejected as exc:
                    syntax_ok, reason = False, exc.reason
                if syntax_ok:
                    legal = codec.legality(action, adm)
                    eff = score(card, action)
                else:
                    eff = None
                t_validate = time.perf_counter() - t0

                ttft = res["benchmark"].get("time_to_first_token_in_second")
                rec = {
                    "card_id": card["card_id"], "arm": arm,
                    "prompt": text, "prompt_chars": len(text),
                    "prompt_tokens": r.tokenize_len(text),
                    "raw_output": res["output"], "error": res["error"],
                    "syntax_ok": syntax_ok, "syntax_reject_reason": reason,
                    "decoded_action": action,
                    "legality": legal, "effect": eff,
                    "timing_s": {
                        "state_projection": round(t_proj, 4),
                        "constraint_calculation": round(t_constr, 4),
                        "prompt_build": round(t_prompt, 4),
                        "model_wall": round(res["wall_s"], 3),
                        "prefill_ttft": (round(ttft, 3) if ttft is not None else None),
                        "decode": (round(res["wall_s"] - ttft, 3) if ttft is not None else None),
                        "decode_validation": round(t_validate, 4),
                    },
                    "engine_counters": res["benchmark"],
                    "constrained": res["constrained"],
                }
                records.append(rec)
                leg = "n/a" if legal is None else ("legal" if legal["legal"] else "illegal")
                print(f"{card['card_id']:20s} {arm:9s} syntax={'ok ' if syntax_ok else 'REJ'} "
                      f"{leg:8s} wall={res['wall_s']:6.2f}s "
                      f"ptok={rec['prompt_tokens']} "
                      + ("" if syntax_ok else f"[{reason}]"))
    finally:
        r.close()

    summary = {}
    for arm in arms:
        rs = [x for x in records if x["arm"] == arm]
        if not rs:
            continue
        syn = [x for x in rs if x["syntax_ok"]]
        leg = [x for x in syn if x["legality"] and x["legality"]["legal"]]
        walls = [x["timing_s"]["model_wall"] for x in rs]
        summary[arm] = {
            "n": len(rs),
            "syntax_ok": len(syn),
            "legal": len(leg),
            "mean_wall_s": round(sum(walls) / len(walls), 3),
            "median_wall_s": round(sorted(walls)[len(walls) // 2], 3),
            "mean_prompt_tokens": (
                round(sum(x["prompt_tokens"] for x in rs if x["prompt_tokens"]) / len(rs), 1)
                if all(x["prompt_tokens"] for x in rs) else None),
            "mean_non_no_op_units": (
                round(sum(x["effect"]["non_no_op_units"] for x in syn) / len(syn), 2)
                if syn else None),
            "mean_money_delta": (
                round(sum(x["effect"]["money_delta"] for x in syn) / len(syn), 1)
                if syn else None),
        }
    payload = {
        "model": {"path": model_path, "sha256": runner_mod.MODEL_SHA256,
                  "bytes": runner_mod.MODEL_BYTES},
        "settings": r.cfg, "engine_pin": cards_mod.ENGINE_PIN,
        "provenance": prov, "summary": summary, "records": records,
    }
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w") as fh:
            json.dump(payload, fh, indent=1, default=str)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--eval-cards", required=True)
    ap.add_argument("--deriv-cards", required=True)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--max-output-tokens", type=int, default=192)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    payload = run(a.model, cards_mod.load(a.eval_cards), cards_mod.load(a.deriv_cards),
                  arms=tuple(a.arms.split(",")), max_output_tokens=a.max_output_tokens,
                  out=a.out)
    print("\n=== summary ===")
    print(json.dumps(payload["summary"], indent=1))


if __name__ == "__main__":
    main()
