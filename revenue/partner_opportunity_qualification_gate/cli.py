from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .engine import (
    QualificationError,
    canonical_json_bytes,
    compile_qualification,
    make_receipt,
    verify_bundle,
)
from .validation import load_strict_json_text


def _load(path: pathlib.Path):
    return load_strict_json_text(path.read_text(encoding="utf-8"))


def _write_exclusive(directory: pathlib.Path, name: str, value) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / name).write_bytes(canonical_json_bytes(value))


def _compile(input_path: pathlib.Path, output_dir: pathlib.Path) -> int:
    raw = _load(input_path)
    output = compile_qualification(raw)
    receipt = make_receipt(raw, output)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "qualification.json").write_bytes(canonical_json_bytes(output))
    (output_dir / "receipt.json").write_bytes(canonical_json_bytes(receipt))
    return 0


def _verify(input_path: pathlib.Path, output_dir: pathlib.Path) -> int:
    raw = _load(input_path)
    output = _load(output_dir / "qualification.json")
    receipt = _load(output_dir / "receipt.json")
    verify_bundle(raw, output, receipt)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline partner-opportunity qualification gate")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("input", type=pathlib.Path)
        cmd.add_argument("--output-dir", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            return _compile(args.input, args.output_dir)
        return _verify(args.input, args.output_dir)
    except (QualificationError, FileExistsError, FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        print(f"qualification-gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
