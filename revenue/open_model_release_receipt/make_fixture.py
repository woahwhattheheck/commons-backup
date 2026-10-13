#!/usr/bin/env python3
"""Create the tiny deterministic good/bad fixtures used by the release-receipt trial."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


ARTIFACTS = {
    "weights": b"FAKE-WEIGHTS-v1\n",
    "config": b'{"hidden_size":4}\n',
    "tokenizer": b'{"tokens":["open","model"]}\n',
    "loader_ref": b"loader-commit-deadbeef\n",
    "data_provenance": b"synthetic data only\n",
    "license": b"Apache-2.0 synthetic fixture\n",
    "evaluation": b"deterministic fixture; no quality claim\n",
    "sha256sums": b"fixture digest index\n",
}


def write_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, payload in ARTIFACTS.items():
        filename = f"{name}.bin"
        (root / filename).write_bytes(payload)
        rows.append({"name": name, "path": filename, "sha256": hashlib.sha256(payload).hexdigest()})
    (root / "loader.py").write_text("print('open model')\n", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({
        "release_id": "olmo-mini-release-v1",
        "artifacts": rows,
        "loader": {"command": [sys.executable, "loader.py"], "timeout_seconds": 5},
    }, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve().parent
    output = here / "generated"
    if output.exists():
        shutil.rmtree(output)
    good = output / "good" / "olmo-mini-release"
    write_fixture(good)
    bad = output / "bad" / "olmo-mini-release"
    shutil.copytree(good, bad)
    (bad / "tokenizer.bin").write_bytes(ARTIFACTS["tokenizer"] + b"X")
    (bad / "license.bin").unlink()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
