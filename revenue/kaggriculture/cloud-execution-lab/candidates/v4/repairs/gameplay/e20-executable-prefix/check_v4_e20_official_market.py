# SPDX-License-Identifier: Apache-2.0
"""Read-only E20 recovery check against the pinned official market phase.

Run on an explicit materialized package containing the reviewed E20 repair:
    python check_v4_e20_official_market.py --package-tree /path/to/package

This is not a full-game, current-V4-package, or economic-promotion gate. It
checks the exact reviewed E20 helper and the frozen official market interpreter,
including real HIRE costs, purchases, sales, raw order slots, and both seats.
No package files are written and no Kaggle installation is required.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
from itertools import product
import json
from pathlib import Path
import stat
from types import SimpleNamespace

E20_BLOB = "cd497140d188794d610d3ae387de8758ecbd0765"
PREDECESSOR_BLOB = "341eed454cae08cfeba31b5205a10263e50999d8"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
EXPECTED_CASES = 3072


class CheckError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CheckError(message)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def regular_bytes(path):
    require(stat.S_ISREG(path.lstat().st_mode), "not a regular file: " + str(path))
    return path.read_bytes()


def package_snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "package contains a symlink: " + str(path))
        if path.is_dir():
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(regular_bytes(path)).hexdigest()
    return result


def load_exact_sources(root):
    helper = root / "e20_hire_guard.py"
    source = regular_bytes(helper)
    require(git_blob(source) == E20_BLOB, "unreviewed E20 helper bytes")
    text = source.decode("utf-8")
    insertion = (
        "def _market_order_limit(config: Mapping[str, Any]) -> int:\n"
        "    try:\n"
        "        return max(1, int(config.get(\"maxMarketOrdersPerTurn\", 10)))\n"
        "    except (TypeError, ValueError):\n"
        "        return 10\n\n\n"
    )
    edits = (
        (insertion, ""),
        ("    market_order_limit = _market_order_limit(cfg)\n", ""),
        ("enumerate(raw_market[:market_order_limit])", "enumerate(raw_market)"),
    )
    predecessor = text
    for old, new in edits:
        require(predecessor.count(old) == 1, "nonunique predecessor reconstruction anchor")
        predecessor = predecessor.replace(old, new)
    require(git_blob(predecessor.encode("utf-8")) == PREDECESSOR_BLOB,
            "reconstructed predecessor is not the frozen source")
    new_ns = {"__name__": "e20_reviewed"}
    old_ns = {"__name__": "e20_predecessor"}
    exec(compile(text, str(helper), "exec"), new_ns)
    exec(compile(predecessor, "frozen_e20_predecessor.py", "exec"), old_ns)

    engine_path = root / "checks" / "reference" / "engine" / "kaggriculture.py"
    engine_source = regular_bytes(engine_path)
    require(hashlib.sha256(engine_source).hexdigest() == ENGINE_SHA256,
            "official interpreter pin mismatch")
    tree = ast.parse(engine_source, filename=str(engine_path))
    omitted = []
    body = []
    for node in tree.body:
        if (isinstance(node, ast.ImportFrom)
                and node.module == "kaggle_environments.utils"):
            require(node.level == 0 and len(node.names) == 1
                    and node.names[0].name == "resolve_episode_seed"
                    and node.names[0].asname is None,
                    "unexpected Kaggle import shape")
            omitted.append(node)
        else:
            body.append(node)
    require(len(omitted) == 1, "seed-resolver import must occur exactly once")
    tree.body = body

    def unused_seed_resolver(*args, **kwargs):
        raise CheckError("market-only check unexpectedly requested episode initialization")

    # The only omitted code is the unrelated episode-seed import. All official
    # market functions, parsing, constants, pricing and commits execute unchanged.
    engine = {"__name__": "pinned_official_market", "__file__": str(engine_path),
              "resolve_episode_seed": unused_seed_resolver}
    exec(compile(tree, str(engine_path), "exec"), engine)
    return new_ns["apply_hire_guard"], old_ns["apply_hire_guard"], engine


def initial_state(engine, own_seat, hires_today):
    farms = [engine["_new_farm"](10, 10000) for _ in range(2)]
    privates = [engine["_new_private"]() for _ in range(2)]
    for private in privates:
        private["shed"].update(WHEAT=12, WOOL=8)
    for _ in range(hires_today):
        engine["_do_hire"](farms[own_seat], privates[own_seat], 10)
    return farms, privates, engine["_new_market"]()


def execute_market(engine, initial, actions, config):
    farms, privates, market = deepcopy(initial)
    state = [SimpleNamespace(
        observation=SimpleNamespace(farms=farms, market=market, private=privates[seat]),
        action=deepcopy(actions[seat]),
    ) for seat in range(2)]
    engine["_process_market"](state, SimpleNamespace(configuration=config))
    return farms, privates, market


def verify(root):
    before_files = package_snapshot(root)
    revised, predecessor, engine = load_exact_sources(root)
    rows = ([], ["HIRE"], ["SELL", "WHEAT", 2], ["BUY_SEED", "CARROT", 1])
    cases = 0
    for layout in product(rows, repeat=3):
        for cap in (-2, 0, 1, 2, 3, 10):
            for max_hires, hires_today in ((0, 0), (1, 0), (3, 1), (3, 3)):
                for seat in (0, 1):
                    initial = initial_state(engine, seat, hires_today)
                    obs = {"step": 100, "player": seat, "farms": initial[0]}
                    action = {"farmer": ["PASS"], "hands": [["PASS"]] * hires_today,
                              "market": deepcopy(list(layout))}
                    config = {"episodeSteps": 720, "maxMarketOrdersPerTurn": cap,
                              "e20_max_hires_per_day": max_hires,
                              "e20_min_unwatered_crops": 3}
                    inputs_before = deepcopy((obs, action, config))
                    new_action, report = revised(obs, action, config, enabled=True)
                    old_action, _ = predecessor(obs, action, config, enabled=True)
                    limit = max(1, cap)
                    require(new_action["market"][:limit] == old_action["market"][:limit],
                            "repair changed an executable raw slot")
                    require(new_action["market"][limit:] == action["market"][limit:],
                            "repair modified the engine-inert tail")
                    require(len(new_action["market"]) == len(action["market"]),
                            "repair compacted raw slots")
                    require((obs, action, config) == inputs_before, "helper mutated an input")
                    require((new_action is not action) == report["changed"],
                            "no-op object identity disagrees with change report")
                    rival = {"market": [["BUY_PRODUCT", "WHEAT", 1],
                                        ["SELL", "WOOL", 2], ["HIRE"]]}
                    new_actions = [rival, rival]
                    old_actions = [rival, rival]
                    new_actions[seat] = new_action
                    old_actions[seat] = old_action
                    new_state = execute_market(engine, initial, new_actions, config)
                    old_state = execute_market(engine, initial, old_actions, config)
                    require(new_state == old_state,
                            "official market-phase poststate differs at case " + str(cases))
                    cases += 1
    require(cases == EXPECTED_CASES, "incomplete official market matrix")
    inert = {"market": [["HIRE"]]}
    out, report = revised(object(), inert, object(), enabled=False)
    require(out is inert and report["reason"] == "OFF", "disabled path is not exact identity")
    require(package_snapshot(root) == before_files, "check modified package files")
    return {"schema": "titan.v4.e20.official-market.v1", "result": "PASS",
            "scope": "exact E20 helper / official market phase only; not full games or V4 package promotion",
            "e20_blob": E20_BLOB, "predecessor_blob": PREDECESSOR_BLOB,
            "engine_sha256": ENGINE_SHA256, "paired_market_cases": cases,
            "official_market_executions": cases * 2, "seats": [0, 1],
            "package_unchanged": True, "package_files_observed": len(before_files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-tree", type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.package_tree.resolve(strict=True)
        require(root.is_dir(), "package tree is not a directory")
        result = verify(root)
    except (CheckError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
