#!/usr/bin/env python3
"""Fail closed while an internal CWPD proposal contains unresolved submission markers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = re.compile(r"\[REQUIRED:([A-Z0-9_]+)\]")
BANNED_READY = (
    "submission_ready: true",
    "ready to submit",
    "authorized to submit",
)

def inspect(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    markers = sorted(set(REQUIRED.findall(text)))
    lower = text.lower()
    conflicting_ready_claims = [phrase for phrase in BANNED_READY if phrase in lower]
    return {
        "path": str(path),
        "submission_ready": not markers and not conflicting_ready_claims,
        "unresolved_markers": markers,
        "conflicting_ready_claims": conflicting_ready_claims,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", nargs="?", default="PROPOSAL-DRAFT.md", type=Path)
    args = parser.parse_args()
    result = inspect(args.proposal)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["submission_ready"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
