# SPDX-License-Identifier: Apache-2.0
"""Identity-free opponent-family gating primitives for TITAN S10.

This module is deliberately additive.  It classifies only public prefix
patterns and returns whether an already-existing GOOP policy is admissible.
Unknown or low-confidence prefixes fall back to canonical.  It accepts no
opponent name/id, submission metadata, or future-action fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any

FAMILIES = ("early_unlock", "animal", "hire", "route", "market")
FAMILY_SET = frozenset(FAMILIES)
FEATURE_FIELDS = (
    "early_unlock_events",
    "animal_events",
    "hire_events",
    "route_events",
    "market_events",
)
PREFIX_FIELDS = frozenset(("turns_observed",) + FEATURE_FIELDS)
PPM = 1_000_000
LOSS_MAX_BP = 10_000


class UnsafePrefix(ValueError):
    """Raised when public-prefix or offline-evaluation data is unsafe/invalid."""


def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise UnsafePrefix(f"{name} must be an int in [{low}, {high}]")
    return value


def _normalize_positive(values: Sequence[int], total: int = PPM) -> tuple[int, ...]:
    if not values or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise UnsafePrefix("normalization values must be nonnegative ints")
    denominator = sum(values)
    if denominator == 0:
        return tuple(0 for _ in values)
    floors = [value * total // denominator for value in values]
    remainder = total - sum(floors)
    residues = [(value * total) % denominator for value in values]
    order = sorted(range(len(values)), key=lambda index: (-residues[index], index))
    for index in order[:remainder]:
        floors[index] += 1
    return tuple(floors)


@dataclass(frozen=True)
class PublicPrefix:
    """Only behavior observable from the public prefix before the gated action."""

    turns_observed: int
    early_unlock_events: int
    animal_events: int
    hire_events: int
    route_events: int
    market_events: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "PublicPrefix":
        if not isinstance(row, Mapping):
            raise UnsafePrefix("prefix must be a mapping")
        keys = frozenset(row)
        if keys != PREFIX_FIELDS:
            missing = sorted(PREFIX_FIELDS - keys)
            extra = sorted(keys - PREFIX_FIELDS, key=repr)
            raise UnsafePrefix(f"prefix fields mismatch: missing={missing} extra={extra}")
        turns = _bounded_int(row["turns_observed"], "turns_observed", 1, 10_000)
        counts = {
            field: _bounded_int(row[field], field, 0, 1_000_000)
            for field in FEATURE_FIELDS
        }
        return cls(turns_observed=turns, **counts)

    def feature_vector_ppm(self) -> tuple[int, ...]:
        return _normalize_positive(tuple(getattr(self, field) for field in FEATURE_FIELDS))


@dataclass(frozen=True)
class Prediction:
    family: str | None
    confidence_ppm: int

    def __post_init__(self) -> None:
        if self.family is not None and self.family not in FAMILY_SET:
            raise UnsafePrefix(f"unknown family: {self.family}")
        _bounded_int(self.confidence_ppm, "confidence_ppm", 0, PPM)


@dataclass(frozen=True)
class GateDecision:
    use_goop: bool
    family: str | None
    confidence_ppm: int
    reason: str


def gate_prediction(prediction: Prediction, *, threshold_ppm: int = 600_000) -> GateDecision:
    threshold = _bounded_int(threshold_ppm, "threshold_ppm", 1, PPM)
    if prediction.family is None:
        return GateDecision(False, None, prediction.confidence_ppm, "unknown_prefix")
    if prediction.confidence_ppm < threshold:
        return GateDecision(False, prediction.family, prediction.confidence_ppm, "low_confidence")
    return GateDecision(True, prediction.family, prediction.confidence_ppm, "confident_public_family")


def rules_prediction(prefix: PublicPrefix | Mapping[str, Any]) -> Prediction:
    """Simple deterministic baseline: unique strongest observed pattern."""
    if not isinstance(prefix, PublicPrefix):
        prefix = PublicPrefix.from_mapping(prefix)
    vector = prefix.feature_vector_ppm()
    if not any(vector):
        return Prediction(None, 0)
    best = max(vector)
    best_indices = [index for index, value in enumerate(vector) if value == best]
    if len(best_indices) != 1:
        return Prediction(None, best)
    return Prediction(FAMILIES[best_indices[0]], best)


@dataclass(frozen=True)
class LabeledPrefix:
    """Offline outcome row; the behavior-family label is never classifier input."""

    family: str
    prefix: PublicPrefix
    goop_loss_bp: int = 0

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "LabeledPrefix":
        if not isinstance(row, Mapping):
            raise UnsafePrefix("labeled row must be a mapping")
        expected = frozenset({"family", "prefix", "goop_loss_bp"})
        keys = frozenset(row)
        if keys != expected:
            missing = sorted(expected - keys)
            extra = sorted(keys - expected, key=repr)
            raise UnsafePrefix(f"labeled fields mismatch: missing={missing} extra={extra}")
        family = row["family"]
        if not isinstance(family, str) or family not in FAMILY_SET:
            raise UnsafePrefix("family must be one fixed public-behavior family")
        prefix = row["prefix"]
        if not isinstance(prefix, PublicPrefix):
            prefix = PublicPrefix.from_mapping(prefix)
        loss = _bounded_int(row["goop_loss_bp"], "goop_loss_bp", 0, LOSS_MAX_BP)
        return cls(family=family, prefix=prefix, goop_loss_bp=loss)


@dataclass(frozen=True)
class CentroidClassifier:
    """Tiny fixed-point prototype classifier; deterministic and dependency-free."""

    centroids: tuple[tuple[int, ...] | None, ...]
    support: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.centroids) != len(FAMILIES) or len(self.support) != len(FAMILIES):
            raise UnsafePrefix("classifier shape must match fixed family vocabulary")
        for index, (centroid, count) in enumerate(zip(self.centroids, self.support)):
            _bounded_int(count, f"support[{index}]", 0, 1_000_000)
            if count == 0:
                if centroid is not None:
                    raise UnsafePrefix("unsupported family cannot have a centroid")
                continue
            if centroid is None or len(centroid) != len(FEATURE_FIELDS):
                raise UnsafePrefix("supported family requires one complete centroid")
            if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= PPM for v in centroid):
                raise UnsafePrefix("centroid values must be integer ppm")
            if sum(centroid) not in {0, PPM}:
                raise UnsafePrefix("centroid must be zero-vector or normalized ppm")

    @classmethod
    def fit(cls, rows: Sequence[LabeledPrefix | Mapping[str, Any]]) -> "CentroidClassifier":
        sums = [[0] * len(FEATURE_FIELDS) for _ in FAMILIES]
        support = [0] * len(FAMILIES)
        for raw in rows:
            row = raw if isinstance(raw, LabeledPrefix) else LabeledPrefix.from_mapping(raw)
            family_index = FAMILIES.index(row.family)
            vector = row.prefix.feature_vector_ppm()
            for feature_index, value in enumerate(vector):
                sums[family_index][feature_index] += value
            support[family_index] += 1
        centroids = []
        for family_index, count in enumerate(support):
            if count == 0:
                centroids.append(None)
                continue
            averages = [value // count for value in sums[family_index]]
            centroids.append(_normalize_positive(averages))
        return cls(tuple(centroids), tuple(support))

    def predict(self, prefix: PublicPrefix | Mapping[str, Any]) -> Prediction:
        if not isinstance(prefix, PublicPrefix):
            prefix = PublicPrefix.from_mapping(prefix)
        vector = prefix.feature_vector_ppm()
        if not any(vector):
            return Prediction(None, 0)

        scored: list[tuple[int, int]] = []
        for family_index, centroid in enumerate(self.centroids):
            if centroid is None:
                continue
            distance = sum(abs(left - right) for left, right in zip(vector, centroid))
            score = 2_000_001 - distance
            scored.append((family_index, max(1, score)))
        if not scored:
            return Prediction(None, 0)

        probabilities = _normalize_positive([score for _, score in scored])
        best_score = max(score for _, score in scored)
        best_locals = [i for i, (_, score) in enumerate(scored) if score == best_score]
        best_probability = max(probabilities[i] for i in best_locals)
        if len(best_locals) != 1:
            return Prediction(None, best_probability)
        family_index = scored[best_locals[0]][0]
        return Prediction(FAMILIES[family_index], best_probability)


@dataclass(frozen=True)
class CalibratedCentroidClassifier:
    """Centroid classifier with a conservative empirical confidence cap.

    The cap is learned only from labeled behavior-family calibration rows. It
    cannot raise raw confidence; sparse or poor calibration pushes the gate
    toward canonical fallback.
    """

    base: CentroidClassifier
    confidence_cap_ppm: int
    calibration_samples: int

    def __post_init__(self) -> None:
        _bounded_int(self.confidence_cap_ppm, "confidence_cap_ppm", 0, PPM)
        _bounded_int(self.calibration_samples, "calibration_samples", 0, 1_000_000)

    @classmethod
    def fit(
        cls,
        training_rows: Sequence[LabeledPrefix | Mapping[str, Any]],
        calibration_rows: Sequence[LabeledPrefix | Mapping[str, Any]],
    ) -> "CalibratedCentroidClassifier":
        base = CentroidClassifier.fit(training_rows)
        parsed = tuple(
            row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row)
            for row in calibration_rows
        )
        classified = 0
        correct = 0
        for row in parsed:
            prediction = base.predict(row.prefix)
            if prediction.family is None:
                continue
            classified += 1
            correct += int(prediction.family == row.family)
        cap = (correct * PPM // classified) if classified else 0
        return cls(base=base, confidence_cap_ppm=cap, calibration_samples=len(parsed))

    def predict(self, prefix: PublicPrefix | Mapping[str, Any]) -> Prediction:
        raw = self.base.predict(prefix)
        if raw.family is None:
            return raw
        return Prediction(raw.family, min(raw.confidence_ppm, self.confidence_cap_ppm))


def family_disjoint_folds(rows: Sequence[LabeledPrefix | Mapping[str, Any]]) -> tuple[tuple[str, tuple[LabeledPrefix, ...], tuple[LabeledPrefix, ...]], ...]:
    parsed = tuple(row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row) for row in rows)
    folds = []
    for family in FAMILIES:
        test = tuple(row for row in parsed if row.family == family)
        if not test:
            continue
        train = tuple(row for row in parsed if row.family != family)
        folds.append((family, train, test))
    return tuple(folds)


def _calibration_error_bp(predictions: Sequence[Prediction], truths: Sequence[str]) -> int:
    if len(predictions) != len(truths):
        raise UnsafePrefix("prediction/truth lengths differ")
    bins = [{"count": 0, "confidence": 0, "correct": 0} for _ in range(10)]
    classified = 0
    for prediction, truth in zip(predictions, truths):
        if prediction.family is None:
            continue
        classified += 1
        bucket = min(9, prediction.confidence_ppm * 10 // (PPM + 1))
        row = bins[bucket]
        row["count"] += 1
        row["confidence"] += prediction.confidence_ppm
        row["correct"] += int(prediction.family == truth)
    if classified == 0:
        return 0
    weighted_ppm = 0
    for row in bins:
        if row["count"] == 0:
            continue
        avg_confidence = row["confidence"] // row["count"]
        accuracy_ppm = row["correct"] * PPM // row["count"]
        weighted_ppm += abs(avg_confidence - accuracy_ppm) * row["count"]
    ece_ppm = weighted_ppm // classified
    return ece_ppm // 100


def evaluate_predictions(
    rows: Sequence[LabeledPrefix | Mapping[str, Any]],
    predictions: Sequence[Prediction],
    *,
    threshold_ppm: int = 600_000,
    ungated: bool = False,
) -> dict[str, Any]:
    parsed = tuple(row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row) for row in rows)
    if len(parsed) != len(predictions):
        raise UnsafePrefix("row/prediction lengths differ")
    threshold = _bounded_int(threshold_ppm, "threshold_ppm", 1, PPM)

    confusion = {
        family: {predicted: 0 for predicted in (*FAMILIES, "unknown")}
        for family in FAMILIES
    }
    correct = 0
    classified = 0
    fallback = 0
    goop_uses = 0
    gated_goop_loss_bp = 0
    misclassification_loss_bp = 0

    for row, prediction in zip(parsed, predictions):
        label = prediction.family if prediction.family is not None else "unknown"
        confusion[row.family][label] += 1
        if prediction.family is not None:
            classified += 1
            correct += int(prediction.family == row.family)

        decision = GateDecision(True, prediction.family, prediction.confidence_ppm, "ungated") if ungated else gate_prediction(prediction, threshold_ppm=threshold)
        if decision.use_goop:
            goop_uses += 1
            gated_goop_loss_bp += row.goop_loss_bp
            if prediction.family != row.family:
                misclassification_loss_bp += row.goop_loss_bp
        else:
            fallback += 1

    return {
        "samples": len(parsed),
        "classified": classified,
        "correct": correct,
        "accuracy_bp": (correct * LOSS_MAX_BP // len(parsed)) if parsed else 0,
        "calibration_error_bp": _calibration_error_bp(predictions, [row.family for row in parsed]),
        "fallback": fallback,
        "goop_uses": goop_uses,
        "gated_goop_loss_bp": gated_goop_loss_bp,
        "misclassification_loss_bp": misclassification_loss_bp,
        "confusion": confusion,
    }


def evaluate_rules(rows: Sequence[LabeledPrefix | Mapping[str, Any]], *, threshold_ppm: int = 600_000) -> dict[str, Any]:
    parsed = tuple(row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row) for row in rows)
    return evaluate_predictions(parsed, [rules_prediction(row.prefix) for row in parsed], threshold_ppm=threshold_ppm)


def evaluate_classifier(
    classifier: CentroidClassifier | CalibratedCentroidClassifier,
    rows: Sequence[LabeledPrefix | Mapping[str, Any]],
    *,
    threshold_ppm: int = 600_000,
) -> dict[str, Any]:
    parsed = tuple(row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row) for row in rows)
    return evaluate_predictions(parsed, [classifier.predict(row.prefix) for row in parsed], threshold_ppm=threshold_ppm)


def evaluate_ungated(rows: Sequence[LabeledPrefix | Mapping[str, Any]]) -> dict[str, Any]:
    parsed = tuple(row if isinstance(row, LabeledPrefix) else LabeledPrefix.from_mapping(row) for row in rows)
    unknown = [Prediction(None, 0) for _ in parsed]
    return evaluate_predictions(parsed, unknown, ungated=True)
