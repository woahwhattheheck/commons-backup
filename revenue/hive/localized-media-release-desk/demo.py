#!/usr/bin/env python3
"""Build a fictional release package in a new, exclusively created workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from desk import ReleaseDesk, strict_json_loads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir", required=True,
        help="new, non-existing directory for demo DB and package; parent must exist",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    work = Path(args.workdir).absolute()
    created = False
    try:
        required = strict_json_loads((root / "demo" / "required.json").read_bytes())
        # Reserve a new namespace before opening SQLite or creating any artifact.
        # Never unlink an existing package or initialize a pre-existing database.
        work.mkdir(mode=0o700, parents=False, exist_ok=False)
        created = True
        db = work / "localized-release.sqlite3"
        package = work / "localized-release-demo.zip"
        desk = ReleaseDesk(db)
        desk.create_title("demo-create", "demo-title", str(root / "demo" / "source.txt"), required)
        desk.set_rights_ready("demo-rights", "demo-title", True)
        for locale, territory, filename, reviewer in (
            ("es", "US", "es-US.srt", "reviewer-es"),
            ("fr", "CA", "fr-CA.srt", "reviewer-fr"),
        ):
            result = desk.add_variant(
                f"demo-add-{locale}", "demo-title", locale, territory,
                "subtitle", str(root / "demo" / filename),
            )
            desk.approve_variant(
                f"demo-approve-{locale}", "demo-title", locale, territory,
                "subtitle", reviewer, result["revision"], result["content_sha256"],
            )
        receipt = desk.export_package("demo-title", package)
        verification = desk.verify_package("demo-title", package)
        print(json.dumps({"status": desk.status("demo-title"), "receipt": receipt,
                          "verification": verification}, indent=2, sort_keys=True))
        return 0 if verification["valid"] else 1
    except Exception as exc:
        error = {
            "error": "DEMO_NOT_COMPLETED",
            "detail": f"{type(exc).__name__}: {exc}",
            "workdir": str(work),
            "new_workdir_created": created,
            "next_action": (
                "Inspect the partial new workspace; choose a new path for a retry. No paths were deleted."
                if created else
                "Use a non-existing workspace under an existing parent. Existing directories and files are not reused."
            ),
        }
        print(json.dumps(error, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
