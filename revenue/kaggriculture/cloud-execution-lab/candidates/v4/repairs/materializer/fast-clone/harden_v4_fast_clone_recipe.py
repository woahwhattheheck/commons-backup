#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Harden only HELPER in the existing a83de6b V4 fast-clone fold recipe.

No new feature, generator, branch or broad V4 root. The recipe's existing
apply-input SHA, hot-path seam and serialization contract are left untouched.
Reject source drift explicitly under both normal and optimized Python.
"""
import argparse
import ast
import hashlib
from pathlib import Path

EXPECTED_HELPER_SHA256 = '3d564710b446e3c2d91e3e340d21cff050e11d66b0cb4c94e164caa01804f4ad'

HARDENED_HELPER = '_R04_JSON_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))\n\n\ndef _r04_is_fast_tape_action(template):\n    """Accept only plain, shallow, non-aliased JSON action containers."""\n    if type(template) is not dict or len(template) != 3:\n        return False\n    if any(type(key) is not str for key in template):\n        return False\n    if not all(key in template for key in ("farmer", "hands", "market")):\n        return False\n    farmer, hands, market = template["farmer"], template["hands"], template["market"]\n    if type(farmer) is not list or type(hands) is not list or type(market) is not list:\n        return False\n    seen = {id(farmer), id(hands), id(market)}\n    if len(seen) != 3:\n        return False\n    if any(type(value) not in _R04_JSON_SCALAR_TYPES for value in farmer):\n        return False\n    for rows in (hands, market):\n        for row in rows:\n            if type(row) is not list or id(row) in seen:\n                return False\n            seen.add(id(row))\n            if any(type(value) not in _R04_JSON_SCALAR_TYPES for value in row):\n                return False\n    return True\n\n\ndef _r04_clone_tape_action(template):\n    """Match deepcopy, including fallback alias graphs and dict insertion order.\n\n    Exact builtin scalar leaves are immutable. Every accepted mutable container\n    is cloned, and the shape proof excludes internal sharing. Unknown schemas,\n    subclasses, cycles and shared rows go to deepcopy with its normal memo.\n    """\n    if not _r04_is_fast_tape_action(template):\n        return copy.deepcopy(template)\n    action = template.copy()\n    action["farmer"] = template["farmer"].copy()\n    action["hands"] = [row.copy() for row in template["hands"]]\n    action["market"] = [row.copy() for row in template["market"]]\n    return action\n'


def harden(text):
    """Replace one authenticated literal HELPER expression, nothing else."""
    tree = ast.parse(text)
    bindings = [node for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "HELPER"
                        for target in node.targets)]
    if len(bindings) != 1 or len(bindings[0].targets) != 1:
        raise ValueError("expected one simple HELPER binding")
    node = bindings[0].value
    try:
        original = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise ValueError("HELPER must be a literal string") from exc
    if type(original) is not str:
        raise ValueError("HELPER must be a literal string")
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if digest != EXPECTED_HELPER_SHA256:
        raise ValueError("HELPER source drift; do not stack/reapply this donor")
    # AST columns are UTF-8 byte offsets, not Python character offsets.
    lines = text.encode("utf-8").splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    raw = text.encode("utf-8")
    result = (raw[:start] + repr(HARDENED_HELPER).encode("utf-8") + raw[end:]).decode("utf-8")
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("output must be distinct; preserve the original donor")
    with args.input.open(encoding="utf-8", newline="") as stream:
        result = harden(stream.read())
    # Create-only avoids overwriting another session's work or a symlink target.
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        stream.write(result)
    raw = args.output.read_bytes()
    print("sha256=" + hashlib.sha256(raw).hexdigest())
    print("git_blob=" + hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())


if __name__ == "__main__":
    main()
