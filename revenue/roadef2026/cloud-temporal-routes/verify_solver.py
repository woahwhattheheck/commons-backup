#!/usr/bin/env python3
"""Compile and independently check the temporal join; no downloads or submissions.

Use a fresh output directory. The fixture is constructed here, not a public
benchmark instance. Checker output is retained verbatim, including its optional
Infinity-valued diagnostics; only finite saturation coordinates are compared.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from apply_temporal import apply, HERE


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fixture() -> tuple[dict, dict, dict, dict]:
    arcs = [(0, 4, 1, 1), (0, 1, 1, 10), (1, 2, 1, 10),
            (2, 4, 1, 10), (1, 3, 1, 10), (3, 2, 1, 10)]
    net = {"directed": True, "multigraph": False,
           "nodes": [{"id": i, "name": f"n{i}"} for i in range(5)], "links": []}
    # The official challenge requires a bidirected network. High-metric reverse
    # arcs satisfy that input contract, while their very small capacities make
    # cyclic detours unattractive. They are present in BOTH compared inputs.
    for a, b, metric, capacity in arcs + [(b, a, 100, 0.001) for a, b, _, _ in arcs]:
        net["links"].append({"id": len(net["links"]), "from": a, "to": b,
                             "metric": metric, "capacity": capacity})
    tm = {"num_time_slots": 2, "demands": [
        {"s": 0, "t": 4, "v": [10, 10]},
        {"s": 1, "t": 2, "v": [0, 95]},
        {"s": 1, "t": 3, "v": [95, 0]}]}
    scenario = {"max_segments": 4, "interventions": [], "budget": [{"t": 1, "value": 3}]}
    menu = {"routes": [{"d": 0, "w": [1, 2]}, {"d": 0, "w": [1, 3, 2]}]}
    return net, tm, scenario, menu


def execute(command: list[str], directory: Path, label: str, env: dict | None = None,
            timeout: float = 60) -> subprocess.CompletedProcess:
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (directory / f"{label}.stdout").write_bytes(exc.stdout or b"")
        (directory / f"{label}.stderr").write_bytes(exc.stderr or b"")
        write_json(directory / f"{label}.process.json", {
            "command": command, "status": "timeout", "seconds": time.perf_counter() - started})
        raise
    (directory / f"{label}.stdout").write_bytes(result.stdout)
    (directory / f"{label}.stderr").write_bytes(result.stderr)
    write_json(directory / f"{label}.process.json", {
        "command": command, "status": "completed", "returncode": result.returncode,
        "seconds": time.perf_counter() - started})
    return result


def parse_checked(data: bytes) -> tuple[dict, tuple[Decimal, ...]]:
    value = json.loads(data, parse_float=Decimal)
    if value.get("valid") is not True:
        raise AssertionError(f"official checker rejected solution: {value}")
    vector = tuple(sorted((Decimal(str(row["sat"])) for row in value["saturations"]), reverse=True))
    if not all(v.is_finite() and v >= 0 for v in vector):
        raise AssertionError("checker returned a nonfinite/negative saturation")
    return value, vector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()
    parent = args.parent.resolve(strict=True)
    vendor = args.vendor.resolve(strict=True)
    checker = args.checker.resolve(strict=True)
    source = parent.read_bytes()
    joined = apply(source.decode("utf-8"))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "bin").mkdir()
    (out / "control.cpp").write_bytes(source)
    (out / "candidate.cpp").write_text(joined, encoding="utf-8")
    (out / "temporal_dp.hpp").write_bytes((HERE / "temporal_dp.hpp").read_bytes())
    for arm in ("control", "candidate"):
        result = execute([args.compiler, "-std=c++17", "-O2", "-DNDEBUG", f"-I{vendor}",
                          str(out / f"{arm}.cpp"), "-o", str(out / "bin" / arm)], out, f"build-{arm}")
        if result.returncode:
            raise RuntimeError(f"{arm} build failed; see recorded streams")

    base = fixture()
    # All controls are evaluated against the same generated topology, except
    # explicitly named segment/budget/index variants. No held data are used.
    cases = [
        ("control", "control", {}, {}),
        ("disabled", "candidate", {}, {}),
        ("search", "candidate", {"DOCK_TEMPORAL": "1"}, {}),
        ("dp_only", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_ONLY": "1"}, {}),
        ("cancelled", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_SECONDS": "0"}, {}),
        ("zero_menu_cap", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_K": "0"}, {}),
        ("resume", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_ONLY": "1"}, {"resume": True}),
        ("too_few_segments", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_ONLY": "1"}, {"segments": 3}),
        ("tight_budget", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_ONLY": "1"}, {"budget": 2}),
        ("remapped_nodes", "candidate", {"DOCK_TEMPORAL": "1", "DOCK_TEMPORAL_ONLY": "1"}, {"remap": True}),
        ("repeat_search", "candidate", {"DOCK_TEMPORAL": "1"}, {}),
    ]
    rows, outputs, vectors = [], {}, {}
    clean_env = {k: v for k, v in os.environ.items()
                 if not k.startswith(("DOCK_", "SEDGE_", "FLEET_", "CLOUD_INITIAL_"))}
    for name, binary, settings, changes in cases:
        directory = out / name
        directory.mkdir()
        net, tm, scenario, menu = copy.deepcopy(base)
        if "segments" in changes:
            scenario["max_segments"] = changes["segments"]
        if "budget" in changes:
            scenario["budget"][0]["value"] = changes["budget"]
        if changes.get("remap"):
            mapping = {i: 100 + 7 * i for i in range(5)}
            for node in net["nodes"]:
                node["id"] = mapping[node["id"]]
            for edge in net["links"]:
                edge["from"], edge["to"] = mapping[edge["from"]], mapping[edge["to"]]
            for demand in tm["demands"]:
                demand["s"], demand["t"] = mapping[demand["s"]], mapping[demand["t"]]
            for route in menu["routes"]:
                route["w"] = [mapping[w] for w in route["w"]]
        for filename, data in (("net", net), ("tm", tm), ("scenario", scenario), ("menu", menu)):
            write_json(directory / f"{filename}.json", data)
        env = dict(clean_env, SEDGE_MAX_ROUNDS="64", SEDGE_SECONDS="30",
                   SEDGE_STATS=str(directory / "stats.json"), DOCK_ROUTE_MENU=str(directory / "menu.json"),
                   **settings)
        if changes.get("resume"):
            env["CLOUD_INITIAL_SOLUTION"] = str(out / "control/solution.json")
        command = [str(out / "bin" / binary), str(directory / "net.json"), str(directory / "tm.json"),
                   str(directory / "scenario.json"), str(directory / "solution.json")]
        result = execute(command, directory, "solver", env=env, timeout=35)
        if result.returncode:
            raise AssertionError(f"solver failed {name}")
        solution = json.loads((directory / "solution.json").read_text())
        stats = json.loads((directory / "stats.json").read_text())
        checked = None
        for decimals in (6, 12):
            command = [str(checker), "--net", str(directory / "net.json"),
                       "--tm", str(directory / "tm.json"), "--scenario", str(directory / "scenario.json"),
                       "--srpaths", str(directory / "solution.json"), "--max-decimal-places", str(decimals)]
            response = execute(command, directory, f"checker-{decimals}", timeout=15)
            if response.returncode:
                raise AssertionError(f"checker failed {name}, precision {decimals}")
            checked, vector = parse_checked(response.stdout)
            if decimals == 6:
                vectors[name] = vector
            if decimals == 12:
                internal = {(x["t"], x["from"], x["to"]): x["sat"] for x in stats["loads"]}
                maximum_error = max(abs(float(x["sat"]) - internal[x["t"], x["from"], x["to"]])
                                    for x in checked["saturations"])
                assert maximum_error < 2e-9, (name, maximum_error)
        assert checked is not None
        assert checked["total_cost"] == sum(stats["budget_used"])
        outputs[name] = solution
        rows.append({"case": name, "valid_6_and_12": True,
                     "maximum_saturation": float(vectors[name][0]),
                     "transition_cost": checked["total_cost"],
                     "max_load_error": maximum_error, "solution_sha256": digest(directory / "solution.json"),
                     "vector_6": [str(v) for v in vectors[name]], "settings": settings,
                     "input_variant": changes})

    for name in ("disabled", "cancelled", "zero_menu_cap"):
        assert outputs[name] == outputs["control"], name
        assert vectors[name] == vectors["control"], name
    assert outputs["repeat_search"] == outputs["search"]
    for name in ("search", "dp_only", "resume", "remapped_nodes"):
        assert vectors[name] < vectors["control"]
        assert vectors[name][0] == Decimal("9.5")
    assert vectors["control"][0] == Decimal("10")
    # Removing either feasibility ingredient must eliminate this particular gain.
    assert vectors["too_few_segments"][0] >= Decimal("10")
    assert vectors["tight_budget"][0] >= Decimal("10")
    assert parent.read_bytes() == source
    write_json(out / "SUMMARY.json", {
        "scope": "constructed official-checker/native integration, not public-instance performance",
        "status": "PASS", "solver_cases": len(rows), "official_checker_invocations": 2 * len(rows),
        "parent_sha256": digest(parent), "joined_source_sha256": digest(out / "candidate.cpp"),
        "header_sha256": digest(out / "temporal_dp.hpp"), "checker_binary_sha256": digest(checker),
        "control_binary_sha256": digest(out / "bin/control"), "candidate_binary_sha256": digest(out / "bin/candidate"),
        "cases": rows})
    print(json.dumps({"status": "PASS", "solver_cases": len(rows), "checker_calls": 2 * len(rows)}))


if __name__ == "__main__":
    main()
