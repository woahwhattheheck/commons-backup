#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Plan or apply a bounded, preimage-safe mobile viewport backfill.

Dry-run planning is the default.  ``--write`` requires an existing plan and
verifies the repository identity, the complete tracked-HTML inventory, every
preimage, and every computed postimage before staging any replacement.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Any, Mapping, Sequence

try:
    from viewport_inventory import (
        HtmlRecord,
        InventoryError,
        TAG,
        TAG_BYTES,
        census,
        classify_bytes,
        inventory_sha256,
        repository_identity,
        scan_repository,
    )
except ImportError:  # pragma: no cover - package-style import
    from .viewport_inventory import (
        HtmlRecord,
        InventoryError,
        TAG,
        TAG_BYTES,
        census,
        classify_bytes,
        inventory_sha256,
        repository_identity,
        scan_repository,
    )

PLAN_SCHEMA = "commons.viewport-backfill-plan.v1"
RECEIPT_SCHEMA = "commons.viewport-backfill-receipt.v1"


class BackfillError(RuntimeError):
    """Raised when a plan or apply boundary is unsafe."""


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_head = False
        self.body_started = False
        self.meta: list[tuple[tuple[int, int], str, list[tuple[str, str | None]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "head":
            self.in_head = True
        elif lowered == "body":
            self.body_started = True
            self.in_head = False
        elif lowered == "meta" and (self.in_head or not self.body_started):
            self.meta.append((self.getpos(), self.get_starttag_text(), attrs))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "head":
            self.in_head = False


def _char_offset(text: str, position: tuple[int, int]) -> int:
    line, column = position
    if line < 1 or column < 0:
        raise BackfillError("invalid parser position")
    starts = [0]
    for index, value in enumerate(text):
        if value == "\n":
            starts.append(index + 1)
    if line > len(starts):
        raise BackfillError("parser position exceeds document")
    return starts[line - 1] + column


def repair_bytes(data: bytes) -> tuple[bytes | None, dict[str, Any]]:
    """Return one exact safe insertion and its metadata, or an unsafe reason."""
    record = classify_bytes("<memory>", data)
    if record.status != "document":
        return None, {"reason": record.status, "detail": record.detail}
    if record.has_viewport:
        return None, {"reason": "already_has_viewport"}
    text = data.decode("utf-8")
    parser = _MetaParser()
    parser.feed(text)
    parser.close()
    anchors: list[tuple[int, int, str]] = []
    unsupported: list[str] = []
    for position, raw, attrs_list in parser.meta:
        attrs = {name.lower(): value for name, value in attrs_list}
        if "charset" not in attrs:
            continue
        value = attrs.get("charset")
        normalized = value.strip().lower() if isinstance(value, str) else ""
        absolute_start = _char_offset(text, position)
        absolute_end = absolute_start + len(raw)
        if normalized not in {"utf-8", "utf8"}:
            unsupported.append(normalized or "<missing>")
        else:
            anchors.append((absolute_start, absolute_end, raw))
    if unsupported:
        return None, {"reason": "unsupported_charset", "values": unsupported}
    if not anchors:
        return None, {"reason": "missing_utf8_charset_meta"}
    if len(anchors) != 1:
        return None, {"reason": "multiple_utf8_charset_meta", "count": len(anchors)}
    char_start, char_end, raw_anchor = anchors[0]
    byte_start = len(text[:char_start].encode("utf-8"))
    byte_end = len(text[:char_end].encode("utf-8"))
    line_start = max(data.rfind(b"\n", 0, byte_start), data.rfind(b"\r", 0, byte_start)) + 1
    indent = data[line_start:byte_start]
    if any(value not in b" \t" for value in indent):
        indent = b""
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    newline = b"\r\n" if crlf > lone_lf else b"\n"
    insertion = newline + indent + TAG_BYTES
    fixed = data[:byte_end] + insertion + data[byte_end:]
    after = classify_bytes("<memory>", fixed)
    if after.status != "document" or after.has_viewport is not True:
        raise BackfillError("computed insertion does not produce a viewport document")
    return fixed, {
        "reason": "repairable",
        "anchor": raw_anchor,
        "insertion_offset": byte_end,
        "insertion_sha256": hashlib.sha256(insertion).hexdigest(),
        "newline": "CRLF" if newline == b"\r\n" else "LF",
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _plan_digest(plan_without_digest: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(plan_without_digest)).hexdigest()


def _post_inventory(records: list[HtmlRecord], replacements: Mapping[str, bytes]) -> str:
    updated: list[HtmlRecord] = []
    for record in records:
        if record.path not in replacements:
            updated.append(record)
            continue
        new_record = classify_bytes(record.path, replacements[record.path],
                                    index_mode=record.index_mode,
                                    index_blob=record.index_blob)
        updated.append(new_record)
    return inventory_sha256(updated)


def make_plan(root: Path, *, limit: int, cursor: str = "",
              source_ref: str | None = None, examples: int = 5) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer in 1..1000")
    if not isinstance(cursor, str):
        raise TypeError("cursor must be a string")
    root = root.resolve()
    report = census(root, examples=examples, source_ref=source_ref, include_records=False)
    if not report["complete"]:
        raise BackfillError("census is incomplete; refusing to plan writes")
    records = scan_repository(root)
    if inventory_sha256(records) != report["inventory_sha256"]:
        raise BackfillError("tracked HTML inventory moved during planning")
    cursor_key = os.fsencode(cursor)
    missing = [record for record in records
               if record.status == "document" and record.has_viewport is False
               and os.fsencode(record.path) > cursor_key]
    replacements: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []
    root_resolved = root.resolve()
    for record in missing:
        path = root_resolved / Path(record.path)
        data = path.read_bytes()
        fixed, metadata = repair_bytes(data)
        if fixed is None:
            unsafe.append({"path": record.path, **metadata})
            continue
        replacements[record.path] = fixed
        rows.append({
            "path": record.path,
            "before_sha256": record.sha256,
            "after_sha256": hashlib.sha256(fixed).hexdigest(),
            "bytes_before": len(data),
            "bytes_after": len(fixed),
            **metadata,
        })
        if len(rows) == limit:
            break
    all_eligible_paths: list[str] = []
    all_replacements: dict[str, bytes] = {}
    all_unsafe: list[dict[str, Any]] = []
    for record in missing:
        data = (root_resolved / Path(record.path)).read_bytes()
        fixed, metadata = repair_bytes(data)
        if fixed is None:
            all_unsafe.append({"path": record.path, **metadata})
        else:
            all_eligible_paths.append(record.path)
            all_replacements[record.path] = fixed
    selected_paths = [row["path"] for row in rows]
    remaining = [path for path in all_eligible_paths if path not in set(selected_paths)]
    next_cursor = selected_paths[-1] if remaining and selected_paths else None
    selected_replacements = {path: replacements[path] for path in selected_paths}
    identity = repository_identity(root)
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "source": identity,
        "source_ref": source_ref or identity["head"],
        "search_space": report["search_space"],
        "tag": TAG,
        "cursor_exclusive": cursor,
        "limit": limit,
        "inventory_sha256_before": report["inventory_sha256"],
        "inventory_sha256_after": _post_inventory(records, selected_replacements),
        "tracked_html": report["counts"]["tracked_html"],
        "missing_viewport": report["counts"]["missing_viewport"],
        "eligible_after_cursor": len(all_eligible_paths),
        "selected": len(rows),
        "unsafe_after_cursor": len(all_unsafe),
        "next_cursor": next_cursor,
        "complete_for_repairable_pages": not remaining,
        "rows": rows,
        "unsafe_examples": all_unsafe[:examples],
    }
    plan["plan_sha256"] = _plan_digest(plan)
    return plan


def _load_plan(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackfillError(f"invalid plan JSON: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != PLAN_SCHEMA:
        raise BackfillError("unsupported plan schema")
    supplied = value.get("plan_sha256")
    unsigned = dict(value)
    unsigned.pop("plan_sha256", None)
    expected = _plan_digest(unsigned)
    if supplied != expected:
        raise BackfillError("plan_sha256 mismatch")
    return value


def _safe_plan_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str):
        raise BackfillError("plan path must be a string")
    value = PurePosixPath(relative)
    if not relative or value.is_absolute() or ".." in value.parts or "\x00" in relative:
        raise BackfillError(f"unsafe plan path: {relative!r}")
    target = (root / Path(relative)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise BackfillError(f"plan path escapes root: {relative!r}") from exc
    return target


def _stage_file(target: Path, data: bytes, mode: int) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.viewport-", dir=target.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, mode)
        return staged
    except BaseException:
        try:
            staged.unlink()
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            previous_umask = os.umask(0)
            os.umask(previous_umask)
            mode = 0o666 & ~previous_umask
    staged = _stage_file(path, data, mode)
    try:
        os.replace(staged, path)
        _fsync_directory(path.parent)
    finally:
        if staged.exists():
            staged.unlink()


def apply_plan(root: Path, plan_path: Path, *, receipt_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    plan = _load_plan(plan_path)
    identity = repository_identity(root)
    if plan.get("source") != identity:
        raise BackfillError(
            f"repository moved: plan={plan.get('source')} current={identity}"
        )
    rows = plan.get("rows")
    if not isinstance(rows, list) or len(rows) != plan.get("selected"):
        raise BackfillError("plan rows/count mismatch")
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if len(paths) != len(rows) or len(set(paths)) != len(paths):
        raise BackfillError("plan rows must have unique paths")
    records = scan_repository(root)
    current_inventory = inventory_sha256(records)
    before_inventory = plan.get("inventory_sha256_before")
    after_inventory = plan.get("inventory_sha256_after")
    if current_inventory == after_inventory:
        for row in rows:
            target = _safe_plan_path(root, row["path"])
            if hashlib.sha256(target.read_bytes()).hexdigest() != row.get("after_sha256"):
                raise BackfillError("post-inventory matched but a postimage digest did not")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "already_applied",
            "plan_sha256": plan["plan_sha256"],
            "source": identity,
            "inventory_sha256": current_inventory,
            "applied": 0,
            "rows": [],
            "next_cursor": plan.get("next_cursor"),
        }
        if receipt_path:
            atomic_write(receipt_path, json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
        return receipt
    if current_inventory != before_inventory:
        raise BackfillError(
            "tracked HTML inventory changed since planning; no files were written"
        )

    staged: list[tuple[Path, Path, dict[str, Any]]] = []
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise BackfillError("plan row must be an object")
            target = _safe_plan_path(root, row["path"])
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise BackfillError(f"planned path is not a regular file: {row['path']}")
            current = target.read_bytes()
            before = hashlib.sha256(current).hexdigest()
            if before != row.get("before_sha256") or len(current) != row.get("bytes_before"):
                raise BackfillError(f"preimage mismatch: {row['path']}")
            fixed, metadata = repair_bytes(current)
            if fixed is None:
                raise BackfillError(f"planned path is no longer repairable: {row['path']}: {metadata}")
            if hashlib.sha256(fixed).hexdigest() != row.get("after_sha256"):
                raise BackfillError(f"postimage mismatch: {row['path']}")
            if len(fixed) != row.get("bytes_after"):
                raise BackfillError(f"postimage length mismatch: {row['path']}")
            staged_path = _stage_file(target, fixed, stat.S_IMODE(info.st_mode))
            staged.append((target, staged_path, row))
        # All source identities and postimages are verified before the first replace.
        for target, staged_path, _ in staged:
            os.replace(staged_path, target)
            _fsync_directory(target.parent)
        staged.clear()
    finally:
        for _, staged_path, _ in staged:
            try:
                staged_path.unlink()
            except OSError:
                pass

    final_records = scan_repository(root)
    final_inventory = inventory_sha256(final_records)
    if final_inventory != after_inventory:
        raise BackfillError(
            "post-apply inventory differs from the planned postimage; inspect the partial batch"
        )
    receipt_rows = [{
        "path": row["path"],
        "before_sha256": row["before_sha256"],
        "after_sha256": row["after_sha256"],
    } for row in rows]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "applied",
        "plan_sha256": plan["plan_sha256"],
        "source": identity,
        "inventory_sha256_before": before_inventory,
        "inventory_sha256_after": final_inventory,
        "applied": len(rows),
        "rows": receipt_rows,
        "next_cursor": plan.get("next_cursor"),
    }
    if receipt_path:
        atomic_write(receipt_path, json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
    return receipt


def _emit(path: Path | None, value: dict[str, Any]) -> None:
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False).encode("utf-8") + b"\n"
    if path is None:
        sys.stdout.buffer.write(data)
    else:
        atomic_write(path, data)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-ref")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--cursor", default="")
    parser.add_argument("--examples", type=int, default=5)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path,
                        help="dry-run plan output, or apply receipt output")
    parser.add_argument("--write", action="store_true",
                        help="apply an existing --plan; default is dry-run planning")
    args = parser.parse_args(argv)
    if args.write and args.plan is not None and args.output is not None:
        # Never let the apply receipt overwrite the only saved authorization
        # document before it has been validated or can be reused for audit.
        # Report this particular CLI contract error on stderr because writing
        # it to --output would destroy the plan we are protecting.
        if args.plan.resolve() == args.output.resolve():
            error = {
                "schema": RECEIPT_SCHEMA,
                "status": "error",
                "error": {
                    "type": "ValueError",
                    "message": "--output must differ from --plan when applying",
                },
            }
            sys.stderr.write(json.dumps(error, sort_keys=True) + "\n")
            return 2
    try:
        if args.write:
            if args.plan is None:
                raise ValueError("--write requires --plan")
            result = apply_plan(args.root, args.plan, receipt_path=args.output)
            if args.output is None:
                _emit(None, result)
            return 0
        if args.plan is not None:
            raise ValueError("--plan is used only with --write")
        if args.limit is None:
            raise ValueError("dry-run planning requires an explicit --limit")
        result = make_plan(args.root, limit=args.limit, cursor=args.cursor,
                           source_ref=args.source_ref, examples=args.examples)
        _emit(args.output, result)
        return 0
    except (BackfillError, InventoryError, OSError, ValueError, TypeError) as exc:
        error = {
            "schema": RECEIPT_SCHEMA if args.write else PLAN_SCHEMA,
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        try:
            _emit(args.output, error)
        except OSError:
            sys.stderr.write(json.dumps(error, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
