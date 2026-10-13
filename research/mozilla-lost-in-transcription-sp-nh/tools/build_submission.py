"""Create a byte-stable submission.zip from submission_src plus optional model assets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

FIXED_TIME = (2026, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {"__pycache__", ".DS_Store"}
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus"}


def iter_files(source_dir: Path):
    for path in sorted(p for p in source_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(source_dir)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if relative.suffix.lower() in AUDIO_SUFFIXES:
            raise ValueError(f"refusing to package competition-like audio: {relative}")
        yield path, relative


def build(source_dir: Path, output_zip: Path) -> str:
    source_dir = source_dir.resolve()
    if not (source_dir / "main.py").is_file():
        raise ValueError("submission source must contain root main.py")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in iter_files(source_dir):
            info = zipfile.ZipInfo(relative.as_posix(), date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())

    digest = hashlib.sha256(output_zip.read_bytes()).hexdigest()
    return digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).parents[1] / "submission_src")
    parser.add_argument("--output", type=Path, default=Path("submission.zip"))
    args = parser.parse_args()
    digest = build(args.source, args.output)
    print(f"{args.output}: sha256={digest}")


if __name__ == "__main__":
    main()
