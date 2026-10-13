# SPDX-License-Identifier: Apache-2.0
"""Offline, exact-source duplicate-observation repair. Does not touch a runtime.

Only the recovered standalone donor is accepted. The original archive/module
remain evidence; this returns a candidate for the existing EXEC-PACE-2 lane.
It does not resolve gap-normalization, missing/nonfinite-price handling, or the
unrecovered economically tested router and original tests. No activation gate.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = "637fe1810f2f937f13ce0407e15d5118e4b5db301cd3395f72654574d5189b83"
OLD = "        if step <= _last_step[0]:\n            _phist.clear()\n"
NEW = "        if step == _last_step[0]:\n            return\n        if step < _last_step[0]:\n            _phist.clear()\n"


def repair(source: bytes) -> bytes:
    """Generate a candidate from the exact donor; reject all other preimages."""
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("source SHA256 mismatch; current ABI/other donors are not accepted")
    text = source.decode("utf-8")
    if text.count(OLD) != 1:
        raise ValueError("expected one duplicate-step guard")
    text = text.replace(OLD, NEW, 1)
    text = text.replace(
        "State is per-game: observation of a step <= the last recorded step resets the\n"
        "histories (new game in a reused worker process)",
        "State is per-game: a strictly earlier step resets histories; duplicate steps\n"
        "are ignored (explicit reset() is needed for indistinguishable new episodes)",
        1,
    )
    text = text.replace(
        "    Idempotent per step; a step <= the last recorded step means a new game in\n"
        "    a reused process, so histories are reset first. Malformed input is a no-op.",
        "    Duplicate steps are ignored; a strictly earlier step resets histories.\n"
        "    Otherwise original donor behavior, including its limitations, is retained.",
        1,
    )
    output = text.encode("utf-8")
    compile(output, "r04_exec_adaptive_duplicate_candidate.py", "exec")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, help="new file only; never a production path")
    args = parser.parse_args(argv)
    try:
        candidate = repair(args.source.read_bytes())
        # Exclusive creation avoids overwriting the raw donor, another repair,
        # or existing output. All validation precedes any filesystem mutation.
        with args.output.open("xb") as stream:
            stream.write(candidate)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"repair rejected: {exc}\n")
    print(hashlib.sha256(candidate).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
