#!/usr/bin/env python3
"""Deterministic offline OCR baseline for the R.O.A.D. Barbados challenge.

The script deliberately keeps challenge data outside the repository.  It reads
the organizer-provided Test.csv and SampleSubmission.csv at runtime, resolves
the corresponding local images, and writes a schema-preserving submission.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence

from PIL import Image, ImageOps


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")


class BaselineError(RuntimeError):
    """Raised for an invalid input contract or failed OCR process."""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise BaselineError(f"{path}: CSV has no header")
        rows = [dict(row) for row in reader]
    if not rows:
        raise BaselineError(f"{path}: CSV has no rows")
    return list(reader.fieldnames), rows


def id_column(columns: Sequence[str]) -> str:
    for column in columns:
        if column.strip().casefold() == "id":
            return column
    raise BaselineError("CSV must contain an ID column (case-insensitive)")


def prediction_column(sample_columns: Sequence[str], sample_id: str) -> str:
    candidates = [column for column in sample_columns if column != sample_id]
    if len(candidates) != 1:
        raise BaselineError(
            "SampleSubmission.csv must contain exactly one prediction column "
            f"besides {sample_id!r}; found {candidates!r}"
        )
    return candidates[0]


def validate_contract(
    test_columns: Sequence[str],
    test_rows: Sequence[dict[str, str]],
    sample_columns: Sequence[str],
    sample_rows: Sequence[dict[str, str]],
) -> tuple[str, str, str]:
    test_id = id_column(test_columns)
    sample_id = id_column(sample_columns)
    prediction = prediction_column(sample_columns, sample_id)

    test_ids = [row.get(test_id, "").strip() for row in test_rows]
    sample_ids = [row.get(sample_id, "").strip() for row in sample_rows]
    if any(not value for value in test_ids + sample_ids):
        raise BaselineError("ID values must be non-empty")
    if len(test_ids) != len(set(test_ids)):
        raise BaselineError("Test.csv contains duplicate IDs")
    if len(sample_ids) != len(set(sample_ids)):
        raise BaselineError("SampleSubmission.csv contains duplicate IDs")
    if set(test_ids) != set(sample_ids):
        missing = sorted(set(test_ids) - set(sample_ids))[:5]
        extra = sorted(set(sample_ids) - set(test_ids))[:5]
        raise BaselineError(
            "Test and sample ID sets differ; "
            f"missing_from_sample={missing}, extra_in_sample={extra}"
        )
    return test_id, sample_id, prediction


def build_image_index(images_dir: Path) -> dict[str, Path]:
    if not images_dir.is_dir():
        raise BaselineError(f"images directory does not exist: {images_dir}")
    index: dict[str, Path] = {}
    collisions: set[str] = set()
    for path in sorted(images_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in IMAGE_SUFFIXES:
            continue
        for key in (path.name.casefold(), path.stem.casefold()):
            if key in index and index[key] != path:
                collisions.add(key)
            else:
                index[key] = path
    for key in collisions:
        index.pop(key, None)
    if not index:
        raise BaselineError(f"no supported image files found under {images_dir}")
    return index


def resolve_image(identifier: str, index: dict[str, Path]) -> Path:
    raw = identifier.strip()
    if not raw:
        raise BaselineError("cannot resolve an empty image ID")
    if Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise BaselineError(f"unsafe image ID: {identifier!r}")
    basename = Path(raw).name.casefold()
    keys = [basename, Path(basename).stem]
    for suffix in IMAGE_SUFFIXES:
        keys.append(f"{Path(basename).stem}{suffix}")
    matches = {index[key] for key in keys if key in index}
    if len(matches) == 1:
        return matches.pop()
    if len(matches) > 1:
        raise BaselineError(f"ambiguous image ID: {identifier!r}")
    raise BaselineError(f"image not found for ID: {identifier!r}")


def normalize_image(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        if gray.height < 64:
            scale = max(2, (64 + gray.height - 1) // gray.height)
            gray = gray.resize(
                (gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS
            )
        gray = ImageOps.expand(gray, border=16, fill=255)
        gray.save(destination, format="PNG", optimize=True)


def parse_tsv(tsv: str) -> tuple[str, float, int]:
    reader = csv.DictReader(tsv.splitlines(), delimiter="\t")
    words: list[str] = []
    weighted_confidences: list[float] = []
    weights: list[int] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            confidence = -1
        if not text or confidence < 0:
            continue
        words.append(text)
        weight = max(1, len(re.sub(r"\W", "", text)))
        weighted_confidences.append(confidence * weight)
        weights.append(weight)
    score = sum(weighted_confidences) / sum(weights) if weights else -1.0
    return " ".join(words), score, len(words)


def tesseract_candidate(
    image: Path, tesseract: str, language: str, psm: int
) -> tuple[str, float, int]:
    command = [
        tesseract,
        str(image),
        "stdout",
        "-l",
        language,
        "--psm",
        str(psm),
        "tsv",
        "-c",
        "preserve_interword_spaces=1",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["unknown error"]
        raise BaselineError(
            f"tesseract failed for {image.name}, psm={psm}: {detail[0]}"
        )
    return parse_tsv(result.stdout)


def ocr_image(
    source: Path,
    *,
    tesseract: str,
    language: str,
    psms: Sequence[int],
    work_dir: Path,
) -> tuple[str, dict[str, object]]:
    normalized = work_dir / f"{source.stem}.normalized.png"
    normalize_image(source, normalized)
    candidates: list[tuple[str, float, int, int]] = []
    for psm in psms:
        text, score, word_count = tesseract_candidate(
            normalized, tesseract, language, psm
        )
        candidates.append((text, score, word_count, psm))
    best = max(candidates, key=lambda item: (item[1], item[2], -psms.index(item[3])))
    text, confidence, word_count, psm = best
    return text, {
        "image": source.name,
        "psm": psm,
        "confidence": round(confidence, 6),
        "word_count": word_count,
        "empty": not bool(text),
    }


def parse_psms(value: str) -> tuple[int, ...]:
    try:
        psms = tuple(int(item) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PSMs must be comma-separated integers") from exc
    if not psms or any(psm < 0 or psm > 13 for psm in psms):
        raise argparse.ArgumentTypeError("PSMs must be between 0 and 13")
    return psms


def write_submission(
    sample_columns: Sequence[str],
    sample_rows: Sequence[dict[str, str]],
    sample_id: str,
    prediction: str,
    predictions: dict[str, str],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sample_columns)
        writer.writeheader()
        for row in sample_rows:
            identifier = row[sample_id].strip()
            rendered = dict(row)
            rendered[prediction] = predictions[identifier]
            writer.writerow(rendered)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--test-csv", type=Path, required=True)
    result.add_argument("--sample-submission", type=Path, required=True)
    result.add_argument("--images-dir", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--report", type=Path)
    result.add_argument("--tesseract", default="tesseract")
    result.add_argument("--language", default="eng")
    result.add_argument("--psms", type=parse_psms, default=(6, 7, 13))
    result.add_argument(
        "--allow-empty",
        action="store_true",
        help="write rows with empty OCR output instead of failing the run",
    )
    result.add_argument(
        "--limit",
        type=int,
        help="process only the first N sample rows (benchmark/debug only)",
    )
    return result


def run(args: argparse.Namespace) -> dict[str, object]:
    executable = shutil.which(args.tesseract)
    if not executable:
        raise BaselineError(f"tesseract executable not found: {args.tesseract}")
    test_columns, test_rows = read_csv(args.test_csv)
    sample_columns, sample_rows = read_csv(args.sample_submission)
    _, sample_id, prediction = validate_contract(
        test_columns, test_rows, sample_columns, sample_rows
    )
    if args.limit is not None:
        if args.limit <= 0:
            raise BaselineError("--limit must be positive")
        sample_rows = sample_rows[: args.limit]

    index = build_image_index(args.images_dir)
    predictions: dict[str, str] = {}
    receipts: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="road-ocr-") as temporary:
        work_dir = Path(temporary)
        for row in sample_rows:
            identifier = row[sample_id].strip()
            source = resolve_image(identifier, index)
            text, receipt = ocr_image(
                source,
                tesseract=executable,
                language=args.language,
                psms=args.psms,
                work_dir=work_dir,
            )
            predictions[identifier] = text
            receipts.append({"id": identifier, **receipt})

    empty = sum(bool(item["empty"]) for item in receipts)
    if empty and not args.allow_empty:
        raise BaselineError(
            f"OCR produced {empty} empty predictions; inspect the report or use "
            "--allow-empty explicitly"
        )
    write_submission(
        sample_columns,
        sample_rows,
        sample_id,
        prediction,
        predictions,
        args.output,
    )
    confidences = [
        float(item["confidence"])
        for item in receipts
        if float(item["confidence"]) >= 0
    ]
    report: dict[str, object] = {
        "state": "BASELINE_COMPLETE",
        "rows": len(receipts),
        "empty_predictions": empty,
        "prediction_column": prediction,
        "psms": list(args.psms),
        "mean_selected_confidence": round(statistics.fmean(confidences), 6)
        if confidences
        else None,
        "items": receipts,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    args = parser().parse_args()
    try:
        report = run(args)
    except BaselineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: value for key, value in report.items() if key != "items"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
