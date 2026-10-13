# SPDX-License-Identifier: Apache-2.0
"""Fail-closed V5 materializer for same-turn funding candidate ranking.

The live helper minimizes ``(moved, remaining_cash, ...)``.  Because candidate
selection uses ``min()``, equal-minimum-movement sale moves prefer *less*
certified remaining cash.  This adapter changes only that sign while binding the
exact current production source and exact top-level function identity.

It does not activate itself.  Callers may materialize a postimage only when the
current ``frozen_selected.py`` Git blob and function hash match the constants
below.  Any drift fails closed before output is written.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

FUNCTION = "fund_same_turn_acquisition"
SOURCE_BLOB = "f9636734692a8b02e3bcfc0feb8cdc1c24bec48f"
RAW_FUNCTION_SHA256 = "2cb97c04c171cd72e57cb2487e6500f5f3dcf10a3cb0ec2cb6c5f6410e359751"
POST_FUNCTION_SHA256 = "d5cafdaf614e423279af36adfa5011db9b8ecee81ef8c970b363b369b4569987"
PREIMAGE = "(moved,int(state['money']),source-target,target-destination,item),"
POSTIMAGE = "(moved,-int(state['money']),source-target,target-destination,item),"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _spans(source: str) -> dict[str, tuple[int, int]]:
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result: dict[str, tuple[int, int]] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in result:
                raise ValueError("duplicate top-level function: " + node.name)
            result[node.name] = (offsets[node.lineno - 1], offsets[node.end_lineno])
    return result


def function_sha256(source: str) -> str:
    spans = _spans(source)
    if FUNCTION not in spans:
        raise ValueError("missing required function: " + FUNCTION)
    start, end = spans[FUNCTION]
    return hashlib.sha256(source[start:end].encode("utf-8")).hexdigest()


def apply(source: str) -> str:
    """Return the one-byte cash-rank repair or fail closed."""
    spans = _spans(source)
    if FUNCTION not in spans:
        raise ValueError("missing required function: " + FUNCTION)
    start, end = spans[FUNCTION]
    part = source[start:end]
    observed = hashlib.sha256(part.encode("utf-8")).hexdigest()
    if observed != RAW_FUNCTION_SHA256:
        raise ValueError("funding rank source changed; rebase explicitly: " + observed)
    if part.count(PREIMAGE) != 1 or part.count(POSTIMAGE) != 0:
        raise ValueError("funding rank anchor is not the unique predecessor expression")

    repaired_part = part.replace(PREIMAGE, POSTIMAGE, 1)
    if repaired_part.count(PREIMAGE) != 0 or repaired_part.count(POSTIMAGE) != 1:
        raise ValueError("funding rank repair did not produce the unique successor expression")
    repaired_hash = hashlib.sha256(repaired_part.encode("utf-8")).hexdigest()
    if repaired_hash != POST_FUNCTION_SHA256:
        raise ValueError("unexpected repaired function identity: " + repaired_hash)

    result = source[:start] + repaired_part + source[end:]
    if len(result) != len(source) + 1:
        raise ValueError("funding rank repair changed unexpected byte count")
    if result.replace(POSTIMAGE, PREIMAGE, 1) != source:
        raise ValueError("funding rank repair changed source outside the objective sign")
    compile(result, "v5_same_turn_funding_cash_rank", "exec")
    return result


def materialize(source_path: Path, output_path: Path) -> dict[str, object]:
    raw = source_path.read_bytes()
    observed_blob = git_blob(raw)
    if observed_blob != SOURCE_BLOB:
        raise ValueError("current frozen_selected.py blob drifted: " + observed_blob)
    source = raw.decode("utf-8")
    result = apply(source)
    output_path.write_text(result, encoding="utf-8", newline="")
    written = output_path.read_bytes()
    receipt = {
        "schema": "titan-v5-funding-cash-rank-materialization/v1",
        "source_blob": observed_blob,
        "raw_function_sha256": RAW_FUNCTION_SHA256,
        "post_function_sha256": function_sha256(written.decode("utf-8")),
        "source_bytes": len(raw),
        "postimage_bytes": len(written),
        "delta_bytes": len(written) - len(raw),
    }
    if receipt["post_function_sha256"] != POST_FUNCTION_SHA256:
        raise ValueError("written postimage identity mismatch")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
