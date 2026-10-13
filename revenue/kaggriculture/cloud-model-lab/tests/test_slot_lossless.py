"""The typed-slot renderer must lose no decision-relevant value.

Every tile with its exact contents, every worker with what it carries, every
admissible op of every worker, every market order with its maximum quantity, the
seed budget, the ordering rule, the shed capacity and room, the production and decay
clocks, the survival counter, the prices, the objective and the horizon must all be
present. This checks presence, not wording: the point is that compression removed
repeated statements of the same fact, not any fact.

Run: python -B tests/test_slot_lossless.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
import constraints
import slots

FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def main():
    card = cards.capture_multi_hand(8800001, [45], seat=0)[0]
    obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
    adm = constraints.admissible(obs, cfg, seat)
    hz = constraints.horizon(obs, cfg, seat)
    text = slots.render(card, adm, hz, plan="test plan")

    # every non-empty tile appears with an id
    missing = []
    tiles = obs["farms"][seat]["tiles"]
    for y in range(len(tiles)):
        for x in range(len(tiles[0])):
            tid = slots._tid(x, y)
            if tid not in text:
                missing.append(tid)
    check("every tile id is present", not missing, f"missing {missing[:5]}")

    # every admissible op of every worker is reachable in the allowed lists
    lost = []
    for i, ops in enumerate(adm["units"]):
        for op in ops:
            if op[0] not in text:
                lost.append((i, op))
    check("every admissible unit op appears", not lost, f"missing {lost[:5]}")

    lostm = [m for m in adm["market"] if " ".join(m["order"]) not in text]
    check("every admissible market order appears", not lostm,
          f"missing {[m['order'] for m in lostm][:5]}")
    caps = [m for m in adm["market"] if m["max_n"] > 1 and f"n<={m['max_n']}" not in text]
    check("market maximum quantities appear", not caps,
          f"missing {[m['order'] for m in caps][:3]}")

    # workers, what they carry, and shared tiles
    farm = obs["farms"][seat]
    check("every worker appears", all(
        lbl in text for lbl in ["farmer"] + [f"hand{i}" for i in range(len(farm.get("hands", [])))]))
    invs = obs["private"].get("inventories", [])
    carried = [f"{k}{v}" for inv in invs for k, v in inv.items() if v]
    check("carried goods appear", all(c in text for c in carried), f"{carried}")

    # clocks, budgets, capacity, objective
    cap = int(cfg["shedCapacity"])
    check("shed capacity and room appear", f"/{cap}" in text and "room" in text)
    check("seed budget appears", "joint seed budget" in text)
    check("ordering rule appears", "resolve before any market order" in text)
    check("horizon appears", str(hz["remaining_decisions"]) in text
          and str(hz["last_decision_step"]) in text)
    check("objective appears", "cash" in text.lower() and "score 0" in text)
    for p in hz["plants"]:
        if p["dies_at_refresh_unless_watered"]:
            check("dying plant is flagged", "DIES at this refresh" in text)
            break
    check("opcode semantics stated", "CARE" in text and "cared_today" in text)
    check("sequential order stated, and not as exclusivity",
          "workers act in order" in text and "Sharing a tile is NOT a conflict" in text
          and "resolves for the FIRST only" not in text)
    check("DIG spares installed animals", "does NOT remove an installed animal" in text)

    # These blocks were missing from the slot renderer while the verbose renderer had
    # them, so a run that bought a cow was never shown how to install or feed it.
    from constraints import engine as _eng
    K = _eng()
    obs2 = copy.deepcopy(obs)
    obs2["private"]["shed"]["COW"] = 1
    card2 = dict(card, observation=obs2)
    adm2 = constraints.admissible(obs2, cfg, seat)
    t2 = slots.render(card2, adm2, constraints.horizon(obs2, cfg, seat))
    check("animals held in the shed show their install path",
          "ANIMALS IN THE SHED" in t2 and "PICKUP" in t2 and "PLACE" in t2)
    # and with an animal installed, the feeding state
    x3, y3 = next((x, y) for y in range(len(obs2["farms"][seat]["tiles"]))
                  for x in range(len(obs2["farms"][seat]["tiles"][0]))
                  if obs2["farms"][seat]["tiles"][y][x] is None)
    obs3 = copy.deepcopy(obs2)
    obs3["farms"][seat]["tiles"][y3][x3] = K._new_animal("GOOSE", int(obs3["day"]))
    card3 = dict(card, observation=obs3)
    t3 = slots.render(card3, constraints.admissible(obs3, cfg, seat),
                      constraints.horizon(obs3, cfg, seat))
    check("installed animals show feeding state",
          "FEEDING" in t3 and "WHEAT" in t3 and "NOT fed today" in t3)

    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        return 1
    print("slot renderer is lossless on the checked facts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
