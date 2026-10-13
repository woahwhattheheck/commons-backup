"""Recompile an offline report from its input; hashes alone are not authority."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from components import InputError, bundle, load


def verify(input_path: Path, output_path: Path) -> list[str]:
    expected = bundle(load(input_path))
    if output_path.is_symlink() or not output_path.is_dir():
        raise InputError("bundle must be a non-symlink directory")
    actual_names = {p.name for p in output_path.iterdir()}
    if actual_names != set(expected):
        missing, extra = set(expected) - actual_names, actual_names - set(expected)
        raise InputError(f"bundle file set mismatch; missing={sorted(missing)} extra={sorted(extra)}")
    for name, data in expected.items():
        p = output_path / name
        if p.is_symlink() or not p.is_file():
            raise InputError("bundle member must be a regular file: " + name)
        # Bounded read also rejects oversized or truncated output without trusting its manifest.
        with p.open("rb") as stream:
            observed = stream.read(len(data) + 1)
        if observed != data:
            raise InputError("semantic recompile mismatch: " + name)
    return sorted(expected)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        names = verify(args.input, args.bundle)
        print(f"Verified {len(names)} exact regenerated files; no authenticity or runtime claim.")
        return 0
    except (InputError, OSError, ValueError, OverflowError) as exc:
        print("Bundle not verified: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
