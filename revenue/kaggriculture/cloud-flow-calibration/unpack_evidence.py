# SPDX-License-Identifier: MIT
"""Extract the retained evidence and verify every output's recorded SHA-256."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path


def unpack(source: Path, output: Path) -> list[str]:
    manifest = json.loads((source / "evidence-manifest.json").read_text(encoding="utf-8"))
    encoded = "".join("".join((source / f"evidence.part{i:02d}.b64").read_text(encoding="ascii").split())
                      for i in range(manifest["base64_parts"]))
    compressed = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(compressed).hexdigest() != manifest["gzip_sha256"]:
        raise ValueError("compressed evidence digest mismatch")
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != manifest["payload_sha256"]:
        raise ValueError("evidence payload digest mismatch")
    files = json.loads(raw)
    if set(files) != set(manifest["files"]):
        raise ValueError("evidence file set mismatch")
    for name, text in files.items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("evidence names must be basenames")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest["files"][name]:
            raise ValueError(f"evidence file digest mismatch: {name}")
    output.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (output / name).write_text(text, encoding="utf-8")
    return sorted(files)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    try:
        print(json.dumps({"verified_files": unpack(Path(__file__).resolve().parent, args.output_dir)}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(2, f"unpack error: {exc}\n")


if __name__ == "__main__":
    main()
