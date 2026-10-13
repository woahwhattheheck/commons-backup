"""Trace public Kaggriculture replays without executing competitor agent code.

Recorded actions are replayed one transition at a time through the pinned
official interpreter. Executed-effect totals include only transitions whose
economic state reconciles. Observed deltas and modeled effects remain separate.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
MAX_DECODED = 256_000_000


def load_replay(path):
    data = Path(path).read_bytes()
    transport_hash = hashlib.sha256(data).hexdigest()
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_DECODED + 1)
    elif data.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if len(members) != 1 or members[0].file_size > MAX_DECODED:
                raise ValueError("Expected one bounded replay member")
            data = archive.read(members[0])
    if len(data) > MAX_DECODED:
        raise ValueError("Decoded replay exceeds bound")
    value = json.loads(data)
    envelope = []
    for _ in range(8):
        if isinstance(value, str):
            value = json.loads(value)
            envelope.append("json_string")
        elif isinstance(value, dict) and isinstance(value.get("steps"), list):
            if len(value["steps"]) < 2:
                raise ValueError("Replay requires at least two frames")
            return value, {"transport_sha256": transport_hash, "decoded_sha256": hashlib.sha256(data).hexdigest(),
                           "envelope": envelope}
        elif isinstance(value, dict):
            candidates = [key for key in ("replay", "result", "episode", "Replay") if key in value]
            if len(candidates) != 1:
                raise ValueError("Unknown or ambiguous replay envelope")
            envelope.append(candidates[0])
            value = value[candidates[0]]
        else:
            break
    raise ValueError("No recognized steps payload")


def evaluator():
    path = HERE.parent / "cloud-eval/evaluate.py"
    spec = importlib.util.spec_from_file_location("frontier_existing_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def frame_rows(frame):
    if isinstance(frame, dict) and "state" in frame:
        frame = frame["state"]
    if not isinstance(frame, list) or not frame or not all(isinstance(v, dict) for v in frame):
        raise ValueError("Expected a list of player states in every frame")
    return frame


def observations(frame):
    rows = frame_rows(frame)
    result = [copy.deepcopy(row.get("observation", {})) for row in rows]
    for key in ("farms", "market", "town", "step", "day", "hour"):
        source = next((obs[key] for obs in result if key in obs), None)
        if source is not None:
            for obs in result:
                if key not in obs:
                    obs[key] = copy.deepcopy(source)
    for seat, obs in enumerate(result):
        obs.setdefault("player", seat)
    return result


def contents(private):
    counts = Counter(private.get("shed", {}))
    for inv in private.get("inventories", []):
        counts.update(inv)
    return counts


def delta(before, after):
    return {key: after.get(key, 0) - before.get(key, 0)
            for key in sorted(set(before) | set(after)) if after.get(key, 0) != before.get(key, 0)}


def farm_snapshot(farm):
    animals, crops, held = Counter(), Counter(), Counter()
    for row in farm["tiles"]:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if "animal" in tile:
                animals[tile["animal"]] += 1
                held[{"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}[tile["animal"]]] += tile.get("yield_units", 0)
            elif tile.get("kind") == "PLANT":
                crops[tile["crop"]] += 1
                held[tile["crop"]] += tile.get("yield_units", 0)
    return {"cash": farm["money"], "animals": dict(animals), "crops": dict(crops),
            "held_yield": dict(held), "land": list(farm["unlocked_quadrants"]),
            "hands": len(farm.get("hands", [])), "hires_today": farm.get("hires_today", 0)}


def economic_farm(farm, day_boundary):
    value = copy.deepcopy(farm)
    if day_boundary:
        # Unknown replay seed affects weed spawn locations only here. Retain
        # every productive tile, position, cash, hand and land field exactly.
        value["tiles"] = [[None if isinstance(t, dict) and t.get("kind") == "WEED" else t
                           for t in row] for row in value["tiles"]]
    return value


def audit_transition(engine, ev, before, after, actions, cfg, step, info):
    missing = [seat for seat, obs in enumerate(before) if "private" not in obs or
               "private" not in after[seat]]
    if missing:
        return {"status": "UNAVAILABLE", "reason": "public replay omits inventory observations", "seats": missing}
    shared = ev.structify(copy.deepcopy(before[0]))
    state = []
    for seat, obs in enumerate(before):
        own = ev.structify(copy.deepcopy(obs))
        own.farms, own.market, own.town = shared.farms, shared.market, shared.town
        own.step = step
        state.append(ev.Struct(observation=own, action=copy.deepcopy(actions[seat]), status="ACTIVE", reward=0))
    env = ev.Struct(configuration=ev.structify(copy.deepcopy(cfg)), done=False, info=copy.deepcopy(info))
    farms = state[0].observation.farms
    owners = {id(farm): seat for seat, farm in enumerate(farms)}
    privates = {id(s.observation.private): seat for seat, s in enumerate(state)}
    events = []
    originals = {}

    def wrap(name, factory):
        originals[name] = getattr(engine, name)
        setattr(engine, name, factory(originals[name]))

    def unit_wrapper(original):
        def call(farm, private, idx, action, *rest, **kw):
            old_farm, old_private = copy.deepcopy(farm), copy.deepcopy(private)
            result = original(farm, private, idx, action, *rest, **kw)
            op = action[0] if isinstance(action, list) and action else "INVALID"
            event = {"kind": "unit", "seat": owners[id(farm)], "worker": idx, "action": action,
                     "changed": old_farm != farm or old_private != private,
                     "inventory_delta": delta(contents(old_private), contents(private)),
                     "seed_delta": delta(old_private.get("seeds", {}), private.get("seeds", {})),
                     "animals_owned_delta": delta(old_private.get("animals", {}), private.get("animals", {})),
                     "held_yield_delta": delta(farm_snapshot(old_farm)["held_yield"], farm_snapshot(farm)["held_yield"]),
                     "installed_crop_delta": delta(farm_snapshot(old_farm)["crops"], farm_snapshot(farm)["crops"]),
                     "installed_animal_delta": delta(farm_snapshot(old_farm)["animals"], farm_snapshot(farm)["animals"])}
            if op == "DROP":
                event["discarded"] = {k: -v for k, v in event["inventory_delta"].items() if v < 0}
            events.append(event)
            return result
        return call

    def trade_wrapper(original):
        def call(op, item, price, farm, private, market, *rest, **kw):
            cash = farm["money"]
            result = original(op, item, price, farm, private, market, *rest, **kw)
            events.append({"kind": "trade", "seat": owners[id(farm)], "op": op, "item": item,
                           "quoted_price": price, "success": bool(result), "cash_delta": farm["money"] - cash})
            return result
        return call

    def capital_wrapper(name):
        def factory(original):
            def call(farm, *args, **kw):
                cash = farm["money"]
                old = copy.deepcopy(farm)
                result = original(farm, *args, **kw)
                events.append({"kind": name, "seat": owners[id(farm)], "changed": old != farm,
                               "cash_delta": farm["money"] - cash})
                return result
            return call
        return factory

    def growth_wrapper(name):
        def factory(original):
            def call(farm, *args, **kw):
                old = farm_snapshot(farm)
                result = original(farm, *args, **kw)
                new = farm_snapshot(farm)
                events.append({"kind": name, "seat": owners[id(farm)],
                    "yield_delta": delta(old["held_yield"], new["held_yield"]),
                    "animal_delta": delta(old["animals"], new["animals"]),
                    "crop_delta": delta(old["crops"], new["crops"])})
                return result
            return call
        return factory

    def drop_wrapper(original):
        def call(private, *args, **kw):
            old = contents(private)
            result = original(private, *args, **kw)
            events.append({"kind": "day_deposit", "seat": privates[id(private)],
                           "inventory_delta": delta(old, contents(private))})
            return result
        return call

    try:
        wrap("_apply_unit_action", unit_wrapper)
        wrap("_commit_unit", trade_wrapper)
        wrap("_do_hire", capital_wrapper("hire"))
        wrap("_do_buy_land", capital_wrapper("land"))
        for name in ("_daily_refresh_plants", "_daily_refresh_animals", "_decay_plants"):
            wrap(name, growth_wrapper(name))
        wrap("_drop_inventories_to_shed", drop_wrapper)
        engine.interpreter(state, env)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        for name, original in originals.items():
            setattr(engine, name, original)
    boundary = (step + 1) % cfg["turnsPerDay"] == 0
    checks = {}
    for seat, observed in enumerate(after):
        checks[f"farm_{seat}"] = economic_farm(farms[seat], boundary) == economic_farm(observed["farms"][seat], boundary)
        checks[f"inventory_{seat}"] = state[seat].observation.private == observed["private"]
    checks["market_prices"] = shared.market["prices"] == after[0]["market"]["prices"]
    checks["market_inventory"] = shared.market["inventory"] == after[0]["market"]["inventory"]
    checks["town"] = shared.town == after[0].get("town", {}) if not boundary else True
    verified = all(checks.values())
    return {"status": "RECONCILED" if verified else "MISMATCH", "checks": checks,
            "excluded_random_boundary_fields": ["weed locations", "new shop draw"] if boundary else [],
            "events": events if verified else [],
            "unverified_event_count": 0 if verified else len(events)}


def analyze(replay, engine, ev, source=None):
    cfg = {k: v.get("default") if isinstance(v, dict) else v
           for k, v in engine.specification["configuration"].items()}
    cfg.update(replay.get("configuration", {}))
    frames = replay["steps"]
    first, last = observations(frames[0]), observations(frames[-1])
    players = len(first)
    if players != 2:
        raise ValueError("This Kaggriculture analyzer expects two players")
    totals = [{"requested": Counter(), "executed": Counter(), "no_effect": Counter(),
               "purchases": Counter(), "purchases_by_order": {}, "water_yield": Counter(), "planted_initial_yield": Counter(), "harvested": Counter(), "sales_units": Counter(), "sales_coins": Counter(),
               "production": Counter(), "discarded": Counter(), "capital_spend": Counter(),
               "cash_residual": 0} for _ in first]
    transitions, daily = [], []
    before = first
    for index in range(1, len(frames)):
        after = observations(frames[index])
        actions = [row.get("action") or {} for row in frame_rows(frames[index])]
        if not all(isinstance(a, dict) for a in actions):
            raise ValueError("Expected action dictionaries")
        step = before[0].get("step", index - 1)
        row = {"frame": index, "action_step": step, "day": step // cfg["turnsPerDay"],
               "actions": actions, "prices_before": before[0]["market"]["prices"],
               "prices_after": after[0]["market"]["prices"],
               "observed_cash_delta": [after[0]["farms"][s]["money"] - before[0]["farms"][s]["money"] for s in range(players)],
               "farms_after": [farm_snapshot(after[0]["farms"][s]) for s in range(players)],
               "inventory_before": [copy.deepcopy(o.get("private")) for o in before],
               "inventory_after": [copy.deepcopy(o.get("private")) for o in after]}
        for seat, action in enumerate(actions):
            for op in [action.get("farmer", ["PASS"]), *action.get("hands", [])]:
                totals[seat]["requested"][op[0] if isinstance(op, list) and op else "INVALID"] += 1
        audit = audit_transition(engine, ev, before, after, actions, cfg, step, replay.get("info", {}))
        row["audit"] = audit
        cash_accounted = [0] * players
        if audit["status"] == "RECONCILED":
            for event in audit["events"]:
                seat, kind = event["seat"], event["kind"]
                total = totals[seat]
                cash_accounted[seat] += event.get("cash_delta", 0)
                if kind == "unit":
                    op = event["action"][0] if event["action"] else "INVALID"
                    total["executed" if event["changed"] else "no_effect"][op] += 1
                    total["discarded"].update(event.get("discarded", {}))
                    if op in ("WATER", "PLANT"):
                        total["water_yield" if op == "WATER" else "planted_initial_yield"].update({k:v for k,v in event["held_yield_delta"].items() if v>0})
                    if op == "HARVEST":
                        total["harvested"].update({k:v for k,v in event["inventory_delta"].items() if v>0})
                elif kind == "trade" and event["success"]:
                    if event["op"] == "SELL":
                        total["sales_units"][event["item"]] += 1
                        total["sales_coins"][event["item"]] += event["cash_delta"]
                    else:
                        total["purchases"][event["item"]] += 1
                        total["purchases_by_order"].setdefault(event["op"], Counter())[event["item"]] += 1
                        total["capital_spend"][event["op"]] -= event["cash_delta"]
                elif kind in ("hire", "land"):
                    total["capital_spend"][kind] -= event["cash_delta"]
                elif kind.startswith("_daily_refresh"):
                    total["production"].update({k: v for k, v in event["yield_delta"].items() if v > 0})
                elif kind == "day_deposit":
                    total["discarded"].update({k: -v for k, v in event["inventory_delta"].items() if v < 0})
            row["cash_residual"] = [row["observed_cash_delta"][s] - cash_accounted[s] for s in range(players)]
            for seat in range(players):
                totals[seat]["cash_residual"] += row["cash_residual"][seat]
        if index == 1 or (step + 1) % cfg["turnsPerDay"] == 0 or index == len(frames) - 1:
            daily.append({"frame": index, "action_step": step, "farms": row["farms_after"], "prices": row["prices_after"],
                          "shops": after[0].get("town", {}).get("unlocked_shops", [])})
        transitions.append(row)
        before = after
    statuses = Counter(row["audit"]["status"] for row in transitions)
    return {"schema_version": 1, "source": source or {}, "engine_ref": ev.ENGINE_REF,
        "episode_id": replay.get("info", {}).get("EpisodeId"), "players": replay.get("info", {}).get("TeamNames"),
        "action_alignment": "actions on frame i consume observations from frame i-1",
        "configuration": cfg, "frames": len(frames), "transition_statuses": dict(statuses),
        "opening": [farm_snapshot(first[0]["farms"][s]) for s in range(players)],
        "terminal": [farm_snapshot(last[0]["farms"][s]) for s in range(players)],
        "recorded_rewards": [row.get("reward") for row in frame_rows(frames[-1])],
        "verified_transition_totals": totals, "daily": daily, "transitions": transitions,
        "limitations": ["Totals of executed effects exclude every unreconciled transition.",
                        "A PASS or unchanged action is observable inactivity, not proof of an avoidable mistake.",
                        "Day-boundary reconciliation excludes random weed locations and the new shop draw.",
                        "Production counts added held yield, not unconstrained theoretical production."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay, source = load_replay(args.replay)
    ev = evaluator()
    engine, hashes = ev.get_engine(args.engine_dir)
    source["engine_sha256"] = hashes
    result = analyze(replay, engine, ev, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("frames", "transition_statuses", "opening", "terminal", "verified_transition_totals")}))
