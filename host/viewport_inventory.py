#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Census every tracked HTML path and report mobile viewport coverage.

The repository index, not filesystem globbing, defines the search space.  Plain
text receipts that merely use an ``.html`` suffix are reported as deliberate
non-document skips.  Malformed/unreadable document candidates make the census
incomplete instead of disappearing from the count.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
from typing import Any, Iterable, Sequence

SCHEMA = "commons.viewport-census.v1"
TAG = '<meta name="viewport" content="width=device-width, initial-scale=1">'
TAG_BYTES = TAG.encode("ascii")


class InventoryError(RuntimeError):
    """Raised when the tracked-file search space cannot be established."""


@dataclass(frozen=True)
class HtmlRecord:
    path: str
    status: str
    sha256: str | None
    bytes: int | None
    has_viewport: bool | None
    index_mode: str | None
    index_blob: str | None
    detail: str | None = None


class _ViewportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_head = False
        self.body_started = False
        self.viewport = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.body_started = True
            self.in_head = False
        elif tag == "meta" and (self.in_head or not self.body_started):
            values = {name.lower(): value for name, value in attrs}
            name = values.get("name")
            if isinstance(name, str) and name.strip().lower() == "viewport":
                self.viewport = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "head":
            self.in_head = False


def _run_git(root: Path, args: Sequence[str]) -> bytes:
    proc = subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise InventoryError(f"git {' '.join(args)} failed: {message or proc.returncode}")
    return proc.stdout


def repository_identity(root: Path) -> dict[str, str]:
    head = _run_git(root, ["rev-parse", "--verify", "HEAD"]).decode("ascii").strip()
    tree = _run_git(root, ["rev-parse", "--verify", "HEAD^{tree}"]).decode("ascii").strip()
    if len(head) != 40 or len(tree) != 40:
        raise InventoryError("unexpected Git object identity")
    return {"head": head, "tree": tree}


def _tracked_index(root: Path) -> list[tuple[str, str, str]]:
    raw = _run_git(root, ["ls-files", "-s", "-z", "--", "*.html"])
    rows: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            prefix, path_raw = record.split(b"\t", 1)
            mode_raw, blob_raw, stage_raw = prefix.split(b" ", 2)
        except ValueError as exc:
            raise InventoryError("malformed git ls-files -s record") from exc
        if stage_raw != b"0":
            raise InventoryError(f"unmerged tracked HTML path: {os.fsdecode(path_raw)}")
        path = os.fsdecode(path_raw)
        _validate_relative_path(path)
        rows.append((path, mode_raw.decode("ascii"), blob_raw.decode("ascii")))
    rows.sort(key=lambda row: row[0].encode("utf-8", "surrogateescape"))
    return rows


def _validate_relative_path(path: str) -> None:
    value = PurePosixPath(path)
    if not path or value.is_absolute() or ".." in value.parts or "\x00" in path:
        raise InventoryError(f"unsafe tracked path: {path!r}")


def _document_prefix(data: bytes) -> bytes:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.lstrip(b" \t\r\n\f")


def _has_viewport(text: str) -> bool:
    parser = _ViewportParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        # HTMLParser is deliberately forgiving, but any unexpected parser error
        # is an incomplete census rather than a false clean result.
        raise
    return parser.viewport


def classify_bytes(
    path: str,
    data: bytes,
    *,
    index_mode: str | None = None,
    index_blob: str | None = None,
) -> HtmlRecord:
    digest = hashlib.sha256(data).hexdigest()
    if not _document_prefix(data).startswith(b"<"):
        return HtmlRecord(path, "non_document", digest, len(data), None,
                          index_mode, index_blob, "first non-space byte is not '<'")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return HtmlRecord(path, "invalid_utf8", digest, len(data), None,
                          index_mode, index_blob,
                          f"invalid UTF-8 at byte {exc.start}")
    try:
        viewport = _has_viewport(text)
    except Exception as exc:  # pragma: no cover - defensive HTMLParser boundary
        return HtmlRecord(path, "parse_error", digest, len(data), None,
                          index_mode, index_blob, type(exc).__name__)
    return HtmlRecord(path, "document", digest, len(data), viewport,
                      index_mode, index_blob)


def scan_repository(root: Path) -> list[HtmlRecord]:
    root = root.resolve()
    records: list[HtmlRecord] = []
    for relative, mode, blob in _tracked_index(root):
        target = root / Path(relative)
        try:
            info = target.lstat()
        except OSError as exc:
            records.append(HtmlRecord(relative, "read_error", None, None, None,
                                      mode, blob, f"{type(exc).__name__}: {exc}"))
            continue
        if not stat.S_ISREG(info.st_mode):
            records.append(HtmlRecord(relative, "non_regular", None, None, None,
                                      mode, blob, oct(stat.S_IFMT(info.st_mode))))
            continue
        try:
            data = target.read_bytes()
        except OSError as exc:
            records.append(HtmlRecord(relative, "read_error", None, None, None,
                                      mode, blob, f"{type(exc).__name__}: {exc}"))
            continue
        records.append(classify_bytes(relative, data, index_mode=mode, index_blob=blob))
    return records


def inventory_sha256(records: Iterable[HtmlRecord]) -> str:
    rows = [asdict(record) for record in records]
    body = json.dumps(rows, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def census(root: Path, *, examples: int = 5, source_ref: str | None = None,
           include_records: bool = False) -> dict[str, Any]:
    if isinstance(examples, bool) or not isinstance(examples, int) or not 0 <= examples <= 100:
        raise ValueError("examples must be an integer in 0..100")
    root = root.resolve()
    identity = repository_identity(root)
    if source_ref is not None and source_ref != identity["head"]:
        raise InventoryError(
            f"source-ref {source_ref} differs from checked out HEAD {identity['head']}"
        )
    records = scan_repository(root)
    groups: dict[str, list[HtmlRecord]] = {}
    for record in records:
        groups.setdefault(record.status, []).append(record)
    documents = groups.get("document", [])
    missing = [record for record in documents if record.has_viewport is False]
    with_viewport = [record for record in documents if record.has_viewport is True]
    incomplete_statuses = ("invalid_utf8", "parse_error", "non_regular", "read_error")
    incomplete = [record for status in incomplete_statuses for record in groups.get(status, [])]

    def sample(rows: Iterable[HtmlRecord]) -> list[dict[str, Any]]:
        return [asdict(row) for row in list(rows)[:examples]]

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "source": identity,
        "source_ref": source_ref or identity["head"],
        "search_space": "git ls-files -s -z -- '*.html'",
        "inventory_sha256": inventory_sha256(records),
        "counts": {
            "tracked_html": len(records),
            "documents": len(documents),
            "with_viewport": len(with_viewport),
            "missing_viewport": len(missing),
            "skipped_non_document": len(groups.get("non_document", [])),
            "invalid_utf8": len(groups.get("invalid_utf8", [])),
            "parse_errors": len(groups.get("parse_error", [])),
            "non_regular": len(groups.get("non_regular", [])),
            "read_errors": len(groups.get("read_error", [])),
        },
        "examples": {
            "missing_viewport": sample(missing),
            "skipped_non_document": sample(groups.get("non_document", [])),
            "incomplete": sample(incomplete),
        },
        "complete": not incomplete,
        "mobile_viewport_complete": not incomplete and not missing,
    }
    if include_records:
        result["records"] = [asdict(record) for record in records]
    return result


def _write_json(path: Path | None, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-ref")
    parser.add_argument("--examples", type=int, default=5)
    parser.add_argument("--include-records", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = census(args.root, examples=args.examples,
                        source_ref=args.source_ref,
                        include_records=args.include_records)
        _write_json(args.output, result)
        if not result["complete"]:
            return 2
        return 1 if result["counts"]["missing_viewport"] else 0
    except (InventoryError, OSError, ValueError, TypeError) as exc:
        _write_json(args.output, {
            "schema": SCHEMA,
            "complete": False,
            "mobile_viewport_complete": False,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
