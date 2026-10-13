from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from revenue.travelers_agent_toolcall_evidence.fixtures import acceptance_envelopes
from revenue.travelers_agent_toolcall_evidence.gate import (
    GateError,
    build_ledger,
    canonical_bytes,
    compile_batch,
    daily_root_manifest,
    loads_strict,
    receipt_markdown,
    verify_batch,
    verify_ledger,
    verify_root,
)


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = loads_strict(line)
        if type(value) is not dict:
            raise GateError(f"{path}:{number}: JSONL row must be object")
        rows.append(value)
    return rows


def _write_json(value) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _write_jsonl(values) -> None:
    for value in values:
        sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="travelers-toolcall-evidence",
        description="Offline synthetic/nonproduction agent tool-call evidence gate.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate", help="compile envelope JSONL into receipt JSONL")
    gate.add_argument("envelopes", type=Path)

    verify = sub.add_parser("verify-batch", help="recompile and verify receipt JSONL")
    verify.add_argument("envelopes", type=Path)
    verify.add_argument("receipts", type=Path)

    markdown = sub.add_parser("markdown", help="render one receipt JSON file")
    markdown.add_argument("receipt", type=Path)

    ledger = sub.add_parser("ledger", help="build hash-chained ledger from receipt JSONL")
    ledger.add_argument("receipts", type=Path)

    verify_ledger_cmd = sub.add_parser("verify-ledger", help="verify ledger JSONL")
    verify_ledger_cmd.add_argument("ledger", type=Path)

    root = sub.add_parser("root", help="build daily Merkle root manifest")
    root.add_argument("ledger", type=Path)
    root.add_argument("day")

    verify_root_cmd = sub.add_parser("verify-root", help="verify daily root against ledger")
    verify_root_cmd.add_argument("manifest", type=Path)
    verify_root_cmd.add_argument("ledger", type=Path)

    acceptance = sub.add_parser("acceptance", help="run deterministic 240-envelope corpus")
    acceptance.add_argument("--receipts", action="store_true", help="emit all receipt JSONL")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "gate":
            _write_jsonl(compile_batch(_read_jsonl(args.envelopes)))
            return 0
        if args.command == "verify-batch":
            ok = verify_batch(_read_jsonl(args.envelopes), _read_jsonl(args.receipts))
            _write_json({"verified": ok})
            return 0 if ok else 2
        if args.command == "markdown":
            value = loads_strict(args.receipt.read_text(encoding="utf-8"))
            if type(value) is not dict:
                raise GateError("receipt file must contain one JSON object")
            sys.stdout.write(receipt_markdown(value))
            return 0
        if args.command == "ledger":
            _write_jsonl(build_ledger(_read_jsonl(args.receipts)))
            return 0
        if args.command == "verify-ledger":
            ok = verify_ledger(_read_jsonl(args.ledger))
            _write_json({"verified": ok})
            return 0 if ok else 2
        if args.command == "root":
            _write_json(daily_root_manifest(_read_jsonl(args.ledger), args.day))
            return 0
        if args.command == "verify-root":
            manifest = loads_strict(args.manifest.read_text(encoding="utf-8"))
            if type(manifest) is not dict:
                raise GateError("manifest must be JSON object")
            ok = verify_root(manifest, _read_jsonl(args.ledger))
            _write_json({"verified": ok})
            return 0 if ok else 2
        if args.command == "acceptance":
            receipts = compile_batch(acceptance_envelopes())
            if args.receipts:
                _write_jsonl(receipts)
            else:
                holds = [receipt for receipt in receipts if receipt["decision"] == "HOLD"]
                distribution: dict[str, int] = {}
                for receipt in holds:
                    for reason in receipt["reasons"]:
                        distribution[reason] = distribution.get(reason, 0) + 1
                _write_json(
                    {
                        "envelopes": len(receipts),
                        "execute_allowed": sum(
                            receipt["decision"] == "EXECUTE_ALLOWED" for receipt in receipts
                        ),
                        "hold": len(holds),
                        "hold_reason_distribution": dict(sorted(distribution.items())),
                        "receipts_sha256": __import__("hashlib").sha256(
                            canonical_bytes(receipts)
                        ).hexdigest(),
                    }
                )
            return 0
    except (GateError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
