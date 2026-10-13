# SPDX-License-Identifier: Apache-2.0
"""Read a mapped CSV export without modifying its source or destination."""
from __future__ import annotations

import csv
import errno
import hashlib
import io
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from attachment_intake import AttachmentError, read_attachment


class MigrationError(ValueError):
    """An actionable source, plan, or destination inconsistency."""


KINDS = ("customers", "tasks", "attachments")
FIELDS = {
    "customers": {"external_id", "name", "email", "phone"},
    "tasks": {"external_id", "customer_external_id", "title", "status", "due_date"},
    "attachments": {"external_id", "customer_external_id", "path", "name"},
}
REQUIRED = {
    "customers": {"external_id", "name"},
    "tasks": {"external_id", "customer_external_id", "title"},
    "attachments": {"external_id", "customer_external_id", "path"},
}
STATUSES = {"open", "in_progress", "done", "cancelled"}
MAX_FILE_BYTES = 64 * 1024 * 1024


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_id(kind: str, namespace: str, external_id: str) -> str:
    return kind[0] + "_" + digest(canonical([kind, namespace, external_id]).encode())[:32]


def read_source(root: Path, relative: str) -> bytes:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise MigrationError(f"Source path must be relative to the export folder: {relative!r}")
    root = root.resolve()
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise MigrationError(f"Use an ordinary source file, not a symbolic link: {relative}")
    try:
        current.resolve().relative_to(root)
        if not current.is_file() or current.stat().st_size > MAX_FILE_BYTES:
            raise MigrationError(f"Source file missing or exceeds 64 MiB: {relative}")
        with current.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise MigrationError(f"Source file exceeds 64 MiB: {relative}")
        return data
    except (OSError, ValueError) as exc:
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"Cannot read source {relative}: {exc}") from exc


def _attachment_error_detail(root: Path, relative: str, exc: AttachmentError) -> str:
    """Translate known safe-reader rejections into stable operator guidance."""
    detail = str(exc)
    if any(marker in detail for marker in (
        "must be nonempty text",
        "use a relative POSIX path",
        "empty, dot or parent component",
    )):
        return "attachment path must be an ordinary relative path"
    cause = exc.__cause__
    if isinstance(cause, OSError) and cause.errno == errno.ELOOP:
        return "symbolic link is not allowed"
    try:
        current = Path(root)
        if current.is_symlink():
            return "symbolic link is not allowed"
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                return "symbolic link is not allowed"
    except OSError:
        pass
    return detail


def read_attachment_source(root: Path, relative: str) -> bytes:
    """Use the bounded descriptor reader when its required APIs are available."""
    descriptor_reads = (
        all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    )
    if not descriptor_reads:
        return read_source(root, relative)
    try:
        return read_attachment(root, relative, max_bytes=MAX_FILE_BYTES)["data"]
    except AttachmentError as exc:
        # A rejected descriptor read must not retry through the portable reader.
        detail = _attachment_error_detail(root, relative, exc)
        raise MigrationError(f"Cannot read attachment {relative}: {detail}") from exc


def validate_data(kind: str, data: dict[str, Any]) -> None:
    if kind == "customers":
        if not data.get("name", "").strip():
            raise MigrationError("Customer name is required")
    elif kind == "tasks":
        if not data.get("title", "").strip():
            raise MigrationError("Task title is required")
        if data.get("status") not in STATUSES:
            raise MigrationError("Task status must be open, in_progress, done, or cancelled")
        due = data.get("due_date", "")
        if due:
            try:
                if date.fromisoformat(due).isoformat() != due:
                    raise ValueError("not YYYY-MM-DD")
            except (TypeError, ValueError) as exc:
                raise MigrationError(f"Use an exact YYYY-MM-DD due date: {due!r}") from exc


def collect(root: Path, mapping_path: str) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}

    def read(relative: str, *, attachment: bool = False) -> bytes:
        raw = read_attachment_source(root, relative) if attachment else read_source(root, relative)
        metadata = {"sha256": digest(raw), "bytes": len(raw)}
        if relative in files and files[relative] != metadata:
            raise MigrationError(f"Source changed during intake: {relative}")
        files[relative] = metadata
        return raw

    try:
        mapping = json.loads(read(mapping_path))
    except (ValueError, UnicodeError) as exc:
        raise MigrationError(f"Mapping is not readable JSON: {exc}") from exc
    if not isinstance(mapping, dict):
        raise MigrationError("Mapping must be a JSON object")
    namespace = mapping.get("namespace", "")
    if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", namespace):
        raise MigrationError("Choose a stable namespace using letters, numbers, dot, dash or underscore")
    duplicate_rule = mapping.get("duplicate_email", "error")
    if duplicate_rule not in {"error", "keep_separate"}:
        raise MigrationError("duplicate_email must be error or keep_separate; automatic merging is not performed")
    records = []
    identities = set()
    for kind in KINDS:
        spec = mapping.get(kind)
        if spec is None:
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("fields"), dict):
            raise MigrationError(f"{kind}: provide file and fields mapping")
        fieldmap = spec["fields"]
        if set(fieldmap) - FIELDS[kind] or not REQUIRED[kind] <= set(fieldmap):
            raise MigrationError(f"{kind}: expected fields {sorted(FIELDS[kind])}; required {sorted(REQUIRED[kind])}")
        if not all(isinstance(v, str) and v for v in fieldmap.values()):
            raise MigrationError(f"{kind}: each mapped column name must be nonempty text")
        relative = spec.get("file")
        if not isinstance(relative, str):
            raise MigrationError(f"{kind}: file must be a relative path")
        try:
            reader = csv.DictReader(io.StringIO(read(relative).decode("utf-8-sig"), newline=""))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise MigrationError(f"{relative}: missing or repeated column headers")
            missing = set(fieldmap.values()) - set(reader.fieldnames)
            if missing:
                raise MigrationError(f"{relative}: missing columns {sorted(missing)}")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise MigrationError(f"{relative} row {reader.line_num}: wrong column count")
                data = {key: row[column] for key, column in fieldmap.items()}
                external = data.pop("external_id")
                if not external.strip():
                    raise MigrationError(f"{relative} row {reader.line_num}: missing external ID")
                identity = (kind, namespace, external)
                if identity in identities:
                    raise MigrationError(f"Duplicate source identity: {identity}")
                identities.add(identity)
                if kind == "customers":
                    data.setdefault("email", "")
                    data.setdefault("phone", "")
                else:
                    customer = data.pop("customer_external_id")
                    if not customer.strip():
                        raise MigrationError(f"{relative} row {reader.line_num}: missing customer reference")
                    data["customer_id"] = record_id("customers", namespace, customer)
                if kind == "tasks":
                    data.setdefault("status", "open")
                    data.setdefault("due_date", "")
                if kind == "attachments":
                    asset = read(data["path"], attachment=True)
                    data.setdefault("name", Path(data["path"]).name)
                    data.update(sha256=digest(asset), bytes=len(asset))
                validate_data(kind, data)
                records.append({"kind": kind, "id": record_id(*identity), "namespace": namespace,
                                "external_id": external, "data": data,
                                "source": {"file": relative, "row": reader.line_num}})
        except (UnicodeError, csv.Error) as exc:
            raise MigrationError(f"Cannot parse UTF-8 CSV {relative}: {exc}") from exc
    if not records:
        raise MigrationError("Export contains no records")
    return {"namespace": namespace, "duplicate_email": duplicate_rule,
            "records": records, "source_files": files, "mapping_path": mapping_path}
