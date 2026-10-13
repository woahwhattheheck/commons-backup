"""Regenerate the deterministic A308734 low-obstruction certificate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .residue_cover import certificate_dict

DEFAULT_PATH = Path(__file__).with_name("evidence") / "low_obstruction_cover_v1.json"


def render() -> bytes:
    return (json.dumps(certificate_dict(), indent=2, sort_keys=True) + "\n").encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args(argv)
    payload = render()
    if args.stdout:
        print(payload.decode(), end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        print(f"wrote {args.output}")
        print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
