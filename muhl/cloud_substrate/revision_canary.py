#!/usr/bin/env python3
"""Create a one-byte carrier-revision canary without interpreting MNO bytes.

The output is for measuring provider object-id and revision behavior only. It is
not an injection address, a gate operation, or a Muhlnickel workload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offset", required=True, type=int)
    parser.add_argument("--xor", type=lambda value: int(value, 0), default=1)
    args = parser.parse_args()

    original = args.source.read_bytes()
    if not 0 <= args.offset < len(original):
        raise ValueError("offset outside source bytes")
    if not 1 <= args.xor <= 255:
        raise ValueError("xor must be 1..255")

    changed = bytearray(original)
    before = changed[args.offset]
    changed[args.offset] ^= args.xor
    after = changed[args.offset]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(changed)

    print(
        json.dumps(
            {
                "purpose": "provider_revision_canary_only",
                "bytes": len(original),
                "offset": args.offset,
                "xor": args.xor,
                "byte_before": before,
                "byte_after": after,
                "source_sha256": digest(original),
                "canary_sha256": digest(changed),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
