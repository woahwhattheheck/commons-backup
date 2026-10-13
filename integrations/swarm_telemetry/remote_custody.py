"""Passive, resumable encrypted-source copying through an existing Drive binding.

The private SQLite journal contains an immutable, complete source_records
snapshot. Ciphertext is streamed with sqlite3.blobopen; this module never loads
a key, imports the encryption implementation, or decrypts source material.
Native connector calls are handed to their existing host as explicit jobs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import gzip
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import zlib
from contextlib import contextmanager
from pathlib import Path


VERSION = 1
IO_BYTES = 1024 * 1024
MANIFEST_FORMAT = "swarm-remote-custody-v1"
COLUMNS = ("ref", "source_id", "sha256", "byte_length", "character_length",
           "iv", "ciphertext", "mac", "format", "key_reference")
META_COLUMNS = tuple(name for name in COLUMNS if name != "ciphertext")
SOURCE_DDL = ("CREATE TABLE source_records (ref TEXT PRIMARY KEY,source_id TEXT,"
              "sha256 TEXT,byte_length INTEGER,character_length INTEGER,iv BLOB,"
              "ciphertext BLOB,mac BLOB,format TEXT,key_reference TEXT)")
TOOL_PREFIX = "mcp__codex_apps__google_drive_"
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


class CustodyError(Exception):
    """Only the fixed code is suitable for operational output."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise CustodyError(code)


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _typed(value):
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bytes):
        return {"type": "blob", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "real", "value": value}
    raise CustodyError("UNSUPPORTED_SOURCE_VALUE")


def _untyped(item):
    _require(isinstance(item, dict) and set(item) == {"type", "value"},
             "INVALID_MANIFEST_VALUE")
    kind, value = item["type"], item["value"]
    if kind == "null" and value is None:
        return None
    if kind == "blob" and isinstance(value, str):
        return base64.b64decode(value, validate=True)
    if kind == "text" and isinstance(value, str):
        return value
    if kind == "integer" and type(value) is int:
        return value
    if kind == "real" and type(value) in (int, float):
        return float(value)
    raise CustodyError("INVALID_MANIFEST_VALUE")


def _metadata_values(metadata):
    _require(isinstance(metadata, dict) and set(metadata) == set(META_COLUMNS),
             "INVALID_SOURCE_METADATA")
    values = {name: _untyped(metadata[name]) for name in META_COLUMNS}
    _require(isinstance(values["ref"], str), "INVALID_SOURCE_REFERENCE")
    _require(isinstance(values["iv"], bytes) and isinstance(values["mac"], bytes),
             "INVALID_SOURCE_BLOBS")
    return values


def _record_id(metadata, ciphertext_sha256, ciphertext_bytes):
    return _digest({"metadata": metadata, "ciphertext_sha256": ciphertext_sha256,
                    "ciphertext_bytes": ciphertext_bytes})


def _provider_id(value):
    _require(isinstance(value, str) and ID_RE.fullmatch(value), "INVALID_PROVIDER_ID")
    return value


def _hash_file(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as handle:
        while block := handle.read(IO_BYTES):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _private_file(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)


@contextmanager
def _db(path):
    path = Path(path).resolve()
    _require(path.is_file(), "JOURNAL_NOT_FOUND")
    db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA temp_store=MEMORY")
    try:
        yield db
    finally:
        db.close()


def _meta(db, key):
    row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    _require(row is not None, "INCOMPLETE_JOURNAL")
    return json.loads(row[0])


def _set_meta(db, key, value):
    db.execute("INSERT INTO metadata(key,value) VALUES (?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, _json(value)))


def _check_journal(db):
    _require(_meta(db, "version") == VERSION, "UNSUPPORTED_JOURNAL_VERSION")


def _object(db, object_id):
    row = db.execute("SELECT * FROM objects WHERE object_id=?", (object_id,)).fetchone()
    _require(row is not None, "OBJECT_NOT_FOUND")
    return row


def _insert_source(db, rowid, values, size):
    slots = ["zeroblob(?)" if name == "ciphertext" else "?" for name in COLUMNS]
    bindings = [rowid] + [size if name == "ciphertext" else values[name] for name in COLUMNS]
    db.execute("INSERT INTO source_records(rowid," + ",".join(COLUMNS) + ") VALUES (?," +
               ",".join(slots) + ")", bindings)


def _initialize_journal(journal, binding):
    """Publish a complete empty journal without replacing an existing file."""
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".custody-bootstrap-", dir=journal.parent) as directory:
        temporary = Path(directory) / "journal.sqlite3"
        _private_file(temporary)
        with _db(temporary) as db:
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE records(seq INTEGER PRIMARY KEY,source_rowid INTEGER UNIQUE,
                    record_id TEXT UNIQUE,metadata_json TEXT NOT NULL,
                    ciphertext_bytes INTEGER NOT NULL,ciphertext_sha256 TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE objects(seq INTEGER PRIMARY KEY,object_id TEXT UNIQUE,
                    kind TEXT NOT NULL,record_seq INTEGER REFERENCES records(seq),
                    part INTEGER,offset_bytes INTEGER NOT NULL,size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,file_name TEXT UNIQUE,state TEXT NOT NULL,
                    remote_file_id TEXT,search_complete INTEGER NOT NULL DEFAULT 0,
                    upload_attempts INTEGER NOT NULL DEFAULT 0,readback_sha256 TEXT,
                    readback_bytes INTEGER,last_error_code TEXT,
                    UNIQUE(record_seq,part));
                CREATE TABLE candidates(object_id TEXT NOT NULL,file_id TEXT NOT NULL,
                    state TEXT NOT NULL,PRIMARY KEY(object_id,file_id));
                CREATE INDEX objects_pending ON objects(state,seq);
            """)
            db.execute(SOURCE_DDL)
            with db:
                _set_meta(db, "version", VERSION)
                _set_meta(db, "prepared", False)
                for key, value in binding.items():
                    _set_meta(db, key, value)
        # A concurrent initializer may have published first. Reuse that file
        # through prepare's existing binding checks; never overwrite it.
        try:
            os.link(temporary, journal)
        except FileExistsError:
            pass


def prepare(source_db, journal, operation_id, account_ref, folder_id,
            chunk_bytes=4 * 1024 * 1024):
    """Capture all rows at one SQLite read snapshot; repeating reuses that snapshot."""
    _require(hasattr(sqlite3.Connection, "blobopen"), "SQLITE_BLOBOPEN_REQUIRED")
    _require(isinstance(operation_id, str) and operation_id.strip(), "OPERATION_ID_REQUIRED")
    _require(isinstance(account_ref, str) and account_ref.strip(), "ACCOUNT_REFERENCE_REQUIRED")
    _require(type(chunk_bytes) is int and 0 < chunk_bytes <= 64 * 1024 * 1024,
             "INVALID_CHUNK_BYTES")
    folder_id = _provider_id(folder_id)
    source_path, journal = Path(source_db).resolve(), Path(journal).resolve()
    _require(source_path != journal, "SOURCE_JOURNAL_COLLISION")
    _require(source_path.is_file(), "SOURCE_DATABASE_NOT_FOUND")
    source_stat = source_path.stat()
    source_identity = {"path": str(source_path), "device": source_stat.st_dev,
                       "inode": source_stat.st_ino}
    destination = {"provider": "google_drive", "account_ref": account_ref,
                   "folder_id": folder_id}
    destination_key = _digest(destination)
    operation_key = _digest({"operation_id": operation_id, "source": source_identity,
                             "destination_key": destination_key})
    binding = {"operation_id": operation_id, "source_identity": source_identity,
               "destination": destination, "destination_key": destination_key,
               "operation_key": operation_key, "chunk_bytes": chunk_bytes}
    if not journal.exists():
        _initialize_journal(journal, binding)
    with _db(journal) as db:
        _check_journal(db)
        for key, value in binding.items():
            _require(_meta(db, key) == value, "OPERATION_INPUT_OR_DESTINATION_CHANGED")
        if _meta(db, "prepared"):
            return _status(db)
        _require(db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0,
                 "INCOMPLETE_SNAPSHOT_CONFLICT")
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=30)
        source.row_factory = sqlite3.Row
        try:
            source.execute("PRAGMA busy_timeout=30000")
            source.execute("BEGIN")
            schema = [row[1] for row in source.execute("PRAGMA table_info(source_records)")]
            _require(schema == list(COLUMNS), "SOURCE_SCHEMA_MISMATCH")
            db.execute("BEGIN IMMEDIATE")
            snapshot_digest, count = hashlib.sha256(), 0
            query = ("SELECT rowid AS source_rowid," + ",".join(META_COLUMNS) +
                     ",length(ciphertext) AS ciphertext_bytes,typeof(ciphertext) AS blob_type "
                     "FROM source_records ORDER BY rowid")
            for row in source.execute(query):
                _require(row["blob_type"] == "blob", "INVALID_CIPHERTEXT_TYPE")
                size, rowid = row["ciphertext_bytes"], row["source_rowid"]
                values = {name: row[name] for name in META_COLUMNS}
                metadata = {name: _typed(values[name]) for name in META_COLUMNS}
                _metadata_values(metadata)
                _insert_source(db, rowid, values, size)
                record_seq = db.execute(
                    "INSERT INTO records(source_rowid,metadata_json,ciphertext_bytes) VALUES (?,?,?)",
                    (rowid, _json(metadata), size)).lastrowid
                cipher_digest, offset, part = hashlib.sha256(), 0, 0
                with source.blobopen("source_records", "ciphertext", rowid, readonly=True) as incoming:
                    with db.blobopen("source_records", "ciphertext", rowid, readonly=False) as outgoing:
                        while offset < size or part == 0:
                            length = min(chunk_bytes, size - offset)
                            remaining, chunk_digest = length, hashlib.sha256()
                            while remaining:
                                block = incoming.read(min(IO_BYTES, remaining))
                                _require(bool(block), "SOURCE_CIPHERTEXT_TRUNCATED")
                                outgoing.write(block)
                                cipher_digest.update(block)
                                chunk_digest.update(block)
                                remaining -= len(block)
                            db.execute("INSERT INTO objects(kind,record_seq,part,offset_bytes,"
                                       "size_bytes,sha256,state) VALUES ('chunk',?,?,?,?,?,'pending_search')",
                                       (record_seq, part, offset, length, chunk_digest.hexdigest()))
                            offset += length
                            part += 1
                cipher_hash = cipher_digest.hexdigest()
                record_id = _record_id(metadata, cipher_hash, size)
                db.execute("UPDATE records SET record_id=?,ciphertext_sha256=?,chunk_count=? WHERE seq=?",
                           (record_id, cipher_hash, part, record_seq))
                for chunk in db.execute("SELECT seq,part,sha256 FROM objects WHERE record_seq=?", (record_seq,)):
                    object_id = _digest({"operation_key": operation_key, "record_id": record_id,
                                         "part": chunk["part"], "sha256": chunk["sha256"]})
                    name = "src-{}-{}-{:08x}.bin".format(operation_key, record_id, chunk["part"])
                    db.execute("UPDATE objects SET object_id=?,file_name=? WHERE seq=?",
                               (object_id, name, chunk["seq"]))
                snapshot_digest.update((record_id + "\n").encode("ascii"))
                count += 1
            _set_meta(db, "snapshot_sha256", snapshot_digest.hexdigest())
            _set_meta(db, "records_total", count)
            _set_meta(db, "prepared", True)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            source.close()
        return _status(db)


def _stage_path(journal, name):
    folder = Path(str(Path(journal).resolve()) + ".objects")
    folder.mkdir(exist_ok=True, mode=0o700)
    _require(not folder.is_symlink(), "INVALID_STAGING_DIRECTORY")
    os.chmod(folder, 0o700)
    _require(Path(name).name == name and "/" not in name and "\\" not in name,
             "INVALID_OBJECT_NAME")
    return folder / name


def _write_resumable(path, blocks):
    """Resume an identical prefix, append only, and retain partial bytes on failure."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    digest, written = hashlib.sha256(), 0
    with os.fdopen(fd, "r+b") as handle:
        os.chmod(path, 0o600)
        existing = os.fstat(handle.fileno()).st_size
        for block in blocks:
            prefix = min(len(block), max(0, existing - written))
            if prefix:
                _require(handle.read(prefix) == block[:prefix], "STAGING_PREFIX_CONFLICT")
            if prefix < len(block):
                handle.write(block[prefix:])
            written += len(block)
            digest.update(block)
        _require(existing <= written, "STAGING_LENGTH_CONFLICT")
        handle.flush()
        os.fsync(handle.fileno())
    return digest.hexdigest(), written


def _chunk_blocks(db, row):
    source_rowid = db.execute("SELECT source_rowid FROM records WHERE seq=?",
                             (row["record_seq"],)).fetchone()[0]
    with db.blobopen("source_records", "ciphertext", source_rowid, readonly=True) as blob:
        blob.seek(row["offset_bytes"])
        remaining = row["size_bytes"]
        while remaining:
            block = blob.read(min(IO_BYTES, remaining))
            _require(bool(block), "SNAPSHOT_CIPHERTEXT_TRUNCATED")
            remaining -= len(block)
            yield block


def _stage_object(db, row, journal):
    path = _stage_path(journal, row["file_name"])
    if row["kind"] == "chunk":
        digest, size = _write_resumable(path, _chunk_blocks(db, row))
    else:
        _require(path.is_file(), "MANIFEST_STAGE_MISSING")
        digest, size = _hash_file(path)
    _require(digest == row["sha256"] and size == row["size_bytes"], "STAGED_OBJECT_MISMATCH")
    return path


def _manifest_blocks(db):
    digest = hashlib.sha256()
    header = {"type": "header", "format": MANIFEST_FORMAT,
              "operation_key": _meta(db, "operation_key"),
              "destination_key": _meta(db, "destination_key"),
              "snapshot_sha256": _meta(db, "snapshot_sha256"),
              "records_total": _meta(db, "records_total"),
              "chunks_total": db.execute("SELECT COUNT(*) FROM objects WHERE kind='chunk'").fetchone()[0]}
    block = (_json(header) + "\n").encode("utf-8")
    digest.update(block)
    yield block
    for record in db.execute("SELECT * FROM records ORDER BY seq"):
        item = {"type": "record", "record_id": record["record_id"],
                "metadata": json.loads(record["metadata_json"]),
                "ciphertext_bytes": record["ciphertext_bytes"],
                "ciphertext_sha256": record["ciphertext_sha256"],
                "chunk_count": record["chunk_count"]}
        block = (_json(item) + "\n").encode("utf-8")
        digest.update(block)
        yield block
        for chunk in db.execute("SELECT * FROM objects WHERE record_seq=? ORDER BY part", (record["seq"],)):
            _require(chunk["state"] == "confirmed" and chunk["remote_file_id"], "CHUNK_NOT_CONFIRMED")
            item = {"type": "chunk", "record_id": record["record_id"], "part": chunk["part"],
                    "offset_bytes": chunk["offset_bytes"], "size_bytes": chunk["size_bytes"],
                    "sha256": chunk["sha256"], "file_name": chunk["file_name"],
                    "provider": "google_drive", "file_id": chunk["remote_file_id"]}
            block = (_json(item) + "\n").encode("utf-8")
            digest.update(block)
            yield block
    yield (_json({"type": "complete", "records_total": header["records_total"],
                  "chunks_total": header["chunks_total"],
                  "content_sha256": digest.hexdigest()}) + "\n").encode("utf-8")


def _ensure_manifest(db, journal):
    if not _meta(db, "prepared") or db.execute("SELECT 1 FROM objects WHERE kind='manifest'").fetchone():
        return
    if db.execute("SELECT 1 FROM objects WHERE kind='chunk' AND state!='confirmed'").fetchone():
        return
    operation_key, snapshot_hash = _meta(db, "operation_key"), _meta(db, "snapshot_sha256")
    name = "src-{}-manifest-{}.jsonl".format(operation_key, snapshot_hash)
    digest, size = _write_resumable(_stage_path(journal, name), _manifest_blocks(db))
    object_id = _digest({"operation_key": operation_key, "manifest_sha256": digest})
    db.execute("INSERT INTO objects(object_id,kind,offset_bytes,size_bytes,sha256,file_name,state) "
               "VALUES (?,'manifest',0,?,?,?,'pending_search')", (object_id, size, digest, name))


def _status(db):
    prepared = _meta(db, "prepared")
    total = _meta(db, "records_total") if prepared else 0
    manifest = db.execute("SELECT * FROM objects WHERE kind='manifest'").fetchone()
    confirmed = bool(manifest and manifest["state"] == "confirmed")
    states = dict(db.execute("SELECT state,COUNT(*) FROM objects GROUP BY state"))
    byte_row = db.execute("SELECT COALESCE(SUM(size_bytes),0),"
                          "COALESCE(SUM(CASE WHEN state='confirmed' THEN size_bytes ELSE 0 END),0) "
                          "FROM objects").fetchone()
    ciphertext = db.execute("SELECT COALESCE(SUM(size_bytes),0),"
                            "COALESCE(SUM(CASE WHEN state='confirmed' THEN size_bytes ELSE 0 END),0) "
                            "FROM objects WHERE kind='chunk'").fetchone()
    complete_ciphertexts = db.execute(
        "SELECT COUNT(*) FROM records r WHERE NOT EXISTS "
        "(SELECT 1 FROM objects o WHERE o.record_seq=r.seq AND o.state!='confirmed')").fetchone()[0]
    return {"ok": True, "operation_key": _meta(db, "operation_key"),
            "destination_key": _meta(db, "destination_key"), "snapshot_complete": prepared,
            "copy_state": "confirmed" if confirmed else "pending",
            "records_total": total, "records_confirmed": total if confirmed else 0,
            "records_ciphertext_confirmed": complete_ciphertexts,
            "objects_total": sum(states.values()), "objects_confirmed": states.get("confirmed", 0),
            "object_states": states, "bytes_total": byte_row[0], "bytes_confirmed": byte_row[1],
            "ciphertext_bytes_total": ciphertext[0], "ciphertext_bytes_confirmed": ciphertext[1],
            "manifest": None if not manifest else {
                "object_id": manifest["object_id"], "state": manifest["state"],
                "sha256": manifest["sha256"], "file_id": manifest["remote_file_id"]}}


def status(journal):
    with _db(journal) as db:
        _check_journal(db)
        return _status(db)


def _fetch_args(file_id):
    return {"url": "https://drive.google.com/file/d/" + _provider_id(file_id) + "/view",
            "download_raw_file": True, "include_base64": False}


def jobs(journal, limit=100, cursor=0):
    """A finite native handoff pass. Issuing an upload durably records uncertainty."""
    _require(type(limit) is int and 0 < limit <= 1000 and type(cursor) is int and cursor >= 0,
             "INVALID_PAGE")
    with _db(journal) as db, db:
        _check_journal(db)
        _require(_meta(db, "prepared"), "SNAPSHOT_NOT_PREPARED")
        db.execute("BEGIN IMMEDIATE")
        _ensure_manifest(db, journal)
        destination = _meta(db, "destination")
        rows = db.execute("SELECT * FROM objects WHERE seq>? AND state!='confirmed' "
                          "ORDER BY seq LIMIT ?", (cursor, limit + 1)).fetchall()
        result = []
        for row in rows[:limit]:
            state = row["state"]
            job = {"object_id": row["object_id"], "cursor": row["seq"]}
            if state == "pending_upload":
                path = _stage_object(db, row, journal)
                db.execute("UPDATE objects SET state='upload_uncertain',search_complete=0,"
                           "upload_attempts=upload_attempts+1 WHERE object_id=?", (row["object_id"],))
                job.update(action="upload", tool_name=TOOL_PREFIX + "upload_file", args={
                    "file_uri": str(path), "file_name": row["file_name"],
                    "mime_type": "application/octet-stream", "parent_folder_id": destination["folder_id"]})
            elif state == "pending_readback":
                job.update(action="readback", file_id=row["remote_file_id"],
                           tool_name=TOOL_PREFIX + "fetch", args=_fetch_args(row["remote_file_id"]))
            else:
                _require(state in ("pending_search", "upload_uncertain"), "INVALID_OBJECT_STATE")
                query = "name = '{}' and '{}' in parents and trashed = false".format(
                    row["file_name"], destination["folder_id"])
                job.update(action="search", tool_name=TOOL_PREFIX + "search", args={
                    "special_filter_query_str": query, "topn": 100})
            result.append(job)
        return {"ok": True, "operation_key": _meta(db, "operation_key"), "jobs": result,
                "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
                "pass_complete": len(rows) <= limit, "copy_state": _status(db)["copy_state"]}


def _receipt(row):
    return {"ok": True, "object_id": row["object_id"], "state": row["state"],
            "file_id": row["remote_file_id"], "sha256": row["sha256"], "bytes": row["size_bytes"]}


def _choose_candidate(db, object_id, complete=False):
    row = _object(db, object_id)
    if row["state"] == "confirmed":
        return
    if row["state"] == "pending_readback" and db.execute(
            "SELECT 1 FROM candidates WHERE object_id=? AND file_id=? AND state='pending'",
            (object_id, row["remote_file_id"])).fetchone():
        return
    candidate = db.execute("SELECT file_id FROM candidates WHERE object_id=? AND state='pending' "
                           "ORDER BY file_id LIMIT 1", (object_id,)).fetchone()
    if candidate:
        db.execute("UPDATE objects SET state='pending_readback',remote_file_id=? WHERE object_id=?",
                   (candidate[0], object_id))
    else:
        db.execute("UPDATE objects SET state=?,remote_file_id=NULL WHERE object_id=?",
                   ("pending_upload" if complete else "pending_search", object_id))


def record_search(journal, object_id, file_ids=(), complete=False):
    """Record only IDs from the exact-name query; complete excludes omitted pages."""
    file_ids = sorted({_provider_id(value) for value in file_ids})
    with _db(journal) as db, db:
        _check_journal(db)
        db.execute("BEGIN IMMEDIATE")
        row = _object(db, object_id)
        if row["state"] == "confirmed":
            return _receipt(row)
        for file_id in file_ids:
            db.execute("INSERT OR IGNORE INTO candidates VALUES (?,?,'pending')", (object_id, file_id))
        db.execute("UPDATE objects SET search_complete=? WHERE object_id=?", (int(bool(complete)), object_id))
        _choose_candidate(db, object_id, bool(complete))
        return _receipt(_object(db, object_id))


def record_upload(journal, object_id, file_id):
    file_id = _provider_id(file_id)
    with _db(journal) as db, db:
        _check_journal(db)
        db.execute("BEGIN IMMEDIATE")
        row = _object(db, object_id)
        if row["state"] == "confirmed":
            return _receipt(row)
        db.execute("INSERT OR IGNORE INTO candidates VALUES (?,?,'pending')", (object_id, file_id))
        _choose_candidate(db, object_id)
        return _receipt(_object(db, object_id))


def record_failure(journal, object_id, code="NATIVE_CALL_FAILED"):
    _require(isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code),
             "INVALID_ERROR_CODE")
    with _db(journal) as db, db:
        _check_journal(db)
        db.execute("BEGIN IMMEDIATE")
        row = _object(db, object_id)
        if row["state"] != "confirmed":
            db.execute("UPDATE objects SET last_error_code=? WHERE object_id=?", (code, object_id))
        return _receipt(_object(db, object_id))


def record_readback(journal, object_id, file_id, download):
    file_id = _provider_id(file_id)
    with _db(journal) as db, db:
        _check_journal(db)
        db.execute("BEGIN IMMEDIATE")
        row = _object(db, object_id)
        if row["state"] == "confirmed":
            return _receipt(row)
        _require(db.execute("SELECT 1 FROM candidates WHERE object_id=? AND file_id=?",
                            (object_id, file_id)).fetchone(), "READBACK_RECEIPT_NOT_RECORDED")
        expected = _stage_object(db, row, journal)
        downloaded = Path(download).resolve()
        _require(downloaded != expected.resolve(), "REMOTE_DOWNLOAD_REQUIRED")
        equal, digest, size = True, hashlib.sha256(), 0
        with expected.open("rb") as left, downloaded.open("rb") as right:
            while True:
                a, b = left.read(IO_BYTES), right.read(IO_BYTES)
                if a != b:
                    equal = False
                    break
                if not b:
                    break
                digest.update(b)
                size += len(b)
        if equal and digest.hexdigest() == row["sha256"] and size == row["size_bytes"]:
            db.execute("UPDATE candidates SET state='confirmed' WHERE object_id=? AND file_id=?",
                       (object_id, file_id))
            db.execute("UPDATE objects SET state='confirmed',remote_file_id=?,readback_sha256=?,"
                       "readback_bytes=?,last_error_code=NULL WHERE object_id=?",
                       (file_id, digest.hexdigest(), size, object_id))
            return _receipt(_object(db, object_id))
        db.execute("UPDATE candidates SET state='mismatch' WHERE object_id=? AND file_id=?",
                   (object_id, file_id))
        db.execute("UPDATE objects SET last_error_code='READBACK_BYTE_MISMATCH' WHERE object_id=?", (object_id,))
        _choose_candidate(db, object_id)
        result = _receipt(_object(db, object_id))
        result.update(ok=False, code="READBACK_BYTE_MISMATCH")
        return result


def _manifest_events(manifest, expected_manifest_sha256=None):
    """Validate the entire streaming manifest, including completeness and ordering."""
    if expected_manifest_sha256 is not None:
        _require(HASH_RE.fullmatch(expected_manifest_sha256), "INVALID_MANIFEST_DIGEST")
        _require(_hash_file(manifest)[0] == expected_manifest_sha256, "MANIFEST_DIGEST_MISMATCH")
    digest, snapshot = hashlib.sha256(), hashlib.sha256()
    header, current, records, chunks = None, None, 0, 0

    def record_complete():
        if current is not None:
            _require(current["part"] == current["chunk_count"] and
                     current["offset"] == current["ciphertext_bytes"], "INCOMPLETE_RECORD_MANIFEST")

    with Path(manifest).open("rb") as handle:
        while True:
            line = handle.readline(16 * 1024 * 1024 + 1)
            _require(bool(line), "MANIFEST_COMPLETION_MISSING")
            _require(len(line) <= 16 * 1024 * 1024 and line.endswith(b"\n"), "INVALID_MANIFEST_LINE")
            item = json.loads(line)
            _require(isinstance(item, dict), "INVALID_MANIFEST_ITEM")
            kind = item.get("type")
            if header is None:
                _require(kind == "header" and item.get("format") == MANIFEST_FORMAT,
                         "UNSUPPORTED_MANIFEST")
                for name in ("operation_key", "destination_key", "snapshot_sha256"):
                    _require(isinstance(item.get(name), str) and HASH_RE.fullmatch(item[name]),
                             "INVALID_MANIFEST_IDENTITY")
                for name in ("records_total", "chunks_total"):
                    _require(type(item.get(name)) is int and item[name] >= 0, "INVALID_MANIFEST_TOTAL")
                header = item
            elif kind == "complete":
                record_complete()
                _require(records == header["records_total"] == item.get("records_total") and
                         chunks == header["chunks_total"] == item.get("chunks_total"),
                         "MANIFEST_TOTAL_MISMATCH")
                _require(snapshot.hexdigest() == header["snapshot_sha256"], "MANIFEST_SNAPSHOT_MISMATCH")
                _require(digest.hexdigest() == item.get("content_sha256"), "MANIFEST_CONTENT_MISMATCH")
                _require(not handle.read(1), "MANIFEST_TRAILING_CONTENT")
                yield item
                return
            elif kind == "record":
                record_complete()
                metadata = item.get("metadata")
                _metadata_values(metadata)
                _require(type(item.get("ciphertext_bytes")) is int and item["ciphertext_bytes"] >= 0,
                         "INVALID_RECORD_LENGTH")
                _require(type(item.get("chunk_count")) is int and item["chunk_count"] > 0,
                         "INVALID_CHUNK_COUNT")
                _require(isinstance(item.get("ciphertext_sha256"), str) and
                         HASH_RE.fullmatch(item["ciphertext_sha256"]), "INVALID_RECORD_DIGEST")
                _require(item.get("record_id") == _record_id(metadata, item["ciphertext_sha256"],
                                                             item["ciphertext_bytes"]),
                         "MANIFEST_RECORD_MISMATCH")
                current = {"record_id": item["record_id"], "part": 0, "offset": 0,
                           "chunk_count": item["chunk_count"], "ciphertext_bytes": item["ciphertext_bytes"]}
                snapshot.update((item["record_id"] + "\n").encode("ascii"))
                records += 1
                _require(records <= header["records_total"], "MANIFEST_RECORD_OVERFLOW")
            elif kind == "chunk":
                _require(current is not None and current["part"] < current["chunk_count"],
                         "UNEXPECTED_MANIFEST_CHUNK")
                _require(item.get("record_id") == current["record_id"] and
                         type(item.get("part")) is int and item["part"] == current["part"] and
                         type(item.get("offset_bytes")) is int and item["offset_bytes"] == current["offset"],
                         "CHUNK_POSITION_MISMATCH")
                _require(type(item.get("size_bytes")) is int and item["size_bytes"] >= 0 and
                         current["offset"] + item["size_bytes"] <= current["ciphertext_bytes"],
                         "INVALID_CHUNK_LENGTH")
                _require(item["size_bytes"] > 0 or
                         (current["ciphertext_bytes"] == 0 and current["chunk_count"] == 1),
                         "INVALID_EMPTY_CHUNK")
                _require(isinstance(item.get("sha256"), str) and HASH_RE.fullmatch(item["sha256"]),
                         "INVALID_CHUNK_DIGEST")
                _require(item.get("provider") == "google_drive", "UNSUPPORTED_MANIFEST_PROVIDER")
                _provider_id(item.get("file_id"))
                expected_name = "src-{}-{}-{:08x}.bin".format(header["operation_key"],
                                                           current["record_id"], current["part"])
                _require(item.get("file_name") == expected_name, "INVALID_MANIFEST_OBJECT_NAME")
                current["part"] += 1
                current["offset"] += item["size_bytes"]
                chunks += 1
                _require(chunks <= header["chunks_total"], "MANIFEST_CHUNK_OVERFLOW")
            else:
                raise CustodyError("UNEXPECTED_MANIFEST_ITEM")
            digest.update(line)
            yield item


def restore_jobs(manifest, limit=100, cursor=0, expected_manifest_sha256=None):
    """Emit native downloads using only the remote manifest, without the journal."""
    _require(type(limit) is int and 0 < limit <= 1000 and type(cursor) is int and cursor >= 0,
             "INVALID_PAGE")
    result, position, more, header = [], 0, False, None
    for item in _manifest_events(manifest, expected_manifest_sha256):
        if item["type"] == "header":
            header = item
        elif item["type"] == "chunk":
            position += 1
            if position <= cursor:
                continue
            if len(result) == limit:
                more = True
                continue
            result.append({"cursor": position, "action": "download", "file_id": item["file_id"],
                           "file_name": item["file_name"], "sha256": item["sha256"],
                           "tool_name": TOOL_PREFIX + "fetch", "args": _fetch_args(item["file_id"])})
    return {"ok": True, "operation_key": header["operation_key"], "jobs": result,
            "next_cursor": result[-1]["cursor"] if more else None, "pass_complete": not more,
            "records_total": header["records_total"], "chunks_total": header["chunks_total"],
            "manifest_sha256": _hash_file(manifest)[0]}


def restore(manifest, downloads, output_db, expected_manifest_sha256=None):
    """Create a NEW source_records database from downloaded manifest and chunks.

    ``downloads`` is a JSON file (or mapping in the Python API) from provider file
    IDs or opaque manifest filenames to actual native-download local paths.
    Existing files, the input database and its original rows are never replaced.
    A failed restoration retains its incomplete output file for inspection.
    """
    _require(hasattr(sqlite3.Connection, "blobopen"), "SQLITE_BLOBOPEN_REQUIRED")
    manifest = Path(manifest).resolve()
    if not isinstance(downloads, dict):
        with Path(downloads).open("r", encoding="utf-8") as handle:
            downloads = json.load(handle)
    _require(isinstance(downloads, dict), "INVALID_DOWNLOAD_MAPPING")
    header = None
    # Validate the complete manifest and the actual download mapping before
    # reserving a new output filename. Ciphertext remains streamed below.
    for item in _manifest_events(manifest, expected_manifest_sha256):
        if item["type"] == "header":
            header = item
        elif item["type"] == "chunk":
            path = downloads.get(item["file_id"], downloads.get(item["file_name"]))
            _require(isinstance(path, str) and Path(path).is_file(), "REMOTE_CHUNK_DOWNLOAD_MISSING")
    manifest_hash = _hash_file(manifest)[0]
    output_db = Path(output_db).resolve()
    _require(not output_db.exists(), "RESTORE_DESTINATION_ALREADY_EXISTS")
    _private_file(output_db)
    db = sqlite3.connect(str(output_db), timeout=30)
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA temp_store=MEMORY")
    incoming_record, outgoing, cipher_digest, cipher_size = None, None, None, 0
    count, total_bytes = 0, 0

    def finish_record():
        nonlocal outgoing
        if outgoing is not None:
            outgoing.close()
            outgoing = None
            _require(cipher_size == incoming_record["ciphertext_bytes"] and
                     cipher_digest.hexdigest() == incoming_record["ciphertext_sha256"],
                     "RESTORED_CIPHERTEXT_MISMATCH")

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(SOURCE_DDL)
        for item in _manifest_events(manifest, manifest_hash):
            kind = item["type"]
            if kind == "record":
                finish_record()
                count += 1
                incoming_record, cipher_digest, cipher_size = item, hashlib.sha256(), 0
                _insert_source(db, count, _metadata_values(item["metadata"]), item["ciphertext_bytes"])
                outgoing = db.blobopen("source_records", "ciphertext", count, readonly=False)
            elif kind == "chunk":
                path = downloads.get(item["file_id"], downloads.get(item["file_name"]))
                chunk_digest, chunk_size = hashlib.sha256(), 0
                with Path(path).open("rb") as source:
                    while block := source.read(min(IO_BYTES, item["size_bytes"] - chunk_size + 1)):
                        chunk_size += len(block)
                        _require(chunk_size <= item["size_bytes"], "REMOTE_CHUNK_LENGTH_MISMATCH")
                        outgoing.write(block)
                        chunk_digest.update(block)
                        cipher_digest.update(block)
                        cipher_size += len(block)
                        total_bytes += len(block)
                _require(chunk_size == item["size_bytes"] and chunk_digest.hexdigest() == item["sha256"],
                         "REMOTE_CHUNK_DIGEST_MISMATCH")
            elif kind == "complete":
                finish_record()
        db.execute("CREATE TABLE remote_custody_restore(operation_key TEXT,manifest_sha256 TEXT,"
                   "snapshot_sha256 TEXT,records_restored INTEGER,ciphertext_bytes_restored INTEGER)")
        db.execute("INSERT INTO remote_custody_restore VALUES (?,?,?,?,?)",
                   (header["operation_key"], manifest_hash, header["snapshot_sha256"], count, total_bytes))
        db.commit()
    except BaseException:
        if outgoing is not None:
            outgoing.close()
        db.rollback()
        raise
    finally:
        db.close()
    return {"ok": True, "operation_key": header["operation_key"], "restore_state": "confirmed",
            "records_restored": count, "ciphertext_bytes_restored": total_bytes,
            "manifest_sha256": manifest_hash, "snapshot_sha256": header["snapshot_sha256"]}


ARCHIVE_FORMAT = "swarm-remote-custody-v2"
ARCHIVE_STATE_TABLES = ("checkpoints", "coverage", "coverage_projection", "runtime_state")


def _a_quote(name):
    return '"' + name.replace('"', '""') + '"'


def _a_pack(text):
    raw = text.encode("utf-8")
    compressed = zlib.compress(raw)
    return b"Z" + compressed if len(compressed) < len(raw) else b"R" + raw


def _a_unpack(value):
    return (zlib.decompress(value[1:]) if value[:1] == b"Z" else value[1:]).decode("utf-8")


def _a_unknown_capacity():
    return {"state": "unknown", "limit_bytes": None, "used_bytes": None,
            "available_bytes": None, "observed_at": None, "basis": None}


def _archive_initialize(index, destination):
    """Atomic metadata-only index bootstrap; the v1 bootstrap remains unchanged."""
    index = Path(index).resolve()
    index.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not index.exists():
        with tempfile.TemporaryDirectory(prefix=".archive-bootstrap-", dir=index.parent) as directory:
            temporary = Path(directory) / "index.sqlite3"
            _private_file(temporary)
            with _db(temporary) as db:
                db.executescript("""
                    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE objects(seq INTEGER PRIMARY KEY,object_id TEXT UNIQUE,
                        kind TEXT NOT NULL,record_seq INTEGER,part INTEGER,offset_bytes INTEGER DEFAULT 0,
                        size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,file_name TEXT NOT NULL,
                        state TEXT NOT NULL,remote_file_id TEXT,search_complete INTEGER DEFAULT 0,
                        upload_attempts INTEGER DEFAULT 0,readback_sha256 TEXT,readback_bytes INTEGER,
                        last_error_code TEXT,raw_sha256 TEXT NOT NULL,raw_bytes INTEGER NOT NULL,
                        codec TEXT NOT NULL,owner_operation TEXT);
                    CREATE INDEX archive_content ON objects(kind,raw_sha256,raw_bytes,state);
                    CREATE TABLE candidates(object_id TEXT,file_id TEXT,state TEXT,
                        PRIMARY KEY(object_id,file_id));
                    CREATE TABLE operations(seq INTEGER PRIMARY KEY,operation_key TEXT UNIQUE,
                        operation_id TEXT UNIQUE,source_identity TEXT,chunk_bytes INTEGER,
                        scope_json TEXT,snapshot_sha256 TEXT,records_total INTEGER DEFAULT 0,
                        state_rows_total INTEGER DEFAULT 0,prepared INTEGER DEFAULT 0,
                        observed_at TEXT NOT NULL);
                    CREATE TABLE record_versions(record_id TEXT PRIMARY KEY,metadata BLOB NOT NULL,
                        ciphertext_sha256 TEXT NOT NULL,ciphertext_bytes INTEGER NOT NULL);
                    CREATE TABLE operation_records(operation_key TEXT,seq INTEGER,source_rowid INTEGER,
                        record_id TEXT,PRIMARY KEY(operation_key,seq));
                    CREATE TABLE parts(operation_key TEXT,record_seq INTEGER,part INTEGER,
                        object_id TEXT,source_offset INTEGER,object_offset INTEGER,size_bytes INTEGER,
                        PRIMARY KEY(operation_key,record_seq,part));
                    CREATE INDEX archive_parts_object ON parts(object_id,operation_key,object_offset);
                    CREATE TABLE operation_objects(operation_key TEXT,object_id TEXT,reused INTEGER,
                        PRIMARY KEY(operation_key,object_id));
                    CREATE TABLE table_versions(state_id TEXT PRIMARY KEY,table_name TEXT,
                        spec BLOB NOT NULL,rows_total INTEGER NOT NULL);
                    CREATE TABLE table_rows(state_id TEXT,seq INTEGER,payload BLOB NOT NULL,
                        PRIMARY KEY(state_id,seq));
                    CREATE TABLE operation_tables(operation_key TEXT,seq INTEGER,state_id TEXT,
                        PRIMARY KEY(operation_key,seq));
                """)
                with db:
                    # Shared receipt transitions use v1's stable object columns.
                    _set_meta(db, "version", VERSION)
                    _set_meta(db, "archive_version", 2)
                    _set_meta(db, "destination", destination)
                    _set_meta(db, "destination_key", _digest(destination))
                    _set_meta(db, "capacity", _a_unknown_capacity())
                    _set_meta(db, "staging_object", None)
            try:
                os.link(temporary, index)
            except FileExistsError:
                pass
    with _db(index) as db:
        _a_check(db)
        _require(_meta(db, "destination") == destination, "ARCHIVE_DESTINATION_CHANGED")
    return index


def _a_check(db):
    _check_journal(db)
    _require(_meta(db, "archive_version") == 2, "UNSUPPORTED_ARCHIVE_INDEX")


def _a_operation(db, operation_id):
    row = db.execute("SELECT * FROM operations WHERE operation_id=? OR operation_key=?",
                     (operation_id, operation_id)).fetchone()
    _require(row is not None, "ARCHIVE_OPERATION_NOT_FOUND")
    return row


def _a_object_id(db, raw_hash, raw_bytes, codec, stored_hash, kind="chunk", owner=None):
    return _digest({"destination_key": _meta(db, "destination_key"), "kind": kind,
                    "raw_sha256": raw_hash, "raw_bytes": raw_bytes, "codec": codec,
                    "sha256": stored_hash, "operation": owner})


def _a_encode(blocks, codec):
    compressor = zlib.compressobj(6, zlib.DEFLATED, 31) if codec == "gzip" else None
    for block in blocks:
        value = compressor.compress(block) if compressor else block
        if value:
            yield value
    if compressor:
        yield compressor.flush()


def _a_descriptor(blocks):
    raw_hash, stored_hash, raw_size, stored_size = hashlib.sha256(), hashlib.sha256(), 0, 0
    compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
    for block in blocks:
        raw_hash.update(block)
        raw_size += len(block)
        compressed = compressor.compress(block)
        stored_hash.update(compressed)
        stored_size += len(compressed)
    last = compressor.flush()
    stored_hash.update(last)
    stored_size += len(last)
    if stored_size < raw_size:
        return raw_hash.hexdigest(), raw_size, "gzip", stored_hash.hexdigest(), stored_size
    return raw_hash.hexdigest(), raw_size, "raw", raw_hash.hexdigest(), raw_size


def _a_add_chunk(db, raw):
    raw_hash, raw_size = hashlib.sha256(raw).hexdigest(), len(raw)
    row = db.execute("SELECT * FROM objects WHERE kind='chunk' AND raw_sha256=? AND raw_bytes=? "
                     "ORDER BY (state='confirmed') DESC,size_bytes,seq LIMIT 1", (raw_hash, raw_size)).fetchone()
    if row:
        return row
    raw_hash, raw_size, codec, stored_hash, stored_size = _a_descriptor((raw,))
    object_id = _a_object_id(db, raw_hash, raw_size, codec, stored_hash)
    name = "src2-{}-{}.{}".format(raw_hash, stored_hash, "gz" if codec == "gzip" else "bin")
    db.execute("INSERT INTO objects(object_id,kind,size_bytes,sha256,file_name,state,raw_sha256,raw_bytes,codec) "
               "VALUES (?,'chunk',?,?,?,'pending_search',?,?,?)",
               (object_id, stored_size, stored_hash, name, raw_hash, raw_size, codec))
    return _object(db, object_id)


def _a_table_spec(source, name):
    definition = source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    _require(definition and definition[0], "SOURCE_STATE_TABLE_MISSING")
    columns = source.execute("PRAGMA table_xinfo(" + _a_quote(name) + ")").fetchall()
    _require(all(not row[6] for row in columns), "UNSUPPORTED_GENERATED_STATE_COLUMN")
    names = [row[1] for row in columns]
    rowid_alias = None
    for alias in ("_rowid_", "rowid", "oid"):
        if alias not in names:
            try:
                source.execute("SELECT " + alias + " FROM " + _a_quote(name) + " LIMIT 0")
                rowid_alias = alias
                break
            except sqlite3.OperationalError:
                pass
    extra = [{"type": row[0], "name": row[1], "sql": row[2]} for row in source.execute(
        "SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') "
        "AND sql IS NOT NULL ORDER BY type,name", (name,))]
    return {"name": name, "sql": definition[0], "columns": names, "rowid_alias": rowid_alias,
            "column_definitions": [{"name": row[1], "type": row[2], "not_null": bool(row[3]),
                                    "default_sql": row[4], "primary_key_order": row[5]} for row in columns],
            "primary_key": [row[1] for row in sorted(columns, key=lambda x: x[5]) if row[5]],
            "extra_schema": extra}


def _a_table_rows(source, spec):
    names = ",".join(_a_quote(name) for name in spec["columns"])
    alias = spec["rowid_alias"]
    order = alias or ",".join(_a_quote(name) for name in (spec["primary_key"] or spec["columns"]))
    query = "SELECT " + (alias + "," if alias else "") + names + " FROM " + _a_quote(spec["name"]) + " ORDER BY " + order
    for row in source.execute(query):
        yield {"rowid": row[0] if alias else None,
               "values": [_typed(value) for value in (row[1:] if alias else row)]}


def archive_prepare(source_db, index, operation_id, account_ref, folder_id,
                    chunk_bytes=4 * 1024 * 1024, state_tables=()):
    """Capture exact metadata/hashes in one read transaction, without copying ciphertext."""
    _require(hasattr(sqlite3.Connection, "blobopen"), "SQLITE_BLOBOPEN_REQUIRED")
    _require(operation_id and account_ref, "ARCHIVE_BINDING_REQUIRED")
    _require(type(chunk_bytes) is int and 0 < chunk_bytes <= 64 * 1024 * 1024, "INVALID_CHUNK_BYTES")
    source_path = Path(source_db).resolve()
    _require(source_path.is_file(), "SOURCE_DATABASE_NOT_FOUND")
    _require(source_path != Path(index).resolve(), "SOURCE_JOURNAL_COLLISION")
    stat = source_path.stat()
    identity = {"path": str(source_path), "device": stat.st_dev, "inode": stat.st_ino}
    destination = {"provider": "google_drive", "account_ref": account_ref, "folder_id": _provider_id(folder_id)}
    index = _archive_initialize(index, destination)
    explicit = sorted(set(state_tables))
    operation_key = _digest({"operation_id": operation_id, "destination_key": _digest(destination)})
    with _db(index) as db, db:
        _a_check(db)
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if existing:
            _require(existing["source_identity"] == _json(identity) and existing["chunk_bytes"] == chunk_bytes and
                     json.loads(existing["scope_json"])["explicit_tables"] == explicit,
                     "OPERATION_INPUT_OR_DESTINATION_CHANGED")
            _require(existing["prepared"], "ARCHIVE_SNAPSHOT_INCOMPLETE")
            return _a_status(db, existing, index)
        source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=30)
        try:
            source.execute("PRAGMA busy_timeout=30000")
            source.execute("BEGIN")
            _require([row[1] for row in source.execute("PRAGMA table_info(source_records)")] == list(COLUMNS),
                     "SOURCE_SCHEMA_MISMATCH")
            all_tables = sorted(row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
            selected = sorted(set(explicit) | {name for name in all_tables if name in ARCHIVE_STATE_TABLES or
                                              any(term in name.lower() for term in ("cursor", "checkpoint", "coverage"))})
            _require("source_records" not in explicit, "SOURCE_TABLE_ALREADY_INCLUDED")
            _require(set(selected).issubset(all_tables), "SOURCE_STATE_TABLE_MISSING")
            scope = {"explicit_tables": explicit, "included_tables": ["source_records"] + selected,
                     "absent_default_tables": sorted(set(ARCHIVE_STATE_TABLES) - set(all_tables)),
                     "other_tables": sorted(set(all_tables) - set(selected) - {"source_records"}),
                     "internal_tables_not_copied": sorted(row[0] for row in source.execute(
                         "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sqlite_%'"))}
            observed = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            db.execute("INSERT INTO operations(operation_key,operation_id,source_identity,chunk_bytes,scope_json,observed_at) "
                       "VALUES (?,?,?,?,?,?)", (operation_key, operation_id, _json(identity), chunk_bytes, _json(scope), observed))
            snapshot, record_count, state_count = hashlib.sha256(), 0, 0
            raw_buffer, buffered_parts = bytearray(), []

            def flush_chunk():
                if not buffered_parts:
                    return
                obj = _a_add_chunk(db, raw_buffer)
                db.execute("INSERT OR IGNORE INTO operation_objects VALUES (?,?,?)",
                           (operation_key, obj["object_id"], int(obj["state"] == "confirmed")))
                for sequence, part, source_offset, object_offset, size in buffered_parts:
                    db.execute("INSERT INTO parts VALUES (?,?,?,?,?,?,?)", (operation_key, sequence, part,
                               obj["object_id"], source_offset, object_offset, size))
                raw_buffer.clear()
                buffered_parts.clear()

            query = "SELECT rowid," + ",".join(META_COLUMNS) + ",length(ciphertext),typeof(ciphertext) FROM source_records ORDER BY rowid"
            for row in source.execute(query):
                _require(row[-1] == "blob", "INVALID_CIPHERTEXT_TYPE")
                rowid, size = row[0], row[-2]
                metadata = {name: _typed(value) for name, value in zip(META_COLUMNS, row[1:-2])}
                _metadata_values(metadata)
                record_count += 1
                cipher_digest, offset, part = hashlib.sha256(), 0, 0
                with source.blobopen("source_records", "ciphertext", rowid, readonly=True) as blob:
                    while offset < size or part == 0:
                        length = min(chunk_bytes - len(raw_buffer), size - offset)
                        buffered_parts.append((record_count, part, offset, len(raw_buffer), length))
                        remaining = length
                        while remaining:
                            block = blob.read(min(IO_BYTES, remaining))
                            _require(bool(block), "SOURCE_CIPHERTEXT_TRUNCATED")
                            cipher_digest.update(block)
                            raw_buffer.extend(block)
                            remaining -= len(block)
                        offset += length
                        part += 1
                        if len(raw_buffer) == chunk_bytes:
                            flush_chunk()
                record_id = _record_id(metadata, cipher_digest.hexdigest(), size)
                db.execute("INSERT OR IGNORE INTO record_versions VALUES (?,?,?,?)",
                           (record_id, _a_pack(_json(metadata)), cipher_digest.hexdigest(), size))
                db.execute("INSERT INTO operation_records VALUES (?,?,?,?)",
                           (operation_key, record_count, rowid, record_id))
                snapshot.update((_json({"record_id": record_id, "rowid": rowid}) + "\n").encode("utf-8"))
            flush_chunk()
            for sequence, name in enumerate(selected, 1):
                spec = _a_table_spec(source, name)
                table_hash = hashlib.sha256((_json(spec) + "\n").encode("utf-8"))
                rows_total = 0
                for item in _a_table_rows(source, spec):
                    table_hash.update((_json(item) + "\n").encode("utf-8"))
                    rows_total += 1
                state_id = table_hash.hexdigest()
                if not db.execute("SELECT 1 FROM table_versions WHERE state_id=?", (state_id,)).fetchone():
                    db.execute("INSERT INTO table_versions VALUES (?,?,?,?)",
                               (state_id, name, _a_pack(_json(spec)), rows_total))
                    for row_seq, item in enumerate(_a_table_rows(source, spec), 1):
                        db.execute("INSERT INTO table_rows VALUES (?,?,?)", (state_id, row_seq, _a_pack(_json(item))))
                db.execute("INSERT INTO operation_tables VALUES (?,?,?)", (operation_key, sequence, state_id))
                snapshot.update((_json({"table": name, "state_id": state_id}) + "\n").encode("utf-8"))
                state_count += rows_total
            db.execute("UPDATE operations SET snapshot_sha256=?,records_total=?,state_rows_total=?,prepared=1 "
                       "WHERE operation_key=?", (snapshot.hexdigest(), record_count, state_count, operation_key))
        finally:
            source.close()
        return _a_status(db, _a_operation(db, operation_id), index)


def archive_import_v1(index, journal):
    """Reuse accepted v1 chunk readbacks as metadata; do not recopy their ciphertext."""
    _require(Path(index).resolve() != Path(journal).resolve(), "ARCHIVE_V1_INDEX_COLLISION")
    with _db(journal) as old:
        _check_journal(old)
        _require(_status(old)["copy_state"] == "confirmed", "V1_MANIFEST_NOT_CONFIRMED")
        index = _archive_initialize(index, _meta(old, "destination"))
        with _db(index) as db, db:
            _a_check(db)
            db.execute("BEGIN IMMEDIATE")
            imported, reused = 0, 0
            for row in old.execute("SELECT * FROM objects WHERE kind='chunk' AND state='confirmed' ORDER BY seq"):
                _require(row["readback_sha256"] == row["sha256"] and row["readback_bytes"] == row["size_bytes"],
                         "V1_READBACK_INCOMPLETE")
                object_id = _a_object_id(db, row["sha256"], row["size_bytes"], "raw", row["sha256"])
                existing = db.execute("SELECT * FROM objects WHERE object_id=?", (object_id,)).fetchone()
                if existing and existing["state"] == "confirmed":
                    reused += 1
                    continue
                if existing:
                    db.execute("UPDATE objects SET state='confirmed',remote_file_id=?,readback_sha256=?,readback_bytes=? "
                               "WHERE object_id=?", (row["remote_file_id"], row["sha256"], row["size_bytes"], object_id))
                else:
                    db.execute("INSERT INTO objects(object_id,kind,size_bytes,sha256,file_name,state,remote_file_id,"
                               "readback_sha256,readback_bytes,raw_sha256,raw_bytes,codec) "
                               "VALUES (?,'chunk',?,?,?,'confirmed',?,?,?,?,?,'raw')",
                               (object_id, row["size_bytes"], row["sha256"], row["file_name"], row["remote_file_id"],
                                row["sha256"], row["size_bytes"], row["sha256"], row["size_bytes"]))
                db.execute("INSERT OR REPLACE INTO candidates VALUES (?,?,'confirmed')", (object_id, row["remote_file_id"]))
                imported += 1
            return {"ok": True, "chunks_imported": imported, "chunks_already_confirmed": reused,
                    "ciphertext_bytes_copied_locally": 0, "destination_key": _meta(db, "destination_key")}


def _a_status(db, operation, index):
    key = operation["operation_key"]
    rows = db.execute("SELECT o.*,m.reused FROM objects o JOIN operation_objects m USING(object_id) "
                      "WHERE m.operation_key=?", (key,)).fetchall()
    chunks = [row for row in rows if row["kind"] == "chunk"]
    manifests = [row for row in rows if row["kind"] == "manifest"]
    manifest = manifests[0] if manifests else None
    complete = bool(manifest and manifest["state"] == "confirmed")
    record_bytes = db.execute("SELECT COALESCE(SUM(v.ciphertext_bytes),0) FROM record_versions v "
                             "JOIN operation_records r USING(record_id) WHERE r.operation_key=?", (key,)).fetchone()[0]
    cipher_records = db.execute("SELECT COUNT(*) FROM operation_records r WHERE r.operation_key=? AND NOT EXISTS "
                                "(SELECT 1 FROM parts p JOIN objects o USING(object_id) WHERE p.operation_key=r.operation_key "
                                "AND p.record_seq=r.seq AND o.state!='confirmed')", (key,)).fetchone()[0]
    states = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    return {"ok": True, "operation_key": key, "snapshot_complete": bool(operation["prepared"]),
            "snapshot_sha256": operation["snapshot_sha256"], "observed_at": operation["observed_at"],
            "copy_state": "confirmed" if complete else "pending", "records_total": operation["records_total"],
            "records_confirmed": operation["records_total"] if complete else 0,
            "records_ciphertext_confirmed": cipher_records, "state_rows_total": operation["state_rows_total"],
            "source_scope": json.loads(operation["scope_json"]), "objects_total": len(rows),
            "object_states": states, "unique_chunks": len(chunks),
            "reused_chunks": sum(bool(row["reused"]) for row in chunks),
            "ciphertext_logical_bytes": record_bytes, "chunk_raw_bytes": sum(row["raw_bytes"] for row in chunks),
            "chunk_stored_bytes": sum(row["size_bytes"] for row in chunks),
            "pending_stored_bytes": sum(row["size_bytes"] for row in rows if row["state"] != "confirmed"),
            "confirmed_stored_bytes": sum(row["size_bytes"] for row in rows if row["state"] == "confirmed"),
            "ciphertext_bytes_in_index": 0,
            "index_bytes": db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0],
            "provider_corpus_complete": None,
            "capacity": _meta(db, "capacity"), "manifest": None if not manifest else {
                "object_id": manifest["object_id"], "state": manifest["state"], "file_id": manifest["remote_file_id"],
                "sha256": manifest["sha256"], "raw_sha256": manifest["raw_sha256"], "codec": manifest["codec"],
                "raw_bytes": manifest["raw_bytes"], "stored_bytes": manifest["size_bytes"],
                "tool_name": TOOL_PREFIX + "fetch",
                "args": _fetch_args(manifest["remote_file_id"]) if manifest["remote_file_id"] else None}}


def archive_status(index, operation_id):
    with _db(index) as db:
        _a_check(db)
        return _a_status(db, _a_operation(db, operation_id), index)


def archive_capacity(index, receipt):
    with Path(receipt).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    result = _a_unknown_capacity()
    _require(isinstance(value, dict), "INVALID_CAPACITY_OBSERVATION")
    for name in ("limit_bytes", "used_bytes", "available_bytes"):
        number = value.get(name)
        _require(number is None or (type(number) is int and number >= 0), "INVALID_CAPACITY_OBSERVATION")
        result[name] = number
    if any(result[name] is not None for name in ("limit_bytes", "used_bytes", "available_bytes")):
        _require(isinstance(value.get("observed_at"), str) and isinstance(value.get("basis"), str),
                 "CAPACITY_OBSERVATION_SOURCE_REQUIRED")
        result.update(state="observed", observed_at=value["observed_at"], basis=value["basis"])
    with _db(index) as db, db:
        _a_check(db)
        _set_meta(db, "capacity", result)
    return {"ok": True, "capacity": result}


def _a_manifest_blocks(db, operation):
    key, digest = operation["operation_key"], hashlib.sha256()
    header = {"type": "header", "format": ARCHIVE_FORMAT, "operation_key": key,
              "operation_id": operation["operation_id"], "destination_key": _meta(db, "destination_key"),
              "snapshot_sha256": operation["snapshot_sha256"], "records_total": operation["records_total"],
              "state_rows_total": operation["state_rows_total"], "chunk_bytes": operation["chunk_bytes"],
              "scope": json.loads(operation["scope_json"]), "observed_at": operation["observed_at"],
              "tables_total": db.execute("SELECT COUNT(*) FROM operation_tables WHERE operation_key=?", (key,)).fetchone()[0],
              "segments_total": db.execute("SELECT COUNT(*) FROM parts WHERE operation_key=?", (key,)).fetchone()[0]}

    def line(value):
        block = (_json(value) + "\n").encode("utf-8")
        digest.update(block)
        return block

    yield line(header)
    for record in db.execute("SELECT r.*,v.metadata,v.ciphertext_sha256,v.ciphertext_bytes "
                             "FROM operation_records r JOIN record_versions v USING(record_id) "
                             "WHERE operation_key=? ORDER BY r.seq", (key,)):
        count = db.execute("SELECT COUNT(*) FROM parts WHERE operation_key=? AND record_seq=?", (key, record["seq"])).fetchone()[0]
        yield line({"type": "record", "record_id": record["record_id"], "source_rowid": record["source_rowid"],
                    "metadata": json.loads(_a_unpack(record["metadata"])), "ciphertext_bytes": record["ciphertext_bytes"],
                    "ciphertext_sha256": record["ciphertext_sha256"], "segment_count": count})
        for part in db.execute("SELECT p.*,o.raw_sha256,o.raw_bytes,o.sha256,o.size_bytes AS stored_bytes,"
                               "o.codec,o.file_name,o.remote_file_id,o.state FROM parts p JOIN objects o USING(object_id) "
                               "WHERE p.operation_key=? AND p.record_seq=? ORDER BY p.part", (key, record["seq"])):
            _require(part["state"] == "confirmed", "CHUNK_NOT_CONFIRMED")
            yield line({"type": "segment", "record_id": record["record_id"], "part": part["part"],
                        "source_offset": part["source_offset"], "object_offset": part["object_offset"],
                        "segment_bytes": part["size_bytes"], "object_id": part["object_id"],
                        "raw_sha256": part["raw_sha256"], "raw_bytes": part["raw_bytes"],
                        "sha256": part["sha256"], "stored_bytes": part["stored_bytes"], "codec": part["codec"],
                        "provider": "google_drive", "file_name": part["file_name"], "file_id": part["remote_file_id"]})
    for table in db.execute("SELECT v.* FROM operation_tables t JOIN table_versions v USING(state_id) "
                            "WHERE t.operation_key=? ORDER BY t.seq", (key,)):
        yield line({"type": "table", "state_id": table["state_id"], "table_name": table["table_name"],
                    "spec": json.loads(_a_unpack(table["spec"])), "rows_total": table["rows_total"]})
        for row in db.execute("SELECT seq,payload FROM table_rows WHERE state_id=? ORDER BY seq", (table["state_id"],)):
            yield line({"type": "state_row", "state_id": table["state_id"], "seq": row["seq"],
                        "row": json.loads(_a_unpack(row["payload"]))})
    yield (_json({"type": "complete", "content_sha256": digest.hexdigest(),
                  "records_total": header["records_total"], "state_rows_total": header["state_rows_total"],
                  "tables_total": header["tables_total"], "segments_total": header["segments_total"]}) + "\n").encode("utf-8")


def _a_ensure_manifest(db, operation):
    key = operation["operation_key"]
    if db.execute("SELECT 1 FROM objects WHERE kind='manifest' AND owner_operation=?", (key,)).fetchone():
        return
    if db.execute("SELECT 1 FROM objects o JOIN operation_objects m USING(object_id) "
                  "WHERE m.operation_key=? AND o.state!='confirmed'", (key,)).fetchone():
        return
    raw_hash, raw_size, codec, stored_hash, stored_size = _a_descriptor(_a_manifest_blocks(db, operation))
    object_id = _a_object_id(db, raw_hash, raw_size, codec, stored_hash, "manifest", key)
    name = "src2-manifest-{}-{}.{}".format(key, stored_hash, "jsonl.gz" if codec == "gzip" else "jsonl")
    db.execute("INSERT INTO objects(object_id,kind,size_bytes,sha256,file_name,state,raw_sha256,raw_bytes,codec,owner_operation) "
               "VALUES (?,'manifest',?,?,?,'pending_search',?,?,?,?)",
               (object_id, stored_size, stored_hash, name, raw_hash, raw_size, codec, key))
    db.execute("INSERT INTO operation_objects VALUES (?,?,0)", (key, object_id))


def _a_raw_chunk(db, obj, operation_key):
    operation = _a_operation(db, operation_key)
    identity = json.loads(operation["source_identity"])
    _require(isinstance(identity, dict) and identity.get("path"), "ORIGINAL_SOURCE_ROUTE_MISSING")
    path = Path(identity["path"])
    _require(path.is_file(), "ORIGINAL_SOURCE_ROUTE_MISSING")
    stat = path.stat()
    _require(stat.st_dev == identity["device"] and stat.st_ino == identity["inode"], "SOURCE_SNAPSHOT_CHANGED")
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    data = bytearray()
    try:
        source.execute("BEGIN")
        parts = db.execute("SELECT p.*,r.source_rowid,v.metadata,v.ciphertext_bytes "
                           "FROM parts p JOIN operation_records r ON r.operation_key=p.operation_key AND r.seq=p.record_seq "
                           "JOIN record_versions v USING(record_id) WHERE p.object_id=? AND p.operation_key=? "
                           "ORDER BY p.record_seq,p.part", (obj["object_id"], operation_key))
        for part in parts:
            if part["object_offset"] != len(data):
                continue
            row = source.execute("SELECT " + ",".join(META_COLUMNS) + ",length(ciphertext) "
                                 "FROM source_records WHERE rowid=?", (part["source_rowid"],)).fetchone()
            expected = json.loads(_a_unpack(part["metadata"]))
            _require(row is not None and row[-1] == part["ciphertext_bytes"] and
                     {name: _typed(value) for name, value in zip(META_COLUMNS, row[:-1])} == expected,
                     "SOURCE_SNAPSHOT_CHANGED")
            with source.blobopen("source_records", "ciphertext", part["source_rowid"], readonly=True) as blob:
                blob.seek(part["source_offset"])
                remaining = part["size_bytes"]
                while remaining:
                    block = blob.read(min(IO_BYTES, remaining))
                    _require(bool(block), "SOURCE_CIPHERTEXT_TRUNCATED")
                    data.extend(block)
                    remaining -= len(block)
            if len(data) == obj["raw_bytes"]:
                break
    finally:
        source.close()
    _require(len(data) == obj["raw_bytes"] and hashlib.sha256(data).hexdigest() == obj["raw_sha256"],
             "SOURCE_SNAPSHOT_CHANGED")
    return data


def _a_stage(db, index, obj, operation_key):
    path = _stage_path(index, "archive-upload.bin")
    active = _meta(db, "staging_object")
    if active == obj["object_id"] and path.is_file():
        _require(_hash_file(path) == (obj["sha256"], obj["size_bytes"]), "STAGED_OBJECT_MISMATCH")
        return path
    if active is not None:
        _require(_object(db, active)["state"] == "confirmed", "ARCHIVE_UPLOAD_STILL_PENDING")
    raw = (_a_manifest_blocks(db, _a_operation(db, obj["owner_operation"])) if obj["kind"] == "manifest"
           else (_a_raw_chunk(db, obj, operation_key),))
    # Only a confirmed, derived staging copy can be replaced. Original source
    # files and all uncertain staging bytes remain untouched.
    fd, temporary = tempfile.mkstemp(prefix=".archive-stage-", dir=path.parent)
    digest, size = hashlib.sha256(), 0
    with os.fdopen(fd, "wb") as handle:
        for block in _a_encode(raw, obj["codec"]):
            handle.write(block)
            digest.update(block)
            size += len(block)
        handle.flush()
        os.fsync(handle.fileno())
    _require((digest.hexdigest(), size) == (obj["sha256"], obj["size_bytes"]), "STAGED_OBJECT_MISMATCH")
    os.replace(temporary, path)
    _set_meta(db, "staging_object", obj["object_id"])
    return path


def archive_jobs(index, operation_id, limit=100, cursor=0):
    _require(type(limit) is int and 0 < limit <= 1000 and type(cursor) is int and cursor >= 0, "INVALID_PAGE")
    with _db(index) as db, db:
        _a_check(db)
        db.execute("BEGIN IMMEDIATE")
        operation = _a_operation(db, operation_id)
        _require(operation["prepared"], "ARCHIVE_SNAPSHOT_INCOMPLETE")
        _a_ensure_manifest(db, operation)
        rows = db.execute("SELECT o.* FROM objects o JOIN operation_objects m USING(object_id) "
                          "WHERE m.operation_key=? AND o.seq>? AND o.state!='confirmed' ORDER BY o.seq LIMIT ?",
                          (operation["operation_key"], cursor, limit + 1)).fetchall()
        active = _meta(db, "staging_object")
        busy = bool(active and _object(db, active)["state"] != "confirmed")
        result, deferred, errors = [], 0, []
        for row in rows[:limit]:
            job = {"object_id": row["object_id"], "cursor": row["seq"]}
            if row["state"] == "pending_upload":
                if busy and active != row["object_id"]:
                    deferred += 1
                    continue
                try:
                    path = _a_stage(db, index, row, operation["operation_key"])
                except (CustodyError, OSError, sqlite3.Error) as exc:
                    code = exc.code if isinstance(exc, CustodyError) else "SOURCE_OR_STAGING_UNAVAILABLE"
                    db.execute("UPDATE objects SET last_error_code=? WHERE object_id=?", (code, row["object_id"]))
                    errors.append({"object_id": row["object_id"], "code": code})
                    continue
                db.execute("UPDATE objects SET state='upload_uncertain',search_complete=0,upload_attempts=upload_attempts+1 "
                           "WHERE object_id=?", (row["object_id"],))
                job.update(action="upload", tool_name=TOOL_PREFIX + "upload_file", args={
                    "file_uri": str(path), "file_name": row["file_name"], "mime_type": "application/octet-stream",
                    "parent_folder_id": _meta(db, "destination")["folder_id"]})
                busy = True
            elif row["state"] == "pending_readback":
                job.update(action="readback", file_id=row["remote_file_id"],
                           tool_name=TOOL_PREFIX + "fetch", args=_fetch_args(row["remote_file_id"]))
            else:
                _require(row["state"] in ("pending_search", "upload_uncertain"), "INVALID_OBJECT_STATE")
                _require(re.fullmatch(r"[A-Za-z0-9._-]{1,255}", row["file_name"]), "INVALID_OBJECT_NAME")
                query = "name = '{}' and '{}' in parents and trashed = false".format(row["file_name"], _meta(db, "destination")["folder_id"])
                job.update(action="search", tool_name=TOOL_PREFIX + "search",
                           args={"special_filter_query_str": query, "topn": 100})
            result.append(job)
        more = len(rows) > limit
        return {"ok": not errors, "operation_key": operation["operation_key"], "jobs": result,
                "next_cursor": 0 if deferred or errors else (rows[limit - 1]["seq"] if more else None),
                "pass_complete": not (more or deferred or errors), "deferred_uploads": deferred,
                "errors": errors, "copy_state": _a_status(db, operation, index)["copy_state"]}


def archive_record_search(index, object_id, file_ids=(), complete=False):
    with _db(index) as db:
        _a_check(db)
    return record_search(index, object_id, file_ids, complete)


def archive_record_upload(index, object_id, file_id):
    with _db(index) as db:
        _a_check(db)
    return record_upload(index, object_id, file_id)


def archive_record_failure(index, object_id, code="NATIVE_CALL_FAILED"):
    with _db(index) as db:
        _a_check(db)
    return record_failure(index, object_id, code)


def _a_decoded_blocks(path, descriptor):
    _require(_hash_file(path) == (descriptor["sha256"], descriptor["stored_bytes"]), "REMOTE_CHUNK_DIGEST_MISMATCH")
    opener = gzip.open if descriptor["codec"] == "gzip" else open
    digest, size = hashlib.sha256(), 0
    with opener(path, "rb") as handle:
        while block := handle.read(min(IO_BYTES, descriptor["raw_bytes"] - size + 1)):
            size += len(block)
            _require(size <= descriptor["raw_bytes"], "REMOTE_CHUNK_LENGTH_MISMATCH")
            digest.update(block)
            yield block
    _require(size == descriptor["raw_bytes"] and digest.hexdigest() == descriptor["raw_sha256"], "REMOTE_CHUNK_DIGEST_MISMATCH")


def archive_record_readback(index, object_id, file_id, download):
    file_id, downloaded = _provider_id(file_id), Path(download).resolve()
    with _db(index) as db, db:
        _a_check(db)
        db.execute("BEGIN IMMEDIATE")
        row = _object(db, object_id)
        if row["state"] == "confirmed":
            return _receipt(row)
        _require(db.execute("SELECT 1 FROM candidates WHERE object_id=? AND file_id=?", (object_id, file_id)).fetchone(),
                 "READBACK_RECEIPT_NOT_RECORDED")
        try:
            descriptor = dict(row)
            descriptor["stored_bytes"] = row["size_bytes"]
            for _ in _a_decoded_blocks(downloaded, descriptor):
                pass
            staged = _stage_path(index, "archive-upload.bin")
            if _meta(db, "staging_object") == object_id and staged.is_file():
                _require(not os.path.samefile(staged, downloaded), "REMOTE_DOWNLOAD_REQUIRED")
                with staged.open("rb") as a, downloaded.open("rb") as b:
                    while True:
                        left, right = a.read(IO_BYTES), b.read(IO_BYTES)
                        _require(left == right, "READBACK_BYTE_MISMATCH")
                        if not left:
                            break
        except (CustodyError, OSError, EOFError, zlib.error) as exc:
            code = exc.code if isinstance(exc, CustodyError) else "READBACK_UNAVAILABLE"
            db.execute("UPDATE objects SET last_error_code=? WHERE object_id=?", (code, object_id))
            if code in ("REMOTE_CHUNK_DIGEST_MISMATCH", "REMOTE_CHUNK_LENGTH_MISMATCH", "READBACK_BYTE_MISMATCH"):
                db.execute("UPDATE candidates SET state='mismatch' WHERE object_id=? AND file_id=?", (object_id, file_id))
                _choose_candidate(db, object_id)
            result = _receipt(_object(db, object_id))
            result.update(ok=False, code=code)
            return result
        db.execute("UPDATE candidates SET state='confirmed' WHERE object_id=? AND file_id=?", (object_id, file_id))
        db.execute("UPDATE objects SET state='confirmed',remote_file_id=?,readback_sha256=?,readback_bytes=?,last_error_code=NULL "
                   "WHERE object_id=?", (file_id, row["sha256"], row["size_bytes"], object_id))
        return _receipt(_object(db, object_id))


@contextmanager
def _a_manifest_stream(path):
    with Path(path).open("rb") as probe:
        compressed = probe.read(2) == b"\x1f\x8b"
    with (gzip.open(path, "rb") if compressed else Path(path).open("rb")) as handle:
        yield handle


def _a_manifest_events(manifest, expected_manifest_sha256=None):
    if expected_manifest_sha256 is not None:
        _require(isinstance(expected_manifest_sha256, str) and HASH_RE.fullmatch(expected_manifest_sha256),
                 "INVALID_MANIFEST_DIGEST")
        _require(_hash_file(manifest)[0] == expected_manifest_sha256, "MANIFEST_DIGEST_MISMATCH")
    digest, snapshot = hashlib.sha256(), hashlib.sha256()
    header, record, table = None, None, None
    records, segments, tables, state_rows = 0, 0, 0, 0
    table_names = set()

    def finish_record():
        if record:
            _require(record["part"] == record["segment_count"] and record["offset"] == record["ciphertext_bytes"],
                     "INCOMPLETE_RECORD_MANIFEST")

    def finish_table():
        if table:
            _require(table["rows"] == table["rows_total"] and table["digest"].hexdigest() == table["state_id"],
                     "STATE_TABLE_DIGEST_MISMATCH")
            snapshot.update((_json({"table": table["name"], "state_id": table["state_id"]}) + "\n").encode("utf-8"))

    with _a_manifest_stream(manifest) as handle:
        while True:
            line = handle.readline(16 * 1024 * 1024 + 1)
            _require(bool(line), "MANIFEST_COMPLETION_MISSING")
            _require(len(line) <= 16 * 1024 * 1024 and line.endswith(b"\n"), "INVALID_MANIFEST_LINE")
            item = json.loads(line)
            _require(isinstance(item, dict), "INVALID_MANIFEST_ITEM")
            kind = item.get("type")
            if header is None:
                _require(kind == "header" and item.get("format") == ARCHIVE_FORMAT, "UNSUPPORTED_MANIFEST")
                for name in ("operation_key", "destination_key", "snapshot_sha256"):
                    _require(isinstance(item.get(name), str) and HASH_RE.fullmatch(item[name]), "INVALID_MANIFEST_IDENTITY")
                for name in ("records_total", "segments_total", "tables_total", "state_rows_total"):
                    _require(type(item.get(name)) is int and item[name] >= 0, "INVALID_MANIFEST_TOTAL")
                _require(type(item.get("chunk_bytes")) is int and 0 < item["chunk_bytes"] <= 64 * 1024 * 1024,
                         "INVALID_CHUNK_BYTES")
                _require(isinstance(item.get("operation_id"), str) and isinstance(item.get("scope"), dict),
                         "INVALID_ARCHIVE_SCOPE")
                header = item
            elif kind == "record":
                _require(table is None, "UNEXPECTED_MANIFEST_RECORD")
                finish_record()
                _metadata_values(item.get("metadata"))
                _require(type(item.get("source_rowid")) is int and type(item.get("ciphertext_bytes")) is int and
                         item["ciphertext_bytes"] >= 0 and type(item.get("segment_count")) is int and item["segment_count"] > 0,
                         "INVALID_RECORD_LENGTH")
                _require(isinstance(item.get("ciphertext_sha256"), str) and HASH_RE.fullmatch(item["ciphertext_sha256"]),
                         "INVALID_RECORD_DIGEST")
                _require(item.get("record_id") == _record_id(item["metadata"], item["ciphertext_sha256"], item["ciphertext_bytes"]),
                         "MANIFEST_RECORD_MISMATCH")
                record = {"record_id": item["record_id"], "part": 0, "offset": 0,
                          "segment_count": item["segment_count"], "ciphertext_bytes": item["ciphertext_bytes"]}
                snapshot.update((_json({"record_id": item["record_id"], "rowid": item["source_rowid"]}) + "\n").encode("utf-8"))
                records += 1
                _require(records <= header["records_total"], "MANIFEST_RECORD_OVERFLOW")
            elif kind == "segment":
                _require(record is not None and table is None, "UNEXPECTED_MANIFEST_SEGMENT")
                _require(item.get("record_id") == record["record_id"] and type(item.get("part")) is int and
                         item["part"] == record["part"] and type(item.get("source_offset")) is int and
                         item["source_offset"] == record["offset"], "CHUNK_POSITION_MISMATCH")
                for name in ("segment_bytes", "object_offset", "raw_bytes", "stored_bytes"):
                    _require(type(item.get(name)) is int and item[name] >= 0, "INVALID_CHUNK_LENGTH")
                _require(item["raw_bytes"] <= header["chunk_bytes"] and
                         item["object_offset"] + item["segment_bytes"] <= item["raw_bytes"] and
                         record["offset"] + item["segment_bytes"] <= record["ciphertext_bytes"], "INVALID_CHUNK_LENGTH")
                _require(item["segment_bytes"] > 0 or record["ciphertext_bytes"] == 0, "INVALID_EMPTY_SEGMENT")
                for name in ("raw_sha256", "sha256", "object_id"):
                    _require(isinstance(item.get(name), str) and HASH_RE.fullmatch(item[name]), "INVALID_CHUNK_DIGEST")
                _require(item.get("codec") in ("raw", "gzip") and item.get("provider") == "google_drive", "UNSUPPORTED_CHUNK_FORMAT")
                if item["codec"] == "raw":
                    _require(item["raw_bytes"] == item["stored_bytes"] and item["raw_sha256"] == item["sha256"], "INVALID_RAW_CHUNK")
                else:
                    _require(item["stored_bytes"] < item["raw_bytes"], "INVALID_COMPRESSED_CHUNK")
                expected_id = _digest({"destination_key": header["destination_key"], "kind": "chunk",
                    "raw_sha256": item["raw_sha256"], "raw_bytes": item["raw_bytes"], "codec": item["codec"],
                    "sha256": item["sha256"], "operation": None})
                _require(expected_id == item["object_id"], "MANIFEST_OBJECT_ID_MISMATCH")
                _provider_id(item.get("file_id"))
                _require(isinstance(item.get("file_name"), str) and re.fullmatch(r"[A-Za-z0-9._-]{1,255}", item["file_name"]),
                         "INVALID_MANIFEST_OBJECT_NAME")
                record["part"] += 1
                record["offset"] += item["segment_bytes"]
                segments += 1
                _require(record["part"] <= record["segment_count"] and segments <= header["segments_total"], "MANIFEST_SEGMENT_OVERFLOW")
            elif kind == "table":
                finish_record()
                finish_table()
                name, spec = item.get("table_name"), item.get("spec")
                _require(isinstance(name, str) and name != "source_records" and name not in table_names and
                         not name.lower().startswith("sqlite_") and isinstance(spec, dict) and spec.get("name") == name,
                         "INVALID_STATE_TABLE")
                _require(isinstance(spec.get("columns"), list) and spec["columns"] and
                         len(spec["columns"]) == len(set(spec["columns"])) and
                         all(isinstance(value, str) for value in spec["columns"]), "INVALID_STATE_COLUMNS")
                _require(type(item.get("rows_total")) is int and item["rows_total"] >= 0 and
                         isinstance(item.get("state_id"), str) and HASH_RE.fullmatch(item["state_id"]), "INVALID_STATE_TABLE")
                table = {"name": name, "spec": spec, "state_id": item["state_id"], "rows_total": item["rows_total"],
                         "rows": 0, "digest": hashlib.sha256((_json(spec) + "\n").encode("utf-8"))}
                table_names.add(name)
                tables += 1
            elif kind == "state_row":
                _require(table is not None and item.get("state_id") == table["state_id"] and
                         type(item.get("seq")) is int and item["seq"] == table["rows"] + 1,
                         "INVALID_STATE_ROW_POSITION")
                row = item.get("row")
                _require(isinstance(row, dict) and set(row) == {"rowid", "values"} and
                         (row["rowid"] is None or type(row["rowid"]) is int) and isinstance(row["values"], list) and
                         len(row["values"]) == len(table["spec"]["columns"]), "INVALID_STATE_ROW")
                for value in row["values"]:
                    _untyped(value)
                table["digest"].update((_json(row) + "\n").encode("utf-8"))
                table["rows"] += 1
                state_rows += 1
                _require(table["rows"] <= table["rows_total"] and state_rows <= header["state_rows_total"], "STATE_ROW_OVERFLOW")
            elif kind == "complete":
                finish_record()
                finish_table()
                for name, value in (("records_total", records), ("segments_total", segments),
                                    ("tables_total", tables), ("state_rows_total", state_rows)):
                    _require(value == header[name] == item.get(name), "MANIFEST_TOTAL_MISMATCH")
                _require(set(header["scope"].get("included_tables", [])) == table_names | {"source_records"}, "MANIFEST_SCOPE_MISMATCH")
                _require(snapshot.hexdigest() == header["snapshot_sha256"], "MANIFEST_SNAPSHOT_MISMATCH")
                _require(digest.hexdigest() == item.get("content_sha256"), "MANIFEST_CONTENT_MISMATCH")
                _require(not handle.read(1), "MANIFEST_TRAILING_CONTENT")
                yield item
                return
            else:
                raise CustodyError("UNEXPECTED_MANIFEST_ITEM")
            digest.update(line)
            yield item


def _a_chunk_descriptor(item):
    return {name: item[name] for name in ("object_id", "raw_sha256", "raw_bytes", "sha256", "stored_bytes",
                                         "codec", "file_name", "file_id", "provider")}


def _a_scan_manifest(manifest, expected_manifest_sha256=None):
    header, objects = None, {}
    for item in _a_manifest_events(manifest, expected_manifest_sha256):
        if item["type"] == "header":
            header = item
        elif item["type"] == "segment":
            descriptor = _a_chunk_descriptor(item)
            old = objects.setdefault(item["object_id"], descriptor)
            _require(old == descriptor, "MANIFEST_CHUNK_LOCATION_CONFLICT")
    return header, objects


def archive_restore_jobs(manifest, limit=100, cursor=0, expected_manifest_sha256=None):
    _require(type(limit) is int and 0 < limit <= 1000 and type(cursor) is int and cursor >= 0, "INVALID_PAGE")
    header, objects = _a_scan_manifest(manifest, expected_manifest_sha256)
    selected = list(objects.values())[cursor:cursor + limit]
    result = [{"cursor": cursor + i, "action": "download", "object_id": item["object_id"],
               "file_id": item["file_id"], "file_name": item["file_name"], "sha256": item["sha256"],
               "tool_name": TOOL_PREFIX + "fetch", "args": _fetch_args(item["file_id"])}
              for i, item in enumerate(selected, 1)]
    more = cursor + len(selected) < len(objects)
    return {"ok": True, "operation_key": header["operation_key"], "jobs": result,
            "next_cursor": cursor + len(selected) if more else None, "pass_complete": not more,
            "records_total": header["records_total"], "state_rows_total": header["state_rows_total"],
            "unique_chunks": len(objects), "manifest_sha256": _hash_file(manifest)[0]}


def _a_downloads(downloads):
    if isinstance(downloads, dict):
        return downloads
    with Path(downloads).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), "INVALID_DOWNLOAD_MAPPING")
    return value


def _a_download_path(downloads, item):
    path = downloads.get(item["file_id"], downloads.get(item["file_name"], downloads.get(item["object_id"])))
    _require(isinstance(path, str) and Path(path).is_file(), "REMOTE_CHUNK_DOWNLOAD_MISSING")
    return Path(path)


def _a_create_table(db, spec):
    """Reconstruct declared columns/keys; never execute SQL carried by a manifest."""
    definitions = spec.get("column_definitions")
    _require(isinstance(definitions, list) and [value.get("name") for value in definitions] == spec["columns"],
             "INVALID_STATE_SCHEMA")
    columns, primary = [], []
    for value in definitions:
        _require(isinstance(value.get("type"), str) and type(value.get("primary_key_order")) is int and
                 value["primary_key_order"] >= 0, "INVALID_STATE_SCHEMA")
        column = _a_quote(value["name"])
        if value["type"]:
            column += " " + _a_quote(value["type"])
        if value.get("not_null"):
            column += " NOT NULL"
        columns.append(column)
        if value["primary_key_order"]:
            primary.append((value["primary_key_order"], value["name"]))
    if primary:
        columns.append("PRIMARY KEY (" + ",".join(_a_quote(name) for _, name in sorted(primary)) + ")")
    db.execute("CREATE TABLE " + _a_quote(spec["name"]) + " (" + ",".join(columns) + ")")


def archive_restore(manifest, downloads, output_db, expected_manifest_sha256=None):
    downloads = _a_downloads(downloads)
    header, objects = _a_scan_manifest(manifest, expected_manifest_sha256)
    for item in objects.values():
        _a_download_path(downloads, item)
    manifest_hash = _hash_file(manifest)[0]
    output = Path(output_db).resolve()
    _require(not output.exists(), "RESTORE_DESTINATION_ALREADY_EXISTS")
    reserved = {"remote_archive_restore", "remote_archive_source_schema"}
    _require(not reserved.intersection(header["scope"]["included_tables"]), "RESTORE_METADATA_NAME_COLLISION")
    _private_file(output)
    db = sqlite3.connect(str(output), timeout=30)
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA temp_store=MEMORY")
    outgoing, current, digest, written = None, None, None, 0
    record_count, state_rows, cipher_bytes = 0, 0, 0
    cached_id, cached_bytes, current_spec = None, None, None

    def finish_record():
        nonlocal outgoing
        if outgoing is not None:
            outgoing.close()
            outgoing = None
            _require(written == current["ciphertext_bytes"] and digest.hexdigest() == current["ciphertext_sha256"],
                     "RESTORED_CIPHERTEXT_MISMATCH")

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(SOURCE_DDL)
        db.execute("CREATE TABLE remote_archive_source_schema(table_name TEXT PRIMARY KEY,spec_json TEXT NOT NULL)")
        for item in _a_manifest_events(manifest, manifest_hash):
            kind = item["type"]
            if kind == "record":
                finish_record()
                current, digest, written = item, hashlib.sha256(), 0
                _insert_source(db, item["source_rowid"], _metadata_values(item["metadata"]), item["ciphertext_bytes"])
                outgoing = db.blobopen("source_records", "ciphertext", item["source_rowid"], readonly=False)
                record_count += 1
            elif kind == "segment":
                if cached_id != item["object_id"]:
                    descriptor = objects[item["object_id"]]
                    cached_bytes = b"".join(_a_decoded_blocks(_a_download_path(downloads, descriptor), descriptor))
                    cached_id = item["object_id"]
                value = cached_bytes[item["object_offset"]:item["object_offset"] + item["segment_bytes"]]
                _require(len(value) == item["segment_bytes"], "REMOTE_SEGMENT_TRUNCATED")
                outgoing.write(value)
                digest.update(value)
                written += len(value)
                cipher_bytes += len(value)
            elif kind == "table":
                finish_record()
                current_spec = item["spec"]
                _a_create_table(db, current_spec)
                db.execute("INSERT INTO remote_archive_source_schema VALUES (?,?)", (item["table_name"], _json(current_spec)))
            elif kind == "state_row":
                row, columns = item["row"], list(current_spec["columns"])
                values = [_untyped(value) for value in row["values"]]
                if current_spec["rowid_alias"] is not None:
                    _require(current_spec["rowid_alias"] in ("rowid", "_rowid_", "oid") and
                             current_spec["rowid_alias"] not in columns and type(row["rowid"]) is int, "INVALID_STATE_ROWID")
                    columns.insert(0, current_spec["rowid_alias"])
                    values.insert(0, row["rowid"])
                db.execute("INSERT INTO " + _a_quote(current_spec["name"]) + " (" + ",".join(_a_quote(name) for name in columns) +
                           ") VALUES (" + ",".join("?" for _ in columns) + ")", values)
                state_rows += 1
            elif kind == "complete":
                finish_record()
        db.execute("CREATE TABLE remote_archive_restore(operation_key TEXT,manifest_sha256 TEXT,scope_json TEXT,"
                   "records_restored INTEGER,state_rows_restored INTEGER,ciphertext_bytes_restored INTEGER)")
        db.execute("INSERT INTO remote_archive_restore VALUES (?,?,?,?,?,?)", (header["operation_key"], manifest_hash,
                   _json(header["scope"]), record_count, state_rows, cipher_bytes))
        db.commit()
    except BaseException:
        if outgoing is not None:
            outgoing.close()
        db.rollback()
        raise
    finally:
        db.close()
    return {"ok": True, "operation_key": header["operation_key"], "restore_state": "confirmed",
            "records_restored": record_count, "state_rows_restored": state_rows, "ciphertext_bytes_restored": cipher_bytes,
            "manifest_sha256": manifest_hash, "source_scope": header["scope"],
            "schema_restoration": "declared_columns_types_primary_keys_and_exact_rows",
            "source_sql_recorded_not_executed": True, "source_indexes_triggers_defaults_executed": False}


def archive_rebuild_index(index, manifest, downloads, manifest_file_id, account_ref, folder_id,
                          expected_manifest_sha256=None):
    """Rebuild a NEW dedup index solely from a remote manifest and downloaded chunks."""
    _require(not Path(index).exists(), "ARCHIVE_INDEX_ALREADY_EXISTS")
    manifest_file_id = _provider_id(manifest_file_id)
    downloads = _a_downloads(downloads)
    header, objects = _a_scan_manifest(manifest, expected_manifest_sha256)
    destination = {"provider": "google_drive", "account_ref": account_ref, "folder_id": _provider_id(folder_id)}
    _require(_digest(destination) == header["destination_key"], "ARCHIVE_DESTINATION_CHANGED")
    for item in objects.values():
        for _ in _a_decoded_blocks(_a_download_path(downloads, item), item):
            pass
    stored_hash, stored_size = _hash_file(manifest)
    raw_hash, raw_size = hashlib.sha256(), 0
    with _a_manifest_stream(manifest) as handle:
        while block := handle.read(IO_BYTES):
            raw_hash.update(block)
            raw_size += len(block)
    with Path(manifest).open("rb") as handle:
        codec = "gzip" if handle.read(2) == b"\x1f\x8b" else "raw"
    index = _archive_initialize(index, destination)
    key, record_seq, table_seq, current_table = header["operation_key"], 0, 0, None
    with _db(index) as db, db:
        _a_check(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO operations(operation_key,operation_id,source_identity,chunk_bytes,scope_json,snapshot_sha256,"
                   "records_total,state_rows_total,prepared,observed_at) VALUES (?,?,?,?,?,?,?,?,1,?)",
                   (key, header["operation_id"], _json({"path": None, "remote_manifest_sha256": stored_hash}),
                    header["chunk_bytes"], _json(header["scope"]), header["snapshot_sha256"], header["records_total"],
                    header["state_rows_total"], header["observed_at"]))
        for obj in objects.values():
            db.execute("INSERT INTO objects(object_id,kind,size_bytes,sha256,file_name,state,remote_file_id,readback_sha256,"
                       "readback_bytes,raw_sha256,raw_bytes,codec) VALUES (?,'chunk',?,?,?,'confirmed',?,?,?,?,?,?)",
                       (obj["object_id"], obj["stored_bytes"], obj["sha256"], obj["file_name"], obj["file_id"], obj["sha256"],
                        obj["stored_bytes"], obj["raw_sha256"], obj["raw_bytes"], obj["codec"]))
            db.execute("INSERT INTO candidates VALUES (?,?,'confirmed')", (obj["object_id"], obj["file_id"]))
            db.execute("INSERT INTO operation_objects VALUES (?,?,1)", (key, obj["object_id"]))
        for item in _a_manifest_events(manifest, stored_hash):
            kind = item["type"]
            if kind == "record":
                record_seq += 1
                db.execute("INSERT OR IGNORE INTO record_versions VALUES (?,?,?,?)", (item["record_id"],
                           _a_pack(_json(item["metadata"])), item["ciphertext_sha256"], item["ciphertext_bytes"]))
                db.execute("INSERT INTO operation_records VALUES (?,?,?,?)", (key, record_seq, item["source_rowid"], item["record_id"]))
            elif kind == "segment":
                db.execute("INSERT INTO parts VALUES (?,?,?,?,?,?,?)", (key, record_seq, item["part"], item["object_id"],
                           item["source_offset"], item["object_offset"], item["segment_bytes"]))
            elif kind == "table":
                table_seq += 1
                current_table = item["state_id"]
                db.execute("INSERT OR IGNORE INTO table_versions VALUES (?,?,?,?)", (current_table, item["table_name"],
                           _a_pack(_json(item["spec"])), item["rows_total"]))
                db.execute("INSERT INTO operation_tables VALUES (?,?,?)", (key, table_seq, current_table))
            elif kind == "state_row":
                db.execute("INSERT INTO table_rows VALUES (?,?,?)", (current_table, item["seq"], _a_pack(_json(item["row"]))))
        object_id = _a_object_id(db, raw_hash.hexdigest(), raw_size, codec, stored_hash, "manifest", key)
        name = "src2-manifest-{}-{}.{}".format(key, stored_hash, "jsonl.gz" if codec == "gzip" else "jsonl")
        db.execute("INSERT INTO objects(object_id,kind,size_bytes,sha256,file_name,state,remote_file_id,readback_sha256,"
                   "readback_bytes,raw_sha256,raw_bytes,codec,owner_operation) "
                   "VALUES (?,'manifest',?,?,?,'confirmed',?,?,?,?,?,?,?)", (object_id, stored_size, stored_hash, name,
                    manifest_file_id, stored_hash, stored_size, raw_hash.hexdigest(), raw_size, codec, key))
        db.execute("INSERT INTO candidates VALUES (?,?,'confirmed')", (object_id, manifest_file_id))
        db.execute("INSERT INTO operation_objects VALUES (?,?,1)", (key, object_id))
        return _a_status(db, _a_operation(db, key), index)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CustodyError("INVALID_ARGUMENTS")


def _parser():
    parser = _Parser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    p = sub.add_parser("prepare")
    for name in ("source-db", "journal", "operation-id", "account-ref", "folder-id"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--chunk-bytes", type=int, default=4 * 1024 * 1024)
    for name in ("jobs", "status", "record-search", "record-upload", "record-readback", "record-failure"):
        p = sub.add_parser(name)
        p.add_argument("--journal", required=True)
        if name == "jobs":
            p.add_argument("--limit", type=int, default=100)
            p.add_argument("--cursor", type=int, default=0)
        if name.startswith("record-"):
            p.add_argument("--object-id", required=True)
        if name == "record-search":
            p.add_argument("--file-id", action="append", default=[], dest="file_ids")
            p.add_argument("--complete", action="store_true")
        if name in ("record-upload", "record-readback"):
            p.add_argument("--file-id", required=True)
        if name == "record-readback":
            p.add_argument("--download", required=True)
        if name == "record-failure":
            p.add_argument("--code", default="NATIVE_CALL_FAILED")
    for name in ("restore", "restore-jobs"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True)
        p.add_argument("--expected-manifest-sha256")
        if name == "restore-jobs":
            p.add_argument("--limit", type=int, default=100)
            p.add_argument("--cursor", type=int, default=0)
        else:
            p.add_argument("--downloads", required=True)
            p.add_argument("--output-db", required=True)
    p = sub.add_parser("archive-prepare")
    for name in ("source-db", "index", "operation-id", "account-ref", "folder-id"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--chunk-bytes", type=int, default=4 * 1024 * 1024)
    p.add_argument("--state-table", action="append", default=[], dest="state_tables")
    for name in ("archive-import-v1", "archive-status", "archive-jobs", "archive-capacity",
                 "archive-record-search", "archive-record-upload", "archive-record-readback", "archive-record-failure"):
        p = sub.add_parser(name)
        p.add_argument("--index", required=True)
        if name in ("archive-status", "archive-jobs"):
            p.add_argument("--operation-id", required=True)
        if name == "archive-jobs":
            p.add_argument("--limit", type=int, default=100)
            p.add_argument("--cursor", type=int, default=0)
        if name == "archive-import-v1":
            p.add_argument("--journal", required=True)
        if name == "archive-capacity":
            p.add_argument("--receipt", required=True)
        if name.startswith("archive-record-"):
            p.add_argument("--object-id", required=True)
        if name == "archive-record-search":
            p.add_argument("--file-id", action="append", default=[], dest="file_ids")
            p.add_argument("--complete", action="store_true")
        if name in ("archive-record-upload", "archive-record-readback"):
            p.add_argument("--file-id", required=True)
        if name == "archive-record-readback":
            p.add_argument("--download", required=True)
        if name == "archive-record-failure":
            p.add_argument("--code", default="NATIVE_CALL_FAILED")
    for name in ("archive-restore-jobs", "archive-restore", "archive-rebuild-index"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True)
        p.add_argument("--expected-manifest-sha256")
        if name == "archive-restore-jobs":
            p.add_argument("--limit", type=int, default=100)
            p.add_argument("--cursor", type=int, default=0)
        else:
            p.add_argument("--downloads", required=True)
        if name == "archive-restore":
            p.add_argument("--output-db", required=True)
        if name == "archive-rebuild-index":
            for field in ("index", "manifest-file-id", "account-ref", "folder-id"):
                p.add_argument("--" + field, required=True)
    return parser


def main(argv=None):
    try:
        args = vars(_parser().parse_args(argv))
        command = args.pop("command").replace("-", "_")
        result = globals()[command](**args)
        print(_json(result))
        return 0 if result.get("ok") else 1
    except KeyboardInterrupt:
        print(_json({"ok": False, "error": "KeyboardInterrupt", "code": "INTERRUPTED"}), file=sys.stderr)
        return 130
    except Exception as exc:
        code = exc.code if isinstance(exc, CustodyError) else (
            "SQLITE_ERROR" if isinstance(exc, sqlite3.Error) else
            "FILESYSTEM_ERROR" if isinstance(exc, OSError) else "INVALID_DATA")
        print(_json({"ok": False, "error": type(exc).__name__, "code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
