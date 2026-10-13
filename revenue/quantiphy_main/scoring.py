"""Leakage-safe scoring, grouping, calibration, and candidate primitives."""
from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .common import (
    CATEGORIES, GROUND_TRUTH, MAX_SAFE_INT, THRESHOLDS, QuantiPhyMainError,
    _dataset_index, _decimal, _decimal_text, _int, category_of, model_name, row_key,
)

def _model_prediction_rows(model: str, dataset_rows: Sequence[Mapping[str, Any]], receipts_by_model: Mapping[str, Mapping[tuple[str, str], Mapping[str, Any]]]) -> list[dict[str, Any]] | None:
    index = receipts_by_model.get(model, {})
    output: list[dict[str, Any]] = []
    for row in dataset_rows:
        receipt = index.get(row_key(row))
        if receipt is None or receipt["status"] != "OK":
            return None
        output.append({**dict(row), "parsed_value": receipt["parsed_value"]})
    return output


def _score_item(prediction: Decimal, truth: Decimal) -> float:
    # Mirror the organizer evaluator's floating threshold arithmetic after strict
    # decimal-domain admission. Custody uses Decimal; scoring semantics use float.
    prediction_f = abs(float(prediction))
    truth_f = float(truth)
    relative_error = abs(prediction_f - truth_f) / truth_f
    return sum(relative_error < (1.0 - threshold) for threshold in THRESHOLDS) / len(THRESHOLDS)


def score_rows(dataset_rows: Sequence[Mapping[str, Any]], prediction_rows: Sequence[Mapping[str, Any]], *, require_all_categories: bool = True) -> dict[str, Any]:
    truth_index = _dataset_index(dataset_rows)
    pred_index = _dataset_index(prediction_rows)
    if set(truth_index) != set(pred_index):
        raise QuantiPhyMainError("prediction key mismatch")
    by_category: dict[str, list[float]] = {cat: [] for cat in CATEGORIES}
    for key, truth_row in truth_index.items():
        if GROUND_TRUTH not in truth_row:
            raise QuantiPhyMainError("score requires ground truth")
        pred_row = pred_index[key]
        pred = _decimal(pred_row.get("parsed_value"), f"prediction:{key}", positive=True)
        truth = _decimal(truth_row[GROUND_TRUTH], f"truth:{key}", positive=True)
        by_category[category_of(truth_row)].append(_score_item(pred, truth))
    category_scores: dict[str, float | None] = {}
    for cat, values in by_category.items():
        category_scores[cat] = sum(values) / len(values) if values else None
    if require_all_categories and any(value is None for value in category_scores.values()):
        raise QuantiPhyMainError("score missing official category")
    present = [value for value in category_scores.values() if value is not None]
    return {
        "mra_average": sum(present) / len(present),
        "mra_by_category": category_scores,
        "rows": len(truth_index),
    }


def _combine(values: Sequence[Decimal], method: str) -> Decimal:
    if not values:
        raise QuantiPhyMainError("cannot combine zero predictions")
    if method == "median":
        ordered = sorted(values)
        n = len(ordered)
        return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / Decimal(2)
    if method == "arithmetic_mean":
        return sum(values, Decimal(0)) / Decimal(len(values))
    if method == "geometric_mean":
        # Organizer uses floating arithmetic. Determinism is from exact input ordering and canonical output.
        f = math.exp(sum(math.log(float(value)) for value in values) / len(values))
        return Decimal(format(f, ".15g"))
    raise QuantiPhyMainError(f"unknown combine method: {method}")


def _ensemble_rows(models: Sequence[str], method: str, dataset_rows: Sequence[Mapping[str, Any]], receipts_by_model: Mapping[str, Mapping[tuple[str, str], Mapping[str, Any]]]) -> list[dict[str, Any]] | None:
    output: list[dict[str, Any]] = []
    for row in dataset_rows:
        key = row_key(row)
        values: list[Decimal] = []
        for model in models:
            receipt = receipts_by_model.get(model, {}).get(key)
            if receipt is None or receipt["status"] != "OK":
                return None
            values.append(_decimal(receipt["parsed_value"], f"{model}:{key}", positive=True))
        changed = dict(row)
        changed["parsed_value"] = _decimal_text(_combine(values, method))
        output.append(changed)
    return output


def _grouped_folds(rows: Sequence[Mapping[str, Any]], fold_count: int) -> dict[tuple[str, str], int]:
    if type(fold_count) is not int or fold_count < 2 or fold_count > 20:
        raise QuantiPhyMainError("fold_count must be integer 2..20")
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        video = str(row["video_id"])
        entry = groups.setdefault(video, {"keys": [], "counts": {cat: 0 for cat in CATEGORIES}})
        entry["keys"].append(row_key(row))
        entry["counts"][category_of(row)] += 1
    if len(groups) < fold_count:
        raise QuantiPhyMainError("not enough video groups for requested folds")
    fold_counts = [{cat: 0 for cat in CATEGORIES} for _ in range(fold_count)]
    fold_rows = [0] * fold_count
    assignments: dict[tuple[str, str], int] = {}
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]["keys"]), hashlib.sha256(item[0].encode("utf-8")).hexdigest(), item[0]),
    )
    for _video, entry in ordered_groups:
        def penalty(fold: int) -> tuple[int, int, int]:
            after = fold_counts[fold].copy()
            for cat in CATEGORIES:
                after[cat] += entry["counts"][cat]
            spread_penalty = sum(after[cat] * after[cat] for cat in CATEGORIES)
            return spread_penalty, fold_rows[fold], fold
        chosen = min(range(fold_count), key=penalty)
        for cat in CATEGORIES:
            fold_counts[chosen][cat] += entry["counts"][cat]
        fold_rows[chosen] += len(entry["keys"])
        for key in entry["keys"]:
            assignments[key] = chosen
    for fold in range(fold_count):
        present = {category_of(row) for row in rows if assignments[row_key(row)] == fold}
        if set(CATEGORIES) - present:
            raise QuantiPhyMainError(f"fold {fold} missing categories: {sorted(set(CATEGORIES)-present)}")
    return assignments


def _subset(rows: Sequence[Mapping[str, Any]], keys: set[tuple[str, str]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row_key(row) in keys]


def _scale_grid() -> tuple[Decimal, ...]:
    return tuple(Decimal(format(2.0 ** (step / 16.0), ".15g")) for step in range(-32, 33))


def fit_scales(truth_rows: Sequence[Mapping[str, Any]], prediction_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    truth_index = _dataset_index(truth_rows)
    pred_index = _dataset_index(prediction_rows)
    if set(truth_index) != set(pred_index):
        raise QuantiPhyMainError("scale-fit key mismatch")
    result: dict[str, str] = {}
    for cat in CATEGORIES:
        keys = [key for key, row in truth_index.items() if category_of(row) == cat]
        if not keys:
            result[cat] = "1"
            continue
        best: tuple[float, float, float] | None = None
        best_scale = Decimal(1)
        for scale in _scale_grid():
            values = [
                _score_item(
                    _decimal(pred_index[key]["parsed_value"], "prediction", positive=True) * scale,
                    _decimal(truth_index[key][GROUND_TRUTH], "truth", positive=True),
                )
                for key in keys
            ]
            mean = sum(values) / len(values)
            candidate = (mean, -abs(math.log2(float(scale))), -float(scale))
            if best is None or candidate > best:
                best = candidate
                best_scale = scale
        result[cat] = _decimal_text(best_scale)
    return result


def apply_scales(rows: Sequence[Mapping[str, Any]], scales: Mapping[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        changed = dict(row)
        value = _decimal(row["parsed_value"], "parsed_value", positive=True)
        scale = _decimal(scales.get(category_of(row), "1"), "scale", positive=True)
        changed["parsed_value"] = _decimal_text(value * scale)
        output.append(changed)
    return output


def _candidate_cost(models: Sequence[str], selected_categories: Mapping[str, str] | None, dataset_rows: Sequence[Mapping[str, Any]], receipts_by_model: Mapping[str, Mapping[tuple[str, str], Mapping[str, Any]]]) -> int:
    total = 0
    for row in dataset_rows:
        key = row_key(row)
        row_models = models if selected_categories is None else [selected_categories[category_of(row)]]
        for model in row_models:
            receipt = receipts_by_model[model][key]
            total += _int(receipt["cost_microusd"], "cost_microusd")
            if total > MAX_SAFE_INT:
                raise QuantiPhyMainError("candidate cost overflow")
    return total


def _model_cv(
    name: str,
    base_rows: Sequence[Mapping[str, Any]],
    dataset_rows: Sequence[Mapping[str, Any]],
    folds: Mapping[tuple[str, str], int],
    fold_count: int,
) -> tuple[float, dict[str, float]]:
    all_keys = set(_dataset_index(dataset_rows))
    fold_scores: list[float] = []
    cat_scores: dict[str, list[float]] = {cat: [] for cat in CATEGORIES}
    for fold in range(fold_count):
        val_keys = {key for key, assigned in folds.items() if assigned == fold}
        train_keys = all_keys - val_keys
        scales = fit_scales(_subset(dataset_rows, train_keys), _subset(base_rows, train_keys))
        val_truth = _subset(dataset_rows, val_keys)
        val_pred = apply_scales(_subset(base_rows, val_keys), scales)
        score = score_rows(val_truth, val_pred)
        fold_scores.append(score["mra_average"])
        for cat, value in score["mra_by_category"].items():
            if value is not None:
                cat_scores[cat].append(value)
    return sum(fold_scores) / len(fold_scores), {cat: sum(values) / len(values) for cat, values in cat_scores.items()}
