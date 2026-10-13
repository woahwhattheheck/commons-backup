"""Run E4B on the harvested route cards and score what the engine actually did.

Per card: the model authors the open slots, those ops are substituted into
Arlene's own turn for exactly those slots, and the merged turn is replayed through
the pinned interpreter on the real observation. Nothing else in the turn moves.

Three things are kept separate and never collapsed:
  syntax     did the constrained decode accept the emission
  engine     did the interpreter act on the chosen op, in context
  economics  what the op produced -- and, for the ops that cost something, what it
             cost, read from the real before/after tile
"""

import argparse
import copy
import json
import os
import time

import constraints
import native_motifs as NM
import runner as runner_mod
import slot_driver


# Effect categories the engine acted on. This is an ACTION counter, not revenue:
# `tile_state_change` covers a WATER and a shed withdrawal alike, and no category
# proves cash. Own cash and own-minus-rival margin over full games decide
# promotion; these counters only say the engine did something.
ACTED_KINDS = ("harvested", "installed_animal", "stored_in_shed", "cleared_weed",
               "tile_state_change")


def merged_action(card, chosen):
    a = copy.deepcopy(card["arlene_action"])
    units = [list(a["farmer"])] + [list(h) for h in a["hands"]]
    for u, op in chosen.items():
        if u < len(units):
            units[u] = list(op)
    return {"farmer": units[0], "hands": units[1:], "market": a["market"]}


def score(card, chosen):
    """What the engine did with the merged turn, against Arlene's own turn.

    The route's WORKING slots are compared by their exact outcome, not by effect
    category: `native_motifs.simulate` records each slot's final position, full
    carried inventory and the tile under it, because two PICKUPs keep the same
    effect string while the later one receives fewer units. Shed and cash deltas
    for the seat are compared too, since the market phase runs on the shed the
    unit phase leaves behind.
    """
    obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
    K = NM.engine()
    a_units = ([list(card["arlene_action"]["farmer"])]
               + [list(h) for h in card["arlene_action"]["hands"]])
    merged = merged_action(card, chosen)
    m_units = [list(merged["farmer"])] + [list(h) for h in merged["hands"]]
    base = NM.simulate(K, obs, cfg, seat, a_units)
    got = NM.simulate(K, obs, cfg, seat, m_units)
    rows = []
    for u, op in sorted(chosen.items()):
        if u >= len(got["slots"]):
            continue
        b = base["slots"][u] if u < len(base["slots"]) else None
        g = got["slots"][u]
        rows.append({
            "unit": u, "op": list(op),
            "baseline_op": b["op"] if b else None,
            "baseline_effect": b["kind"] if b else None,
            "effect": g["kind"], "acted": g["kind"] != "none",
            "tile_before": (b or {}).get("tile"), "tile_after": g["tile"],
            "carry_after": g["carry"], "pos_after": g["pos"],
        })
    disturbed = []
    for j in range(len(m_units)):
        if j in chosen or j >= len(base["slots"]) or j >= len(got["slots"]):
            continue
        b, g = base["slots"][j], got["slots"][j]
        if (b["kind"], b["pos"], b["carry"], b["tile"]) != \
                (g["kind"], g["pos"], g["carry"], g["tile"]):
            disturbed.append({"unit": j, "op": b["op"],
                              "baseline": {"effect": b["kind"], "pos": b["pos"],
                                           "carry": b["carry"]},
                              "merged": {"effect": g["kind"], "pos": g["pos"],
                                         "carry": g["carry"]}})
    shed_delta = {k: got["priv"]["shed"].get(k, 0) - base["priv"]["shed"].get(k, 0)
                  for k in set(got["priv"]["shed"]) | set(base["priv"]["shed"])}
    return {"slots": rows,
            "disturbed_route_slots": disturbed,
            "shed_delta_vs_route": {k: v for k, v in shed_delta.items() if v},
            "cash_delta_vs_route": float(got["farm"]["money"])
            - float(base["farm"]["money"]),
            "merged_action": merged}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--cards", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-slots", type=int, default=4)
    ap.add_argument("--out", default="results/slot-probe.json")
    a = ap.parse_args()

    payload = json.load(open(a.cards))
    cards = payload["cards"][:a.limit] if a.limit else payload["cards"]
    r = runner_mod.Runner(a.model)
    d = slot_driver.SlotDriver(r, max_slots=a.max_slots)
    rows, t0 = [], time.time()
    try:
        for k, card in enumerate(cards):
            row = d.act(card)
            if row is None:
                continue
            if row["slots"]:
                row["engine"] = score(card, row["slots"])
            else:
                row["engine"] = None
            rows.append(row)
            chosen = (" ".join(f"u{u}:{' '.join(str(t) for t in op)}"
                               for u, op in sorted(row["slots"].items()))
                      if row["slots"]
                      else f"REJECT[{row['rejected']}"
                           + (f" | engine: {row['error']}" if row.get("error") else "")
                           + "]")
            acted = (sum(1 for s in row["engine"]["slots"] if s["acted"])
                     if row["engine"] else 0)
            offered = " ".join(sorted({o["op"][0] for o in row["offered"]}))
            print(f"[{k + 1}/{len(cards)}] seed{card['seed']} step{card['step']:4d} "
                  f"d{card['day']}h{card['hour']:02d} offered[{offered}] -> {chosen}"
                  f"  acted {acted}/{len(row['slots'] or {})} "
                  f"{row['timing_s']['model_inference']:5.1f}s", flush=True)
            if row["engine"]:
                for s in row["engine"]["slots"]:
                    print(f"        u{s['unit']} {s['op']} -> {s['effect']}"
                          f"{'' if s['acted'] else '  (engine ignored)'}", flush=True)
                if row["engine"]["disturbed_route_slots"]:
                    for dsl in row["engine"]["disturbed_route_slots"]:
                        print(f"        DISTURBED route slot u{dsl['unit']} "
                              f"{dsl['op']}: {dsl['baseline']} -> {dsl['merged']}",
                              flush=True)
    finally:
        r.close()

    n = len(rows)
    dec = [x for x in rows if x["slots"]]
    acted = sum(1 for x in dec for s in x["engine"]["slots"] if s["acted"])
    total = sum(len(x["slots"]) for x in dec)
    acted_kind = sum(1 for x in dec for s in x["engine"]["slots"]
                     if s["acted"] and s["effect"] in ACTED_KINDS)
    passes = sum(1 for x in dec for op in x["slots"].values() if op[0] == "PASS")
    summary = {
        "cards": n, "decoded": len(dec), "syntax_rejections": n - len(dec),
        "slots_authored": total, "slots_passed": passes,
        "slots_engine_acted": acted,
        "slots_engine_acted_by_kind": acted_kind,
        "note": "action counters only; no revenue is claimed from them",
        "cards_disturbing_route": sum(1 for x in dec
                                      if x["engine"]["disturbed_route_slots"]),
        "wall_s": round(time.time() - t0, 1),
        "mean_inference_s": round(sum(x["timing_s"]["model_inference"]
                                      for x in rows) / max(1, n), 2),
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"summary": summary, "cards_meta": payload.get("meta"), "rows": rows},
              open(a.out, "w"), indent=1, default=str)
    print("\n=== summary ===")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
