#!/usr/bin/env python3
"""Classify Commons changed paths as generated, mixed, or feature work.

This is the visibility-plan B6 primitive.  It is intentionally path-only: callers
can attach the returned receipt to drift/custody data without trusting commit
messages or authors.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from typing import Any

SCHEMA = "commons-generated-path-moves/v1"

_EXACT_RULES = {
    "feed/github.json": "board_ingest",
    "feed/head.json": "board_ingest",
    "feed/window.json": "board_ingest",
    "ground/MANUAL.md": "manual_rebuild",
}
_PREFIX_RULES = (
    ("projection/pending/", "projection"),
    ("projection/converged/", "projection"),
)


def _validate_path(path: object) -> str:
    if type(path) is not str:
        raise ValueError("changed path must be an exact string")
    if not path or path.strip() != path:
        raise ValueError("changed path must be nonempty with no edge whitespace")
    if "\x00" in path or "\\" in path:
        raise ValueError("changed path must be a repository POSIX path")
    if path.startswith("/") or path.endswith("/") or "//" in path:
        raise ValueError("changed path must be canonical and relative")
    pieces = path.split("/")
    if any(piece in {"", ".", ".."} for piece in pieces):
        raise ValueError("changed path may not contain dot segments")
    return path


def generated_kind(path: str) -> str | None:
    """Return the generated surface for one canonical repository path."""
    path = _validate_path(path)
    exact = _EXACT_RULES.get(path)
    if exact is not None:
        return exact
    for prefix, kind in _PREFIX_RULES:
        if path.startswith(prefix):
            return kind
    return None


def classify_paths(paths: Iterable[str]) -> dict[str, Any]:
    """Return a deterministic fail-closed classification receipt.

    ``generated_only`` means every changed path belongs to a known generated
    surface. ``mixed`` means generated output moved together with source or
    feature paths. ``feature`` means no known generated path moved.
    """
    if isinstance(paths, (str, bytes)):
        raise ValueError("paths must be an iterable of path strings, not one string")

    validated = [_validate_path(path) for path in paths]
    if not validated:
        raise ValueError("at least one changed path is required")
    if len(set(validated)) != len(validated):
        raise ValueError("duplicate changed paths are not allowed")

    rows = []
    for path in sorted(validated):
        kind = generated_kind(path)
        rows.append({"path": path, "generated": kind is not None, "kind": kind})

    generated = [row["path"] for row in rows if row["generated"]]
    feature = [row["path"] for row in rows if not row["generated"]]
    kinds = sorted({row["kind"] for row in rows if row["kind"] is not None})

    if generated and not feature:
        disposition = "generated_only"
    elif generated:
        disposition = "mixed"
    else:
        disposition = "feature"

    return {
        "schema": SCHEMA,
        "disposition": disposition,
        "changed_path_count": len(rows),
        "generated_path_count": len(generated),
        "feature_path_count": len(feature),
        "generated_kinds": kinds,
        "generated_paths": generated,
        "feature_paths": feature,
        "paths": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify Commons changed paths for visibility-plan B6."
    )
    parser.add_argument("paths", nargs="+", help="repository-relative changed paths")
    args = parser.parse_args(argv)
    try:
        receipt = classify_paths(args.paths)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
