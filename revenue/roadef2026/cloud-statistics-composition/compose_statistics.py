#!/usr/bin/env python3
"""Apply the landed output-preservation change to the exact frozen 3-kernel source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

FROZEN_BYTES = 37_251
FROZEN_SHA256 = "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f"
PATCH_BYTES = 3_406
PATCH_SHA256 = "232ff8744ef8cc5179165906ad4894053c5fe0482d9f61e660539d8b8e180d92"
COMPOSED_BYTES = 39_435
COMPOSED_SHA256 = "79f07a25ecd745d25a6e0a03030e709ec8f3ec54cdebe1d250baaf5ac07a802a"


def identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
    }


def require(path: Path, size: int, digest: str, label: str) -> dict[str, Any]:
    record = identity(path)
    if record["bytes"] != size or record["sha256"] != digest:
        raise ValueError(
            f"{label} identity mismatch: got {record['bytes']} bytes / {record['sha256']}"
        )
    return record


def same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False) or os.path.samefile(left, right)
    except FileNotFoundError:
        return left.resolve(strict=False) == right.resolve(strict=False)


def compose(source: Path, patch: Path, output: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    patch = patch.resolve(strict=True)
    output = output.resolve(strict=False)
    if same_file(source, output) or same_file(patch, output):
        raise ValueError("output must be a new file, not the source or patch")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    before = require(source, FROZEN_BYTES, FROZEN_SHA256, "frozen source")
    patch_record = require(patch, PATCH_BYTES, PATCH_SHA256, "composition patch")
    source_bytes = source.read_bytes()
    with tempfile.TemporaryDirectory(prefix="roadef-statistics-compose-") as name:
        root = Path(name)
        candidate = root / "main.cpp"
        candidate.write_bytes(source_bytes)
        run = subprocess.run(
            ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if run.returncode:
            raise RuntimeError(
                f"patch failed ({run.returncode}):\n{run.stdout}{run.stderr}"
            )
        composed = require(candidate, COMPOSED_BYTES, COMPOSED_SHA256, "composed source")
        if source.read_bytes() != source_bytes:
            raise RuntimeError("input source changed during composition")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(candidate.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, output)
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
    final = require(output, COMPOSED_BYTES, COMPOSED_SHA256, "written output")
    return {
        "schema": "roadef-statistics-composition-v1",
        "status": "COMPOSED",
        "source": before,
        "patch": patch_record,
        "output": final,
        "patch_stdout": run.stdout,
        "source_unchanged": True,
        "semantics": "output_publication_only_no_search_or_objective_change",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--patch",
        type=Path,
        default=Path(__file__).with_name("frozen-three-kernel-statistics.patch"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        record = compose(args.source, args.patch, args.output)
        if args.report:
            if args.report.exists() or args.report.is_symlink():
                raise FileExistsError(f"report already exists: {args.report}")
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
