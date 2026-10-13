"""Read-only, lossless collection of local machine activity stores and logs.

This collector deliberately keeps source payloads opaque. The caller should seal
``full_source`` before deriving operational summaries or exposing event metadata.
Checkpoints are proposals and should be saved only after successful ingestion.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import quote

_SQLITE_MAGIC = b"SQLite format 3\x00"
_LOG_SUFFIXES = {".jsonl", ".ndjson", ".log", ".txt", ".history", ".out", ".xml", ".csv"}
_LOG_NAME_HINTS = ("log", "history", "session", "activity", "event", "transcript", "queue", "journal", "telemetry", "state", "record")
_CHUNK_BYTES = 1_048_576
_SQLITE_PAGE_ROWS = 500
_WINDOWS_EVENT_PAGE = 500


def _hash(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(value or "") for value in parts).encode("utf-8", "replace")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        try:
            number = float(value)
            return datetime.fromtimestamp(number / (1000 if number > 10_000_000_000 else 1), timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, OverflowError, OSError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    return None


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _typed(value: Any) -> Any:
    """JSON-safe and reversible representation for a database value."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value:
            return {"$type": "float", "value": "nan"}
        if value in (float("inf"), float("-inf")):
            return {"$type": "float", "value": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return {"$type": "bytes", "encoding": "base64", "data": _b64(value), "byte_length": len(value)}
    # SQLite's standard Python adapter returns only these types. Keep an explicit
    # representation should a custom adapter ever be registered by an embedding app.
    return {"$type": type(value).__name__, "repr": repr(value)}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "surrogatepass")


def _event(*, source: str, source_id: str, event_type: str, summary: str,
           full_source: Any, source_ref: Mapping[str, Any], occurred_at: str | None = None,
           status: str = "observed", provider: str | None = None, harness: str | None = None,
           session_id: str | None = None, metrics: Mapping[str, Any] | None = None,
           metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "event_id": _hash(source, source_id, event_type), "source": source, "source_id": source_id,
        "occurred_at": occurred_at, "observed_at": _now(), "event_type": event_type,
        "peer_id": None, "session_id": session_id, "agent_id": None, "parent_agent_id": None,
        "provider": provider, "model": None, "harness": harness, "work_id": None,
        "operation_id": None, "status": status, "summary": summary, "url": None,
        "metrics": dict(metrics or {}), "metadata": dict(metadata or {}),
        "full_source": full_source, "source_ref": dict(source_ref),
    }


def _expand_path(value: str | os.PathLike[str]) -> Path:
    raw = os.path.expandvars(os.path.expanduser(os.fspath(value)))
    return Path(raw)


def _path_list(values: Any) -> list[str | os.PathLike[str]]:
    if values is None:
        return []
    if isinstance(values, (str, os.PathLike)):
        return [values]
    if isinstance(values, Mapping):
        if isinstance(values.get("path", values.get("root", values.get("value"))), (str, os.PathLike)):
            return [values.get("path", values.get("root", values.get("value")))]
        values = values.values()
    result = []
    for value in values:
        if isinstance(value, Mapping):
            path = value.get("path", value.get("root", value.get("value")))
            if isinstance(path, (str, os.PathLike)):
                result.append(path)
        elif isinstance(value, (str, os.PathLike)):
            result.append(value)
    return result


def _registry_path_values(value: Any) -> Iterator[str]:
    """Yield path-like strings from caller-named registries without exposing contents."""
    path_terms = re.compile(r"(?i)(path|root|dir|directory|location|journal|history|log|storage|cache|state)")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(child, str) and path_terms.search(str(key)):
                yield child
            else:
                yield from _registry_path_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _registry_path_values(child)


def _read_path_registry(path: Path) -> tuple[list[str], str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            value = json.loads(raw)
        elif path.suffix.lower() == ".toml":
            import tomllib
            value = tomllib.loads(raw)
        else:
            # Support simple key=value / key: value path registries without
            # treating arbitrary prose as a path source.
            value = {}
            for line in raw.splitlines():
                match = re.match(r"\s*([\w.-]*(?:path|root|dir|directory|location|journal|history|log|storage|cache|state)[\w.-]*)\s*[:=]\s*[\"']?(.+?)[\"']?\s*$", line, re.I)
                if match:
                    value[match.group(1)] = match.group(2)
        return list(_registry_path_values(value)), None
    except (OSError, UnicodeError, ValueError, ImportError) as exc:
        return [], type(exc).__name__


def discover_activity_roots(*, extra_roots: Iterable[str | os.PathLike[str]] = (),
                            path_registries: Iterable[str | os.PathLike[str]] = ()) -> dict[str, Any]:
    """Discover likely machine-activity roots and configured path registries.

    Roots are discovery starting points, not an allowlist. Callers can supply any
    additional readable path and registries can contribute further paths.
    """
    env = os.environ
    home = Path.home()
    candidates: list[tuple[str, Path]] = []
    for label, path in (
        ("codex", home / ".codex"), ("claude", home / ".claude"),
        ("gemini", home / ".gemini"), ("cursor", home / ".cursor"),
        ("windsurf", home / ".windsurf"), ("commons", home / ".commons"),
        ("user_codex_documents", home / "Documents" / "Codex"),
    ):
        candidates.append((label, path))
    for key, label in (("APPDATA", "roaming_appdata"), ("LOCALAPPDATA", "local_appdata"),
                       ("PROGRAMDATA", "program_data")):
        if env.get(key):
            candidates.append((label, Path(env[key])))
    if os.name == "nt":
        for label, rel in (
            ("powershell_psreadline", Path("Microsoft") / "Windows" / "PowerShell" / "PSReadLine"),
            ("powershell_legacy_psreadline", Path("WindowsPowerShell") / "v1.0" / "PSReadLine"),
        ):
            if env.get("APPDATA"):
                candidates.append((label, Path(env["APPDATA"]) / rel))
    roots: dict[str, Path] = {}
    labels: dict[str, set[str]] = {}
    for label, path in candidates:
        try:
            if path.exists():
                resolved = str(path.resolve())
                roots[resolved] = path
                labels.setdefault(resolved, set()).add(label)
        except OSError:
            continue
    for value in _path_list(extra_roots):
        path = _expand_path(value)
        try:
            if path.exists():
                resolved = str(path.resolve())
                roots[resolved] = path
                labels.setdefault(resolved, set()).add("caller_configured")
        except OSError:
            continue
    registry_records = []
    for value in _path_list(path_registries):
        registry = _expand_path(value)
        discovered, error = _read_path_registry(registry)
        registry_records.append({"registry_id": _hash(str(registry.resolve() if registry.exists() else registry))[:20],
                                 "status": "read" if error is None else "pending_recovery",
                                 "paths_found": len(discovered), "error": error})
        for discovered_path in discovered:
            path = _expand_path(discovered_path)
            try:
                if path.exists():
                    resolved = str(path.resolve())
                    roots[resolved] = path
                    labels.setdefault(resolved, set()).add("path_registry")
            except OSError:
                continue
    ordered = sorted(roots.items(), key=lambda item: item[0].casefold())
    return {"roots": [path for _, path in ordered],
            "root_records": [{"root_id": _hash(path_key)[:20], "path": path_key,
                              "discovery_sources": sorted(labels.get(path_key, set()))} for path_key, path in ordered],
            "path_registries": registry_records}


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16) == _SQLITE_MAGIC
    except OSError:
        return path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}


def _is_log_candidate(path: Path, explicitly_passed: bool = False) -> bool:
    if explicitly_passed:
        return True
    suffix = path.suffix.lower()
    if suffix in _LOG_SUFFIXES:
        return True
    name = path.name.lower()
    if re.search(r"\.(?:jsonl|ndjson|log|txt|history)(?:\.\d+)?$", name):
        return True
    return suffix in {".json", ".json5", ".yaml", ".yml"} and any(hint in name for hint in _LOG_NAME_HINTS)


def _derived_role(path: Path, derived_paths: Iterable[str | os.PathLike[str]]) -> str | None:
    try:
        resolved = path.resolve()
        for value in derived_paths:
            root = _expand_path(value)
            root_resolved = root.resolve()
            if resolved == root_resolved:
                return "derived_measurement_store"
            if root.is_dir() and resolved.is_relative_to(root_resolved):
                relative = resolved.relative_to(root_resolved)
                parts = {part.lower() for part in relative.parts[:-1]}
                derived_segments = {"outbox", "cipherdata", "cipher_data", "materialized", "measurements"}
                if root.name.lower() in derived_segments or any(part in derived_segments for part in parts):
                    return "derived_measurement_outbox"
                if path.suffix.lower() in {".db", ".db3", ".sqlite", ".sqlite3"} or _is_sqlite(path):
                    return "derived_measurement_store"
    except (OSError, ValueError):
        return None
    return None


def _discover_derived_files(derived_paths: Iterable[str | os.PathLike[str]]) -> tuple[dict[str, tuple[Path, str]], list[dict[str, Any]]]:
    found: dict[str, tuple[Path, str]] = {}
    issues: list[dict[str, Any]] = []
    for value in derived_paths:
        root = _expand_path(value)
        try:
            if root.is_file():
                found[str(root.resolve())] = (root, "derived_measurement_store")
                continue
            if not root.is_dir():
                issues.append({"source": root.name or str(root), "reason": "derived_path_missing", "recovery": "verify_configured_path"})
                continue
            for parent, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [directory for directory in dirs if not (Path(parent) / directory).is_symlink()]
                for name in names:
                    path = Path(parent) / name
                    role = _derived_role(path, [root])
                    if role:
                        found[str(path.resolve())] = (path, role)
        except OSError as exc:
            issues.append({"source": root.name or str(root), "reason": type(exc).__name__,
                           "recovery": "retry_derived_path_metadata"})
    return found, issues


def _derived_reference(path: Path, role: str, writer_counters: Mapping[str, Any] | None,
                       checkpoint: Mapping[str, Any] | None,
                       original_event_references: Any = None) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    stat = path.stat()
    source_id = _hash("derived-measurement", str(path.resolve()))[:24]
    counters = {str(key): value for key, value in (writer_counters or {}).items()
                if isinstance(value, (int, float, bool)) and not re.search(r"(?i)(token|secret|password|key|command|path)", str(key))}
    def reference_only(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): reference_only(child) for key, child in value.items()
                    if not re.search(r"(?i)(full_source|body|content|payload|text|token|secret|password|credential|private.?key|api[_-]?key|access[_-]?key|authorization|commandline)", str(key))}
        if isinstance(value, (list, tuple)):
            return [reference_only(child) for child in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, bytes):
            return {"encoding": "base64", "data": _b64(value), "byte_length": len(value)}
        return str(value)
    references = reference_only(original_event_references)
    state = {"kind": "derived_reference", "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
             "writer_counters": counters, "reference_hash": _hash(_json_bytes(references))}
    prior = checkpoint or {}
    unchanged = (prior.get("size") == stat.st_size and prior.get("mtime_ns") == stat.st_mtime_ns
                 and prior.get("writer_counters", {}) == counters
                 and prior.get("reference_hash") == state["reference_hash"])
    if unchanged:
        return None, state, {"source_id": source_id, "path": str(path), "kind": role, "status": "referenced_only"}
    metadata_source = {"kind": "derived_measurement_reference", "source_file_id": source_id,
                      "source_size": stat.st_size, "modified_at_ns": stat.st_mtime_ns,
                      "writer_counters": counters, "original_event_references": references,
                      "recorded_via": "original_event_references"}
    version = _hash(stat.st_size, stat.st_mtime_ns, json.dumps(counters, sort_keys=True))[:20]
    event = _event(source="machine_activity", source_id=f"{source_id}:reference:{version}",
        event_type="derived_store_reference", summary="Derived telemetry store represented by original source references",
        full_source=metadata_source,
        source_ref={"source_file_id": source_id, "path": str(path), "size": stat.st_size,
                    "modified_at_ns": stat.st_mtime_ns, "original_event_references": references,
                    "recorded_via": "original_event_references"},
        metrics={"storage_bytes": stat.st_size, **counters},
        metadata={"source_role": role, "recorded_via": "original_event_references"})
    return event, state, {"source_id": source_id, "path": str(path), "kind": role,
                          "status": "referenced_only", "recorded_via": "original_event_references",
                          "storage_bytes": stat.st_size}


def _discover_files(roots: Iterable[str | os.PathLike[str]]) -> tuple[list[Path], list[dict[str, Any]]]:
    found: dict[str, tuple[Path, bool]] = {}
    issues: list[dict[str, Any]] = []
    for value in roots:
        root = _expand_path(value)
        try:
            if root.is_file():
                found[str(root.resolve())] = (root, True)
                continue
            if not root.is_dir():
                issues.append({"source": root.name or str(root), "reason": "root_missing_or_not_directory", "recovery": "verify_path_and_retry"})
                continue
            def onerror(exc: OSError) -> None:
                issues.append({"source": Path(getattr(exc, "filename", "") or root).name,
                               "reason": type(exc).__name__, "recovery": "retry_accessible_subtree"})
            for parent, dirs, names in os.walk(root, onerror=onerror, followlinks=False):
                dirs[:] = [directory for directory in dirs if not (Path(parent) / directory).is_symlink()]
                for name in names:
                    path = Path(parent) / name
                    try:
                        suffix = path.suffix.lower()
                        sqlite_candidate = suffix in {".sqlite", ".sqlite3", ".db", ".db3"}
                        extensionless_store = not suffix and any(term in path.name.lower() for term in ("sqlite", "database", "state", "queue", "history", "journal"))
                        if path.is_file() and (_is_log_candidate(path) or
                                               (sqlite_candidate and _is_sqlite(path)) or
                                               (extensionless_store and _is_sqlite(path))):
                            found[str(path.resolve())] = (path, False)
                    except OSError as exc:
                        issues.append({"source": path.name, "reason": type(exc).__name__, "recovery": "retry_source_read"})
        except OSError as exc:
            issues.append({"source": root.name or str(root), "reason": type(exc).__name__, "recovery": "retry_root_read"})
    return [item[0] for _, item in sorted(found.items(), key=lambda pair: pair[0].casefold())], issues


def _file_identity(path: Path, sample_bytes: int = 4096) -> tuple[int, int, str]:
    stat = path.stat()
    with path.open("rb") as handle:
        sample = handle.read(sample_bytes)
    signature = _hash(path.name, sample, stat.st_dev, stat.st_ino)
    return stat.st_size, stat.st_mtime_ns, signature


def _sqlite_identity(path: Path) -> tuple[int, int, str]:
    size, mtime_ns, signature = _file_identity(path)
    sidecar_parts: list[Any] = [signature]
    # The WAL index is reader bookkeeping: read-only connections can rewrite
    # -shm without changing rows. Track only sidecars carrying database content.
    for suffix in ("-wal", "-journal"):
        sidecar = Path(str(path) + suffix)
        try:
            stat = sidecar.stat()
            with sidecar.open("rb") as handle:
                sample = handle.read(4096)
            size += stat.st_size
            mtime_ns = max(mtime_ns, stat.st_mtime_ns)
            sidecar_parts.extend((suffix, stat.st_size, stat.st_mtime_ns, hashlib.sha256(sample).hexdigest()))
        except FileNotFoundError:
            sidecar_parts.extend((suffix, "absent"))
        except OSError as exc:
            sidecar_parts.extend((suffix, type(exc).__name__))
    return size, mtime_ns, _hash(*sidecar_parts)


def _provider_harness(path: Path) -> tuple[str | None, str | None]:
    lower = str(path).lower()
    known = (("claude", "anthropic", "claude-code"), ("gemini", "google", "gemini-cli"),
             ("codex", "openai", "codex"), ("cursor", "cursor", "cursor"),
             ("windsurf", "windsurf", "windsurf"), ("copilot", "github", "github-copilot"))
    for needle, provider, harness in known:
        if needle in lower:
            return provider, harness
    return None, None


def _text_timestamp(values: Mapping[str, Any]) -> str | None:
    for key, value in values.items():
        if re.search(r"(?i)(timestamp|created_at|updated_at|occurred_at|event_time|time_utc)$", str(key)):
            normalized = _iso(value)
            if normalized:
                return normalized
    return None


def _read_log_chunk(path: Path, key: str, checkpoint: Mapping[str, Any] | None,
                    max_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    ck = dict(checkpoint or {})
    size, mtime_ns, signature = _file_identity(path)
    version = int(ck.get("version", 1) or 1)
    offset = int(ck.get("offset", 0) or 0)
    old_size = ck.get("size")
    old_mtime = ck.get("mtime_ns")
    prior_prefix_signature = signature
    if ck.get("signature") and old_size is not None and 0 <= old_size < min(size, 4096):
        # A short log's normal append extends the sampled prefix. Compare the
        # exact previous sample length so appends keep their byte checkpoint,
        # while a replaced inode or rewritten prefix starts a new version.
        _, _, prior_prefix_signature = _file_identity(path, sample_bytes=old_size)
    if offset < 0 or offset > size:
        offset = 0
        version += 1
    elif old_size == size and old_mtime not in (None, mtime_ns) and offset >= size:
        # A same-size rewrite is a new source version, not an empty append.
        offset = 0
        version += 1
    elif ck.get("signature") and ck.get("signature") != prior_prefix_signature:
        offset = 0
        version += 1
    with path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read(max(1, int(max_bytes)))
    end_offset = offset + len(payload)
    source_file_id = _hash(str(path.resolve()))[:24]
    events: list[dict[str, Any]] = []
    if payload:
        source_id = f"{source_file_id}:v{version}:bytes:{offset}-{end_offset}"
        packed = {"kind": "raw_bytes", "encoding": "base64", "data": _b64(payload), "byte_length": len(payload)}
        events.append(_event(source="machine_activity", source_id=source_id, event_type="log_bytes",
            summary="Local activity bytes captured", full_source=packed,
            source_ref={"source_file_id": source_file_id, "path": str(path), "byte_offset": offset,
                        "byte_length": len(payload), "file_version": version, "file_size_at_scan": size,
                        "file_signature": signature},
            provider=_provider_harness(path)[0], harness=_provider_harness(path)[1],
            metrics={"bytes_read": len(payload)}, metadata={"format": path.suffix.lower() or "extensionless"}))
    after_size, after_mtime, after_signature = _file_identity(path)
    changed = (size, mtime_ns, signature) != (after_size, after_mtime, after_signature)
    proposed = {"kind": "log", "offset": end_offset, "size": size, "mtime_ns": mtime_ns,
                "signature": signature, "version": version, "changed_during_read": changed}
    source = {"source_id": source_file_id, "path": str(path), "kind": "log", "size": size,
              "offset_before": offset, "offset_after": end_offset,
              "status": "pending" if end_offset < size or changed else "read",
              "file_version": version}
    return events, proposed, source


def _source_needs_scan(path: Path, checkpoint: Mapping[str, Any] | None) -> bool:
    if checkpoint is None:
        return True
    try:
        size, mtime_ns, signature = _sqlite_identity(path) if _is_sqlite(path) else _file_identity(path)
    except OSError:
        return True
    if checkpoint.get("size") != size or checkpoint.get("mtime_ns") != mtime_ns:
        return True
    if checkpoint.get("signature") != signature:
        return True
    if _is_sqlite(path):
        return bool(checkpoint.get("rescan_required")) or any(
            not bool(state.get("done")) for state in (checkpoint.get("tables") or {}).values()
            if isinstance(state, Mapping))
    return int(checkpoint.get("offset", 0) or 0) < size


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _decode_cursor_value(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("$type") == "bytes":
        return base64.b64decode(value.get("data", ""))
    if isinstance(value, Mapping) and value.get("$type") == "float":
        return {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf")}.get(value.get("value"), 0.0)
    return value


def _sqlite_table_page(connection: sqlite3.Connection, source_id: str, path: Path, table: str,
                       columns: list[tuple[str, int]], cursor: Mapping[str, Any] | None,
                       row_limit: int, version: int) -> tuple[list[dict[str, Any]], dict[str, Any], bool, int]:
    # (name, type, pk-order); use an ordered primary key when present, otherwise rowid.
    pk_columns = [column[0] for column in sorted(columns, key=lambda item: item[2]) if column[2]]
    cursor_kind = "pk" if pk_columns else "rowid"
    position = dict((cursor or {}).get("position") or {})
    select_columns = ", ".join(_quote_identifier(name) for name, _, _ in columns)
    table_sql = _quote_identifier(table)
    params: list[Any] = []
    where_sql = ""
    order = ", ".join(_quote_identifier(name) for name in pk_columns) if pk_columns else "rowid"
    rowid_column = ""
    if pk_columns and position:
        placeholders = ", ".join("?" for _ in pk_columns)
        where_sql = f" WHERE ({order}) > ({placeholders})"
        params = [_decode_cursor_value(position.get(name)) for name in pk_columns]
    elif not pk_columns:
        rowid_column = ", rowid AS __codex_rowid"
        if position.get("rowid") is not None:
            where_sql = " WHERE rowid > ?"
            params = [int(position["rowid"])]
    query = f"SELECT {select_columns}{rowid_column} FROM {table_sql}{where_sql} ORDER BY {order} LIMIT ?"
    params.append(max(1, int(row_limit)) + 1)
    try:
        fetched = connection.execute(query, params).fetchall()
    except sqlite3.OperationalError as exc:
        if not pk_columns and "rowid" in str(exc).lower():
            # WITHOUT ROWID tables must have a declared PK; malformed schemas are
            # retained as pending recovery rather than silently excluded.
            raise
        raise
    more = len(fetched) > row_limit
    page = fetched[:row_limit]
    events: list[dict[str, Any]] = []
    next_position = position
    emitted = 0
    colnames = [name for name, _, _ in columns]
    for record in page:
        values = {name: _typed(record[name]) for name in colnames}
        if pk_columns:
            key_values = {name: _typed(record[name]) for name in pk_columns}
            pk_hash = _hash(_json_bytes(key_values))[:24]
            next_position = key_values
            ref_key = {"primary_key_hash": pk_hash}
        else:
            rowid_value = int(record["__codex_rowid"])
            next_position = {"rowid": rowid_value}
            ref_key = {"rowid": rowid_value}
        row_source = {"kind": "sqlite_row", "table": table, "columns": colnames, "values": values}
        encoded = _json_bytes(row_source)
        row_hash = hashlib.sha256(encoded).hexdigest()
        row_key = pk_hash if pk_columns else str(next_position["rowid"])
        logical_id = f"{source_id}:{_hash(table)[:12]}:{row_key}:{row_hash[:16]}"
        exposed = {name: record[name] for name in colnames}
        events.append(_event(source="machine_activity", source_id=logical_id, event_type="sqlite_row",
            summary="Local activity database row captured", full_source=row_source,
            source_ref={"source_file_id": source_id, "path": str(path), "table": table,
                        **ref_key, "row_byte_length": len(encoded), "file_version": version},
            occurred_at=_text_timestamp(exposed), provider=_provider_harness(path)[0],
            harness=_provider_harness(path)[1], metrics={"row_byte_length": len(encoded)},
            metadata={"column_count": len(colnames)}))
        emitted += 1
    return events, {"kind": "sqlite_table", "position": next_position, "cursor_kind": cursor_kind,
                    "done": not more}, more, emitted


def _collect_sqlite(path: Path, key: str, checkpoint: Mapping[str, Any] | None,
                    row_limit: int) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    prior = dict(checkpoint or {})
    size, mtime_ns, signature = _sqlite_identity(path)
    version = int(prior.get("version", 1) or 1)
    tables_state = dict(prior.get("tables") or {})
    prior_size = int(prior.get("size", 0)) if prior else 0
    identity_changed = bool(prior) and (size != prior_size or mtime_ns != prior.get("mtime_ns") or
                                         (prior.get("signature") and signature != prior.get("signature")))
    scan_in_progress = any(isinstance(state, Mapping) and not state.get("done")
                           for state in tables_state.values())
    rescan_required = bool(prior.get("rescan_required"))
    if identity_changed and scan_in_progress:
        # Keep the current bounded pass moving under an active writer. Its
        # changed snapshot must be followed by a complete new scan before read.
        rescan_required = True
    elif identity_changed or (rescan_required and not scan_in_progress):
        # Growth is not proof of append-only rows: mutable values and new keys
        # can precede a saved cursor. Stable row IDs deduplicate this replay.
        version += 1
        tables_state = {}
        rescan_required = False
    uri = "file:" + quote(str(path.resolve()).replace("\\", "/"), safe="/:@") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=3.0)
    connection.row_factory = sqlite3.Row
    events: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    source_id = _hash(str(path.resolve()))[:24]
    pending = False
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        schema_rows = connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        current_tables = {str(schema["name"]) for schema in schema_rows}
        tables_state = {name: state for name, state in tables_state.items() if name in current_tables}
        for schema in schema_rows:
            table = str(schema["name"])
            try:
                table_info = connection.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
                columns = [(str(row["name"]), str(row["type"] or ""), int(row["pk"] or 0)) for row in table_info]
                schema_value = {"kind": "sqlite_schema", "table": table, "sql": schema["sql"],
                                "columns": [{"name": name, "type": kind, "primary_key_order": pk} for name, kind, pk in columns]}
                schema_bytes = _json_bytes(schema_value)
                schema_hash = hashlib.sha256(schema_bytes).hexdigest()
                schema_id = f"{source_id}:{_hash(table)[:12]}:schema:{schema_hash[:16]}"
                events.append(_event(source="machine_activity", source_id=schema_id, event_type="sqlite_schema",
                    summary="Local activity database schema captured", full_source=schema_value,
                    source_ref={"source_file_id": source_id, "path": str(path), "table": table,
                                "schema_byte_length": len(schema_bytes), "file_version": version},
                    provider=_provider_harness(path)[0], harness=_provider_harness(path)[1],
                    metrics={"schema_byte_length": len(schema_bytes)}, metadata={"column_count": len(columns)}))
                if isinstance(tables_state.get(table), Mapping) and tables_state[table].get("done"):
                    continue
                table_events, proposed_table, more, count = _sqlite_table_page(connection, source_id, path, table,
                    columns, tables_state.get(table), row_limit, version)
                events.extend(table_events)
                tables_state[table] = proposed_table
                if more:
                    pending = True
                    issues.append({"source": table, "reason": "sqlite_table_batch_deferred",
                                   "recovery": "continue_from_table_cursor"})
                else:
                    proposed_table["done"] = True
            except (sqlite3.DatabaseError, OSError, ValueError, TypeError) as exc:
                pending = True
                issues.append({"source": table, "reason": type(exc).__name__,
                               "recovery": "retry_table_from_saved_cursor"})
    finally:
        connection.close()
    after_size, after_mtime, after_signature = _sqlite_identity(path)
    changed = (size, mtime_ns, signature) != (after_size, after_mtime, after_signature)
    if changed:
        pending = True
        rescan_required = True
        issues.append({"source": path.name, "reason": "database_changed_during_read",
                       "recovery": "repeat_source_scan_for_changed_rows"})
    elif rescan_required:
        pending = True
        issues.append({"source": path.name, "reason": "database_changed_during_scan",
                       "recovery": "finish_current_pass_then_repeat_source_scan"})
    proposed = {"kind": "sqlite", "size": size, "mtime_ns": mtime_ns,
                "signature": signature, "version": version, "tables": tables_state,
                "changed_during_read": changed, "rescan_required": rescan_required}
    source = {"source_id": source_id, "path": str(path), "kind": "sqlite",
              "size": size, "file_version": version, "status": "pending" if pending else "read",
              "table_count": len(tables_state)}
    return events, proposed, source, issues


def _windows_event_channels() -> tuple[list[str], str | None]:
    if os.name != "nt":
        return [], None
    executable = shutil.which("wevtutil.exe") or shutil.which("wevtutil")
    if not executable:
        return [], "wevtutil_unavailable"
    try:
        result = subprocess.run([executable, "el"], capture_output=True, timeout=20, check=False)
        if result.returncode != 0:
            return [], f"wevtutil_exit_{result.returncode}"
        return [line.strip() for line in result.stdout.decode("utf-8", "replace").splitlines() if line.strip()], None
    except (OSError, subprocess.SubprocessError) as exc:
        return [], type(exc).__name__


def _split_event_xml(payload: bytes) -> list[bytes]:
    return [match.group(0) for match in re.finditer(rb"<Event(?:\s[^>]*)?>.*?</Event>", payload, re.DOTALL)]


def _event_record_id(xml_bytes: bytes) -> tuple[int | None, str | None]:
    try:
        root = ET.fromstring(xml_bytes)
        record_id = root.findtext(".//{*}EventRecordID")
        time_node = root.find(".//{*}TimeCreated")
        occurred_at = _iso(time_node.attrib.get("SystemTime")) if time_node is not None else None
        return int(record_id) if record_id else None, occurred_at
    except (ET.ParseError, ValueError):
        return None, None


def _collect_windows_events(checkpoints: Mapping[str, Any], page_size: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], int, list[dict[str, Any]]]:
    channels, discovery_error = _windows_event_channels()
    events: list[dict[str, Any]] = []
    proposed: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    pending_channels = 0
    if discovery_error:
        issues.append({"source": "Windows Event Log registry", "reason": discovery_error,
                       "recovery": "retry_event_log_discovery"})
        sources.append({"source_id": "windows-event-log-registry", "kind": "windows_event_log_registry",
                        "status": "pending_recovery", "reason": discovery_error})
        return events, proposed, issues, pending_channels, sources
    executable = shutil.which("wevtutil.exe") or shutil.which("wevtutil")
    for channel in channels:
        checkpoint_key = "machine:windows_event:" + channel
        old = checkpoints.get(checkpoint_key, {}) if isinstance(checkpoints.get(checkpoint_key), Mapping) else {}
        cursor = int(old.get("record_id", 0) or 0)
        query = f"*[System[EventRecordID > {cursor}]]"
        try:
            result = subprocess.run([executable, "qe", channel, "/q:" + query, "/f:RenderedXml", "/rd:false",
                                     "/c:" + str(max(1, int(page_size)) + 1)], capture_output=True, timeout=45, check=False)
            if result.returncode != 0:
                issues.append({"source": channel, "reason": f"wevtutil_exit_{result.returncode}",
                               "recovery": "retry_channel_from_saved_record_id"})
                pending_channels += 1
                proposed[checkpoint_key] = dict(old)
                sources.append({"source_id": _hash("windows-event-log", channel)[:24],
                                "kind": "windows_event_log", "channel": channel,
                                "status": "pending_recovery", "record_id_cursor": cursor})
                continue
            records = _split_event_xml(result.stdout)
            has_more = len(records) > page_size
            selected = records[:page_size]
            latest = cursor
            source_id = _hash("windows-event-log", channel)[:24]
            for ordinal, xml_bytes in enumerate(selected):
                record_id, occurred = _event_record_id(xml_bytes)
                if record_id is not None:
                    latest = max(latest, record_id)
                byte_text = {"kind": "windows_event_xml", "encoding": "base64", "data": _b64(xml_bytes), "byte_length": len(xml_bytes)}
                source_key = str(record_id if record_id is not None else f"unparsed-{cursor}-{ordinal}")
                events.append(_event(source="windows_event_log", source_id=f"{source_id}:{source_key}",
                    event_type="windows_event", summary="Windows event record captured", full_source=byte_text,
                    source_ref={"event_log": channel, "source_id": source_id, "record_id": record_id,
                                "byte_length": len(xml_bytes)}, occurred_at=occurred,
                    metrics={"record_byte_length": len(xml_bytes)}, metadata={"record_id_present": record_id is not None}))
            if has_more:
                issues.append({"source": channel, "reason": "event_log_batch_deferred",
                               "recovery": "continue_from_record_id"})
                pending_channels += 1
            proposed[checkpoint_key] = {"kind": "windows_event_log", "record_id": latest,
                                        "status": "pending" if has_more else "read"}
            sources.append({"source_id": source_id, "kind": "windows_event_log", "channel": channel,
                            "status": "pending" if has_more else "read", "record_id_before": cursor,
                            "record_id_after": latest, "records_read": len(selected)})
        except (OSError, subprocess.SubprocessError) as exc:
            issues.append({"source": channel, "reason": type(exc).__name__,
                           "recovery": "retry_channel_from_saved_record_id"})
            pending_channels += 1
            proposed[checkpoint_key] = dict(old)
            sources.append({"source_id": _hash("windows-event-log", channel)[:24],
                            "kind": "windows_event_log", "channel": channel,
                            "status": "pending_recovery", "record_id_cursor": cursor,
                            "reason": type(exc).__name__})
    return events, proposed, issues, pending_channels, sources


def collect_machine_activity(config: Mapping[str, Any] | None = None, *,
                              roots: Iterable[str | os.PathLike[str]] | None = None,
                              extra_roots: Iterable[str | os.PathLike[str]] = (),
                              path_registries: Iterable[str | os.PathLike[str]] = (),
                              checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
                              max_sources: int | None = None,
                              max_bytes_per_source: int = _CHUNK_BYTES,
                              max_rows_per_table: int = _SQLITE_PAGE_ROWS,
                              include_windows_events: bool = True,
                              windows_event_page_size: int = _WINDOWS_EVENT_PAGE) -> dict[str, Any]:
    """Collect local SQLite rows, raw activity-log bytes, and Windows event XML.

    All limits create continuation checkpoints. ``coverage.complete`` stays false
    whenever a source, table, byte range, or event-log page remains pending.
    """
    config = config or {}
    if roots is None:
        roots = config.get("roots", config.get("paths", config.get("activity_roots", config.get("root", config.get("path")))))
    if not extra_roots:
        extra_roots = config.get("extra_roots", ()) or ()
    if not path_registries:
        path_registries = config.get("path_registries", ()) or ()
    if checkpoints is None:
        checkpoints = config.get("checkpoints")
    roots = _path_list(roots) if roots is not None else None
    extra_roots = _path_list(extra_roots)
    path_registries = _path_list(path_registries)
    max_sources = max_sources if max_sources is not None else config.get("max_sources")
    max_bytes_per_source = config.get("max_bytes_per_source", max_bytes_per_source)
    max_rows_per_table = config.get("max_rows_per_table", max_rows_per_table)
    include_windows_events = config.get("include_windows_events", include_windows_events)
    windows_event_page_size = config.get("windows_event_page_size", windows_event_page_size)
    requested_roots = list(roots) if roots is not None else None
    derived_paths = _path_list(config.get("derived_measurement_paths", ()))
    writer_counters = config.get("writer_counters", {})
    original_event_references = config.get("original_event_references", ())
    discovered = discover_activity_roots(extra_roots=extra_roots, path_registries=path_registries)
    selected_roots = requested_roots if requested_roots is not None else discovered["roots"]
    selected_root_records = ([{"root_id": _hash(str(_expand_path(value).resolve()))[:20],
                               "path": str(_expand_path(value).resolve()), "discovery_sources": ["caller_configured"]}
                              for value in selected_roots]
                             if requested_roots is not None else discovered["root_records"])
    paths, discovery_issues = _discover_files(selected_roots)
    derived_found, derived_issues = _discover_derived_files(derived_paths)
    path_map = {str(path.resolve()): path for path in paths}
    for resolved, (derived_path, _) in derived_found.items():
        path_map.setdefault(resolved, derived_path)
    paths = sorted(path_map.values(), key=lambda item: str(item.resolve()).casefold())
    prior = checkpoints or {}
    events: list[dict[str, Any]] = []
    next_checkpoints: dict[str, dict[str, Any]] = {}
    source_records: list[dict[str, Any]] = list(selected_root_records)
    issues = list(discovery_issues) + list(derived_issues)
    for registry in discovered["path_registries"]:
        if registry.get("status") == "pending_recovery":
            issues.append({"source": registry.get("registry_id"), "reason": registry.get("error"),
                           "recovery": "retry_path_registry_read"})
    if not selected_roots and not (include_windows_events and os.name == "nt"):
        issues.append({"source": "root_discovery", "reason": "no_activity_roots_available",
                       "recovery": "configure_roots_or_path_registries"})
    coverage = {"roots_discovered": len(selected_root_records), "sources_discovered": len(paths),
                "sources_read": 0, "sources_pending": 0, "sources_deferred": 0,
                "derived_sources_referenced": 0,
                "tables_discovered": 0, "rows_read": 0, "bytes_read": 0,
                "windows_channels_discovered": 0, "windows_channels_pending": 0,
                "events_emitted": 0, "unread_reasons": issues, "complete": False}
    collector_state = dict(prior.get("__machine_collector__", {})) if isinstance(prior.get("__machine_collector__"), Mapping) else {}
    dirty: list[tuple[str, Path]] = []
    unchanged: list[tuple[str, Path]] = []
    normal_paths: list[Path] = []
    for path in paths:
        role = _derived_role(path, derived_paths)
        if role:
            derived_key = "machine:derived:" + str(path.resolve())
            try:
                event, proposed, source = _derived_reference(path, role,
                    writer_counters if isinstance(writer_counters, Mapping) else {}, prior.get(derived_key),
                    original_event_references)
                if event:
                    events.append(event)
                next_checkpoints[derived_key] = proposed
                source_records.append(source)
                coverage["derived_sources_referenced"] += 1
                coverage["sources_read"] += 1
            except (OSError, PermissionError) as exc:
                source_records.append({"source_id": _hash(str(path.resolve()))[:24], "path": str(path),
                                      "kind": role, "status": "pending_recovery", "reason": type(exc).__name__})
                issues.append({"source": str(path), "reason": type(exc).__name__,
                               "recovery": "retry_derived_metadata_read"})
                coverage["sources_pending"] += 1
            continue
        normal_paths.append(path)
        resolved_path = str(path.resolve())
        key = ("machine:sqlite:" if _is_sqlite(path) else "machine:file:") + resolved_path
        old = prior.get(key) if isinstance(prior.get(key), Mapping) else None
        (dirty if _source_needs_scan(path, old) else unchanged).append((key, path))
    dirty.sort(key=lambda pair: pair[0].casefold())
    cursor = str(collector_state.get("cursor") or "")
    if cursor and dirty:
        pivot = next((index for index, item in enumerate(dirty) if item[0].casefold() > cursor.casefold()), 0)
        dirty = dirty[pivot:] + dirty[:pivot]
    cap = len(dirty) if max_sources is None else max(0, int(max_sources))
    selected_items = dirty[:cap]
    deferred_items = dirty[cap:]
    selected_paths = [path for _, path in selected_items]
    coverage["sources_deferred"] = len(deferred_items)
    for key, path in unchanged:
        source_records.append({"source_id": _hash(str(path.resolve()))[:24], "path": str(path),
                               "kind": "sqlite" if _is_sqlite(path) else "log", "status": "unchanged"})
    for key, path in deferred_items:
        source_records.append({"source_id": _hash(str(path.resolve()))[:24], "path": str(path),
                               "kind": "sqlite" if _is_sqlite(path) else "log", "status": "pending_deferred"})
    if deferred_items:
        issues.append({"source": "source_scan", "reason": "source_batch_deferred",
                       "count": len(deferred_items), "recovery": "continue_from_collector_cursor"})
    for path in selected_paths:
        resolved_path = str(path.resolve())
        key = ("machine:sqlite:" if _is_sqlite(path) else "machine:file:") + resolved_path
        old = prior.get(key, {}) if isinstance(prior.get(key), Mapping) else {}
        try:
            if _is_sqlite(path):
                source_events, proposed, source, source_issues = _collect_sqlite(path, key, old, max_rows_per_table)
                next_checkpoints[key] = proposed
                events.extend(source_events)
                issues.extend({"path_id": source["source_id"], **issue} for issue in source_issues)
                coverage["tables_discovered"] += source.get("table_count", 0)
                coverage["rows_read"] += sum(e["event_type"] == "sqlite_row" for e in source_events)
                if source.get("status") == "pending":
                    coverage["sources_pending"] += 1
            else:
                source_events, proposed, source = _read_log_chunk(path, key, old, max_bytes_per_source)
                next_checkpoints[key] = proposed
                events.extend(source_events)
                coverage["bytes_read"] += sum(e.get("metrics", {}).get("bytes_read", 0) for e in source_events)
                if source.get("status") == "pending":
                    coverage["sources_pending"] += 1
            source_records.append(source)
            coverage["sources_read"] += 1
            collector_state["cursor"] = key
        except (OSError, PermissionError, sqlite3.DatabaseError, ValueError, TypeError) as exc:
            source_records.append({"source_id": _hash(str(path.resolve()))[:24], "path": str(path),
                                   "status": "pending_recovery", "reason": type(exc).__name__})
            issues.append({"source": str(path), "reason": type(exc).__name__, "recovery": "retry_from_saved_checkpoint"})
            coverage["sources_pending"] += 1
    if include_windows_events and os.name == "nt":
        windows_events, windows_cursors, windows_issues, pending_channels, windows_sources = _collect_windows_events(
            prior, windows_event_page_size)
        events.extend(windows_events)
        source_records.extend(windows_sources)
        next_checkpoints.update(windows_cursors)
        issues.extend(windows_issues)
        coverage["windows_channels_discovered"] = len(windows_cursors)
        coverage["windows_channels_pending"] = pending_channels
    if collector_state:
        next_checkpoints["__machine_collector__"] = collector_state
    # Any key omitted by a max_sources batch remains explicitly pending. Existing
    # sources with unread byte/table pages likewise prevent a complete claim.
    coverage["events_emitted"] = len(events)
    coverage["complete"] = (not issues and coverage["sources_deferred"] == 0
                            and coverage["sources_pending"] == 0
                            and coverage["windows_channels_pending"] == 0)
    coverage["unread_reasons"] = issues
    return {"events": events, "checkpoints": next_checkpoints, "coverage": coverage,
            "sources": source_records, "path_registries": discovered["path_registries"],
            "discovered_roots": selected_root_records,
            "auto_discovered_roots": discovered["root_records"]}


__all__ = ["discover_activity_roots", "collect_machine_activity"]

