#!/usr/bin/env python3
"""Build a deterministic, source-only Paceboard release archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED_SUFFIXES = {".py", ".html", ".js", ".css", ".md"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in ALLOWED_SUFFIXES:
            continue
        if "__pycache__" in path.parts or path.name.startswith("."):
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if executable else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def build(output: Path) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files()
    manifest_rows: list[str] = []
    payloads: list[tuple[str, bytes, bool]] = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        manifest_rows.append(f"{digest(data)}  {len(data):>8}  {relative}")
        payloads.append((f"paceboard/{relative}", data, path.suffix == ".py"))
    manifest = ("PACEBOARD SOURCE MANIFEST v1\n" + "\n".join(manifest_rows) + "\n").encode("utf-8")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".paceboard-release-", suffix=".zip", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data, executable in payloads:
                archive.writestr(zip_info(name, executable), data)
            archive.writestr(zip_info("paceboard/MANIFEST.sha256"), manifest)
        artifact = temporary.read_bytes()
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "format": "paceboard-source-release/v1",
        "output": str(output),
        "file_count": len(files),
        "artifact_bytes": len(artifact),
        "artifact_sha256": digest(artifact),
        "manifest_sha256": digest(manifest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(args.output)), sort_keys=True))


if __name__ == "__main__":
    main()
