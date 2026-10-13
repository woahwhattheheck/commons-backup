from __future__ import annotations

from pathlib import Path
from typing import Any

from .codec_v2 import ClaimError, canonical
from .io_v2 import read_regular, write_exclusive


def publish(directory: Path, report: dict[str, Any], markdown: str, receipt: dict[str, Any]) -> tuple[Path, Path, Path]:
    if not directory.is_dir():
        raise ClaimError("output directory must already exist")
    paths = (directory / "payment-claim.report.json", directory / "payment-claim.md", directory / "payment-claim.receipt.json")
    if any(path.exists() for path in paths):
        raise ClaimError("output artifacts already exist")
    write_exclusive(paths[0], canonical(report) + b"\n")
    write_exclusive(paths[1], markdown.encode("utf-8"))
    write_exclusive(paths[2], canonical(receipt) + b"\n")
    return paths


def read_text(path: Path) -> str:
    try:
        return read_regular(path).decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ClaimError(f"read {path}: UTF-8 required") from exc
