"""Committed-output contract: lifecycle, disjointness, and T08's own validator.

Everything here runs against the retained MIDGAME fixture -- real engine
observations from a real game, captured by `capture_cap_fixture.py` -- and against
T08's actual `integration-v2/arrival_contract.py`, imported unmodified.

Run: python -B tests/test_producer_snapshot.py
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, LAB)

import arlene_plan
import arrival_facts
import native_motifs as NM
import route_cards

FIXTURE = os.path.join(LAB, "fixtures", "cap-midgame-errand.json")
T08 = os.path.join(LAB, "..", "cloud-titan-composition", "integration-v2")
FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def contract_mod():
    spec = importlib.util.spec_from_file_location(
        "t08_arrival_contract", os.path.realpath(os.path.join(T08, "arrival_contract.py")))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def overlay():
    A, _ = route_cards.load_arlene()
    ov = arlene_plan.PlanOverlay(A, arrival_facts.RouteAwareCapChooser(NM.engine()),
                                 one_way=True)
    ov.chooser.agent = ov.agent
    return ov


def main():
    fx = json.load(open(FIXTURE))
    C = contract_mod()
    frames = fx["frames"]
    check("retained fixture is real midgame engine state, not synthetic",
          fx["frames"] and all(f["day"] < 29 for f in frames)
          and "nothing synthetic" in fx["note"],
          f"seed {fx['seed']}, days {frames[0]['day']}-{frames[-1]['day']}, "
          f"{len(frames)} frames")

    # ---- committed lifecycle: committed -> harvest -> carried -> EOD ----
    pre = [f["tracked_row"] for f in frames if f["tracked_row"]]
    post = [f.get("tracked_row_post_unit") for f in frames
            if f.get("tracked_row_post_unit")]
    check("errand id is stable across its whole life",
          len({r["errand_id"] for r in pre}) == 1, pre[0]["errand_id"])
    check("it is committed as pending with the WHOLE lot and a distinct incremental",
          pre[0]["status"] == "pending" and pre[0]["units_total"] == 4
          and pre[0]["units_incremental"] == 2,
          f"total {pre[0]['units_total']} incremental {pre[0]['units_incremental']}")
    check("pre-unit observation of the harvest turn is still PENDING capacity",
          pre[-1]["status"] == "pending" and pre[-1]["observed_carried_units"] == 0)
    carried = [r for r in post if r["status"] == "carried"]
    check("post-unit observation of that same turn is CARRIED with the realised lot",
          carried and carried[0]["observed_carried_units"] == 4
          and carried[0]["units_total"] == 4,
          f"{carried[0]['observed_carried_units'] if carried else 'none'} units")
    check("carried state reports realization equal to the whole lot, as the "
          "contract requires",
          all(r["observed_carried_units"] == r["units_total"] for r in carried))
    last = frames[-1]
    check("after the day closes the lot is gone from the snapshot, not a ghost lot",
          last["tracked_row"] is None)
    arr = [f["arrival_step"] for f in pre]
    eod = (frames[0]["step"] // 24 + 1) * 24 - 1
    check("arrival is this observed day's close, as eod_auto requires",
          set(arr) == {eod} and pre[0]["arrival_kind"] == "eod_auto", f"step {eod}")

    # ---- T08's own validator accepts every frame ----
    bad = []
    for f in frames:
        for key, obs in (("pre", f["observation"]),
                         ("post", f.get("post_unit_observation"))):
            snap = (f["producer_snapshot"] if key == "pre"
                    else f.get("producer_snapshot_post_unit"))
            if not snap or obs is None:
                continue
            try:
                C.build_arrival_contract(obs, {"turnsPerDay": 24, "episodeSteps": 720},
                                         f["selected_action"], [snap])
            except C.ContractError as exc:
                bad.append((f["step"], key, str(exc)))
    check(f"T08's build_arrival_contract accepts all {len(frames)} retained frames, "
          f"pre-unit and post-unit", not bad, str(bad[:3]))

    ev = [f["arrival_contract"]["capacity_events"] for f in frames
          if isinstance(f.get("arrival_contract"), dict)
          and f["arrival_contract"].get("capacity_events")]
    check("pending capacity is exported as contingent, never as guaranteed stock",
          ev and all(e["contingent"] and e["guaranteed_stock_units"] == 0
                     and e["no_forced_sale_date"] for row in ev for e in row))
    check("pending capacity units are the WHOLE lot, not the incremental part",
          all(e["pending_capacity_units"] == e["units_total"]
              and e["units_incremental"] <= e["units_total"]
              for row in ev for e in row),
          f"{ev[0][0]['pending_capacity_units']} of {ev[0][0]['units_total']}, "
          f"incremental {ev[0][0]['units_incremental']}")

    # ---- opportunity rows are NOT committed output ----
    ov = overlay()
    obs0 = frames[0]["observation"]
    opp = ov.opportunity_facts(obs0)
    snap0 = ov.producer_snapshot(obs0)
    check("opportunity_facts stays separately callable", isinstance(opp, list))
    check("a fresh overlay has committed nothing, however many opportunities exist",
          snap0["plans"] == [] and len(opp) >= 0,
          f"{len(opp)} opportunity rows, {len(snap0['plans'])} committed")
    tgts = [tuple(o["at"]) for o in opp]
    check("opportunity rows may repeat a tile, which is why they are not reservable",
          len(tgts) >= len(set(tgts)))
    raised = None
    try:
        ov.pending_arrivals(obs0)
    except AttributeError as exc:
        raised = str(exc)
    check("the old pending_arrivals name refuses rather than returning candidates "
          "that a consumer would reserve", raised and "producer_snapshot" in raised)

    # ---- abort releases the reservation ----
    ov2 = overlay()
    ov2._step = 100
    ov2.errands["cap-100-w2-t33"] = {
        "errand_id": "cap-100-w2-t33", "worker_index": 2, "target": [3, 3],
        "product": "MILK", "units_total": 3, "units_incremental": 1,
        "arrival_step": 119, "arrival_kind": "eod_auto", "no_forced_sale_date": True,
        "status": "pending", "observed_carried_units": 0, "started": 100,
        "day": 4, "realized_at_step": None}
    ov2._abort("cap-100-w2-t33")
    obs_a = {"day": 4, "hour": 5, "player": 0, "step": 101,
             "private": {"inventories": [{}, {}, {}]}, "farms": [{}, {}]}
    rows = ov2.producer_snapshot(obs_a)["plans"]
    check("an aborted errand exports as aborted and reserves nothing",
          rows == [{"errand_id": "cap-100-w2-t33", "status": "aborted"}], str(rows))
    ov2.errands["cap-100-w2-t33"]["status"] = "carried"
    ov2.errands["cap-100-w2-t33"]["observed_carried_units"] = 3
    ov2.errands["cap-100-w2-t33"]["realized_at_step"] = 100
    ov2._abort("cap-100-w2-t33")
    check("a lot already carried is not retroactively aborted",
          ov2.errands["cap-100-w2-t33"]["status"] == "carried")

    # ---- disjointness for FLORA-owned hands and tiles ----
    ov3 = overlay()
    check("excluded workers and blocked targets default to empty, so frozen "
          "behaviour is unchanged",
          ov3.excluded_workers == set() and ov3.blocked_targets == set())
    obs1 = frames[0]["observation"]
    ov3.act(obs1, excluded_workers=[8], blocked_targets=[(1, 4)])
    check("supplied exclusions are retained for the composition",
          ov3.excluded_workers == {8} and ov3.blocked_targets == {(1, 4)})
    owned = {p["worker_index"] for p in ov3.producer_snapshot(obs1)["plans"]
             if p.get("status") != "aborted"}
    check("an excluded worker is never committed by this producer",
          8 not in owned, f"committed workers {sorted(owned)}")
    tset = {tuple(p["target"]) for p in ov3.producer_snapshot(obs1)["plans"]
            if p.get("target")}
    check("a blocked target is never committed by this producer",
          (1, 4) not in tset, f"committed targets {sorted(tset)}")

    # ---- selected-action injection: no second parent controller ----
    ov4 = overlay()
    injected = {"farmer": ["PASS"],
                "hands": [["PASS"]] * len(obs1["farms"][0].get("hands") or []),
                "market": []}
    out = ov4.act(obs1, selected_action=injected)
    check("an injected selected action is used as the base instead of calling the "
          "parent", isinstance(out, dict) and "farmer" in out and "market" in out
          and out["market"] == [])

    print(f"\n{'ALL PASS' if not FAIL else str(len(FAIL)) + ' FAILED: ' + ', '.join(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
