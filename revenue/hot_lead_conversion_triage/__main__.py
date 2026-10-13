"""CLI for deterministic hot-lead conversion triage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .triage import TriageInputError, loads_strict, triage_document

MAX_INPUT_BYTES = 2_000_000


def _read_input(path: str) -> str:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        try:
            with Path(path).open("rb") as handle:
                data = handle.read(MAX_INPUT_BYTES + 1)
        except OSError as exc:
            raise TriageInputError("INPUT_UNAVAILABLE", "input file is unavailable") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise TriageInputError(
            "INPUT_TOO_LARGE",
            f"input exceeds {MAX_INPUT_BYTES} bytes",
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TriageInputError("INVALID_UTF8", "input must be UTF-8") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rank owner-supplied hot-lead observations without authorizing sends."
    )
    parser.add_argument("input", help="JSON input path or - for stdin")
    args = parser.parse_args(argv)

    try:
        receipt = triage_document(loads_strict(_read_input(args.input)))
    except TriageInputError as exc:
        print(
            json.dumps(
                {
                    "error": "hot_lead_triage_invalid",
                    "reason_code": exc.code,
                    "external_send_authorized": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2

    print(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
