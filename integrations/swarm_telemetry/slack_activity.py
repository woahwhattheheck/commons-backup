"""Whole-page Slack reads and durable history/thread/file source jobs.

Source capture is exact and private; the host SourceEngine owns encryption and
ingest. This module never sends a message, changes account state, or executes
anything found in a source. Every current/future peer can execute pending jobs
through the existing direct service tools without an acknowledgement gate.
"""
from __future__ import annotations

import hashlib
import base64
import json
import math
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from .notifications import redact

HISTORY_TOOL = "mcp__codex_apps__slack_slack_read_channel"
THREAD_TOOL = "mcp__codex_apps__slack_slack_read_thread"
FILE_TOOL = "mcp__codex_apps__slack_slack_read_file"
_TS = re.compile(r"^\d{9,}\.\d+$")


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def capture_native_chunk(path, index, total, part, *, account_ref, workspace_id=None):
    """Receive exact native data in bounded chunks without plaintext files.

    This transports a large existing native response around Windows command
    length limits. Each intermediate chunk is encrypted immediately. Final
    assembly occurs in memory and produces the ordinary native snapshot format.
    """
    from .discovery import _dpapi, save_native_snapshot
    destination = Path(path)
    descriptor = json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else {}
    if descriptor.get("source_capture_status") != "assembling_encrypted_chunks":
        descriptor = {"source_capture_status": "assembling_encrypted_chunks", "account_ref": account_ref,
                      "workspace_id": workspace_id, "total_chunks": total, "chunks": {}, "complete": False}
    if descriptor["total_chunks"] != total:
        raise SourceReadError("native_capture_chunk_count_conflict")
    descriptor["chunks"][str(index)] = base64.b64encode(_dpapi(part.encode("utf-8"))).decode("ascii")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(descriptor), encoding="utf-8")
    if len(descriptor["chunks"]) == total:
        raw = b"".join(_dpapi(base64.b64decode(descriptor["chunks"][str(number)]), decrypt=True) for number in range(total))
        result = save_native_snapshot(destination, payload=json.loads(raw.decode("utf-8")), service="slack", account_ref=account_ref, workspace_id=workspace_id, complete=False)
        return {"capture_complete": True, "source_envelope_sha256": result["source_envelope_sha256"], "source_envelope_bytes": result["source_envelope_bytes"]}
    return {"capture_complete": False, "received_chunks": len(descriptor["chunks"]), "total_chunks": total}


def _timestamp(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _unwrap(value):
    for _ in range(12):
        if isinstance(value, Mapping) and (value.get("isError") or value.get("ok") is False or value.get("error")):
            raise SourceReadError(str(value.get("error") or "native_source_read_error"))
        if isinstance(value, Mapping) and isinstance(value.get("structuredContent"), (dict, list)):
            value = value["structuredContent"]
        elif isinstance(value, Mapping) and isinstance(value.get("result"), (dict, list)):
            value = value["result"]
        elif isinstance(value, Mapping) and isinstance(value.get("content"), list):
            texts = [block["text"] for block in value["content"] if block.get("type") == "text"]
            if not texts:
                return value
            try:
                value = json.loads(texts[0])
            except ValueError:
                return {"formatted_source": "\n".join(texts)}
        else:
            return value
    return value


class SourceReadError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code if re.fullmatch(r"[A-Za-z0-9_:-]{1,120}", code) else "source_read_failed"


def _provider_retry_seconds(value):
    """Retain numeric provider retry hints across native transport envelopes."""
    delays = []
    for _ in range(12):
        if not isinstance(value, Mapping):
            break
        for metadata in (value, value.get("error_data")):
            if not isinstance(metadata, Mapping):
                continue
            for fields in (metadata, metadata.get("headers")):
                if not isinstance(fields, Mapping):
                    continue
                for key in ("retry_after_seconds", "retry_after", "Retry-After", "retry-after"):
                    hint = fields.get(key)
                    if isinstance(hint, bool):
                        continue
                    try:
                        seconds = float(hint)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if math.isfinite(seconds) and seconds >= 0:
                        delays.append(seconds)
        if isinstance(value.get("structuredContent"), Mapping):
            value = value["structuredContent"]
        elif isinstance(value.get("result"), Mapping):
            value = value["result"]
        elif isinstance(value.get("content"), list):
            texts = [block["text"] for block in value["content"]
                     if isinstance(block, Mapping) and block.get("type") == "text" and isinstance(block.get("text"), str)]
            try:
                value = json.loads(texts[0]) if texts else None
            except (ValueError, RecursionError):
                break
        else:
            break
    return max(delays) if delays else None


def _page(value):
    """Parse supplied native/API fields, retaining complete formatted blocks."""
    value = _unwrap(value)
    if not isinstance(value, Mapping):
        return [], None, False, {"parse_state": "source_schema_pending"}
    rows = value.get("messages")
    if rows is None:
        rows = next((value[field] for field in ("thread_messages", "thread", "events")
                     if value.get(field) is not None), None)
    parsed_empty = False
    page_counts = {}
    if isinstance(rows, list):
        messages = [{**row["event"], "native_event_source": dict(row)} if isinstance(row.get("event"), Mapping) else dict(row) for row in rows if isinstance(row, Mapping)]
    else:
        text = rows if isinstance(rows, str) else value.get("formatted_source") or value.get("result") or value.get("text")
        messages = []
        if isinstance(text, str):
            # The native channel reader represents an empty page as its
            # channel header alone. A nonempty unknown format is still unread.
            parsed_empty = bool(re.fullmatch(r"Channel: [^\n]+ \([CGD][A-Z0-9]{7,}\)\s*", text.strip()))
            boundaries = list(re.finditer(r"(?m)^=== (?:Message|Reply) from (.*?) ===[^\n]*\nMessage TS:\s*(\d{9,}\.\d+)\s*\n", text))
            for index, marker in enumerate(boundaries):
                end = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(text)
                block = text[marker.start():end]
                body = text[marker.end():end]
                sender = re.search(r"\(([UW][A-Z0-9]+)\)\s+at\s", marker.group(1))
                thread = re.search(r"(?m)^Thread:\s*(\d+)\s+replies?", body)
                thread_ts = re.search(r"(?m)^(?:Thread TS|Thread timestamp|Parent TS):\s*(\d{9,}\.\d+)", body)
                files = []
                for file_line in re.finditer(r"(?m)^(?:Files?|Attachments?):\s*(.+)$", body):
                    for fid in re.finditer(r"(?:ID:\s*|\bfile_id[=:]\s*)(F[A-Z0-9]{7,})", file_line.group(1)):
                        files.append({"id": fid.group(1), "formatted_metadata": file_line.group(0)})
                messages.append({"ts": marker.group(2), "user": sender.group(1) if sender else None,
                                 "text": body, "thread_ts": thread_ts.group(1) if thread_ts else None,
                                 "reply_count": int(thread.group(1)) if thread else 0, "files": files,
                                 "native_formatted_source": block, "source_format": "native_formatted_projection"})
            if not boundaries:
                thread_markers = list(re.finditer(r"(?m)^(?:=== THREAD PARENT MESSAGE ===|--- Reply \d+ of \d+ ---)\s*\nFrom:\s*(.*?)\nTime:\s*([^\n]*)\nMessage TS:\s*(\d{9,}\.\d+)\s*\n", text))
                parent_ts = thread_markers[0].group(3) if thread_markers else None
                reply_total = re.search(r"=== THREAD REPLIES \((\d+) total\) ===", text)
                if reply_total:
                    declared = int(reply_total.group(1))
                    returned = sum(marker.group(0).startswith("--- Reply ") for marker in thread_markers)
                    page_counts = {"declared_replies": declared, "normalized_replies": returned,
                                   "native_page_complete": returned == declared}
                for index, marker in enumerate(thread_markers):
                    end = thread_markers[index + 1].start() if index + 1 < len(thread_markers) else len(text)
                    block, body = text[marker.start():end], text[marker.end():end]
                    sender = re.search(r"\(([UW][A-Z0-9]+)\)", marker.group(1))
                    files = [{"id": fid.group(1), "formatted_metadata": line.group(0)}
                             for line in re.finditer(r"(?m)^(?:Files?|Attachments?):\s*(.+)$", body)
                             for fid in re.finditer(r"ID:\s*(F[A-Z0-9]{7,})", line.group(1))]
                    messages.append({"ts": marker.group(3), "user": sender.group(1) if sender else None, "text": body,
                                     "thread_ts": parent_ts, "reply_count": int(reply_total.group(1)) if index == 0 and reply_total else 0,
                                     "files": files, "native_formatted_source": block, "source_format": "native_formatted_projection"})
    metadata = value.get("response_metadata") if isinstance(value.get("response_metadata"), Mapping) else {}
    if "next_cursor" in metadata:
        cursor = str(metadata.get("next_cursor") or "")
        terminal = not cursor and not value.get("has_more", False)
    elif "next_cursor" in value:
        cursor = str(value.get("next_cursor") or "")
        terminal = not cursor and not value.get("has_more", False)
    elif isinstance(value.get("pagination_info"), str):
        pagination = value["pagination_info"]
        next_page = re.search(r"(?:use\s+cursor|next_cursor|cursor)\s*[:=]\s*`?([^`\s]+)", pagination, re.I)
        if next_page:
            cursor, terminal = next_page.group(1), False
        elif re.search(r"\b(?:no more (?:messages|pages)|end of results)\b", pagination, re.I):
            # Check the explicit end marker before its contained phrase
            # "more messages available", or empty tails never finish.
            cursor, terminal = "", True
        elif re.search(r"more messages available|next page|has_more.{0,5}true", pagination, re.I):
            cursor, terminal = "", False
        else:
            cursor, terminal = None, False
    elif value.get("has_more") is False:
        cursor, terminal = "", True
    elif isinstance(rows, list) and len(rows) < 100 and "has_more" not in value:
        # Raw Slack API usually includes has_more; absent pagination is kept
        # unknown even when a formatter or bridge returns fewer than requested.
        cursor, terminal = None, False
    else:
        cursor, terminal = None, False
    incomplete = page_counts.get("native_page_complete") is False
    return messages, cursor, terminal and not incomplete, {"parse_state": "source_page_incomplete" if incomplete else "parsed" if messages or isinstance(rows, list) or parsed_empty else "source_schema_pending",
                                      "normalized_records": len(messages), "pagination_known": cursor is not None,
                                      "source_pagination": value.get("pagination_info") or metadata, **page_counts}


def _message_revision(message):
    """Hash message content, independently of its history/thread read wrapper.

    Exact envelopes and formatted blocks remain in source custody. Pagination,
    thread counters and presentation metadata describe the read, not an edit.
    Content, edit timestamps, files, attachments and reactions still contribute
    to the revision so genuine message changes retain distinct event identities.
    """
    inner = message.get("message") if isinstance(message.get("message"), Mapping) else message
    snapshot = dict(inner)
    for field in ("native_formatted_source", "native_event_source", "source_format",
                  "thread_ts", "reply_count", "reply_users", "reply_users_count", "latest_reply",
                  "last_read", "subscribed", "unread_count", "parent_user_id",
                  "user_profile", "bot_profile"):
        snapshot.pop(field, None)
    # History may omit thread_ts even for a broadcast reply. The immutable
    # message timestamp identifies the record; its parent remains in metadata.
    if message.get("source_format") == "native_formatted_projection":
        body = str(snapshot.get("text") or "")
        body = re.sub(r"\n=== THREAD REPLIES \(\d+ total\) ===\s*$", "", body)
        body = re.sub(r"\nThread:\s*\d+\s+repl(?:y|ies)(?:\s+\(latest:[^\r\n]*\))?\s*$", "", body)
        snapshot["text"] = body.rstrip("\r\n")
        snapshot["files"] = [{key: value for key, value in file.items() if key != "formatted_metadata"}
                             if isinstance(file, Mapping) else file for file in snapshot.get("files", [])]
    return _digest("slack-message-content-v1", snapshot)


def _base_event(job, kind, identity, occurred_at, full_source, summary, metadata=None):
    return {"event_id": "slack:" + _digest(job["account_ref"], job.get("workspace_id"), job.get("channel_id"), kind, identity),
            "source": "slack", "source_id": str(identity), "event_type": kind, "occurred_at": occurred_at,
            "observed_at": _now(), "peer_id": None, "session_id": job.get("channel_id"), "agent_id": None, "parent_agent_id": None,
            "provider": "slack", "model": None, "harness": "native-service-connector", "work_id": None, "operation_id": job["job_id"],
            "status": "observed", "summary": redact(str(summary)[:2000]), "url": None, "metrics": {},
            "metadata": {"account_ref": job["account_ref"], "workspace_id": job.get("workspace_id"), "channel_id": job.get("channel_id"),
                         "source_job_id": job["job_id"], "full_source_capture": "exact; host encrypts before persistence", **(metadata or {})},
            "full_source": full_source}


def _request(job):
    if job["kind"] == "file":
        return FILE_TOOL, {"file_id": job["file_id"]}
    args = {"channel_id": job.get("dm_user_id") or job["channel_id"], "limit": job.get("page_limit", 100), "response_format": "detailed"}
    if job.get("cursor"):
        args["cursor"] = job["cursor"]
    if job.get("oldest"):
        args["oldest"] = job["oldest"]
    if job.get("latest"):
        args["latest"] = job["latest"]
    if job["kind"] in {"thread", "thread_tail"}:
        args["message_ts"] = job["thread_ts"]
        return THREAD_TOOL, args
    return HISTORY_TOOL, args


def _thread_page_regressed(job, reply_timestamps):
    """Recognize a cursor traversal reversing its observed reply progress.

    Native thread pages can move in either direction. Their opaque cursors do
    not establish ordering, and the repeated parent is not reply progress.
    Empty terminal pages and inclusive boundary replies remain valid.
    """
    if job["kind"] not in {"thread", "thread_tail"} or not reply_timestamps:
        return False
    oldest, newest = min(reply_timestamps, key=Decimal), max(reply_timestamps, key=Decimal)
    window = {field: job[field] for field in ("oldest", "latest") if field in job}
    previous = job.get("thread_page_progress") if job.get("cursor") else None
    previous = previous if isinstance(previous, Mapping) else {}
    if previous.get("window") != window:
        previous = {}
    direction = previous.get("direction")
    prior_oldest, prior_newest = previous.get("oldest_ts"), previous.get("newest_ts")
    if _TS.fullmatch(str(prior_oldest or "")) and _TS.fullmatch(str(prior_newest or "")):
        forward = Decimal(oldest) >= Decimal(prior_oldest) and Decimal(newest) > Decimal(prior_newest)
        backward = Decimal(newest) <= Decimal(prior_newest) and Decimal(oldest) < Decimal(prior_oldest)
        movement = "forward" if forward else "backward" if backward else None
        if direction and movement and direction != movement:
            return True
        direction = direction or movement
    job["thread_page_progress"] = {"oldest_ts": oldest, "newest_ts": newest, "direction": direction, "window": window}
    return False


def _default_reader(config):
    from .runner import Gateway
    gateway = Gateway(config.get("gateway") or config.get("gateway_url") or "http://127.0.0.1:8878", config.get("timeout_seconds", 25))
    def read(name, args, account_ref):
        if name == FILE_TOOL:
            raise SourceReadError("native_file_reader_binding_pending")
        short = "slack_read_thread" if name == THREAD_TOOL else "slack_read_channel"
        fields = {"channel_id": config.get("_dm_channel_mapping", {}).get(args["channel_id"], args["channel_id"]), "limit": args.get("limit", 100)}
        for field in ("cursor", "oldest", "latest", "response_format"):
            if field in args:
                fields[field] = args[field]
        if "message_ts" in args:
            fields["thread_ts"] = args["message_ts"]
        return gateway.call(short, fields)
    return read


def collect_slack_activity(config=None, state=None, sources=None, read_page=None):
    """Seed/advance all Slack source jobs with round-robin backfill and live tail.

    read_page(tool_name,args,account_ref) returns the untouched actual MCP/API
    envelope. Config slack_page_budget defaults to 4 requests per call. Jobs and
    cursors in returned state are durable host-owned work, not access grants.
    config slack_seed_only creates jobs without issuing provider reads. Existing
    connector_snapshot_paths seed all native conversations; sources can be the
    discovery result or its sources array. Files above native size limits and
    binary references become resumable source jobs through another existing
    direct reader; no source is marked excluded or complete on a partial read.
    config.native_results[job_id] (or native_results.slack[job_id]) forwards an
    already returned actual source envelope once; an unchanged cached page is
    never reused as a different cursor page.
    """
    config, state = dict(config or {}), dict(state or {})
    at = _now()
    jobs = {str(key): dict(value) for key, value in (state.get("jobs") or {}).items()}
    observations = dict(state.get("message_versions") or {})
    coverage, events = [], []
    descriptors = sources.get("sources", []) if isinstance(sources, Mapping) else list(sources or [])
    channel_records = dict(state.get("channels") or {})
    for path in config.get("connector_snapshot_paths", []):
        try:
            from .discovery import load_native_snapshot, _connector_channels
            snapshot = load_native_snapshot(path)
            if snapshot.get("service") != "slack":
                continue
            rows, cursor, complete = _connector_channels(snapshot["payload"])
            for row in rows:
                channel = str(row.get("id") or "")
                ref = str(snapshot.get("account_ref") or "slack:installed-connector-account-unresolved")
                if channel:
                    channel_records[ref + ":" + channel] = {"account_ref": ref, "channel_id": channel, "workspace_id": snapshot.get("workspace_id"), "listing_metadata": row}
            coverage.append({"source": "slack:native-conversation-snapshot", "status": "observed", "complete": complete, "records": len(rows), "cursor": cursor,
                             "observed_at": snapshot.get("observed_at"), "scope": "conversation discovery only; history/thread/file ingestion separate"})
        except Exception as error:
            coverage.append({"source": "slack:native-conversation-snapshot", "status": "pending_recovery", "complete": False, "error": type(error).__name__})
    for descriptor in descriptors:
        if descriptor.get("service") != "slack" and descriptor.get("source") != "slack":
            continue
        channel = descriptor.get("channel_id") or descriptor.get("source_locator")
        if isinstance(channel, str) and re.fullmatch(r"[CGD][A-Z0-9]{7,}", channel):
            ref = str(descriptor.get("account_ref") or "slack:account-unresolved")
            channel_records[ref + ":" + channel] = {"account_ref": ref, "workspace_id": descriptor.get("workspace_id"), "channel_id": channel,
                                                     "listing_metadata": descriptor.get("listing_metadata", {})}
    for channel in config.get("slack_channels", []):
        if re.fullmatch(r"[CGD][A-Z0-9]{7,}", str(channel)):
            ref = str(config.get("slack_account_ref") or "slack:existing-shared-service")
            channel_records.setdefault(ref + ":" + str(channel), {"account_ref": ref, "channel_id": str(channel), "workspace_id": config.get("slack_workspace_id")})

    def add_job(kind, record, **extra):
        identity = _digest(record["account_ref"], record.get("workspace_id"), record.get("channel_id"), kind, extra.get("thread_ts"), extra.get("file_id"))
        job_id = "slack-read:" + identity[:32]
        if job_id not in jobs:
            jobs[job_id] = {"job_id": job_id, "kind": kind, "account_ref": record["account_ref"], "workspace_id": record.get("workspace_id"),
                            "channel_id": record.get("channel_id"), "cursor": "", "status": "pending", "complete": False,
                            "pages_read": 0, "records_read": 0, "last_attempt_at": None, "next_attempt_epoch": 0,
                            "dm_user_id": record.get("dm_user_id") or (record.get("listing_metadata", {}).get("user_id") if record.get("listing_metadata", {}).get("is_im") else None), **extra}
            name, args = _request(jobs[job_id])
            jobs[job_id]["reader"] = {"tool_name": name, "arguments": args, "account_ref": record["account_ref"], "mode": "read_only", "acknowledgement_required": False, "credential_grant_required": False}
        return jobs[job_id]

    for record in channel_records.values():
        add_job("history", record)
        tail = add_job("tail", record)
        if not tail.get("oldest") and not tail.get("pages_read"):
            tail["oldest"] = str(Decimal(str(time.time())) - Decimal(str(config.get("slack_tail_overlap_seconds", 300))))
    reader = read_page or config.get("read_page")
    config["_dm_channel_mapping"] = {record.get("listing_metadata", {}).get("user_id"): record["channel_id"] for record in channel_records.values() if record.get("listing_metadata", {}).get("is_im") and record.get("listing_metadata", {}).get("user_id")}
    native_results = config.get("native_results") or {}
    if isinstance(native_results.get("slack"), Mapping):
        native_results = native_results["slack"]
    if not reader and not config.get("slack_seed_only"):
        reader = _default_reader(config)
    budget = max(0, int(config.get("slack_page_budget", 4)))
    if config.get("slack_seed_only"):
        budget = 0
    turn = int(state.get("round_robin", 0))
    ready = sorted((job for job in jobs.values() if not job.get("complete") and float(job.get("next_attempt_epoch", 0)) <= time.time()), key=lambda row: row["job_id"])
    if config.get("slack_native_receipts_only"):
        # Supplied native pages advance their exact jobs without issuing a
        # second connector call or modifying any other pending scope.
        ready = [job for job in ready if job["job_id"] in native_results]
    if ready:
        offset = turn % len(ready)
        ready = ready[offset:] + ready[:offset]
    for job in ready[:budget]:
        tool, arguments = _request(job)
        job["reader"]["arguments"] = arguments
        job["last_attempt_at"] = at
        job["attempts"] = int(job.get("attempts", 0)) + 1
        raw = None
        try:
            cached = native_results.get(job["job_id"])
            if isinstance(cached, Mapping) and "payload" in cached:
                cached = cached["payload"]
            cached_digest = _digest(cached) if cached is not None else None
            if cached is not None and cached_digest != job.get("last_native_result_sha256"):
                raw = cached
                job["last_native_result_sha256"] = cached_digest
            elif config.get("slack_native_receipts_only"):
                continue
            elif job["kind"] == "file" and callable(config.get("read_file_stream")) and job.get("alternate_reader"):
                raw = config["read_file_stream"](job["file_id"], job["account_ref"], job.get("restore_point"), job.get("file_metadata"))
            else:
                if not callable(reader):
                    raise SourceReadError("native_connector_reader_binding_pending")
                raw = reader(tool, arguments, job["account_ref"])
            page_id = _digest(job["account_ref"], job["job_id"], arguments, raw)
            page_event = _base_event(job, "slack_source_page" if job["kind"] != "file" else "slack_file_source", page_id, at, raw,
                                     "Whole Slack source response captured", {"tool_name": tool, "reader_arguments": arguments, "source_exact": True})
            events.append(page_event)
            if job["kind"] == "file":
                file_value = _unwrap(raw)
                contents = raw.get("content", []) if isinstance(raw, Mapping) else []
                references = [row for row in contents if row.get("type") == "resource_link" or row.get("type") == "resource" and not any(key in row.get("resource", {}) for key in ("text", "blob"))]
                if isinstance(file_value, Mapping):
                    for field in ("file_ref", "file_reference", "download_url", "url_private", "url_private_download"):
                        if file_value.get(field):
                            references.append({"field": field, "reference": file_value[field]})
                    mime = str(file_value.get("mimeType") or file_value.get("mimetype") or job.get("file_metadata", {}).get("mimetype") or "")
                    if mime and not mime.startswith("text/") and not any(block.get("type") in {"image", "audio"} or block.get("type") == "resource" and "blob" in block.get("resource", {}) for block in contents):
                        references.append({"file_id": job["file_id"], "mimetype": mime, "reason": "exact_original_binary_pending"})
                if references:
                    job.update(status="binary_content_pending", complete=False, native_file_references=references,
                               next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)), restore_point={"file_id": job["file_id"], "source_page_event_id": page_event["event_id"], "native_references": references},
                               alternate_reader={"mode": "read_only_stream", "scope": "entire referenced binary, no 10MB crop", "account_ref": job["account_ref"]})
                else:
                    job.update(status="complete", complete=True, pages_read=job["pages_read"] + 1, records_read=job["records_read"] + 1)
                continue
            messages, cursor, terminal, parse = _page(raw)
            page_event["metadata"].update(parse)
            if parse["parse_state"] != "parsed":
                job["last_source_page_event_id"] = page_event["event_id"]
                if parse["parse_state"] == "source_page_incomplete":
                    # Keep the same cursor/window: even the last rendered
                    # message can be cut off by the native response formatter.
                    job["page_limit"] = max(1, arguments["limit"] // 2)
                    raise SourceReadError("source_page_incomplete")
                raise SourceReadError("source_schema_pending")
            newest = job.get("newest_ts")
            reply_timestamps = []
            for message in messages:
                ts = str(message.get("ts") or message.get("event_ts") or "")
                subtype = str(message.get("subtype") or "")
                inner = message.get("message") if isinstance(message.get("message"), Mapping) else message
                identity_ts = str(inner.get("ts") or message.get("deleted_ts") or ts)
                if job["kind"] in {"thread", "thread_tail"} and identity_ts != str(job.get("thread_ts")) and _TS.fullmatch(identity_ts):
                    reply_timestamps.append(identity_ts)
                revision = _message_revision(message)
                key = job["account_ref"] + ":" + str(job.get("channel_id")) + ":" + identity_ts
                previous = observations.get(key)
                previous = previous if isinstance(previous, Mapping) else {}
                # Old checkpoints used wrapper hashes. Their first canonical
                # observation is a baseline, not evidence of a message edit.
                changed = bool(previous.get("revision")) and previous["revision"] != revision
                kind = "message_deleted" if subtype == "message_deleted" else "message_changed" if subtype == "message_changed" or inner.get("edited") else "message_snapshot_changed" if changed else previous.get("event_type", "message")
                event = _base_event(job, "message", identity_ts + ":" + revision, _timestamp(ts or identity_ts), message.get("native_formatted_source") or message.get("native_event_source") or message, inner.get("text") or "Slack message source",
                                    {"message_ts": identity_ts, "event_ts": ts or None, "thread_ts": inner.get("thread_ts"), "subtype": subtype,
                                     "source_page_event_id": page_event["event_id"], "source_format": message.get("source_format", "slack_api"), "revision": revision,
                                     "original_event_id": "slack-message:" + _digest(job.get("workspace_id"), job.get("channel_id"), identity_ts, revision)})
                event["event_type"] = kind
                event["peer_id"] = inner.get("user") or message.get("user")
                events.append(event)
                observations[key] = {"revision": revision, "event_type": kind}
                if _TS.fullmatch(identity_ts) and (newest is None or Decimal(identity_ts) > Decimal(str(newest))):
                    newest = identity_ts
                thread_ts = inner.get("thread_ts") or (identity_ts if inner.get("reply_count", 0) else None)
                if thread_ts and _TS.fullmatch(str(thread_ts)):
                    add_job("thread", job, thread_ts=str(thread_ts))
                    thread_tail = add_job("thread_tail", job, thread_ts=str(thread_ts))
                    if not thread_tail.get("oldest"):
                        thread_tail["oldest"] = str(max(Decimal(0), Decimal(identity_ts or "0") - Decimal(str(config.get("slack_tail_overlap_seconds", 300)))))
                for file in inner.get("files", []) or []:
                    if isinstance(file, Mapping) and file.get("id"):
                        add_job("file", job, file_id=str(file["id"]), file_metadata=dict(file))
                # Attachments retain every field in message full_source. Slack
                # file IDs explicitly referenced by attachment metadata also
                # receive whole-file descendants.
                for attachment in inner.get("attachments", []) or []:
                    if isinstance(attachment, Mapping):
                        for fid in re.findall(r"\bF[A-Z0-9]{7,}\b", json.dumps(attachment, ensure_ascii=False)):
                            add_job("file", job, file_id=fid, attachment_metadata=dict(attachment))
            job["pages_read"] += 1
            job["records_read"] += len(messages)
            job["newest_ts"] = newest
            job["last_source_page_event_id"] = page_event["event_id"]
            job.pop("error", None)
            if job["kind"] in {"history", "thread"} and newest:
                matching_tail = add_job("tail" if job["kind"] == "history" else "thread_tail", job, **({"thread_ts": job["thread_ts"]} if job["kind"] == "thread" else {}))
                overlap = Decimal(str(config.get("slack_tail_overlap_seconds", 300)))
                candidate = max(Decimal(0), Decimal(newest) - overlap)
                existing = matching_tail.get("oldest")
                if existing is not None and _TS.fullmatch(str(existing)):
                    candidate = max(candidate, Decimal(str(existing)))
                matching_tail["oldest"] = str(candidate)
            if _thread_page_regressed(job, reply_timestamps):
                # Re-read the unchanged window instead of trusting a terminal
                # cursor that reversed direction or skipping unseen messages by
                # advancing a timestamp bound. Exact pages remain in custody.
                page_event["metadata"]["thread_cursor_regressed"] = True
                job.pop("thread_page_progress", None)
                job.update(cursor="", page_limit=max(1, arguments["limit"] // 2),
                           status="cursor_recovery_pending", complete=False,
                           next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)),
                           restore_point={"tool_name": tool, "arguments": arguments, "account_ref": job["account_ref"],
                                          "source_page_event_id": page_event["event_id"], "cursor": arguments.get("cursor"),
                                          "recovery": "smaller_page_same_window"})
            elif cursor is None:
                job.update(status="pagination_metadata_pending", complete=False, next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)))
            elif cursor and cursor == job.get("cursor"):
                job.update(status="cursor_recovery_pending", complete=False, next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)))
            elif terminal:
                job.pop("thread_page_progress", None)
                if job["kind"] in {"tail", "thread_tail"}:
                    overlap = Decimal(str(config.get("slack_tail_overlap_seconds", 300)))
                    job.pop("latest", None)
                    candidate = max(Decimal(0), Decimal(newest or "0") - overlap)
                    existing = job.get("oldest")
                    if existing is not None and _TS.fullmatch(str(existing)):
                        candidate = max(candidate, Decimal(str(existing)))
                    job.update(cursor="", status="live", complete=False, oldest=str(candidate), next_attempt_epoch=time.time() + float(config.get("slack_tail_seconds", 30)))
                else:
                    job.update(cursor="", status="complete", complete=True)
            elif not cursor and not terminal and messages:
                stamps = [str(message.get("ts")) for message in messages if _TS.fullmatch(str(message.get("ts") or ""))]
                if stamps:
                    checkpoint = min(stamps, key=Decimal)
                    if checkpoint == job.get("latest"):
                        job.update(status="timestamp_pagination_recovery_pending", complete=False, next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)))
                    else:
                        job.update(cursor="", latest=checkpoint, status="backfilling", complete=False, pagination_basis="latest_ts")
                else:
                    job.update(status="pagination_metadata_pending", complete=False, next_attempt_epoch=time.time() + float(config.get("slack_retry_seconds", 120)))
            else:
                job.update(cursor=cursor, status="backfilling", complete=False)
        except Exception as error:
            code = getattr(error, "code", type(error).__name__)
            if raw is not None:
                events.append(_base_event(job, "slack_source_read_failure", _digest(raw), at, raw, "Slack source read requires recovery", {"error": code}))
            retry_seconds = _provider_retry_seconds(raw)
            if code == "source_page_incomplete" and job.get("page_limit", 100) < arguments.get("limit", 100):
                retry_seconds = 0
            if retry_seconds is None:
                retry_seconds = float(config.get("slack_retry_seconds", 120))
            job.update(status="pending_recovery", complete=False, error=code, next_attempt_epoch=time.time() + retry_seconds,
                       restore_point={"tool_name": tool, "arguments": arguments, "account_ref": job["account_ref"], "cursor": job.get("cursor"), "file_id": job.get("file_id")})
            if job["kind"] == "file":
                job["alternate_reader"] = {"mode": "read_only_stream", "scope": "all file bytes through another existing direct source road", "account_ref": job["account_ref"], "file_id": job["file_id"], "native_limit_bytes": 10 * 1024 * 1024}
        turn += 1

    for job in jobs.values():
        tool, args = _request(job)
        job["reader"]["arguments"] = args
        coverage.append({"source_id": job["job_id"], "source": "slack", "service": "slack", "account_ref": job["account_ref"], "workspace_id": job.get("workspace_id"),
                         "channel_id": job.get("channel_id"), "file_id": job.get("file_id"), "thread_ts": job.get("thread_ts"), "scope": job["kind"], "status": job["status"],
                         "complete": job.get("complete", False), "pages_read": job["pages_read"], "records_read": job["records_read"], "cursor": job.get("cursor"),
                         "observed_at": job.get("last_attempt_at"), "reader": job["reader"], "restore_point": job.get("restore_point"), "error": job.get("error"),
                         "unread_regions": [] if job.get("complete") else ["entire file bytes" if job["kind"] == "file" else "source pages after retained cursor"], "live_tail": job["kind"] in {"tail", "thread_tail"}})
    source_rows = [{"source_id": job["job_id"], "service": "slack", "account_ref": job["account_ref"], "scope": job["kind"], "source_locator": job.get("file_id") or job.get("channel_id"),
                    "status": job["status"], "complete": job.get("complete", False), "reader": job["reader"], "thread_ts": job.get("thread_ts"), "workspace_id": job.get("workspace_id"),
                    "full_source_required": True} for job in jobs.values()]
    return {"events": events, "coverage": coverage, "state": {"jobs": jobs, "channels": channel_records, "message_versions": observations, "round_robin": turn, "observed_at": at}, "sources": source_rows}
