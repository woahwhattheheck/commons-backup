#!/usr/bin/env python3
"""Slack CLI get-manifest hook. Prints Commons Service Tools JSON. No tokens."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = (
    HERE / "manifest.json",
    HERE.parent / "slack_custom_tools_manifest.json",
)


def load_manifest() -> dict:
    for path in CANDIDATES:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise SystemExit("manifest_not_object")
            return data
    raise SystemExit("no_manifest")


def main(argv: list[str] | None = None) -> int:
    del argv  # Slack CLI may pass --protocol flags; ignore them.
    payload = load_manifest()
    functions = payload.get("functions") or {}
    if "drive_tagged_service" not in functions:
        raise SystemExit("missing_drive_tagged_service")
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
