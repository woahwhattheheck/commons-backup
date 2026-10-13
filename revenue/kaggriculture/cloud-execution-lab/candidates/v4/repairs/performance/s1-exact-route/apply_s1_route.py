# SPDX-License-Identifier: Apache-2.0
"""Source-only, two-function S1 route port. Never runs the legacy materializer.

This port preserves every byte outside the two audited top-level functions.
Unrelated S1 cash/funding/shape repairs are retained. An edited route function is
an explicit conflict, not permission to overwrite a peer's work. Copy the sibling
r04_s1_collection_route.py into the same package as the output before executing.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

DONOR_COMMIT = 'c8bb1b30047c2827f51931c55c1ceebdfe42979b'
DONOR_BLOB = 'f14e18e67b5c0b95943f3c9b9db649d3327d5eb4'

OLD_COUNT = '''def _reachable_count(start, targets, callbacks: int) -> int:
    pos = tuple(start)
    remaining = list(targets)
    used = 0
    count = 0
    while remaining and count < REACH:
        target = min(
            remaining,
            key=lambda p: (abs(pos[0] - p[0]) + abs(pos[1] - p[1]), p[1], p[0]),
        )
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        cost = distance + 1
        if used + cost > callbacks:
            break
        used += cost
        count += 1
        pos = target
        remaining.remove(target)
    return count
'''

OLD_COMMAND = '''def _hand_command(observation: dict, st: _Day):
    parsed = _farm(observation)
    if parsed is None or st.index is None:
        return ["PASS"]
    step, _, farm, _, _ = parsed
    if st.index >= len(farm["hands"]):
        return ["PASS"]
    pos = tuple(farm["hands"][st.index])
    targets = _targets(farm)
    if not targets:
        return ["PASS"]
    callbacks = TURNS_PER_DAY - (step % TURNS_PER_DAY)
    reachable = []
    for target in targets:
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        if distance + 1 <= callbacks:
            reachable.append((distance, target[1], target[0], target))
    if not reachable:
        return ["PASS"]
    _, _, _, target = min(reachable)
    if target == pos:
        REPORT["collections"] += 1
        return ["COLLECT_FERTILIZER"]
    return _step_toward(pos, target) or ["PASS"]
'''

NEW_COUNT = '''def _reachable_count(start, targets, callbacks: int) -> int:
    from r04_s1_collection_route import plan_collection_route
    return len(plan_collection_route(start, targets, callbacks, max_collect=REACH))
'''

NEW_COMMAND = '''def _hand_command(observation: dict, st: _Day):
    from r04_s1_collection_route import plan_collection_route
    parsed = _farm(observation)
    if parsed is None or st.index is None:
        return ["PASS"]
    step, _, farm, _, _ = parsed
    if st.index >= len(farm["hands"]):
        return ["PASS"]
    pos = tuple(farm["hands"][st.index])
    callbacks = TURNS_PER_DAY - (step % TURNS_PER_DAY)
    route = plan_collection_route(pos, _targets(farm), callbacks, max_collect=REACH)
    if not route:
        return ["PASS"]
    target = route[0]
    if target == pos:
        REPORT["collections"] += 1
        return ["COLLECT_FERTILIZER"]
    return _step_toward(pos, target) or ["PASS"]
'''

_PAIRS = {'_reachable_count': (OLD_COUNT, NEW_COUNT),
          '_hand_command': (OLD_COMMAND, NEW_COMMAND)}


def _signature(source):
    return ast.dump(ast.parse(source).body[0], include_attributes=False)


def port_source(source: str) -> str:
    """Port both matching route functions, or return already-ported source.

    No candidate code executes. AST matching tolerates formatting/comment-only
    changes inside the two functions; all other source bytes are preserved.
    Mixed old/new functions and semantic drift require explicit reconciliation.
    """
    tree = ast.parse(source)
    replacements = []
    states = []
    for name, (old, new) in _PAIRS.items():
        nodes = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == name]
        if len(nodes) != 1:
            raise ValueError(f'expected one top-level {name}, found {len(nodes)}')
        node = nodes[0]
        signature = ast.dump(node, include_attributes=False)
        if signature == _signature(old):
            states.append('old')
            replacements.append((node.lineno - 1, node.end_lineno, new))
        elif signature == _signature(new):
            states.append('new')
        else:
            raise ValueError(f'route conflict: {name} differs from audited donor and port')
    if states == ['new', 'new']:
        return source
    if states != ['old', 'old']:
        raise ValueError('partial route port: reconcile admission and execution together')
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    result = ''.join(lines)
    compile(result, '<ported-s1>', 'exec')  # Syntax check only, never execution.
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    if args.source.resolve() == args.output.resolve():
        parser.error('use a distinct output path to preserve the source donor')
    if args.output.exists():
        parser.error('output already exists; refusing to overwrite a peer artifact')
    raw = args.source.read_bytes()
    result = port_source(raw.decode('utf-8')).encode('utf-8')
    # Exclusive creation also protects against a concurrent output writer.
    with args.output.open('xb') as handle:
        handle.write(result)
    print('source_sha256=' + hashlib.sha256(raw).hexdigest())
    print('output_sha256=' + hashlib.sha256(result).hexdigest())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
