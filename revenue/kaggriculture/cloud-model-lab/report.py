"""Report a model run in the leader trace's own units.

`cloud-frontier-trace/OBSERVATIONS.md` measures episode 106392861 with two counters
that are directly comparable to this lane's outcome classifier:

  non-PASS unchanged unit effects   leader 0, opponent 123
  discarded units                   leader 0, opponent 30

Both are pure waste by the engine's own accounting: an emitted op the interpreter did
not act on, and stock destroyed at the end-of-day drop. This script reads a play run's
JSON and reports them alongside the outcome mix, so a model segment can be compared to
the frontier on the same axis instead of on legality counts.

It reads a finished run and computes nothing new from the engine, so it can be run
while another job holds the CPU.
"""

import argparse
import collections
import json


def report(path):
    d = json.load(open(path))
    turns = d.get("turns", [])
    non_pass_unchanged = 0
    emitted_non_pass = 0
    structures_razed = 0
    weeds_cleared = 0
    churn_turns = 0
    care_without_feed = 0
    outcomes = collections.Counter()
    rejects = 0
    market_orders = 0
    for t in turns:
        outcomes[(t.get("outcome") or {}).get("label", "unrecorded")] += 1
        if t.get("rejected"):
            rejects += 1
        act = t.get("action") or {}
        market_orders += len(act.get("market") or [])
        lbl = (t.get("outcome") or {}).get("label")
        if lbl == "churn":
            churn_turns += 1
        if lbl == "pending" and "not yet fed" in ((t.get("outcome") or {}).get("detail") or ""):
            care_without_feed += 1
        for e in t.get("unit_effects") or []:
            if e.get("effect") == "removed_structure":
                structures_razed += 1
            if e.get("effect") == "cleared_weed":
                weeds_cleared += 1
            if e["action"][0] == "PASS":
                continue
            emitted_non_pass += 1
            if not e["non_no_op"]:
                non_pass_unchanged += 1
    infer = [t["timing_s"]["model_inference"] for t in turns if t.get("timing_s")]
    n = len(turns) or 1
    return {
        "run": path,
        # margin first: the game is won on cash relative to the opponent
        "money": d.get("money"), "opponent_money": d.get("opponent_money"),
        "margin": d.get("margin"),
        "seed": d.get("seed"), "seat": d.get("seat"),
        "from_step": d.get("from_step"), "model_turns": len(turns),
        "render": (turns[0].get("render") if turns else None),
        "examples_mode": (turns[0].get("examples_mode") if turns else None),
        "non_pass_unchanged_effects": non_pass_unchanged,
        "emitted_non_pass_ops": emitted_non_pass,
        "waste_rate": (round(non_pass_unchanged / emitted_non_pass, 3)
                       if emitted_non_pass else None),
        "neutral_turns": outcomes.get("neutral", 0),
        "neutral_share": round(outcomes.get("neutral", 0) / n, 3),
        "structures_razed": structures_razed,
        "weeds_cleared": weeds_cleared,
        "churn_turns": churn_turns,
        "care_without_feed_turns": care_without_feed,
        "syntax_rejections": rejects,
        "market_orders_authored": market_orders,
        "outcomes": dict(outcomes),
        "mean_inference_s": (round(sum(infer) / len(infer), 2) if infer else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    rows = []
    for p in a.runs:
        try:
            rows.append(report(p))
        except Exception as exc:
            print(f"{p}: {type(exc).__name__}: {exc}")
    for r in rows:
        print(json.dumps(r, indent=1))
    if rows:
        print("\nleader trace 106392861: terminal cash 139,044 vs opponent 106,987 "
              "(margin +32,057); non-PASS unchanged effects 0 vs 123; discarded 0 vs 30. "
              "Margin is the objective; the waste counters are hygiene, not victory.")


if __name__ == "__main__":
    main()
