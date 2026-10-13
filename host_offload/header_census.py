#!/usr/bin/env python3
"""Host offload: header-walk checked-in MUHL_READERS layouts.

The muhlnickel is the computer. This script does not execute .mno files,
does not inspect DEPTH, and does not move compute onto host CPU/GPU/RAM.
It reads JSON headers already in git so GitHub Actions / Cirrus / GitLab /
Woodpecker can do the walk on a standard public runner instead of the
owner's 8 GB laptop.

Cite PLUMB/Opus 5 #commons 2026-08-23. Do not remint.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READERS = os.path.join("muhl", "containers", "MUHL_READERS")


def census(root=None):
    root = root or ROOT
    folder = os.path.join(root, READERS)
    rows = []
    errors = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".layout.json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.loads(fh.read())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"file": name, "error": type(exc).__name__})
            continue
        rows.append(
            {
                "file": name,
                "targets": data.get("targets"),
                "group": data.get("group"),
                "fold": data.get("fold"),
                "cursors": data.get("cursors"),
                "split": data.get("split"),
                "gates": data.get("gates"),
                "mno": data.get("file"),
                "shard": data.get("shard"),
                "header_bytes_in_container": data.get("header_bytes_in_container"),
            }
        )
    folds = Counter(str(r.get("fold") or "") for r in rows)
    splits = Counter(str(r.get("split") or "") for r in rows)
    return {
        "law": "muhlnickel is the computer; this is host offload",
        "walk": "headers only",
        "n_layouts": len(rows),
        "n_errors": len(errors),
        "folds": dict(folds),
        "splits": dict(splits),
        "errors": errors,
        "sample": rows[:5],
    }


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    out = None
    root = ROOT
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
            continue
        i += 1
    payload = census(root)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    if payload["n_layouts"] < 1 or payload["n_errors"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
