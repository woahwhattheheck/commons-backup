#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound fast clone for current native IntegratedSelected route actions.

This is an offline materializer only. It never edits a runtime in place.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

SOURCE_GIT_BLOB = "defa9b84c77fff28ae107bce291b6235bec5d26c"
CLONE_PREIMAGE = "                action = deepcopy(route[step])"
CLONE_POSTIMAGE = "                action = _clone_route_action(route[step])"
INSERT_ANCHOR = "HERE = Path(__file__).resolve().parent\n\n"
HELPERS = '''\
_ROUTE_JSON_SCALARS = frozenset((str, int, float, bool, type(None)))


def _is_fast_route_action(template):
    """True only for the exact detached JSON route-action shape."""
    if (type(template) is not dict or len(template) != 3
            or "farmer" not in template or "hands" not in template or "market" not in template):
        return False
    farmer, hands, market = template["farmer"], template["hands"], template["market"]
    if type(farmer) is not list or type(hands) is not list or type(market) is not list:
        return False
    if any(type(value) not in _ROUTE_JSON_SCALARS for value in farmer):
        return False
    for rows in (hands, market):
        for row in rows:
            if type(row) is not list:
                return False
            if any(type(value) not in _ROUTE_JSON_SCALARS for value in row):
                return False
    return True


def _clone_route_action(template):
    """Clone known route JSON cheaply; future/foreign schemas use deepcopy."""
    if not _is_fast_route_action(template):
        return deepcopy(template)
    return {
        "farmer": list(template["farmer"]),
        "hands": [list(row) for row in template["hands"]],
        "market": [list(row) for row in template["market"]],
    }

'''

class MaterializationError(RuntimeError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def materialize_bytes(source: bytes) -> bytes:
    actual = git_blob(source)
    if actual != SOURCE_GIT_BLOB:
        raise MaterializationError(f"integrated_selected blob drift: expected {SOURCE_GIT_BLOB}, got {actual}")
    text = source.decode("utf-8")
    checks = (
        (INSERT_ANCHOR, 1, "insert anchor"),
        (CLONE_PREIMAGE, 1, "clone callsite"),
        ("def _clone_route_action(", 0, "preexisting helper"),
    )
    for needle, expected, label in checks:
        found = text.count(needle)
        if found != expected:
            raise MaterializationError(f"{label}: expected {expected}, found {found}")
    candidate = text.replace(INSERT_ANCHOR, INSERT_ANCHOR + HELPERS, 1)
    candidate = candidate.replace(CLONE_PREIMAGE, CLONE_POSTIMAGE, 1)
    if candidate.count(CLONE_POSTIMAGE) != 1 or CLONE_PREIMAGE in candidate:
        raise MaterializationError("callsite replacement drift")
    compile(candidate, "<integrated-selected-fast-route-clone>", "exec")
    return candidate.encode("utf-8")


def materialize(source: Path, output: Path) -> None:
    if source.resolve(strict=False) == output.resolve(strict=False):
        raise MaterializationError("output must not alias source")
    before = source.read_bytes()
    candidate = materialize_bytes(before)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    if source.read_bytes() != before:
        output.unlink(missing_ok=True)
        raise MaterializationError("source changed during materialization")
    if output.read_bytes() != candidate:
        raise MaterializationError("output readback mismatch")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    materialize(a.source, a.output)
