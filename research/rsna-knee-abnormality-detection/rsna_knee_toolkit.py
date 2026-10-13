"""Data-free utilities for the 2026 RSNA Knee Abnormality Detection challenge.

This module intentionally has no Kaggle-data dependency. It validates the public
submission contract, computes the published macro-AUC metric, creates stable
group splits, and packages files deterministically.
"""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

LABELS: tuple[str, ...] = (
    "ACL",
    "MCL",
    "Medial Meniscus",
    "Lateral Meniscus",
    "Medial OA",
    "Lateral OA",
    "PF OA",
    "Effusion",
    "Synovitis",
    "Baker's",
    "Contusion",
    "Fracture",
)
SUBMISSION_COLUMNS: tuple[str, ...] = ("StudyInstanceUID", *LABELS)


class ContractError(ValueError):
    """Raised when a public competition contract is violated."""


def _probability(value: object, *, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{context}: expected a numeric confidence score") from exc
    if not math.isfinite(result):
        raise ContractError(f"{context}: score must be finite")
    if not 0.0 <= result <= 1.0:
        raise ContractError(f"{context}: score {result!r} is outside [0, 1]")
    return result


def validate_submission(path: str | Path) -> dict[str, object]:
    """Validate exact header, unique study IDs, and [0,1] finite probabilities."""
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SUBMISSION_COLUMNS:
            raise ContractError(
                "header mismatch: expected " + ",".join(SUBMISSION_COLUMNS)
            )

        seen: set[str] = set()
        rows = 0
        for row_number, row in enumerate(reader, start=2):
            study_uid = (row.get("StudyInstanceUID") or "").strip()
            if not study_uid:
                raise ContractError(f"row {row_number}: StudyInstanceUID is empty")
            if study_uid in seen:
                raise ContractError(
                    f"row {row_number}: duplicate StudyInstanceUID {study_uid!r}"
                )
            seen.add(study_uid)
            for label in LABELS:
                _probability(row.get(label), context=f"row {row_number} {label}")
            rows += 1

    if rows == 0:
        raise ContractError("submission has no prediction rows")
    return {"rows": rows, "labels": len(LABELS), "study_ids_unique": True}


def write_submission(
    study_ids: Sequence[str],
    predictions: Mapping[str, Sequence[float]],
    path: str | Path,
) -> Path:
    """Write a submission.csv using the exact published column order."""
    if len(set(study_ids)) != len(study_ids):
        raise ContractError("study_ids must be unique")
    if not study_ids:
        raise ContractError("study_ids must not be empty")

    for label in LABELS:
        if label not in predictions:
            raise ContractError(f"missing predictions for {label!r}")
        if len(predictions[label]) != len(study_ids):
            raise ContractError(
                f"{label!r}: expected {len(study_ids)} scores, "
                f"got {len(predictions[label])}"
            )

    extra = sorted(set(predictions) - set(LABELS))
    if extra:
        raise ContractError(f"unexpected prediction labels: {extra}")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(SUBMISSION_COLUMNS)
        for index, study_uid in enumerate(study_ids):
            if not str(study_uid).strip():
                raise ContractError(f"study_ids[{index}] is empty")
            scores = [
                _probability(
                    predictions[label][index],
                    context=f"study {study_uid!r} {label}",
                )
                for label in LABELS
            ]
            writer.writerow([study_uid, *[format(score, ".12g") for score in scores]])
    return output


def binary_auc(targets: Sequence[int], scores: Sequence[float]) -> float:
    """Compute ROC AUC exactly via pairwise comparisons, including tied scores."""
    if len(targets) != len(scores):
        raise ContractError("targets and scores must have equal length")
    if not targets:
        raise ContractError("AUC requires at least one sample")

    positives: list[float] = []
    negatives: list[float] = []
    for index, (target, score) in enumerate(zip(targets, scores)):
        if target not in (0, 1, False, True):
            raise ContractError(f"targets[{index}] must be binary")
        value = _probability(score, context=f"scores[{index}]")
        (positives if int(target) == 1 else negatives).append(value)

    if not positives or not negatives:
        raise ContractError("AUC is undefined without both positive and negative targets")

    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def macro_auc(
    targets_by_label: Mapping[str, Sequence[int]],
    scores_by_label: Mapping[str, Sequence[float]],
) -> float:
    """Compute the published mean ROC AUC across all twelve target labels."""
    missing_targets = [label for label in LABELS if label not in targets_by_label]
    missing_scores = [label for label in LABELS if label not in scores_by_label]
    if missing_targets or missing_scores:
        raise ContractError(
            f"missing labels: targets={missing_targets}, scores={missing_scores}"
        )

    aucs = [
        binary_auc(targets_by_label[label], scores_by_label[label])
        for label in LABELS
    ]
    return sum(aucs) / len(aucs)


def deterministic_group_split(
    groups: Iterable[str],
    *,
    validation_fraction: float = 0.2,
    seed: str = "rsna-knee-2026",
) -> dict[str, str]:
    """Assign each unique group wholly to train or validation, deterministically.

    The function hashes unique group identifiers, then selects the lowest hashes
    for validation. This is useful for patient/site grouping without row leakage.
    """
    if not 0.0 < validation_fraction < 1.0:
        raise ContractError("validation_fraction must be strictly between 0 and 1")

    unique_groups = sorted({str(group) for group in groups})
    if len(unique_groups) < 2:
        raise ContractError("at least two unique groups are required")

    ranked = sorted(
        unique_groups,
        key=lambda group: (
            hashlib.sha256(f"{seed}\0{group}".encode("utf-8")).digest(),
            group,
        ),
    )
    validation_count = max(
        1, min(len(ranked) - 1, round(len(ranked) * validation_fraction))
    )
    validation = set(ranked[:validation_count])
    return {
        group: ("validation" if group in validation else "train")
        for group in unique_groups
    }


def build_deterministic_zip(
    files: Mapping[str, bytes | str], output: str | Path
) -> tuple[Path, str]:
    """Write a byte-reproducible ZIP and return its SHA-256 digest."""
    if not files:
        raise ContractError("cannot package an empty file set")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for archive_name in sorted(files):
            if archive_name.startswith("/") or ".." in Path(archive_name).parts:
                raise ContractError(f"unsafe archive path: {archive_name!r}")
            payload = files[archive_name]
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            info = ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest
