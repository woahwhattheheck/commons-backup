# SPDX-License-Identifier: Apache-2.0
"""Exact-loader oracle for cross-episode process-state isolation.

Run the same two full games in opposite order in two isolated workers. Each
scenario is therefore observed once as the first game in a fresh process and
once after another complete game while the candidate callable, imported runtime
modules and process caches remain alive. Exact action hashes and terminal
outcomes must agree, and step 0 must replace the prior TitanAgent instance.

The candidate is called on one persistent worker thread per process, matching
the existing 719-call worker-episode oracle and exercising the thread deadline
guard across the episode boundary. Every call also proves that the guard has
restored the worker's trace hook and active-deadline ContextVar before returning.

This is a verification harness only; it does not alter production policy.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Dict, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SCENARIOS = {
    "A": {"seed": 9922999, "seat": 0},
    "B": {"seed": 1909087201, "seat": 1},
}


def attributed_root_modules(lab: Path | None = None) -> dict[str, Path]:
    """Archive-root members whose live bytes live outside the lab directory.

    Isolated ``python3 -I`` workers only insert the agent parent. Hosted
    sparse-checkout of the lab therefore cannot import seller_snapshot /
    observed_clone unless those attributed siblings are materialized beside
    main.py or their parent directories are on sys.path. GitHub Actions run
    34671866030 failed first while ``build_integrated.py --check`` tried to
    read ``../cloud-quickstep/seller_snapshot.py`` from a lab-only checkout.
    """
    lab = Path(lab or ROOT).resolve()
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files

    mapping: dict[str, Path] = {}
    for member, source in source_files().items():
        if Path(member).parent != Path("."):
            continue
        origin = (lab / source).resolve()
        try:
            origin.relative_to(lab)
        except ValueError:
            mapping[member] = origin
    return mapping


def missing_mapped_sources(lab: Path | None = None) -> list[str]:
    """Return human-readable rows for every source_files() origin that is absent."""
    lab = Path(lab or ROOT).resolve()
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files

    missing = []
    for member, source in source_files().items():
        origin = lab / source
        if not origin.is_file():
            missing.append(f"{member} <- {source}")
    return missing


def materialize_live_worker_root(lab: Path, dest: Path) -> Path:
    """Copy the lab and place archive-layout members for isolated live workers.

    The live-source hosted step previously copied only cloud-execution-lab
    into a temp root. Bare imports and SOURCE.json then failed even after the
    sibling files were present in the checkout. A real lab ``checks/`` directory
    also suppresses the historical ``checks -> .`` symlink, so mapped
    ``checks/reference/engine/utils.py`` (and the rest of the archive checks
    layout) must be overlaid explicitly. GitHub Actions run 34690162038 failed
    while the live worker tried to read that missing path after
    ``--materialize-live`` reported PASS.
    """
    lab = Path(lab).resolve()
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copytree(lab, dest, symlinks=True)
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files

    for member, source in source_files().items():
        origin = (lab / source).resolve()
        if not origin.is_file():
            raise FileNotFoundError(origin)
        target = dest / member
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(origin.read_bytes())
    for member, origin in attributed_root_modules(lab).items():
        if not origin.is_file():
            raise FileNotFoundError(origin)
        target = dest / member
        if target.resolve() != origin:
            target.write_bytes(origin.read_bytes())
    checks = dest / "checks"
    if not checks.exists():
        checks.symlink_to(".")
    published = lab / "runtime/integrated-selected/CURRENT-SOURCE.json"
    if published.is_file() and not (dest / "SOURCE.json").is_file():
        (dest / "SOURCE.json").write_bytes(published.read_bytes())
    return dest


def _load_official(root: Path):
    """Load the same pinned raw-loader helpers as test_worker_episode.py."""
    sys.path.insert(0, str(root))
    sys.path.insert(1, str(root / "checks"))

    def offline(event, args):
        if event in ("socket.connect", "socket.getaddrinfo"):
            raise RuntimeError("offline reset-invariance worker")

    sys.addaudithook(offline)
    from test_engine_semantics import EngineSemantics

    EngineSemantics.setUpClass()
    namespace = dict(globals(), InvalidArgument=ValueError, NotFound=FileNotFoundError)
    for path, names in [
        (root / "checks/reference/engine/utils.py", {"read_file"}),
        (
            root / "checks/reference/evaluator/official_agent.py",
            {"is_url", "get_last_callable", "build_agent"},
        ),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        if len(nodes) != len(names):
            raise AssertionError(f"raw-loader helper mismatch in {path}")
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    candidate, _ = namespace["build_agent"](str(root / "main.py"), {}, "kaggriculture")
    try:
        _entrypoint(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError("official lazy loader exposed main.py::agent before first invocation")
    return EngineSemantics, candidate


def _entrypoint(candidate):
    """Recover loaded main.py::agent without assuming raw-loader closure order."""
    for cell in candidate.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        globals_dict = getattr(value, "__globals__", None)
        if callable(value) and isinstance(globals_dict, dict) and "_INSTANCE" in globals_dict:
            return value
    raise AssertionError("official raw-loader closure does not expose main.py::agent")


def _configuration(engine, evaluator, seed: int):
    cfg = evaluator.Struct(
        {
            key: value.get("default") if isinstance(value, dict) else value
            for key, value in engine.specification["configuration"].items()
        }
    )
    cfg.seed = seed
    return cfg


def _call_candidate(candidate, observation, cfg):
    """One worker-thread call plus timeout-guard cleanup assertions."""
    action = candidate(observation, cfg)
    import titan_runtime

    if sys.gettrace() is not None:
        raise AssertionError("deadline trace hook leaked past candidate return")
    if titan_runtime.deadline._ACTIVE_TIMER.get() is not None:
        raise AssertionError("deadline ContextVar leaked past candidate return")
    return action


def _run_game(
    engine_semantics,
    candidate,
    executor: ThreadPoolExecutor,
    scenario: dict[str, int],
    prior_instance,
):
    engine = engine_semantics.engine
    evaluator = engine_semantics.ev
    cfg = _configuration(engine, evaluator, scenario["seed"])
    seat = scenario["seat"]
    rival = 1 - seat
    env = evaluator.Struct(configuration=cfg, done=False, info={})
    state = [
        evaluator.Struct(observation=evaluator.Struct(), action={}, status="ACTIVE", reward=0)
        for _ in range(2)
    ]
    engine.interpreter(state, env)

    if prior_instance is None:
        _warmup_worker_act(candidate, executor, state[seat].observation, cfg)

    trace = hashlib.sha256()
    loaded_entrypoint = None
    active_instance = None
    last_instance = None
    replacement_verified = False
    within_episode_discards = 0
    calls = 0
    last_step = None

    for step in range(720):
        for player in (0, 1):
            state[player].observation.step = step
        action = getattr(executor, "submit")(
            _call_candidate, candidate, copy.deepcopy(state[seat].observation), cfg
        ).result(timeout=2)
        if loaded_entrypoint is None:
            loaded_entrypoint = _entrypoint(candidate)
        encoded = json.dumps(action, sort_keys=True, separators=(",", ":"), allow_nan=False)
        current = loaded_entrypoint.__globals__.get("_INSTANCE")
        if current is None:
            if active_instance is None:
                globals_dict = loaded_entrypoint.__globals__
                spatial = globals_dict.get("_SPATIAL_RECOVERY")
                raw_route = globals_dict.get("_ROUTE_RECOVERY")
                normalize_route = globals_dict.get("_route_recovery_capsule")
                route = normalize_route(raw_route) if callable(normalize_route) else None
                spatial_ok = (
                    isinstance(spatial, dict)
                    and set(spatial) == {"last_step", "state"}
                    and spatial.get("last_step") == step
                )
                route_ok = (
                    isinstance(route, dict)
                    and route.get("last_step") == step
                    and route.get("player") == seat
                )
                prior_diagnostics = (
                    dict(getattr(last_instance, "diagnostics", {}) or {})
                    if last_instance is not None else {}
                )
                if (
                    last_instance is None
                    or prior_diagnostics.get("status") != "deadline_fallback"
                    or prior_diagnostics.get("entrypoint_guard") is not True
                    or last_step is None
                    or step != last_step + 1
                    or not (spatial_ok or route_ok)
                    or not isinstance(action, dict)
                ):
                    raise AssertionError((
                        "uncertified consecutive singleton absence",
                        scenario,
                        step,
                        {
                            "prior_entrypoint_guard": prior_diagnostics.get("entrypoint_guard"),
                            "prior_status": prior_diagnostics.get("status"),
                            "previous_step": last_step,
                            "spatial_recovery": spatial_ok,
                            "route_recovery": route_ok,
                            "valid_action_dict": isinstance(action, dict),
                        },
                    ))
            else:
                diagnostics = dict(active_instance.diagnostics)
                if (diagnostics.get("status") != "deadline_fallback"
                        or diagnostics.get("entrypoint_guard") is not True):
                    raise AssertionError(("unaccounted singleton discard", scenario, step, diagnostics))
                last_instance = active_instance
                active_instance = None
                within_episode_discards += 1
        else:
            diagnostics = dict(current.diagnostics)
            if (diagnostics.get("parent_calls") != 1
                    or diagnostics.get("status") not in ("completed", "deadline_fallback")):
                raise AssertionError(("non-returned action", scenario, step, diagnostics))
            if step == 0:
                if prior_instance is not None and current is prior_instance:
                    raise AssertionError(("step zero reused prior TitanAgent", scenario))
                active_instance = current
                replacement_verified = True
            elif active_instance is None:
                if last_instance is not None and current is last_instance:
                    raise AssertionError(("deadline-discarded TitanAgent was reused", scenario, step))
                active_instance = current
            elif current is not active_instance:
                raise AssertionError(("singleton changed without certified discard", scenario, step))
            last_instance = current

        trace.update(encoded.encode("utf-8") + b"\n")
        state[seat].action = json.loads(encoded)
        state[rival].action = engine.starter_agent(copy.deepcopy(state[rival].observation))
        engine.interpreter(state, env)
        calls += 1
        last_step = step
        if any(player.status == "DONE" for player in state):
            break

    if not replacement_verified or last_instance is None:
        raise AssertionError(("episode never verified singleton replacement", scenario))
    return {
        "seed": scenario["seed"],
        "seat": seat,
        "calls": calls,
        "last_step": last_step,
        "action_sha256": trace.hexdigest(),
        "status": [player.status for player in state],
        "rewards": [player.reward for player in state],
        "singleton_replaced": True,
        "within_episode_instance_discards": within_episode_discards,
        "deadline_guard_clean_after_every_call": True,
    }, last_instance


def _dynamic_module_files(root: Path) -> list[tuple[str, Path]]:
    source = (
        root
        if (root / "pressure_priority.py").is_file()
        else root.parent / "cloud-opponent-league/lark-responsive"
    )
    hist = root / "reference/titan-history"
    return [
        ("sell_priority", source / "sell_priority.py"),
        ("_titan_pressure_priority", source / "pressure_priority.py"),
        ("_titan_pressure_mechanics", root / "mechanics.py"),
        ("_titan_funding", root / "reference/titan-current/seed_funding.py"),
        ("_titan_seed_budget", root / "reference/integrated-selected/alder/seed_budget.py"),
        ("_titan_redundant_hire", root / "reference/titan-current/redundant_hire.py"),
        ("_titan_history_terminal_mechanics", hist / "terminal_mechanics.py"),
        ("_titan_history_selected_action_history", hist / "selected_action_history.py"),
        ("_titan_history_observed_fills", hist / "observed_fills.py"),
        ("_titan_history_flow", hist / "flow.py"),
        ("_titan_history_scenario_adapter", hist / "scenario_adapter.py"),
    ]


def _prewarm_dynamic_modules(root: Path) -> list[str]:
    """Load known dynamic modules on the calling thread through the cached loader.

    Hosted AB/BA traces still diverged after main-thread prewarm with swallowed
    load failures (Actions 35164150054: scenario A 8 vs 7 discards). Load
    present files fail-closed on this thread, which must be the persistent
    worker thread that later runs candidate calls.
    """
    import titan_runtime

    loader = getattr(titan_runtime, "load")
    loaded: list[str] = []
    for mod_name, mod_file in _dynamic_module_files(root):
        if not mod_file.is_file():
            continue
        loader(mod_name, mod_file, cache=True)
        loaded.append(mod_name)
    return loaded


def _clear_loaded_instance(candidate) -> None:
    entry = _entrypoint(candidate)
    entry.__globals__["_INSTANCE"] = None


def _warmup_worker_act(candidate, executor: ThreadPoolExecutor, observation, cfg) -> None:
    """Compile the worker-thread act() path, then drop the warmup singleton."""
    getattr(executor, "submit")(
        _call_candidate, candidate, copy.deepcopy(observation), cfg
    ).result(timeout=5)
    _clear_loaded_instance(candidate)


def _worker(root: Path, order: list[str]) -> dict[str, Any]:
    engine_semantics, candidate = _load_official(root)
    results = {}
    prior_instance = None
    with ThreadPoolExecutor(1) as executor:
        getattr(executor, "submit")(_prewarm_dynamic_modules, root).result(timeout=30)
        for name in order:
            result, prior_instance = _run_game(
                engine_semantics, candidate, executor, SCENARIOS[name], prior_instance
            )
            results[name] = result

    import titan_runtime

    cache_keys = sorted(f"{name}:{Path(path).name}" for name, path in titan_runtime._MODULE_CACHE)
    return {
        "method": (
            "Exact official raw-loader helpers + official interpreter; same candidate callable "
            "on one persistent worker thread for two full games; offline; reverse-order differential"
        ),
        "order": order,
        "results": results,
        "module_cache_keys": cache_keys,
        "engine_sha256": engine_semantics.hashes,
        "raw_loader_sha256": hashlib.sha256(
            (root / "checks/reference/evaluator/official_agent.py").read_bytes()
        ).hexdigest(),
        "source_manifest_sha256": hashlib.sha256((root / "SOURCE.json").read_bytes()).hexdigest(),
    }


def _run_worker(script: Path, root: Path, order: list[str], output: Path):
    process = getattr(subprocess, "run")(
        [
            sys.executable,
            "-I",
            str(script),
            "--worker",
            str(root),
            "--order",
            *order,
            "--output",
            str(output),
        ],
        cwd=root.parent,
        capture_output=True,
        text=True,
        timeout=360,
    )
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)
    return json.loads(output.read_text(encoding="utf-8"))


_IDENTITY_KEYS = (
    "seed",
    "seat",
    "calls",
    "last_step",
    "action_sha256",
    "status",
    "rewards",
    "singleton_replaced",
    "deadline_guard_clean_after_every_call",
)


def _scenario_projection(result: dict[str, Any], name: str):
    """Order-invariant game identity. Discard counts are wall-clock diagnostics."""
    game = result["results"][name]
    return {key: game[key] for key in _IDENTITY_KEYS}


def _verify() -> dict[str, Any]:
    from build_integrated import verify_current

    receipt = verify_current()
    archive = ROOT / "exports/titan-current.tar.gz"
    with tempfile.TemporaryDirectory(prefix="titan-reset-clean-", dir="/tmp") as folder:
        base = Path(folder)
        extracted = base / "candidate"
        extracted.mkdir()
        with tarfile.open(archive) as stream:
            stream.extractall(extracted, filter="data")
        ab_path = base / "ab.json"
        ba_path = base / "ba.json"
        ab = _run_worker(Path(__file__).resolve(), extracted, ["A", "B"], ab_path)
        ba = _run_worker(Path(__file__).resolve(), extracted, ["B", "A"], ba_path)

    mismatches = {}
    for name in sorted(SCENARIOS):
        first = _scenario_projection(ab, name)
        second = _scenario_projection(ba, name)
        if first != second:
            mismatches[name] = {"AB": first, "BA": second}
    if ab["module_cache_keys"] != ba["module_cache_keys"]:
        mismatches["module_cache_keys"] = {
            "AB": ab["module_cache_keys"],
            "BA": ba["module_cache_keys"],
        }
    if mismatches:
        raise AssertionError(json.dumps(mismatches, indent=2, sort_keys=True))

    return {
        "schema": "titan-v4-reset-invariance/v1",
        "archive_sha256": receipt["sha256"],
        "source_manifest_sha256": ab["source_manifest_sha256"],
        "raw_loader_sha256": ab["raw_loader_sha256"],
        "engine_sha256": ab["engine_sha256"],
        "orders": [ab["order"], ba["order"]],
        "scenarios": {name: _scenario_projection(ab, name) for name in sorted(SCENARIOS)},
        "module_cache_keys": ab["module_cache_keys"],
        "result": "PASS",
        "claim": (
            "For these two full official-interpreter games on one persistent worker thread, "
            "action trace and terminal result are identical whether the game runs first in a "
            "fresh process or second after the other game; step zero replaces the prior "
            "TitanAgent singleton, certified outer-deadline discards reconstruct a fresh "
            "instance, and deadline guard state is clean after every call."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--order", nargs="+", choices=sorted(SCENARIOS))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check-sources",
        action="store_true",
        help="Fail if any build_integrated.source_files() origin is missing",
    )
    parser.add_argument(
        "--materialize-live",
        type=Path,
        help="Copy the lab plus attributed root modules to DEST and exit",
    )
    args = parser.parse_args()
    if args.check_sources:
        missing = missing_mapped_sources()
        if missing:
            raise SystemExit("missing mapped sources:\n" + "\n".join(missing))
        print(json.dumps({"result": "PASS", "mapped_sources": "present"}))
        return 0
    if args.materialize_live is not None:
        dest = materialize_live_worker_root(ROOT, args.materialize_live)
        print(json.dumps({"result": "PASS", "live_root": str(dest)}))
        return 0
    if args.worker is not None:
        if not args.order or args.output is None:
            parser.error("--worker requires --order and --output")
        report = _worker(args.worker, args.order)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    if args.order or args.output:
        parser.error("--order/--output are worker-only")
    print(json.dumps(_verify(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())