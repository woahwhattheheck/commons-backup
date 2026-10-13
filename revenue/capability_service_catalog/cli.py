from __future__ import annotations

import argparse
import os
from pathlib import Path

from .catalog import compile_catalog, dumps_canonical, load_json_strict, render_csv, render_markdown, verify_package


def _write_exclusive(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile demonstrated Commons capabilities into bounded service-catalog review evidence.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--as-of", required=True, help="trusted UTC-Z instant, e.g. 2026-09-13T10:00:00Z")
    parser.add_argument("--max-evidence-age-days", type=int, default=90)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)

    doc = load_json_strict(args.input.read_text(encoding="utf-8"))
    package = compile_catalog(doc, as_of=args.as_of, max_evidence_age_days=args.max_evidence_age_days)
    if not verify_package(doc, package, as_of=args.as_of, max_evidence_age_days=args.max_evidence_age_days):
        raise SystemExit("internal verification failed")

    if args.out_dir is None:
        print(dumps_canonical(package))
    else:
        args.out_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        _write_exclusive(args.out_dir / "catalog.json", dumps_canonical(package["catalog"]) + "\n")
        _write_exclusive(args.out_dir / "catalog.csv", render_csv(package))
        _write_exclusive(args.out_dir / "catalog.md", render_markdown(package))
        _write_exclusive(args.out_dir / "receipt.json", dumps_canonical(package["receipt"]) + "\n")
        print(f"{package['catalog']['status']} {package['receipt']['receipt_sha256']}")
    return 0 if package["catalog"]["status"] != "HOLD" else 3


if __name__ == "__main__":
    raise SystemExit(main())
