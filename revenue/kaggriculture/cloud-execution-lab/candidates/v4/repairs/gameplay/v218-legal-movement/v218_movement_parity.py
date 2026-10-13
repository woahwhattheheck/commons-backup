#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inactive, component-pinned V218 movement/shed parity source repair.

No runtime imports or installs this tool. OFF is byte-identical. Explicit ON
removes exactly two terrain-ownership filters, not bounds/target/stock guards.
The engine permits both movement and shed operations on LOCKED access tiles.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

CURRENT_ROUTER_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"
HISTORICAL_FIXTURE_BLOB = "21c4f1db0298f8955b1f5ad366bd780a89cad206"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
COMPONENT_SHA256 = {'FarmView': 'ecf218d71e1f74ba544ca8dd2e02fb6b568ede4b9d5de4c532b854703d91477b', 'V218_AGENT': 'ddee83e61e2dc9bce94b3d8e63a5c3b3afaa62352572d97cb11d3a722fe6aa6d', '_v218_capacity_bound': '0f8f8d6e1fa84cbd6b5c5ce7ea27eac1aaa5df7257b56055e2061698d3affd64', '_v218_path': '0bae71a8f055c45fe945cbdf3dc7942c5423521fca8be8a181e37a343d061765', '_v218_plan': 'a0329830ce5c8c77960c0e217adf4f85730135a7d914966cac9ebca551e7cfdc', '_v218_routes': '03df62dcf5d8a07a29dea02b8f58bb0c93fbaf6d3a86a7dcfef28b5222e3cc73'}
PATH_OLD = "if not (0<=y<len(tiles) and 0<=x<len(tiles[y])) or tiles[y][x]=='LOCKED':"
PATH_NEW = "if not (0<=y<len(tiles) and 0<=x<len(tiles[y])):"
SHEDS_OLD = "sheds=[(x,y) for x,y in ((half-1,half-1),(half,half-1),(half-1,half),(half,half)) if view.tiles[y][x]!='LOCKED']"
SHEDS_NEW = "sheds=[(x,y) for x,y in ((half-1,half-1),(half,half-1),(half-1,half),(half,half))]"

class PinError(ValueError):
    pass

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

def components(source: str) -> dict[str, str]:
    found = {}
    for node in ast.parse(source).body:
        key = None
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in COMPONENT_SHA256:
            key = node.name
        if (isinstance(node, ast.FunctionDef) and node.name == "agent"
                and any(isinstance(n, ast.Name) and n.id == "_V218_PARENT" for n in ast.walk(node))):
            key = "V218_AGENT"
        if key is not None:
            if key in found:
                raise PinError(f"duplicate component: {key}")
            found[key] = ast.get_source_segment(source, node)
    if set(found) != set(COMPONENT_SHA256):
        raise PinError("incomplete V218 component set")
    return found

def verify(source: str) -> dict[str, str]:
    found = components(source)
    for name, text in found.items():
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != COMPONENT_SHA256[name]:
            raise PinError(f"component source drift: {name}")
    return found

def transform(source: str, *, enabled: bool = False) -> str:
    if type(source) is not str or type(enabled) is not bool:
        raise TypeError("source must be str; enabled must be a literal bool")
    if not enabled:
        return source
    before = verify(source)
    out = source
    for old, new in ((PATH_OLD, PATH_NEW), (SHEDS_OLD, SHEDS_NEW)):
        if out.count(old) != 1:
            raise PinError("repair anchor cardinality drift")
        out = out.replace(old, new, 1)
    after = components(out)
    for name in before:
        expected = before[name].replace(PATH_OLD, PATH_NEW).replace(SHEDS_OLD, SHEDS_NEW)
        if after[name] != expected:
            raise PinError(f"unexpected component mutation: {name}")
    return out

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--enable-movement-parity", action="store_true")
    args = parser.parse_args()
    try:
        if args.source.resolve() == args.output.resolve():
            raise PinError("source and output must differ")
        before = args.source.read_bytes()
        candidate = transform(before.decode("utf-8"), enabled=args.enable_movement_parity).encode("utf-8")
        # No overwrite of any existing candidate or source, including symlinks.
        with args.output.open("xb") as handle:
            handle.write(candidate)
        print(json.dumps({"source_blob": git_blob(before), "output_blob": git_blob(candidate),
                          "enabled": args.enable_movement_parity, "production_activation": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, SyntaxError, TypeError) as exc:
        parser.exit(2, f"movement-parity: {exc}\n")

if __name__ == "__main__":
    raise SystemExit(main())
