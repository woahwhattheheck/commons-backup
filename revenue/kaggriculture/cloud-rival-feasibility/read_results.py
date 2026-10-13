# SPDX-License-Identifier: MIT
"""Decode the exact retained results, checking archive and payload identities."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path


def read(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    manifest = json.loads((root / "VALIDATION.json").read_text(encoding="utf-8"))
    record = manifest["evidence"]
    encoded = b"".join((root / name).read_bytes() for name in record["parts"])
    if hashlib.sha256(encoded).hexdigest() != record["encoded_sha256"]:
        raise ValueError("Evidence archive differs from the recorded bytes")
    raw = gzip.decompress(base64.b64decode(b"".join(encoded.split()), validate=True))
    if len(raw) != record["decoded_bytes"] or hashlib.sha256(raw).hexdigest() != record["decoded_sha256"]:
        raise ValueError("Decoded evidence differs from the recorded bytes")
    return raw, json.loads(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    raw, report = read()
    if args.output:
        Path(args.output).write_bytes(raw)
    print(json.dumps({"unit_tests": report["unit_tests"],
                      "engine": {k: v for k, v in report["engine"].items() if k != "cases"},
                      "solver": {k: v for k, v in report["solver"].items() if k != "cases"}}, indent=2))
