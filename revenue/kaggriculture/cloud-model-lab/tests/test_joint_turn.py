"""Joint-turn regression tests against full engine fixtures.

Every fixture is a real captured card from the official harness; every expected
value is produced by the pinned interpreter, not by a re-implementation here.
Run: python -B tests/test_joint_turn.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
import constraints
import codec
import prompt
from constraints import engine

FAILURES = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)
    return ok


def fixture(seed=7700001, steps=(150,), seat=0):
    return cards.capture(seed, list(steps), seat=seat)


def _empty_tile(card):
    tiles = card["observation"]["farms"][card["seat"]]["tiles"]
    found = []
    for y in range(len(tiles)):
        for x in range(len(tiles[0])):
            if tiles[y][x] is None:
                found.append((x, y))
    return found


def _add_hand(card, pos):
    """Add one hand at `pos` with its own inventory slot, as the engine shapes it."""
    farm = card["observation"]["farms"][card["seat"]]
    farm["hands"] = list(farm.get("hands", [])) + [list(pos)]
    invs = card["observation"]["private"].setdefault("inventories", [{}])
    while len(invs) < 1 + len(farm["hands"]):
        invs.append({})


# ---------------------------------------------------------------- 920-933
def test_atomic_plant_budget(card):
    """One seed, two planters blocks BOTH; two seeds, two planters plants both."""
    spots = _empty_tile(card)
    assert len(spots) >= 2, "need two empty tiles"
    (x0, y0), (x1, y1) = spots[0], spots[1]

    def build(seeds_n):
        c = copy.deepcopy(card)
        c["observation"]["farms"][c["seat"]]["farmer"] = [x0, y0]
        _add_hand(c, (x1, y1))
        c["observation"]["private"]["seeds"]["WHEAT"] = seeds_n
        return c

    action = {"farmer": ["PLANT", "WHEAT"], "hands": [["PLANT", "WHEAT"]], "market": []}

    one = build(1)
    r1 = constraints.evaluate_turn(one["observation"], one["configuration"], one["seat"], action)
    two = build(2)
    r2 = constraints.evaluate_turn(two["observation"], two["configuration"], two["seat"], action)

    check("plant_budget: 1 seed / 2 planters -> ALL PLANT dropped",
          r1["plant_blocked"] == ["WHEAT"] and r1["seeds_after"].get("WHEAT") == 1,
          f"blocked={r1['plant_blocked']} seeds_after={r1['seeds_after'].get('WHEAT')}")
    check("plant_budget: 2 seeds / 2 planters -> both plant",
          r2["plant_blocked"] == [] and r2["seeds_after"].get("WHEAT") == 0,
          f"blocked={r2['plant_blocked']} seeds_after={r2['seeds_after'].get('WHEAT')}")
    check("plant_budget: the two cards differ",
          r1["seeds_after"].get("WHEAT") != r2["seeds_after"].get("WHEAT"))
    check("plant_budget: marginal probe alone cannot express it",
          ["PLANT", "WHEAT"] in constraints.unit_admissible(
              one["observation"], one["configuration"], one["seat"], 0),
          "single-unit view still admits PLANT with 1 seed, which the joint turn drops")


# ---------------------------------------------------------------- 935-944
def test_unit_phase_before_market(card):
    c = copy.deepcopy(card)
    seat = c["seat"]
    # Stand the farmer on a shed-access tile so DROP resolves this turn.
    K = engine()
    board = int(c["configuration"]["boardSize"])
    c["observation"]["farms"][seat]["farmer"] = list(K._shed_access_tiles(board)[0])
    c["observation"]["private"]["inventories"][0] = {"CARROT": 4}
    c["observation"]["private"]["shed"] = {k: 0 for k in c["observation"]["private"]["shed"]}

    drop_sell = {"farmer": ["DROP"], "hands": [], "market": [["SELL", "CARROT", 4]]}
    pass_sell = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "CARROT", 4]]}
    r_ds = constraints.evaluate_turn(c["observation"], c["configuration"], seat, drop_sell)
    r_ps = constraints.evaluate_turn(c["observation"], c["configuration"], seat, pass_sell)
    check("ordering: DROP then SELL sells in the SAME turn",
          r_ds["money_delta"] > 0, f"delta={r_ds['money_delta']}")
    check("ordering: SELL without depositing sells nothing",
          r_ps["money_delta"] == 0, f"delta={r_ps['money_delta']}")

    adm = constraints.admissible(c["observation"], c["configuration"], seat)
    pre = {" ".join(m["order"]) for m in adm["market"]}
    post = {" ".join(m["order"]) for m in adm["market_after_full_deposit"]}
    check("ordering: pre-unit market set misses the same-turn sale",
          "SELL CARROT" not in pre and "SELL CARROT" in post,
          f"pre_has={'SELL CARROT' in pre} post_has={'SELL CARROT' in post}")

    # The reverse does NOT hold: a seed bought this turn cannot be planted this turn.
    c2 = copy.deepcopy(card)
    spots = _empty_tile(c2)
    c2["observation"]["farms"][c2["seat"]]["farmer"] = list(spots[0])
    c2["observation"]["private"]["seeds"]["WHEAT"] = 0
    r_bp = constraints.evaluate_turn(c2["observation"], c2["configuration"], c2["seat"],
                                     {"farmer": ["PLANT", "WHEAT"], "hands": [],
                                      "market": [["BUY_SEED", "WHEAT", 1]]})
    tiles = None
    check("ordering: BUY_SEED does NOT enable PLANT in the same turn",
          r_bp["plant_blocked"] == ["WHEAT"] and r_bp["seeds_after"].get("WHEAT") == 1,
          f"blocked={r_bp['plant_blocked']} seeds_after={r_bp['seeds_after'].get('WHEAT')}")


# ---------------------------------------------------------------- quantities
def test_quantity_domains(card):
    c = copy.deepcopy(card)
    seat = c["seat"]
    K = engine()
    board = int(c["configuration"]["boardSize"])
    c["observation"]["farms"][seat]["farmer"] = list(K._shed_access_tiles(board)[0])
    c["observation"]["private"]["shed"] = {k: 0 for k in c["observation"]["private"]["shed"]}
    c["observation"]["private"]["shed"]["WHEAT"] = 7
    c["observation"]["private"]["inventories"][0] = {}

    q = constraints.quantity_domains(c["observation"], c["configuration"], seat, 0)
    check("quantities: PICKUP domain is the shed stock, not 1",
          q["PICKUP"].get("WHEAT") == 7, f"max={q['PICKUP'].get('WHEAT')}")

    r5 = constraints.evaluate_turn(c["observation"], c["configuration"], seat,
                                   {"farmer": ["PICKUP", "WHEAT", 5], "hands": [], "market": []})
    check("quantities: PICKUP 5 moves five units",
          r5["carried_after"] == 5, f"carried_after={r5['carried_after']}")

    adm = constraints.admissible(c["observation"], c["configuration"], seat)
    sell = next((m for m in adm["market"] if m["order"] == ["SELL", "WHEAT"]), None)
    check("quantities: market max_n exceeds 1 and equals the stock",
          sell is not None and sell["max_n"] == 7,
          f"max_n={sell and sell['max_n']}")

    # Sequential market orders share cash and reprice per unit.
    c3 = copy.deepcopy(c)
    c3["observation"]["farms"][seat]["money"] = 45.0
    adm3 = constraints.admissible(c3["observation"], c3["configuration"], seat)
    seedbuy = next((m for m in adm3["market"] if m["order"] == ["BUY_SEED", "WHEAT"]), None)
    check("quantities: BUY_SEED max_n is bounded by shared cash",
          seedbuy is not None and seedbuy["max_n"] == 4,
          f"money=45 seed=10 -> max_n={seedbuy and seedbuy['max_n']}")
    r_two = constraints.evaluate_turn(c3["observation"], c3["configuration"], seat,
                                      {"farmer": ["PASS"], "hands": [],
                                       "market": [["BUY_SEED", "WHEAT", 3], ["BUY_SEED", "CARROT", 2]]})
    # money 45: three WHEAT seeds at 10 spend 30, leaving 15, which cannot afford a
    # 20-cost CARROT seed -- so the second order is starved by the first. That is the
    # shared balance, not two independent orders.
    check("quantities: a later order is starved by the cash an earlier one spent",
          r_two["money_delta"] == -30 and r_two["seeds_after"].get("CARROT", 0)
          == c3["observation"]["private"]["seeds"].get("CARROT", 0),
          f"delta={r_two['money_delta']} (3 WHEAT @10 = 30; 15 left < 20 for CARROT)")


# ---------------------------------------------------------------- 873-882 / 960-963
def test_end_of_day_and_terminal(card_h22, card_h23):
    for label, c in (("hour22", card_h22), ("hour23", card_h23)):
        cc = copy.deepcopy(c)
        seat = cc["seat"]
        cc["observation"]["private"]["inventories"][0] = {"CARROT": 3}
        r = constraints.evaluate_turn(cc["observation"], cc["configuration"], seat,
                                      {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]})
        eod = constraints.turn_rules(cc["observation"], cc["configuration"], seat)["end_of_day_this_turn"]
        if label == "hour22":
            check("end_of_day: hour22 is not an end-of-day turn", not eod)
            check("end_of_day: hour22 keeps the hired hand", r["hands_after"] == 1,
                  f"hands_after={r['hands_after']}")
            check("end_of_day: hour22 keeps carried goods on the unit",
                  r["carried_after"] == 3, f"carried_after={r['carried_after']}")
        else:
            check("end_of_day: hour23 IS an end-of-day turn", eod)
            check("end_of_day: hour23 removes the hired hand", r["hands_after"] == 0,
                  f"hands_after={r['hands_after']}")
            check("end_of_day: hour23 drops carried goods into the shed",
                  r["carried_after"] == 0 and r["shed_after"].get("CARROT", 0) == 3,
                  f"carried={r['carried_after']} shed CARROT={r['shed_after'].get('CARROT', 0)}")

    # Overflow at the end-of-day drop is DISCARDED, not held.
    cc = copy.deepcopy(card_h23)
    seat = cc["seat"]
    cap = int(cc["configuration"]["shedCapacity"])
    cc["observation"]["private"]["shed"] = {k: 0 for k in cc["observation"]["private"]["shed"]}
    cc["observation"]["private"]["shed"]["WHEAT"] = cap - 2
    cc["observation"]["private"]["inventories"][0] = {"CARROT": 5}
    r = constraints.evaluate_turn(cc["observation"], cc["configuration"], seat,
                                  {"farmer": ["PASS"], "hands": [], "market": []})
    check("end_of_day: overflow above shedCapacity is discarded",
          r["shed_after"].get("CARROT", 0) == 2 and r["carried_after"] == 0,
          f"shed CARROT={r['shed_after'].get('CARROT', 0)} of 5 carried, room was 2")

    # Terminal reward is cash: an unsold stock scores nothing, a final sale does.
    cc = copy.deepcopy(card_h23)
    seat = cc["seat"]
    cc["observation"]["private"]["shed"] = {k: 0 for k in cc["observation"]["private"]["shed"]}
    cc["observation"]["private"]["shed"]["CARROT"] = 6
    cc["observation"]["private"]["inventories"][0] = {}
    sold = constraints.evaluate_turn(cc["observation"], cc["configuration"], seat,
                                     {"farmer": ["PASS"], "hands": [], "market": [["SELL", "CARROT", 6]]})
    held = constraints.evaluate_turn(cc["observation"], cc["configuration"], seat,
                                     {"farmer": ["PASS"], "hands": [], "market": []})
    check("terminal: selling stock raises cash, holding it does not",
          sold["money_delta"] > 0 and held["money_delta"] == 0,
          f"sold={sold['money_delta']} held={held['money_delta']}")


# ---------------------------------------------------------------- no leakage
def test_no_leakage(card):
    import operators
    c = copy.deepcopy(card)
    seat = c["seat"]
    adm = constraints.admissible(c["observation"], c["configuration"], seat)
    text = prompt.build(c, adm, operators.BASELINE_INSTRUCTION)
    seed = str(c["seed"])
    check("leak: the episode seed is absent from the model input",
          seed not in text, f"seed={seed}")
    check("leak: 'seed' config key is not in the visible configuration",
          "seed" not in constraints.visible_config(c["configuration"]))
    check("leak: no opponent private state in the model input",
          "opponent_private" not in text and "private" not in text.lower().split())
    check("leak: the card wrapper's capture metadata is absent",
          str(c["step"]) not in text.split("STATE")[0] and c["agent"] not in text)


def test_absolute_clock(card):
    """A seat observation without `step` must still report the real clock."""
    c = copy.deepcopy(card)
    seat = c["seat"]
    obs, cfg = c["observation"], c["configuration"]
    tpd = int(cfg["turnsPerDay"])
    expected = int(obs["day"]) * tpd + int(obs["hour"])
    stripped = copy.deepcopy(obs)
    stripped.pop("step", None)
    check("clock: derived from day and hour when `step` is absent",
          constraints.absolute_step(stripped, cfg) == expected,
          f"got {constraints.absolute_step(stripped, cfg)} want {expected}")
    last = int(cfg["episodeSteps"]) - 2
    check("clock: horizon is unchanged by a missing `step`",
          constraints.horizon(stripped, cfg, seat)["remaining_decisions"]
          == constraints.horizon(obs, cfg, seat)["remaining_decisions"]
          == max(0, last - expected + 1),
          f"stripped={constraints.horizon(stripped, cfg, seat)['remaining_decisions']} "
          f"want {max(0, last - expected + 1)}")
    check("clock: end-of-day boundary survives a missing `step`",
          constraints.turn_rules(stripped, cfg, seat)["end_of_day_this_turn"]
          == ((expected + 1) % tpd == 0))
    # evaluate_turn must replay at the right day, not day 0.
    r = constraints.evaluate_turn(stripped, cfg, seat,
                                  {"farmer": ["PASS"], "hands": [], "market": []})
    r2 = constraints.evaluate_turn(obs, cfg, seat,
                                   {"farmer": ["PASS"], "hands": [], "market": []})
    check("clock: evaluate_turn replays identically with and without `step`",
          r["money_after"] == r2["money_after"] and r["shed_after"] == r2["shed_after"])


def main():
    base = fixture(steps=(150,))[0]
    h22 = fixture(steps=(6 * 24 + 22,))[0]
    h23 = fixture(steps=(6 * 24 + 23,))[0]
    print(f"fixtures: {base['card_id']} (day{base['observation']['day']} h{base['observation']['hour']}), "
          f"{h22['card_id']} h{h22['observation']['hour']}, {h23['card_id']} h{h23['observation']['hour']}\n")
    test_atomic_plant_budget(base)
    test_unit_phase_before_market(base)
    test_quantity_domains(base)
    test_end_of_day_and_terminal(h22, h23)
    test_no_leakage(base)
    seat1 = fixture(seed=9900017, steps=(200,), seat=1)[0]
    test_absolute_clock(seat1)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all joint-turn regressions pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
