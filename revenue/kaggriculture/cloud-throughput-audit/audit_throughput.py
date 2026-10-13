"""Audit recorded TITAN unit phases. No policy invocation or new whole games.

The supplied deterministic mechanics module is used only on deep copies of
observations that were actually recorded. Counts are diagnostics, not proposed
policy gains. This standalone program never writes into the input bundle.
"""
from __future__ import annotations
import argparse
import collections
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mechanics(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("throughput_pinned_mechanics", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import mechanics: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_action(mechanics: Any, obs: dict, action: dict, cfg: dict) -> dict:
    """Model exact ordered unit actions, including global seed preflight.

    Observe pre-unit state AFTER earlier units, so a duplicate harvest is not
    confused with an animal that had no yield before either worker arrived.
    """
    me = int(obs["player"])
    farm = copy.deepcopy(obs["farms"][me])
    private = copy.deepcopy(obs["private"])
    original_tiles = obs["farms"][me]["tiles"]
    action = action if isinstance(action, dict) else {}
    hands = action.get("hands", [])
    hands = hands if isinstance(hands, list) else []
    actions = [action.get("farmer", ["PASS"]), *hands]
    demand = collections.Counter(a[1] for a in actions if isinstance(a, list) and len(a) > 1 and a[0] == "PLANT")
    blocked = {p for p, n in demand.items() if n > private["seeds"].get(p, 0)}
    step = int(obs["step"])
    day_len = max(1, int(cfg.get("turnsPerDay", 24)))
    harvest_counts: collections.Counter = collections.Counter()
    drops = []
    noops = []
    harvested_here = {}
    for idx, requested in enumerate(actions):
        if not isinstance(requested, list) or not requested:
            continue
        op = requested[0]
        positions = [farm["farmer"], *farm["hands"]]
        if idx >= len(positions):
            if op == "HARVEST":
                harvest_counts["missing_unit"] += 1
                noops.append({"step": step, "unit": idx, "reason": "missing_unit", "xy": None})
            continue
        x, y = positions[idx]
        tile = copy.deepcopy(farm["tiles"][y][x])
        initial_tile = original_tiles[y][x]
        inv_before = dict(private["inventories"][idx])
        shed_before = dict(private["shed"])
        actual = ["PASS"] if op == "PLANT" and len(requested) > 1 and requested[1] in blocked else requested
        mechanics._apply_unit_action(farm, private, idx, actual, int(cfg.get("boardSize", len(farm["tiles"]))), step // day_len, day_len, int(cfg.get("shedCapacity", 100)))
        inv_after = private["inventories"][idx]
        if op == "HARVEST":
            added = {p: n - inv_before.get(p, 0) for p, n in inv_after.items() if n > inv_before.get(p, 0)}
            if added:
                harvest_counts["productive"] += 1
                harvested_here[(x, y)] = idx
                continue
            reason = "unclassified"
            if (x, y) in harvested_here:
                reason = "depleted_by_earlier_unit"
            elif not isinstance(tile, dict):
                reason = "no_yield_tile"
            elif tile.get("yield_units", 0) <= 0:
                reason = "zero_yield_before_turn"
            elif tile.get("kind") == "PLANT" and step // day_len - tile["planted_day"] < mechanics.CROPS[tile["crop"]]["first_yield_day"]:
                reason = "immature_crop"
            harvest_counts[reason] += 1
            event = {"step": step, "unit": idx, "xy": [x, y], "reason": reason, "pre_unit_tile": tile, "observed_tile": initial_tile}
            if (x, y) in harvested_here:
                event["earlier_harvester"] = harvested_here[(x, y)]
            noops.append(event)
        elif op == "DROP":
            lost = {}
            deposited = {}
            for product, quantity in inv_before.items():
                moved = private["shed"].get(product, 0) - shed_before.get(product, 0)
                missing = quantity - inv_after.get(product, 0) - moved
                if moved > 0:
                    deposited[product] = moved
                if missing > 0:
                    lost[product] = missing
            if lost:
                drops.append({"step": step, "unit": idx, "xy": [x, y], "lost": lost, "deposited": deposited, "shed_used_before": sum(shed_before.values()), "inventory_before": inv_before})
    terminal = None
    if step == int(cfg.get("episodeSteps", 720)) - 2:
        market = action.get("market", [])[:max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))]
        sold = collections.Counter()
        sale_only = all(not o or (len(o) >= 3 and o[0] == "SELL") for o in market)
        for o in market:
            if o and len(o) >= 3 and o[0] == "SELL":
                sold[o[1]] += max(0, int(o[2]))
        terminal = {"sale_only_orders": sale_only, "post_unit_shed": private["shed"], "requested_sales": dict(sold), "unoffered_shed": {p: n - sold[p] for p, n in private["shed"].items() if p in mechanics.PRODUCTS and n > sold[p]}, "held_inventory": [{p: n for p, n in inv.items() if n > 0} for inv in private["inventories"]]}
    return {"harvest_counts": dict(harvest_counts), "noops": noops, "drop_losses": drops, "terminal": terminal}


def audit_bundle(root: Path, output: Path, limit: int | None = None) -> dict:
    summary = json.loads((root / "FINAL-SUMMARY.json").read_text())
    current = json.loads((root / "CURRENT-ARCHIVE.json").read_text())
    if current["sha256"] != summary["archive_sha256"]:
        raise ValueError("Summary and archived CURRENT identity differ")
    mechanics_path = root / "candidate/mechanics.py"
    mechanics = load_mechanics(mechanics_path)
    results = []
    for item in summary["games"][:limit]:
        report_path = (root / item["report"]).resolve()
        if not report_path.is_relative_to(root.resolve()):
            raise ValueError("Report is outside the input bundle")
        if sha256(report_path) != item["report_sha256"]:
            raise ValueError(f"Report bytes changed: {report_path.name}")
        report = json.loads(report_path.read_text())
        trace_path = (report_path.parent / report["trace_file"]).resolve()
        if not trace_path.is_relative_to(root.resolve()):
            raise ValueError("Trace is outside the input bundle")
        if sha256(trace_path) != report["trace_file_sha256"]:
            raise ValueError(f"Trace bytes changed: {trace_path.name}")
        if report["archive_sha256"] != current["sha256"]:
            raise ValueError("Mixed candidate archives")
        game = report["game"]
        if game["status"] != "complete":
            raise ValueError("This analysis expects retained completed games")
        records = json.loads(gzip.decompress(trace_path.read_bytes()))
        own = [row for row in records if row["seat"] == game["candidate_seat"]]
        if [row["step"] for row in own] != list(range(game["steps"])):
            raise ValueError("Missing, duplicate, or out-of-order own observations")
        counts: collections.Counter = collections.Counter()
        noops, drops = [], []
        terminal = None
        for row in own:
            if row["observation"]["step"] != row["step"] or row["observation"]["player"] != row["seat"]:
                raise ValueError("Observation identity mismatch")
            audited = audit_action(mechanics, row["observation"], row["response"]["action"], row["configuration"])
            counts.update(audited["harvest_counts"])
            noops.extend(audited["noops"])
            drops.extend(audited["drop_losses"])
            if audited["terminal"] is not None:
                terminal = audited["terminal"]
        out = {"opponent": game["opponent"], "seed": game["seed"], "candidate_seat": game["candidate_seat"], "margin": game["scores"][game["candidate_seat"]] - game["scores"][1 - game["candidate_seat"]], "report_sha256": sha256(report_path), "trace_sha256": sha256(trace_path), "own_observations": len(own), "harvest_counts": dict(counts), "harvest_noops": noops, "drop_losses": drops, "terminal": terminal}
        results.append(out)
        print(json.dumps({k: out[k] for k in ("opponent", "seed", "candidate_seat", "harvest_counts")} | {"drop_loss_events": len(drops), "terminal_unoffered": terminal["unoffered_shed"] if terminal else None}), flush=True)
    total: collections.Counter = collections.Counter()
    lost: collections.Counter = collections.Counter()
    for game in results:
        total.update(game["harvest_counts"])
        for event in game["drop_losses"]:
            lost.update(event["lost"])
    result = {"scope": "Offline deterministic unit-phase diagnostics from existing completed DEVELOPMENT games. Zero new full games and zero policy calls. No demonstrated policy improvement.", "input_operation": summary["operation"], "archive_sha256": current["sha256"], "mechanics_sha256": sha256(mechanics_path), "games_read": len(results), "own_observations": sum(g["own_observations"] for g in results), "harvest_counts": dict(total), "drop_lost_products": dict(lost), "games": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    audit_bundle(args.bundle_dir, args.output, args.limit)


if __name__ == "__main__":
    main()
