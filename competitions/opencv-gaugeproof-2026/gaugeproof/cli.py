from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .core import Calibration
from .receipt import compile_receipt, verify_receipt
from .synthetic import render_sequence


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _demo(args: argparse.Namespace) -> int:
    calibration = Calibration(135.0, 405.0, 0.0, 100.0, "psi")
    values = [float(v) for v in args.values.split(",")]
    frames = render_sequence(values, calibration)
    receipt, annotations = compile_receipt(frames, calibration)
    payload = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    if args.output is None:
        sys.stdout.buffer.write(payload)
        return 0
    out = Path(args.output)
    if out.exists():
        raise ValueError("output directory already exists")
    out.mkdir(parents=False)
    _write_new(out / "receipt.json", payload)
    for idx, png in enumerate(annotations):
        _write_new(out / f"frame-{idx:02d}.png", png)
    return 0


def _verify(args: argparse.Namespace) -> int:
    path = Path(args.receipt)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        print("invalid receipt file", file=sys.stderr)
        return 2
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("invalid receipt JSON", file=sys.stderr)
        return 2
    ok = verify_receipt(receipt)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GaugeProof evidence-first visual inspection demo")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="generate a synthetic gauge sequence and evidence receipt")
    d.add_argument("--values", default="49.7,50.1,50.0,49.9,50.2")
    d.add_argument("--output", help="new directory for receipt and annotated frames")
    d.set_defaults(func=_demo)
    v = sub.add_parser("verify", help="verify receipt self-integrity and authority ceiling")
    v.add_argument("receipt")
    v.set_defaults(func=_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"GaugeProof refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
