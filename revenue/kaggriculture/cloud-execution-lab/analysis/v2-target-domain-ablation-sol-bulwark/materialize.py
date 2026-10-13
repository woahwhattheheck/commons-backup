# SPDX-License-Identifier: Apache-2.0
"""Materialize a one-factor V2 target-domain ablation.

The frozen V2 tree is copied byte-for-byte, then exactly one scheduler
expression is replaced.  The source tree is never modified.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

EXPECTED_V2_SCHEDULER_BLOB = "7c068b7078c3d7c09bb3836590ad42b0af934cdf"
EXPECTED_V1_SCHEDULER_BLOB = "cbc502a92fe9d790cfaf763f6990d1057bc9b82d"

OLD = (
    "        targets={p:max(0,int(shed.get(p,0))) for p in PRODUCTS "
    "if shed.get(p,0)>0}\n"
)
NEW = (
    "        targets={p:min(max(0,int(shed.get(p,0))),q+self.pending.get(p,0))\n"
    "                 for p,q in {**{p:0 for p in self.pending},**baseline_q}.items()}\n"
)


class MaterializeError(ValueError):
    """The frozen source or requested materialization is not exact."""


def git_blob_sha1(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    """Return a deterministic regular-file inventory and reject link tricks."""
    if not root.is_dir():
        raise MaterializeError(f"source is not a directory: {root}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise MaterializeError(f"non-regular member is forbidden: {relative}")
        data = path.read_bytes()
        result[relative] = {
            "bytes": len(data),
            "sha256": sha256(data),
            "git_blob_sha1": git_blob_sha1(data),
        }
    if not result:
        raise MaterializeError("source inventory is empty")
    return result


def closure_sha256(items: dict[str, dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for relative, record in sorted(items.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def materialize(
    source: Path,
    output: Path,
    *,
    expected_scheduler_blob: str = EXPECTED_V2_SCHEDULER_BLOB,
) -> dict[str, Any]:
    """Copy *source* and change only the frozen V2 target-domain expression."""
    source = source.resolve()
    output = output.resolve()
    if output.exists():
        raise MaterializeError(f"output already exists: {output}")
    try:
        output.relative_to(source)
    except ValueError:
        pass
    else:
        raise MaterializeError("output may not be nested inside source")

    before = inventory(source)
    scheduler = source / "scheduler.py"
    candidate = source / "candidate.py"
    if "scheduler.py" not in before or "candidate.py" not in before:
        raise MaterializeError("source is missing scheduler.py or candidate.py")

    original = scheduler.read_bytes()
    actual_blob = git_blob_sha1(original)
    if actual_blob != expected_scheduler_blob:
        raise MaterializeError(
            "frozen V2 scheduler blob mismatch: "
            f"expected {expected_scheduler_blob}, got {actual_blob}"
        )
    old = OLD.encode("utf-8")
    new = NEW.encode("utf-8")
    if original.count(old) != 1:
        raise MaterializeError(
            f"expected exactly one V2 target expression, found {original.count(old)}"
        )
    if new in original:
        raise MaterializeError("V1 target-domain expression already exists in V2 source")

    shutil.copytree(source, output, symlinks=False)
    patched = original.replace(old, new, 1)
    try:
        compile(patched.decode("utf-8"), str(output / "scheduler.py"), "exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise MaterializeError(f"patched scheduler does not compile: {exc}") from exc
    atomic_write(output / "scheduler.py", patched)

    after = inventory(output)
    if set(before) != set(after):
        raise MaterializeError("materialized file inventory differs from frozen V2")
    changed = [
        relative
        for relative in sorted(before)
        if before[relative]["sha256"] != after[relative]["sha256"]
    ]
    if changed != ["scheduler.py"]:
        raise MaterializeError(f"one-factor boundary violated: changed={changed!r}")
    if scheduler.read_bytes() != original:
        raise MaterializeError("source scheduler changed during materialization")
    source_after = inventory(source)
    if source_after != before:
        raise MaterializeError("frozen source tree changed during materialization")

    diff = "".join(
        difflib.unified_diff(
            original.decode("utf-8").splitlines(keepends=True),
            patched.decode("utf-8").splitlines(keepends=True),
            fromfile="v2/scheduler.py",
            tofile="v2-target-domain/scheduler.py",
            n=3,
        )
    )
    return {
        "schema_version": 1,
        "operation": "titan-v2-target-domain-ablation-20260909-sol-bulwark-01",
        "source": {
            "scheduler_git_blob_sha1": actual_blob,
            "scheduler_sha256": sha256(original),
            "closure_sha256": closure_sha256(before),
            "files": len(before),
        },
        "ablation": {
            "changed_files": changed,
            "scheduler_git_blob_sha1": git_blob_sha1(patched),
            "scheduler_sha256": sha256(patched),
            "closure_sha256": closure_sha256(after),
            "old_occurrences_before": original.count(old),
            "old_occurrences_after": patched.count(old),
            "new_occurrences_before": original.count(new),
            "new_occurrences_after": patched.count(new),
            "unified_diff": diff,
        },
        "frozen_v1_scheduler_git_blob_sha1": EXPECTED_V1_SCHEDULER_BLOB,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = materialize(args.source, args.output)
    atomic_write(
        args.receipt,
        (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
            "utf-8"
        ),
    )
    print(
        json.dumps(
            {
                "source_blob": receipt["source"]["scheduler_git_blob_sha1"],
                "patched_blob": receipt["ablation"]["scheduler_git_blob_sha1"],
                "changed_files": receipt["ablation"]["changed_files"],
                "source_closure": receipt["source"]["closure_sha256"],
                "patched_closure": receipt["ablation"]["closure_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
