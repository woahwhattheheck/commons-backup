# SPDX-License-Identifier: Apache-2.0
"""Run SOL-AMPLIFIER through an action-bound paired official panel."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, MutableMapping, Sequence

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "v3-l02-ledger-tranche"
RUNNER = SOURCE / "run_panel.py"
EXPECTED_OPPONENTS = ("arlene", "apex", "public_bt12", "v1")
EXPECTED_SEEDS = (2611092201, 2611092203, 2611092205, 2611092207)
EXPECTED_SEATS = (0, 1)
EXPECTED_EPISODE_STEPS = 720
EXPECTED_ACTION_COUNT = 719


def _load_runner():
    spec = importlib.util.spec_from_file_location("_sol_amplifier_paired_panel", RUNNER)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _replace_once(text: str, needle: str, replacement: str, label: str) -> str:
    if text.count(needle) != 1:
        raise RuntimeError(f"evaluator {label} seam changed")
    return text.replace(needle, replacement, 1)


def instrument_candidate_actions(path: Path) -> None:
    """Add candidate-seat pre-interpreter action custody to a patched evaluator."""
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "actors, trace = [], hashlib.sha256()",
        "actors, trace, candidate_actions = [], hashlib.sha256(), hashlib.sha256()",
        "digest initialization",
    )
    text = _replace_once(
        text,
        '"failure": None, "steps": 0, "episode_steps": cfg.episodeSteps, "daily_bank": []}',
        '"failure": None, "steps": 0, "episode_steps": cfg.episodeSteps, "daily_bank": [],\n'
        '              "candidate_action_count": 0, "candidate_action_sha256": None}',
        "result schema",
    )
    text = _replace_once(
        text,
        '                actions.append(response["action"])\n            for seat in range(2):',
        '                actions.append(response["action"])\n'
        '            candidate_actions.update(encoded({"step": step, "action": actions[candidate_seat]}))\n'
        '            result["candidate_action_count"] += 1\n'
        '            for seat in range(2):',
        "pre-interpreter action",
    )
    text = _replace_once(
        text,
        '        else:\n            result["trace_sha256"] = trace.hexdigest()\n        if finalization_errors:',
        '        else:\n            result["trace_sha256"] = trace.hexdigest()\n'
        '        result["candidate_action_sha256"] = candidate_actions.hexdigest()\n'
        '        if finalization_errors:',
        "digest finalization",
    )
    path.write_text(text, encoding="utf-8")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _expected_keys() -> set[tuple[str, int, int]]:
    return {
        (opponent, seed, seat)
        for opponent in EXPECTED_OPPONENTS
        for seed in EXPECTED_SEEDS
        for seat in EXPECTED_SEATS
    }


def _validate_action_receipt(game: Mapping[str, Any], key: tuple[str, int, int], arm: str) -> None:
    opponent, seed, seat = key
    if game.get("opponent") != opponent:
        raise ValueError(f"{arm} opponent mismatch for {key}")
    if type(game.get("seed")) is not int or game.get("seed") != seed:
        raise ValueError(f"{arm} literal seed mismatch for {key}")
    if type(game.get("candidate_seat")) is not int or game.get("candidate_seat") != seat:
        raise ValueError(f"{arm} literal seat mismatch for {key}")
    if type(game.get("episode_steps")) is not int or game.get("episode_steps") != EXPECTED_EPISODE_STEPS:
        raise ValueError(f"{arm} episode length mismatch for {key}")
    if type(game.get("steps")) is not int or game.get("steps") != EXPECTED_ACTION_COUNT:
        raise ValueError(f"{arm} completed-step mismatch for {key}")
    if type(game.get("candidate_action_count")) is not int:
        raise ValueError(f"{arm} action count type mismatch for {key}")
    if game.get("candidate_action_count") != EXPECTED_ACTION_COUNT:
        raise ValueError(f"{arm} action count mismatch for {key}")
    if game.get("candidate_action_count") != game.get("steps"):
        raise ValueError(f"{arm} action/step mismatch for {key}")
    if not _is_sha256(game.get("candidate_action_sha256")):
        raise ValueError(f"{arm} candidate action digest missing for {key}")


def bind_candidate_actions(
    rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[tuple[str, int, int], Mapping[str, Any]],
    candidate: Mapping[tuple[str, int, int], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Bind each paired score row to candidate-seat action sequences."""
    expected = _expected_keys()
    if set(baseline) != expected or set(candidate) != expected:
        raise ValueError("panel is not the literal 4-opponent x 4-seed x both-seat grid")
    if len(rows) != len(expected):
        raise ValueError("paired row cardinality mismatch")
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for raw in rows:
        key = (raw.get("opponent"), raw.get("seed"), raw.get("candidate_seat"))
        if key not in expected or key in seen:
            raise ValueError(f"invalid or duplicate paired row: {key}")
        seen.add(key)
        base, cand = baseline[key], candidate[key]
        _validate_action_receipt(base, key, "baseline")
        _validate_action_receipt(cand, key, "candidate")
        row = dict(raw)
        row["baseline_candidate_action_sha256"] = base["candidate_action_sha256"]
        row["candidate_candidate_action_sha256"] = cand["candidate_action_sha256"]
        row["candidate_action_count"] = cand["candidate_action_count"]
        row["candidate_action_changed"] = (
            base["candidate_action_sha256"] != cand["candidate_action_sha256"]
        )
        output.append(row)
    if seen != expected:
        raise ValueError("paired grid incomplete after action binding")
    return output


def add_action_summary(
    summary: MutableMapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> MutableMapping[str, Any]:
    if rows:
        if any(type(row.get("candidate_action_changed")) is not bool for row in rows):
            raise ValueError("candidate action activation missing from paired rows")
        summary["candidate_action_changed_cells"] = sum(
            row["candidate_action_changed"] for row in rows
        )
        summary["score_changed_cells"] = sum(
            float(row["own_delta"]) != 0.0 or float(row["margin_delta"]) != 0.0
            for row in rows
        )
    else:
        summary["candidate_action_changed_cells"] = 0
        summary["score_changed_cells"] = 0
    return summary


def _mean_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(float(row["own_delta"]))
    return {name: statistics.fmean(values) for name, values in sorted(groups.items())}


def strict_verdict(
    global_summary: Mapping[str, Any],
    per_opponent: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Own-cash-first gate with literal grid, action, opponent, and seat custody."""
    keys = {
        (row.get("opponent"), row.get("seed"), row.get("candidate_seat"))
        for row in rows
    }
    per_seat_own = _mean_by(rows, "candidate_seat") if rows else {}
    changed = [row for row in rows if row.get("candidate_action_changed") is True]
    score_changed = [
        row
        for row in rows
        if float(row.get("own_delta", 0.0)) != 0.0
        or float(row.get("margin_delta", 0.0)) != 0.0
    ]
    checks = {
        "literal_complete_grid": keys == _expected_keys() and len(rows) == len(_expected_keys()),
        "candidate_actions_activated": int(
            global_summary.get("candidate_action_changed_cells", 0)
        ) > 0,
        "every_score_change_action_bound": all(
            row.get("candidate_action_changed") is True for row in score_changed
        ),
        "activated_cell_has_own_cash_effect": any(
            float(row.get("own_delta", 0.0)) != 0.0 for row in changed
        ),
        "positive_global_own_cash": float(global_summary.get("mean_own_delta", 0.0)) > 0,
        "positive_global_margin": float(global_summary.get("mean_margin_delta", 0.0)) > 0,
        "all_expected_opponents_present": set(per_opponent) == set(EXPECTED_OPPONENTS),
        "no_opponent_mean_own_regression": (
            set(per_opponent) == set(EXPECTED_OPPONENTS)
            and all(
                float(per_opponent[name].get("mean_own_delta", -math.inf)) >= 0
                for name in EXPECTED_OPPONENTS
            )
        ),
        "both_seats_present": set(per_seat_own) == {"0", "1"},
        "no_seat_mean_own_regression": (
            set(per_seat_own) == {"0", "1"}
            and all(value >= 0 for value in per_seat_own.values())
        ),
    }
    return {
        "decision": "ADVANCE" if all(checks.values()) else "REJECT",
        "checks": checks,
        "per_seat_mean_own_delta": per_seat_own,
        "scope": "action-bound development panel only; not a Kaggle or leaderboard claim",
    }


def _required_argument(argv: Sequence[str], name: str) -> Path:
    try:
        index = list(argv).index(name)
        value = list(argv)[index + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"missing required runner argument: {name}") from error
    return Path(value)


def main(argv=None) -> int:
    runner = _load_runner()
    original_dependency_receipt = runner.dependency_receipt
    original_markdown = runner.markdown
    original_patch_evaluator = runner.patch_evaluator
    original_pair_games = runner.pair_games
    original_summarize = runner.summarize
    paired_rows: list[dict[str, Any]] = []

    def agent_spec(variant: str) -> str:
        path = runner.LAB / "main.py" if variant == "baseline" else HERE / "candidate.py"
        return str(path.resolve()) + "::agent"

    def patch_evaluator(source: Path, target: Path) -> None:
        original_patch_evaluator(source, target)
        instrument_candidate_actions(target)

    def pair_games(baseline, candidate):
        rows = bind_candidate_actions(
            original_pair_games(baseline, candidate), baseline, candidate
        )
        paired_rows[:] = rows
        return rows

    def summarize(rows):
        return add_action_summary(original_summarize(rows), rows)

    def verdict(global_summary, per_opponent):
        return strict_verdict(global_summary, per_opponent, paired_rows)

    def dependency_receipt(head: str, *, evaluator=None):
        saved_here = runner.HERE
        runner.HERE = SOURCE
        try:
            receipt = original_dependency_receipt(head, evaluator=evaluator)
        finally:
            runner.HERE = saved_here
        receipt["sha256"]["candidate"] = runner.sha256_file(HERE / "candidate.py")
        receipt["sha256"].pop("overlay", None)
        receipt["sha256"]["growth_patch"] = runner.sha256_file(HERE / "growth_patch.py")
        receipt["sha256"]["frozen_selected"] = runner.sha256_file(
            runner.LAB / "frozen_selected.py"
        )
        receipt["sha256"]["source_audit"] = runner.sha256_file(HERE / "audit_change.py")
        receipt["sha256"]["panel_adapter"] = runner.sha256_file(HERE / "run_panel.py")
        receipt["sha256"]["panel_source"] = runner.sha256_file(RUNNER)
        receipt["sha256"]["supplemental_gate"] = runner.sha256_file(
            HERE / "verify_panel.py"
        )
        receipt["candidate_bundle"] = runner.tree_sha256(HERE)
        receipt["ablation"] = {
            "operation": "titan-v3-full-queue-same-product-sell-growth-20260909-sol-amplifier-01",
            "target": "frozen_selected.FrozenSelected.transform",
            "planner_change": "exact-limit q>offered admitted only with positive inherited same-product SELL",
            "emitter_change": "selected excess added to first matching row without new slot or index change",
            "canonical_code_object_reused": True,
            "canonical_files_modified": False,
            "candidate_action_receipt": {
                "stage": "candidate-seat pre-interpreter action",
                "digest": "sha256(canonical-json({step,action}) stream)",
                "expected_actions_per_cell": EXPECTED_ACTION_COUNT,
                "expected_episode_steps": EXPECTED_EPISODE_STEPS,
            },
        }
        return receipt

    def markdown(report):
        text = original_markdown(report)
        return text.replace(
            "# TITAN L02 ledger-coherent tranche — development panel",
            "# TITAN V3 saturated-queue SELL expansion — action-bound development panel",
            1,
        )

    runner._agent_spec = agent_spec
    runner.patch_evaluator = patch_evaluator
    runner.pair_games = pair_games
    runner.summarize = summarize
    runner.verdict = verdict
    runner.dependency_receipt = dependency_receipt
    runner.markdown = markdown
    arguments = list(sys.argv[1:] if argv is None else argv)
    code = int(runner.main(arguments))
    if code not in (0, 3):
        return code
    import verify_panel

    result = verify_panel.verify_files(
        _required_argument(arguments, "--output"),
        _required_argument(arguments, "--markdown"),
    )
    return 0 if result["decision"] == "ADVANCE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
