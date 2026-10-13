from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import CatalogError, canonical_manifest_bytes, compile_catalog, verify_catalog


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify an evidence-bound Commons expertise catalog.")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="compile catalog JSON + buyer-facing Markdown")
    compile_parser.add_argument("--input", required=True, type=Path)
    compile_parser.add_argument("--as-of", required=True)
    compile_parser.add_argument("--out-json", required=True, type=Path)
    compile_parser.add_argument("--out-md", required=True, type=Path)

    verify_parser = sub.add_parser("verify", help="verify compiled catalog and optional Markdown")
    verify_parser.add_argument("--manifest", required=True, type=Path)
    verify_parser.add_argument("--markdown", type=Path)
    verify_parser.add_argument("--expected-catalog-digest")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            raw = _load_json(args.input)
            if type(raw) is not dict or set(raw) != {"offers"}:
                raise CatalogError("input: expected exact object with offers field")
            compiled = compile_catalog(raw["offers"], as_of=args.as_of)
            args.out_json.parent.mkdir(parents=True, exist_ok=True)
            args.out_md.parent.mkdir(parents=True, exist_ok=True)
            args.out_json.write_bytes(canonical_manifest_bytes(compiled.manifest))
            args.out_md.write_text(compiled.markdown, encoding="utf-8", newline="\n")
            print(
                f"VALID=true total={compiled.manifest['counts']['total']} "
                f"review_ready={compiled.manifest['counts']['review_packet_ready']} "
                f"hold={compiled.manifest['counts']['hold']} "
                f"digest={compiled.manifest['catalog_digest']}"
            )
            return 0
        manifest = _load_json(args.manifest)
        markdown = args.markdown.read_text(encoding="utf-8") if args.markdown else None
        ok = verify_catalog(
            manifest,
            markdown,
            expected_catalog_digest=args.expected_catalog_digest,
        )
        print(f"VALID={'true' if ok else 'false'}")
        return 0 if ok else 2
    except (CatalogError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"VALID=false error={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
