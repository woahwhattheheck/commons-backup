"""Validate Lost in Transcription submission ZIP/CSV contracts without protected data."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path, PurePosixPath
import zipfile

REQUIRED_PREDICTION_COLUMNS = {"audio_filename", "transcript"}
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus"}


def validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "main.py" not in names:
            raise ValueError("submission.zip must contain main.py at archive root")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe archive path: {name}")
            if member.suffix.lower() in AUDIO_SUFFIXES:
                raise ValueError(f"competition audio must not be packaged: {name}")


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not REQUIRED_PREDICTION_COLUMNS.issubset(fields):
            raise ValueError(
                "submission.csv must contain audio_filename and transcript columns"
            )
        rows = list(reader)
    return rows


def validate_csv(predicted_path: Path, format_path: Path | None = None) -> None:
    rows = _read_rows(predicted_path)
    filenames = [row["audio_filename"] for row in rows]
    if len(filenames) != len(set(filenames)):
        raise ValueError("duplicate audio_filename in submission.csv")

    if format_path is not None:
        with format_path.open("r", encoding="utf-8", newline="") as handle:
            format_rows = list(csv.DictReader(handle))
        expected = [row["audio_filename"] for row in format_rows]
        if set(filenames) != set(expected):
            missing = sorted(set(expected) - set(filenames))
            extra = sorted(set(filenames) - set(expected))
            raise ValueError(f"prediction keys differ; missing={missing[:3]} extra={extra[:3]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", type=Path)
    parser.add_argument("--csv", dest="csv_path", type=Path)
    parser.add_argument("--format", dest="format_path", type=Path)
    args = parser.parse_args()
    if not args.zip_path and not args.csv_path:
        parser.error("provide --zip and/or --csv")
    if args.zip_path:
        validate_zip(args.zip_path)
    if args.csv_path:
        validate_csv(args.csv_path, args.format_path)
    print("VALID")


if __name__ == "__main__":
    main()
