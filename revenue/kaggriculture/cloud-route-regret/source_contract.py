#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail closed unless the experiment is running against the named V3 closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "SOURCE.json"


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside_root(relative: str) -> Path:
    if not isinstance(relative, str):
        raise TypeError("source path must be a string")
    path = (HERE / relative).resolve(strict=True)
    try:
        path.relative_to(ROOT.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"source path escapes Kaggriculture root: {path}") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"source is not a regular file: {path}")
    return path


def checkpoints(contract: dict[str, Any] | None = None) -> tuple[tuple[object, ...], ...]:
    contract = contract or load_json(SOURCE)
    rows = contract.get("checkpoints")
    if not isinstance(rows, list) or not rows:
        raise ValueError("source contract has no checkpoints")
    parsed = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, list) or len(raw) != 4:
            raise ValueError(f"invalid checkpoint row: {raw!r}")
        turn, feature, threshold, target = raw
        if type(turn) is not int or turn < 0 or turn in seen:
            raise ValueError(f"invalid checkpoint turn: {turn!r}")
        if not isinstance(feature, str) or not feature:
            raise ValueError("checkpoint feature must be nonempty")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("checkpoint threshold must be numeric")
        if not isinstance(target, str) or not target:
            raise ValueError("checkpoint target must be nonempty")
        parsed.append((turn, feature, threshold, target))
        seen.add(turn)
    return tuple(parsed)


def verify_source_contract(path: Path = SOURCE) -> dict[str, Any]:
    contract = load_json(path)
    if contract.get("schema") != "titan-route-regret-source/v1":
        raise ValueError("unexpected source-contract schema")
    expected = contract.get("git_blobs")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("source contract has no Git blobs")
    observed = {}
    for relative, wanted in sorted(expected.items()):
        if not isinstance(wanted, str) or len(wanted) != 40:
            raise ValueError(f"invalid wanted Git blob for {relative}")
        source = _inside_root(relative)
        actual = git_blob_sha1(source)
        if actual != wanted:
            raise ValueError(
                f"source drift at {relative}: expected Git blob {wanted}, got {actual}"
            )
        observed[relative] = {
            "git_blob": actual,
            "sha256": sha256(source),
            "bytes": source.stat().st_size,
        }
    parsed = checkpoints(contract)
    return {
        "schema": "titan-route-regret-source-receipt/v1",
        "operation": contract["operation"],
        "authored_base": contract["authored_base"],
        "engine_ref": contract["engine_ref"],
        "source_contract_sha256": sha256(path),
        "git_blobs": observed,
        "checkpoints": [list(row) for row in parsed],
        "invariants": contract["invariants"],
    }


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        temporary = stream.name
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify_source_contract()
    atomic_json(args.output, receipt)
    print(json.dumps({"status": "PASS", "sources": len(receipt["git_blobs"])}))


if __name__ == "__main__":
    main()
