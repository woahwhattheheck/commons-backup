#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose represented-market physical transition with integral-money custody.

The official engine stores farm money as ``float(int(startingMoney))`` and this
represented market seam only applies integer-valued prices/costs/credits.
Canonical balances may therefore be floats, but they remain integer-valued.
This source-only compositor rejects finite fractional floats before allowing any
represented BUY_PRODUCT / BUY_ANIMAL / HIRE transition.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

UPSTREAM_MATERIALIZER_GIT_BLOB = "647fcccb4f07adbb308e93f99aa0bc8c4a9ffd1f"

_MONEY_GUARD_OLD = (
    "if isinstance(money,bool) or not isinstance(money,(int,float)) or "
    "not math.isfinite(float(money)) or money<0:"
)
_MONEY_GUARD_NEW = (
    "if isinstance(money,bool) or not isinstance(money,(int,float)) or "
    "not math.isfinite(float(money)) or money<0 or "
    "(isinstance(money,float) and not money.is_integer()):"
)


class MaterializationError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _upstream_namespace(upstream_bytes: bytes) -> dict:
    if git_blob_sha(upstream_bytes) != UPSTREAM_MATERIALIZER_GIT_BLOB:
        raise MaterializationError("represented physical materializer Git blob mismatch")
    namespace = {"__name__": "_bound_represented_physical_materializer"}
    exec(
        compile(
            upstream_bytes.decode("utf-8"),
            "<bound-represented-physical-materializer>",
            "exec",
        ),
        namespace,
    )
    helper = namespace.get("CANDIDATE_HELPER")
    if not isinstance(helper, str):
        raise MaterializationError("represented physical helper source missing")
    if helper.count(_MONEY_GUARD_OLD) != 2:
        raise MaterializationError("represented money guard preimage drift")
    if _MONEY_GUARD_NEW in helper:
        raise MaterializationError("integral-money custody already present upstream")
    if not callable(namespace.get("materialize")):
        raise MaterializationError("represented physical materialize() missing")
    return namespace


def patched_candidate_helper(upstream_bytes: bytes) -> str:
    namespace = _upstream_namespace(upstream_bytes)
    helper = namespace["CANDIDATE_HELPER"].replace(
        _MONEY_GUARD_OLD, _MONEY_GUARD_NEW
    )
    if helper.count(_MONEY_GUARD_NEW) != 2:
        raise MaterializationError("integral-money guard cardinality drift")
    if _MONEY_GUARD_OLD in helper:
        raise MaterializationError("fractional-money predecessor guard survived")
    ast.parse(helper, filename="<represented-integral-money-helper>")
    return helper


def materialize(
    source_bytes: bytes,
    engine_bytes: bytes,
    prefix_bytes: bytes,
    upstream_bytes: bytes,
) -> bytes:
    namespace = _upstream_namespace(upstream_bytes)
    namespace["CANDIDATE_HELPER"] = patched_candidate_helper(upstream_bytes)
    candidate = namespace["materialize"](source_bytes, engine_bytes, prefix_bytes)
    text = candidate.decode("utf-8")
    if text.count(_MONEY_GUARD_NEW) != 2:
        raise MaterializationError("generated scheduler lost integral-money custody")
    if _MONEY_GUARD_OLD in text:
        raise MaterializationError("generated scheduler retained permissive money guard")
    ast.parse(text, filename="<v4-represented-integral-money-candidate>")
    compile(text, "<v4-represented-integral-money-candidate>", "exec")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--prefix-materializer", type=Path, required=True)
    parser.add_argument("--upstream-materializer", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    engine_bytes = args.engine.read_bytes()
    prefix_bytes = args.prefix_materializer.read_bytes()
    upstream_bytes = args.upstream_materializer.read_bytes()
    candidate = materialize(source_bytes, engine_bytes, prefix_bytes, upstream_bytes)

    inputs = {
        args.source.resolve(strict=False),
        args.engine.resolve(strict=False),
        args.prefix_materializer.resolve(strict=False),
        args.upstream_materializer.resolve(strict=False),
    }
    if args.output.resolve(strict=False) in inputs:
        raise MaterializationError("output must not alias a bound input")
    with args.output.open("xb") as stream:
        stream.write(candidate)

    if args.source.read_bytes() != source_bytes:
        raise MaterializationError("raw scheduler changed during materialization")
    if args.engine.read_bytes() != engine_bytes:
        raise MaterializationError("engine changed during materialization")
    if args.prefix_materializer.read_bytes() != prefix_bytes:
        raise MaterializationError("scheduler-prefix materializer changed during materialization")
    if args.upstream_materializer.read_bytes() != upstream_bytes:
        raise MaterializationError("represented physical materializer changed during materialization")
    if args.output.read_bytes() != candidate:
        raise MaterializationError("output readback mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
