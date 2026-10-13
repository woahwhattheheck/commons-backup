#!/usr/bin/env python3
"""Build the publication checksum manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
files = {}
for path in sorted(HERE.rglob("*")):
    unpublished = path.name in {"stage-4.json", "stage-12.json"}
    if path.is_file() and path.name != "MANIFEST.json" and not unpublished and "__pycache__" not in path.parts:
        files[str(path.relative_to(HERE))] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
manifest = {
    "schema_version": 1,
    "canonical_archive_sha256": "70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb",
    "source_json_sha256": "5f6aab68a5c286e574adc80c998733c83680ac41ef92350b19867ffe9be52ef2",
    "panel": {"seeds": list(range(9922013, 9922029)), "seats": [0, 1],
              "games": 32, "wins": 27, "ties": 4, "losses": 1},
    "files": files,
}
(HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(hashlib.sha256((HERE / "MANIFEST.json").read_bytes()).hexdigest())
