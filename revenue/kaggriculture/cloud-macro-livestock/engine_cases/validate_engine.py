"""Differential validation against real pinned engine helpers, not a mock game.

The local artifact's peer/evaluate.py can be supplied as --loader when the
normal repository loader is unavailable. All engine bytes are checked BEFORE
calling that existing loader, so missing source never triggers its downloader.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time

from livestock_ledger import ANIMALS, ENGINE_REF, ServiceAction as A, project_calendar, purchase_checkpoint

ENGINE_BLOBS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}


def load_engine(directory: Path, loader_path: Path):
    sources = {}
    for name, expected in ENGINE_BLOBS.items():
        data = (directory / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != expected:
            raise ValueError(f"Pinned engine bytes differ: {name}: {blob}")
        sources[name] = {"git_blob": blob, "sha256": hashlib.sha256(data).hexdigest()}
    spec = importlib.util.spec_from_file_location("t02_existing_loader", loader_path)
    if spec is None or spec.loader is None:
        raise ValueError("Could not load the existing evaluator")
    loader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loader
    spec.loader.exec_module(loader)
    if loader.ENGINE_REF != ENGINE_REF:
        raise ValueError("Loader references a different engine")
    engine, _ = loader.get_engine(directory)
    return engine, sources


def reference_calendar(engine, species, placement, actions, last):
    """Replay each explicit visit using the engine's own unit/daily functions."""
    calendar = sorted(actions, key=lambda event: (event.step, event.unit))
    count = 1 + max((event.unit for event in calendar), default=0)
    farm = engine._new_farm(10, 1000)
    farm["farmer"] = [4, 4]
    farm["hands"] = [[4, 4] for _ in range(count - 1)]
    farm["tiles"][4][4] = engine._new_animal(species, placement // 24)
    private = engine._new_private()
    private["inventories"] = [{} for _ in range(count)]
    by_step = {}
    for event in calendar:
        by_step.setdefault(event.step, []).append(event)
    trace, harvests, feeds, fertilizer, actions_out = [], [], [], [], []
    escape = None
    product = engine.ANIMALS[species]["product"]
    for step in range(placement, last + 1):
        for event in by_step.get(step, []):
            inv = private["inventories"][event.unit]
            if event.op == "FEED":
                # The explicit available-inventory condition is a scenario input,
                # not a simulated free purchase or an assumption about the shed.
                inv["WHEAT"] = event.wheat_available
            before_tile = copy.deepcopy(farm["tiles"][4][4])
            before_inv = dict(inv)
            engine._apply_unit_action(farm, private, event.unit, [event.op], 10, step // 24, 24)
            tile = farm["tiles"][4][4]
            n = 0
            if event.op == "HARVEST":
                n = inv.get(product, 0) - before_inv.get(product, 0)
                if n:
                    harvests.append({"step": step, "unit": event.unit, "product": product, "units": n})
            elif event.op == "FEED":
                n = before_inv.get("WHEAT", 0) - inv.get("WHEAT", 0)
                if n:
                    feeds.append({"step": step, "unit": event.unit, "units": n})
            elif event.op == "COLLECT_FERTILIZER":
                n = inv.get("FERTILIZER", 0) - before_inv.get("FERTILIZER", 0)
                if n:
                    fertilizer.append({"step": step, "unit": event.unit, "units": n})
            actions_out.append({"step": step, "unit": event.unit, "op": event.op, "applied": tile != before_tile, "units": n})
            trace.append({"step": step, "phase": "action", "unit": event.unit, "tile": copy.deepcopy(tile)})
        if (step + 1) % 24 == 0 and "animal" in farm["tiles"][4][4]:
            engine._daily_refresh_animals(farm, step // 24)
            tile = farm["tiles"][4][4]
            if "animal" not in tile:
                escape = step
            trace.append({"step": step, "phase": "daily", "tile": copy.deepcopy(tile)})
    return {"trace": trace, "harvest_receipts": harvests, "feed_receipts": feeds,
            "fertilizer_receipts": fertilizer, "action_results": actions_out,
            "terminal_tile": farm["tiles"][4][4], "escape_step": escape}


def fixtures():
    # These are deterministic local fixture selectors, NOT game/evaluation seeds.
    for placement in (0, 23, 24, 47, 168, 576, 695, 718):
        for mode in ("fed_cared", "fed_no_care", "alternating_feed", "no_feed", "late_harvest"):
            events = []
            for step in range(placement, 719):
                hour, day = step % 24, step // 24
                if hour == 2 and mode != "no_feed":
                    events.append(A(step, "FEED", wheat_available=int(mode != "alternating_feed" or day % 2 == 0)))
                if hour == 3 and mode != "fed_no_care":
                    events.append(A(step, "CARE"))
                if hour == (22 if mode == "late_harvest" else 4):
                    events.append(A(step, "HARVEST"))
                if hour == 5:
                    events.append(A(step, "COLLECT_FERTILIZER"))
            yield f"placement-{placement}-{mode}", placement, events
    rng = random.Random(0x4D455341)
    for case in range(128):
        placement = rng.randrange(0, 700)
        events = []
        for step in range(placement, 719):
            if rng.random() < .13:
                for unit in range(rng.randrange(1, 4)):
                    events.append(A(step, rng.choice(("FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER", "PASS")),
                                    unit=unit, wheat_available=rng.randrange(0, 3)))
        yield f"generated-{case:03d}", placement, events


def run(engine, sources, loader_path):
    for species, local in ANIMALS.items():
        assert all(engine.ANIMALS[species][key] == value for key, value in local.items())
    rows = []
    total_transitions = 0
    timings = []
    for label, placement, calendar in fixtures():
        for species in ANIMALS:
            started = time.perf_counter()
            actual = project_calendar(species, placement, calendar, include_trace=True)
            timings.append(time.perf_counter() - started)
            reference = reference_calendar(engine, species, placement, calendar, 718)
            for key, expected in reference.items():
                if actual[key] != expected:
                    raise AssertionError(f"{label}/{species}/{key}: differential mismatch")
            total_transitions += len(reference["trace"])
            rows.append({"fixture": label, "species": species, "placement_step": placement,
                         "transitions": len(reference["trace"]), "harvested_units": actual["harvested_units"],
                         "feed_units": actual["feed_units"], "escape_step": actual["escape_step"],
                         "trace_sha256": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()})
    purchase_cases = 0
    for cash in (0, 399, 400, 499, 500, 550, 1000):
        for stock in (0, 99, 100, 101):
            check = purchase_checkpoint(cash, stock)
            for branch, species in (("baseline", "COW"), ("candidate", "SHEEP")):
                farm, private, market = engine._new_farm(10, cash), engine._new_private(), engine._new_market()
                private["shed"] = {"WHEAT": stock}
                success = engine._commit_unit("BUY_ANIMAL", species, engine.ANIMALS[species]["cost"], farm, private, market)
                assert check[branch]["engine_purchase_possible"] == success
                assert check[branch]["cash_after_if_purchased"] == (farm["money"] if success else None)
                purchase_cases += 1
    here = Path(__file__).parent
    return {"schema": "titan.livestock-engine-validation.v1", "engine_ref": ENGINE_REF,
            "engine_sources": sources, "loader_sha256": hashlib.sha256(loader_path.read_bytes()).hexdigest(),
            "source_sha256": {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
                              for name in ("livestock_ledger.py", "test_livestock_ledger.py", "validate_engine.py")},
            "differential_cases": len(rows), "compared_transitions": total_transitions,
            "purchase_cases": purchase_cases, "mismatches": 0,
            "projection_seconds": {"maximum": max(timings), "mean": sum(timings) / len(timings)},
            "method": "Exact official helper calls on controlled legal-visit scenarios; no game panel, outcome, cash gain or policy promotion is claimed.",
            "game_seeds_used": [], "rows": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-dir", type=Path, required=True)
    p.add_argument("--loader", type=Path, default=Path(__file__).resolve().parents[2] / "20260907-offline-agent" / "evaluate.py")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    engine, sources = load_engine(args.engine_dir, args.loader)
    report = run(engine, sources, args.loader)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
