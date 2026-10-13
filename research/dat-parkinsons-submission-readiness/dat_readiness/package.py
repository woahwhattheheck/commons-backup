# SPDX-License-Identifier: MIT
from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
FORBIDDEN_NAMES = {"submission_format.csv", "submission.csv"}

def _forbidden(relative: PurePosixPath) -> bool:
    lowered = relative.as_posix().lower()
    return relative.name.lower() in FORBIDDEN_NAMES or lowered.endswith(".nii") or lowered.endswith(".nii.gz") or "/niftis/" in f"/{lowered}/"

def collect_submission_files(source: str | Path) -> tuple[tuple[Path, PurePosixPath], ...]:
    root = Path(source)
    if not root.is_dir():
        raise ValueError(f"source directory not found: {root}")
    pairs = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in submission archive: {path}")
        if not path.is_file():
            continue
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if "__pycache__" in rel.parts or rel.name.endswith((".pyc", ".pyo")):
            continue
        if _forbidden(rel):
            raise ValueError(f"refusing competition-data/output-shaped artifact: {rel}")
        pairs.append((path, rel))
    pairs.sort(key=lambda item: item[1].as_posix())
    if not any(rel == PurePosixPath("main.py") for _, rel in pairs):
        raise ValueError("submission source must contain main.py at archive root")
    return tuple(pairs)

def deterministic_zip(source: str | Path, output: str | Path) -> Path:
    pairs = collect_submission_files(source)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, rel in pairs:
            info = zipfile.ZipInfo(rel.as_posix(), FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return target
