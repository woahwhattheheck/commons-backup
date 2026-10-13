# SPDX-License-Identifier: Apache-2.0
"""Run the exact-current T01 carrier through a paired official-engine panel."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from audit import audit_cell, panel_verdict

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
KAG = LAB.parent
REPO = LAB.parents[2]
SOURCE_RUNNER = LAB / "candidates" / "v3-l02-ledger-tranche" / "run_panel.py"
SETTLEMENT_SOURCE = LAB / "candidates" / "v3-terminal-settlement" / "terminal_settlement.py"
BASE_COMMIT = "b986558e41938d34fcb4ab28b08c517be51203dc"
EXPECTED_CELLS = 32

if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))


def _load(name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_RUNNER = _load("_sol_settle_paired_runner", SOURCE_RUNNER)
_SETTLEMENT = _load("_sol_settle_recomputed_certificate", SETTLEMENT_SOURCE)

# The exact current archive is assembled from root modules that intentionally
# live outside cloud-execution-lab (observed_clone, seller_snapshot, etc.). The
# inherited runner already derives this source-root closure for stripped
# official workers. Apply the same ordered roots in this parent process before
# importing scheduler.post_units for audit recomputation; otherwise importing
# lab scheduler.py fails before game 1 on observed_clone.
_SOURCE_ROOTS = tuple(
    root for root in _RUNNER.isolated_source_pythonpath(LAB).split(os.pathsep) if root
)
for root in reversed(_SOURCE_ROOTS):
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
from scheduler import post_units

_ORIGINAL_PATCH_EVALUATOR = _RUNNER.patch_evaluator
_ORIGINAL_PAIR_GAMES = _RUNNER.pair_games
_ORIGINAL_FAILURE_MARKDOWN = _RUNNER.failure_markdown
_AUDITED_ROWS: list[dict[str, Any]] = []

_EVIDENCE_SEAM = '''            for seat in range(2):
                state[seat].action = actions[seat]
'''
_EVIDENCE_REPLACEMENT = '''            if step == cfg.episodeSteps - 2:
                # Snapshot before the interpreter resolves either final action.
                # JSON round-tripping detaches the evidence from mutable engine state.
                result["terminal_step"] = step
                result["terminal_candidate_observation"] = json.loads(
                    encoded(state[candidate_seat].observation)
                )
                result["terminal_configuration"] = json.loads(encoded(cfg))
                result["terminal_candidate_action"] = json.loads(
                    encoded(actions[candidate_seat])
                )
                result["terminal_opponent_action"] = json.loads(
                    encoded(actions[1 - candidate_seat])
                )
            for seat in range(2):
                state[seat].action = actions[seat]
'''


def _agent_spec(variant: str) -> str:
    path = LAB / "main.py" if variant == "baseline" else HERE / "candidate.py"
    return str(path.resolve()) + "::agent"


def patch_evaluator(source: Path, target: Path) -> None:
    """Add bounded step-718 evidence after retaining the isolated import seam."""
    _ORIGINAL_PATCH_EVALUATOR(source, target)
    text = target.read_text(encoding="utf-8")
    if text.count(_EVIDENCE_SEAM) != 1:
        raise RuntimeError("official evaluator terminal-action seam changed")
    target.write_text(text.replace(_EVIDENCE_SEAM, _EVIDENCE_REPLACEMENT), encoding="utf-8")


def dependency_receipt(head: str, *, evaluator: Path | None = None) -> dict[str, Any]:
    evaluator_path = Path(evaluator) if evaluator is not None else _RUNNER.EVALUATOR
    paths = {
        "candidate": HERE / "candidate.py",
        "panel_runner": HERE / "run_panel.py",
        "audit": HERE / "audit.py",
        "candidate_tests": HERE / "test_candidate.py",
        "audit_tests": HERE / "test_audit.py",
        "terminal_settlement": SETTLEMENT_SOURCE,
        "terminal_settlement_tests": SETTLEMENT_SOURCE.with_name("test_terminal_settlement.py"),
        "canonical_main": LAB / "main.py",
        "titan_runtime": LAB / "titan_runtime.py",
        "scheduler": LAB / "scheduler.py",
        "observed_clone": LAB.parent / "cloud-runtime-pulse" / "observed_clone.py",
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


def pair_games(baseline, candidate):
    rows = _ORIGINAL_PAIR_GAMES(baseline, candidate)
    audited: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row["opponent"]), int(row["seed"]), int(row["candidate_seat"]))
        evidence = audit_cell(
            baseline[key],
            candidate[key],
            compose=_SETTLEMENT.compose_terminal_settlement,
            project_units=post_units,
        )
        item = dict(row)
        item["terminal_audit"] = evidence
        audited.append(item)
    _AUDITED_ROWS[:] = audited
    return audited


def verdict(global_summary: Mapping[str, Any], _per_opponent: Mapping[str, Mapping[str, Any]]):
    return panel_verdict(_AUDITED_ROWS, global_summary, expected_cells=EXPECTED_CELLS)


def markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    decision = report["verdict"]
    lines = [
        "# TITAN T01 exact-current terminal settlement — development panel",
        "",
        f"Verdict: **{decision['decision']}**",
        "",
        f"Paired cells: {summary['cells']}",
        f"Action-bound activated cells: {decision['activated_cells']} "
        f"({decision['activation_rate']:.1%})",
        f"Certified minimum cash total: {decision['certified_min_cash_total']}",
        f"Observed activated-cell own cash total: {decision['observed_own_cash_total']:.3f}",
        f"Observed activated-cell rival cash total: {decision['observed_rival_cash_total']:.3f}",
        f"Observed activated-cell margin total: {decision['observed_margin_total']:.3f}",
        f"Global mean / median own-cash delta: {summary['mean_own_delta']:.3f} / "
        f"{summary['median_own_delta']:.3f}",
        f"Global min own-cash delta: {summary['min_own_delta']:.3f}",
        f"Global mean / median margin delta: {summary['mean_margin_delta']:.3f} / "
        f"{summary['median_margin_delta']:.3f}",
        f"Global min margin delta: {summary['min_margin_delta']:.3f}",
        f"Outcome regressions: {decision['outcome_regressions']}",
        "",
        "| Opponent × seat | Cells | Mean own Δ | Median own Δ | Mean margin Δ | Min margin Δ | Regressions |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in decision["opponent_seat_strata"].items():
        lines.append(
            f"| {name} | {row['cells']} | {row['mean_own_delta']:.3f} | "
            f"{row['median_own_delta']:.3f} | {row['mean_margin_delta']:.3f} | "
            f"{row['min_margin_delta']:.3f} | {row['outcome_regressions']} |"
        )
    lines += ["", "## Gate", ""]
    for name, passed in decision["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
    lines += ["", decision["scope"], ""]
    return "\n".join(lines)


def failure_markdown(payload: Mapping[str, Any]) -> str:
    text = _ORIGINAL_FAILURE_MARKDOWN(payload)
    return text.replace(
        "# TITAN L02 ledger-coherent tranche — development panel",
        "# TITAN T01 exact-current terminal settlement — development panel",
        1,
    )


def main(argv: Sequence[str] | None = None) -> int:
    _RUNNER._agent_spec = _agent_spec
    _RUNNER.patch_evaluator = patch_evaluator
    _RUNNER.dependency_receipt = dependency_receipt
    _RUNNER.pair_games = pair_games
    _RUNNER.verdict = verdict
    _RUNNER.markdown = markdown
    _RUNNER.failure_markdown = failure_markdown
    return int(_RUNNER.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())