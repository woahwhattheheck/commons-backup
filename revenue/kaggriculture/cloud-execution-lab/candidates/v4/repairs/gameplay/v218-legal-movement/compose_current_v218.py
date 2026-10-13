#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind the existing V218 movement-parity repair to the exact current router.

This is integration tooling, not a second V218 implementation.  Production use
requires the exact current donor blob and the exact already-landed repair tool.
OFF is whole-file byte identity.  ON delegates semantic mutation to
v218_movement_parity.py, then independently proves that exactly two source lines
changed: LOCKED transit admission and LOCKED shed-corner admission.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

CURRENT_ROUTER_PATH = "revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/overlay/r04_full_router.py"
CURRENT_ROUTER_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"
REPAIR_TOOL_BLOB = "88abf4fd6c44f3ff938cede8815aeb58085eaace"
REPAIR_TOOL_NAME = "v218_movement_parity.py"

PATH_OLD = "if not (0<=y<len(tiles) and 0<=x<len(tiles[y])) or tiles[y][x]=='LOCKED':"
PATH_NEW = "if not (0<=y<len(tiles) and 0<=x<len(tiles[y])):"
SHEDS_OLD = "sheds=[(x,y) for x,y in ((half-1,half-1),(half,half-1),(half-1,half),(half,half)) if view.tiles[y][x]!='LOCKED']"
SHEDS_NEW = "sheds=[(x,y) for x,y in ((half-1,half-1),(half,half-1),(half-1,half),(half,half))]"


class IntakeError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    if type(data) is not bytes:
        raise TypeError("git_blob requires bytes")
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _load_repair(tool_path: Path) -> ModuleType:
    raw = tool_path.read_bytes()
    actual = git_blob(raw)
    if actual != REPAIR_TOOL_BLOB:
        raise IntakeError(f"repair tool blob drift: {actual}")
    spec = importlib.util.spec_from_file_location("_v218_movement_parity_pinned", tool_path)
    if spec is None or spec.loader is None:
        raise IntakeError("cannot load repair tool")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "CURRENT_ROUTER_BLOB", None) != CURRENT_ROUTER_BLOB:
        raise IntakeError("repair tool current-router pin disagrees with intake pin")
    return module


def audit_two_line_delta(before: str, after: str) -> list[dict[str, Any]]:
    """Return the two exact changed lines or fail closed on any wider mutation."""
    if type(before) is not str or type(after) is not str:
        raise TypeError("audit inputs must be str")
    b_lines = before.splitlines(keepends=True)
    a_lines = after.splitlines(keepends=True)
    if len(b_lines) != len(a_lines):
        raise IntakeError("line count changed")
    changed: list[dict[str, Any]] = []
    for index, (old, new) in enumerate(zip(b_lines, a_lines), 1):
        if old == new:
            continue
        changed.append({"line": index, "before": old.rstrip("\r\n"), "after": new.rstrip("\r\n")})
    if len(changed) != 2:
        raise IntakeError(f"expected exactly two changed lines, got {len(changed)}")
    pairs = {(c["before"].strip(), c["after"].strip()) for c in changed}
    expected = {(PATH_OLD, PATH_NEW), (SHEDS_OLD, SHEDS_NEW)}
    if pairs != expected:
        raise IntakeError("changed-line set is not the exact V218 legality repair")
    if before.count(PATH_OLD) != 1 or before.count(SHEDS_OLD) != 1:
        raise IntakeError("current source anchor cardinality drift")
    if after.count(PATH_OLD) or after.count(SHEDS_OLD):
        raise IntakeError("old V218 legality anchor survived composition")
    if after.count(PATH_NEW) != before.count(PATH_NEW) + 1:
        raise IntakeError("LOCKED-transit replacement cardinality drift")
    if after.count(SHEDS_NEW) != before.count(SHEDS_NEW) + 1:
        raise IntakeError("shed-corner replacement cardinality drift")
    return changed


def _compose_verified(
    source_bytes: bytes,
    *,
    enabled: bool,
    expected_source_blob: str,
    repair: ModuleType,
) -> tuple[bytes, dict[str, Any]]:
    if type(source_bytes) is not bytes or type(enabled) is not bool:
        raise TypeError("source_bytes must be bytes and enabled must be bool")
    source_blob = git_blob(source_bytes)
    if source_blob != expected_source_blob:
        raise IntakeError(f"current router blob drift: {source_blob}")
    try:
        before = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntakeError("current router is not UTF-8") from exc

    if not enabled:
        out = source_bytes
        changed: list[dict[str, Any]] = []
    else:
        transformed = repair.transform(before, enabled=True)
        if type(transformed) is not str:
            raise IntakeError("repair transform returned non-str output")
        changed = audit_two_line_delta(before, transformed)
        out = transformed.encode("utf-8")
        if out == source_bytes:
            raise IntakeError("enabled repair produced byte-identical output")

    return out, {
        "schema": "titan-v4-v218-current-intake/v1",
        "source_path": CURRENT_ROUTER_PATH,
        "source_blob": source_blob,
        "output_blob": git_blob(out),
        "repair_tool_blob": REPAIR_TOOL_BLOB,
        "enabled": enabled,
        "changed_line_count": len(changed),
        "changes": changed,
        "production_activation": False,
        "legacy_materializer_used": False,
    }


def compose_current(source_bytes: bytes, *, enabled: bool, repair_tool: Path) -> tuple[bytes, dict[str, Any]]:
    repair = _load_repair(repair_tool)
    return _compose_verified(
        source_bytes,
        enabled=enabled,
        expected_source_blob=CURRENT_ROUTER_BLOB,
        repair=repair,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact current r04_full_router.py")
    parser.add_argument("output", type=Path, help="new output path; never overwritten")
    parser.add_argument("--repair-tool", type=Path, default=Path(__file__).with_name(REPAIR_TOOL_NAME))
    parser.add_argument("--enable-current-v218", action="store_true")
    parser.add_argument("--receipt", type=Path, help="optional JSON receipt path; never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.source.resolve() == args.output.resolve():
            raise IntakeError("source and output must differ")
        raw = args.source.read_bytes()
        out, receipt = compose_current(raw, enabled=args.enable_current_v218, repair_tool=args.repair_tool)
        with args.output.open("xb") as handle:
            handle.write(out)
        text = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        if args.receipt:
            with args.receipt.open("x", encoding="utf-8") as handle:
                handle.write(text)
        print(text, end="")
        return 0
    except (OSError, IntakeError, TypeError, ValueError, SyntaxError) as exc:
        parser.exit(2, f"v218-current-intake: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
