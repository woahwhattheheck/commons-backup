# SPDX-License-Identifier: Apache-2.0
"""Fail-closed V4 repair for same-turn funding candidate ranking.

The inherited helper minimizes a tuple whose second field is *positive* certified
remaining cash.  Because ``min`` selects the candidate, equal-minimum-movement
funding choices deterministically prefer *less* remaining cash.  This adapter
changes only that sign and is deliberately scoped to the existing V4
``funding-capacity-stack`` authority.

This source carrier does not activate, compose, or promote itself.  A future
materialized V4 postimage must bind its exact pre/post identities before the
central composer may execute it.
"""
from __future__ import annotations

import ast
import hashlib

FUNCTION = "fund_same_turn_acquisition"
PREIMAGE = "(moved,int(state['money']),source-target,target-destination,item),"
POSTIMAGE = "(moved,-int(state['money']),source-target,target-destination,item),"

# Exact function identities already authenticated by the existing V4 funding
# composer.  The raw current source is BEFORE; funding-replay's current composed
# function is AFTER.  Projection-state-clone edits another method, so the latter
# remains the expected function-level preimage after that component as well.
ALLOWED_PREIMAGE_FUNCTION_SHA256 = {
    "2cb97c04c171cd72e57cb2487e6500f5f3dcf10a3cb0ec2cb6c5f6410e359751",
    "117f150d54bd6bae75133bf6b415fdc0b12c1dc56327563965200d3499166167",
}


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
    """Return the one-line cash-rank repair or fail closed without partial output."""
    spans = _spans(source)
    if FUNCTION not in spans:
        raise ValueError("missing required function: " + FUNCTION)
    start, end = spans[FUNCTION]
    part = source[start:end]
    observed = hashlib.sha256(part.encode("utf-8")).hexdigest()
    if observed not in ALLOWED_PREIMAGE_FUNCTION_SHA256:
        raise ValueError("funding rank source changed; rebase explicitly: " + observed)
    if part.count(PREIMAGE) != 1 or part.count(POSTIMAGE) != 0:
        raise ValueError("funding rank anchor is not the unique predecessor expression")

    repaired_part = part.replace(PREIMAGE, POSTIMAGE, 1)
    if repaired_part.count(PREIMAGE) != 0 or repaired_part.count(POSTIMAGE) != 1:
        raise ValueError("funding rank repair did not produce the unique successor expression")
    result = source[:start] + repaired_part + source[end:]

    # One added minus sign is the complete source delta.  Parsing/compilation is
    # required before the caller can publish any materialized postimage.
    if len(result) != len(source) + 1:
        raise ValueError("funding rank repair changed unexpected byte count")
    if result.replace(POSTIMAGE, PREIMAGE, 1) != source:
        raise ValueError("funding rank repair changed source outside the objective sign")
    compile(result, "v4_same_turn_funding_cash_rank", "exec")
    return result
