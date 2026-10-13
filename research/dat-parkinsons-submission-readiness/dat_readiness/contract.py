# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Callable, Iterable

COLUMNS = ("uid", "is_pathologic")

def read_submission_format(path: str | Path) -> tuple[str, ...]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"submission format columns must be exactly {COLUMNS}")
        rows = list(reader)
    uids = tuple((row.get("uid") or "").strip() for row in rows)
    if any(not uid for uid in uids):
        raise ValueError("submission format contains an empty uid")
    if len(uids) != len(set(uids)):
        raise ValueError("submission format contains duplicate uid values")
    return uids

def validate_probability(value: object) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"prediction is not numeric: {value!r}") from exc
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError(f"prediction must be finite and in [0,1], got {probability!r}")
    return probability

def write_submission(path: str | Path, rows: Iterable[tuple[str, object]]) -> Path:
    output = Path(path)
    materialized = [(uid, validate_probability(prob)) for uid, prob in rows]
    uids = [uid for uid, _ in materialized]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate uid in predictions")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(materialized)
    return output

def run_independent(
    submission_format: str | Path,
    nifti_dir: str | Path,
    output_path: str | Path,
    predictor: Callable[[Path], object],
) -> Path:
    """Run one scan at a time; predictor receives no test-set context."""
    uids = read_submission_format(submission_format)
    nifti_root = Path(nifti_dir)
    predictions: list[tuple[str, float]] = []
    for uid in uids:
        scan_path = nifti_root / f"{uid}.nii.gz"
        if not scan_path.is_file():
            raise FileNotFoundError(scan_path)
        predictions.append((uid, validate_probability(predictor(scan_path))))
    return write_submission(output_path, predictions)
