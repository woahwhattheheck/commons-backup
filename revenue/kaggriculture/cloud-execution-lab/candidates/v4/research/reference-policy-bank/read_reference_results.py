# SPDX-License-Identifier: Apache-2.0
"""Decode the exact retained acceptance report; no policy or engine execution."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

GZIP_SHA256 = "ccd858c2d58d03aedd82e3a59334fbee1b0b8debe3d78d77f50b0cdba1811606"
RAW_SHA256 = "deeb664f8bae5f8ad1dc423bae3e970a797838f28bb52a0ee84a7c8d15f3a0d2"


def read_report(root=Path(__file__).resolve().parent):
    text = "".join((Path(root) / f"apex-engine-results.json.gz.b64.{i:02d}")
                   .read_text(encoding="ascii").strip() for i in range(1, 5))
    compressed = base64.b64decode(text, validate=True)
    if hashlib.sha256(compressed).hexdigest() != GZIP_SHA256:
        raise ValueError("Compressed report hash mismatch")
    raw = gzip.decompress(compressed)
    if len(raw) != 28821 or hashlib.sha256(raw).hexdigest() != RAW_SHA256:
        raise ValueError("Raw report length/hash mismatch")
    return json.loads(raw)


if __name__ == "__main__":
    print(json.dumps(read_report(), indent=2, allow_nan=False))
