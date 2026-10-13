from __future__ import annotations

import argparse
from pathlib import Path
import sys

from revenue.travelers_agent_toolcall_evidence.bundle import (
    build_evidence_bundle,
    verify_evidence_bundle,
)
from revenue.travelers_agent_toolcall_evidence.gate import (
    GateError,
    canonical_bytes,
    loads_strict,
)


def _jsonl(path: Path) -> list[dict]:
    values: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = loads_strict(line)
        if type(value) is not dict:
            raise GateError(f"{path}:{number}: JSONL row must be object")
        values.append(value)
    return values


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="travelers-toolcall-evidence-bundle",
        description=(
            "Build or verify an end-to-end synthetic tool-call evidence bundle. "
            "Verification requires semantic receipt recompilation plus ledger/root integrity."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("envelopes", type=Path)
    build.add_argument("day")

    verify = sub.add_parser("verify")
    verify.add_argument("envelopes", type=Path)
    verify.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        envelopes = _jsonl(args.envelopes)
        if args.command == "build":
            bundle = build_evidence_bundle(envelopes, args.day)
            sys.stdout.buffer.write(canonical_bytes(bundle) + b"\n")
            return 0
        if args.command == "verify":
            bundle = loads_strict(args.bundle.read_text(encoding="utf-8"))
            if type(bundle) is not dict:
                raise GateError("bundle must be JSON object")
            ok = verify_evidence_bundle(envelopes, bundle)
            sys.stdout.buffer.write(canonical_bytes({"verified": ok}) + b"\n")
            return 0 if ok else 2
    except (GateError, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
