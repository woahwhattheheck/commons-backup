#!/usr/bin/env python3
"""Acceptance runner for the frozen 12-agent fixture."""
from __future__ import annotations

import json
from pathlib import Path

try:
    from .core import compile_registry, load_json_bytes, verify_compiled
except ImportError:
    from core import compile_registry, load_json_bytes, verify_compiled


def main() -> int:
    fixture = Path(__file__).with_name("fixture_12_agents.json")
    source = load_json_bytes(fixture.read_bytes(), "fixture")
    first = compile_registry(source)
    second = compile_registry(source)
    expected = {"READY": 5, "TOOLING_NEEDED": 3, "OWNER_DECISION": 2, "HOLD": 2}
    if first.result["counts"] != expected:
        raise SystemExit(f"counts mismatch: {first.result['counts']}")
    if first.result_bytes != second.result_bytes or first.markdown_bytes != second.markdown_bytes or first.receipt_bytes != second.receipt_bytes:
        raise SystemExit("non-deterministic compile")
    proof = verify_compiled(source, first.result_bytes, first.markdown_bytes, first.receipt_bytes)
    print(json.dumps({"acceptance": "PASS", **proof}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
