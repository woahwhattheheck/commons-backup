#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage exact evaluator dependencies outside the checkout; never run them.

Recovers #12351's default-relative-path contract without changing the canonical
release builder, archive, source manifests, runtime, or evaluator semantics.
Requires a local checkout with the pinned reference sources and a new output
path whose parent exists outside the checkout. Prints a smoke command as data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

HERE = Path(__file__).resolve().parent
MAX_FILE_BYTES = 2 * 1024 * 1024
# destination, origin, source relative to origin, exact reviewed Git blob
SOURCES = (
    ("reference/evaluator/evaluate.py", "lab", "reference/evaluator/evaluate.py",
     "1fb6b655bb4ca1e1684be165a8ef513e2e6c2325"),
    ("reference/evaluator/loader.py", "lab", "reference/evaluator/loader.py",
     "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"),
    ("reference/evaluator/opponents.py", "donor", "opponents.py",
     "d18a3472cb1ea0f809ce1cd8ab7e4018aac73534"),
    ("reference/20260907-offline-agent/evaluate.py", "lab", "reference/evaluator/loader.py",
     "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"),
    ("reference/20260907-offline-agent/main.py", "lab", "../20260907-offline-agent/main.py",
     "f76bfdaa442b63c2a35de829e52e006fc55f6049"),
    ("reference/engine/kaggriculture.py", "lab", "reference/engine/kaggriculture.py",
     "3c202c7ee921da239356789e266b694635103fc4"),
    ("reference/engine/kaggriculture.json", "lab", "reference/engine/kaggriculture.json",
     "b354d06b742fe48402513792253f1a5c29366b20"),
    ("reference/engine/utils.py", "lab", "reference/engine/utils.py",
     "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87"),
    ("reference/engine/LICENSE", "lab", "reference/engine/LICENSE",
     "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"),
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def checkout_root(path: Path) -> Path:
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent
    raise ValueError("--lab must be in a checkout with a .git marker")


def read_source(path: Path, expected: str, root: Path) -> bytes:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"Source escapes its authorized root: {path}")
    # Accept ../ in the historical source path, but never a symlinked leaf.
    if path.is_symlink() or not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError(f"Source is not a regular non-symlink file: {path}")
    with resolved.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Source exceeds size limit: {path}")
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"Source pin mismatch for {path}: expected {expected}, got {actual}")
    return data


def stage(lab: Path, output: Path) -> dict:
    """Validate all inputs first, then create one new evaluator-only directory.

    No imported candidate, builder, evaluator, loader, or downloaded source is
    executed. A receipt is written last; interrupted/incomplete directories are
    not reusable. Repository source files and published artifacts are read-only.
    """
    lab = lab.expanduser().resolve(strict=True)
    if not lab.is_dir():
        raise ValueError("--lab must be a directory")
    repo = checkout_root(lab)
    donor = (HERE / "donor").resolve(strict=True)
    raw_output = output.expanduser().absolute()
    if os.path.lexists(raw_output):
        raise ValueError("Output already exists; use a fresh scratch directory")
    output = raw_output.resolve()
    if output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError("Output must be outside the source checkout, not an ancestor")
    if output.is_relative_to(HERE) or HERE.is_relative_to(output):
        raise ValueError("Output must not overlap this recovery tool")
    if not output.parent.is_dir():
        raise ValueError("Output parent must already exist")

    payloads = {}
    files = []
    for target, origin, source, expected in SOURCES:
        relative = Path(target)
        if relative.is_absolute() or ".." in relative.parts or target in payloads or target == "STAGING.json":
            raise ValueError(f"Invalid or duplicate output path: {target}")
        if origin not in ("lab", "donor"):
            raise ValueError(f"Unknown source origin: {origin}")
        base, root = (lab, repo) if origin == "lab" else (donor, donor)
        data = read_source(base / source, expected, root)
        payloads[target] = data
        files.append({"path": target, "origin": origin, "source": source,
                      "git_blob": expected, "sha256": hashlib.sha256(data).hexdigest(),
                      "bytes": len(data)})
    smoke = [sys.executable, str(output / "reference/evaluator/evaluate.py"),
             "--engine-dir", str(output / "reference/engine"),
             "--candidate", str(lab / "main.py"), "--seeds", "2027",
             "--episode-steps", "8", "--output", str(output / "smoke.json")]
    receipt = {"schema": "titan-evaluator-default-stage/v1", "source_pr": 12351,
               "source_head": "a5b0b09eba576aa0c1740f708f29aedf82bb634d",
               "stage_only": True, "executed": False, "economic_gate": False,
               "source_checkout": str(repo), "lab": str(lab),
               "files": files, "smoke_argv_not_executed": smoke}
    # mkdir is the exclusive claim. Never delete a path another writer created.
    output.mkdir(mode=0o700)
    try:
        for name, data in payloads.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                written = stream.write(data)
                if written != len(data):
                    raise OSError(f"Short write: {name}")
            if target.read_bytes() != data:
                raise OSError(f"Output readback mismatch: {name}")
        with (output / "STAGING.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except BaseException:
        # The private output directory is owned by this call, never an existing tree.
        shutil.rmtree(output)
        raise
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = stage(args.lab, args.output)
    except (OSError, ValueError) as exc:
        print(f"Evaluator staging refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
