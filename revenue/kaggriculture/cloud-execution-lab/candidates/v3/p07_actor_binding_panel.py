#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-current P07 worker-cardinality and score panel.

The panel materializes the observation-certified P07 candidate from its exact
canonical archive, then reuses the source-bound paired official-engine runner.
The evaluator is instrumented only in the parent process to bind every returned
candidate action to the physical hand count in the immediately preceding
observation. No transition rule is reimplemented.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
SOURCE_RUNNER = LAB / "candidates" / "v3-l02-ledger-tranche" / "run_panel.py"
MATERIALIZER = HERE / "p07_materialize.py"
BASE_ARCHIVE = LAB / "exports" / "titan-current.tar.gz"
EXPECTED_ACTION_COUNT = 719
EXPECTED_EPISODE_STEPS = 720
METRIC_FIELDS = (
    "hand_overage_rows",
    "hand_overage_commands",
    "hand_overage_nonpass_commands",
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _replace_once(text: str, needle: str, replacement: str, label: str) -> str:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"evaluator {label} seam changed: found {count}")
    return text.replace(needle, replacement, 1)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _strict_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _key(row: Mapping[str, Any]) -> tuple[str, int, int]:
    return (
        str(row["opponent"]),
        int(row["seed"]),
        int(row["candidate_seat"]),
    )


def instrument_evaluator(path: Path) -> None:
    """Add action digests and physical-hand overage receipts to one evaluator."""
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "    actors, trace = [], hashlib.sha256()\n",
        "    actors, trace, candidate_actions = [], hashlib.sha256(), hashlib.sha256()\n",
        "digest initialization",
    )
    text = _replace_once(
        text,
        '"failure": None, "steps": 0, "episode_steps": cfg.episodeSteps, "daily_bank": []}',
        '"failure": None, "steps": 0, "episode_steps": cfg.episodeSteps, "daily_bank": [],\n'
        '              "candidate_action_count": 0, "candidate_action_sha256": None,\n'
        '              "hand_overage_rows": 0, "hand_overage_commands": 0,\n'
        '              "hand_overage_nonpass_commands": 0, "hand_shape_errors": [],\n'
        '              "first_hand_overages": []}',
        "result schema",
    )
    text = _replace_once(
        text,
        '                actions.append(response["action"])\n            for seat in range(2):',
        '''                actions.append(response["action"])
            candidate_action = actions[candidate_seat]
            candidate_actions.update(encoded({"step": step, "action": candidate_action}))
            result["candidate_action_count"] += 1
            try:
                own_farm = state[candidate_seat].observation.farms[candidate_seat]
                physical_hands = len(own_farm["hands"])
                represented_hands = candidate_action.get("hands")
                if not isinstance(represented_hands, list):
                    raise TypeError("candidate action hands must be a list")
                suffix = represented_hands[physical_hands:]
                nonpass = 0
                for command in suffix:
                    if (
                        isinstance(command, (list, tuple))
                        and command
                        and isinstance(command[0], str)
                    ):
                        kind = command[0].strip().upper()
                    else:
                        kind = "__MALFORMED__"
                    nonpass += int(kind not in ("", "PASS", "NONE", "NOOP"))
                if suffix:
                    result["hand_overage_rows"] += 1
                    result["hand_overage_commands"] += len(suffix)
                    result["hand_overage_nonpass_commands"] += nonpass
                    if len(result["first_hand_overages"]) < 16:
                        result["first_hand_overages"].append({
                            "step": step,
                            "physical_hands": physical_hands,
                            "represented_hands": len(represented_hands),
                            "unreachable_commands": suffix,
                            "unreachable_nonpass": nonpass,
                        })
            except Exception as error:
                result["hand_shape_errors"].append({
                    "step": step,
                    "type": type(error).__name__,
                    "message": str(error)[:240],
                })
            for seat in range(2):''',
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


def validate_game_metrics(
    game: Mapping[str, Any], key: tuple[str, int, int], arm: str
) -> dict[str, int]:
    """Validate one complete action/cardinality receipt and return its metrics."""
    if _key(game) != key:
        raise ValueError(f"{arm} key mismatch for {key}")
    if int(game.get("episode_steps", -1)) != EXPECTED_EPISODE_STEPS:
        raise ValueError(f"{arm} episode length mismatch for {key}")
    if int(game.get("steps", -1)) != EXPECTED_ACTION_COUNT:
        raise ValueError(f"{arm} completed-step mismatch for {key}")
    if int(game.get("candidate_action_count", -1)) != EXPECTED_ACTION_COUNT:
        raise ValueError(f"{arm} action count mismatch for {key}")
    if not _is_sha256(game.get("candidate_action_sha256")):
        raise ValueError(f"{arm} action digest missing for {key}")
    errors = game.get("hand_shape_errors")
    if errors != []:
        raise ValueError(f"{arm} hand-shape instrumentation failed for {key}: {errors!r}")

    metrics = {
        field: _strict_nonnegative_int(game.get(field), field=f"{arm}.{field}")
        for field in METRIC_FIELDS
    }
    if metrics["hand_overage_rows"] > metrics["hand_overage_commands"]:
        raise ValueError(f"{arm} overage rows exceed commands for {key}")
    if metrics["hand_overage_nonpass_commands"] > metrics["hand_overage_commands"]:
        raise ValueError(f"{arm} non-PASS overage exceeds commands for {key}")
    samples = game.get("first_hand_overages")
    if not isinstance(samples, list) or len(samples) > 16:
        raise ValueError(f"{arm} overage samples malformed for {key}")
    if metrics["hand_overage_rows"] == 0 and samples:
        raise ValueError(f"{arm} sampled an overage with zero overage rows for {key}")
    return metrics


def bind_actor_metrics(
    rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[tuple[str, int, int], Mapping[str, Any]],
    candidate: Mapping[tuple[str, int, int], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Bind paired score rows to exact actions and actor-cardinality receipts."""
    if set(baseline) != set(candidate):
        raise ValueError("baseline/candidate cell sets differ")
    if len(rows) != len(baseline):
        raise ValueError("paired row cardinality mismatch")

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for raw in rows:
        key = _key(raw)
        if key in seen or key not in baseline:
            raise ValueError(f"invalid or duplicate paired row: {key}")
        seen.add(key)
        base, cand = baseline[key], candidate[key]
        base_metrics = validate_game_metrics(base, key, "baseline")
        candidate_metrics = validate_game_metrics(cand, key, "candidate")
        row = dict(raw)
        row.update(
            baseline_candidate_action_sha256=base["candidate_action_sha256"],
            candidate_candidate_action_sha256=cand["candidate_action_sha256"],
            candidate_action_count=cand["candidate_action_count"],
            candidate_action_changed=(
                base["candidate_action_sha256"] != cand["candidate_action_sha256"]
            ),
            baseline_first_hand_overages=base.get("first_hand_overages", []),
            candidate_first_hand_overages=cand.get("first_hand_overages", []),
        )
        for field in METRIC_FIELDS:
            row[f"baseline_{field}"] = base_metrics[field]
            row[f"candidate_{field}"] = candidate_metrics[field]
            row[f"{field}_delta"] = candidate_metrics[field] - base_metrics[field]
        row["actor_cardinality_improved"] = any(
            candidate_metrics[field] < base_metrics[field] for field in METRIC_FIELDS
        )
        row["actor_cardinality_regressed"] = any(
            candidate_metrics[field] > base_metrics[field] for field in METRIC_FIELDS
        )
        output.append(row)
    if seen != set(baseline):
        raise ValueError("paired grid incomplete after actor-metric binding")
    return output


def augment_summary(
    base: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    summary = dict(base)
    if not rows:
        summary.update(
            candidate_action_changed_cells=0,
            score_changed_cells=0,
            actor_cardinality_improved_cells=0,
            actor_cardinality_regressed_cells=0,
        )
        for field in METRIC_FIELDS:
            summary[f"baseline_total_{field}"] = 0
            summary[f"candidate_total_{field}"] = 0
            summary[f"total_{field}_delta"] = 0
        return summary

    summary["candidate_action_changed_cells"] = sum(
        row.get("candidate_action_changed") is True for row in rows
    )
    summary["score_changed_cells"] = sum(
        float(row.get("own_delta", 0.0)) != 0.0
        or float(row.get("margin_delta", 0.0)) != 0.0
        for row in rows
    )
    summary["actor_cardinality_improved_cells"] = sum(
        row.get("actor_cardinality_improved") is True for row in rows
    )
    summary["actor_cardinality_regressed_cells"] = sum(
        row.get("actor_cardinality_regressed") is True for row in rows
    )
    for field in METRIC_FIELDS:
        baseline_total = sum(int(row[f"baseline_{field}"]) for row in rows)
        candidate_total = sum(int(row[f"candidate_{field}"]) for row in rows)
        summary[f"baseline_total_{field}"] = baseline_total
        summary[f"candidate_total_{field}"] = candidate_total
        summary[f"total_{field}_delta"] = candidate_total - baseline_total
    return summary


def _mean_groups(
    rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        name = "/".join(str(row[field]) for field in fields)
        groups.setdefault(name, []).append(float(row["own_delta"]))
    return {
        name: statistics.fmean(values) for name, values in sorted(groups.items())
    }


def classify_verdict(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    per_opponent: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Separate exact physical closure, score safety, and strict score gain."""
    score_changed = [
        row
        for row in rows
        if float(row.get("own_delta", 0.0)) != 0.0
        or float(row.get("margin_delta", 0.0)) != 0.0
    ]
    own_deltas = [float(row.get("own_delta", 0.0)) for row in rows]
    margin_deltas = [float(row.get("margin_delta", 0.0)) for row in rows]
    new_losses = sum(
        row.get("baseline_outcome") != "L" and row.get("candidate_outcome") == "L"
        for row in rows
    )
    lost_wins = sum(
        row.get("baseline_outcome") == "W" and row.get("candidate_outcome") != "W"
        for row in rows
    )
    strata = _mean_groups(rows, ("opponent", "candidate_seat")) if rows else {}

    structural = {
        "complete_nonempty_grid": bool(rows),
        "candidate_action_receipts_complete": bool(rows)
        and all(
            int(row.get("candidate_action_count", -1)) == EXPECTED_ACTION_COUNT
            and _is_sha256(row.get("candidate_candidate_action_sha256"))
            for row in rows
        ),
        "baseline_defect_witnessed": int(
            summary.get("baseline_total_hand_overage_commands", 0)
        )
        > 0,
        "candidate_action_changed": int(
            summary.get("candidate_action_changed_cells", 0)
        )
        > 0,
        "actor_cardinality_improved": int(
            summary.get("actor_cardinality_improved_cells", 0)
        )
        > 0
        and int(summary.get("total_hand_overage_commands_delta", 0)) < 0,
        "no_actor_cardinality_regression": int(
            summary.get("actor_cardinality_regressed_cells", 0)
        )
        == 0,
        "nonpass_unreachable_work_not_increased": int(
            summary.get("total_hand_overage_nonpass_commands_delta", 0)
        )
        <= 0,
        "every_score_change_action_bound": all(
            row.get("candidate_action_changed") is True for row in score_changed
        ),
    }
    score_safety = {
        "no_negative_own_cash_cell": bool(own_deltas)
        and all(value >= 0.0 for value in own_deltas),
        "no_negative_margin_cell": bool(margin_deltas)
        and all(value >= 0.0 for value in margin_deltas),
        "no_new_losses": new_losses == 0,
        "no_lost_wins": lost_wins == 0,
        "no_negative_opponent_seat_own_stratum": bool(strata)
        and all(value >= 0.0 for value in strata.values()),
        "all_opponents_reported": set(per_opponent)
        == {str(row["opponent"]) for row in rows},
    }
    strict_gain = {
        "positive_own_cash_some_cell": any(value > 0.0 for value in own_deltas),
        "positive_margin_some_cell": any(value > 0.0 for value in margin_deltas),
    }

    if not structural["complete_nonempty_grid"]:
        decision = "REJECT_STRUCTURAL_FAILURE"
    elif not structural["baseline_defect_witnessed"]:
        decision = "REJECT_NO_DEFECT_WITNESS"
    elif not all(structural.values()):
        decision = "REJECT_DORMANT_OR_UNBOUND"
    elif not all(score_safety.values()):
        decision = "ACTIVE_BUT_REJECT_SCORE_SAFETY"
    elif any(strict_gain.values()):
        decision = "ADVANCE_TO_DISJOINT_HOLDOUT"
    else:
        decision = "ACTIVE_PARITY_EXTEND_PANEL"

    return {
        "decision": decision,
        "structural_checks": structural,
        "score_safety_checks": score_safety,
        "strict_gain_checks": strict_gain,
        "new_losses": new_losses,
        "lost_wins": lost_wins,
        "per_opponent_seat_mean_own_delta": strata,
        "scope": (
            "exact-current development evidence only; no canonical promotion, "
            "Kaggle upload, hosted-rating, or leaderboard claim"
        ),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    identity = report.get("identity") or {}
    archive = identity.get("archive") or {}
    lines = [
        "# TITAN V3 P07 observation-bound actor assignment — development panel",
        "",
        f"Verdict: **{verdict['decision']}**",
        "",
        f"Cells: **{summary['cells']}**; action-changed: "
        f"**{summary['candidate_action_changed_cells']}**; score-changed: "
        f"**{summary['score_changed_cells']}**",
        f"Canonical archive: `{archive.get('baseline_sha256', 'missing')}`",
        f"Materialized P07 archive: `{archive.get('candidate_sha256', 'missing')}`",
        "",
        "## Physical actor closure",
        "",
        "| Metric | Canonical | P07 | Delta |",
        "|---|---:|---:|---:|",
    ]
    labels = {
        "hand_overage_rows": "rows with nonexistent-hand commands",
        "hand_overage_commands": "unreachable hand commands",
        "hand_overage_nonpass_commands": "unreachable non-PASS commands",
    }
    for field in METRIC_FIELDS:
        lines.append(
            f"| {labels[field]} | {summary[f'baseline_total_{field}']} | "
            f"{summary[f'candidate_total_{field}']} | "
            f"{summary[f'total_{field}_delta']:+d} |"
        )
    lines += [
        "",
        "## Score deltas",
        "",
        f"Mean own-cash delta: **{float(summary.get('mean_own_delta', 0.0)):.3f}**",
        f"Mean margin delta: **{float(summary.get('mean_margin_delta', 0.0)):.3f}**",
        "",
        "| Opponent | Cells | Own Δ | Margin Δ | Cardinality improved / regressed |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in report["per_opponent"].items():
        lines.append(
            f"| {name} | {row['cells']} | {float(row.get('mean_own_delta', 0.0)):.3f} | "
            f"{float(row.get('mean_margin_delta', 0.0)):.3f} | "
            f"{row.get('actor_cardinality_improved_cells', 0)} / "
            f"{row.get('actor_cardinality_regressed_cells', 0)} |"
        )
    lines += ["", "## Admission gates", ""]
    for section in ("structural_checks", "score_safety_checks", "strict_gain_checks"):
        lines.append(f"### {section.replace('_', ' ').title()}")
        lines.append("")
        for name, passed in verdict[section].items():
            lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
        lines.append("")

    changed = [
        row
        for row in report.get("cells", [])
        if row.get("actor_cardinality_improved")
        or row.get("actor_cardinality_regressed")
        or row.get("candidate_action_changed")
    ]
    if changed:
        lines += [
            "## First changed cells",
            "",
            "| Opponent | Seed | Seat | Overages base→P07 | Non-PASS base→P07 | Own Δ | Margin Δ |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in changed[:16]:
            lines.append(
                f"| {row['opponent']} | {row['seed']} | {row['candidate_seat']} | "
                f"{row['baseline_hand_overage_commands']}→{row['candidate_hand_overage_commands']} | "
                f"{row['baseline_hand_overage_nonpass_commands']}→"
                f"{row['candidate_hand_overage_nonpass_commands']} | "
                f"{float(row['own_delta']):.3f} | {float(row['margin_delta']):.3f} |"
            )
        lines.append("")
    lines += [verdict["scope"], ""]
    return "\n".join(lines)


def failure_markdown(payload: Mapping[str, Any]) -> str:
    errors = [str(item) for item in list(payload.get("errors") or [])]
    if payload.get("error") not in (None, ""):
        errors.insert(0, str(payload["error"]))
    lines = [
        "# TITAN V3 P07 actor-binding panel",
        "",
        f"Status: **{payload.get('status', 'failed')}**",
        f"Stage: `{payload.get('stage', 'unknown')}`",
        "",
    ]
    lines.extend(f"- {item[:300]}" for item in errors[:24])
    lines.append("")
    return "\n".join(lines)


def _argument(argv: Sequence[str], flag: str) -> str:
    try:
        index = list(argv).index(flag)
        return str(argv[index + 1])
    except (ValueError, IndexError) as error:
        raise ValueError(f"{flag} is required") from error


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    output = Path(_argument(args, "--output")).resolve()
    head = _argument(args, "--head")
    output.parent.mkdir(parents=True, exist_ok=True)

    materializer = _load_module(MATERIALIZER, "_p07_actor_binding_materializer")
    candidate_tree = output.parent / "p07-candidate-tree"
    candidate_archive = output.parent / "titan-v3-p07.tar.gz"
    materialization_path = output.parent / "P07-MATERIALIZATION.json"
    materialization = materializer.materialize(
        BASE_ARCHIVE,
        candidate_archive,
        enabled=True,
        tree=candidate_tree,
    )
    materialization_path.write_text(
        json.dumps(materialization, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runner = _load_module(SOURCE_RUNNER, "_p07_actor_binding_source_runner")
    original_patch_evaluator = runner.patch_evaluator
    original_pair_games = runner.pair_games
    original_summarize = runner.summarize
    paired_rows: list[dict[str, Any]] = []

    def agent_spec(variant: str) -> str:
        path = runner.LAB / "main.py" if variant == "baseline" else candidate_tree / "main.py"
        return str(path.resolve()) + "::agent"

    def patch_evaluator(source: Path, target: Path) -> None:
        original_patch_evaluator(source, target)
        instrument_evaluator(target)

    def dependency_receipt(requested_head: str, *, evaluator: Path | None = None):
        evaluator_path = Path(evaluator) if evaluator is not None else runner.EVALUATOR
        paths = {
            "canonical_main": runner.LAB / "main.py",
            "candidate": candidate_tree / "main.py",
            "canonical_config": runner.LAB / "TITAN-CONFIG.json",
            "candidate_config": candidate_tree / "TITAN-CONFIG.json",
            "source_manifest": runner.LAB / "runtime/integrated-selected/CURRENT-SOURCE.json",
            "evaluator": evaluator_path,
            "evaluator_source": runner.EVALUATOR,
            "loader": runner.LOADER,
            "panel_adapter": Path(__file__),
            "source_panel_runner": SOURCE_RUNNER,
            "materializer": MATERIALIZER,
            "p07_module": HERE / "overlay/p07_joint_actor_assignment.py",
        }
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing dependency paths: " + ", ".join(missing))
        receipt = {
            "git_head": requested_head,
            "sha256": {name: runner.sha256_file(path) for name, path in paths.items()},
            "opponent_entries": {
                name: runner.sha256_file(path) for name, path in runner.OPPONENTS.items()
            },
            "candidate_bundle": runner.tree_sha256(candidate_tree),
            "archive": {
                "baseline_path": str(BASE_ARCHIVE),
                "baseline_sha256": runner.sha256_file(BASE_ARCHIVE),
                "candidate_path": str(candidate_archive),
                "candidate_sha256": runner.sha256_file(candidate_archive),
            },
            "materialization": materialization,
            "measurement": {
                "orientation": "returned action at step k bound to observation at step k before interpreter",
                "expected_actions_per_game": EXPECTED_ACTION_COUNT,
                "physical_actor_source": "state[candidate_seat].observation.farms[candidate_seat].hands",
                "overage_definition": "returned action.hands suffix beyond physical hand count",
            },
        }
        if requested_head != head:
            raise ValueError(f"head argument changed: {requested_head} != {head}")
        return receipt

    def pair_games(baseline, candidate):
        rows = bind_actor_metrics(
            original_pair_games(baseline, candidate), baseline, candidate
        )
        paired_rows[:] = rows
        return rows

    def summarize(rows):
        return augment_summary(original_summarize(rows), rows)

    def verdict(global_summary, per_opponent):
        return classify_verdict(paired_rows, global_summary, per_opponent)

    runner._agent_spec = agent_spec
    runner.patch_evaluator = patch_evaluator
    runner.dependency_receipt = dependency_receipt
    runner.pair_games = pair_games
    runner.summarize = summarize
    runner.verdict = verdict
    runner.markdown = render_markdown
    runner.failure_markdown = failure_markdown
    return runner.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
