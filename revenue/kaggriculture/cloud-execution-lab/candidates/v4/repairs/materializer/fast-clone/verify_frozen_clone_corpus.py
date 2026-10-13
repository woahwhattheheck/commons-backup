#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare both preserved clone donors against their exact frozen action corpus.

No materializer or production entrypoint is executed. Input Git blobs are pinned;
the hardener's literal helper is extracted without executing the hardener script.
Run normally and with -O. Timings measure clone calls only, never game performance.
"""
import argparse
import ast
import copy
import hashlib
import itertools
import json
import platform
import statistics
import time
import types
from pathlib import Path

PINS = {
    "hardener": "22acbcc6f1beb0460ba3f796af0e1febf7d94ca1",
    "helper": "b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a",
    "tapes": "a43289b9cc5e34a2481fddf652762a7d92f427ef",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def pinned(path, expected):
    raw = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(actual == expected, f"{path}: expected {expected}, got {actual}")
    return raw.decode("utf-8")


def load_source(source, name):
    module = types.ModuleType(name)
    exec(compile(source, name, "exec"), module.__dict__)
    return module


def graph(value):
    """Value/type/order/alias fingerprint, including cycles and custom attributes."""
    seen = {}
    def visit(node):
        kind = type(node).__module__ + "." + type(node).__qualname__
        if isinstance(node, (dict, list, tuple, set)) or hasattr(node, "__dict__"):
            if id(node) in seen:
                return ("ref", seen[id(node)])
            number = seen[id(node)] = len(seen)
            if isinstance(node, dict):
                contents = tuple((visit(k), visit(v)) for k, v in node.items())
            elif isinstance(node, set):
                contents = tuple(visit(v) for v in sorted(node, key=repr))
            elif isinstance(node, (list, tuple)):
                contents = tuple(visit(v) for v in node)
            else:
                contents = repr(node)
            attrs = visit(vars(node)) if hasattr(node, "__dict__") else None
            return (kind, number, contents, attrs)
        return (kind, repr(node))
    return visit(value)


def mutable_ids(value):
    seen, mutable = set(), set()
    def visit(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, (dict, list, set)) or hasattr(node, "__dict__"):
            mutable.add(id(node))
        if isinstance(node, dict):
            for k, v in node.items():
                visit(k); visit(v)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                visit(item)
        if hasattr(node, "__dict__"):
            visit(vars(node))
    visit(value)
    return mutable


def check_clone(fn, value):
    before = graph(value)
    result = fn(value)
    require(graph(result) == graph(copy.deepcopy(value)), "value/type/order/alias mismatch")
    require(not (mutable_ids(value) & mutable_ids(result)), "mutable input/output alias")
    require(graph(value) == before, "clone mutated input")
    return result


def action():
    return {"farmer": ["PASS"], "hands": [["NORTH"], ["CARE"]],
            "market": [["SELL", "WOOL", 2]]}


def future_cases():
    values = []
    for keys in itertools.permutations(action()):
        a = action(); values.append({key: a[key] for key in keys})
    a = action(); a["hands"] = [a["farmer"], a["farmer"]]; values.append(a)
    a = action(); a["market"] = a["hands"]; values.append(a)
    a = action(); a["market"] = [a["hands"][0]]; values.append(a)
    a = action(); a["farmer"].append(a["farmer"]); values.append(a)
    a = action(); a["metadata"] = a; values.append(a)
    for cell in (["NORTH"], {"meta": ["x"]}, (["x"],), {"x"}):
        a = action(); a["market"][0].append(cell); values.append(a)
    class L(list): pass
    class S(str): pass
    a = action(); a["farmer"] = L(a["farmer"]); a["farmer"].meta = [1]; values.append(a)
    a = action(); key = S("farmer"); key.meta = [1]
    values.append({key: a["farmer"], "hands": a["hands"], "market": a["market"]})
    for key in ("farmer", "hands", "market"):
        a = action(); del a[key]; values.append(a)
    values.extend([None, [], (), 1, {"farmer": [], "hands": [], "market": []}])
    return values


def timing(functions, actions, repeats):
    samples = {name: [] for name in functions}
    entries = list(functions.items())
    for repeat in range(repeats):
        # Rotate order rather than always measuring one donor after the other.
        ordered = entries[repeat % len(entries):] + entries[:repeat % len(entries)]
        for name, fn in ordered:
            start = time.perf_counter()
            for a in actions:
                fn(a)
            samples[name].append(time.perf_counter() - start)
    return {name: statistics.median(values) for name, values in samples.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    require(args.repeats >= 3, "at least three timing samples required")
    sources = {name: pinned(getattr(args, name), sha) for name, sha in PINS.items()}
    bindings = [n.value for n in ast.parse(sources["hardener"]).body
                if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "HARDENED_HELPER"]
    require(len(bindings) == 1, "expected one literal HARDENED_HELPER")
    helper_source = ast.literal_eval(bindings[0])
    require(type(helper_source) is str, "helper must be literal text")
    hardened = load_source("import copy\n" + helper_source, "_hardened_clone")
    preserved = load_source(sources["helper"], "_preserved_clone")
    tapes = load_source(sources["tapes"], "_frozen_tapes").load_tapes()
    require(len(tapes) == 13 and all(len(t) == 719 for t in tapes), "wrong frozen corpus")
    actions = [a for tape in tapes for a in tape]
    donors = {
        "materializer_hardened": (hardened._r04_is_fast_tape_action, hardened._r04_clone_tape_action),
        "performance_preserved": (preserved.is_fast_tape_action, preserved.apply_fast_tape_clone),
    }
    report = {}
    for name, (predicate, clone) in donors.items():
        fallback = 0
        for a in actions:
            fallback += not predicate(a)
            result = check_clone(clone, a)
            before = graph(a)
            result["farmer"].append("MUTATION_WITNESS")
            for key in ("hands", "market"):
                for row in result[key]:
                    row.append("MUTATION_WITNESS")
            require(graph(a) == before, "output mutation leaked to tape")
        cases = future_cases()
        for a in cases:
            check_clone(clone, a)
        require(fallback == 0, f"{name}: frozen corpus needs fallback")
        report[name] = {"corpus_actions": len(actions), "corpus_fallbacks": fallback,
                        "future_schema_cases": len(cases), "mutation_checks": len(actions)}
    rejected = 0
    for broken in (lambda a: a.copy(), lambda a: {k: copy.deepcopy(a[k]) for k in ("market", "hands", "farmer")}):
        try:
            check_clone(broken, action())
        except AssertionError:
            rejected += 1
    require(rejected == 2, "negative control false-pass")
    medians = timing({"deepcopy": copy.deepcopy, **{k: v[1] for k, v in donors.items()}}, actions, args.repeats)
    for name in donors:
        report[name]["median_speedup"] = medians["deepcopy"] / medians[name]
        require(report[name]["median_speedup"] >= 1.50, f"{name}: clone speed gate failed")
    import sys
    print(json.dumps({"status": "PASS", "python": platform.python_version(), "optimized": bool(sys.flags.optimize),
                      "input_git_blobs": PINS, "donors": report, "median_seconds": medians,
                      "timing_repeats": args.repeats, "negative_controls_rejected": rejected,
                      "scope": "clone helpers only; no materializer, production runtime, or game gate executed"}, indent=2))


if __name__ == "__main__":
    main()
