from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SOURCE_MANIFEST.sha256"


def main() -> int:
    expected: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64 or rel in expected:
            print(f"invalid manifest line: {line!r}", file=sys.stderr)
            return 2
        expected[rel] = digest
    failed = False
    for rel, digest in sorted(expected.items()):
        path = ROOT / rel
        if not path.is_file():
            print(f"MISSING {rel}")
            failed = True
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            print(f"MISMATCH {rel} expected={digest} actual={actual}")
            failed = True
    if failed:
        return 1
    print(f"VERIFIED {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
