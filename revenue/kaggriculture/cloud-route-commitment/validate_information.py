# SPDX-License-Identifier: Apache-2.0
"""Exercise the information-window consumer against the shared inspector and engine.

No policy actions or full games are run. Output is one JSON report on stdout.
Input modules are explicit trusted local project dependencies, not downloaded.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

from information import future_shop_reveals, from_commitment

BOUNDARY_SHA = "87e42af7ccc3a6db4a71d0db140c05b6bed4a7affc85df7b720857bb143338df"
ARLENE_SHA = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_SHA = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}
LOADER_SHA = "cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e"


def identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


def require_source(path, expected):
    record = identity(path)
    if record["sha256"] != expected:
        raise ValueError(f"Source differs from this validation's recorded input: {Path(path).name}")
    return record


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def function_lines(path, name):
    tree = ast.parse(Path(path).read_text())
    item = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return [item.lineno, item.end_lineno]


def validate(arlene_path, engine_cache, loader_path, boundary_path):
    arlene_path, engine_cache, loader_path = map(Path, (arlene_path, engine_cache, loader_path))
    source = {"boundary": require_source(boundary_path, BOUNDARY_SHA), "arlene": require_source(arlene_path, ARLENE_SHA),
              "loader": require_source(loader_path, LOADER_SHA),
              "engine_ref": ENGINE_REF,
              "engine": {n: require_source(engine_cache/n, h) for n, h in ENGINE_SHA.items()}}
    # The old loader has a download fallback, so make any such use an error here.
    with patch("urllib.request.urlopen", side_effect=AssertionError("Validation is offline")) as net:
        arlene = load_module("commitment_original_arlene", arlene_path)
        shared = load_module("commitment_shared_boundary", boundary_path)
        loader = load_module("commitment_original_loader", loader_path)
        engine, engine_hashes = loader.get_engine(engine_cache)
        if engine_hashes != ENGINE_SHA:
            raise AssertionError("Loaded engine differs")
        original = arlene.Agent()  # A fresh test fixture, never a live controller.
        before = json.dumps(original.R, sort_keys=True, separators=(",", ":"))
        joined = []
        cases = ((arlene.MAIN, arlene.YARN, 215, 2, True),
                 (arlene.MAIN, arlene.YARN, 216, 3, False),
                 (arlene.MAIN, arlene.YARN, 226, 3, False),
                 (arlene.MAIN, arlene.YARN, 227, 3, False),
                 (arlene.MAIN, arlene.MILK_GLUT, 433, 6, True),
                 (arlene.MAIN, arlene.MILK_GLUT, 577, 7, False),
                 (arlene.YARN, arlene.YARN, 226, 3, False),
                 (arlene.YARN, arlene.YARN_CARROT, 359, 4, True),
                 (arlene.YARN, arlene.YARN_CARROT, 360, 5, False))
        with patch.object(arlene.Agent, "act", side_effect=AssertionError("No policy actions")) as act:
            for current, target, now, shops, expected in cases:
                original.cur = current
                # One existing predicate invocation, not another prefix implementation.
                report = shared.inspect_commitment(original, target, now)
                result = from_commitment(report, shop_count=shops)
                if result["can_wait_for_next_reveal"] is not expected:
                    raise AssertionError((current, target, now, result))
                if original.cur != current:
                    raise AssertionError("Inspection changed the current route")
                joined.append({key: result[key] for key in
                    ("now", "last_compatible_decision", "compatible_now", "next_reveal_decision",
                     "next_reveal_delay", "can_wait_for_next_reveal", "reveals_while_compatible")}
                    | {"current_route": current, "target_route": target})
            action_calls = act.call_count
        after = json.dumps(original.R, sort_keys=True, separators=(",", ":"))
        if before != after:
            raise AssertionError("Route inputs changed")

        counts = {"initializations": 0, "end_of_day_calls": 0, "interpreter_boundary_calls": 0}
        def fixture(overrides=None):
            cfg = loader.Struct()
            for key, value in engine.specification["configuration"].items():
                cfg[key] = value.get("default") if isinstance(value, dict) else value
            cfg.update(overrides or {})
            cfg.seed = 0  # Reproducible synthetic source fixture, not a gameplay panel.
            env = loader.Struct(configuration=cfg, done=False, info={})
            state = [loader.Struct(observation=loader.Struct(), action={}, status="ACTIVE", reward=0)
                     for _ in range(2)]
            engine.interpreter(state, env)
            counts["initializations"] += 1
            return state, env

        calendars = []
        for label, overrides, initial_shops in (
            ("default", {}, 0),
            ("custom_12_turn_2_day_120_step", {"turnsPerDay": 12, "townShopUnlockInterval": 2,
                                              "episodeSteps": 120}, 0),
            ("already_at_instance_cap", {}, engine.MAX_SHOP_INSTANCES),
        ):
            state, env = fixture(overrides)
            town = state[0].observation.town
            # Explicit synthetic public count, including the saturation witness.
            town["unlocked_shops"] = [sorted(engine.SHOPS)[0]] * initial_shops
            cfg = env.configuration
            expected = future_shop_reveals(0, shop_count=initial_shops, turns_per_day=cfg.turnsPerDay,
                                          unlock_interval_days=cfg.townShopUnlockInterval,
                                          max_instances=engine.MAX_SHOP_INSTANCES,
                                          decision_count=cfg.episodeSteps-1)
            observed = []
            for day in range((cfg.episodeSteps-1)//cfg.turnsPerDay):
                prior = len(town["unlocked_shops"])
                engine._end_of_day(state, env, day)
                counts["end_of_day_calls"] += 1
                if len(town["unlocked_shops"]) > prior:
                    observed.append((day+1)*cfg.turnsPerDay)
            if tuple(observed) != expected:
                raise AssertionError((label, observed, expected))
            calendars.append({"label": label, "initial_shop_count": initial_shops,
                              "action_ready_reveal_decisions": observed, "matches": True})

        boundaries = []
        for step, initial_shops, increment in ((70, 0, 0), (71, 0, 1), (72, 1, 0), (287, 3, 1)):
            state, env = fixture()
            town = state[0].observation.town
            town["unlocked_shops"] = [sorted(engine.SHOPS)[0]] * initial_shops
            state[0].observation.step = step
            engine.interpreter(state, env)
            counts["interpreter_boundary_calls"] += 1
            own = len(state[0].observation.town["unlocked_shops"])
            other = len(state[1].observation.town["unlocked_shops"])
            if own != initial_shops + increment or other != own:
                raise AssertionError((step, own, other))
            if (state[0].observation.day*env.configuration.turnsPerDay+state[0].observation.hour) != step+1:
                raise AssertionError("Wrong action-ready boundary")
            boundaries.append({"previous_action_step": step, "next_decision": step+1,
                               "added_shop_instances": increment, "both_seats_same_public_count": True})
        network_calls = net.call_count
    # Confirm none of the source files were rewritten by imports or fixtures.
    require_source(arlene_path, ARLENE_SHA)
    require_source(loader_path, LOADER_SHA)
    for name, sha in ENGINE_SHA.items():
        require_source(engine_cache/name, sha)
    source["switch_ok_lines"] = function_lines(arlene_path, "_switch_ok")
    source["end_of_day_lines"] = function_lines(engine_cache/"kaggriculture.py", "_end_of_day")
    source["implementation"] = identity(Path(__file__).with_name("information.py"))
    source["pure_tests"] = identity(Path(__file__).with_name("test_information.py"))
    source["validator"] = identity(__file__)
    return {"schema": "route-information-validation-v1", "status": "PASS", "sources": source,
            "joined_boundary_cases": joined, "actual_shared_inspector_calls": len(joined),
            "route_input_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "route_inputs_unchanged": True, "calendars": calendars, "boundaries": boundaries,
            "engine_calls": counts, "policy_action_calls": action_calls,
            "network_calls": network_calls, "full_games": 0, "new_game_seed_reservations": 0,
            "limits": ["Consumes BRIDGE's inspector; no duplicate prefix implementation.",
                       "Structural waiting opportunity is not physical/economic feasibility.",
                       "Shop identities and future demand remain unknown.",
                       "Synthetic engine boundaries are not reached-game or held-out evidence.",
                       "No producer, selector, scorer, or default policy was changed."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arlene", required=True)
    parser.add_argument("--engine-cache", required=True)
    parser.add_argument("--loader", required=True)
    parser.add_argument("--boundary", required=True, help="BRIDGE commitment_window.py")
    args = parser.parse_args(argv)
    try:
        result = validate(args.arlene, args.engine_cache, args.loader, args.boundary)
    except (ValueError, OSError, AssertionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
