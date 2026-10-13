#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an engaged F3 V217 EOD-tail candidate without mutating canonical runtime.

This is deliberately a *second-stage source transformer*, not another router.
It consumes the already-landed ``rebase_current_router.py`` result and changes
exactly one literal: the current V217 planner call's final ``False`` admission
argument may become ``True`` for an explicitly requested research candidate.

The canonical donor stays untouched and F3 still ships OFF.  Full-engine
activation/economics remain a separate gate; this file only makes that gate
possible against the exact source already authenticated by the first-stage
rebase.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
REBASE_PATH = HERE / "rebase_current_router.py"
CALL_OFF = "        task=_v217_plan(view,st,step,action,pending,configuration,False)\n"
CALL_ON = "        task=_v217_plan(view,st,step,action,pending,configuration,True)\n"


class EngagedVariantError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_rebase() -> ModuleType:
    spec = importlib.util.spec_from_file_location("f3_rebase_current_router", REBASE_PATH)
    if spec is None or spec.loader is None:
        raise EngagedVariantError("cannot load landed F3 rebase")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def materialize(source_bytes: bytes, *, enabled: bool) -> bytes:
    """Return exact rebase output, optionally engaging only the live F3 call.

    ``source_bytes`` remains protected by the first-stage transform's exact Git
    blob pin.  OFF is byte-identical to that transform.  ON is accepted only if
    the hard-OFF live-call anchor occurs exactly once and no ON anchor already
    exists, so stale/double-applied source fails closed.
    """
    if type(enabled) is not bool:
        raise EngagedVariantError("enabled must be a literal bool")
    rebase = _load_rebase()
    try:
        staged = rebase.materialize(source_bytes)
    except Exception as exc:  # preserve fail-closed source pinning without laundering the cause
        raise EngagedVariantError(f"first-stage F3 rebase rejected source: {exc}") from exc
    try:
        text = staged.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngagedVariantError("rebased F3 source is not UTF-8") from exc
    if text.count(CALL_OFF) != 1 or text.count(CALL_ON) != 0:
        raise EngagedVariantError("F3 live-call admission anchor drift")
    if enabled:
        text = text.replace(CALL_OFF, CALL_ON, 1)
    try:
        ast.parse(text, filename="<f3-v217-eod-tail-engaged>")
    except SyntaxError as exc:
        raise EngagedVariantError("engaged F3 materialization is not valid Python") from exc
    return text.encode("utf-8")


def receipt(source_bytes: bytes, output_bytes: bytes, *, enabled: bool) -> dict:
    rebase = _load_rebase()
    expected = getattr(rebase, "SOURCE_GIT_BLOB", None)
    return {
        "schema": "titan-v4-f3-engaged-materialization/v1",
        "source_git_blob": git_blob_sha(source_bytes),
        "expected_source_git_blob": expected,
        "enabled": enabled,
        "output_git_blob": git_blob_sha(output_bytes),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "canonical_runtime_mutated": False,
        "production_activation": False,
        "truth_boundary": (
            "Source-only research materialization. OFF must equal the landed current-router "
            "rebase byte-for-byte; ON changes only the V217 planner admission literal. "
            "No full-engine engagement, economics, default, archive, or submission claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    before = args.source.read_bytes()
    if args.source.resolve(strict=False) == args.output.resolve(strict=False):
        raise EngagedVariantError("output must not alias source")
    output = materialize(before, enabled=args.enabled)
    args.output.write_bytes(output)
    if args.source.read_bytes() != before:
        args.output.unlink(missing_ok=True)
        raise EngagedVariantError("source mutated during materialization")
    if args.receipt is not None:
        if args.receipt.resolve(strict=False) in {
            args.source.resolve(strict=False), args.output.resolve(strict=False)
        }:
            args.output.unlink(missing_ok=True)
            raise EngagedVariantError("receipt path must not alias source or output")
        args.receipt.write_text(
            json.dumps(receipt(before, output, enabled=args.enabled), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
