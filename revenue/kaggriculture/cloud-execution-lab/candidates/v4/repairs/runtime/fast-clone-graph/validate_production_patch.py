#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound R04 clone proof, recovered into the one V4 line from #12431.

--self-test executes only the helper extracted from production.patch. The full
proof authenticates the checkout, copies the overlay to temporary storage, applies
the patch there, proves the exact native AST delta, and checks all frozen tapes.
No live overlay, configuration, or tape is written by this validator.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import itertools
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve()
V3 = HERE.parents[2]
OVERLAY = V3 / "overlay"
SOURCE = OVERLAY / "r04_full_router.py"
TAPES = OVERLAY / "r01_tapes.py"
PATCH = HERE.with_name("production.patch")
EXPECTED_BASE = "465f4263da1c98acf78889d67cdd21b61dbba145"
EXPECTED_SOURCE_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"
EXPECTED_TAPES_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
EXPECTED_PATHS = {
    ".github/workflows/titan-v31-r04-fast-clone-production-port.yml",
    "revenue/kaggriculture/cloud-execution-lab/candidates/v3/experiments/r04_fast_clone/production.patch",
    "revenue/kaggriculture/cloud-execution-lab/candidates/v3/experiments/r04_fast_clone/validate_production_patch.py",
}
HELPER_NAMES = {
    "_R04_JSON_SCALAR_TYPES", "_r04_is_fast_tape_action", "_r04_clone_tape_action",
}
EXPECTED_ACTIONS = 13 * 719
MIN_MEDIAN_SPEEDUP = 1.50


def require(condition, message):
    # Explicit checks stay active under python -O.
    if not condition:
        raise AssertionError(message)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def repo_root():
    for parent in (HERE.parent, *HERE.parents):
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("repository root not found")


def run(root, *args):
    return subprocess.run(args, cwd=root, text=True, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def validate_checkout_custody(root):
    expected = os.environ.get("TITAN_EXPECTED_HEAD_SHA", "").strip()
    require(bool(expected), "TITAN_EXPECTED_HEAD_SHA is required")
    observed = run(root, "git", "rev-parse", "HEAD").stdout.strip()
    require(observed == expected, f"wrong checkout head: {observed} != {expected}")
    require(not run(root, "git", "status", "--porcelain").stdout.strip(),
            "checkout must be pristine before proof")
    merge_base = run(root, "git", "merge-base", EXPECTED_BASE, observed).stdout.strip()
    require(merge_base == EXPECTED_BASE, f"wrong V4 ancestry: {merge_base}")
    changed = set(run(root, "git", "diff", "--name-only",
                      f"{EXPECTED_BASE}...{observed}").stdout.splitlines())
    require(changed == EXPECTED_PATHS,
            f"wrong proof-only scope: missing={sorted(EXPECTED_PATHS-changed)} "
            f"extra={sorted(changed-EXPECTED_PATHS)}")
    require(git_blob(SOURCE.read_bytes()) == EXPECTED_SOURCE_BLOB, "R04 source drift")
    require(git_blob(TAPES.read_bytes()) == EXPECTED_TAPES_BLOB, "R01 tape drift")
    return observed


def graph_signature(value):
    """Ordered, type-sensitive graph oracle; repeated nodes include their identity edge."""
    seen = {}
    def visit(node):
        tag = (type(node).__module__, type(node).__qualname__)
        if isinstance(node, (dict, list, tuple, set, frozenset)):
            marker = id(node)
            if marker in seen:
                return ("ref", seen[marker])
            index = seen[marker] = len(seen)
            if isinstance(node, dict):
                children = tuple((visit(k), visit(v)) for k, v in node.items())
            elif isinstance(node, (set, frozenset)):
                children = tuple(visit(v) for v in sorted(node, key=repr))
            else:
                children = tuple(visit(v) for v in node)
            return ("node", index, tag, children)
        return ("scalar", tag, repr(node))
    return visit(value)


def mutable_ids(value):
    seen, mutable = set(), set()
    def visit(node):
        marker = id(node)
        if marker in seen:
            return
        seen.add(marker)
        if isinstance(node, (dict, list, set)):
            mutable.add(marker)
        if isinstance(node, dict):
            for key, child in node.items():
                visit(key)
                visit(child)
        elif isinstance(node, (list, tuple, set, frozenset)):
            for child in node:
                visit(child)
    visit(value)
    return mutable


def check_clone(r04, template, label, fast=None):
    before = graph_signature(template)
    if fast is not None:
        require(r04._r04_is_fast_tape_action(template) is fast,
                f"{label}: wrong fast-path classification")
    reference = copy.deepcopy(template)
    candidate = r04._r04_clone_tape_action(template)
    require(graph_signature(candidate) == graph_signature(reference),
            f"{label}: value/type/key-order/alias-graph mismatch")
    require(not (mutable_ids(template) & mutable_ids(candidate)),
            f"{label}: mutable template escaped into clone")
    require(graph_signature(template) == before, f"{label}: template mutated")
    return candidate


def helper_from_patch(path=PATCH):
    """Extract the actual first-hunk helper, not a second test implementation."""
    added, hunks = [], 0
    for line in path.read_text().splitlines():
        if line.startswith("@@"):
            hunks += 1
        elif hunks == 1 and line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    tree = ast.parse("\n".join(added), filename=str(path))
    names = [node.name if isinstance(node, ast.FunctionDef)
             else node.targets[0].id if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             else None for node in tree.body]
    require(len(names) == 3 and set(names) == HELPER_NAMES,
            "unexpected first-hunk helper surface")
    scope = {"copy": copy}
    exec(compile(tree, str(path), "exec"), scope)
    return SimpleNamespace(**{name: scope[name] for name in HELPER_NAMES})


def validate_fallback_and_graph_contracts(r04):
    class ListChild(list):
        pass
    class DictChild(dict):
        pass
    class StringChild(str):
        pass
    class IntChild(int):
        pass
    def action():
        return {"farmer": ["PASS"], "hands": [["CARE"]],
                "market": [["SELL", "MILK", 2]]}

    cases = []
    for first, second in (("farmer", "hands"), ("farmer", "market"),
                          ("hands", "market")):
        value = action()
        value[first] = value[second] = []
        cases.append((f"shared_top_{first}_{second}", value, False))
    value = action(); value["hands"] = [value["farmer"]]
    cases.append(("farmer_is_hand_row", value, False))
    value = action(); value["market"] = [value["farmer"]]
    cases.append(("farmer_is_market_row", value, False))
    value = action(); value["hands"] *= 2
    cases.append(("repeated_hand_row", value, False))
    value = action(); value["market"] *= 2
    cases.append(("repeated_market_row", value, False))
    value = action(); value["market"] = [value["hands"][0]]
    cases.append(("cross_hand_market_row", value, False))
    value = action(); value["farmer"] = ["MOVE", ["NORTH"]]
    cases.append(("farmer_nested_list", value, False))
    value = action(); value["hands"] = [["CARE", {"meta": ["x"]}]]
    cases.append(("hands_nested_dict", value, False))
    value = action(); value["market"] = [["SELL", "MILK", (["x"],)]]
    cases.append(("market_tuple_with_mutable", value, False))
    value = action(); value["market"] = [["SELL", "MILK", {"x"}]]
    cases.append(("market_nested_set", value, False))
    value = action(); value["farmer"].append(value)
    cases.append(("cycle_to_action", value, False))
    value = action(); value["hands"].append(value["hands"])
    cases.append(("cycle_in_hands", value, False))
    value = action(); value["farmer"] = ListChild(value["farmer"])
    cases.append(("list_subclass", value, False))
    cases.append(("dict_subclass", DictChild(action()), False))
    value = action(); value[StringChild("farmer")] = value.pop("farmer")
    cases.append(("key_subclass", value, False))
    value = action(); value["market"][0][2] = IntChild(2)
    cases.append(("scalar_subclass", value, False))
    value = action(); value["farmer"] = ("PASS",)
    cases.append(("tuple_farmer", value, False))
    value = action(); value["hands"] = [("CARE",)]
    cases.append(("tuple_hand_row", value, False))
    value = action(); del value["market"]
    cases.append(("missing_key", value, False))
    value = action(); value["future"] = {"mutable": []}
    cases.append(("extra_key", value, False))
    cases.append(("null_action", None, False))
    cases.append(("scalar_action", 42, False))
    cases.append(("independent_empty_lists", {"farmer": [], "hands": [], "market": []}, True))
    value = action(); value["farmer"] = ["PASS", 1, 1.5, True, None]
    cases.append(("exact_json_scalar_types", value, True))
    for keys in itertools.permutations(("farmer", "hands", "market")):
        value = action()
        cases.append(("key_order_" + "_".join(keys), {k: value[k] for k in keys}, True))
    for label, value, fast in cases:
        candidate = check_clone(r04, value, label, fast)
        if type(value) is dict and "farmer" in value and isinstance(candidate["farmer"], list):
            before = graph_signature(value)
            candidate["farmer"].append("MUTATION_PROBE")
            require(graph_signature(value) == before, f"{label}: mutation reached input")

    # Exhaustive small mutable-row sharing partitions: six labelled row positions.
    # Every candidate must match deepcopy, not merely compare equal as JSON.
    partitions = 0
    for assignments in itertools.product(range(3), repeat=6):
        rows = [["PASS"] for _ in range(3)]
        value = {"farmer": rows[assignments[0]],
                 "hands": [rows[i] for i in assignments[1:4]],
                 "market": [rows[i] for i in assignments[4:]]}
        check_clone(r04, value, f"sharing_{assignments}", False)
        partitions += 1
    return len(cases), partitions


def validate_native_ast_delta(before, after):
    original = ast.parse(before)
    changed = ast.parse(after)
    retained, removed = [], []
    for node in changed.body:
        name = node.name if isinstance(node, ast.FunctionDef) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in HELPER_NAMES:
            removed.append(name)
        else:
            retained.append(node)
    require(len(removed) == 3 and set(removed) == HELPER_NAMES, "wrong injected helper set")
    changed.body = retained
    policies = [n for n in changed.body if isinstance(n, ast.ClassDef) and n.name == "Policy"]
    require(len(policies) == 1, "ambiguous native Policy")
    methods = [n for n in policies[0].body if isinstance(n, ast.FunctionDef) and n.name == "act"]
    require(len(methods) == 1, "ambiguous native Policy.act")
    calls = [n for n in ast.walk(methods[0]) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_r04_clone_tape_action"]
    require(len(calls) == 1, "must replace exactly one native clone call")
    call = calls[0]
    require(len(call.args) == 1 and not call.keywords
            and ast.dump(call.args[0]) == ast.dump(ast.parse("tape[step]", mode="eval").body),
            "wrong clone operand")
    call.func = ast.Attribute(value=ast.Name(id="copy", ctx=ast.Load()),
                              attr="deepcopy", ctx=ast.Load())
    require(ast.dump(original) == ast.dump(changed), "unrelated native AST changed")



def validate_native_delta_contracts():
    before = "import copy\nclass Policy:\n    def act(self, tape, step):\n        action = copy.deepcopy(tape[step])\n        return action\n"
    # Use the exact extracted first-hunk definitions in the source-delta fixtures.
    lines, hunk = [], 0
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@"):
            hunk += 1
        elif hunk == 1 and line.startswith("+"):
            lines.append(line[1:])
    helper = "\n".join(lines) + "\n"
    after = before.replace("class Policy:", helper + "class Policy:").replace(
        "copy.deepcopy(tape[step])", "_r04_clone_tape_action(tape[step])")
    validate_native_ast_delta(before, after)
    poisons = (
        after.replace("        return action", "        return None"),
        after.replace("_r04_clone_tape_action(tape[step])", "_r04_clone_tape_action(tape[step + 1])"),
        after.replace("        return action", "        action = _r04_clone_tape_action(tape[step])\n        return action"),
        after.replace("_R04_JSON_SCALAR_TYPES =", "RENAMED_TYPES =", 1),
    )
    for index, poison in enumerate(poisons):
        try:
            validate_native_ast_delta(before, poison)
        except AssertionError:
            continue
        raise AssertionError(f"native AST poison {index} accepted")
    return 1 + len(poisons)


def timed(fn, actions, repeats=7):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        for action in actions:
            fn(action)
        samples.append(time.perf_counter() - started)
    return min(samples), statistics.median(samples)


def main():
    root = repo_root()
    head = validate_checkout_custody(root)
    original_bytes = SOURCE.read_bytes()
    with tempfile.TemporaryDirectory(prefix="titan-r04-clone-") as tmp:
        scratch = Path(tmp)
        target_overlay = scratch / OVERLAY.relative_to(root)
        shutil.copytree(OVERLAY, target_overlay, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        run(scratch, "git", "apply", "--check", str(PATCH))
        run(scratch, "git", "apply", str(PATCH))
        target = target_overlay / SOURCE.name
        patched = target.read_bytes()
        compile(patched, str(target), "exec")
        validate_native_ast_delta(original_bytes, patched)
        sys.path.insert(0, str(target_overlay))
        importlib.invalidate_caches()
        r04 = importlib.import_module("r04_full_router")
        require(Path(r04.__file__).resolve() == target.resolve(), "wrong imported router")
        require("_r04_clone_tape_action(tape[step])" in inspect.getsource(r04.Policy.act),
                "native Policy.act seam missing")
        actions = [action for tape in r04._INLINE_TAPES for action in tape]
        require(len(actions) == EXPECTED_ACTIONS, f"wrong action count: {len(actions)}")
        fallback_shapes = 0
        for index, template in enumerate(actions):
            fallback_shapes += not r04._r04_is_fast_tape_action(template)
            check_clone(r04, template, f"frozen_action_{index}")
        require(fallback_shapes == 0, f"frozen corpus needs {fallback_shapes} fallbacks")
        contracts, sharing_cases = validate_fallback_and_graph_contracts(r04)
        deep_best, deep_median = timed(copy.deepcopy, actions)
        fast_best, fast_median = timed(r04._r04_clone_tape_action, actions)
        require(fast_median > 0 and deep_median / fast_median >= MIN_MEDIAN_SPEEDUP,
                f"median helper speed gate failed: deep={deep_median} fast={fast_median}")
        require(SOURCE.read_bytes() == original_bytes, "live router changed")
        require(not run(root, "git", "status", "--porcelain").stdout.strip(),
                "proof modified checkout")
        print("R04 FAST CLONE V4 PROOF PASS")
        print(f"head={head} base={EXPECTED_BASE} changed_paths={len(EXPECTED_PATHS)}")
        print(f"actions={len(actions)} fallback_shapes={fallback_shapes} "
              f"contracts={contracts} sharing_cases={sharing_cases}")
        print(f"native_ast_delta=helper_plus_one_call checkout_clean=true "
              f"patched_source_sha256={hashlib.sha256(patched).hexdigest()}")
        print(f"deepcopy_best_s={deep_best:.6f} fast_best_s={fast_best:.6f} "
              f"best_speedup={deep_best/fast_best:.2f}x")
        print(f"deepcopy_median_s={deep_median:.6f} fast_median_s={fast_median:.6f} "
              f"median_speedup={deep_median/fast_median:.2f}x")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        contracts, sharing_cases = validate_fallback_and_graph_contracts(helper_from_patch())
        native_contracts = validate_native_delta_contracts()
        print(f"R04 CLONE SELF-TEST PASS contracts={contracts} sharing_cases={sharing_cases} "
              f"native_delta_contracts={native_contracts}")
    elif sys.argv[1:]:
        raise SystemExit("usage: validate_production_patch.py [--self-test]")
    else:
        main()
