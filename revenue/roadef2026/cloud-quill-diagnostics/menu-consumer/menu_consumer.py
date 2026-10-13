#!/usr/bin/env python3
"""Evaluate QUILL route menus with the existing DOCK temporal kernel.

This is a source-bound public-development consumer. It does not alter the
production kernel. The generated test binary restricts DOCK_TEMPORAL_ONLY to
demand IDs explicitly present in DOCK_ROUTE_MENU and passes no generic ranked
waypoints, so an accepted result is attributable to the supplied menu plus the
incumbent routes already required by the kernel.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence

CASES = ("setB-02", "setB-05", "setB-07", "setB-10")
EXPECTED_PARENT_SHA256 = "322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1"
EXPECTED_DOCK_GIT_BLOBS = {
    "apply_temporal.py": "fa0901ee8c2cb20752023e73f6fe594aa9517192",
    "temporal_dp.hpp": "74b3b5e327db7e73cf0dddf2c84467e43f2d3bd8",
    "temporal_join.inc": "a50e0d7fe0447e23692925fcbd9e4f2bd846373f",
}
RUN_LOOP = """            Route nodes(n); std::iota(nodes.begin(),nodes.end(),0);\n            for(int d=0;d<static_cast<int>(demands.size()) && !finished();++d) dockTemporal(d,nodes);\n            writeSolution(); statistics();"""
MENU_ONLY_LOOP = """            // Consumer harness: evaluate only demand IDs explicitly present in\n            // DOCK_ROUTE_MENU, and pass no generic ranked-waypoint proposals.\n            // The dockTemporal implementation and acceptance logic are unchanged.\n            dockLoadMenu();\n            for(int d=0;d<static_cast<int>(demands.size()) && !finished();++d)\n                if(!dockExtraMenu[static_cast<std::size_t>(d)].empty()) dockTemporal(d);\n            writeSolution(); statistics();"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command: Sequence[str], *, env: Mapping[str, str] | None = None,
        cwd: Path | None = None, timeout: float = 120.0,
        stdout: Path | None = None, stderr: Path | None = None) -> subprocess.CompletedProcess[str]:
    out_handle = stdout.open("w", encoding="utf-8") if stdout else subprocess.PIPE
    err_handle = stderr.open("w", encoding="utf-8") if stderr else subprocess.PIPE
    try:
        return subprocess.run(
            list(map(str, command)), cwd=cwd, env=dict(env) if env else None,
            text=True, stdout=out_handle, stderr=err_handle, timeout=timeout,
            check=False,
        )
    finally:
        if stdout:
            out_handle.close()
        if stderr:
            err_handle.close()


def load_apply(path: Path):
    spec = importlib.util.spec_from_file_location("quill_dock_apply", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_function(source: str, signature: str) -> str:
    """Return one C++ function definition using string-aware scans.

    The opening body brace is found only after the parameter list closes, so a
    default initializer such as ``const Route& r = {}`` cannot be mistaken for
    the function body.
    """
    start = source.find(signature)
    if start < 0:
        raise ValueError(f"missing function signature: {signature}")
    opening = source.find("(", start)
    if opening < 0:
        raise ValueError(f"missing parameter list: {signature}")

    def advance_balanced(index: int, opener: str, closer: str) -> int:
        depth = 0
        quote: str | None = None
        escape = False
        line_comment = False
        block_comment = False
        i = index
        while i < len(source):
            c = source[i]
            n = source[i + 1] if i + 1 < len(source) else ""
            if line_comment:
                if c == "\n":
                    line_comment = False
                i += 1
                continue
            if block_comment:
                if c == "*" and n == "/":
                    block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if quote is not None:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == quote:
                    quote = None
                i += 1
                continue
            if c == "/" and n == "/":
                line_comment = True
                i += 2
                continue
            if c == "/" and n == "*":
                block_comment = True
                i += 2
                continue
            if c in ('"', "'"):
                quote = c
                i += 1
                continue
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError(f"unterminated balanced region after: {signature}")

    after_parameters = advance_balanced(opening, "(", ")")
    body_open = source.find("{", after_parameters)
    if body_open < 0:
        raise ValueError(f"missing opening brace: {signature}")
    body_end = advance_balanced(body_open, "{", "}")
    return source[start:body_end]


def build_menu_only_source(parent: Path, dock_dir: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    if sha256(parent) != EXPECTED_PARENT_SHA256:
        raise ValueError("parent source does not match fleet 2885d176")
    for name, expected in EXPECTED_DOCK_GIT_BLOBS.items():
        actual = git_blob(dock_dir / name)
        if actual != expected:
            raise ValueError(f"{name} Git blob {actual} != expected {expected}")
    module = load_apply(dock_dir / "apply_temporal.py")
    generated = module.apply(parent.read_text(encoding="utf-8"))
    if generated.count(RUN_LOOP) != 1:
        raise ValueError("current DOCK temporal-only run loop did not match once")
    patched = generated.replace(RUN_LOOP, MENU_ONLY_LOOP, 1)
    before = extract_function(generated, "    bool dockTemporal(")
    after = extract_function(patched, "    bool dockTemporal(")
    if before != after:
        raise AssertionError("menu-only harness changed dockTemporal")
    output.mkdir(parents=True)
    (output / "main.cpp").write_text(patched, encoding="utf-8")
    shutil.copy2(dock_dir / "temporal_dp.hpp", output / "temporal_dp.hpp")
    manifest = {
        "parent_sha256": sha256(parent),
        "dock_git_blobs": {name: git_blob(dock_dir / name) for name in EXPECTED_DOCK_GIT_BLOBS},
        "generated_main_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "menu_only_main_sha256": hashlib.sha256(patched.encode()).hexdigest(),
        "dock_temporal_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "consumer_change": "only temporal-only demand selection; menu routes plus incumbent routes, no generic ranked waypoints",
    }
    write_json(output / "SOURCE.json", manifest)
    return manifest


def compile_solver(source_dir: Path, vendor: Path, output: Path, cxx: str) -> dict[str, Any]:
    command = [cxx, "-std=c++20", "-O2", "-DNDEBUG", f"-I{vendor}",
               str(source_dir / "main.cpp"), "-o", str(output)]
    result = run(command, timeout=180.0)
    if result.returncode:
        raise RuntimeError(f"solver compilation failed\n{result.stderr}")
    return {"command": command, "sha256": sha256(output)}


def compile_checker(checker_source: Path, networktools: Path, output: Path, cxx: str) -> dict[str, Any]:
    command = [cxx, "-std=c++20", "-O2", "-DNDEBUG", "-DLANG_EN",
               f"-I{networktools}", str(checker_source), "-o", str(output)]
    result = run(command, timeout=240.0)
    if result.returncode:
        raise RuntimeError(f"checker compilation failed\n{result.stderr}")
    return {"command": command, "sha256": sha256(output)}


def verify_bindings(bindings: Mapping[str, Any], menu_root: Path,
                    screen_root: Path) -> dict[str, Any]:
    checked: list[dict[str, str]] = []
    for row in bindings["instances"]:
        menu = menu_root / row["menu"]
        actual = sha256(menu)
        if actual != row["menu_sha256"]:
            raise ValueError(f"menu hash mismatch: {menu}")
        checked.append({"path": str(menu), "sha256": actual})
        for item in row["inputs"].values():
            path = screen_root / item["archive_member"]
            actual = sha256(path)
            if actual != item["sha256"]:
                raise ValueError(f"input hash mismatch: {path}")
            checked.append({"path": str(path), "sha256": actual})
    return {"objects": len(checked), "verified": checked}


def routes(document: Mapping[str, Any]) -> dict[tuple[int, int], tuple[int, ...]]:
    return {(int(row["d"]), int(row["t"])): tuple(map(int, row["w"]))
            for row in document.get("srpaths", [])}


def route_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    old, new = routes(before), routes(after)
    result = []
    for d, t in sorted(set(old) | set(new)):
        a, b = old.get((d, t), ()), new.get((d, t), ())
        if a != b:
            result.append({"d": d, "t": t, "before": list(a), "after": list(b)})
    return result


def compare_checker(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    old = [str(row["sat"]) for row in before["saturations"]]
    new = [str(row["sat"]) for row in after["saturations"]]
    if len(old) != len(new):
        raise ValueError("checker saturation vectors differ in length")
    first = next((i for i, pair in enumerate(zip(old, new)) if pair[0] != pair[1]), None)
    relation = "tie"
    if old != new:
        from decimal import Decimal
        old_dec = list(map(Decimal, old))
        new_dec = list(map(Decimal, new))
        relation = "improved" if new_dec < old_dec else "worse"
    return {
        "valid": bool(after.get("valid")),
        "relation": relation,
        "vector_length": len(old),
        "first_difference_rank_1_based": None if first is None else first + 1,
        "old_at_first": None if first is None else old[first],
        "new_at_first": None if first is None else new[first],
        "differing_coordinates": sum(a != b for a, b in zip(old, new)),
        "old_total_cost": before["total_cost"],
        "new_total_cost": after["total_cost"],
        "cost_delta": after["total_cost"] - before["total_cost"],
        "old_total_srpaths": before["total_srpaths"],
        "new_total_srpaths": after["total_srpaths"],
        "old_total_segments": before["total_segments"],
        "new_total_segments": after["total_segments"],
    }


def checker_command(checker: Path, network: Path, traffic: Path, scenario: Path,
                    solution: Path, decimals: int) -> list[str]:
    return [str(checker), "--net", str(network), "--tm", str(traffic),
            "--scenario", str(scenario), "--srpaths", str(solution),
            "--max-decimal-places", str(decimals)]


def execute_case(case: str, row: Mapping[str, Any], *, solver: Path, checker: Path,
                 screen_root: Path, menu_root: Path, output: Path,
                 seconds: float, temporal_seconds: float) -> dict[str, Any]:
    case_dir = output / case
    case_dir.mkdir(parents=True, exist_ok=False)
    network = screen_root / f"inputs/setB/{case}-net.json"
    traffic = screen_root / f"inputs/setB/{case}-tm.json"
    scenario = screen_root / f"inputs/setB/{case}-scenario.json"
    incumbent = screen_root / f"screen30/{case}/candidate/solution.json"
    menu = menu_root / row["menu"]
    solution = case_dir / "solution.json"
    statistics = case_dir / "statistics.json"
    env = os.environ.copy()
    env.update({
        "CLOUD_INITIAL_SOLUTION": str(incumbent),
        "DOCK_ROUTE_MENU": str(menu),
        "DOCK_TEMPORAL": "1",
        "DOCK_TEMPORAL_ONLY": "1",
        "DOCK_TEMPORAL_K": "12",
        "DOCK_TEMPORAL_SECONDS": str(temporal_seconds),
        "SEDGE_SECONDS": str(seconds),
        "SEDGE_STATS": str(statistics),
    })
    process = run([solver, network, traffic, scenario, solution], env=env,
                  timeout=seconds + 30, stdout=case_dir / "solver.stdout",
                  stderr=case_dir / "solver.stderr")
    if process.returncode:
        raise RuntimeError(f"{case} solver failed with {process.returncode}")
    before_doc, after_doc = read_json(incumbent), read_json(solution)
    checks: dict[str, Any] = {}
    for decimals in (6, 12):
        old_path = screen_root / f"screen30/{case}/candidate/checker-{decimals}.stdout"
        old_report = read_json(old_path)
        if not old_report.get("valid"):
            raise AssertionError(f"{case} retained incumbent checker {decimals} is not valid")
        if solution.read_bytes() == incumbent.read_bytes():
            new_path = old_path
            new_report = copy.deepcopy(old_report)
            executed = False
        else:
            new_path = case_dir / f"candidate-checker-{decimals}.json"
            result = run(checker_command(checker, network, traffic, scenario, solution, decimals),
                         timeout=240, stdout=new_path,
                         stderr=case_dir / f"candidate-checker-{decimals}.stderr")
            if result.returncode:
                raise RuntimeError(f"{case} checker {decimals} failed for {solution}")
            new_report = read_json(new_path)
            executed = True
        comparison = compare_checker(old_report, new_report)
        comparison.update({"checker_executed_for_candidate": executed,
                           "incumbent_checker_sha256": sha256(old_path),
                           "candidate_checker_sha256": sha256(new_path)})
        checks[str(decimals)] = comparison
    repeat_solution = case_dir / "repeat-solution.json"
    repeat_statistics = case_dir / "repeat-statistics.json"
    repeat_env = env.copy()
    repeat_env["SEDGE_STATS"] = str(repeat_statistics)
    repeat = run([solver, network, traffic, scenario, repeat_solution], env=repeat_env,
                 timeout=seconds + 30, stdout=case_dir / "repeat.stdout",
                 stderr=case_dir / "repeat.stderr")
    if repeat.returncode or repeat_solution.read_bytes() != solution.read_bytes():
        raise AssertionError(f"{case} solution is not deterministic")
    first_stats, second_stats = read_json(statistics), read_json(repeat_statistics)
    for key in ("resumed", "attempted", "joint_attempted", "joint_accepted",
                "ranked_candidates", "accepted", "initial_mlu", "final_mlu",
                "budget_used", "loads"):
        if first_stats.get(key) != second_stats.get(key):
            raise AssertionError(f"{case} non-timing statistic changed: {key}")
    return {
        "case": case,
        "targets": row["demand_ids"],
        "menu": read_json(menu)["routes"],
        "incumbent_sha256": sha256(incumbent),
        "solution_sha256": sha256(solution),
        "changed": before_doc != after_doc,
        "route_changes": route_changes(before_doc, after_doc),
        "solver": {key: first_stats.get(key) for key in
                   ("seconds", "resumed", "accepted", "initial_mlu", "final_mlu", "budget_used")},
        "checks": checks,
        "deterministic": True,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--dock-dir", type=Path, required=True)
    p.add_argument("--vendor", type=Path, required=True)
    p.add_argument("--checker-source", type=Path, required=True)
    p.add_argument("--networktools", type=Path, required=True)
    p.add_argument("--screen-root", type=Path, required=True)
    p.add_argument("--menu-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--solver-binary", type=Path,
                   help="Reuse a previously built binary from this exact menu-only source")
    p.add_argument("--checker-binary", type=Path,
                   help="Reuse a previously built checker from the supplied source context")
    p.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--temporal-seconds", type=float, default=26.0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    bindings = read_json(args.menu_root / "menu-bindings.json")
    binding_report = verify_bindings(bindings, args.menu_root, args.screen_root)
    source_dir = args.output / "source"
    source_report = build_menu_only_source(args.parent, args.dock_dir, source_dir)
    bin_dir = args.output / "bin"
    bin_dir.mkdir()
    if args.solver_binary:
        solver = args.solver_binary.resolve()
        if not solver.is_file():
            raise FileNotFoundError(solver)
        solver_report = {"reused": True, "path": str(solver), "sha256": sha256(solver)}
    else:
        solver = bin_dir / "dock-menu-only"
        solver_report = compile_solver(source_dir, args.vendor, solver, args.cxx)
    if args.checker_binary:
        checker = args.checker_binary.resolve()
        if not checker.is_file():
            raise FileNotFoundError(checker)
        checker_report = {"reused": True, "path": str(checker), "sha256": sha256(checker)}
    else:
        checker = bin_dir / "checker"
        checker_report = compile_checker(args.checker_source, args.networktools, checker, args.cxx)
    by_case = {row["instance"]: row for row in bindings["instances"]}
    results = [execute_case(case, by_case[case], solver=solver, checker=checker,
                            screen_root=args.screen_root, menu_root=args.menu_root,
                            output=args.output / "cases", seconds=args.seconds,
                            temporal_seconds=args.temporal_seconds)
               for case in args.cases]
    expected_changed = [case for case in args.cases if case in ("setB-02", "setB-05", "setB-07")]
    if [row["case"] for row in results if row["changed"]] != expected_changed:
        raise AssertionError("unexpected changed-case set")
    if any(row["checks"][str(d)]["relation"] not in ("improved", "tie")
           or not row["checks"][str(d)]["valid"] for row in results for d in (6, 12)):
        raise AssertionError("invalid or worsening checker result")
    report = {
        "schema": "roadef.quill-dock-menu-consumer.v1",
        "scope": "public development; exact saved incumbents; no full-budget or submission claim",
        "source": source_report,
        "bindings": {"objects_verified": binding_report["objects"]},
        "solver_build": solver_report,
        "checker_build": checker_report,
        "results": results,
    }
    write_json(args.output / "RESULTS.json", report)
    print(json.dumps({"status": "pass", "changed": [r["case"] for r in results if r["changed"]],
                      "unchanged": [r["case"] for r in results if not r["changed"]]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
