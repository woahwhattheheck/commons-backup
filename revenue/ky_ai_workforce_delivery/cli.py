from __future__ import annotations

import argparse
import os
from pathlib import Path

from .io import atomic_write, paths_alias, read_plain_file
from .model import BundleError, _canonical_bytes, _report, load_json_bytes
from .validate import validate_bundle

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Kentucky AI workforce delivery evidence")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    alias_error = False
    try:
        if args.output is not None and paths_alias(args.bundle, args.output):
            alias_error = True
            raise BundleError("input and output must be distinct filesystem objects")
        raw = read_plain_file(args.bundle)
        bundle = load_json_bytes(raw)
        report = validate_bundle(bundle)
        payload = _canonical_bytes(report)
        if args.output:
            atomic_write(args.output, payload)
        else:
            os.write(1, payload)
        return 0 if report["ok"] else 2
    except BundleError as exc:
        report = _report({}, [str(exc)], [])
        payload = _canonical_bytes(report)
        if args.output and not alias_error:
            try:
                atomic_write(args.output, payload)
            except Exception:
                os.write(1, payload)
        else:
            os.write(1, payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
