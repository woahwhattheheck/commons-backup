# SPDX-License-Identifier: Apache-2.0
"""Paired route-arm validation and development-only monotone threshold fitting."""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Iterable


class PairError(ValueError):
    """Raised when two alleged counterfactual cells do not share one prefix."""


def _receipt(game: dict[str, Any], checkpoint: int) -> dict[str, Any]:
    rows = [
        row
        for row in game.get("checkpoint_receipts", [])
        if row.get("checkpoint") == checkpoint
    ]
    if len(rows) != 1:
        raise PairError(
            f"{game.get('arm')} has {len(rows)} receipts for checkpoint {checkpoint}"
        )
    return rows[0]


def _outcome(game: dict[str, Any]) -> dict[str, float | int | str]:
    if game.get("status") != "complete":
        raise PairError(f"incomplete game: {game.get('failure')}")
    seat = game.get("tested_seat")
    if type(seat) is not int or seat not in (0, 1):
        raise PairError("game has invalid tested seat")
    bank = game.get("bank_snapshot")
    if not isinstance(bank, list) or len(bank) != 2:
        raise PairError("game has no two-seat terminal bank snapshot")
    own = float(bank[seat])
    rival = float(bank[1 - seat])
    if not math.isfinite(own) or not math.isfinite(rival):
        raise PairError("game has nonfinite terminal bank")
    result = "W" if own > rival else "L" if own < rival else "T"
    return {
        "own": own,
        "rival": rival,
        "margin": own - rival,
        "result": result,
        "win": int(result == "W"),
        "loss": int(result == "L"),
        "tie": int(result == "T"),
    }


def _index(games: Iterable[dict[str, Any]]) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    indexed = {}
    for game in games:
        key = (
            game.get("arm"),
            game.get("opponent"),
            game.get("seed"),
            game.get("tested_seat"),
        )
        if key in indexed:
            raise PairError(f"duplicate game cell: {key}")
        indexed[key] = game
    return indexed


def build_pairs(
    games: Iterable[dict[str, Any]], checkpoints: Iterable[tuple[Any, ...]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed = _index(games)
    cells = {
        (opponent, seed, seat)
        for arm, opponent, seed, seat in indexed
        if arm == "auto"
    }
    pairs = []
    rejected = []
    for checkpoint, feature_name, shipped_threshold, target in checkpoints:
        checkpoint = int(checkpoint)
        for opponent, seed, seat in sorted(cells):
            force_key = (f"force_{checkpoint}", opponent, seed, seat)
            stay_key = (f"stay_{checkpoint}", opponent, seed, seat)
            auto_key = ("auto", opponent, seed, seat)
            if force_key not in indexed or stay_key not in indexed:
                raise PairError(f"missing route arms for {checkpoint}/{opponent}/{seed}/{seat}")
            force = indexed[force_key]
            stay = indexed[stay_key]
            auto = indexed[auto_key]
            try:
                force_receipt = _receipt(force, checkpoint)
                stay_receipt = _receipt(stay, checkpoint)
                auto_receipt = _receipt(auto, checkpoint)
                if force_receipt.get("mode") != "force":
                    raise PairError("force receipt mode mismatch")
                if stay_receipt.get("mode") != "stay":
                    raise PairError("stay receipt mode mismatch")
                if auto_receipt.get("mode") != "auto":
                    raise PairError("auto receipt mode mismatch")
                for name, row in (
                    ("force", force_receipt),
                    ("stay", stay_receipt),
                    ("auto", auto_receipt),
                ):
                    if row.get("feature") != feature_name:
                        raise PairError(f"{name} feature-name mismatch")
                    if row.get("target") != target:
                        raise PairError(f"{name} target mismatch")
                    if row.get("shipped_threshold") != shipped_threshold:
                        raise PairError(f"{name} shipped-threshold mismatch")
                if force_receipt.get("pre_world_sha256") != stay_receipt.get(
                    "pre_world_sha256"
                ):
                    raise PairError("counterfactual prefix state mismatch")
                if force_receipt.get("opponent_action_sha256") != stay_receipt.get(
                    "opponent_action_sha256"
                ):
                    raise PairError("counterfactual checkpoint rival action mismatch")
                if force_receipt.get("feature_value") != stay_receipt.get("feature_value"):
                    raise PairError("counterfactual feature mismatch")
                if force_receipt.get("route_before") != stay_receipt.get("route_before"):
                    raise PairError("counterfactual source route mismatch")
                if not force_receipt.get("switch_legal") or not stay_receipt.get(
                    "switch_legal"
                ):
                    raise PairError("checkpoint switch was not prefix-legal")
                if not force_receipt.get("override_applied") or not stay_receipt.get(
                    "override_applied"
                ):
                    raise PairError("checkpoint override was not applied")
                if force_receipt.get("route_after") != target:
                    raise PairError("forced route did not persist through action selection")
                if stay_receipt.get("route_after") != stay_receipt.get("route_before"):
                    raise PairError("stay arm changed route")
                feature_value = force_receipt.get("feature_value")
                if isinstance(feature_value, bool) or not isinstance(
                    feature_value, (int, float)
                ):
                    raise PairError("feature value is not numeric")
                natural_target = bool(feature_value >= shipped_threshold)
                natural = force if natural_target else stay
                auto_match = (
                    auto.get("tested_action_stream_sha256")
                    == natural.get("tested_action_stream_sha256")
                    and auto.get("opponent_action_stream_sha256")
                    == natural.get("opponent_action_stream_sha256")
                    and auto.get("world_stream_sha256")
                    == natural.get("world_stream_sha256")
                    and auto.get("bank_snapshot") == natural.get("bank_snapshot")
                )
                pair = {
                    "checkpoint": checkpoint,
                    "feature": feature_name,
                    "feature_value": feature_value,
                    "shipped_threshold": shipped_threshold,
                    "target": target,
                    "opponent": opponent,
                    "seed": seed,
                    "seat": seat,
                    "pre_world_sha256": force_receipt["pre_world_sha256"],
                    "route_before": force_receipt.get("route_before"),
                    "auto_match": auto_match,
                    "force": _outcome(force),
                    "stay": _outcome(stay),
                    "auto": _outcome(auto),
                }
                if not auto_match:
                    raise PairError("natural arm did not reproduce the untouched auto game")
                pairs.append(pair)
            except PairError as exc:
                rejected.append(
                    {
                        "checkpoint": checkpoint,
                        "opponent": opponent,
                        "seed": seed,
                        "seat": seat,
                        "reason": str(exc),
                    }
                )
    return pairs, rejected


def _candidates(pairs: list[dict[str, Any]], shipped: int | float) -> list[int | float]:
    values = sorted({pair["feature_value"] for pair in pairs})
    if not values:
        return [shipped]
    result = {shipped}
    for value in values:
        result.add(value)
        if type(value) is int:
            result.add(value + 1)
    if all(type(value) is int for value in values):
        result.add(values[0] - 1)
        result.add(values[-1] + 1)
    return sorted(result)


def _choice(pair: dict[str, Any], threshold: int | float) -> dict[str, Any]:
    return pair["force"] if pair["feature_value"] >= threshold else pair["stay"]


def score_policy(
    pairs: Iterable[dict[str, Any]], threshold: int | float
) -> dict[str, float | int]:
    chosen = [_choice(pair, threshold) for pair in pairs]
    return {
        "cells": len(chosen),
        "wins": sum(int(row["win"]) for row in chosen),
        "ties": sum(int(row["tie"]) for row in chosen),
        "losses": sum(int(row["loss"]) for row in chosen),
        "own_total": sum(float(row["own"]) for row in chosen),
        "rival_total": sum(float(row["rival"]) for row in chosen),
        "margin_total": sum(float(row["margin"]) for row in chosen),
    }


def _objective(score: dict[str, Any]) -> tuple[float, ...]:
    return (
        float(score["wins"]),
        -float(score["losses"]),
        float(score["own_total"]),
        float(score["margin_total"]),
    )


def select_threshold(
    development_pairs: list[dict[str, Any]], shipped_threshold: int | float
) -> dict[str, Any]:
    """Select from development rows only; holdout rows are not an argument."""
    table = []
    for threshold in _candidates(development_pairs, shipped_threshold):
        score = score_policy(development_pairs, threshold)
        table.append({"threshold": threshold, "score": score})
    selected = max(
        table,
        key=lambda row: (
            _objective(row["score"]),
            row["threshold"] == shipped_threshold,
            -abs(float(row["threshold"]) - float(shipped_threshold)),
            -float(row["threshold"]),
        ),
    )
    shipped = next(
        row for row in table if row["threshold"] == shipped_threshold
    )
    return {
        "selected_threshold": selected["threshold"],
        "selected_score": selected["score"],
        "shipped_threshold": shipped_threshold,
        "shipped_score": shipped["score"],
        "strict_development_improvement": _objective(selected["score"])
        > _objective(shipped["score"]),
        "candidate_table": table,
    }


def _delta(candidate: dict[str, Any], shipped: dict[str, Any]) -> dict[str, float | int]:
    return {
        key: candidate[key] - shipped[key]
        for key in ("wins", "ties", "losses", "own_total", "rival_total", "margin_total")
    }


def _cell_nonregression(
    pairs: list[dict[str, Any]], candidate: int | float, shipped: int | float
) -> tuple[bool, list[dict[str, Any]]]:
    """Reject any individual L/T/W downgrade, even when aggregates improve."""
    rank = {"L": 0, "T": 1, "W": 2}
    receipts = []
    passed = True
    for pair in sorted(
        pairs,
        key=lambda row: (
            str(row.get("opponent")),
            str(row.get("seed")),
            str(row.get("seat")),
        ),
    ):
        candidate_row = _choice(pair, candidate)
        shipped_row = _choice(pair, shipped)
        candidate_result = candidate_row.get("result")
        shipped_result = shipped_row.get("result")
        ok = (
            candidate_result in rank
            and shipped_result in rank
            and rank[candidate_result] >= rank[shipped_result]
        )
        passed = passed and ok
        receipts.append(
            {
                "opponent": pair.get("opponent"),
                "seed": pair.get("seed"),
                "seat": pair.get("seat"),
                "shipped_result": shipped_result,
                "candidate_result": candidate_result,
                "passed": ok,
            }
        )
    return passed, receipts


def _group_nonregression(
    pairs: list[dict[str, Any]], candidate: int | float, shipped: int | float
) -> tuple[bool, list[dict[str, Any]]]:
    groups: dict[tuple[str, object], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        groups[("opponent", pair["opponent"])].append(pair)
        groups[("seat", pair["seat"])].append(pair)
        groups[("opponent_seat", (pair["opponent"], pair["seat"]))].append(pair)
    receipts = []
    passed = True
    for (kind, value), rows in sorted(groups.items(), key=lambda item: str(item[0])):
        candidate_score = score_policy(rows, candidate)
        shipped_score = score_policy(rows, shipped)
        delta = _delta(candidate_score, shipped_score)
        ok = (
            delta["wins"] >= 0
            and delta["losses"] <= 0
            and delta["own_total"] >= 0
            and delta["margin_total"] >= 0
        )
        passed = passed and ok
        receipts.append(
            {
                "kind": kind,
                "value": value,
                "cells": len(rows),
                "passed": ok,
                "delta": delta,
            }
        )
    return passed, receipts


def fit_report(
    pairs: list[dict[str, Any]],
    checkpoints: Iterable[tuple[Any, ...]],
    development_seeds: set[int],
    holdout_seeds: set[int],
    *,
    minimum_holdout_cells: int = 4,
) -> dict[str, Any]:
    if development_seeds & holdout_seeds:
        raise ValueError("development and holdout seeds overlap")
    reports = []
    for checkpoint, feature, shipped, target in checkpoints:
        rows = [pair for pair in pairs if pair["checkpoint"] == checkpoint]
        development = [pair for pair in rows if pair["seed"] in development_seeds]
        holdout = [pair for pair in rows if pair["seed"] in holdout_seeds]
        selection = select_threshold(development, shipped)
        selected = selection["selected_threshold"]
        holdout_selected = score_policy(holdout, selected)
        holdout_shipped = score_policy(holdout, shipped)
        holdout_delta = _delta(holdout_selected, holdout_shipped)
        cells_passed, cell_receipts = _cell_nonregression(holdout, selected, shipped)
        groups_passed, group_receipts = _group_nonregression(
            holdout, selected, shipped
        )
        gate_reasons = []
        if selected == shipped:
            gate_reasons.append("development selector retained shipped threshold")
        if not selection["strict_development_improvement"]:
            gate_reasons.append("no strict development objective improvement")
        if len(holdout) < minimum_holdout_cells:
            gate_reasons.append("insufficient holdout cells")
        if holdout_delta["wins"] < 0:
            gate_reasons.append("holdout wins regressed")
        if holdout_delta["losses"] > 0:
            gate_reasons.append("holdout losses regressed")
        if holdout_delta["own_total"] < 0:
            gate_reasons.append("holdout own cash regressed")
        if holdout_delta["margin_total"] < 0:
            gate_reasons.append("holdout margin regressed")
        if not cells_passed:
            gate_reasons.append("holdout outcome transition regressed")
        if not groups_passed:
            gate_reasons.append("seat/opponent/intersection holdout subgroup regressed")
        passed = not gate_reasons
        reports.append(
            {
                "checkpoint": checkpoint,
                "feature": feature,
                "target": target,
                "shipped_threshold": shipped,
                "selected_threshold": selected,
                "development_cells": len(development),
                "holdout_cells": len(holdout),
                "development": selection,
                "holdout_selected": holdout_selected,
                "holdout_shipped": holdout_shipped,
                "holdout_delta": holdout_delta,
                "holdout_transitions": cell_receipts,
                "holdout_groups": group_receipts,
                "screen_passed": passed,
                "gate_reasons": gate_reasons,
            }
        )
    passed = [row for row in reports if row["screen_passed"]]
    return {
        "verdict": "THRESHOLD_CANDIDATE_SCREEN" if passed else "NO_THRESHOLD_CHANGE",
        "candidate_checkpoints": [row["checkpoint"] for row in passed],
        "checkpoints": reports,
    }
