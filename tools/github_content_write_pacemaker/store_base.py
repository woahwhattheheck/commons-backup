"""SQLite generation ownership and schema setup."""

from __future__ import annotations
import os
import sqlite3
import stat
from pathlib import Path
from .codec import now_utc
from .constants import DB_SCHEMA
from .errors import PacemakerError, StoreInvariantError


def _make_connect_method(sqlite_connect, sqlite_error, sqlite_row):
    """Capture SQLite open authority once; never re-resolve it from module state."""
    def _connect(self) -> sqlite3.Connection:
        self._assert_db_identity()
        try:
            db = sqlite_connect(
                self._db_uri, timeout=30, isolation_level=None, uri=True
            )
        except sqlite_error:
            self._assert_db_identity()
            raise
        try:
            self._assert_db_identity()
            db.row_factory = sqlite_row
            db.execute("PRAGMA busy_timeout=30000")
            return db
        except Exception:
            db.close()
            raise

    return _connect


def _owned(info) -> None:
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise PacemakerError("database path owner mismatch")


def _safe_file(info) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PacemakerError("database must be one ordinary single-link file")
    _owned(info)


def _descriptor_sqlite_uri(fd: int, identity: tuple[int, int]) -> str:
    """Return a SQLite URI that reopens the already-acquired file generation."""
    for root in (Path("/proc/self/fd"), Path("/dev/fd")):
        candidate = root / str(fd)
        try:
            info = os.stat(candidate)
        except OSError:
            continue
        if (info.st_dev, info.st_ino) == identity:
            return candidate.as_uri() + "?mode=rw"
    raise PacemakerError("descriptor-backed SQLite open is unavailable")


def _prepare_db_path(path: Path) -> tuple[Path, tuple[int, int], int]:
    path = Path(path)
    if str(path) == ":memory:":
        raise PacemakerError("persistent database path required")
    parent = path.parent if str(path.parent) else Path(".")
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise PacemakerError("database parent prepare failed") from exc

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(parent, flags)
    except OSError as exc:
        raise PacemakerError("database parent must be an ordinary directory") from exc

    fd = None
    try:
        parent_info = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_info.st_mode):
            raise PacemakerError("database parent must be an ordinary directory")
        _owned(parent_info)
        if parent_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PacemakerError("database parent must not be group/other writable")

        try:
            canonical_parent = parent.resolve(strict=True)
            canonical_info = os.stat(canonical_parent, follow_symlinks=False)
        except OSError as exc:
            raise PacemakerError("database parent identity unavailable") from exc
        if (canonical_info.st_dev, canonical_info.st_ino) != (
            parent_info.st_dev, parent_info.st_ino
        ):
            raise PacemakerError("database parent changed during acquisition")

        name = path.name
        if not name or name in (".", ".."):
            raise PacemakerError("database path is invalid")

        try:
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            open_flags = (
                os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                fd = os.open(name, open_flags, 0o600, dir_fd=parent_fd)
            except OSError as exc:
                raise PacemakerError("database create failed") from exc
        except OSError as exc:
            raise PacemakerError("database path inspection failed") from exc
        else:
            _safe_file(visible)
            open_flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(name, open_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise PacemakerError("database open failed") from exc
            opened = os.fstat(fd)
            _safe_file(opened)
            if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
                raise PacemakerError("database path changed during acquisition")

        info = os.fstat(fd)
        _safe_file(info)
        try:
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        except OSError as exc:
            raise PacemakerError("database permission hardening failed") from exc
        after = os.fstat(fd)
        _safe_file(after)
        identity = (after.st_dev, after.st_ino)
        try:
            visible_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise PacemakerError("database path changed during acquisition") from exc
        if (visible_after.st_dev, visible_after.st_ino) != identity:
            raise PacemakerError("database path changed during acquisition")

        kept_fd = fd
        fd = None
        return canonical_parent / name, identity, kept_fd
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.close(parent_fd)
        except OSError:
            pass


try:
    _TRUSTED_CONNECT_METHOD = StoreBase._connect
except NameError:
    _TRUSTED_CONNECT_METHOD = _make_connect_method(
        sqlite3.connect, sqlite3.Error, sqlite3.Row
    )


class StoreBase:
    def __init__(self, path: Path, *, clock=now_utc) -> None:
        self.clock = clock
        self._db_fd = None
        try:
            self.path, self._db_identity, self._db_fd = _prepare_db_path(Path(path))
            self._db_uri = _descriptor_sqlite_uri(
                self._db_fd, self._db_identity
            )
            self._init()
            self._assert_db_identity()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        fd = getattr(self, "_db_fd", None)
        if fd is None:
            return
        self._db_fd = None
        try:
            os.close(fd)
        except OSError:
            pass

    def __del__(self):
        self.close()

    def _assert_db_identity(self) -> None:
        fd = getattr(self, "_db_fd", None)
        if fd is None:
            raise StoreInvariantError("database generation anchor is closed")
        try:
            anchored = os.fstat(fd)
            _safe_file(anchored)
            info = os.lstat(self.path)
            _safe_file(info)
        except (OSError, PacemakerError) as exc:
            raise StoreInvariantError("database path generation changed") from exc
        if (anchored.st_dev, anchored.st_ino) != self._db_identity:
            raise StoreInvariantError("database generation anchor changed")
        if (info.st_dev, info.st_ino) != self._db_identity:
            raise StoreInvariantError("database path generation changed")

    _connect = _TRUSTED_CONNECT_METHOD

    def _init(self) -> None:
        db = self._connect()
        try:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema TEXT NOT NULL,
              last_claim_at TEXT, cooldown_until TEXT, cooldown_reason TEXT);
            INSERT OR IGNORE INTO meta(singleton,schema)
              VALUES(1,'commons-github-content-write-pacemaker-db/v2');
            CREATE TABLE IF NOT EXISTS mutations(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,
              mutation_key TEXT NOT NULL UNIQUE,
              semantic_sha256 TEXT NOT NULL UNIQUE,
              intent_sha256 TEXT NOT NULL,
              method TEXT NOT NULL, api_path TEXT NOT NULL,
              description TEXT NOT NULL, body_json BLOB NOT NULL,
              body_sha256 TEXT NOT NULL, state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              enqueued_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              claimed_at TEXT, retry_at TEXT, provider_status INTEGER,
              provider_receipt_sha256 TEXT, observation_ref_sha256 TEXT,
              observation_sha256 TEXT, reason TEXT NOT NULL);
            """)
            self._assert_db_identity()
            schema = db.execute(
                "SELECT schema FROM meta WHERE singleton=1"
            ).fetchone()[0]
            if schema != DB_SCHEMA:
                raise StoreInvariantError("database schema mismatch")
        finally:
            db.close()


del _TRUSTED_CONNECT_METHOD
del _make_connect_method
