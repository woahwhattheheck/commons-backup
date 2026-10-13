#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Preserved graph-safe clone repair for the exact historical R04 donor router.

This donor-only materializer is not wired into current production. It accepts
only the historical SOURCE_GIT_BLOB and fails closed on source drift. Current
main:candidates/v4 owns integration; do not apply a legacy R04 postimage to the
current production ABI. The fast-clone mechanism belongs to the #12643 lineage.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


SOURCE_GIT_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"
DONOR_PATCH_GIT_BLOB = "84346b65edacbfb2e46580adace4ec407707ed5e"
REPAIR_PATCH_GIT_BLOB = "5a3c99636fbacade217368226ed1f4715c5500a4"

INSERT_ANCHOR = 'ANIMALS = {"GOOSE", "COW", "SHEEP"}\n\n'
CLONE_PREIMAGE = "        action = copy.deepcopy(tape[step])"
CLONE_POSTIMAGE = "        action = _r04_clone_tape_action(tape[step])"

HELPERS = '''\
_R04_JSON_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))


def _r04_is_fast_tape_action(template):
    """Prove exact scalar rows and an unshared mutable-container graph."""
    if (type(template) is not dict or len(template) != 3
            or "farmer" not in template or "hands" not in template or "market" not in template):
        return False
    for key in template:
        if type(key) is not str:
            return False
    farmer, hands, market = template["farmer"], template["hands"], template["market"]
    if type(farmer) is not list or type(hands) is not list or type(market) is not list:
        return False
    seen = {id(farmer), id(hands), id(market)}
    if len(seen) != 3:
        return False
    for value in farmer:
        if type(value) not in _R04_JSON_SCALAR_TYPES:
            return False
    for rows in (hands, market):
        for row in rows:
            if type(row) is not list or id(row) in seen:
                return False
            seen.add(id(row))
            for value in row:
                if type(value) not in _R04_JSON_SCALAR_TYPES:
                    return False
    return True


def _r04_clone_tape_action(template):
    """Clone scalar tape rows; preserve deepcopy semantics on every fallback."""
    if not _r04_is_fast_tape_action(template):
        return copy.deepcopy(template)
    # Exact-str keys are immutable. Retain their insertion order as deepcopy does.
    action = template.copy()
    action["farmer"] = list(template["farmer"])
    action["hands"] = [list(row) for row in template["hands"]]
    action["market"] = [list(row) for row in template["market"]]
    return action

'''


class MaterializationError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def materialize_bytes(source_bytes: bytes) -> bytes:
    actual = git_blob_sha(source_bytes)
    if actual != SOURCE_GIT_BLOB:
        raise MaterializationError(
            f"router blob mismatch: expected {SOURCE_GIT_BLOB}, got {actual}"
        )
    try:
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializationError("router must be strict UTF-8") from exc

    checks = {
        "insert anchor": (INSERT_ANCHOR, 1),
        "deepcopy callsite": (CLONE_PREIMAGE, 1),
        "preexisting fast predicate": ("def _r04_is_fast_tape_action(", 0),
        "preexisting fast clone": ("def _r04_clone_tape_action(", 0),
    }
    for label, (needle, expected) in checks.items():
        found = source.count(needle)
        if found != expected:
            raise MaterializationError(f"{label}: expected {expected}, found {found}")

    candidate = source.replace(INSERT_ANCHOR, INSERT_ANCHOR + HELPERS, 1)
    candidate = candidate.replace(CLONE_PREIMAGE, CLONE_POSTIMAGE, 1)
    if candidate.count("def _r04_clone_tape_action(") != 1:
        raise MaterializationError("materialized clone helper cardinality drift")
    if candidate.count(CLONE_POSTIMAGE) != 1 or CLONE_PREIMAGE in candidate:
        raise MaterializationError("materialized Policy.act callsite drift")
    compile(candidate, "<v4-r04-fast-clone>", "exec")
    return candidate.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    if args.source.resolve(strict=False) == args.output.resolve(strict=False):
        raise MaterializationError("output must not alias source")
    before = args.source.read_bytes()
    candidate = materialize_bytes(before)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    if args.source.read_bytes() != before:
        args.output.unlink(missing_ok=True)
        raise MaterializationError("source changed during materialization")
    if args.output.read_bytes() != candidate:
        raise MaterializationError("output readback mismatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
