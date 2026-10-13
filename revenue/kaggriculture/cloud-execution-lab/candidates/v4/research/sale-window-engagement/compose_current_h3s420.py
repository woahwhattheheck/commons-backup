#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-pinned current-FrozenSelected H3/S420 candidate composer.

H3 maps the historical sale-window horizon 8 -> 3 onto the current scheduler's
baseline horizon. S420 maps the historical "stop new late reservation" rule onto
current FrozenSelected by suppressing only *new plan selection* at/after step 420.
Inherited/base SELL rows and quantities from already-planned due commitments are
still materialized by the untouched tail of FrozenSelected.transform().

The accepted preimages are exact authenticated one-tree postimages only. CAPTRACE
changes top-level funding functions, LIVEPATH changes represented_shed_event, and
SPINDLE changes scheduler MarketPath.__init__; none owns this transform block or
scheduler HORIZON. Unknown postimages fail closed and require explicit rebase.

Candidate/research composer only. It never edits production files in place.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

FROZEN_SELECTED_INPUTS = {
    "fc7baf5c179818a55037f6a61d92984d81d1a21c": "native",
    "ef090f6731c2d1ee648e2caaf3e215641b006518": "captrace",
    "4a5d3d5f4bed04acf73c7339e41fed56badf34c9": "captrace+livepath",
}
SCHEDULER_INPUTS = {
    "a483b24dd72b580d7d8811636b54d2d44f391575": "native",
    "eb289f87adebb7dc7e90046bfbec31a307cb5aaa": "captrace",
    "b29d1e9887f517506c5b3d858baa9bda5848e73f": "captrace+spindle",
}
FROZEN_SELECTED_GIT_BLOB = next(iter(FROZEN_SELECTED_INPUTS))
SCHEDULER_GIT_BLOB = next(iter(SCHEDULER_INPUTS))
BASELINE_HORIZON = 3
SUPPRESS_NEW_PLANS_AFTER = 420

_IMPORT_MARKER = (
    "from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n"
)
_BLOCK_START = "        budget=self.cash_reserve(obs,config,base,end)\n"
_BLOCK_END = "        out=copy.deepcopy(base)\n"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def authenticate_git_blobs(source_git: str, scheduler_git: str) -> tuple[str, str]:
    if source_git not in FROZEN_SELECTED_INPUTS:
        raise ValueError("frozen_selected.py source drift; explicit rebase required")
    if scheduler_git not in SCHEDULER_INPUTS:
        raise ValueError("scheduler.py source drift; explicit rebase required")
    return FROZEN_SELECTED_INPUTS[source_git], SCHEDULER_INPUTS[scheduler_git]


def _method_span(source: str, class_name: str, method_name: str) -> tuple[int, int]:
    """Return one undecorated class-method byte span in the original source."""
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    classes = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise ValueError(f"{class_name}: missing or ambiguous source boundary")
    methods = [
        node for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1 or methods[0].decorator_list:
        raise ValueError(f"{class_name}.{method_name}: missing, ambiguous or decorated")
    node = methods[0]
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def _rewrite_source(source: str) -> str:
    if source.count(_IMPORT_MARKER) != 1:
        raise ValueError("selected-sell import marker drift")

    method_start, method_end = _method_span(source, "FrozenSelected", "transform")
    method = source[method_start:method_end]
    if method.count(_BLOCK_START) != 1:
        raise ValueError("FrozenSelected transform start marker drift")
    relative_start = method.index(_BLOCK_START)
    post_start = method[relative_start:]
    if post_start.count(_BLOCK_END) != 1:
        raise ValueError("FrozenSelected transform end marker drift")
    relative_end = method.index(_BLOCK_END, relative_start)

    block = method[relative_start:relative_end]
    indented = "".join(
        ("    " + line) if line.strip() else line for line in block.splitlines(True)
    )
    guard = (
        "        self.diagnostics['h3s420']={\n"
        "            'baseline_horizon':H3S420_BASELINE_HORIZON,\n"
        "            'suppress_new_plans_after':H3S420_SUPPRESS_NEW_PLANS_AFTER,\n"
        "            'new_plan_suppressed':now>=H3S420_SUPPRESS_NEW_PLANS_AFTER}\n"
        "        if now < H3S420_SUPPRESS_NEW_PLANS_AFTER:\n"
        + indented
    )
    method = method[:relative_start] + guard + method[relative_end:]
    out = source[:method_start] + method + source[method_end:]

    constants = (
        _IMPORT_MARKER + "\n"
        + "# H3/S420 current-ABI experiment: source-pinned and default-off at composition.\n"
        + f"H3S420_BASELINE_HORIZON = {BASELINE_HORIZON}\n"
        + f"H3S420_SUPPRESS_NEW_PLANS_AFTER = {SUPPRESS_NEW_PLANS_AFTER}\n"
        + "# scheduler.HORIZON was imported above via `from scheduler import *`; shadow it\n"
        + "# only in this generated FrozenSelected module.\n"
        + "HORIZON = H3S420_BASELINE_HORIZON\n"
    )
    out = out.replace(_IMPORT_MARKER, constants, 1)
    compile(out, "<h3s420-frozen-selected>", "exec")
    return out


def compose(source: bytes, *, enabled: bool) -> bytes:
    if not enabled:
        return source
    source_git = git_blob(source)
    if source_git not in FROZEN_SELECTED_INPUTS:
        raise ValueError("frozen_selected.py source drift; explicit rebase required")
    return _rewrite_source(source.decode("utf-8")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scheduler", type=Path, required=True,
                        help="authenticated scheduler.py; read-only, never modified")
    parser.add_argument("--enable-current-h3s420", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    scheduler = args.scheduler.read_bytes()
    source_git = git_blob(source)
    scheduler_git = git_blob(scheduler)
    source_profile, scheduler_profile = authenticate_git_blobs(source_git, scheduler_git)
    result = compose(source, enabled=args.enable_current_h3s420)
    args.output.write_bytes(result)
    if args.receipt is not None:
        import json
        payload = {
            "schema": "titan.v4.h3s420-current-source/v3",
            "enabled": bool(args.enable_current_h3s420),
            "source_git_blob": source_git,
            "source_profile": source_profile,
            "scheduler_git_blob": scheduler_git,
            "scheduler_profile": scheduler_profile,
            "output_git_blob": git_blob(result),
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "output_sha256": hashlib.sha256(result).hexdigest(),
            "baseline_horizon": BASELINE_HORIZON if args.enable_current_h3s420 else 8,
            "suppress_new_plans_after": SUPPRESS_NEW_PLANS_AFTER if args.enable_current_h3s420 else None,
            "production_activation": False,
            "semantics": (
                "new plan selection suppressed at/after threshold; inherited/base SELLs and "
                "already-planned due quantities remain materialized"
            ),
        }
        args.receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
