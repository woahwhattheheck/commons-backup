#!/usr/bin/env python3
"""Keep the established UIOWA command names while using the versioned codec."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from . import transport as t
    from .projection_io import project_docx, project_pdf
except ImportError:
    import transport as t
    from projection_io import project_docx, project_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("json-to-csv", "csv-to-json", "json-to-xlsx", "xlsx-to-json",
                 "json-to-docx", "json-to-pdf", "embedded-to-json"):
        command = sub.add_parser(name)
        command.add_argument("src")
        command.add_argument("dst")
    for name in ("project-docx", "project-pdf"):
        sub.add_parser(name).add_argument("src")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "json-to-csv":
            t.write_csv(t.read_json(args.src), args.dst)
        elif args.cmd == "csv-to-json":
            t.write_json(t.read_csv(args.src), args.dst)
        elif args.cmd == "json-to-xlsx":
            t.write_xlsx(t.read_json(args.src), args.dst)
        elif args.cmd == "xlsx-to-json":
            t.write_json(t.read_xlsx(args.src), args.dst)
        elif args.cmd == "embedded-to-json":
            try:
                from .embedded_payload import read_embedded
            except ImportError:
                from embedded_payload import read_embedded
            t.write_json(read_embedded(args.src), args.dst)
        elif args.cmd in ("json-to-docx", "json-to-pdf"):
            try:
                from . import documents
            except ImportError:
                import documents
            writer = documents.write_docx if args.cmd.endswith("docx") else documents.write_pdf
            writer(t.read_json(args.src), args.dst)
        else:
            reader = project_docx if args.cmd == "project-docx" else project_pdf
            json.dump(reader(args.src), sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        return 0
    except (t.InterchangeError, OSError, ImportError) as exc:
        parser.exit(2, f"interchange: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
