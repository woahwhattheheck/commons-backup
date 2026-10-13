from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .core import KitError, compile_kit, render_private_json, render_public_json, render_public_markdown, strict_json_loads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a proof-to-paid-work record without granting outbound/payment authority.")
    parser.add_argument("input", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--private-json", action="store_true")
    group.add_argument("--public-json", action="store_true")
    args = parser.parse_args(argv)
    try:
        compiled = compile_kit(strict_json_loads(args.input.read_text(encoding="utf-8")))
        if args.private_json:
            sys.stdout.write(render_private_json(compiled))
        elif args.public_json:
            sys.stdout.write(render_public_json(compiled))
        else:
            sys.stdout.write(render_public_markdown(compiled))
        return 0
    except (OSError, KitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
