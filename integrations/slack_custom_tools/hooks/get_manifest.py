#!/usr/bin/env python3
"""Print the local Slack CLI manifest.json (official get-manifest shape)."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
print((HERE / "manifest.json").read_text(encoding="utf-8"), end="")
