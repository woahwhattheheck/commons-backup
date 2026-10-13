# SPDX-License-Identifier: Apache-2.0
"""Fail-closed source and execution-custody audit for SOL-AMPLIFIER."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
OPERATION = "titan-v3-full-queue-same-product-sell-growth-20260909-sol-amplifier-01"
EXPECTED_PATCH_BLOB = "f1803dafb558745376f28d3c9e005c4688ff4452"
EXPECTED_EXECUTION_BLOBS = {
    "growth_patch": EXPECTED_PATCH_BLOB,
    "frozen_selected": "fc7baf5c179818a55037f6a61d92984d81d1a21c",
    "main": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "config": "3a3bef83899d3010fad623b628d9e95d9978111b",
    "build_integrated": "05994d946885ff0fe2a2ce77439fd335174900aa",
    "source_manifest": "f5d8a9f1338dbef5396de8f23262453b0f70e832",
}
EXPECTED_BLOBS = {
    "v1": "cbc502a92fe9d790cfaf763f6990d1057bc9b82d",
    "v2": "7c068b7078c3d7c09bb3836590ad42b0af934cdf",
    "frozen_selected": "fc7baf5c179818a55037f6a61d92984d81d1a21c",
    "main": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "config": "3a3bef83899d3010fad623b628d9e95d9978111b",
    "build_integrated": "05994d946885ff0fe2a2ce77439fd335174900aa",
    "source_manifest": "f5d8a9f1338dbef5396de8f23262453b0f70e832",
    "observed_clone": "f810d53193d3035655a36c21021e18ba1d415916",
}
QUEUE_NEEDLE = "if q>offered:return False"
CAP_NEEDLE = "q=min(max(0,int(o[2])),remaining.get(item,0),max(0,available.get(item,0)))"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _nested_feasible_has_exact_gate(text: str, class_name: str) -> bool:
    tree = ast.parse(text)
    functions = [
        node
        for top in tree.body
        if isinstance(top, ast.ClassDef) and top.name == class_name
        for method in top.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and method.name in ("act", "transform")
        for node in ast.walk(method)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "feasible"
    ]
    if len(functions) != 1:
        return False
    gates = []
    for node in ast.walk(functions[0]):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "q"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Gt)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Name)
            and test.comparators[0].id == "offered"
        ):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and value.value is False:
                gates.append(node)
    return len(gates) == 1


def _one_function(text: str, name: str) -> bool:
    tree = ast.parse(text)
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in ast.walk(tree)
    ) == 1


def build_report(lab: Path = LAB) -> dict[str, Any]:
    root = lab.parents[2]
    paths = {
        "v1": lab / "runtime/variants/v1/scheduler.py",
        "v2": lab / "runtime/variants/v2/scheduler.py",
        "frozen_selected": lab / "frozen_selected.py",
        "main": lab / "main.py",
        "titan_runtime": lab / "titan_runtime.py",
        "config": lab / "TITAN-CONFIG.json",
        "build_integrated": lab / "build_integrated.py",
        "source_manifest": lab / "runtime/integrated-selected/CURRENT-SOURCE.json",
        "observed_clone": lab / "../cloud-runtime-pulse/observed_clone.py",
        "growth_patch": HERE / "growth_patch.py",
        "candidate": HERE / "candidate.py",
        "panel_adapter": HERE / "run_panel.py",
        "action_tests": HERE / "test_action_bound_panel.py",
        "panel_source": HERE.parent / "v3-l02-ledger-tranche/run_panel.py",
        "evaluator_source": root / "revenue/kaggriculture/cloud-eval/evaluate.py",
        "workflow": root / ".github/workflows/titan-v3-full-queue-sell-growth-sol-amplifier.yml",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing source: " + ", ".join(missing))
    blobs = {name: path.read_bytes() for name, path in paths.items()}
    text = {name: data.decode("utf-8") for name, data in blobs.items()}
    source_manifest = json.loads(text["source_manifest"])
    source_runtime = source_manifest.get("runtime", {})
    checks = {
        "exact_historical_and_current_blobs": all(
            git_blob_sha1(blobs[name]) == expected
            for name, expected in EXPECTED_BLOBS.items()
        ),
        "v1_has_no_saturated_offered_gate": QUEUE_NEEDLE not in text["v1"],
        "v1_grows_first_inherited_same_product_row": (
            text["v1"].count("if item not in used:") == 1
            and text["v1"].count("q=current[item]") == 1
        ),
        "v2_has_exact_saturated_offered_gate": (
            text["v2"].count(QUEUE_NEEDLE) == 1
            and _nested_feasible_has_exact_gate(text["v2"], "SellScheduler")
        ),
        "v2_caps_inherited_sell_to_original_quantity": (
            text["v2"].count(CAP_NEEDLE) == 1
        ),
        "current_selected_has_exact_saturated_offered_gate": (
            text["frozen_selected"].count(QUEUE_NEEDLE) == 1
            and _nested_feasible_has_exact_gate(text["frozen_selected"], "FrozenSelected")
        ),
        "current_selected_has_one_materializer_with_quantity_cap": (
            _one_function(text["frozen_selected"], "materialize_sales")
            and text["frozen_selected"].count(CAP_NEEDLE) == 1
        ),
        "actual_runtime_imports_frozen_selected_at_lazy_init": (
            text["titan_runtime"].count("from frozen_selected import FrozenSelected") == 1
            and text["titan_runtime"].count("self.consumer = FrozenSelected()") == 1
        ),
        "current_config_selects_frozen_consumer": (
            json.loads(text["config"]).get("consumer") == "frozen"
        ),
        "candidate_delegates_canonical_outer_agent": (
            text["candidate"].count("return _CANONICAL.agent(observation, configuration)") == 1
            and "instance.act(observation" not in text["candidate"]
        ),
        "candidate_attaches_inside_canonical_new_instance": (
            text["candidate"].count("instance = _ORIGINAL_NEW_INSTANCE(root, feature_data)") == 1
            and text["candidate"].count("**attach(instance, frozen_selected)") == 1
            and text["candidate"].count('"entry_files": dict(_ENTRY_FILES)') == 1
            and text["candidate"].count('"source_closure": dict(_SOURCE_CLOSURE)') == 1
        ),
        "candidate_self_verifies_exact_execution_closure_before_import": (
            all(
                git_blob_sha1(blobs[name]) == expected
                and expected in text["candidate"]
                for name, expected in EXPECTED_EXECUTION_BLOBS.items()
            )
            and text["candidate"].count("_ENTRY_FILES = _verify_entry_files()") == 1
            and text["candidate"].count(
                "_SOURCE_CLOSURE = _verify_and_install_source_roots()"
            ) == 1
            and text["candidate"].index("_ENTRY_FILES = _verify_entry_files()")
                < text["candidate"].index(
                    "_SOURCE_CLOSURE = _verify_and_install_source_roots()"
                )
                < text["candidate"].index("_GROWTH_PATCH = _load_private(")
            and text["candidate"].count("cursor.is_symlink()") == 1
            and text["candidate"].count("relative = lexical.relative_to(REPOSITORY)") == 1
        ),
        "candidate_derives_and_verifies_canonical_source_roots": (
            text["build_integrated"].count(
                "mapping['observed_clone.py']='../cloud-runtime-pulse/observed_clone.py'"
            ) == 1
            and isinstance(source_runtime.get("observed_clone.py"), dict)
            and source_runtime["observed_clone.py"].get("source_path")
                == "../cloud-runtime-pulse/observed_clone.py"
            and source_runtime["observed_clone.py"].get("bytes")
                == len(blobs["observed_clone"])
            and source_runtime["observed_clone.py"].get("sha256")
                == sha256_bytes(blobs["observed_clone"])
            and text["candidate"].count("mapping = builder.source_files()") == 1
            and text["candidate"].count("if set(mapping) != set(runtime):") == 1
            and text["candidate"].count(
                'record.get("sha256") != digest'
            ) == 1
            and text["candidate"].count(
                '"observed_clone",'
            ) >= 1
            and text["candidate"].count("importlib.util.find_spec(module_name)") == 1
            and text["candidate"].count("preloaded module collision") == 1
            and text["candidate"].count("root module resolves outside closure") == 1
        ),
        "candidate_private_loaders_do_not_publish_global_aliases": (
            text["candidate"].count("def _load_private") == 1
            and text["candidate"].count("spec.loader.exec_module(module)") == 1
            and "sys.modules[" not in text["candidate"]
            and text["candidate"].count("sys.modules.get(module_name)") == 1
        ),
        "patch_reuses_exact_transform_code_with_private_globals": (
            text["growth_patch"].count("base_transform.__code__") == 1
            and text["growth_patch"].count('"optimize_lot": _build_optimizer') == 1
            and text["growth_patch"].count('"materialize_sales": _build_materializer') == 1
        ),
        "patch_is_exact_length_and_existing_positive_row_only": (
            text["growth_patch"].count("len(orders) != limit") >= 2
            and text["growth_patch"].count("offered <= 0") == 1
            and text["growth_patch"].count("if not matches or desired <= inherited") == 1
        ),
        "initializer_uses_private_import_without_global_mutation": (
            text["growth_patch"].count('if level == 0 and name == "frozen_selected"') == 1
            and text["growth_patch"].count('{"__builtins__": private_builtins}') == 1
            and "frozen_selected_module.FrozenSelected =" not in text["growth_patch"]
            and "sys.modules[" not in text["growth_patch"]
            and "sys.modules." not in text["growth_patch"]
        ),
        "panel_instruments_candidate_actions_before_interpreter": (
            text["panel_adapter"].count("def instrument_candidate_actions") == 1
            and text["panel_adapter"].count(
                'candidate_actions.update(encoded({"step": step, "action": actions[candidate_seat]}))'
            ) == 1
            and text["panel_adapter"].count('result["candidate_action_count"] += 1') == 1
            and text["panel_adapter"].count(
                'result["candidate_action_sha256"] = candidate_actions.hexdigest()'
            ) == 1
            and text["evaluator_source"].count("actors, trace = [], hashlib.sha256()") == 1
            and text["evaluator_source"].count(
                '                actions.append(response["action"])\n            for seat in range(2):'
            ) == 1
        ),
        "panel_requires_literal_action_bound_own_cash_grid": (
            all(value in text["panel_adapter"] for value in (
                "EXPECTED_EPISODE_STEPS = 720",
                "EXPECTED_ACTION_COUNT = 719",
                'EXPECTED_OPPONENTS = ("arlene", "apex", "public_bt12", "v1")',
                "literal_complete_grid",
                "candidate_actions_activated",
                "every_score_change_action_bound",
                "positive_global_own_cash",
                "no_opponent_mean_own_regression",
                "no_seat_mean_own_regression",
            ))
            and text["panel_adapter"].count("runner.patch_evaluator = patch_evaluator") == 1
            and text["panel_adapter"].count("runner.pair_games = pair_games") == 1
            and text["panel_adapter"].count("runner.verdict = verdict") == 1
        ),
        "workflow_executes_both_contract_suites_and_exact_grid": (
            "test_full_queue_sell_growth.py test_action_bound_panel.py" in text["workflow"]
            and "2611092201,2611092203,2611092205,2611092207" in text["workflow"]
            and "arlene,apex,public_bt12,v1" in text["workflow"]
            and "Run 32-cell action-bound official-engine screen" in text["workflow"]
        ),
        "canonical_sources_are_read_only_targets": all(
            path.parent != HERE for name, path in paths.items()
            if name in EXPECTED_BLOBS
        ),
    }
    return {
        "schema_version": 1,
        "operation": OPERATION,
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "claim": {
            "historical_v1_saturated_growth": True,
            "historical_v2_saturated_growth": False,
            "current_selected_saturated_growth": False,
            "candidate_changes": [
                "capacity admission for exact-limit queues with a positive inherited same-product SELL row",
                "in-place quantity expansion of that inherited row",
            ],
            "new_slot_created": False,
            "order_index_changed": False,
            "canonical_files_modified": False,
            "candidate_action_receipt": "719 pre-interpreter actions per complete cell",
            "score_gate": "positive global own cash with no opponent or seat mean regression",
        },
        "checks": checks,
        "sources": {
            name: {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(blobs[name]),
                "git_blob_sha1": git_blob_sha1(blobs[name]),
                "sha256": sha256_bytes(blobs[name]),
            }
            for name, path in paths.items()
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "checks": report["checks"]}, sort_keys=True))
    return 0 if report["decision"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
