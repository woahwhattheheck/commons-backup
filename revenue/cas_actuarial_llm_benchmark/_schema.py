# SPDX-License-Identifier: MPL-2.0
"""Deterministic evidence core for a CAS-style actuarial LLM benchmark.

The module is deliberately offline. It validates task, dataset, model, and run
artifacts; enforces one source-bound evaluation universe per task; computes
objective metrics; and emits a content-addressed comparison snapshot. It never
calls model providers and does not assert actuarial validity of task content.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from typing import Any


class BenchmarkInputError(ValueError):
    """Raised when benchmark evidence is malformed, ambiguous, or incomplete."""


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,127}$")
_REQUIRED_COMMERCIAL = frozenset({"openai", "anthropic", "google"})
_SUPPORTED_TASK_TYPES = frozenset({"binary", "multiclass"})
_FIXED_METRIC_RE = re.compile(r"^\d+\.\d{12}$")


def _canon(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BenchmarkInputError(
            "evidence must be canonical JSON without non-finite values"
        ) from exc
    return text.encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _plain_key(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise BenchmarkInputError(f"{field} must be a string")
    normalized = value.strip()
    if not _KEY_RE.fullmatch(normalized):
        raise BenchmarkInputError(f"{field} must be a stable lowercase key")
    return normalized


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BenchmarkInputError(f"{field} must be a lowercase sha256 hex digest")
    return value


def _nonempty(value: Any, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str):
        raise BenchmarkInputError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > max_len:
        raise BenchmarkInputError(f"{field} must be non-empty and <= {max_len} characters")
    return normalized


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise BenchmarkInputError(f"{field} must be numeric")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise BenchmarkInputError(f"{field} must be decimal text") from exc
        if not result.is_finite():
            raise BenchmarkInputError(f"{field} must be finite")
        return result
    raise BenchmarkInputError(f"{field} must be integer or exact decimal string")


def _ratio(value: Any, field: str) -> Decimal:
    result = _decimal(value, field)
    if result < 0 or result > 1:
        raise BenchmarkInputError(f"{field} must be within [0, 1]")
    return result


def _decimal_text(value: Decimal) -> str:
    """Return one exact canonical non-exponent decimal representation."""
    if not value.is_finite():
        raise BenchmarkInputError("record manifests cannot contain non-finite decimals")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"0", "-0"} else text


def _normalize_universe_records(
    raw: Any,
    labels: list[str],
) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise BenchmarkInputError("evaluation universe records must be a non-empty list")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, record in enumerate(raw):
        if not isinstance(record, dict) or set(record) != {"item_id", "truth"}:
            raise BenchmarkInputError(
                "evaluation universe records must contain exactly item_id and truth"
            )
        item_id = _plain_key(record.get("item_id"), f"evaluation_universe[{index}].item_id")
        if item_id in seen:
            raise BenchmarkInputError("evaluation universe item_id values must be unique")
        seen.add(item_id)
        truth = record.get("truth")
        if truth not in labels:
            raise BenchmarkInputError("evaluation universe truth must be a declared task label")
        normalized.append({"item_id": item_id, "truth": truth})
    normalized.sort(key=lambda row: row["item_id"])
    return normalized


def _universe_payload(
    *,
    task_id: str,
    task_version: str,
    dataset_sha256: str,
    split_sha256: str,
    records: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_version": task_version,
        "dataset_sha256": dataset_sha256,
        "split_sha256": split_sha256,
        "records": records,
    }


def _task(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BenchmarkInputError("each task must be an object")
    task_id = _plain_key(raw.get("task_id"), "task_id")
    version = _plain_key(raw.get("version"), "task version")
    task_type = raw.get("task_type")
    if task_type not in _SUPPORTED_TASK_TYPES:
        raise BenchmarkInputError("task_type must be binary or multiclass")

    labels_raw = raw.get("labels")
    if not isinstance(labels_raw, list) or len(labels_raw) < 2:
        raise BenchmarkInputError("task labels must contain at least two labels")
    labels = [_plain_key(label, "label") for label in labels_raw]
    if len(set(labels)) != len(labels):
        raise BenchmarkInputError("task labels must be unique")
    if task_type == "binary" and len(labels) != 2:
        raise BenchmarkInputError("binary tasks must have exactly two labels")

    dataset = raw.get("dataset")
    if not isinstance(dataset, dict):
        raise BenchmarkInputError("task dataset must be an object")
    dataset_sha256 = _sha(dataset.get("sha256"), "dataset sha256")
    split_sha256 = _sha(dataset.get("split_sha256"), "dataset split_sha256")
    if dataset.get("license_status") != "confirmed_publishable":
        raise BenchmarkInputError("dataset license_status must be confirmed_publishable")
    license_reference = _nonempty(dataset.get("license_reference"), "license_reference")
    provenance = _nonempty(dataset.get("provenance"), "dataset provenance", max_len=1024)
    source_uri = _nonempty(dataset.get("source_uri"), "dataset source_uri", max_len=1024)
    if not source_uri.startswith("https://"):
        raise BenchmarkInputError("dataset source_uri must use https")
    evaluation_protocol_sha256 = _sha(
        raw.get("evaluation_protocol_sha256"),
        "evaluation protocol sha256",
    )

    universe = raw.get("evaluation_universe")
    if not isinstance(universe, dict) or set(universe) != {"sha256", "records"}:
        raise BenchmarkInputError(
            "evaluation_universe must contain exactly sha256 and records"
        )
    universe_records = _normalize_universe_records(universe.get("records"), labels)
    claimed_universe_sha256 = _sha(
        universe.get("sha256"), "evaluation universe sha256"
    )
    universe_payload = _universe_payload(
        task_id=task_id,
        task_version=version,
        dataset_sha256=dataset_sha256,
        split_sha256=split_sha256,
        records=universe_records,
    )
    computed_universe_sha256 = _digest(universe_payload)
    if claimed_universe_sha256 != computed_universe_sha256:
        raise BenchmarkInputError(
            "evaluation universe digest does not match canonical task cohort"
        )

    return {
        "task_id": task_id,
        "version": version,
        "task_type": task_type,
        "labels": labels,
        "dataset": {
            "sha256": dataset_sha256,
            "split_sha256": split_sha256,
            "license_status": "confirmed_publishable",
            "license_reference": license_reference,
            "provenance": provenance,
            "source_uri": source_uri,
        },
        "evaluation_protocol_sha256": evaluation_protocol_sha256,
        "evaluation_universe": {
            "sha256": computed_universe_sha256,
            "record_count": len(universe_records),
            "records": universe_records,
        },
    }


def _model(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BenchmarkInputError("each model must be an object")
    model_id = _plain_key(raw.get("model_id"), "model_id")
    model_version = _nonempty(raw.get("model_version"), "model_version")
    model_class = raw.get("model_class")
    if model_class not in {"commercial", "open"}:
        raise BenchmarkInputError("model_class must be commercial or open")
    provider = _plain_key(raw.get("provider"), "provider")
    artifact_sha256 = _sha(raw.get("artifact_sha256"), "model artifact_sha256")
    return {
        "model_id": model_id,
        "model_version": model_version,
        "model_class": model_class,
        "provider": provider,
        "artifact_sha256": artifact_sha256,
    }


def _normalize_probabilities(
    raw: Any,
    labels: list[str],
    field: str,
) -> dict[str, Decimal]:
    if not isinstance(raw, dict) or set(raw) != set(labels):
        raise BenchmarkInputError(f"{field} must provide exactly every task label")
    probabilities = {
        label: _ratio(raw[label], f"{field}.{label}")
        for label in labels
    }
    if sum(probabilities.values(), Decimal(0)) != Decimal(1):
        raise BenchmarkInputError(f"{field} probabilities must sum exactly to 1")
    return probabilities


def _record_manifest_payload(
    *,
    task: dict[str, Any],
    model: dict[str, Any],
    protocol_sha256: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    serializable_records = []
    for record in records:
        serializable_records.append(
            {
                "item_id": record["item_id"],
                "truth": record["truth"],
                "prediction": record["prediction"],
                "probabilities": {
                    label: _decimal_text(record["probabilities"][label])
                    for label in task["labels"]
                },
            }
        )
    return {
        "task_id": task["task_id"],
        "task_version": task["version"],
        "dataset_sha256": task["dataset"]["sha256"],
        "split_sha256": task["dataset"]["split_sha256"],
        "evaluation_universe_sha256": task["evaluation_universe"]["sha256"],
        "model_id": model["model_id"],
        "model_version": model["model_version"],
        "model_artifact_sha256": model["artifact_sha256"],
        "protocol_sha256": protocol_sha256,
        "records": serializable_records,
    }


def _run(raw: Any, task: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BenchmarkInputError("each run must be an object")
    run_id = _plain_key(raw.get("run_id"), "run_id")
    if raw.get("task_id") != task["task_id"] or raw.get("task_version") != task["version"]:
        raise BenchmarkInputError("run task identity/version does not match task manifest")
    if raw.get("dataset_sha256") != task["dataset"]["sha256"]:
        raise BenchmarkInputError("run dataset digest does not match task manifest")
    if raw.get("split_sha256") != task["dataset"]["split_sha256"]:
        raise BenchmarkInputError("run split digest does not match task manifest")
    if raw.get("model_id") != model["model_id"] or raw.get("model_version") != model["model_version"]:
        raise BenchmarkInputError("run model identity/version does not match model roster")
    if raw.get("model_artifact_sha256") != model["artifact_sha256"]:
        raise BenchmarkInputError("run model artifact digest does not match model roster")
    protocol_sha256 = _sha(raw.get("protocol_sha256"), "protocol_sha256")
    if protocol_sha256 != task["evaluation_protocol_sha256"]:
        raise BenchmarkInputError(
            "run protocol digest does not match task evaluation protocol"
        )

    records = raw.get("records")
    if not isinstance(records, list) or not records:
        raise BenchmarkInputError("run records must be a non-empty list")
    labels = task["labels"]
    seen: set[str] = set()
    normalized_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise BenchmarkInputError("run record must be an object")
        item_id = _plain_key(record.get("item_id"), f"records[{index}].item_id")
        if item_id in seen:
            raise BenchmarkInputError("run item_id values must be unique")
        seen.add(item_id)
        truth = record.get("truth")
        prediction = record.get("prediction")
        if truth not in labels or prediction not in labels:
            raise BenchmarkInputError("truth/prediction must be declared task labels")
        probabilities = _normalize_probabilities(
            record.get("probabilities"), labels, f"records[{index}].probabilities"
        )
        normalized_records.append(
            {
                "item_id": item_id,
                "truth": truth,
                "prediction": prediction,
                "probabilities": probabilities,
            }
        )
    normalized_records.sort(key=lambda row: row["item_id"])

    expected_truth = {
        row["item_id"]: row["truth"]
        for row in task["evaluation_universe"]["records"]
    }
    actual_truth = {row["item_id"]: row["truth"] for row in normalized_records}
    missing_ids = sorted(set(expected_truth) - set(actual_truth))
    extra_ids = sorted(set(actual_truth) - set(expected_truth))
    if missing_ids:
        raise BenchmarkInputError(
            "run is missing evaluation universe item_id values: " + ",".join(missing_ids)
        )
    if extra_ids:
        raise BenchmarkInputError(
            "run contains item_id values outside evaluation universe: " + ",".join(extra_ids)
        )
    truth_drift = sorted(
        item_id
        for item_id, truth in actual_truth.items()
        if expected_truth[item_id] != truth
    )
    if truth_drift:
        raise BenchmarkInputError(
            "run truth does not match evaluation universe for item_id values: "
            + ",".join(truth_drift)
        )

    manifest_payload = _record_manifest_payload(
        task=task,
        model=model,
        protocol_sha256=protocol_sha256,
        records=normalized_records,
    )
    return {
        "run_id": run_id,
        "protocol_sha256": protocol_sha256,
        "evaluation_universe_sha256": task["evaluation_universe"]["sha256"],
        "record_manifest_sha256": _digest(manifest_payload),
        "records": normalized_records,
    }


def _macro_f1(records: list[dict[str, Any]], labels: list[str]) -> Decimal:
    scores: list[Decimal] = []
    for label in labels:
        true_positive = sum(
            row["truth"] == label and row["prediction"] == label for row in records
        )
        false_positive = sum(
            row["truth"] != label and row["prediction"] == label for row in records
        )
        false_negative = sum(
            row["truth"] == label and row["prediction"] != label for row in records
        )
        denominator = (2 * true_positive) + false_positive + false_negative
        scores.append(
            Decimal(0)
            if denominator == 0
            else Decimal(2 * true_positive) / Decimal(denominator)
        )
    return sum(scores, Decimal(0)) / Decimal(len(scores))


def _metrics(task: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, str]:
    labels = task["labels"]
    count = Decimal(len(records))
    accuracy = Decimal(
        sum(row["truth"] == row["prediction"] for row in records)
    ) / count
    macro_f1 = _macro_f1(records, labels)
    with localcontext() as context:
        context.prec = 50
        brier_total = Decimal(0)
        log_loss_total = Decimal(0)
        for record in records:
            for label in labels:
                target = Decimal(1) if record["truth"] == label else Decimal(0)
                delta = record["probabilities"][label] - target
                brier_total += delta * delta
            p_true = record["probabilities"][record["truth"]]
            if p_true == 0:
                log_loss_total = Decimal("Infinity")
            elif log_loss_total.is_finite():
                log_loss_total -= p_true.ln()
        brier = brier_total / count
        if task["task_type"] == "binary":
            brier /= Decimal(2)
        log_loss = log_loss_total / count if log_loss_total.is_finite() else log_loss_total

    def render(value: Decimal) -> str:
        if not value.is_finite():
            return "Infinity"
        return format(value.quantize(Decimal("0.000000000001")), "f")

    return {
        "accuracy": render(accuracy),
        "macro_f1": render(macro_f1),
        "brier_score": render(brier),
        "log_loss": render(log_loss),
    }

