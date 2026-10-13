#!/usr/bin/env python3
"""Extract a document folder into source-linked reports and a final status index."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

try:
    from . import extract as engine
except ImportError:
    import extract as engine

SCHEMA = "uiowa.document-extraction-batch.v1"
EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class BatchError(ValueError):
    pass


def discover(root: Path) -> tuple[list[Path], dict]:
    """Keep relative paths; never recurse through directory symlinks."""
    if not root.is_dir():
        raise BatchError("input must be an existing document directory")
    paths, scan_errors, directory_links = [], [], []
    unsupported = 0

    def scan_error(exc):
        location = Path(exc.filename) if exc.filename else root
        try:
            location = location.relative_to(root)
        except ValueError:
            pass
        scan_errors.append({"path": location.as_posix(), "error": type(exc).__name__})

    for parent, directories, names in os.walk(root, followlinks=False, onerror=scan_error):
        parent = Path(parent)
        for name in sorted(directories):
            path = parent / name
            if path.is_symlink():
                directory_links.append(path.relative_to(root).as_posix())
        directories[:] = sorted(name for name in directories if not (parent / name).is_symlink())
        for name in sorted(names):
            path = parent / name
            if path.suffix.lower() in EXTENSIONS:
                paths.append(path.relative_to(root))
            else:
                unsupported += 1
    return sorted(paths, key=lambda path: path.as_posix()), {
        "recursive": True,
        "supported_extensions": sorted(EXTENSIONS),
        "unsupported_extension_files": unsupported,
        "directory_symlinks_not_traversed": sorted(directory_links),
        "scan_errors": sorted(scan_errors, key=lambda row: row["path"]),
        "file_symlinks": "Resolved by the native extractor; each report binds the bytes actually read.",
    }


def write_json(path: Path, value: dict) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def run(source: Path, destination: Path) -> dict:
    root = source.resolve()
    paths, coverage = discover(root)
    # Discover first, so a new destination inside the source cannot join this run.
    # Each report also keeps the original filename as a directory component:
    # sources a.md and a.md.json/b.md therefore cannot collide in the output tree.
    destination.mkdir(parents=True, exist_ok=False)
    documents = []
    counts = {status: 0 for status in ("ok", "partial", "unreadable", "error")}
    for relative in paths:
        path = root / relative
        try:
            result = engine.extract(path)
        except engine.ExtractionError as exc:
            result = {"schema": engine.SCHEMA, "document": {"name": path.name},
                      "status": "error", "error": str(exc), "warnings": [], "segments": []}
        target = Path("reports") / relative / "extraction.json"
        (destination / target).parent.mkdir(parents=True, exist_ok=True)
        output_sha = write_json(destination / target, result)
        counts[result["status"]] += 1
        documents.append({
            "source": relative.as_posix(),
            "source_is_symlink": path.is_symlink(),
            "source_sha256": result["document"].get("sha256"),
            "source_bytes": result["document"].get("bytes"),
            "output": target.as_posix(),
            "output_sha256": output_sha,
            "status": result["status"],
            "error": result.get("error"),
            "segments": len(result["segments"]),
            "warnings": len(result["warnings"]) + sum(len(row["warnings"]) for row in result["segments"]),
        })
    incomplete = (not documents or counts["unreadable"] or counts["error"]
                  or coverage["scan_errors"] or coverage["directory_symlinks_not_traversed"])
    result = {
        "schema": SCHEMA,
        "source_root": str(source),
        "status": "incomplete" if incomplete else "partial" if counts["partial"] else "ok",
        "reason": "NO_SUPPORTED_DOCUMENTS" if not documents else None,
        "counts": {"documents": len(documents), **counts},
        "coverage": coverage,
        "extractor": {"schema": engine.SCHEMA,
                      "source_sha256": hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()},
        "documents": documents,
    }
    # The index is the completion marker, including completed runs with errors.
    write_json(destination / "index.json", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="folder containing PDF, DOCX, TXT or Markdown evidence")
    parser.add_argument("output", type=Path, help="new output directory; existing destinations are never overwritten")
    args = parser.parse_args(argv)
    try:
        result = run(args.source, args.output)
        print(json.dumps({"status": result["status"], "counts": result["counts"],
                          "index": str(args.output / "index.json"),
                          "scan_errors": len(result["coverage"]["scan_errors"]),
                          "directory_symlinks_not_traversed": len(result["coverage"]["directory_symlinks_not_traversed"])}))
        return 2 if result["status"] == "incomplete" else 0
    except (BatchError, OSError, RuntimeError, UnicodeError) as exc:
        print(f"document-batch: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
