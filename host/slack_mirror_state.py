"""Durable local receipts for a source event mirrored to a Slack destination.

The database must live in a trusted local directory shared by all mirror workers.
A committed in-flight intent is NEVER retried automatically: it may already have
reached Slack. Only an explicit, attempt-bound reconciliation can release it.
No Slack token or message body is retained in this database.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

APPLICATION_ID = 0x534C4D31
VERSION = 1
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_PARTS = 4096
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
SLACK_TS = re.compile(r"[0-9]{1,20}\.[0-9]{6}\Z")


class DeliveryError(RuntimeError):
    """A controlled delivery/state error; never contains a credential."""


class DeliveryConflict(DeliveryError):
    """The event identity was reused for different content or chunk boundaries."""


class DeliveryUncertain(DeliveryError):
    """A send may be in progress or delivered; native evidence is required."""


class RejectedSend(DeliveryError):
    """Transport evidence establishes non-delivery of the attempted part."""

    def __init__(self, code: str, retry_after: int = 0):
        # Codes are supplied by the transport adapter, not arbitrary error prose.
        if not isinstance(code, str) or not re.fullmatch(r"[a-z_]{1,80}", code):
            raise ValueError("invalid rejection code")
        if type(retry_after) is not int or not 0 <= retry_after <= 86400:
            raise ValueError("invalid retry delay")
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"Slack rejected part: {code}; retry_after={retry_after}s")


def default_state_path() -> Path:
    configured = os.environ.get("COMMONS_SLACK_MIRROR_STATE", "").strip()
    if configured:
        return Path(configured).expanduser()
    root = Path(os.environ.get("XDG_STATE_HOME", "").strip() or
                (Path.home() / ".local" / "state"))
    return root / "commons" / "slack-mirror.sqlite3"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value: object, name: str, maximum: int = 2048) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise DeliveryError(f"invalid {name}")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DeliveryError(f"invalid {name}")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise DeliveryError(f"invalid {name}") from None
    return value


def _timestamp(value: object, *, empty: bool = False) -> str:
    if type(value) is not str or not ((empty and value == "") or SLACK_TS.fullmatch(value)):
        raise DeliveryError("invalid Slack timestamp")
    return value


def event_identity(source_event: str, channel: str, thread_ts: str = "") -> dict:
    return {"source_event": _text(source_event, "source event"),
            "channel": _text(channel, "channel"),
            "thread_ts": _timestamp(thread_ts, empty=True)}


def _parts(parts: list[str]) -> tuple[str, list[str]]:
    if type(parts) is not list or not 1 <= len(parts) <= MAX_PARTS:
        raise DeliveryError("event must contain 1..4096 parts")
    hashes = []
    for text in parts:
        if type(text) is not str or not text:
            raise DeliveryError("event contains an empty or non-text part")
        try:
            hashes.append(_sha(text))
        except UnicodeError:
            raise DeliveryError("part is not valid UTF-8 text") from None
    return _sha(_canonical(parts)), hashes


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= (2 ** 53 - 1)


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise DeliveryError("duplicate state key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise DeliveryError("non-finite state number")


def _validate(record: object, key: str) -> dict:
    fields = {"version", "identity", "payload_sha256", "part_sha256", "receipts",
              "in_flight", "retry_at_ms", "last_error", "reconciliations"}
    if type(record) is not dict or set(record) != fields or type(record["version"]) is not int:
        raise DeliveryError("malformed receipt record")
    if record["version"] != VERSION:
        raise DeliveryError("unsupported receipt version")
    identity = record["identity"]
    if type(identity) is not dict or set(identity) != {"source_event", "channel", "thread_ts"}:
        raise DeliveryError("malformed event identity")
    if event_identity(**identity) != identity or _sha(_canonical(identity)) != key:
        raise DeliveryError("receipt identity mismatch")
    hashes = record["part_sha256"]
    if (type(hashes) is not list or not 1 <= len(hashes) <= MAX_PARTS or
            any(type(h) is not str or not HEX64.fullmatch(h) for h in hashes) or
            type(record["payload_sha256"]) is not str or not HEX64.fullmatch(record["payload_sha256"])):
        raise DeliveryError("malformed payload fingerprint")
    receipts = record["receipts"]
    if type(receipts) is not list or len(receipts) > len(hashes):
        raise DeliveryError("malformed receipt progress")
    for ts in receipts:
        _timestamp(ts)
    if len(set(receipts)) != len(receipts):
        raise DeliveryError("duplicate part receipt")
    pending = record["in_flight"]
    if pending is not None:
        if (type(pending) is not dict or set(pending) != {"part", "attempt"} or
                type(pending["part"]) is not int or pending["part"] != len(receipts) or
                pending["part"] >= len(hashes) or type(pending["attempt"]) is not str or
                not ATTEMPT.fullmatch(pending["attempt"])):
            raise DeliveryError("malformed in-flight intent")
    if not _integer(record["retry_at_ms"]) or (pending and record["retry_at_ms"]):
        raise DeliveryError("malformed retry state")
    error = record["last_error"]
    if error is not None and (type(error) is not str or not re.fullmatch(r"[a-z_]{1,80}", error)):
        raise DeliveryError("malformed error code")
    history = record["reconciliations"]
    if type(history) is not list:
        raise DeliveryError("malformed reconciliation history")
    for row in history:
        if (type(row) is not dict or set(row) != {"part", "attempt", "result", "receipt_ts", "evidence", "recorded_at_ms"}
                or type(row["part"]) is not int or not 0 <= row["part"] < len(hashes)
                or type(row["attempt"]) is not str or not ATTEMPT.fullmatch(row["attempt"])
                or row["result"] not in ("ACCEPTED", "NOT_SENT") or not _integer(row["recorded_at_ms"])):
            raise DeliveryError("malformed reconciliation entry")
        _text(row["evidence"], "reconciliation evidence")
        _timestamp(row["receipt_ts"], empty=row["result"] == "NOT_SENT")
        if row["result"] == "NOT_SENT" and row["receipt_ts"]:
            raise DeliveryError("contradictory reconciliation entry")
    return record


class MirrorStore:
    """SQLite serialization of intents and native receipts, not send permission.

    Each method opens its own connection. A transaction is never held during an
    HTTP request. Concurrent workers encounter the same committed intent and
    cannot both invoke the sender for that part.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._check_file()
        # Exclusive creation prevents a creator from changing another worker's
        # existing mode. SQLite itself serializes initialization below.
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self._connection(check_schema=False) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            application = db.execute("PRAGMA application_id").fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version == 0 and application == 0 and not tables:
                db.execute("CREATE TABLE deliveries (event_key TEXT PRIMARY KEY NOT NULL, record TEXT NOT NULL)")
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.execute(f"PRAGMA user_version={VERSION}")
            elif version != VERSION or application != APPLICATION_ID:
                raise DeliveryError("unsupported mirror state database; preserved unchanged")
            self._check_schema(db)

    def _check_file(self):
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode):
            raise DeliveryError("state database must be an ordinary file, not a symlink")

    def _check_schema(self, db):
        if (db.execute("PRAGMA user_version").fetchone()[0] != VERSION or
                db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID):
            raise DeliveryError("unsupported mirror state database; preserved unchanged")
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        columns = db.execute("PRAGMA table_info(deliveries)").fetchall()
        if (tables != [("deliveries",)] or
                [(c[1], c[2], c[3], c[5]) for c in columns] != [
                    ("event_key", "TEXT", 1, 1), ("record", "TEXT", 1, 0)]):
            raise DeliveryError("malformed mirror state database; preserved unchanged")

    @contextmanager
    def _connection(self, *, check_schema=True, write=True) -> Iterator[sqlite3.Connection]:
        self._check_file()
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if check_schema:
                self._check_schema(db)
            yield db
            db.execute("COMMIT")
        except sqlite3.Error:
            if db is not None and db.in_transaction:
                db.rollback()
            raise DeliveryError("mirror state database could not be read or committed; do not discard it") from None
        except BaseException:
            if db is not None and db.in_transaction:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def _load(self, db, identity, fingerprint, hashes, *, create=False):
        key = _sha(_canonical(identity))
        row = db.execute("SELECT record FROM deliveries WHERE event_key=?", (key,)).fetchone()
        if row is None:
            if not create:
                return key, None
            record = {"version": VERSION, "identity": identity, "payload_sha256": fingerprint,
                      "part_sha256": hashes, "receipts": [], "in_flight": None,
                      "retry_at_ms": 0, "last_error": None, "reconciliations": []}
        else:
            if type(row[0]) is not str or len(row[0].encode("utf-8")) > MAX_RECORD_BYTES:
                raise DeliveryError("oversized or non-text state record")
            try:
                record = json.loads(row[0], object_pairs_hook=_pairs, parse_constant=_reject_constant)
                _validate(record, key)
            except (ValueError, TypeError, RecursionError, UnicodeError):
                raise DeliveryError("malformed state JSON; preserved unchanged") from None
            if record["identity"] != identity or record["payload_sha256"] != fingerprint or record["part_sha256"] != hashes:
                raise DeliveryConflict("event already exists with different content or chunk boundaries")
        return key, record

    def _save(self, db, key, record):
        _validate(record, key)
        raw = _canonical(record)
        if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
            raise DeliveryError("receipt record exceeds storage bound")
        db.execute("INSERT INTO deliveries(event_key,record) VALUES (?,?) "
                   "ON CONFLICT(event_key) DO UPDATE SET record=excluded.record", (key, raw))

    def inspect(self, source_event: str, parts: list[str], *, channel: str, thread_ts: str = "") -> dict:
        identity = event_identity(source_event, channel, thread_ts)
        fingerprint, hashes = _parts(parts)
        with self._connection(write=False) as db:
            key, record = self._load(db, identity, fingerprint, hashes)
        if record is None:
            return {"event_key": key, "state": "ABSENT", "identity": identity}
        state = ("UNCERTAIN_OR_IN_FLIGHT" if record["in_flight"] else
                 "COMPLETE" if len(record["receipts"]) == len(hashes) else "READY")
        return {"event_key": key, "state": state, **record}

    def send(self, source_event: str, parts: list[str], sender: Callable[[str, str], str],
             *, channel: str, thread_ts: str = "") -> list[str]:
        identity = event_identity(source_event, channel, thread_ts)
        # Freeze the complete message before the first part is committed/sent.
        if type(parts) is not list:
            raise DeliveryError("event parts must be a list")
        parts = parts.copy()
        fingerprint, hashes = _parts(parts)
        while True:
            with self._connection() as db:
                key, record = self._load(db, identity, fingerprint, hashes, create=True)
                if record["in_flight"]:
                    pending = record["in_flight"]
                    raise DeliveryUncertain(f"part {pending['part'] + 1} is in-flight/uncertain; "
                                            f"attempt={pending['attempt']}; inspect and reconcile before retry")
                if len(record["receipts"]) == len(parts):
                    return list(record["receipts"])
                delay = max(0, math.ceil((record["retry_at_ms"] - int(time.time() * 1000)) / 1000))
                if delay:
                    raise RejectedSend("rate_limited", min(delay, 86400))
                attempt = {"part": len(record["receipts"]), "attempt": uuid.uuid4().hex}
                record["in_flight"] = attempt
                record["retry_at_ms"] = 0
                record["last_error"] = None
                self._save(db, key, record)
                reply_to = thread_ts or (record["receipts"][0] if record["receipts"] else "")
            try:
                ts = _timestamp(sender(parts[attempt["part"]], reply_to))
            except RejectedSend as exc:
                self._finish(identity, fingerprint, hashes, attempt, rejection=exc)
                raise
            except Exception:
                # The intent was committed before transport. Preserve it even if
                # Slack's response was lost, malformed, or only partly successful.
                self._finish(identity, fingerprint, hashes, attempt, uncertain=True)
                raise DeliveryUncertain(f"part {attempt['part'] + 1} outcome unknown; "
                                        f"attempt={attempt['attempt']}; no automatic resend") from None
            # A valid provider receipt means Slack may already have committed the
            # message. If local receipt persistence/COMMIT now fails, the only safe
            # immediate result is UNCERTAIN: retain the exact pre-transport intent
            # and require reconciliation rather than exposing a retryable state error.
            try:
                self._finish(identity, fingerprint, hashes, attempt, receipt=ts)
            except DeliveryUncertain:
                raise
            except DeliveryError:
                raise DeliveryUncertain(
                    f"part {attempt['part'] + 1} provider receipt could not be durably recorded; "
                    f"attempt={attempt['attempt']}; inspect and reconcile before retry"
                ) from None

    def _finish(self, identity, fingerprint, hashes, attempt, *, receipt=None, rejection=None, uncertain=False):
        with self._connection() as db:
            key, record = self._load(db, identity, fingerprint, hashes)
            if record is None or record["in_flight"] != attempt:
                raise DeliveryUncertain("attempt changed during transport; reconcile native evidence")
            if receipt is not None:
                if receipt in record["receipts"]:
                    raise DeliveryUncertain("duplicate native timestamp; retain intent for reconciliation")
                record["receipts"].append(receipt)
                record["in_flight"] = None
                record["last_error"] = None
            elif rejection is not None:
                record["in_flight"] = None
                record["retry_at_ms"] = int(time.time() * 1000) + rejection.retry_after * 1000
                record["last_error"] = rejection.code
            elif uncertain:
                record["last_error"] = "uncertain_transport"
            self._save(db, key, record)

    def reconcile(self, source_event: str, parts: list[str], *, channel: str, thread_ts: str = "",
                  part: int, attempt: str, evidence: str, accepted_ts: str = "", not_sent: bool = False) -> dict:
        """Record operator-observed native evidence. This method sends nothing.

        Accepted evidence records a timestamp and prevents retransmission.
        NOT_SENT reopens just this pending part; it must not be inferred from a
        search miss. Stop the original worker before performing reconciliation.
        """
        if type(part) is not int or part < 1 or type(attempt) is not str or not ATTEMPT.fullmatch(attempt):
            raise DeliveryError("reconciliation requires a one-based part and exact attempt")
        if type(not_sent) is not bool or bool(accepted_ts) == not_sent:
            raise DeliveryError("choose exactly one of accepted_ts or not_sent")
        _text(evidence, "reconciliation evidence")
        _timestamp(accepted_ts, empty=not_sent)
        identity = event_identity(source_event, channel, thread_ts)
        fingerprint, hashes = _parts(parts)
        pending = {"part": part - 1, "attempt": attempt}
        with self._connection() as db:
            key, record = self._load(db, identity, fingerprint, hashes)
            if record is None or record["in_flight"] != pending:
                raise DeliveryConflict("reconciliation does not match the pending attempt")
            if accepted_ts:
                if accepted_ts in record["receipts"]:
                    raise DeliveryConflict("native timestamp already belongs to another part")
                record["receipts"].append(accepted_ts)
            record["in_flight"] = None
            record["retry_at_ms"] = 0
            record["last_error"] = None
            record["reconciliations"].append({"part": part - 1, "attempt": attempt,
                "result": "NOT_SENT" if not_sent else "ACCEPTED", "receipt_ts": accepted_ts,
                "evidence": evidence, "recorded_at_ms": int(time.time() * 1000)})
            self._save(db, key, record)
        return self.inspect(source_event, parts, channel=channel, thread_ts=thread_ts)