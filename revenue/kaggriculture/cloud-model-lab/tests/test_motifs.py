"""Guards for the motif proposal layer, and the held-out state-shape checks.

Every case here is built with the engine's own constructors on real captured cards
and judged by the pinned transition, not by a re-implementation. The five named
sequencing cases come first; then one case per behavioural guard the layer claims.

Run: python -B tests/test_motifs.py
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
import constraints
import native_motifs as NM
from constraints import engine

FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def _card():
    c = cards.capture(3131017, [3], seat=0)[0]
    return c


def _place(card, x, y, tile):
    c = copy.deepcopy(card)
    farm = c["observation"]["farms"][c["seat"]]
    farm["tiles"][y][x] = tile
    return c


def _workers(card, positions, carries=None):
    c = copy.deepcopy(card)
    farm = c["observation"]["farms"][c["seat"]]
    farm["farmer"] = list(positions[0])
    farm["hands"] = [list(p) for p in positions[1:]]
    invs = [dict(x) for x in (carries or [{} for _ in positions])]
    c["observation"]["private"]["inventories"] = invs
    return c


def _sim(c, units, K=None):
    return NM.simulate(K or NM.engine(), c["observation"], c["configuration"],
                       c["seat"], units)


def _motif(op, when, effect="tile_state_change", support=3, proposable=True):
    return {"id": "t_" + "_".join(str(t) for t in op), "op": list(op), "when": when,
            "effect": effect, "role": "worker", "observed_roles": ["hand"],
            "proposable": proposable, "hold_reason": None,
            "support": {"model": support, "teacher": 0, "total": support},
            "provenance": ["model"], "sources": []}


# ------------------------------------------------------------- sequencing cases

def case_feed_and_care(card):
    K = engine()
    c = _place(card, 4, 4, K._new_animal("GOOSE", int(card["observation"]["day"])))
    c = _workers(c, [(4, 4), (4, 4)], [{"WHEAT": 2}, {}])
    r = _sim(c, [["FEED"], ["CARE"]])
    check("FEED + CARE on one animal: both act",
          all(k != "none" for k in r["kinds"]), str(r["kinds"]))
    t = r["farm"]["tiles"][4][4]
    check("FEED + CARE: both daily flags set",
          t.get("fed_today") and t.get("cared_today"),
          f"fed={t.get('fed_today')} cared={t.get('cared_today')}")
    d = _sim(c, [["CARE"], ["CARE"]])
    check("duplicate CARE: the second does nothing",
          d["kinds"][0] != "none" and d["kinds"][1] == "none", str(d["kinds"]))


def case_duplicate_move(card):
    c = _workers(card, [(4, 4), (3, 4)])
    r = _sim(c, [["NORTH"], ["NORTH"]])
    check("duplicate NORTH by two workers: both move",
          r["kinds"] == ["moved", "moved"], str(r["kinds"]))
    check("duplicate NORTH: they end on different tiles",
          r["slots"][0]["pos"] != r["slots"][1]["pos"],
          f"{r['slots'][0]['pos']} {r['slots'][1]['pos']}")


def case_build_then_place(card):
    c = _workers(card, [(4, 4), (4, 4)], [{}, {"COW": 1}])
    c = _place(c, 4, 4, None)
    fwd = _sim(c, [["BUILD_PASTURE"], ["PLACE", "COW", 1]])
    check("BUILD_PASTURE then PLACE COW: the animal is installed",
          fwd["kinds"][1] == "installed_animal", str(fwd["kinds"]))
    rev = _sim(c, [["PLACE", "COW", 1], ["BUILD_PASTURE"]])
    check("reversed order differs: PLACE first does not install",
          rev["kinds"][0] != "installed_animal" and fwd["kinds"] != rev["kinds"],
          f"fwd={fwd['kinds']} rev={rev['kinds']}")


def case_dig_destroys_harvest_target(card):
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    plant = K._new_plant("WHEAT", day, tpd)
    plant["yield_units"] = 3
    c = _place(card, 4, 4, plant)
    c = _workers(c, [(4, 4), (4, 4)])
    r = _sim(c, [["DIG"], ["HARVEST"]])
    check("DIG destroys a live HARVEST target",
          r["kinds"][0] == "destroyed_plant" and r["kinds"][1] == "none",
          str(r["kinds"]))
    check("DIG has no motif precondition at all",
          NM.precondition(["DIG"], NM.unit_facts(
              c["observation"]["farms"][c["seat"]], c["observation"]["private"],
              c["configuration"], 0)) is None)


def case_three_plants_two_seeds(card):
    c = _workers(card, [(0, 0), (1, 0), (2, 0)])
    for x in range(3):
        c = _place(c, x, 0, None)
    c["observation"]["private"]["seeds"] = {"WHEAT": 2}
    units = [["PLANT", "WHEAT"]] * 3
    check("three PLANT against two seeds: the joint budget drops every one",
          NM.seed_blocked(units, {"WHEAT": 2}) == ["WHEAT"])
    r = _sim(c, units)
    check("three PLANT against two seeds: nothing is planted",
          all(k == "none" for k in r["kinds"]), str(r["kinds"]))
    check("two PLANT against two seeds: both plant",
          all(k != "none" for k in _sim(c, units[:2] + [["PASS"]])["kinds"][:2]))


# ------------------------------------------------------------ behavioural guards

def case_cache_never_admits(card):
    """Same coarse key, different quantities and flags -- `holds` must still reject."""
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    p_dry = K._new_plant("WHEAT", day, tpd)
    p_dry["watered_today"] = False
    p_dry["consecutive_unwatered"] = 0
    c = _place(card, 4, 4, p_dry)
    c = _workers(c, [(4, 4)], [{"WHEAT": 2}])
    farm, priv = c["observation"]["farms"][c["seat"]], c["observation"]["private"]
    priv["shed"] = {"WHEAT": 2}
    f0 = NM.unit_facts(farm, priv, c["configuration"], 0)
    water = _motif(["WATER"], NM.precondition(["WATER"], f0))
    pick = _motif(["PICKUP", "WHEAT", 2],
                  NM.precondition(["PICKUP", "WHEAT", 2], f0))
    prop = NM.Proposer({"motifs": [water, pick]})
    got = [m["id"] for m in prop._candidates(f0)]
    check("cache: both motifs match the state they came from", len(got) == 2, str(got))

    # SAME coarse key: same tile kind, same item NAMES in carry/shed/seeds.
    c2 = copy.deepcopy(c)
    c2["observation"]["private"]["shed"] = {"WHEAT": 1}       # quantity below n
    p2 = c2["observation"]["farms"][c2["seat"]]["tiles"][4][4]
    p2["consecutive_unwatered"] = 2                           # flag differs
    f1 = NM.unit_facts(c2["observation"]["farms"][c2["seat"]],
                       c2["observation"]["private"], c2["configuration"], 0)
    check("cache: the coarse key is genuinely the same",
          NM.coarse_key(f0) == NM.coarse_key(f1),
          f"{NM.coarse_key(f0)} vs {NM.coarse_key(f1)}")
    got2 = [m["id"] for m in prop._candidates(f1)]
    check("cache hit does not admit PICKUP once shed stock fell below n",
          pick["id"] not in got2, str(got2))
    check("cache hit does not admit WATER once unwatered_run differs",
          water["id"] not in got2, str(got2))


def case_prefix_facts(card):
    """A later slot's facts come from the prefix, so PLACE sees an earlier BUILD."""
    c = _place(card, 4, 4, None)
    c = _workers(c, [(4, 4), (4, 4)], [{}, {"COW": 1}])
    obs, cfg, seat = c["observation"], c["configuration"], c["seat"]
    K = NM.engine()
    head = NM.unit_facts(obs["farms"][seat], obs["private"], cfg, 1)
    check("at the head of the turn hand0 stands on an empty tile",
          head["tile"] == "EMPTY", head["tile"])
    pre = NM.simulate(K, obs, cfg, seat, [["BUILD_PASTURE"], ["PLACE", "COW", 1]], upto=1)
    after = NM.unit_facts(pre["farm"], pre["priv"], cfg, 1)
    check("after the prefix it stands on the PASTURE the farmer just built",
          after["tile"] == "PASTURE" and after["structure"] == "PASTURE",
          f"{after['tile']}/{after.get('structure')}")
    when = NM.precondition(["PLACE", "COW", 1], after)
    check("the PLACE precondition holds only on the prefix state",
          NM.holds(when, ["PLACE", "COW", 1], after)
          and not NM.holds(when, ["PLACE", "COW", 1], head))


def case_exact_worker_preservation(card):
    """Two PICKUPs stay `tile_state_change` while the second receives fewer units."""
    c = _workers(card, [(4, 4), (4, 4)], [{}, {}])
    c["observation"]["private"]["shed"] = {"WHEAT": 3}
    base = _sim(c, [["PASS"], ["PICKUP", "WHEAT", 3]])
    trial = _sim(c, [["PICKUP", "WHEAT", 2], ["PICKUP", "WHEAT", 3]])
    check("effect category alone cannot tell the two apart",
          base["kinds"][1] == trial["kinds"][1], str((base["kinds"], trial["kinds"])))
    check("the exact carry does: hand0 receives fewer units",
          base["slots"][1]["carry"] != trial["slots"][1]["carry"],
          f"{base['slots'][1]['carry']} vs {trial['slots'][1]['carry']}")
    f = NM.unit_facts(c["observation"]["farms"][c["seat"]],
                      c["observation"]["private"], c["configuration"], 0)
    m = _motif(["PICKUP", "WHEAT", 2], NM.precondition(["PICKUP", "WHEAT", 2], f))
    contract = dict(NM.derived_contract(c["observation"], c["configuration"], c["seat"],
                                        {"farmer": ["PASS"],
                                         "hands": [["PICKUP", "WHEAT", 3]],
                                         "market": []}),
                    value=lambda *a: 1.0)      # a value function, so the pool is priced
    prop = NM.Proposer({"motifs": [m]}, contract=contract)
    act, notes = prop.propose(c["observation"], c["configuration"], c["seat"],
                              {"farmer": ["PASS"], "hands": [["PICKUP", "WHEAT", 3]],
                               "market": []})
    check("the proposal is rejected, not accepted on category equality",
          act["farmer"] == ["PASS"] and any("rejected" in n for n in notes),
          json.dumps(notes)[:200])


def case_contract_required(card):
    """Free upkeep is testable without a value function; a consuming op is not."""
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    p = K._new_plant("WHEAT", day, tpd)
    p["watered_today"] = False
    c = _place(card, 4, 4, p)
    c = _workers(c, [(4, 4)], [{"WHEAT": 1}])
    obs, cfg, seat = c["observation"], c["configuration"], c["seat"]
    f = NM.unit_facts(obs["farms"][seat], obs["private"], cfg, 0)
    water = _motif(["WATER"], NM.precondition(["WATER"], f))
    baseline = {"farmer": ["PASS"], "hands": [], "market": []}
    act, notes = NM.Proposer({"motifs": [water]}).propose(obs, cfg, seat, baseline)
    check("WATER on the seat's own unwatered plant fills the idle slot",
          act["farmer"] == ["WATER"], f"{act['farmer']} {json.dumps(notes)[:160]}")
    check("the accepted note makes no cash claim",
          any("no cash claim" in str(n.get("not_established", "")) for n in notes))

    a2 = K._new_animal("GOOSE", day)
    a2["fed_today"] = False
    c2 = _place(card, 4, 4, a2)
    c2 = _workers(c2, [(4, 4)], [{"WHEAT": 1}])
    o2 = c2["observation"]
    f2 = NM.unit_facts(o2["farms"][seat], o2["private"], cfg, 0)
    feed = _motif(["FEED"], NM.precondition(["FEED"], f2))
    act2, notes2 = NM.Proposer({"motifs": [feed]}).propose(o2, cfg, seat, baseline)
    check("FEED is refused without a value function: it spends carried WHEAT",
          act2["farmer"] == ["PASS"]
          and any("consumes a shared pool" in str(n.get("rejected", "")) for n in notes2),
          json.dumps(notes2)[:200])

    contract = dict(NM.derived_contract(o2, cfg, seat, baseline),
                    value=lambda *a: 1.0)
    contract["reserved_carry"] = {0: {"WHEAT": 1}}
    act3, notes3 = NM.Proposer({"motifs": [feed]}, contract=contract).propose(
        o2, cfg, seat, baseline)
    check("FEED is refused when the contract reserves that carried WHEAT",
          act3["farmer"] == ["PASS"]
          and any("reserved" in str(n.get("rejected", "")) for n in notes3),
          json.dumps(notes3)[:200])


def case_move_displacement_off(card):
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    p = K._new_plant("WHEAT", day, tpd)
    p["watered_today"] = False
    c = _place(card, 4, 4, p)
    c = _workers(c, [(4, 4)])
    obs, cfg, seat = c["observation"], c["configuration"], c["seat"]
    f = NM.unit_facts(obs["farms"][seat], obs["private"], cfg, 0)
    water = _motif(["WATER"], NM.precondition(["WATER"], f))
    baseline = {"farmer": ["NORTH"], "hands": [], "market": []}
    p_off = NM.Proposer({"motifs": [water]})
    check("movement displacement is off by default", not p_off.allow_displace_move)
    act, _ = p_off.propose(obs, cfg, seat, baseline)
    check("a moving slot is left alone by default", act["farmer"] == ["NORTH"])
    p_ask = NM.Proposer({"motifs": [water]}, allow_displace_move=True)
    check("asking for it without a value function does not enable it",
          not p_ask.allow_displace_move)
    contract = dict(NM.derived_contract(obs, cfg, seat, baseline),
                    value=lambda o, cf, s, u: 1.0 if u[0][0] == "WATER" else 0.0)
    p_on = NM.Proposer({"motifs": [water]}, contract=contract, allow_displace_move=True)
    check("with a value function it can be enabled", p_on.allow_displace_move)
    act2, notes2 = p_on.propose(obs, cfg, seat, baseline)
    check("and then the forgone step is recorded as the cost",
          act2["farmer"] == ["WATER"]
          and any("forgoes one step" in str(n.get("displaced", "")) for n in notes2),
          json.dumps(notes2)[:200])


def case_bundle_parity(card):
    """The bundled transition must be the engine's, on real and generated states."""
    bundle = NM.engine(prefer_bundle=True)
    installed = NM.engine(prefer_bundle=False)
    check("the bundle is engine_pin, not the installed package",
          bundle.__name__ == "engine_pin" and bundle is not installed,
          bundle.__name__)
    K = engine()
    day = int(card["observation"]["day"])
    tpd = int(card["configuration"]["turnsPerDay"])
    vectors = [
        ([["BUILD_PASTURE"], ["PLACE", "COW", 1]], (4, 4), None, [{}, {"COW": 1}]),
        ([["PLACE", "COW", 1], ["BUILD_PASTURE"]], (4, 4), None, [{}, {"COW": 1}]),
        ([["FEED"], ["CARE"]], (4, 4), K._new_animal("GOOSE", day), [{"WHEAT": 2}, {}]),
        ([["CARE"], ["CARE"]], (4, 4), K._new_animal("GOOSE", day), [{}, {}]),
        ([["DIG"], ["HARVEST"]], (4, 4), K._new_plant("WHEAT", day, tpd), [{}, {}]),
        ([["PICKUP", "WHEAT", 2], ["PICKUP", "WHEAT", 3]], (4, 4), None, [{}, {}]),
        ([["NORTH"], ["SOUTH"]], (4, 4), None, [{}, {}]),
        ([["DROP"], ["PASS"]], (4, 4), None, [{"WHEAT": 2}, {}]),
    ]
    bad = []
    for units, (x, y), tile, carries in vectors:
        c = _place(card, x, y, tile)
        c = _workers(c, [(x, y), (x, y)], carries)
        c["observation"]["private"]["shed"] = {"WHEAT": 3}
        a = _sim(c, units, K=bundle)
        b = _sim(c, units, K=installed)
        if (a["kinds"], [s["carry"] for s in a["slots"]],
                [s["pos"] for s in a["slots"]], a["farm"], a["priv"]) != \
           (b["kinds"], [s["carry"] for s in b["slots"]],
                [s["pos"] for s in b["slots"]], b["farm"], b["priv"]):
            bad.append(units)
    check(f"bundle/engine parity on {len(vectors)} sequencing vectors", not bad, str(bad))


def case_held_out_state_shapes():
    """Unseen seeds, driven by the real native baseline, not an all-PASS stub.

    The table was compiled from seeds 3131017 and 5252003; these seeds appear in no
    compiled row. Each proposal the layer makes on them is put back through the
    official interpreter and must be legal, non-blocking, and free of contextual
    no-ops and forbidden effects.
    """
    import motif_arm
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "results", "motifs.json")
    if not os.path.exists(path):
        check("held-out states: motif table present", False, "results/motifs.json missing")
        return
    table = json.load(open(path))
    compiled_seeds = {s.get("seed") for m in table["motifs"] for s in m.get("sources", [])}
    bad, proposed, turns = [], 0, 0
    for seed in (9191013, 6060013):
        check(f"held-out seed {seed} is not in the compiled sources",
              seed not in compiled_seeds, str(sorted(compiled_seeds)))
        r = motif_arm.run(seed, 0, "../20260907-offline-agent/main.py::agent",
                          "starter", table, arm="on", max_steps=220)
        turns += r["turns"]
        proposed += r["changed_turns"]
        for ch in r["changes"]:
            if ch["effect"] in NM.FORBIDDEN_EFFECTS:
                bad.append(f"{seed}@{ch['step']}: forbidden effect {ch['effect']}")
            if not str(ch["displaced"]).endswith("did nothing in context"):
                bad.append(f"{seed}@{ch['step']}: displaced a working slot")
    check(f"held-out: {turns} turns on unseen seeds, {proposed} proposals, "
          f"none forbidden and none displacing a working slot", not bad, str(bad[:4]))
    check("held-out: the layer actually fired on unseen state shapes", proposed > 0,
          f"{proposed} proposals")


def main():
    card = _card()
    case_feed_and_care(card)
    case_duplicate_move(card)
    case_build_then_place(card)
    case_dig_destroys_harvest_target(card)
    case_three_plants_two_seeds(card)
    case_cache_never_admits(card)
    case_prefix_facts(card)
    case_exact_worker_preservation(card)
    case_contract_required(card)
    case_move_displacement_off(card)
    case_bundle_parity(card)
    case_held_out_state_shapes()
    print(f"\n{'ALL PASS' if not FAIL else str(len(FAIL)) + ' FAILED: ' + ', '.join(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
