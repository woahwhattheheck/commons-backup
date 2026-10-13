# SPDX-License-Identifier: Apache-2.0
"""Source-only V4 admission for the funding-trace plant-decay stage.

The canonical V4 funding chain already composes TOWNPATH -> UNITFLOW ->
FUNDING-PERF -> CAPTRACE.  The official interpreter then decays plants after
market and town consumption, but the composed funding trace still returns from
each represented turn without that deterministic stage.

The represented funding trace also omits the official end-of-day lifecycle.
This adapter therefore admits only horizons that remain inside one exact
24-turn day, matching the current replay's existing ``t // 24`` and literal
``24`` unit-stage semantics.  Cross-EOD replay fails closed rather than
fabricating workers, inventories, plant refresh, or shed state.

This adapter applies only to the exact current full-chain funding seam.  It
adds the same-day guard plus the one plant-decay line and otherwise preserves
every byte.  It does not mutate root source, activate COMPOSITION, or publish a
runtime/archive/submission.
"""
from __future__ import annotations

import ast
import hashlib

TARGET = "_funding_trace"
EOD_GUARD = (
    "    _funding_turns_per_day = config.get('turnsPerDay', 24)\n"
    "    if type(_funding_turns_per_day) is not int or _funding_turns_per_day != 24:\n"
    "        raise ValueError('funding replay requires exact 24-turn day')\n"
    "    if now // _funding_turns_per_day != end // _funding_turns_per_day:\n"
    "        raise ValueError('funding replay cannot cross end-of-day lifecycle')\n"
)
DECAY_LINE = "        m._decay_plants(f, t)\n"

# Current CAPTRACE-accepted postimages.  Full V4 custody is narrowed further by
# requiring the TOWNPATH, UNITFLOW and CAPTRACE markers below.
CAPTRACE_AFTER = {
    "2adf10d26fd7a0d3445783e5fb64e540361eecdfd0702e1edc2b777034aaf1e4",
    "61b78c43f796c10a943b72ca84a458720219e3cc732903df27f18c6c2545906b",
    "74ef800fe10fbec67e1771644de3a3ba2b43f7fbb07e93b6597e7689858f17a9",
    "db252cac77861df9c946340affbd9ebeaf9de34d286a77e68c218d31dae3d6b0",
}
REQUIRED_MARKERS = (
    "shop_interval",          # TOWNPATH
    "center_interval",        # TOWNPATH
    "apply_projected_units",  # UNITFLOW
    "sale_receipts",          # CAPTRACE
)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _offsets(source: str) -> list[int]:
    result = [0]
    for line in source.splitlines(keepends=True):
        result.append(result[-1] + len(line))
    return result


def _target(source: str) -> tuple[ast.FunctionDef, int, int, str]:
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == TARGET
    ]
    if len(nodes) != 1:
        raise ValueError("exactly one top-level _funding_trace is required")
    node = nodes[0]
    offsets = _offsets(source)
    start, end = offsets[node.lineno - 1], offsets[node.end_lineno]
    return node, start, end, source[start:end]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_outer_funding_loop(node: ast.stmt) -> bool:
    if not isinstance(node, ast.For):
        return False
    if not isinstance(node.target, ast.Name) or node.target.id != "t":
        return False
    call = node.iter
    if not isinstance(call, ast.Call) or _name(call.func) != "range" or len(call.args) != 2:
        return False
    start, stop = call.args
    return (
        isinstance(start, ast.Name) and start.id == "now"
        and isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Add)
        and isinstance(stop.left, ast.Name) and stop.left.id == "end"
        and isinstance(stop.right, ast.Constant) and stop.right.value == 1
    )


def _preimage_details(source: str) -> tuple[ast.FunctionDef, ast.For, int]:
    fn, _start, _end, part = _target(source)
    digest = _digest(part)
    if digest not in CAPTRACE_AFTER:
        raise ValueError("funding trace is not an authenticated CAPTRACE postimage: " + digest)
    missing = [marker for marker in REQUIRED_MARKERS if marker not in part]
    if missing:
        raise ValueError("funding trace is not the full current V4 chain: " + ", ".join(missing))
    loops = [node for node in fn.body if _is_outer_funding_loop(node)]
    if len(loops) != 1:
        raise ValueError("expected exactly one outer represented-turn funding loop")
    loop = loops[0]
    index = fn.body.index(loop)
    if index + 1 >= len(fn.body) or not isinstance(fn.body[index + 1], ast.Return):
        raise ValueError("outer funding loop must flow directly to the receipt return")
    existing = [
        call for call in ast.walk(fn)
        if isinstance(call, ast.Call) and _name(call.func) == "m._decay_plants"
    ]
    if existing:
        raise ValueError("authenticated predecessor unexpectedly already contains plant decay")
    if "_funding_turns_per_day" in part:
        raise ValueError("authenticated predecessor unexpectedly already contains EOD guard")
    return fn, loop, fn.body[index + 1].lineno


def _verify_post(source: str) -> None:
    fn, start, end, part = _target(source)
    loops = [node for node in fn.body if _is_outer_funding_loop(node)]
    if len(loops) != 1:
        raise ValueError("postimage lost the unique outer funding loop")
    loop = loops[0]

    if part.count(EOD_GUARD) != 1:
        raise ValueError("postimage must contain exactly one same-day funding guard")
    offsets = _offsets(source)
    guard_start = source.find(EOD_GUARD, start, end)
    if guard_start < 0 or guard_start + len(EOD_GUARD) != offsets[loop.lineno - 1]:
        raise ValueError("same-day funding guard must immediately precede the represented-turn loop")

    calls = [
        call for call in ast.walk(fn)
        if isinstance(call, ast.Call) and _name(call.func) == "m._decay_plants"
    ]
    if len(calls) != 1:
        raise ValueError("postimage must contain exactly one funding plant-decay call")
    call = calls[0]
    if [getattr(arg, "id", None) for arg in call.args] != ["f", "t"]:
        raise ValueError("funding plant-decay call must be m._decay_plants(f, t)")
    if not loop.body or not isinstance(loop.body[-1], ast.Expr) or loop.body[-1].value is not call:
        raise ValueError("plant decay must be the final represented stage of each funding turn")
    index = fn.body.index(loop)
    if index + 1 >= len(fn.body) or not isinstance(fn.body[index + 1], ast.Return):
        raise ValueError("postimage funding loop no longer flows directly to its receipt return")
    compile(source, "v4_funding_plant_decay", "exec")


def apply(source: str) -> str:
    """Add the same-day guard and official plant-decay stage or fail closed."""
    if not isinstance(source, str):
        raise TypeError("source must be decoded UTF-8 text")

    has_guard = EOD_GUARD in source or "_funding_turns_per_day" in source
    has_decay = "m._decay_plants(f, t)" in source
    if has_guard or has_decay:
        if source.count(EOD_GUARD) != 1 or source.count(DECAY_LINE) != 1:
            raise ValueError("funding plant-decay postimage is ambiguous")
        predecessor = source.replace(EOD_GUARD, "", 1).replace(DECAY_LINE, "", 1)
        _preimage_details(predecessor)
        _verify_post(source)
        return source

    _fn, loop, return_line = _preimage_details(source)
    lines = source.splitlines(keepends=True)
    lines.insert(return_line - 1, DECAY_LINE)
    lines.insert(loop.lineno - 1, EOD_GUARD)
    result = "".join(lines)
    predecessor = result.replace(EOD_GUARD, "", 1).replace(DECAY_LINE, "", 1)
    if predecessor != source:
        raise ValueError("funding adapter changed bytes outside the guard/decay insertions")
    _verify_post(result)
    return result
