# SPDX-License-Identifier: Apache-2.0
"""Run a complete paired official-engine panel for TITAN L02 versus canonical.

Each cell is evaluated twice against the same opponent/seed/seat: once with the
unchanged canonical entrypoint and once with L02. Evaluator invocations are
sharded only by disjoint seed sets. The runner rejects missing, extra, duplicate,
incomplete, nonfinite, or provenance-drifted cells before computing deltas.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if HERE.parent.name == "candidates" and HERE.parent.parent.name == "cloud-execution-lab":
    LAB = HERE.parents[1]
    KAG = HERE.parents[2]
    REPO = HERE.parents[4]
else:  # Importable in an isolated unit-test scratch directory.
    LAB = HERE
    KAG = HERE
    REPO = HERE
EVALUATOR = KAG / "cloud-eval" / "evaluate.py"
LOADER = KAG / "20260907-offline-agent" / "evaluate.py"
ENGINE = LAB / "reference" / "engine"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
DEFAULT_SEEDS = tuple(range(2611092201, 2611092209))
OPPONENTS = {
    "arlene": LAB / "runtime/variants/v1/reference/next-panel/vendor/arlene.py",
    "apex": KAG / "cloud-policy-portfolio/vendor/apex/main.py",
    "kaito_v43": KAG / "cloud-frontier-policy/vendor/kaito_v43.py",
    "cok_v10": KAG / "cloud-policy-portfolio/revision2/vendor/opponents/cok-v10.py",
    "public_bt12": KAG / "cloud-frontier-decision/public-opponent/submission.py",
    "v1": LAB / "runtime/variants/v1/candidate.py",
}
ISOLATED_IMPORT_PROBE = (
    "from observed_clone import detached_json_value\n"
    "import scheduler\n"
    "assert callable(detached_json_value)\n"
)
EVALUATOR_ENV_SEAM = '''        env = {"PATH": os.defpath, "HOME": self.directory.name, "LANG": "C.UTF-8",
               "PYTHONHASHSEED": str(rng_seed % (2**32)), "PYTHONDONTWRITEBYTECODE": "1"}'''



def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def cell_failure_reason(game: Mapping[str, Any], *, limit: int = 240) -> str:
    """Compact cell failure for logs and markdown; never embed observations.

    Official evaluator RPC failures retain the request wire, including the full
    observation. GitHub Actions run 34400397411 stringified that blob into every
    collect_games error and then catted L02-PANEL.json into GITHUB_STEP_SUMMARY
    (1024 KiB cap). Keep kind/step/error only.
    """
    parts: list[str] = []
    status = game.get("status")
    if status not in (None, ""):
        parts.append(str(status))
    failure = game.get("failure")
    if failure is None:
        if game.get("scores") is None:
            parts.append("missing scores")
        return _clip(" ".join(parts) or "invalid cell", limit)
    if isinstance(failure, str):
        parts.append(failure)
        return _clip(" ".join(parts), limit)
    if not isinstance(failure, Mapping):
        parts.append(type(failure).__name__)
        return _clip(" ".join(parts), limit)
    for key in ("phase", "kind"):
        value = failure.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    if failure.get("step") is not None:
        parts.append(f"step={failure['step']}")
    if failure.get("seat") is not None:
        parts.append(f"seat={failure['seat']}")
    error = failure.get("error")
    rpc = failure.get("rpc_failure")
    if error in (None, "") and isinstance(rpc, Mapping):
        error = rpc.get("error")
    if error not in (None, ""):
        parts.append(_clip(str(error).splitlines()[0], 160))
    return _clip(" ".join(parts) or "invalid cell", limit)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def isolated_source_pythonpath(lab: Path) -> str:
    """Bare imports in stripped official workers resolve archive siblings.

    The official evaluator copies a PATH/HOME/LANG-only environment into each
    worker and inserts only the agent parent. Root modules that
    ``build_integrated.source_files`` maps from outside the lab
    (``observed_clone``, ``seller_snapshot``, …) must therefore appear on
    PYTHONPATH. GitHub Actions run 34400397411 failed every L02 cell at step 0
    with ``ModuleNotFoundError: No module named 'observed_clone'``.
    """
    lab = lab.resolve()
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files
    ordered = [lab]
    seen = {lab}
    for member, source in source_files().items():
        if Path(member).parent != Path("."):
            continue
        origin = (lab / source).resolve()
        if not origin.is_file():
            raise FileNotFoundError(
                f"mapped root module {member} missing at {origin}")
        parent = origin.parent
        if parent not in seen:
            seen.add(parent)
            ordered.append(parent)
    return os.pathsep.join(str(path) for path in ordered)


def patch_evaluator(source: Path, target: Path) -> None:
    """Forward the isolated source path into stripped worker environments."""
    text = source.read_text(encoding="utf-8")
    new = EVALUATOR_ENV_SEAM + '''
        if os.environ.get("TITAN_L02_PYTHONPATH"):
            env["PYTHONPATH"] = os.environ["TITAN_L02_PYTHONPATH"]'''
    if text.count(EVALUATOR_ENV_SEAM) != 1:
        raise RuntimeError("evaluator environment seam changed")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.replace(EVALUATOR_ENV_SEAM, new), encoding="utf-8")


def assert_isolated_source_imports(lab: Path, pythonpath: str) -> None:
    """Fail closed before the 192-game panel if stripped workers cannot import."""
    with tempfile.TemporaryDirectory(prefix="kag-eval-agent-") as tmp:
        env = {
            "PATH": os.defpath,
            "HOME": tmp,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": pythonpath,
        }
        result = subprocess.run(
            [sys.executable, "-B", "-c", ISOLATED_IMPORT_PROBE],
            cwd=tmp, env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "isolated official-panel workers cannot import lab source: "
                + (result.stderr or result.stdout)[:1500]
            )


def tree_sha256(root: Path) -> dict[str, Any]:
    """Hash a declared source bundle, excluding generated caches/native output."""
    root = root.resolve()
    if root.is_file():
        return {"root": str(root), "files": 1, "sha256": sha256_file(root)}
    if not root.is_dir():
        raise FileNotFoundError(root)
    ignored_names = {"__pycache__", ".pytest_cache"}
    ignored_suffixes = {".pyc", ".pyo", ".so", ".dylib", ".dll"}
    files = [path for path in root.rglob("*")
             if path.is_file() and not path.is_symlink()
             and not any(part in ignored_names for part in path.relative_to(root).parts)
             and path.suffix not in ignored_suffixes]
    digest = hashlib.sha256()
    entries = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        content_digest = sha256_file(path)
        digest.update(relative.encode("utf-8") + b"\0" + bytes.fromhex(content_digest))
        entries.append({"path": relative, "sha256": content_digest, "bytes": path.stat().st_size})
    return {"root": str(root), "files": len(entries), "sha256": digest.hexdigest(),
            "entries": entries}


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def shard(items: Sequence[int], workers: int) -> list[list[int]]:
    groups = [[] for _ in range(max(1, min(workers, len(items))))]
    for index, item in enumerate(items):
        groups[index % len(groups)].append(item)
    return [group for group in groups if group]


def _agent_spec(variant: str) -> str:
    path = LAB / "main.py" if variant == "baseline" else HERE / "candidate.py"
    return str(path.resolve()) + "::agent"


def _opponent_args(names: Sequence[str]) -> list[str]:
    args: list[str] = []
    for name in names:
        path = OPPONENTS[name]
        args.extend(("--opponent", f"{name}={path.resolve()}::agent"))
    return args


def run_evaluator(variant: str, seeds: Sequence[int], opponents: Sequence[str],
                  directory: Path, shard_index: int, *, action_timeout: float,
                  startup_timeout: float, game_timeout: float,
                  evaluator: Path, pythonpath: str) -> dict[str, Any]:
    output = directory / f"{variant}-shard-{shard_index:02d}.json"
    command = [
        sys.executable, "-B", str(evaluator),
        "--engine-dir", str(ENGINE),
        "--loader", str(LOADER),
        "--candidate", _agent_spec(variant),
        "--seeds", ",".join(str(seed) for seed in seeds),
        "--rng-seed", "20260909",
        "--action-timeout", str(action_timeout),
        "--startup-timeout", str(startup_timeout),
        "--game-timeout", str(game_timeout),
        "--output", str(output),
        *_opponent_args(opponents),
    ]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TITAN_L02_PYTHONPATH"] = pythonpath
    completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                               env=env,
                               timeout=max(300.0, game_timeout * len(seeds) * len(opponents) * 2 + 120.0))
    report = None
    if output.is_file():
        report = json.loads(output.read_text(encoding="utf-8"))
    return {
        "variant": variant,
        "shard": shard_index,
        "seeds": list(seeds),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "report_path": str(output),
        "report": report,
    }


def expected_keys(seeds: Sequence[int], opponents: Sequence[str]) -> set[tuple[str, int, int]]:
    return {(opponent, int(seed), seat)
            for opponent in opponents for seed in seeds for seat in (0, 1)}


def collect_games(results: Iterable[Mapping[str, Any]], variant: str,
                  seeds: Sequence[int], opponents: Sequence[str],
                  *, expected_candidate_sha256: str | None = None,
                  expected_opponent_sha256: Mapping[str, str] | None = None,
                  expected_evaluator_sha256: str | None = None,
                  expected_loader_sha256: str | None = None
                  ) -> tuple[dict[tuple[str, int, int], dict], dict]:
    expected = expected_keys(seeds, opponents)
    games: dict[tuple[str, int, int], dict] = {}
    errors: list[str] = []
    provenance: list[dict[str, Any]] = []
    for result in results:
        if result.get("variant") != variant:
            continue
        if result.get("returncode") != 0:
            errors.append(f"shard {result.get('shard')} return code {result.get('returncode')}")
        report = result.get("report")
        if not isinstance(report, dict):
            errors.append(f"shard {result.get('shard')} missing final report")
            continue
        if report.get("schema_version") != 1 or report.get("engine_ref") != ENGINE_REF:
            errors.append(f"shard {result.get('shard')} evaluator provenance mismatch")
        candidate_evidence = report.get("candidate") or {}
        if expected_candidate_sha256 is not None and candidate_evidence.get("sha256") != expected_candidate_sha256:
            errors.append(f"shard {result.get('shard')} candidate entry digest mismatch")
        for opponent, expected_digest in dict(expected_opponent_sha256 or {}).items():
            evidence = (report.get("opponents") or {}).get(opponent) or {}
            if evidence.get("sha256") != expected_digest:
                errors.append(f"shard {result.get('shard')} opponent digest mismatch: {opponent}")
        if (expected_evaluator_sha256 is not None
                and report.get("evaluator_sha256") != expected_evaluator_sha256):
            errors.append(f"shard {result.get('shard')} evaluator digest mismatch")
        if (expected_loader_sha256 is not None
                and report.get("loader_sha256") != expected_loader_sha256):
            errors.append(f"shard {result.get('shard')} loader digest mismatch")
        progress = report.get("progress") or {}
        if progress.get("state") != "complete":
            errors.append(f"shard {result.get('shard')} not complete: {progress.get('state')}")
        provenance.append({
            "shard": result.get("shard"),
            "candidate": report.get("candidate"),
            "opponents": report.get("opponents"),
            "engine_sha256": report.get("engine_sha256"),
            "loader_sha256": report.get("loader_sha256"),
            "evaluator_sha256": report.get("evaluator_sha256"),
            "limits": report.get("limits"),
        })
        for game in report.get("games", []):
            try:
                key = (str(game["opponent"]), int(game["seed"]), int(game["candidate_seat"]))
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"malformed game key: {type(exc).__name__}")
                continue
            if key in games:
                errors.append(f"duplicate cell {key}")
                continue
            scores = game.get("scores")
            valid_scores = (isinstance(scores, list) and len(scores) == 2 and
                            all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                and math.isfinite(value) for value in scores))
            if game.get("status") != "complete" or game.get("failure") is not None or not valid_scores:
                errors.append(
                    f"incomplete or invalid cell {key}: {cell_failure_reason(game)}")
                continue
            if not isinstance(game.get("trace_sha256"), str) or len(game["trace_sha256"]) != 64:
                errors.append(f"missing trace digest {key}")
                continue
            games[key] = dict(game)
    actual = set(games)
    missing, extra = sorted(expected - actual), sorted(actual - expected)
    if missing:
        errors.append(f"missing cells: {missing[:8]}{' ...' if len(missing) > 8 else ''}")
    if extra:
        errors.append(f"extra cells: {extra[:8]}{' ...' if len(extra) > 8 else ''}")
    return games, {"valid": not errors, "errors": errors, "expected": len(expected),
                   "accepted": len(games), "provenance": provenance}


def _outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "T"


def pair_games(baseline: Mapping[tuple[str, int, int], Mapping[str, Any]],
               candidate: Mapping[tuple[str, int, int], Mapping[str, Any]]) -> list[dict[str, Any]]:
    if set(baseline) != set(candidate):
        raise ValueError("baseline/candidate cells are not identical")
    rows = []
    for key in sorted(baseline):
        opponent, seed, seat = key
        base, cand = baseline[key], candidate[key]
        base_own = float(base["scores"][seat]); base_rival = float(base["scores"][1-seat])
        cand_own = float(cand["scores"][seat]); cand_rival = float(cand["scores"][1-seat])
        base_margin = base_own - base_rival; cand_margin = cand_own - cand_rival
        rows.append({
            "opponent": opponent, "seed": seed, "candidate_seat": seat,
            "baseline_scores": base["scores"], "candidate_scores": cand["scores"],
            "baseline_own": base_own, "candidate_own": cand_own,
            "own_delta": cand_own - base_own,
            "baseline_margin": base_margin, "candidate_margin": cand_margin,
            "margin_delta": cand_margin - base_margin,
            "baseline_outcome": _outcome(base_margin),
            "candidate_outcome": _outcome(cand_margin),
            "trace_changed": base["trace_sha256"] != cand["trace_sha256"],
            "baseline_trace_sha256": base["trace_sha256"],
            "candidate_trace_sha256": cand["trace_sha256"],
        })
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"cells": 0}
    own = [float(row["own_delta"]) for row in rows]
    margin = [float(row["margin_delta"]) for row in rows]
    flips = Counter((row["baseline_outcome"], row["candidate_outcome"]) for row in rows)
    return {
        "cells": len(rows),
        "mean_own_delta": statistics.fmean(own),
        "median_own_delta": statistics.median(own),
        "min_own_delta": min(own), "max_own_delta": max(own),
        "positive_own_cells": sum(value > 0 for value in own),
        "zero_own_cells": sum(value == 0 for value in own),
        "negative_own_cells": sum(value < 0 for value in own),
        "mean_margin_delta": statistics.fmean(margin),
        "median_margin_delta": statistics.median(margin),
        "min_margin_delta": min(margin), "max_margin_delta": max(margin),
        "trace_changed_cells": sum(bool(row["trace_changed"]) for row in rows),
        "outcome_transitions": {f"{a}->{b}": count for (a, b), count in sorted(flips.items())},
    }


def stratify(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    values: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        values.setdefault(str(row[key]), []).append(row)
    return {name: summarize(group) for name, group in sorted(values.items())}


def verdict(global_summary: Mapping[str, Any], per_opponent: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks = {
        "behavior_activated": int(global_summary.get("trace_changed_cells", 0)) > 0,
        "positive_global_own_cash": float(global_summary.get("mean_own_delta", 0.0)) > 0,
        "positive_global_margin": float(global_summary.get("mean_margin_delta", 0.0)) > 0,
        "four_of_six_nonnegative_strata": sum(
            float(row.get("mean_own_delta", 0.0)) >= 0 for row in per_opponent.values()) >= 4,
        "arlene_nonnegative": float(per_opponent.get("arlene", {}).get("mean_own_delta", -math.inf)) >= 0,
        "v1_nonnegative": float(per_opponent.get("v1", {}).get("mean_own_delta", -math.inf)) >= 0,
        "no_large_stratum_regression": all(
            float(row.get("mean_own_delta", -math.inf)) >= -500 for row in per_opponent.values()),
    }
    return {"decision": "ADVANCE" if all(checks.values()) else "REJECT",
            "checks": checks, "scope": "development panel only; not a Kaggle or leaderboard claim"}


def dependency_receipt(head: str, *, evaluator: Path | None = None) -> dict[str, Any]:
    evaluator_path = Path(evaluator) if evaluator is not None else EVALUATOR
    paths = {
        "candidate": HERE / "candidate.py",
        "overlay": HERE / "ledger_tranche.py",
        "canonical_main": LAB / "main.py",
        "titan_runtime": LAB / "titan_runtime.py",
        "frozen_selected": LAB / "frozen_selected.py",
        "scheduler": LAB / "scheduler.py",
        "config": LAB / "TITAN-CONFIG.json",
        "source_manifest": LAB / "runtime/integrated-selected/CURRENT-SOURCE.json",
        "evaluator": evaluator_path,
        "evaluator_source": EVALUATOR,
        "loader": LOADER,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing dependency paths: " + ", ".join(missing))
    bundles = {
        "arlene": OPPONENTS["arlene"],
        "apex": OPPONENTS["apex"].parent,
        "kaito_v43": OPPONENTS["kaito_v43"],
        "cok_v10": OPPONENTS["cok_v10"],
        "public_bt12": OPPONENTS["public_bt12"].parent,
        "v1": OPPONENTS["v1"].parent,
    }
    receipt = {
        "git_head": head,
        "sha256": {name: sha256_file(path) for name, path in paths.items()},
        "opponent_entries": {name: sha256_file(path) for name, path in OPPONENTS.items()},
        "opponent_bundles": {name: tree_sha256(root) for name, root in bundles.items()},
    }
    apex_binary = OPPONENTS["apex"].parent / "agent.so"
    if apex_binary.is_file():
        receipt["generated_apex_binary"] = {"sha256": sha256_file(apex_binary),
                                               "bytes": apex_binary.stat().st_size}
    return receipt


def markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = ["# TITAN L02 ledger-coherent tranche — development panel", "",
             f"Verdict: **{report['verdict']['decision']}**", "",
             f"Cells: {summary['cells']}; trace-changed: {summary['trace_changed_cells']}",
             f"Mean own-cash delta: {summary['mean_own_delta']:.3f}",
             f"Mean margin delta: {summary['mean_margin_delta']:.3f}", "",
             "| Opponent | Cells | Mean own Δ | Mean margin Δ | + / 0 / - |",
             "|---|---:|---:|---:|---:|"]
    for name, row in report["per_opponent"].items():
        lines.append(f"| {name} | {row['cells']} | {row['mean_own_delta']:.3f} | "
                     f"{row['mean_margin_delta']:.3f} | {row['positive_own_cells']} / "
                     f"{row['zero_own_cells']} / {row['negative_own_cells']} |")
    lines += ["", "## Gate", ""]
    for name, passed in report["verdict"]["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
    lines += ["", report["verdict"]["scope"], ""]
    return "\n".join(lines)


def failure_markdown(payload: Mapping[str, Any]) -> str:
    """Always-write compact receipt so CI never cats the failed JSON blob."""
    errors = [str(item) for item in list(payload.get("errors") or [])]
    extra = payload.get("error")
    if extra not in (None, ""):
        errors = [_clip(str(extra), 240), *errors]
    shown = errors[:24]
    lines = [
        "# TITAN L02 ledger-coherent tranche — development panel",
        "",
        f"Status: **{payload.get('status', 'failed')}**",
        f"Stage: `{payload.get('stage', 'unknown')}`",
        "",
        f"Compact errors: {len(errors)} (observations omitted)",
        "",
    ]
    for item in shown:
        lines.append(f"- {item}")
    if len(errors) > len(shown):
        lines.append(f"- … {len(errors) - len(shown)} more compact errors retained in JSON")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    parser.add_argument("--opponents", default=",".join(OPPONENTS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--action-timeout", type=float, default=1.0)
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--game-timeout", type=float, default=180.0)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    seeds = [int(part) for part in args.seeds.split(",") if part]
    opponents = [part for part in args.opponents.split(",") if part]
    if len(seeds) != len(set(seeds)) or not seeds:
        parser.error("seeds must be distinct and nonempty")
    if len(opponents) != len(set(opponents)) or not opponents or any(name not in OPPONENTS for name in opponents):
        parser.error("opponents must be distinct known names")
    if args.workers <= 0 or any(not math.isfinite(value) or value <= 0 for value in
                                (args.action_timeout, args.startup_timeout, args.game_timeout)):
        parser.error("workers/timeouts must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pythonpath = isolated_source_pythonpath(LAB)
    work = args.output.parent / "shards"
    work.mkdir(parents=True, exist_ok=True)
    patched_evaluator = work / "evaluate-l02.py"
    patch_evaluator(EVALUATOR, patched_evaluator)
    assert_isolated_source_imports(LAB, pythonpath)
    receipt = dependency_receipt(args.head, evaluator=patched_evaluator)
    initial = {"schema_version": 1, "status": "running", "phase": "development",
               "identity": receipt, "seeds": seeds, "opponents": opponents,
               "expected_cells_per_variant": len(expected_keys(seeds, opponents)),
               "isolated_pythonpath": pythonpath.split(os.pathsep)}
    atomic_json(args.output, initial)
    groups = shard(seeds, args.workers)
    futures = []
    results: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=len(groups)) as executor:
            for index, group in enumerate(groups):
                for variant in ("baseline", "candidate"):
                    futures.append(executor.submit(
                        run_evaluator, variant, group, opponents, work, index,
                        action_timeout=args.action_timeout, startup_timeout=args.startup_timeout,
                        game_timeout=args.game_timeout, evaluator=patched_evaluator,
                        pythonpath=pythonpath))
            for future in as_completed(futures):
                results.append(future.result())
                initial["completed_shards"] = [{"variant": result["variant"],
                                                 "shard": result["shard"],
                                                 "returncode": result["returncode"]}
                                                for result in results]
                atomic_json(args.output, initial)

        opponent_entry_digests = {name: receipt["opponent_entries"][name] for name in opponents}
        baseline, baseline_gate = collect_games(
            results, "baseline", seeds, opponents,
            expected_candidate_sha256=receipt["sha256"]["canonical_main"],
            expected_opponent_sha256=opponent_entry_digests,
            expected_evaluator_sha256=receipt["sha256"]["evaluator"],
            expected_loader_sha256=receipt["sha256"]["loader"])
        candidate, candidate_gate = collect_games(
            results, "candidate", seeds, opponents,
            expected_candidate_sha256=receipt["sha256"]["candidate"],
            expected_opponent_sha256=opponent_entry_digests,
            expected_evaluator_sha256=receipt["sha256"]["evaluator"],
            expected_loader_sha256=receipt["sha256"]["loader"])
        errors = baseline_gate["errors"] + candidate_gate["errors"]
        if errors:
            failed = dict(initial)
            failed.update(status="failed", stage="validation", errors=errors,
                          baseline_gate=baseline_gate, candidate_gate=candidate_gate)
            atomic_json(args.output, failed)
            args.markdown.write_text(failure_markdown(failed), encoding="utf-8")
            return 2
        rows = pair_games(baseline, candidate)
        global_summary = summarize(rows)
        per_opponent = stratify(rows, "opponent")
        report = {
            **initial,
            "status": "complete",
            "baseline_gate": baseline_gate,
            "candidate_gate": candidate_gate,
            "summary": global_summary,
            "per_opponent": per_opponent,
            "per_seat": stratify(rows, "candidate_seat"),
            "verdict": verdict(global_summary, per_opponent),
            "cells": rows,
        }
        atomic_json(args.output, report)
        args.markdown.write_text(markdown(report), encoding="utf-8")
        print(json.dumps({"status": report["status"], "summary": global_summary,
                          "verdict": report["verdict"]}, sort_keys=True))
        return 0 if report["verdict"]["decision"] == "ADVANCE" else 3
    except BaseException as exc:
        failed = dict(initial)
        failed.update(status="failed", stage="execution",
                      error=f"{type(exc).__name__}: {exc}"[:2000])
        try:
            atomic_json(args.output, failed)
            args.markdown.write_text(failure_markdown(failed), encoding="utf-8")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
