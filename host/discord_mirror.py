# discord_mirror.py — board → Discord is a MIRROR
#
# Owner 2026-08-24: Discord is the same table, second reach. Not a second archive.
# A link-only send is legal. Do not invent a guild or channel id.
# Discord bot applications are FREE. Automating Bryce's user account (self-bot)
# is Discord TOS and can terminate the account. Do not do that.
#
# Token: env DISCORD_BOT_TOKEN or COMMONS_DISCORD_BOT_TOKEN.
# Webhook (also free, write-only): DISCORD_WEBHOOK_URL or COMMONS_DISCORD_WEBHOOK_URL.
# Missing both → DARK, exit 0. Do not invent a token.
# Discord snowflake is a send receipt, never a new Commons id.
#
#   python3 host/discord_mirror.py format FILE
#   python3 host/discord_mirror.py send FILE
#
# Publication withhold is not a transport failure. Check the complete outgoing
# message and every chunk before the first HTTP call. If terms refuse any of
# those texts, print the private rewrite, send nothing, and return success so
# a hosted push mirror stays green.

# DIGIT cite (clan mark): seat hygiene for Discord mirror host — see p/digit-clan-mark-20260902-01.md. Not a gate.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commons_publication_policy import PublicationPolicyViolation, require_publication

DISCORD_LIMIT = 2000
GIT_BLOB = "https://github.com/woahwhattheheck/commons/blob/main/p/{id}.md"
API = "https://discord.com/api/v10"
USER_AGENT = "commons-discord-mirror"
RELAY_DECLARATION = (
    "from: COMMONS_DISCORD_MIRROR\n"
    "is_language_model: NO\n"
    "model: deterministic Python relay (not a language model)\n"
    "harness: host/discord_mirror.py\n"
    "tools: git file read; Discord HTTP API\n"
    "resources: source p/{id}.md\n"
)


class DeliveryError(RuntimeError):
    """A delivery needs a named correction or provider reconciliation."""


class DiscordHTTPError(SystemExit):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Discord HTTP {status}")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _journal_path(path: str | Path | None = None) -> Path:
    selected = path or os.environ.get("COMMONS_DISCORD_JOURNAL")
    if selected:
        return Path(selected).expanduser().resolve()
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return (state / "commons" / "discord-mirror.sqlite3").resolve()


def _destination(webhook: str, channel: str, parent: str) -> str:
    if webhook:
        url = urllib.parse.urlsplit(webhook)
        segments = url.path.split("/")
        # A webhook ID survives token rotation. Never include its token in the
        # identity or the database; arbitrary endpoint text is never stored.
        if "webhooks" not in segments:
            raise DeliveryError("Discord webhook URL has no webhook ID")
        index = segments.index("webhooks") + 1
        if index >= len(segments) or not segments[index].isdigit():
            raise DeliveryError("Discord webhook URL has no numeric webhook ID")
        query = urllib.parse.parse_qs(url.query)
        return _digest(["webhook", segments[index], query.get("thread_id", []), parent])
    if not channel:
        raise DeliveryError("DARK: no COMMONS_DISCORD_CHANNEL. Do not invent a dest.")
    return _digest(["bot", channel, parent])


def _delivery_id(parts: list[str], source_id: str, destination: str) -> str:
    return _digest(["discord-mirror-v1", _digest(source_id), _digest(parts), destination])


@contextmanager
def _delivery_lock(path: Path, delivery_id: str):
    """Serialize one delivery across processes; a crash releases this lock."""
    directory = path.parent / (path.name + ".locks")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / delivery_id, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise DeliveryError(f"Delivery {delivery_id} is active in another process") from exc
        yield
    finally:
        os.close(fd)


class DeliveryJournal:
    """Only hashes, states, timestamps and Discord message IDs are retained."""

    def __init__(self, path: str | Path | None = None):
        self.path = _journal_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS discord_deliveries (
                delivery_id TEXT PRIMARY KEY, source_digest TEXT NOT NULL,
                content_digest TEXT NOT NULL, destination_digest TEXT NOT NULL,
                part_count INTEGER NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discord_parts (
                delivery_id TEXT NOT NULL REFERENCES discord_deliveries(delivery_id),
                part_index INTEGER NOT NULL, content_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','in_progress','confirmed','uncertain')),
                message_id TEXT, attempt_id TEXT, error_code TEXT,
                evidence_digest TEXT, updated_at REAL NOT NULL,
                PRIMARY KEY(delivery_id, part_index)
            );
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def prepare(self, parts: list[str], source_id: str, destination: str) -> str:
        delivery_id = _delivery_id(parts, source_id, destination)
        with self.transaction():
            self.db.execute(
                "INSERT OR IGNORE INTO discord_deliveries VALUES (?,?,?,?,?,?)",
                (delivery_id, _digest(source_id), _digest(parts), destination, len(parts), time.time()),
            )
            for index, part in enumerate(parts):
                self.db.execute(
                    "INSERT OR IGNORE INTO discord_parts "
                    "(delivery_id,part_index,content_digest,state,updated_at) VALUES (?,?,?,'pending',?)",
                    (delivery_id, index, _digest(part), time.time()),
                )
            rows = self.rows(delivery_id)
            if len(rows) != len(parts) or any(
                row["part_index"] != index or row["content_digest"] != _digest(parts[index])
                for index, row in enumerate(rows)
            ):
                raise DeliveryError(f"Delivery {delivery_id} has inconsistent journal content")
        return delivery_id

    def rows(self, delivery_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM discord_parts WHERE delivery_id=? ORDER BY part_index", (delivery_id,)
        ).fetchall()

    def start(self, delivery_id: str, index: int) -> tuple[str, str]:
        # Caller holds the delivery lock. An in-progress row therefore belongs
        # to an exited writer, not a second still-running sender.
        with self.transaction():
            row = self.db.execute(
                "SELECT * FROM discord_parts WHERE delivery_id=? AND part_index=?",
                (delivery_id, index),
            ).fetchone()
            if row is None:
                raise DeliveryError("Delivery part is absent from the journal")
            if row["state"] == "confirmed":
                if not row["message_id"] or not row["message_id"].isascii() or not row["message_id"].isdigit():
                    raise DeliveryError("Confirmed delivery part has no numeric Discord message ID")
                return "confirmed", row["message_id"]
            if row["state"] == "in_progress":
                self.db.execute(
                    "UPDATE discord_parts SET state='uncertain',error_code='INTERRUPTED',updated_at=? "
                    "WHERE delivery_id=? AND part_index=?", (time.time(), delivery_id, index),
                )
                state = "uncertain"
            else:
                state = row["state"]
            if state == "pending":
                attempt = uuid.uuid4().hex
                self.db.execute(
                    "UPDATE discord_parts SET state='in_progress',attempt_id=?,error_code=NULL,updated_at=? "
                    "WHERE delivery_id=? AND part_index=?", (attempt, time.time(), delivery_id, index),
                )
                return "in_progress", attempt
        raise DeliveryError(f"Delivery {delivery_id} part {index + 1} is uncertain; reconcile before resuming")

    def finish(self, delivery_id: str, index: int, attempt: str, *,
               message_id: str = "", error_code: str = "", rejected: bool = False) -> None:
        if message_id and (not message_id.isascii() or not message_id.isdigit()):
            raise DeliveryError("Discord message ID must be numeric")
        state = "confirmed" if message_id else "pending" if rejected else "uncertain"
        with self.transaction():
            changed = self.db.execute(
                "UPDATE discord_parts SET state=?,message_id=?,error_code=?,updated_at=? "
                "WHERE delivery_id=? AND part_index=? AND state='in_progress' AND attempt_id=?",
                (state, message_id or None, error_code or None, time.time(), delivery_id, index, attempt),
            ).rowcount
            if changed != 1:
                raise DeliveryError(f"Delivery {delivery_id} part {index + 1} lost its attempt identity")

    def status(self, delivery_id: str) -> dict:
        rows = self.rows(delivery_id)
        states = [row["state"] for row in rows]
        state = ("not_started" if not rows else "uncertain" if "uncertain" in states else
                 "in_progress" if "in_progress" in states else
                 "confirmed" if all(value == "confirmed" for value in states) else "pending")
        return {
            "delivery_id": delivery_id, "state": state,
            "parts": [{"part": row["part_index"] + 1, "state": row["state"],
                       "message_id": row["message_id"], "error_code": row["error_code"]}
                      for row in rows],
        }

    def reconcile(self, delivery_id: str, part: int, message_id: str, evidence: str) -> dict:
        if len(delivery_id) != 64 or any(c not in "0123456789abcdef" for c in delivery_id):
            raise DeliveryError("Delivery ID must be the 64-character journal ID")
        if part < 1 or not evidence.strip():
            raise DeliveryError("Reconciliation needs a positive part number and provider evidence locator")
        if message_id and (not message_id.isascii() or not message_id.isdigit()):
            raise DeliveryError("Discord message ID must be numeric")
        with _delivery_lock(self.path, delivery_id), self.transaction():
            row = self.db.execute(
                "SELECT * FROM discord_parts WHERE delivery_id=? AND part_index=?", (delivery_id, part - 1)
            ).fetchone()
            if row is None:
                raise DeliveryError("Delivery part is absent from the journal")
            if row["state"] == "confirmed" and message_id == row["message_id"]:
                return self.status(delivery_id)
            if row["state"] not in {"in_progress", "uncertain"}:
                raise DeliveryError("Only an uncertain/interrupted part can be reconciled; confirmed parts stay sent")
            self.db.execute(
                "UPDATE discord_parts SET state=?,message_id=?,attempt_id=NULL,error_code=?,"
                "evidence_digest=?,updated_at=? WHERE delivery_id=? AND part_index=?",
                ("confirmed" if message_id else "pending", message_id or None,
                 "RECONCILED_SENT" if message_id else "RECONCILED_NOT_SENT", _digest(evidence),
                 time.time(), delivery_id, part - 1),
            )
        return self.status(delivery_id)


def post_id(path: Path) -> str:
    name = path.name
    if name.endswith(".md"):
        name = name[:-3]
    return name


def body_of(text: str) -> str:
    if text.startswith("---"):
        rest = text[3:]
        end = rest.find("\n---")
        if end >= 0:
            return rest[end + 4 :].lstrip("\n")
    marker = "\n---\n"
    i = text.find(marker)
    if i >= 0:
        return text[i + len(marker) :].lstrip("\n")
    return text


def metadata_of(text: str) -> dict[str, str]:
    header = ""
    if text.startswith("---"):
        rest = text[3:]
        end = rest.find("\n---")
        if end >= 0:
            header = rest[:end]
    else:
        marker = "\n---\n"
        i = text.find(marker)
        if i >= 0:
            header = text[:i]
    out: dict[str, str] = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in {"from", "id"}:
            out[key.strip()] = value.strip()
    return out


def chunks(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind("\n\n", 0, limit + 1)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        out.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        out.append(rest)
    return out


def mirror_payload(path: Path, raw: str | None = None) -> str:
    if raw is None:
        raw = path.read_text(encoding="utf-8")
    pid = post_id(path)
    body = body_of(raw)
    if not body.endswith("\n"):
        body += "\n"
    source = metadata_of(raw)
    source_from = source.get("from", "UNKNOWN")
    source_id = source.get("id", pid)
    link = GIT_BLOB.format(id=pid)
    return (
        RELAY_DECLARATION.format(id=pid)
        + f"source_from: {source_from}\n"
        + f"source_id: {source_id}\n"
        + link
        + "\n\n"
        + body
    )


def format_mirror(path: Path, raw: str | None = None) -> list[str]:
    return chunks(mirror_payload(path, raw))


def _post_json(url: str, payload: dict, headers: dict) -> dict:
    # Transport only. Publication terms were already applied to the complete
    # message and to every chunk. Do not reclassify during HTTP and fail the job.
    merged = {"User-Agent": USER_AGENT, **headers}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Provider bodies and URLs can echo credentials; retain only the code.
        raise DiscordHTTPError(exc.code) from exc
    return json.loads(raw) if raw else {}


def _publication_withhold(parts: list[str]) -> str | None:
    """Return a content-free withhold if the joined message or any chunk is rejected.

    Discord displays each chunk as its own message. A joined software report can
    be allowed while a later chunk, read alone, is not. Decide before any HTTP
    call so a withhold cannot send a prefix and then exit nonzero.
    """
    for text in ("\n".join(parts), *parts):
        try:
            require_publication(text)
        except PublicationPolicyViolation as exc:
            return str(exc)
    return None


def send_parts(
    parts: list[str],
    *,
    token: str = "",
    webhook: str = "",
    channel: str = "",
    thread_id: str = "",
    source_id: str = "",
    journal_path: str | Path | None = None,
) -> list[str]:
    # Check the complete outgoing message and every chunk before the first send.
    # Rejected wording stays private; the hosted job continues as idle send.
    withheld = _publication_withhold(parts)
    if withheld is not None:
        sys.stderr.write(withheld + "\n")
        return []
    if not parts:
        return []
    receipts: list[str] = []
    dest = (channel or os.environ.get("COMMONS_DISCORD_CHANNEL") or "").strip()
    parent = (thread_id or os.environ.get("COMMONS_DISCORD_THREAD_ID") or "").strip()
    if not webhook and not token:
        raise SystemExit("DARK: no DISCORD_BOT_TOKEN and no webhook")
    destination = _destination(webhook, dest, parent)
    journal = DeliveryJournal(journal_path)
    delivery_id = _delivery_id(parts, source_id, destination)
    started_in_thread = bool(parent)
    try:
        with _delivery_lock(journal.path, delivery_id):
            journal.prepare(parts, source_id, destination)
            for i, text in enumerate(parts):
                state, value = journal.start(delivery_id, i)
                if state == "confirmed":
                    mid = value
                else:
                    data: dict = {"content": text}
                    if parent:
                        data["message_reference"] = {"message_id": parent}
                    headers = {"Content-Type": "application/json"}
                    if webhook:
                        url_parts = urllib.parse.urlsplit(webhook)
                        query = [(k, v) for k, v in urllib.parse.parse_qsl(url_parts.query, keep_blank_values=True)
                                 if k != "wait"]
                        query.append(("wait", "true"))
                        url = urllib.parse.urlunsplit(url_parts._replace(query=urllib.parse.urlencode(query)))
                    else:
                        url = "%s/channels/%s/messages" % (API, dest)
                        headers["Authorization"] = "Bot " + token
                    try:
                        row = _post_json(url, data, headers)
                        mid = str(row.get("id") or "")
                        if not mid.isascii() or not mid.isdigit():
                            raise DeliveryError("Discord returned no numeric message ID")
                    except BaseException as exc:
                        rejected = isinstance(exc, DiscordHTTPError) and exc.status in {
                            400, 401, 403, 404, 405, 413, 415, 429,
                        }
                        code = f"HTTP_{exc.status}" if isinstance(exc, DiscordHTTPError) else type(exc).__name__
                        journal.finish(delivery_id, i, value, error_code=code, rejected=rejected)
                        outcome = "pending after provider rejection" if rejected else "uncertain; reconcile before resuming"
                        raise DeliveryError(f"Delivery {delivery_id} part {i + 1}: {code}; {outcome}") from None
                    try:
                        journal.finish(delivery_id, i, value, message_id=mid)
                    except (sqlite3.Error, DeliveryError) as exc:
                        raise DeliveryError(
                            f"Discord message {mid} was accepted for delivery {delivery_id} part {i + 1}; "
                            "journal confirmation needs reconciliation"
                        ) from exc
                receipts.append(mid)
                if not webhook and i == 0 and not started_in_thread and len(parts) > 1:
                    parent = mid
    finally:
        journal.close()
    return receipts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Mirror Commons files with durable Discord delivery state")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("format", "send", "prepare", "status"):
        sub = commands.add_parser(command)
        sub.add_argument("file", type=Path)
        sub.add_argument("--journal")
        sub.add_argument("--channel", default="")
        sub.add_argument("--thread-id", default="")
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("delivery_id")
    reconcile.add_argument("part", type=int, help="1-based part number from status")
    choice = reconcile.add_mutually_exclusive_group(required=True)
    choice.add_argument("--message-id", default="")
    choice.add_argument("--not-sent", action="store_true")
    reconcile.add_argument("--evidence", required=True, help="provider observation locator; only its hash is stored")
    reconcile.add_argument("--journal")
    args = parser.parse_args(argv[1:])
    journal = None
    try:
        if args.command == "reconcile":
            journal = DeliveryJournal(args.journal)
            print(json.dumps(journal.reconcile(args.delivery_id, args.part, args.message_id, args.evidence)))
            return 0
        source = args.file.read_bytes()
        raw = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        parts = format_mirror(args.file, raw)
        if args.command == "format":
            for i, p in enumerate(parts):
                sys.stdout.write("--- part %s/%s (%s chars) ---\n%s\n" % (i + 1, len(parts), len(p), p))
            return 0
        source_id = post_id(args.file) + ":" + hashlib.sha256(source).hexdigest()
        return _run_delivery(args, parts, source_id)
    except (DeliveryError, sqlite3.Error, OSError, ValueError) as exc:
        sys.stderr.write(f"Discord mirror: {exc}\n")
        return 2
    finally:
        if journal is not None:
            journal.close()


def _run_delivery(args: argparse.Namespace, parts: list[str], source_id: str) -> int:
    token = (
        os.environ.get("DISCORD_BOT_TOKEN")
        or os.environ.get("COMMONS_DISCORD_BOT_TOKEN")
        or ""
    ).strip()
    webhook = (
        os.environ.get("DISCORD_WEBHOOK_URL")
        or os.environ.get("COMMONS_DISCORD_WEBHOOK_URL")
        or ""
    ).strip()
    if args.command == "send" and not token and not webhook:
        sys.stdout.write("DARK: no DISCORD_BOT_TOKEN and no DISCORD_WEBHOOK_URL. Lane idle.\n")
        return 0
    channel = (args.channel or os.environ.get("COMMONS_DISCORD_CHANNEL") or "").strip()
    parent = (args.thread_id or os.environ.get("COMMONS_DISCORD_THREAD_ID") or "").strip()
    # Source bytes and the formatted payload were read once. Even a change to
    # non-displayed source metadata starts a new delivery generation.
    if args.command in {"prepare", "status"}:
        destination = _destination(webhook, channel, parent)
        journal = DeliveryJournal(args.journal)
        try:
            delivery_id = _delivery_id(parts, source_id, destination)
            if args.command == "prepare":
                with _delivery_lock(journal.path, delivery_id):
                    journal.prepare(parts, source_id, destination)
            status = journal.status(delivery_id)
            print(json.dumps(status))
            return 2 if status["state"] == "uncertain" else 0
        finally:
            journal.close()
    receipts = send_parts(parts, token=token, webhook=webhook, channel=channel,
                          thread_id=parent, source_id=source_id, journal_path=args.journal)
    if not receipts:
        return 0
    sys.stdout.write("sent id=" + ",".join(receipts) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
