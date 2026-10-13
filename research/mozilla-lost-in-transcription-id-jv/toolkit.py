#!/usr/bin/env python3
"""Offline helpers for Mozilla/DrivenData Lost in Transcription submissions.

No competition audio, transcripts, or model weights are required by this module.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


_REQUIRED_COLUMNS = ("audio_filename", "transcript")
_FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def normalize_for_scoring(text: str) -> str:
    """Mirror the public scorer's text normalization for local diagnostics.

    The implementation is independent but intentionally follows the behavior
    documented by the pinned official scorer: remove annotations and selected
    punctuation, unwrap parentheticals, lowercase sentence starts except
    acronym-like starts, preserve ellipses, and collapse whitespace.
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)

    text = text.replace("~", "")
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\(\?+\)", " ", text)
    while re.search(r"\([^()]*\)", text):
        text = re.sub(r"\(([^()]*)\)", r"\1", text)
    text = text.replace("#x27;", "'")
    text = re.sub(r'[¿¡";:]+', " ", text)

    pattern = re.compile(r"(^\s*|[.!?—]\s*)([^\W\d_])([^\W\d_]?)", re.UNICODE)

    def lower_initial(match: re.Match[str]) -> str:
        delimiter, first, second = match.group(1), match.group(2), match.group(3)
        if first.isupper() and not (second and second.isupper()):
            first = first.lower()
        return delimiter + first + second

    text = pattern.sub(lower_initial, text)
    text = text.replace("—", ", ")
    text = re.sub(r",+", " ", text)
    text = re.sub(r"[!?]+", " ", text)
    sentinel = "\u0000ELLIPSIS\u0000"
    text = text.replace("...", sentinel).replace(".", " ").replace(sentinel, "...")
    while " ... " in text:
        text = text.replace(" ... ", " ")
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ErrorCounts:
    substitutions: int
    deletions: int
    insertions: int
    reference_words: int

    @property
    def wer(self) -> float:
        if self.reference_words == 0:
            return 0.0 if self.insertions == 0 else float("inf")
        return (self.substitutions + self.deletions + self.insertions) / self.reference_words


def _edit_counts(reference: Sequence[str], hypothesis: Sequence[str]) -> ErrorCounts:
    """Levenshtein alignment with deterministic S/D/I tie-breaking."""
    n, m = len(reference), len(hypothesis)
    dp: list[list[tuple[int, int, int, int]]] = [
        [(0, 0, 0, 0) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    for i in range(1, n + 1):
        dp[i][0] = (i, 0, i, 0)
    for j in range(1, m + 1):
        dp[0][j] = (j, 0, 0, j)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                continue
            sub = dp[i - 1][j - 1]
            delete = dp[i - 1][j]
            insert = dp[i][j - 1]
            candidates = [
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (delete[0] + 1, delete[1], delete[2] + 1, delete[3]),
                (insert[0] + 1, insert[1], insert[2], insert[3] + 1),
            ]
            dp[i][j] = min(candidates)

    _, substitutions, deletions, insertions = dp[n][m]
    return ErrorCounts(substitutions, deletions, insertions, n)


def corpus_wer(references: Iterable[str], hypotheses: Iterable[str]) -> ErrorCounts:
    """Compute corpus-level WER after official-style normalization."""
    refs = list(references)
    hyps = list(hypotheses)
    if len(refs) != len(hyps):
        raise ValueError(f"reference/prediction length mismatch: {len(refs)} != {len(hyps)}")

    total_s = total_d = total_i = total_n = 0
    for ref, hyp in zip(refs, hyps):
        ref_tokens = normalize_for_scoring(ref).split()
        hyp_tokens = normalize_for_scoring(hyp).split()
        counts = _edit_counts(ref_tokens, hyp_tokens)
        total_s += counts.substitutions
        total_d += counts.deletions
        total_i += counts.insertions
        total_n += counts.reference_words
    return ErrorCounts(total_s, total_d, total_i, total_n)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_submission_rows(
    expected_rows: Sequence[Mapping[str, str]],
    prediction_rows: Sequence[Mapping[str, str]],
) -> None:
    """Validate exact filename coverage and output schema."""
    if any(set(row.keys()) != set(_REQUIRED_COLUMNS) for row in prediction_rows):
        raise ValueError("prediction rows must contain exactly audio_filename,transcript")

    expected = [row.get("audio_filename", "") for row in expected_rows]
    predicted = [row.get("audio_filename", "") for row in prediction_rows]

    if any(not name for name in expected):
        raise ValueError("expected rows contain a blank audio_filename")
    if any(not name for name in predicted):
        raise ValueError("prediction rows contain a blank audio_filename")
    if len(set(expected)) != len(expected):
        raise ValueError("expected rows contain duplicate audio_filename values")
    if len(set(predicted)) != len(predicted):
        raise ValueError("prediction rows contain duplicate audio_filename values")

    missing = sorted(set(expected) - set(predicted))
    extra = sorted(set(predicted) - set(expected))
    if missing or extra:
        raise ValueError(f"filename coverage mismatch: missing={missing[:3]} extra={extra[:3]}")


def validate_submission_csv(submission_format: Path, predictions: Path) -> None:
    validate_submission_rows(read_csv_rows(submission_format), read_csv_rows(predictions))


def stable_split(
    rows: Sequence[Mapping[str, str]],
    *,
    seed: str = "mozilla-id-jv-v1",
    validation_fraction: float = 0.2,
    group_column: str | None = None,
) -> list[str]:
    """Return deterministic train/validation labels without reordering rows.

    If `group_column` is supplied, all rows sharing that value stay together.
    """
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")

    labels: list[str] = []
    threshold = int(validation_fraction * (1 << 64))
    for row in rows:
        filename = row.get("audio_filename", "")
        if not filename:
            raise ValueError("every row needs audio_filename")
        group = row.get(group_column, "") if group_column else filename
        if group_column and not group:
            raise ValueError(f"missing group value in {group_column}")
        digest = hashlib.sha256(f"{seed}\0{group}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big")
        labels.append("validation" if bucket < threshold else "train")
    return labels


def write_split_manifest(
    input_csv: Path,
    output_csv: Path,
    *,
    seed: str = "mozilla-id-jv-v1",
    validation_fraction: float = 0.2,
    group_column: str | None = None,
) -> None:
    rows = read_csv_rows(input_csv)
    if not rows:
        raise ValueError("input metadata is empty")
    labels = stable_split(
        rows,
        seed=seed,
        validation_fraction=validation_fraction,
        group_column=group_column,
    )
    fieldnames = list(rows[0].keys()) + ["split"]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row, label in zip(rows, labels):
            writer.writerow({**row, "split": label})


def build_submission_zip(source_dir: Path, output_zip: Path) -> str:
    """Build a byte-stable submission archive and return its SHA-256.

    The source directory must have `main.py` at its root. Symlinks are rejected.
    """
    source_dir = source_dir.resolve()
    main_py = source_dir / "main.py"
    if not main_py.is_file():
        raise ValueError("source directory must contain root-level main.py")

    files = [path for path in source_dir.rglob("*") if path.is_file()]
    for path in files:
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in submission archive: {path}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with io.BytesIO() as buffer:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(files, key=lambda p: p.relative_to(source_dir).as_posix()):
                rel = path.relative_to(source_dir).as_posix()
                if rel.startswith("/") or ".." in Path(rel).parts:
                    raise ValueError(f"unsafe archive path: {rel}")
                info = zipfile.ZipInfo(rel, date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        payload = buffer.getvalue()

    output_zip.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def inspect_submission_zip(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "main.py" not in names:
            raise ValueError("submission.zip has no root-level main.py")
        if len(names) != len(set(names)):
            raise ValueError("submission.zip contains duplicate paths")
        for name in names:
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts:
                raise ValueError(f"unsafe ZIP member: {name}")
        return names
