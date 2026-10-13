"""Optional operational metadata export; full source stays in local custody.

Run ``python -m integrations.swarm_telemetry.posthog_export --help``.
Native bindings may consume the private batch/query files or use Journal directly.
No collector, schedule, account, person profile, or background worker is created.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.error
from urllib.parse import quote, urlsplit
import urllib.request
import uuid


EVENT = "commons_swarm_operation"
DISTINCT_ID = "commons-swarm-operations"
MAX_BATCH = 500
QUERY_COLUMNS = (
    "event_uuid", "event", "timestamp", "distinct_id",
    "source_event_id_sha256", "operation_id_sha256",
)
OPERATION_TYPES = frozenset((
    "operation", "operation_started", "operation_completed", "operation_failed",
    "request", "request_completed", "request_failed", "tool_call", "tool_result",
    "pr_merged", "pr_activity", "activity", "github_source_response", "native_service_response",
    "merge", "merged", "artifact", "artifact_published", "result",
    "result_available", "completion", "rate_limit", "rate_limited", "cache_hit",
    "service_recovery", "service_recovered", "usage",
))
PROVIDERS = frozenset((
    "github", "slack", "openai", "grok", "xai", "gemini", "google", "anthropic",
    "claude", "cursor", "local", "posthog", "railway", "vercel", "netlify",
    "stripe", "bountyhub", "unknown",
))
SOURCES = PROVIDERS | {"transcript", "gateway", "runtime", "observation", "provider"}
STATUSES = frozenset((
    "observed", "pending", "queued", "running", "started", "completed", "complete",
    "succeeded", "success", "done", "failed", "error", "cancelled", "canceled", "merged",
    "closed", "available", "published", "rate_limit", "rate_limited", "deferred",
    "uncertain", "throttled", "recovered", "unknown",
))
NUMERIC_METRICS = (
    "duration_ms", "latency_ms", "request_count", "attempt_count", "retry_after_seconds",
)
SECRET = re.compile(r"(?i)(?:^(?:sk|ghp|gho|github_pat|xox[baprs])[-_]|bearer|password|secret|api[_-]?key|access[_-]?token)")


class ExportError(RuntimeError):
    """Messages are fixed codes, never provider bodies, credentials or paths."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ExportError("recorded_timestamp_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExportError("recorded_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ExportError("recorded_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def label(value, allowed):
    text = value.lower().replace("-", "_") if isinstance(value, str) else "unknown"
    return text if text in allowed else "other"


def project_event(row):
    """Project only recognized operational fields, never arbitrary source text."""
    event_type = label(row.get("event_type"), OPERATION_TYPES)
    if event_type == "other":
        return None
    source_id = row.get("event_id")
    if not isinstance(source_id, str) or not source_id:
        raise ExportError("stable_source_event_id_required")
    properties = {
        "$process_person_profile": False,
        "source_event_id_sha256": digest(source_id),
        "observed_at": timestamp(row.get("observed_at")),
        "source": label(row.get("source"), SOURCES),
        "provider": label(row.get("provider"), PROVIDERS),
        "event_type": event_type,
        "status": label(row.get("status"), STATUSES),
    }
    operation = row.get("operation_id")
    if isinstance(operation, str) and operation:
        properties["operation_id_sha256"] = digest(operation)
    capability = row.get("capability")
    if (isinstance(capability, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,159}", capability)
            and not SECRET.search(capability)):
        properties["capability"] = capability
    metrics = row.get("metrics")
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except ValueError:
            metrics = None
    if isinstance(metrics, dict) and metrics.get("basis", "observed") == "observed":
        for key in NUMERIC_METRICS + ("cache_hit",):
            value = metrics.get(key)
            if isinstance(value, dict):
                if value.get("basis") != "observed":
                    continue
                value = value.get("value")
            if key == "cache_hit":
                if isinstance(value, bool):
                    properties[key] = value
            elif type(value) in (int, float) and 0 <= value <= 10**18 and math.isfinite(value):
                if key.endswith("_count") and (type(value) is not int):
                    continue
                properties[key] = value
    artifact = row.get("public_artifact")
    if isinstance(artifact, str):
        try:
            artifact = json.loads(artifact)
        except ValueError:
            artifact = None
    if isinstance(artifact, dict) and artifact.get("visibility") == "public":
        value = artifact.get("url")
        if isinstance(value, str) and len(value) <= 1000:
            try:
                parsed = urlsplit(value)
                if (parsed.scheme == "https" and parsed.hostname and not parsed.username
                        and not parsed.password and not parsed.query and not parsed.fragment
                        and not SECRET.search(value)):
                    properties["public_artifact_url"] = value
            except ValueError:
                pass
    return {
        "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, "commons-swarm-event:" + source_id)),
        "event": EVENT, "distinct_id": DISTINCT_ID,
        "timestamp": timestamp(row.get("occurred_at")), "properties": properties,
    }


def bound(value):
    if type(value) is not int or not 1 <= value <= MAX_BATCH:
        raise ExportError("limit_must_be_1_to_500")
    return value


def build_retention_query(events):
    if not events:
        raise ExportError("no_events_to_reconcile")
    bound(len(events))
    times = [datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")) for event in events]
    start = min(times).replace(hour=0, minute=0, second=0, microsecond=0)
    end = max(times).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    values = {"event_name": EVENT, "distinct_id": DISTINCT_ID,
              "from_utc": start.strftime("%Y-%m-%d %H:%M:%S"),
              "to_utc": end.strftime("%Y-%m-%d %H:%M:%S")}
    ids = []
    for index, event in enumerate(events):
        key = f"uuid_{index}"
        values[key] = event["uuid"]
        ids.append("toUUID({" + key + "})")
    sql = """SELECT DISTINCT toString(uuid) AS event_uuid, event, timestamp, distinct_id,
properties.source_event_id_sha256 AS source_event_id_sha256,
properties.operation_id_sha256 AS operation_id_sha256
FROM events WHERE event={event_name} AND distinct_id={distinct_id}
AND timestamp >= toDateTime({from_utc}) AND timestamp < toDateTime({to_utc})
AND uuid IN (""" + ",".join(ids) + f") LIMIT {len(events) + 1}"
    return {"query": {"kind": "HogQLQuery", "query": sql, "values": values},
            "refresh": "force_blocking", "name": "commons swarm export reconciliation"}


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with self.connect() as db:
            existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existing and "posthog_export_meta" not in existing:
                raise ExportError("journal_contains_other_schema")
            os.chmod(self.path, 0o600)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS posthog_export_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS posthog_export_outbox (
                    event_uuid TEXT PRIMARY KEY, source_seq INTEGER NOT NULL, event_json TEXT NOT NULL,
                    envelope_sha256 TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT, last_query_at TEXT, replay_attempt INTEGER,
                    retained_at TEXT, error_code TEXT);
                CREATE INDEX IF NOT EXISTS posthog_export_pending ON posthog_export_outbox(state,source_seq);
                CREATE TABLE IF NOT EXISTS posthog_export_queries (
                    query_sha256 TEXT PRIMARY KEY, request_json TEXT NOT NULL, scope_json TEXT NOT NULL,
                    issued_at TEXT NOT NULL, completed_at TEXT, response_sha256 TEXT);
            """)
            db.execute("INSERT OR IGNORE INTO posthog_export_meta VALUES ('schema','1')")
            if self._get(db, "schema") != "1":
                raise ExportError("journal_schema_unsupported")

    def connect(self):
        class Connection(sqlite3.Connection):
            def __exit__(self, *arguments):
                try:
                    return super().__exit__(*arguments)
                finally:
                    self.close()
        db = sqlite3.connect(self.path, timeout=10, factory=Connection)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _get(db, key, default=None):
        row = db.execute("SELECT value FROM posthog_export_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def _set(db, key, value):
        db.execute("INSERT OR REPLACE INTO posthog_export_meta VALUES (?,?)", (key, str(value)))

    def _bind(self, db, project_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ExportError("existing_project_reference_required")
        value = digest(project_id)
        previous = self._get(db, "destination")
        if previous is not None and previous != value:
            raise ExportError("journal_destination_changed_use_separate_journal")
        self._set(db, "destination", value)

    def prepare(self, source_db, limit=100):
        limit = bound(limit)
        source = Path(source_db).resolve(strict=True)
        if source == self.path.resolve():
            raise ExportError("source_and_export_journal_must_differ")
        source_key = digest(str(source))
        counts = {"read": 0, "staged": 0, "already_staged": 0, "excluded": 0, "invalid": 0}
        uri = "file:" + quote(str(source), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as origin, self.connect() as db:
            origin.row_factory = sqlite3.Row
            origin.execute("BEGIN")
            db.execute("BEGIN IMMEDIATE")
            prior_source = self._get(db, "source")
            if prior_source is not None and prior_source != source_key:
                raise ExportError("source_database_changed_use_separate_journal")
            cursor = int(self._get(db, "cursor", "0"))
            if cursor:
                prior = origin.execute("SELECT event_id FROM events WHERE seq=?", (cursor,)).fetchone()
                if prior is None or digest(prior[0]) != self._get(db, "cursor_event"):
                    raise ExportError("source_cursor_identity_changed")
            # The SQL projection never selects summaries, full payloads, source
            # records, conversations, account IDs, session IDs or private paths.
            rows = origin.execute("""SELECT seq,event_id,source,occurred_at,observed_at,
                event_type,provider,operation_id,status,
                json_extract(payload,'$.metrics') AS metrics,
                json_extract(payload,'$.metadata.capability') AS capability,
                json_extract(payload,'$.metadata.public_artifact') AS public_artifact
                FROM events WHERE seq>? ORDER BY seq LIMIT ?""", (cursor, limit))
            for row in rows:
                counts["read"] += 1
                try:
                    event = project_event(dict(row))
                except ExportError:
                    event = None
                    counts["invalid"] += 1
                else:
                    if event is None:
                        counts["excluded"] += 1
                if event is not None:
                    payload = canonical(event)
                    outcome = db.execute("""INSERT OR IGNORE INTO posthog_export_outbox
                        (event_uuid,source_seq,event_json,envelope_sha256,state) VALUES (?,?,?,?, 'pending')""",
                        (event["uuid"], row["seq"], payload, digest(payload)))
                    counts["staged" if outcome.rowcount else "already_staged"] += 1
                cursor = row["seq"]
                self._set(db, "cursor_event", digest(row["event_id"]))
            self._set(db, "source", source_key)
            self._set(db, "cursor", cursor)
            for key in counts:
                self._set(db, "total_" + key, int(self._get(db, "total_" + key, "0")) + counts[key])
        return {"ok": True, "cursor": cursor, **counts}

    def status(self):
        with self.connect() as db:
            states = {row[0]: row[1] for row in db.execute(
                "SELECT state,count(*) FROM posthog_export_outbox GROUP BY state")}
            replayable = db.execute("""SELECT count(*) FROM posthog_export_outbox
                WHERE state='uncertain' AND replay_attempt=attempts""").fetchone()[0]
            return {"ok": True, "cursor": int(self._get(db, "cursor", "0")), "states": states,
                    "replayable_after_explicit_decision": replayable,
                    "capture_not_before": self._get(db, "capture_not_before"),
                    "query_not_before": self._get(db, "query_not_before"),
                    "capture_last_error": self._get(db, "capture_last_error"),
                    "query_last_error": self._get(db, "query_last_error"),
                    "query_budget_remaining_bytes": self._get(db, "query_query_budget_remaining_bytes"),
                    "totals": {key: int(self._get(db, "total_" + key, "0"))
                               for key in ("read", "staged", "already_staged", "excluded", "invalid")}}

    def batch(self, project_id, limit=100, replay_uncertain=False):
        limit = bound(limit)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._bind(db, project_id)
            cutoff = self._get(db, "capture_not_before")
            if cutoff and cutoff > now():
                db.execute("UPDATE posthog_export_outbox SET state='deferred' WHERE state='pending'")
                return {"batch": [], "deferred_until": cutoff}
            condition = "state='uncertain' AND replay_attempt=attempts" if replay_uncertain else "state IN ('pending','deferred')"
            rows = db.execute("SELECT * FROM posthog_export_outbox WHERE " + condition + " ORDER BY source_seq LIMIT ?", (limit,)).fetchall()
            events = []
            for row in rows:
                if digest(row["event_json"]) != row["envelope_sha256"]:
                    raise ExportError("journal_envelope_changed")
                events.append(json.loads(row["event_json"]))
                # Commit before exposing bytes to any caller or transport.
                db.execute("""UPDATE posthog_export_outbox SET state='uncertain', attempts=attempts+1,
                    last_attempt_at=?, last_query_at=NULL, replay_attempt=NULL, error_code=NULL WHERE event_uuid=?""",
                    (now(), row["event_uuid"]))
        return {"batch": events}

    def query(self, project_id, limit=100):
        limit = bound(limit)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._bind(db, project_id)
            cutoff = self._get(db, "query_not_before")
            if cutoff and cutoff > now():
                raise ExportError("query_deferred_by_provider_retry_after")
            rows = db.execute("""SELECT event_uuid,event_json,envelope_sha256,attempts FROM posthog_export_outbox
                WHERE state='uncertain' ORDER BY last_query_at IS NOT NULL,last_query_at,source_seq LIMIT ?""", (limit,)).fetchall()
            if any(digest(row["event_json"]) != row["envelope_sha256"] for row in rows):
                raise ExportError("journal_envelope_changed")
            events = [json.loads(row["event_json"]) for row in rows]
            request = build_retention_query(events)
            # A new read gets a new benign name so a native operation journal
            # cannot return an earlier request's complete-but-old response.
            request["name"] += " " + uuid.uuid4().hex
            encoded = canonical(request)
            scope = {row["event_uuid"]: {"attempt": row["attempts"], "envelope_sha256": row["envelope_sha256"]} for row in rows}
            db.execute("INSERT INTO posthog_export_queries VALUES (?,?,?,?,NULL,NULL)",
                       (digest(encoded), encoded, canonical(scope), now()))
        return request

    def reconcile(self, request, response):
        encoded = canonical(request)
        if not isinstance(request, dict) or request.get("refresh") != "force_blocking":
            raise ExportError("fresh_query_required")
        if not isinstance(response, dict) or response.get("is_cached") is not False:
            raise ExportError("query_freshness_unconfirmed")
        status = response.get("query_status")
        if (response.get("error") or response.get("isError") or response.get("hasMore") is True
                or isinstance(status, dict) and (status.get("complete") is not True or status.get("error"))):
            raise ExportError("query_incomplete_or_failed")
        if response.get("columns") != list(QUERY_COLUMNS) or not isinstance(response.get("results"), list):
            raise ExportError("query_projection_unconfirmed")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            query = db.execute("SELECT * FROM posthog_export_queries WHERE query_sha256=?", (digest(encoded),)).fetchone()
            if query is None or query["request_json"] != encoded:
                raise ExportError("unknown_retention_query")
            if query["completed_at"] is not None:
                if query["response_sha256"] != digest(canonical(response)):
                    raise ExportError("query_response_changed")
                return {"ok": True, "already_reconciled": True, "retained": 0}
            scope = json.loads(query["scope_json"])
            if len(response["results"]) > len(scope):
                raise ExportError("query_scope_inconsistent")
            expected = {}
            for event_uuid, version in scope.items():
                row = db.execute("SELECT * FROM posthog_export_outbox WHERE event_uuid=?", (event_uuid,)).fetchone()
                if (row is None or row["envelope_sha256"] != version["envelope_sha256"]
                        or digest(row["event_json"]) != row["envelope_sha256"]):
                    raise ExportError("journal_envelope_changed")
                expected[event_uuid] = (row, json.loads(row["event_json"]))
            retained = set()
            for values in response["results"]:
                if not isinstance(values, list) or len(values) != len(QUERY_COLUMNS) or values[0] not in expected:
                    raise ExportError("query_row_outside_scope")
                event = expected[values[0]][1]
                properties = event["properties"]
                if (values[1] != EVENT or timestamp(values[2]) != event["timestamp"] or values[3] != DISTINCT_ID
                        or values[4] != properties["source_event_id_sha256"]
                        or values[5] != properties.get("operation_id_sha256")):
                    raise ExportError("query_event_identity_mismatch")
                retained.add(values[0])
            checked = now()
            unchanged_attempts = 0
            for event_uuid, (row, event) in expected.items():
                if event_uuid in retained:
                    db.execute("""UPDATE posthog_export_outbox SET state='retained',retained_at=?,
                        last_query_at=?,replay_attempt=NULL,error_code=NULL WHERE event_uuid=?""", (checked, checked, event_uuid))
                elif row["state"] == "uncertain" and row["attempts"] == scope[event_uuid]["attempt"]:
                    # Absence means only not visible now. It never sends or
                    # requeues automatically; an explicit replay decision is separate.
                    db.execute("UPDATE posthog_export_outbox SET last_query_at=?,replay_attempt=attempts WHERE event_uuid=?", (checked, event_uuid))
                    unchanged_attempts += 1
            db.execute("UPDATE posthog_export_queries SET completed_at=?,response_sha256=? WHERE query_sha256=?",
                       (checked, digest(canonical(response)), digest(encoded)))
        return {"ok": True, "retained": len(retained), "not_visible_at_query": len(scope) - len(retained),
                "replayable_after_explicit_decision": unchanged_attempts, "automatic_replays": 0}

    def provider_failure(self, kind, error, events=()):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._set(db, kind + "_last_error", error.code)
            if error.remaining_bytes is not None:
                self._set(db, kind + "_query_budget_remaining_bytes", error.remaining_bytes)
            if error.retry_after is not None:
                cutoff = (datetime.now(timezone.utc) + timedelta(seconds=error.retry_after)).isoformat().replace("+00:00", "Z")
                previous = self._get(db, kind + "_not_before")
                self._set(db, kind + "_not_before", max(cutoff, previous or cutoff))
            if kind == "capture" and error.retry_after is not None:
                db.execute("UPDATE posthog_export_outbox SET state='deferred' WHERE state='pending'")
            for event in events:
                db.execute("UPDATE posthog_export_outbox SET error_code=? WHERE event_uuid=? AND state='uncertain'",
                           (error.code, event["uuid"]))


class ProviderError(ExportError):
    def __init__(self, code, retry_after=None, remaining_bytes=None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.remaining_bytes = remaining_bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _endpoint(host, suffix):
    parsed = urlsplit(host)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ExportError("provider_https_origin_required")
    return host.rstrip("/") + suffix


def _post(url, body, headers=None, expect_json=True):
    request = urllib.request.Request(url, data=canonical(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1) if expect_json else b""
    except urllib.error.HTTPError as error:
        value = error.headers.get("Retry-After", "")
        delay = int(value) if re.fullmatch(r"[0-9]{1,10}", value) else None
        if delay is None and value:
            try:
                delay = max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
        remaining = error.headers.get("X-PostHog-Query-Budget-Remaining-Bytes", "")
        remaining = int(remaining) if re.fullmatch(r"[0-9]{1,20}", remaining) else None
        error.close()
        raise ProviderError("provider_http_" + str(error.code), delay, remaining) from None
    except (urllib.error.URLError, OSError):
        raise ProviderError("provider_transport_outcome_uncertain") from None
    if len(raw) > 4 * 1024 * 1024:
        raise ProviderError("provider_query_response_too_large")
    if not expect_json:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        raise ProviderError("provider_query_response_invalid") from None


def private_write(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "status", "batch", "query", "reconcile", "submit", "query-live"):
        child = commands.add_parser(name)
        child.add_argument("--journal", required=True)
        if name in ("prepare", "batch", "query", "submit", "query-live"):
            child.add_argument("--limit", type=int, default=100)
        if name in ("batch", "query", "submit", "query-live"):
            child.add_argument("--project-id", required=True)
        if name in ("batch", "query"):
            child.add_argument("--output", required=True)
        if name in ("batch", "submit"):
            child.add_argument("--replay-uncertain", action="store_true")
        if name == "prepare":
            child.add_argument("--source-db", required=True)
        if name == "reconcile":
            child.add_argument("--query-file", required=True)
            child.add_argument("--response-file", required=True)
        if name == "submit":
            child.add_argument("--capture-host", required=True)
            child.add_argument("--project-key-env", default="POSTHOG_PROJECT_API_KEY")
        if name == "query-live":
            child.add_argument("--query-host", required=True)
            child.add_argument("--query-key-env", default="POSTHOG_PERSONAL_API_KEY")
    args = parser.parse_args(argv)
    try:
        journal = Journal(args.journal)
        if args.command == "prepare":
            result = journal.prepare(args.source_db, args.limit)
        elif args.command == "status":
            result = journal.status()
        elif args.command == "batch":
            result = journal.batch(args.project_id, args.limit, args.replay_uncertain)
            private_write(args.output, result)
            result = {"ok": True, "exported": len(result["batch"]), "state": "uncertain" if result["batch"] else "empty_or_deferred"}
        elif args.command == "query":
            result = journal.query(args.project_id, args.limit)
            private_write(args.output, result)
            result = {"ok": True, "query_prepared": True}
        elif args.command == "reconcile":
            result = journal.reconcile(load_json(args.query_file), load_json(args.response_file))
        elif args.command == "submit":
            key = os.environ.get(args.project_key_env)
            if not key:
                raise ExportError("existing_project_key_reference_unavailable")
            endpoint = _endpoint(args.capture_host, "/batch/")
            packet = journal.batch(args.project_id, args.limit, args.replay_uncertain)
            events = packet["batch"]
            if events:
                try:
                    _post(endpoint, {"api_key": key, "batch": events}, expect_json=False)
                except ProviderError as error:
                    journal.provider_failure("capture", error, events)
                    raise
            result = {"ok": True, "acknowledged": len(events), "retained": 0, "state": "uncertain" if events else "empty_or_deferred"}
        else:
            key = os.environ.get(args.query_key_env)
            if not key:
                raise ExportError("existing_query_key_reference_unavailable")
            endpoint = _endpoint(args.query_host, "/api/projects/" + quote(args.project_id, safe="") + "/query/")
            request = journal.query(args.project_id, args.limit)
            try:
                response = _post(endpoint, request, {"Authorization": "Bearer " + key})
            except ProviderError as error:
                journal.provider_failure("query", error)
                raise
            result = journal.reconcile(request, response)
        print(canonical(result))
        return 0
    except (ExportError, OSError, sqlite3.Error, ValueError, TypeError) as error:
        message = str(error) if isinstance(error, ExportError) else type(error).__name__
        print(canonical({"ok": False, "error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
