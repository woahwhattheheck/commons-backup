from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .authority import evaluate_current, verify
from .gate import AdmissionError, markdown
from .strict_json import StrictJSONError, loads


def _read(path: str):
    return loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paid-pilot-admission")
    sub = parser.add_subparsers(dest="command", required=True)

    ev = sub.add_parser("evaluate")
    ev.add_argument("packet")
    ev.add_argument("--json-out")
    ev.add_argument("--markdown-out")

    vr = sub.add_parser("verify")
    vr.add_argument("packet")
    vr.add_argument("receipt")

    args = parser.parse_args(argv)
    try:
        packet = _read(args.packet)
        if args.command == "evaluate":
            result = evaluate_current(packet)
            text = json.dumps(result.receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
            if args.json_out:
                Path(args.json_out).write_text(text, encoding="utf-8")
            else:
                sys.stdout.write(text)
            if args.markdown_out:
                Path(args.markdown_out).write_text(markdown(result.receipt), encoding="utf-8")
            return 0 if result.status == "READY_FOR_OWNER_WORK_ADMISSION" else 3
        receipt = _read(args.receipt)
        ok = verify(packet, receipt)
        sys.stdout.write(json.dumps({"verified": ok}, sort_keys=True) + "\n")
        return 0 if ok else 4
    except (AdmissionError, StrictJSONError, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
