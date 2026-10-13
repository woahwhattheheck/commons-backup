"""Verify the checked-in source manifest without network access."""

from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "SOURCE_MANIFEST.sha256"


def main() -> int:
    expected: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, sep, rel = line.partition("  ")
        if sep != "  " or len(digest) != 64 or not rel:
            raise SystemExit(f"invalid manifest line: {line!r}")
        if rel in expected:
            raise SystemExit(f"duplicate manifest path: {rel}")
        expected[rel] = digest

    actual_paths = {
        str(path.relative_to(HERE)).replace("\\", "/")
        for path in HERE.rglob("*")
        if path.is_file()
        and path != MANIFEST
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    if actual_paths != set(expected):
        missing = sorted(set(expected) - actual_paths)
        extra = sorted(actual_paths - set(expected))
        raise SystemExit(f"manifest inventory mismatch: missing={missing}, extra={extra}")

    for rel, digest in expected.items():
        path = HERE / rel
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"missing/non-ordinary manifest file: {rel}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f"manifest mismatch: {rel}")
    print(f"manifest ok: {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
