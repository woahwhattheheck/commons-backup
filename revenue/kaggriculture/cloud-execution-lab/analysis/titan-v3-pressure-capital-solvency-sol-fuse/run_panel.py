# SPDX-License-Identifier: Apache-2.0
"""Run the exact-current pressure/capital interlock through a paired panel."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
KAG = LAB.parent
RUNNER_SOURCE = LAB / "candidates" / "v3-l02-ledger-tranche" / "run_panel.py"
BASE_COMMIT = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"


def _load(name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_RUNNER = _load("_sol_fuse_paired_runner", RUNNER_SOURCE)


def _agent_spec(variant: str) -> str:
    path = LAB / "main.py" if variant == "baseline" else HERE / "candidate.py"
    return str(path.resolve()) + "::agent"


def dependency_receipt(head: str, *, evaluator: Path | None = None) -> dict[str, Any]:
    evaluator_path = Path(evaluator) if evaluator is not None else _RUNNER.EVALUATOR
    paths = {
        "candidate": HERE / "candidate.py",
        "guard": HERE / "pressure_capital_solvent.py",
        "panel_runner": HERE / "run_panel.py",
        "guard_tests": HERE / "test_pressure_capital_solvent.py",
        "candidate_tests": HERE / "test_candidate.py",
        "canonical_main": LAB / "main.py",
        "titan_runtime": LAB / "titan_runtime.py",
        "early_capital": LAB / "early_capital.py",
        "pressure_priority": KAG / "cloud-opponent-league/lark-responsive/pressure_priority.py",
        "scheduler": LAB / "scheduler.py",
        "config": LAB / "TITAN-CONFIG.json",
        "source_manifest": LAB / "runtime/integrated-selected/CURRENT-SOURCE.json",
        "evaluator": evaluator_path,
        "evaluator_source": _RUNNER.EVALUATOR,
        "loader": _RUNNER.LOADER,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing dependency paths: " + ", ".join(missing))
    bundles = {
        "arlene": _RUNNER.OPPONENTS["arlene"],
        "apex": _RUNNER.OPPONENTS["apex"].parent,
        "kaito_v43": _RUNNER.OPPONENTS["kaito_v43"],
        "cok_v10": _RUNNER.OPPONENTS["cok_v10"],
        "public_bt12": _RUNNER.OPPONENTS["public_bt12"].parent,
        "v1": _RUNNER.OPPONENTS["v1"].parent,
    }
    return {
        "git_head": head,
        "base_commit": BASE_COMMIT,
        "sha256": {name: _RUNNER.sha256_file(path) for name, path in paths.items()},
        "opponent_entries": {
            name: _RUNNER.sha256_file(path) for name, path in _RUNNER.OPPONENTS.items()
        },
        "opponent_bundles": {
            name: _RUNNER.tree_sha256(root) for name, root in bundles.items()
        },
        "analysis_bundle": _RUNNER.tree_sha256(HERE),
    }


def verdict(global_summary: Mapping[str, Any],
            per_opponent: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    transitions = dict(global_summary.get("outcome_transitions") or {})
    regressions = sum(int(transitions.get(key, 0)) for key in ("W->T", "W->L", "T->L"))
    checks = {
        "behavior_activated": int(global_summary.get("trace_changed_cells", 0)) > 0,
        "positive_global_own_cash": float(global_summary.get("mean_own_delta", 0.0)) > 0,
        "positive_global_margin": float(global_summary.get("mean_margin_delta", 0.0)) > 0,
        "nonnegative_global_median_own_cash":
            float(global_summary.get("median_own_delta", -math.inf)) >= 0,
        "no_outcome_regressions": regressions == 0,
        "no_large_opponent_regression": all(
            float(row.get("mean_own_delta", -math.inf)) >= -100
            for row in per_opponent.values()),
        "v1_nonnegative": float(per_opponent.get("v1", {}).get(
            "mean_own_delta", -math.inf)) >= 0,
        "arlene_nonnegative": float(per_opponent.get("arlene", {}).get(
            "mean_own_delta", -math.inf)) >= 0,
    }
    return {
        "decision": "ADVANCE" if all(checks.values()) else "REJECT",
        "checks": checks,
        "outcome_regressions": regressions,
        "scope": ("Development panel only. ADVANCE authorizes a separate one-tree "
                  "composition review; it is not a Kaggle, leaderboard, merge, or "
                  "canonical-release authorization."),
    }


def markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    decision = report["verdict"]
    lines = [
        "# TITAN final-pressure acquisition-solvency interlock — development panel",
        "",
        f"Verdict: **{decision['decision']}**",
        "",
        f"Paired cells: {summary['cells']}",
        f"Trace-changed cells: {summary['trace_changed_cells']}",
        f"Mean / median own-cash delta: {summary['mean_own_delta']:.3f} / "
        f"{summary['median_own_delta']:.3f}",
        f"Minimum / maximum own-cash delta: {summary['min_own_delta']:.3f} / "
        f"{summary['max_own_delta']:.3f}",
        f"Mean margin delta: {summary['mean_margin_delta']:.3f}",
        f"Outcome regressions: {decision['outcome_regressions']}",
        "",
        "| Opponent | Cells | Mean own Δ | Mean margin Δ | + / 0 / - | Trace changed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["per_opponent"].items():
        lines.append(
            f"| {name} | {row['cells']} | {row['mean_own_delta']:.3f} | "
            f"{row['mean_margin_delta']:.3f} | {row['positive_own_cells']} / "
            f"{row['zero_own_cells']} / {row['negative_own_cells']} | "
            f"{row['trace_changed_cells']} |"
        )
    lines += ["", "## Gate", ""]
    for name, passed in decision["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
    lines += ["", decision["scope"], ""]
    return "\n".join(lines)


def failure_markdown(payload: Mapping[str, Any]) -> str:
    text = _RUNNER.failure_markdown(payload)
    return text.replace(
        "# TITAN L02 ledger-coherent tranche — development panel",
        "# TITAN final-pressure acquisition-solvency interlock — development panel",
        1,
    )


def main(argv: Sequence[str] | None = None) -> int:
    _RUNNER._agent_spec = _agent_spec
    _RUNNER.dependency_receipt = dependency_receipt
    _RUNNER.verdict = verdict
    _RUNNER.markdown = markdown
    _RUNNER.failure_markdown = failure_markdown
    return int(_RUNNER.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
