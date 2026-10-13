from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import LabError, canonical_json, parse_time, strict_loads, utc_now_seconds
from .compiler import compile_experiment, verify_artifacts


OUTPUT_NAMES = ("report.json", "report.csv", "report.md", "packet.json", "receipt.json")


def _read_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise LabError(f"refusing non-regular input: {path}")
    return path.read_text(encoding="utf-8")


def _read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise LabError(f"refusing non-regular artifact: {path}")
    return path.read_bytes()


def _write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)


def _compile(args: argparse.Namespace) -> int:
    value = strict_loads(_read_text(args.input))
    evaluated_at = utc_now_seconds()
    compiled = compile_experiment(value, as_of=evaluated_at)
    out_dir: Path = args.out_dir
    if out_dir.exists() or out_dir.is_symlink():
        raise LabError(f"output directory already exists: {out_dir}")
    if not out_dir.parent.exists() or not out_dir.parent.is_dir() or out_dir.parent.is_symlink():
        raise LabError("output parent must be an existing real directory")
    out_dir.mkdir(mode=0o700)
    try:
        _write_exclusive(out_dir / "report.json", compiled["json"])
        _write_exclusive(out_dir / "report.csv", compiled["csv"])
        _write_exclusive(out_dir / "report.md", compiled["markdown"])
        _write_exclusive(out_dir / "packet.json", canonical_json(compiled["packet"]))
        _write_exclusive(out_dir / "receipt.json", canonical_json(compiled["receipt"]))
    except Exception:
        # A partial directory is a visible failure receipt; never silently overwrite/reuse it.
        raise
    print(compiled["receipt"]["receipt_sha256"])
    return 0


def _verify(args: argparse.Namespace) -> int:
    value = strict_loads(_read_text(args.input))
    receipt = strict_loads(_read_text(args.receipt))
    if not isinstance(receipt, dict) or not isinstance(receipt.get("evaluated_at"), str):
        raise LabError("receipt missing evaluated_at")
    parse_time(receipt["evaluated_at"], "receipt.evaluated_at")
    packet = strict_loads(_read_text(args.packet))
    ok = verify_artifacts(
        value,
        as_of=receipt["evaluated_at"],
        packet=packet,
        receipt=receipt,
        report_json=_read_bytes(args.report_json),
        report_csv=_read_bytes(args.report_csv),
        report_markdown=_read_bytes(args.report_md),
    )
    if not ok:
        print("VERIFY_MISMATCH", file=sys.stderr)
        return 4
    print("VERIFIED")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-bound commercial experiment analytics")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="compile using trusted process UTC")
    compile_parser.add_argument("input", type=Path)
    compile_parser.add_argument("--out-dir", type=Path, required=True)
    compile_parser.set_defaults(func=_compile)

    verify_parser = sub.add_parser("verify", help="byte-verify a recorded compilation")
    verify_parser.add_argument("input", type=Path)
    verify_parser.add_argument("--packet", type=Path, required=True)
    verify_parser.add_argument("--receipt", type=Path, required=True)
    verify_parser.add_argument("--report-json", type=Path, required=True)
    verify_parser.add_argument("--report-csv", type=Path, required=True)
    verify_parser.add_argument("--report-md", type=Path, required=True)
    verify_parser.set_defaults(func=_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (LabError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
