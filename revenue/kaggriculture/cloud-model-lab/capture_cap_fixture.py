"""Capture a REAL midgame cap errand: observation, selected action, snapshot, arrival.

T08 asked for a retained midgame fixture rather than synthetic day-29 states. This
runs an actual game and retains every turn of one committed errand's life --
the turn it is committed, each turn it travels, the turn the harvest executes and
the lot becomes carried, and the end-of-day close the cargo is deposited at --
with the exact observation, the exact selected action, the producer snapshot, and
the arrival contract T08's own module builds from it.

Nothing here is constructed. Every observation is one the engine produced.
"""

import argparse
import copy
import json
import os
import sys

import cards as cards_mod
import route_cards

T08 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "cloud-titan-composition", "integration-v2")


def post_unit_observation(obs, cfg, seat, action):
    """Apply the seat's own unit phase with the pinned transition, nothing else."""
    import copy as _c
    import native_motifs as NM
    units = [list(action.get("farmer") or ["PASS"])] + \
            [list(h) for h in (action.get("hands") or [])]
    pos = [obs["farms"][seat]["farmer"]] + list(obs["farms"][seat].get("hands") or [])
    units = units[:len(pos)]
    res = NM.simulate(NM.engine(), obs, cfg, seat, units)
    out = _c.deepcopy(obs)
    out["farms"][seat] = res["farm"]
    out["private"] = res["priv"]
    return out


def load_contract():
    import importlib.util
    path = os.path.join(T08, "arrival_contract.py")
    spec = importlib.util.spec_from_file_location("t08_arrival_contract",
                                                  os.path.realpath(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def scan(seed, seat, opponent):
    """Pass one: find an errand that actually reaches `carried`.

    The first live errand is not necessarily a completed one -- the first attempt
    tracked one that was still travelling when the day closed. The episode is
    deterministic, so a second pass reproduces the chosen errand exactly.
    """
    import arlene_arm
    import arlene_plan
    import arrival_facts
    import native_motifs as NM
    A, _ = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    me = arlene_plan.PlanOverlay(A, arrival_facts.RouteAwareCapChooser(NM.engine()),
                                 one_way=True)
    me.chooser.agent = me.agent
    env = cards_mod.make_env(seed)
    env.reset(2)
    life = {}
    while not env.done:
        acts = [None, None]
        obs = env.state[seat].observation
        step = int(obs["day"]) * 24 + int(obs["hour"])
        for i in range(2):
            o = env.state[i].observation
            acts[i] = me.act(o) if i == seat else opp(o, env.configuration)
        for eid, e in me.errands.items():
            rec = life.setdefault(eid, {"start": step, "carried": None,
                                        "aborted": None, "day": e["day"]})
            if e["status"] == "carried" and rec["carried"] is None:
                rec["carried"] = step
            if e["status"] == "aborted" and rec["aborted"] is None:
                rec["aborted"] = step
        env.step(acts)
    done = [(k, v) for k, v in life.items() if v["carried"] is not None]
    done.sort(key=lambda kv: kv[1]["start"])
    return done, life


def capture(seed, seat, opponent, out_path, max_days=None, want=None):
    import arlene_arm
    import arlene_plan
    import arrival_facts
    import native_motifs as NM
    A, arl_id = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    contract = load_contract()

    me = arlene_plan.PlanOverlay(A, arrival_facts.RouteAwareCapChooser(NM.engine()),
                                 one_way=True)
    me.chooser.agent = me.agent
    env = cards_mod.make_env(seed)
    env.reset(2)
    frames, tracked, done_at = [], want, None
    while not env.done:
        acts = [None, None]
        obs = env.state[seat].observation
        step = int(obs["day"]) * 24 + int(obs["hour"])
        if max_days is not None and int(obs["day"]) > max_days:
            break
        snap_obs = copy.deepcopy(json.loads(json.dumps(dict(obs), default=str)))
        snap_obs["step"] = step
        snap_obs["player"] = seat
        for i in range(2):
            o = env.state[i].observation
            acts[i] = me.act(o) if i == seat else opp(o, env.configuration)
        action = json.loads(json.dumps(acts[seat], default=str))
        snap = me.producer_snapshot(snap_obs)
        # The post-unit observation: the caller's own deterministic unit transition
        # applied to the selected action, which is the state a SELL reconciliation
        # actually works from and the one in which a lifted lot is visible.
        post_obs = post_unit_observation(snap_obs, dict(env.configuration), seat,
                                         action)
        post_snap = me.producer_snapshot(post_obs)
        live = [p for p in snap["plans"] if p.get("status") in ("pending", "carried")]
        if tracked is None and live:
            tracked = live[0]["errand_id"]
        row = (next((p for p in snap["plans"] if p.get("errand_id") == tracked), None)
               if tracked else None)
        if row is None and not frames:
            env.step(acts)
            continue          # the tracked errand has not been committed yet
        if tracked:
            arr = None
            if row is not None:
                one = {"owner": snap["owner"], "observed_step": step,
                       "plans": [row]}
                try:
                    arr = contract.build_arrival_contract(
                        snap_obs, dict(env.configuration), action, [one])
                except contract.ContractError as exc:
                    arr = {"contract_error": str(exc)}
            frames.append({
                "step": step, "day": int(obs["day"]), "hour": int(obs["hour"]),
                "observation": snap_obs, "selected_action": action,
                "producer_snapshot": snap, "tracked_row": row,
                "post_unit_observation": post_obs,
                "producer_snapshot_post_unit": post_snap,
                "tracked_row_post_unit": next(
                    (q for q in post_snap["plans"]
                     if q.get("errand_id") == tracked), None),
                "arrival_contract": arr,
                "carried_now": {k: int(v) for inv in
                                (obs["private"].get("inventories") or [])
                                for k, v in inv.items() if v},
            })
            if row is not None and row.get("status") == "carried":
                done_at = done_at or step
            if row is None:
                break                     # the day closed; the lot has landed
        env.step(acts)
    payload = {
        "seed": seed, "seat": seat, "opponent": opponent, "arlene": arl_id,
        "engine_pin": cards_mod.ENGINE_PIN,
        "tracked_errand": tracked, "carried_at_step": done_at,
        "note": "real engine observations from a full game; nothing synthetic",
        "frames": frames,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(payload, open(out_path, "w"), indent=1, default=str)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=9810001)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--out", default="fixtures/cap-midgame-errand.json")
    a = ap.parse_args()
    done, life = scan(a.seed, a.seat, a.opponent)
    if not done:
        print(f"no errand reached `carried` on seed {a.seed} seat {a.seat}; "
              f"{len(life)} errand(s) recorded")
        return
    want = done[0][0]
    print(f"{len(life)} errands recorded, {len(done)} reached `carried`; "
          f"retaining {want} (start {done[0][1]['start']}, "
          f"carried {done[0][1]['carried']})")
    p = capture(a.seed, a.seat, a.opponent, a.out, a.max_days, want=want)
    print(f"tracked errand {p['tracked_errand']}, {len(p['frames'])} retained frames, "
          f"carried at step {p['carried_at_step']}")
    for f in p["frames"]:
        r = f["tracked_row"] or {"status": "gone (day closed; lot deposited)"}
        ac = f["arrival_contract"] or {}
        ev = (ac.get("capacity_events") or []) if isinstance(ac, dict) else []
        rc = (ac.get("realized_carried") or []) if isinstance(ac, dict) else []
        print(f"  step {f['step']:4d} d{f['day']}h{f['hour']:02d} "
              f"status={str(r.get('status')):<34s} "
              f"total={r.get('units_total')} incr={r.get('units_incremental')} "
              f"carried={r.get('observed_carried_units')} "
              f"arrival={r.get('arrival_step')} | events={len(ev)} "
              f"realized={len(rc)} | post-unit status="
              f"{(f.get('tracked_row_post_unit') or {}).get('status')} "
              f"carried={(f.get('tracked_row_post_unit') or {}).get('observed_carried_units')}"
              + (f"  ERROR {ac['contract_error']}" if isinstance(ac, dict)
                 and ac.get("contract_error") else ""))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
