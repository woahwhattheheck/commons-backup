# SPDX-License-Identifier: Apache-2.0
"""Validate E20 domain repair against exact original source and official markets.

Requires explicit files, never network access or legacy materialization:
  python -B check_v4_e20_input_domain_engine.py --engine /path/kaggriculture.py \
      --baseline /path/e20-before.py --helper /path/e20_hire_guard.py

The original source is Git blob cd497140d188794d610d3ae387de8758ecbd0765.
The engine is Git blob 3c202c7ee921da239356789e266b694635103fc4.
Only the unused external seed-resolver import is replaced by a failing sentinel.
This is market-phase compatibility, not full games or an economic promotion.
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

HELPER_BLOB = "9aaba92c5888df854f309b7d4a515ec1bf82020c"
BASELINE_BLOB = "cd497140d188794d610d3ae387de8758ecbd0765"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SCHEMA_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"


class CheckError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise CheckError(message)


def read_exact(path, expected):
    require(stat.S_ISREG(path.lstat().st_mode), "not a regular file: " + str(path))
    data = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    require(actual == expected, "source pin mismatch: " + str(path))
    return data


def load_helper(source, name):
    scope = {"__name__": name}
    exec(compile(source, name + ".py", "exec"), scope)
    return scope["apply_hire_guard"]


def load_engine(source, path):
    require(hashlib.sha256(source).hexdigest() == ENGINE_SHA256, "engine sha256 mismatch")
    tree = ast.parse(source, filename=str(path))
    omitted = []
    body = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "kaggle_environments.utils":
            require(node.level == 0 and len(node.names) == 1
                    and node.names[0].name == "resolve_episode_seed"
                    and node.names[0].asname is None, "unexpected external import")
            omitted.append(node)
        else:
            body.append(node)
    require(len(omitted) == 1, "missing or duplicate seed resolver import")
    tree.body = body

    def unused_seed_resolver(*args, **kwargs):
        raise CheckError("unexpected episode initialization")

    scope = {"__name__": "pinned_official_e20_engine", "__file__": str(path),
             "resolve_episode_seed": unused_seed_resolver}
    exec(compile(tree, str(path), "exec"), scope)
    return scope


def initial_state(engine, seat, hires):
    farms = [engine["_new_farm"](10, 10000) for _ in range(2)]
    private = [engine["_new_private"]() for _ in range(2)]
    for bag in private:
        bag["shed"].update(WHEAT=12, WOOL=8)
    for _ in range(hires):
        engine["_do_hire"](farms[seat], private[seat], 10)
    return farms, private, engine["_new_market"]()


def market_poststate(engine, initial, action, seat, config):
    farms, private, market = deepcopy(initial)
    rival = {"market": [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "WOOL", 2], ["HIRE"]]}
    state = [SimpleNamespace(
        observation=SimpleNamespace(farms=farms, market=market, private=private[i]),
        action=deepcopy(action if i == seat else rival)) for i in range(2)]
    engine["_process_market"](state, SimpleNamespace(configuration=config))
    return farms, private, market


def verify(revised, baseline, engine):
    rows = ([], ["HIRE"], ["SELL", "WHEAT", 2], ["BUY_SEED", "CARROT", 1])
    cases = activations = 0
    for layout, cap, budgets, seat in product(
            product(rows, repeat=3), (-2, 0, 1, 2, 3, 10),
            ((0, 0), (1, 0), (3, 1), (3, 3)), (0, 1)):
        max_hires, hires = budgets
        initial = initial_state(engine, seat, hires)
        obs = {"step": 100, "player": seat, "farms": initial[0]}
        action = {"farmer": ["PASS"], "hands": [["PASS"]] * hires,
                  "market": deepcopy(list(layout))}
        cfg = {"episodeSteps": 720, "maxMarketOrdersPerTurn": cap,
               "e20_max_hires_per_day": max_hires, "e20_min_unwatered_crops": 3}
        before = deepcopy((obs, action, cfg))
        actual, report = revised(obs, action, cfg, enabled=True)
        expected, old_report = baseline(obs, action, cfg, enabled=True)
        require(actual == expected and report == old_report,
                "valid official-farm behavior differs at case " + str(cases))
        require((actual is not action) == report["changed"], "no-op identity mismatch")
        require((obs, action, cfg) == before, "input mutation")
        require(market_poststate(engine, initial, actual, seat, cfg)
                == market_poststate(engine, initial, expected, seat, cfg),
                "official market poststate mismatch at case " + str(cases))
        activations += int(report["changed"])
        cases += 1
    require(cases == 3072 and activations > 0, "empty or incomplete matrix")

    demand_cases = 0
    for seat, demand, watered in product((0, 1), (0, 1, 3, 5), (False, True)):
        initial = initial_state(engine, seat, 3)
        for x in range(demand):
            initial[0][seat]["tiles"][0][x] = {"kind": "PLANT", "watered_today": watered}
        obs = {"step": 100, "player": seat, "farms": initial[0]}
        action = {"market": [["HIRE"], [], ["HIRE"]]}
        cfg = {"e20_max_hires_per_day": 3, "e20_min_unwatered_crops": 3}
        new_action, new_report = revised(obs, action, cfg, enabled=True)
        old_action, old_report = baseline(obs, action, cfg, enabled=True)
        require((new_action, new_report) == (old_action, old_report), "demand mismatch")
        require((new_action is action) == (old_action is action), "demand identity mismatch")
        demand_cases += 1
    return {"result": "PASS", "paired_market_cases": cases,
            "official_market_executions": 2 * cases, "activations": activations,
            "official_board_demand_cases": demand_cases, "seats": [0, 1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    args = parser.parse_args()
    try:
        helper = read_exact(args.helper, HELPER_BLOB)
        baseline = read_exact(args.baseline, BASELINE_BLOB)
        engine_source = read_exact(args.engine, ENGINE_BLOB)
        schema_path = args.engine.parent / "kaggriculture.json"
        schema_source = read_exact(schema_path, ENGINE_SCHEMA_BLOB)
        result = verify(load_helper(helper, "e20_revised"),
                        load_helper(baseline, "e20_baseline"),
                        load_engine(engine_source, args.engine))
        require(args.helper.read_bytes() == helper and args.baseline.read_bytes() == baseline
                and args.engine.read_bytes() == engine_source
                and schema_path.read_bytes() == schema_source, "input files changed")
        result.update(schema="titan.v4.e20.input-domain-engine.v1", helper_blob=HELPER_BLOB,
                      baseline_blob=BASELINE_BLOB, engine_blob=ENGINE_BLOB,
                      engine_sha256=ENGINE_SHA256, engine_schema_blob=ENGINE_SCHEMA_BLOB,
                      input_files_unchanged=True,
                      scope="official market phase and farm schema; no full games or promotion")
    except (CheckError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"result": "FAIL", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
