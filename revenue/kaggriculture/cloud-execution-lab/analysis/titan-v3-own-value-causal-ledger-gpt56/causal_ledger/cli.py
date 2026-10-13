# SPDX-License-Identifier: Apache-2.0
"""Atomic command-line transport for causal panel reports."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .strict import EvidenceError, load_json_strict
from .panel import analyze_panel

def _atomic_write_json(path: Path, value: Any, *, forbidden: Sequence[Path]) -> None:
    target = path.resolve(strict=False)
    for source in forbidden:
        resolved_source = source.resolve(strict=False)
        if target == resolved_source:
            raise EvidenceError("output path aliases an input path")
        try:
            if target.exists() and resolved_source.exists() and os.path.samefile(target, resolved_source):
                raise EvidenceError("output path aliases an input inode")
        except OSError as exc:
            raise EvidenceError(f"cannot verify output/input path identity: {exc}") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        panel = load_json_strict(args.input)
        report = analyze_panel(panel)
        _atomic_write_json(args.output, report, forbidden=[args.input])
    except EvidenceError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "verdict": report["verdict"],
        "input_sha256": report["input_sha256"],
        "report_sha256": report["report_sha256"],
    }, sort_keys=True))
    return 0 if report["verdict"] in ("ADMIT", "INACTIVE") else 1


