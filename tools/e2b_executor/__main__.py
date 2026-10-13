from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .executor import (
    MAX_PACKET_BYTES,
    JobValidationError,
    execute_job,
    load_job_packet_bytes,
)


def _load_packet(path: str | None) -> dict:
    if path:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_PACKET_BYTES + 1)
    else:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(MAX_PACKET_BYTES + 1)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
    return load_job_packet_bytes(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a caller-supplied source archive in one E2B sandbox and emit "
            "a canonical byte-custody execution receipt. Git commit binding is separate."
        )
    )
    parser.add_argument(
        "job",
        nargs="?",
        help="JSON job packet path; omit to read stdin",
    )
    args = parser.parse_args(argv)
    try:
        receipt = execute_job(_load_packet(args.job))
    except (JobValidationError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)},
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt.get("green") else 1


if __name__ == "__main__":
    raise SystemExit(main())
