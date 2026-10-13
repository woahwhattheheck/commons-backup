#!/usr/bin/env python3
"""Independent, activation-aware S8 panel using the pinned official interpreter.

No hosted-score claim. Agents run in separate child processes; only their own
private observation is supplied. Observer callbacks wrap (never replace) the
unmodified engine transitions. Results retain failed cells and exact trace pins.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def package_hashes(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


class Census:
    """Passive counts: opportunity is distinct from returned or effective CARE."""
    def __init__(self, seat):
        self.seat = seat
        self.counts = Counter()
        self.hour = Counter()
        self.day = Counter()
        self.prices = []
        self.samples = []
        self.spare_rows = []
        self.effects = Counter()

    def observe(self, obs, action):
        step = obs["step"]
        day, hour = divmod(step, 24)
        farm = obs["farms"][self.seat]
        positions = [farm["farmer"], *farm["hands"]]
        rows = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
        prices = obs["market"]["prices"]
        egg, fert = prices.get("EGG", 0), prices.get("FERTILIZER", 0)
        for actor, row in enumerate(rows):
            self.counts["returned_" + str(row[0] if row else "EMPTY")] += 1
            if actor >= len(positions):
                self.counts["unrepresented_actor"] += 1
                continue
            x, y = positions[actor]
            tile = farm["tiles"][y][x]
            if not isinstance(tile, dict) or tile.get("animal") != "GOOSE":
                continue
            self.counts["goose_actor_turns"] += 1
            if row not in (["COLLECT_FERTILIZER"], ["PASS"]):
                continue
            self.counts["goose_spare_" + row[0]] += 1
            self.spare_rows.append({"step": step, "actor": actor, "action": row,
                                   "position": [x, y], "tile": dict(tile),
                                   "egg": egg, "fertilizer": fert,
                                   "shed_fertilizer": obs["private"]["shed"].get("FERTILIZER", 0)})
            if row == ["COLLECT_FERTILIZER"] and not tile.get("fertilizer_available"):
                self.counts["fertilizer_available_block"] += 1
                continue
            if not tile.get("fed_today") or tile.get("cared_today"):
                self.counts["fed_uncared_block"] += 1
                continue
            if tile.get("pending_care_bonus", 0):
                self.counts["pending_bonus_block"] += 1
                continue
            if day > 27 or day < tile["placed_day"] + 2:
                self.counts["production_window_block"] += 1
                continue
            current = int(day >= tile["placed_day"] + 3)
            if tile["yield_units"] + current + 2 > 4:
                self.counts["no_harvest_room_bound_block"] += 1
                continue
            if sum(p == positions[actor] for p in positions) > 1:
                self.counts["shared_site_block"] += 1
                continue
            self.counts["physiology_opportunity"] += 1
            self.day[str(day)] += 1
            self.hour[str(hour)] += 1
            original_price = egg - fert >= 20 and egg * 5 >= fert * 6
            original_buffer = obs["private"]["shed"].get("FERTILIZER", 0) >= 4
            if row == ["COLLECT_FERTILIZER"] and hour == 23:
                self.counts["h23_collect_physiology"] += 1
                self.counts["h23_collect_price_pass"] += int(original_price)
                self.counts["h23_collect_price_and_buffer"] += int(original_price and original_buffer)
                self.prices.append({"step": step, "actor": actor, "egg": egg,
                                    "fertilizer": fert, "buffer": original_buffer,
                                    "old_price_guard": original_price})
            if len(self.samples) < 24:
                self.samples.append({"step": step, "actor": actor, "action": row,
                                     "egg": egg, "fertilizer": fert, "held": tile["yield_units"]})

    def result(self):
        return {"counts": dict(self.counts), "effects": dict(self.effects),
                "opportunity_by_day": dict(self.day), "opportunity_by_hour": dict(self.hour),
                "h23_quotes": self.prices, "samples": self.samples, "spare_rows": self.spare_rows}


def install_observers(engine, census, own_farm, own_private):
    """The original engine functions remain the sole transition authority."""
    originals = {name: getattr(engine, name) for name in
                 ("_apply_unit_action", "_daily_refresh_animals", "_drop_inventories_to_shed", "_process_market")}
    effects = census.effects

    def unit(farm, private, actor, command, *args, **kwargs):
        relevant = farm is own_farm
        before = dict(private["inventories"][actor]) if relevant and actor < len(private["inventories"]) else {}
        tile = None
        if relevant:
            positions = [farm["farmer"], *farm["hands"]]
            if actor < len(positions):
                x, y = positions[actor]
                tile = farm["tiles"][y][x]
        cared = isinstance(tile, dict) and tile.get("cared_today", False)
        fed = isinstance(tile, dict) and tile.get("fed_today", False)
        result = originals["_apply_unit_action"](farm, private, actor, command, *args, **kwargs)
        if relevant and actor < len(private["inventories"]):
            after = private["inventories"][actor]
            if command and command[0] == "HARVEST":
                effects["egg_harvested"] += after.get("EGG", 0) - before.get("EGG", 0)
            if command == ["FERTILIZE"]:
                effects["fertilizer_consumed"] += before.get("FERTILIZER", 0) - after.get("FERTILIZER", 0)
            if command == ["COLLECT_FERTILIZER"]:
                effects["fertilizer_collected"] += after.get("FERTILIZER", 0) - before.get("FERTILIZER", 0)
            if isinstance(tile, dict) and tile.get("animal") == "GOOSE":
                effects["goose_effective_CARE"] += int(not cared and tile.get("cared_today", False))
                effects["goose_effective_FEED"] += int(not fed and tile.get("fed_today", False))
        return result

    def refresh(farm, day):
        before = []
        if farm is own_farm:
            for y, row in enumerate(farm["tiles"]):
                for x, tile in enumerate(row):
                    if isinstance(tile, dict) and tile.get("animal") == "GOOSE":
                        before.append((x, y, dict(tile)))
        result = originals["_daily_refresh_animals"](farm, day)
        for x, y, prior in before:
            tile = farm["tiles"][y][x]
            if not isinstance(tile, dict) or tile.get("animal") != "GOOSE":
                effects["goose_escaped"] += 1
                continue
            effects["egg_produced"] += tile["yield_units"] - prior["yield_units"]
            if day + 1 >= prior["placed_day"] + 4:
                bonus = prior.get("pending_care_bonus", 0) if prior["fed_today"] else 0
                effects["goose_bonus_present_on_fed_production"] += bonus
                effects["egg_clipped"] += max(0, prior["yield_units"] + 1 + bonus - 4)
            effects["goose_care_banked"] += int(prior["fed_today"] and prior["cared_today"])
        return result

    def drop(private, capacity):
        if private is not own_private:
            return originals["_drop_inventories_to_shed"](private, capacity)
        carried = Counter()
        for inv in private["inventories"]:
            carried.update(inv)
        before = dict(private["shed"])
        result = originals["_drop_inventories_to_shed"](private, capacity)
        for item in ("EGG", "FERTILIZER"):
            admitted = private["shed"].get(item, 0) - before.get(item, 0)
            effects[item.lower() + "_eod_admitted"] += admitted
            effects[item.lower() + "_eod_discarded"] += carried.get(item, 0) - admitted
        return result

    def market(state, env):
        before = dict(own_private["shed"])
        money = own_farm["money"]
        result = originals["_process_market"](state, env)
        effects["net_market_cash"] += own_farm["money"] - money
        for item in ("EGG", "FERTILIZER"):
            # Positive net removal, not a claim of gross sells under buy/sell mixtures.
            effects[item.lower() + "_net_market_out"] += before.get(item, 0) - own_private["shed"].get(item, 0)
        return result

    engine._apply_unit_action = unit
    engine._daily_refresh_animals = refresh
    engine._drop_inventories_to_shed = drop
    engine._process_market = market
    return originals


def play(runtime, seed, seat, output, *, opponent="official_starter", passive=True,
         entry=None, configuration=None, expected_package_sha256=None):
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = package_hashes(runtime)
    package_digest = hashlib.sha256(encoded(package)).hexdigest()
    if expected_package_sha256 is not None and package_digest != expected_package_sha256:
        raise ValueError("Runtime package digest mismatch; no agent code was executed")
    ev = load(runtime / "checks/reference/evaluator/evaluate.py", "henhouse_evaluator")
    cache = runtime / "checks/reference/engine"
    loader = runtime / "checks/reference/evaluator/loader.py"
    engine, engine_hashes = ev.get_engine(cache, loader)
    cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                     for k, v in engine.specification["configuration"].items()})
    overrides = dict(configuration or {})
    if set(overrides) - {"startingMoney", "shedCapacity"}:
        raise ValueError("Only explicit startingMoney/shedCapacity fixture overrides are supported")
    if any(type(value) is not int or value <= 0 for value in overrides.values()):
        raise ValueError("Fixture overrides must be positive integers")
    cfg.update(overrides)
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    if cfg.get("seed") is not None:
        raise ValueError("Environment seed must not be exposed to the agent")
    census, actors = Census(seat), []
    trace, actions_digest, world = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    originals = install_observers(engine, census, state[0].observation.farms[seat], state[seat].observation.private) if passive else {}
    rival = opponent if opponent == "official_starter" else str(Path(opponent).resolve() / "main.py")
    own = str(runtime / "main.py") if entry is None else str(entry)
    specs = [own, rival] if seat == 0 else [rival, own]
    entry_path, _, entry_function = own.partition("::")
    result = {"seed": seed, "seat": seat, "status": "failed", "steps": 0,
              "scores": None, "failure": None, "method": "official interpreter, process-isolated native entrypoints; not hosted scoring",
              "passive_observers": passive, "entrypoint": own,
              "entry_sha256": sha256(entry_path), "entry_function": entry_function or "agent",
              "opponent": "official_starter" if opponent == "official_starter" else {
                  "package_sha256": hashlib.sha256(encoded(package_hashes(Path(opponent).resolve()))).hexdigest()},
              "configuration_overrides": overrides, "configuration": dict(cfg),
              "runtime_members": len(package), "expected_package_sha256": expected_package_sha256,
              "rpc_timeout_seconds": 1.15,
              "game_timeout_seconds": 420, "engine_sha256": engine_hashes,
              "package_sha256": package_digest}
    start = time.perf_counter()
    rows = []
    try:
        for idx, spec in enumerate(specs):
            actor = ev.Actor(spec, cache, loader, 20260907 + (idx != seat), 15)
            actors.append(actor)
            if actor.ready.get("kind") != "ready":
                result["failure"] = {"seat": idx, "phase": "startup", **actor.ready}
                return result
        for step in range(cfg.episodeSteps):
            actions = []
            for idx, actor in enumerate(actors):
                state[idx].observation.step = step
                state[idx].observation.remainingOverageTime = 0
                response = actor.act(state[idx].observation, cfg, 1.15)
                if response.get("kind") != "action":
                    result["failure"] = {"seat": idx, "step": step, **response}
                    return result
                actions.append(response["action"])
            census.observe(state[seat].observation, actions[seat])
            for idx in range(2):
                state[idx].action = actions[idx]
            engine.interpreter(state, env)
            bank = [f["money"] for f in state[0].observation.farms]
            ownhash = hashlib.sha256(encoded(actions[seat])).hexdigest()
            row = {"step": step, "actions": actions, "bank": bank}
            trace.update(encoded(row))
            world.update(encoded([dict(s) for s in state]))
            actions_digest.update(encoded(actions[seat]))
            rows.append({"step": step, "own_action_sha256": ownhash, "bank": bank})
            result["steps"] += 1
            if all(s.status == "DONE" for s in state):
                result.update(status="complete", scores=[s.reward for s in state])
                result["margin"] = result["scores"][seat] - result["scores"][1-seat]
                result["terminal_stock"] = dict(state[seat].observation.private["shed"])
                break
            if time.perf_counter() - start > 420:
                result["failure"] = {"kind": "game_timeout", "step": step}
                break
        if result["status"] != "complete" and result["failure"] is None:
            result["failure"] = {"kind": "incomplete"}
    except Exception as exc:
        result["failure"] = {"kind": "driver_error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        for actor in actors:
            actor.close()
        for name, function in originals.items():
            setattr(engine, name, function)
        result.update(wall_seconds=time.perf_counter() - start, actors=[a.report() for a in actors],
                      trace_sha256=trace.hexdigest(), action_sha256=actions_digest.hexdigest(),
                      world_sha256=world.hexdigest(),
                      census=census.result())
        (output / "game.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        (output / "rows.json").write_text(json.dumps(rows, separators=(",", ":")) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seat", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--opponent", default="official_starter")
    parser.add_argument("--no-observers", action="store_true")
    parser.add_argument("--entry", help="Optional executable fixture path.py::function; NOT native strength evidence")
    parser.add_argument("--configuration", default="{}", help="Explicit JSON fixture overrides for both players")
    parser.add_argument("--expected-package-sha256")
    args = parser.parse_args()
    game = play(args.runtime, args.seed, args.seat, args.output,
                opponent=args.opponent, passive=not args.no_observers, entry=args.entry,
                configuration=json.loads(args.configuration), expected_package_sha256=args.expected_package_sha256)
    print(json.dumps({k: game[k] for k in ("seed", "seat", "status", "steps", "scores", "failure", "wall_seconds")}))
    return int(game["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
