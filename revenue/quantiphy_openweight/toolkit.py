"""Deterministic QuantiPhy public-validation scoring, selection, and packaging.

The official evaluator treats ``parsed_value`` as an absolute numeric prediction,
scores ten relative-error thresholds, and macro-averages S2/D2/S3/D3.  This
module mirrors that public contract without importing the organizer evaluator and
adds leakage-resistant public-validation model/ensemble selection.

No inference, registration, submission, or hidden-test access is performed here.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

THRESHOLDS: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
CATEGORIES: tuple[str, ...] = ("S2", "D2", "S3", "D3")
KEY_COLUMNS: tuple[str, str] = ("video_id", "question")
GROUND_TRUTH_COLUMN = "ground_truth_posterior"
PREDICTION_COLUMN = "parsed_value"
SCHEMA_VERSION = 1


class QuantiPhyError(ValueError):
    """Raised when a QuantiPhy carrier violates the public data contract."""


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise QuantiPhyError(f"CSV has no header: {path}")
        return [dict(row) for row in reader]


def _row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    missing = [column for column in KEY_COLUMNS if not str(row.get(column, "")).strip()]
    if missing:
        raise QuantiPhyError(f"missing key column(s) {','.join(missing)}")
    return (str(row["video_id"]).strip(), str(row["question"]).strip())


def _finite_number(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise QuantiPhyError(f"{field} must be numeric: {value!r}") from exc
    if not math.isfinite(result):
        raise QuantiPhyError(f"{field} must be finite: {value!r}")
    return result


def category_of(row: Mapping[str, Any]) -> str:
    inference_type = str(row.get("inference_type", "")).strip()
    video_type = str(row.get("video_type", "")).strip()
    if len(inference_type) < 1 or len(video_type) < 2:
        raise QuantiPhyError("inference_type/video_type cannot form an official category")
    category = inference_type[0].upper() + video_type[1]
    if category not in CATEGORIES:
        raise QuantiPhyError(f"unsupported QuantiPhy category: {category!r}")
    return category


def _index_rows(rows: Sequence[Mapping[str, Any]], *, label: str) -> dict[tuple[str, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = _row_key(row)
        if key in indexed:
            raise QuantiPhyError(f"duplicate {label} key: {key!r}")
        indexed[key] = row
    if not indexed:
        raise QuantiPhyError(f"{label} rows are empty")
    return indexed


def validate_prediction_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    require_categories: bool = False,
    reject_zero: bool = True,
) -> dict[str, Any]:
    indexed = _index_rows(rows, label="prediction")
    categories: dict[str, int] = {category: 0 for category in CATEGORIES}
    for key, row in indexed.items():
        value = _finite_number(row.get(PREDICTION_COLUMN), field=f"{PREDICTION_COLUMN}:{key}")
        if reject_zero and value == 0:
            raise QuantiPhyError(f"zero prediction is counted invalid by the organizer evaluator: {key!r}")
        if require_categories:
            categories[category_of(row)] += 1
    return {
        "ok": True,
        "rows": len(indexed),
        "categories": categories if require_categories else None,
        "zero_rejected": reject_zero,
    }


def item_mra(prediction: float, truth: float) -> float:
    """Mirror the official per-row MRA computation.

    The public evaluator takes ``abs(parsed_value)`` before computing relative
    error.  Ground-truth values in the released validation contract are positive;
    fail closed here for zero/negative truth instead of dividing ambiguously.
    """
    prediction = abs(_finite_number(prediction, field="prediction"))
    truth = _finite_number(truth, field="ground_truth")
    if truth <= 0:
        raise QuantiPhyError("ground_truth_posterior must be positive")
    relative_error = abs(prediction - truth) / truth
    return sum(relative_error < (1.0 - threshold) for threshold in THRESHOLDS) / len(THRESHOLDS)


def score_prediction_rows(
    ground_truth_rows: Sequence[Mapping[str, Any]],
    prediction_rows: Sequence[Mapping[str, Any]],
    *,
    require_all_categories: bool = True,
) -> dict[str, Any]:
    truth_index = _index_rows(ground_truth_rows, label="ground-truth")
    pred_index = _index_rows(prediction_rows, label="prediction")
    if set(truth_index) != set(pred_index):
        missing = sorted(set(truth_index) - set(pred_index))[:3]
        extra = sorted(set(pred_index) - set(truth_index))[:3]
        raise QuantiPhyError(f"prediction key mismatch: missing={missing!r} extra={extra!r}")

    category_scores: dict[str, list[float]] = {category: [] for category in CATEGORIES}
    invalid = 0
    for key, truth_row in truth_index.items():
        pred_row = pred_index[key]
        try:
            prediction = _finite_number(pred_row.get(PREDICTION_COLUMN), field=f"prediction:{key}")
        except QuantiPhyError:
            invalid += 1
            prediction = float("nan")
        truth = _finite_number(truth_row.get(GROUND_TRUTH_COLUMN), field=f"ground_truth:{key}")
        category = category_of(truth_row)
        if math.isnan(prediction):
            category_scores[category].append(0.0)
        else:
            category_scores[category].append(item_mra(prediction, truth))

    means: dict[str, float | None] = {}
    for category in CATEGORIES:
        values = category_scores[category]
        means[category] = (sum(values) / len(values)) if values else None
    present = [score for score in means.values() if score is not None]
    if require_all_categories and len(present) != len(CATEGORIES):
        missing_categories = [category for category, score in means.items() if score is None]
        raise QuantiPhyError(f"missing official category rows: {missing_categories}")
    macro = sum(present) / len(present) if present else float("nan")
    return {
        "mra_average": macro,
        "mra_by_category": means,
        "rows": len(truth_index),
        "invalid_predictions": invalid,
    }


def _prediction_value(row: Mapping[str, Any]) -> float:
    return abs(_finite_number(row.get(PREDICTION_COLUMN), field=PREDICTION_COLUMN))


def _combine(values: Sequence[float], method: str) -> float:
    if not values:
        raise QuantiPhyError("cannot ensemble zero values")
    if method == "median":
        return float(median(values))
    if method == "arithmetic_mean":
        return sum(values) / len(values)
    if method == "geometric_mean":
        if any(value <= 0 for value in values):
            raise QuantiPhyError("geometric_mean requires positive predictions")
        return math.exp(sum(math.log(value) for value in values) / len(values))
    if method.startswith("model:"):
        try:
            index = int(method.split(":", 1)[1])
        except ValueError as exc:
            raise QuantiPhyError(f"invalid model selector: {method}") from exc
        if index < 0 or index >= len(values):
            raise QuantiPhyError(f"model selector out of range: {method}")
        return values[index]
    raise QuantiPhyError(f"unknown ensemble method: {method}")


def ensemble_prediction_sets(
    prediction_sets: Sequence[Sequence[Mapping[str, Any]]],
    method: str,
) -> list[dict[str, Any]]:
    if not prediction_sets:
        raise QuantiPhyError("at least one prediction set is required")
    indices = [_index_rows(rows, label=f"prediction[{idx}]") for idx, rows in enumerate(prediction_sets)]
    keys = set(indices[0])
    for idx, index in enumerate(indices[1:], start=1):
        if set(index) != keys:
            raise QuantiPhyError(f"prediction[{idx}] keys do not match prediction[0]")

    output: list[dict[str, Any]] = []
    for key in sorted(keys):
        base = dict(indices[0][key])
        values = [_prediction_value(index[key]) for index in indices]
        base[PREDICTION_COLUMN] = _combine(values, method)
        output.append(base)
    return output


def _apply_scales(
    rows: Sequence[Mapping[str, Any]],
    category_scales: Mapping[str, float],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        changed = dict(row)
        category = category_of(row)
        scale = float(category_scales.get(category, 1.0))
        changed[PREDICTION_COLUMN] = _prediction_value(row) * scale
        output.append(changed)
    return output


def _subset_by_keys(rows: Sequence[Mapping[str, Any]], keys: set[tuple[str, str]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if _row_key(row) in keys]


def _scale_grid() -> tuple[float, ...]:
    # Multiplicative correction from 0.25x to 4x in 1/16-octave increments.
    return tuple(2.0 ** (step / 16.0) for step in range(-32, 33))


def fit_category_scales(
    ground_truth_rows: Sequence[Mapping[str, Any]],
    prediction_rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    truth_index = _index_rows(ground_truth_rows, label="ground-truth")
    pred_index = _index_rows(prediction_rows, label="prediction")
    if set(truth_index) != set(pred_index):
        raise QuantiPhyError("scale-fit key mismatch")
    scales: dict[str, float] = {}
    for category in CATEGORIES:
        keys = [key for key, row in truth_index.items() if category_of(row) == category]
        if not keys:
            scales[category] = 1.0
            continue
        best: tuple[float, float, float] | None = None
        for scale in _scale_grid():
            scores = [
                item_mra(_prediction_value(pred_index[key]) * scale, _finite_number(truth_index[key][GROUND_TRUTH_COLUMN], field="ground_truth"))
                for key in keys
            ]
            mean = sum(scores) / len(scores)
            candidate = (mean, -abs(math.log2(scale)), -scale)
            if best is None or candidate > best:
                best = candidate
                scales[category] = scale
    return scales


def _stratified_folds(ground_truth_rows: Sequence[Mapping[str, Any]], fold_count: int) -> dict[tuple[str, str], int]:
    if fold_count < 2:
        raise QuantiPhyError("fold_count must be >= 2")
    assignments: dict[tuple[str, str], int] = {}
    buckets: dict[str, list[tuple[str, tuple[str, str]]]] = {category: [] for category in CATEGORIES}
    for row in ground_truth_rows:
        key = _row_key(row)
        digest = hashlib.sha256((key[0] + "\0" + key[1]).encode("utf-8")).hexdigest()
        buckets[category_of(row)].append((digest, key))
    for category, items in buckets.items():
        if len(items) < fold_count:
            raise QuantiPhyError(f"category {category} has {len(items)} rows; need >= {fold_count} for stratified CV")
        for index, (_, key) in enumerate(sorted(items)):
            assignments[key] = index % fold_count
    return assignments


def build_recipe(
    ground_truth_rows: Sequence[Mapping[str, Any]],
    prediction_sets: Sequence[Sequence[Mapping[str, Any]]],
    *,
    prediction_names: Sequence[str] | None = None,
    fold_count: int = 5,
) -> dict[str, Any]:
    if not prediction_sets:
        raise QuantiPhyError("at least one prediction set is required")
    names = list(prediction_names or [f"model_{idx}" for idx in range(len(prediction_sets))])
    if len(names) != len(prediction_sets) or len(set(names)) != len(names):
        raise QuantiPhyError("prediction_names must be unique and match prediction_sets")

    truth_index = _index_rows(ground_truth_rows, label="ground-truth")
    for idx, rows in enumerate(prediction_sets):
        if set(_index_rows(rows, label=f"prediction[{idx}]") ) != set(truth_index):
            raise QuantiPhyError(f"prediction[{idx}] keys do not match ground truth")

    methods = [f"model:{idx}" for idx in range(len(prediction_sets))]
    if len(prediction_sets) > 1:
        methods.extend(["median", "geometric_mean", "arithmetic_mean"])
    folds = _stratified_folds(ground_truth_rows, fold_count)
    cv_scores: dict[str, float] = {}

    for method in methods:
        base = ensemble_prediction_sets(prediction_sets, method)
        fold_scores: list[float] = []
        for fold in range(fold_count):
            validation_keys = {key for key, assigned in folds.items() if assigned == fold}
            train_keys = set(truth_index) - validation_keys
            train_truth = _subset_by_keys(ground_truth_rows, train_keys)
            train_pred = _subset_by_keys(base, train_keys)
            scales = fit_category_scales(train_truth, train_pred)
            validation_truth = _subset_by_keys(ground_truth_rows, validation_keys)
            validation_pred = _apply_scales(_subset_by_keys(base, validation_keys), scales)
            fold_scores.append(score_prediction_rows(validation_truth, validation_pred, require_all_categories=True)["mra_average"])
        cv_scores[method] = sum(fold_scores) / len(fold_scores)

    # Prefer simpler single-model selection on exact ties, then median/geometric/arithmetic.
    priority = {method: idx for idx, method in enumerate(methods)}
    selected = max(methods, key=lambda method: (cv_scores[method], -priority[method]))
    full_base = ensemble_prediction_sets(prediction_sets, selected)
    full_scales = fit_category_scales(ground_truth_rows, full_base)
    full_scaled = _apply_scales(full_base, full_scales)
    full_score = score_prediction_rows(ground_truth_rows, full_scaled, require_all_categories=True)["mra_average"]

    return {
        "schema_version": SCHEMA_VERSION,
        "method": selected,
        "prediction_names": names,
        "category_scales": {category: full_scales[category] for category in CATEGORIES},
        "cv": {
            "fold_count": fold_count,
            "selection_mra": cv_scores[selected],
            "candidate_mra": {method: cv_scores[method] for method in methods},
            "split": "sha256(video_id\\0question), category-stratified round-robin",
        },
        "full_validation_mra": full_score,
        "official_thresholds": list(THRESHOLDS),
        "official_macro_categories": list(CATEGORIES),
    }


def apply_recipe(
    recipe: Mapping[str, Any],
    prediction_sets: Sequence[Sequence[Mapping[str, Any]]],
    *,
    prediction_names: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if int(recipe.get("schema_version", -1)) != SCHEMA_VERSION:
        raise QuantiPhyError("unsupported recipe schema_version")
    expected_names = list(recipe.get("prediction_names", []))
    if prediction_names is not None and list(prediction_names) != expected_names:
        raise QuantiPhyError(f"prediction name/order mismatch: expected={expected_names!r}")
    method = str(recipe.get("method", ""))
    combined = ensemble_prediction_sets(prediction_sets, method)
    scales = recipe.get("category_scales")
    if not isinstance(scales, Mapping):
        raise QuantiPhyError("recipe category_scales missing")
    return _apply_scales(combined, {str(key): float(value) for key, value in scales.items()})


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_submission(rows: Sequence[Mapping[str, Any]], path: str | Path) -> dict[str, Any]:
    validate_prediction_rows(rows, reject_zero=True)
    if not rows:
        raise QuantiPhyError("cannot write empty submission")
    excluded = {GROUND_TRUTH_COLUMN, "mra"}
    fieldnames = [name for name in rows[0].keys() if name not in excluded]
    for required in (*KEY_COLUMNS, PREDICTION_COLUMN):
        if required not in fieldnames:
            fieldnames.append(required)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=_row_key):
            output = {name: row.get(name, "") for name in fieldnames}
            output[PREDICTION_COLUMN] = format(abs(_finite_number(row[PREDICTION_COLUMN], field=PREDICTION_COLUMN)), ".17g")
            writer.writerow(output)
    return {"path": str(target), "rows": len(rows), "sha256": file_sha256(target)}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
