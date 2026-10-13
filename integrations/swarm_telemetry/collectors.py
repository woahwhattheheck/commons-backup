"""Read-only adapters for passive Swarm Telemetry sources.

Transcript checkpoints are proposals: callers must persist them only after the
events in the corresponding batch have been ingested successfully.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

_MAX_SUMMARY_CHARS = 480
_TRANSCRIPT_SUFFIXES = {".jsonl", ".ndjson", ".json"}
_TRANSCRIPT_PREFIX_BYTES = 4096


def _text(value: Any, limit: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        raw = value
    elif isinstance(value, (int, float, bool)):
        raw = str(value)
    else:
        return ""
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw if limit is None else raw[:limit]


def _hash(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(x or "") for x in parts).encode("utf-8", "replace")).hexdigest()


def _iso(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        try:
            # Provider timestamps are generally seconds; large values are ms.
            stamp = float(value) / (1000 if value > 10_000_000_000 else 1)
            return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, OverflowError, OSError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _summary_text(value: Any) -> str:
    """Create a short dashboard summary; exact visible source is retained separately."""
    text = _text(value, _MAX_SUMMARY_CHARS)
    if not text:
        return ""
    # Do not expose common credential forms, even when embedded in a message.
    text = re.sub(r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,})\b", "[redacted]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1[redacted]", text)
    text = re.sub(r"(?i)\b(password|passwd|secret|api[_ -]?key|access[_ -]?token)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    return text[:_MAX_SUMMARY_CHARS]


def _visible_text(content: Any) -> str:
    if isinstance(content, str):
        return _summary_text(content)
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, Mapping):
            kind = str(_pick(part, "type", "kind") or "").lower()
            if kind in {"text", "output_text", "input_text", "text_delta"}:
                chunks.append(str(_pick(part, "text", "content") or ""))
            # Reasoning, images, tool arguments/results and opaque blocks are excluded.
    return _summary_text(" ".join(chunks))


def _visible_source_text(content: Any) -> str:
    """Return all ordinary visible text without excerpting or whitespace edits."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, Mapping):
            kind = str(_pick(part, "type", "kind") or "").lower()
            if kind in {"text", "output_text", "input_text", "text_delta"}:
                value = _pick(part, "text", "content")
                if isinstance(value, str):
                    chunks.append(value)
    return "".join(chunks)


def _source_ref(path: Path, row: Mapping[str, Any], text: str | None = None) -> dict[str, Any]:
    try:
        file_length = path.stat().st_size
    except OSError:
        file_length = None
    return {
        "source_file_id": _hash(str(path.resolve()))[:20],
        "byte_offset": row.get("__source_offset"),
        "record_byte_length": row.get("__source_byte_length"),
        "record_index": row.get("__source_index"),
        "file_byte_length": file_length,
        "body_byte_length": len(text.encode("utf-8")) if text is not None else None,
    }


def _provider(path: Path, row: Mapping[str, Any]) -> str:
    haystack = (str(path).lower() + " " + " ".join(str(k).lower() for k in row.keys()))
    if ".claude" in haystack or "claude" in haystack or "claude" in str(row.get("provider", "")).lower():
        return "anthropic"
    if "gemini" in haystack or "google" in str(row.get("provider", "")).lower():
        return "google"
    return "openai"


def _base_event(*, source: str, source_id: str, event_type: str, occurred_at: str | None,
                session_id: str | None, agent_id: str | None, parent_agent_id: str | None,
                provider: str, model: str | None, harness: str | None, status: str | None,
                summary: str, metrics: Mapping[str, Any] | None = None,
                metadata: Mapping[str, Any] | None = None, url: str | None = None,
                full_source: str | None = None,
                source_ref: Mapping[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "event_id": _hash(source, source_id, event_type), "source": source,
        "source_id": source_id, "occurred_at": occurred_at, "observed_at": _now(),
        "event_type": event_type, "peer_id": None, "session_id": session_id,
        "agent_id": agent_id, "parent_agent_id": parent_agent_id, "provider": provider,
        "model": model, "harness": harness, "work_id": None, "operation_id": None,
        "status": status, "summary": _summary_text(summary), "url": url,
        "metrics": dict(metrics or {}), "metadata": dict(metadata or {}),
    }
    if full_source is not None:
        event["full_source"] = full_source
    if source_ref is not None:
        event["source_ref"] = dict(source_ref)
    return event


def _usage_delta(row: Mapping[str, Any], previous: Mapping[str, float]) -> tuple[dict[str, int], dict[str, float]]:
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "promptTokenCount", "inputTokenCount"),
        "output_tokens": ("output_tokens", "completion_tokens", "candidatesTokenCount", "outputTokenCount"),
        "cached_input_tokens": ("cached_input_tokens", "cached_tokens", "cachedContentTokenCount"),
        "total_tokens": ("total_tokens", "totalTokenCount"),
        "reasoning_output_tokens": ("reasoning_output_tokens",),
        "cache_write_input_tokens": ("cache_write_input_tokens",),
    }
    delta: dict[str, int] = {}
    next_previous = dict(previous)

    # Provider ``usage`` describes this request. Codex also attaches cumulative
    # turn/thread counters; convert those to independent, prefixed deltas.
    usage = _pick(row, "usage", "token_usage", "usageMetadata")
    token_count = row.get("token_count")
    if not isinstance(usage, Mapping) and isinstance(token_count, Mapping):
        usage = token_count.get("last_token_usage") if isinstance(token_count.get("last_token_usage"), Mapping) else token_count
    if isinstance(usage, Mapping):
        last_usage = usage.get("last_token_usage") if isinstance(usage.get("last_token_usage"), Mapping) else None
        if last_usage is not None:
            usage = last_usage
        for normalized, names in aliases.items():
            val = _pick(usage, *names)
            if isinstance(val, (int, float)) and val >= 0:
                delta[normalized] = int(val)

    for scope in ("turn", "thread", "total"):
        usage_key = {"turn": "turn_token_usage", "thread": "thread_token_usage", "total": "total_token_usage"}[scope]
        cumulative = row.get(usage_key)
        if not isinstance(cumulative, Mapping) and isinstance(token_count, Mapping):
            cumulative = token_count.get(usage_key)
        if not isinstance(cumulative, Mapping):
            continue
        for normalized, names in aliases.items():
            value = _pick(cumulative, *names)
            if not isinstance(value, (int, float)) or value < 0:
                continue
            prior_key = f"{scope}_{normalized}"
            previous_value = next_previous.get(prior_key, 0.0)
            amount = value - previous_value if value >= previous_value else value
            delta[f"{scope}_delta_{normalized}"] = max(0, int(amount))
            next_previous[prior_key] = float(value)
    if delta and "total_tokens" not in delta and "thread_delta_total_tokens" not in delta and "total_delta_total_tokens" not in delta:
        total = sum(delta.get(k, 0) for k in ("input_tokens", "output_tokens"))
        if total:
            delta["total_tokens"] = total
    return delta, next_previous


def _rows(value: Any) -> Iterable[Mapping[str, Any]]:
    """Yield likely event records from native JSON or connector JSON shapes."""
    if isinstance(value, Mapping):
        if isinstance(value.get("content"), list) and len(value["content"]) == 1:
            item = value["content"][0]
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                try:
                    yield from _rows(json.loads(item["text"]))
                    return
                except (ValueError, TypeError):
                    pass
        for key in ("events", "messages", "items", "data", "results", "threads"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    if isinstance(item, Mapping):
                        yield item
                return
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                yield item


def _nested_rows(value: Any, keys: tuple[str, ...]) -> Iterator[Mapping[str, Any]]:
    """Walk provider collections while retaining parent activity and replies."""
    if isinstance(value, Mapping):
        # Unwrap connector text envelopes without losing ordinary message text.
        content = value.get("content")
        if isinstance(content, list):
            parsed_any = False
            for block in content:
                if isinstance(block, Mapping) and isinstance(block.get("text"), str):
                    try:
                        yield from _nested_rows(json.loads(block["text"]), keys)
                        parsed_any = True
                    except (json.JSONDecodeError, TypeError):
                        pass
            if parsed_any:
                return
        yield value
        for key in keys:
            child = value.get(key)
            if isinstance(child, (Mapping, list)):
                yield from _nested_rows(child, keys)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (Mapping, list)):
                yield from _nested_rows(item, keys)


def _transcript_events(path: Path, records: Iterable[Mapping[str, Any]], source_prefix: str,
                       context: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    state = context if context is not None else {}
    session_id = state.get("session_id")
    agent_id = state.get("agent_id")
    parent_agent_id = state.get("parent_agent_id")
    model = state.get("model")
    provider = state.get("provider", "openai")
    harness = state.get("harness")
    prior_usage: dict[str, float] = dict(state.get("prior_usage") or {})
    path_key = _hash(str(path.resolve()))[:20]
    for index, original in enumerate(records):
        row = original
        payload = row.get("payload")
        nested_type = str(payload.get("type", "")).lower() if isinstance(payload, Mapping) else ""
        if isinstance(payload, Mapping):
            row = {**payload, **{k: v for k, v in row.items() if k != "payload"}}
        provider = _provider(path, row)
        session_id = _text(_pick(row, "session_id", "sessionId", "session", "conversation_id") or session_id, 160) or session_id
        model = _text(_pick(row, "model", "model_name", "modelName", "model_id") or model, 160) or model
        harness = _text(_pick(row, "harness", "cli", "source_app") or ("claude-code" if provider == "anthropic" else "gemini-cli" if provider == "google" else "codex"), 80)
        agent_id = _text(_pick(row, "agent_id", "agentId"), 160) or agent_id
        parent_agent_id = _text(_pick(row, "parent_agent_id", "parentAgentId", "parentUuid", "parent_id") or parent_agent_id, 160) or parent_agent_id
        when = _iso(_pick(row, "timestamp", "created_at", "createdAt", "time", "ts"))
        role = str(_pick(row, "role", "type", "speaker", "kind") or "").lower()
        event_id = _text(_pick(row, "id", "uuid", "message_id", "messageId"), 200) or str(row.get("__source_offset", index))
        source_offset = row.get("__source_offset")
        source_id = f"{path_key}:{event_id}" + (f"@{source_offset}" if source_offset is not None else "")
        row_type = str(_pick(row, "type", "kind") or "").lower()
        state.update({"session_id": session_id, "agent_id": agent_id, "parent_agent_id": parent_agent_id,
                      "provider": provider, "model": model, "harness": harness, "prior_usage": prior_usage})

        usage_delta, prior_usage = _usage_delta(row, prior_usage)
        state["prior_usage"] = prior_usage
        if usage_delta:
            yield _base_event(source="transcript", source_id=source_id + ":usage", event_type="usage",
                occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                provider=provider, model=model, harness=harness, status="observed", summary="Usage counters observed",
                metrics=usage_delta, metadata={"counter_semantics": "per_call_and_cumulative_deltas"},
                source_ref=_source_ref(path, row))

        # Session metadata can carry identity and execution context but is not prose.
        if any(x in row_type for x in ("session_meta", "session_start", "init")):
            if session_id is None:
                session_id = _text(_pick(row, "id", "session_id", "sessionId"), 160) or None
            meta = {}
            for field in ("cwd", "gitBranch", "branch", "version", "reasoning_effort", "reasoningEffort"):
                val = row.get(field)
                if isinstance(val, (str, int, float, bool)):
                    meta[field] = _text(val, 160)
            if meta:
                yield _base_event(source="transcript", source_id=source_id, event_type="session_context",
                    occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                    provider=provider, model=model, harness=harness, status="observed", summary="Session context observed",
                    metadata=meta, source_ref=_source_ref(path, row))
            continue

        lifecycle = (nested_type or row_type).lower()
        lifecycle_map = {
            "task_started": ("task_started", "started"),
            "task_complete": ("task_complete", "completed"),
            "task_completed": ("task_complete", "completed"),
            "turn_started": ("turn_started", "started"),
            "turn_completed": ("turn_completed", "completed"),
            "turn_complete": ("turn_completed", "completed"),
            "turn_aborted": ("interruption", "interrupted"),
            "turn_cancelled": ("interruption", "interrupted"),
            "turn_canceled": ("interruption", "interrupted"),
        }
        if lifecycle in lifecycle_map:
            normalized_type, status = lifecycle_map[lifecycle]
            yield _base_event(source="transcript", source_id=source_id, event_type=normalized_type,
                occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                provider=provider, model=model, harness=harness, status=status,
                summary=f"Session event: {normalized_type}", source_ref=_source_ref(path, row))
            continue

        tool_name = _pick(row, "tool_name", "toolName", "name")
        # Explicit results take precedence over the generic named-call heuristic.
        if role in {"tool_result", "function_call_output", "tool_output"} or row_type in {"tool_result", "function_call_output", "tool_output"} or nested_type in {"tool_result", "function_call_output", "tool_output"}:
            name = _text(_pick(row, "tool_name", "toolName", "name") or "tool", 100)
            raw_status = str(_pick(row, "status", "state", "error") or "").lower()
            error_flag = _pick(row, "isError", "is_error")
            has_output = any(key in row for key in ("output", "result", "content"))
            status = "error" if raw_status in {"error", "failed", "failure", "true"} or error_flag is True or bool(row.get("error")) else "completed" if raw_status in {"ok", "success", "completed", "done"} or (has_output and error_flag is False) else "unknown"
            result = _pick(row, "output", "result", "content")
            result_text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str) if isinstance(result, Mapping) else _visible_source_text(result)
            yield _base_event(source="transcript", source_id=source_id, event_type="tool_result",
                occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                provider=provider, model=model, harness=harness, status=status, summary=f"Tool result: {name}",
                metadata={"tool_name": name},
                full_source=result_text, source_ref=_source_ref(path, row, result_text))
            continue
        if role in {"tool_use", "tool_call", "function_call", "toolcall"} or tool_name and role not in {"user", "assistant", "human", "gemini"}:
            name = _text(tool_name or _pick(row, "tool", "function"), 100)
            if not name:
                continue
            yield _base_event(source="transcript", source_id=source_id, event_type="tool_call",
                occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                provider=provider, model=model, harness=harness, status="observed", summary=f"Tool called: {name}",
                metadata={"tool_name": name}, source_ref=_source_ref(path, row))
            continue

        # Codex event_msg and other wrappers may nest the visible message.
        message = _pick(row, "message", "content", "text")
        if isinstance(message, Mapping):
            role = str(_pick(message, "role", "author") or role).lower()
            message = _pick(message, "content", "text", "parts")
        normalized_role = {"human": "user", "gemini": "assistant", "model": "assistant"}.get(role, role)
        if normalized_role in {"user", "assistant"}:
            visible_source = _visible_source_text(message)
            if isinstance(message, list):
                for part_index, part in enumerate(message):
                    if not isinstance(part, Mapping):
                        continue
                    part_kind = str(_pick(part, "type", "kind") or "").lower()
                    part_id = _text(_pick(part, "id", "tool_use_id", "call_id"), 100) or str(part_index)
                    if part_kind in {"tool_use", "function_call", "tool_call"}:
                        tool_name = _text(_pick(part, "name", "tool_name", "toolName"), 100)
                        if tool_name:
                            yield _base_event(source="transcript", source_id=source_id + ":tool:" + part_id,
                                event_type="tool_call", occurred_at=when, session_id=session_id, agent_id=agent_id,
                                parent_agent_id=parent_agent_id, provider=provider, model=model, harness=harness,
                                status="observed", summary=f"Tool called: {tool_name}", metadata={"tool_name": tool_name},
                                source_ref=_source_ref(path, row))
                    elif part_kind in {"tool_result", "function_call_output", "tool_output"}:
                        tool_name = _text(_pick(part, "name", "tool_name", "toolName") or "tool", 100)
                        error_flag = _pick(part, "is_error", "isError")
                        result_status = "error" if error_flag is True else "completed" if error_flag is False else "unknown"
                        result_text = _visible_source_text(_pick(part, "content", "output", "text"))
                        yield _base_event(source="transcript", source_id=source_id + ":tool-result:" + part_id,
                            event_type="tool_result", occurred_at=when, session_id=session_id, agent_id=agent_id,
                            parent_agent_id=parent_agent_id, provider=provider, model=model, harness=harness,
                            status=result_status, summary=f"Tool result: {tool_name}", metadata={"tool_name": tool_name},
                            full_source=result_text, source_ref=_source_ref(path, row, result_text))
            excerpt = _visible_text(message)
            if visible_source:
                yield _base_event(source="transcript", source_id=source_id, event_type=f"message_{normalized_role}",
                    occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                    provider=provider, model=model, harness=harness, status="observed", summary=excerpt,
                    full_source=visible_source, source_ref=_source_ref(path, row, visible_source))
        turn_status = str(_pick(row, "status", "state", "stop_reason", "stopReason") or "").lower()
        if any(word in turn_status for word in ("interrupt", "cancel", "abort")) or any(word in value for value in (row_type, nested_type) for word in ("turn_aborted", "interrupted", "cancelled", "canceled")):
            yield _base_event(source="transcript", source_id=source_id + ":interrupt", event_type="interruption",
                occurred_at=when, session_id=session_id, agent_id=agent_id, parent_agent_id=parent_agent_id,
                provider=provider, model=model, harness=harness, status="interrupted", summary="Session turn interrupted",
                source_ref=_source_ref(path, row))
    state.update({"session_id": session_id, "agent_id": agent_id, "parent_agent_id": parent_agent_id,
                  "provider": provider, "model": model, "harness": harness, "prior_usage": prior_usage})


def _file_stamp(stat: os.stat_result) -> dict[str, Any]:
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns, "file_identity": [stat.st_dev, stat.st_ino]}


def _prefix_fingerprint(handle: Any, length: int) -> dict[str, Any]:
    position = handle.tell()
    try:
        handle.seek(0)
        prefix = handle.read(min(max(0, length), _TRANSCRIPT_PREFIX_BYTES))
    finally:
        handle.seek(position)
    return {"prefix_bytes": len(prefix), "prefix_sha256": hashlib.sha256(prefix).hexdigest()}


def _prefix_matches(handle: Any, checkpoint: Mapping[str, Any]) -> bool:
    length = checkpoint.get("prefix_bytes")
    if not isinstance(length, int) or not 0 <= length <= _TRANSCRIPT_PREFIX_BYTES:
        return False
    fingerprint = _prefix_fingerprint(handle, length)
    return all(checkpoint.get(key) == value for key, value in fingerprint.items())


def _file_unchanged(path: Path, checkpoint: Mapping[str, Any], stat: os.stat_result) -> bool:
    stamp = _file_stamp(stat)
    if any(checkpoint.get(key) != value for key, value in stamp.items()):
        return False
    with path.open("rb") as handle:
        return _file_stamp(os.fstat(handle.fileno())) == stamp and _prefix_matches(handle, checkpoint)


def _parse_file(path: Path, checkpoint: Mapping[str, Any] | None, *,
                max_bytes: int = 1024 * 1024, max_records: int = 256) -> tuple[list[Mapping[str, Any]], dict[str, Any], str | None]:
    ck = dict(checkpoint or {})
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        offset = int(ck.get("offset", 0) or 0)
        rows: list[Mapping[str, Any]] = []
        malformed = 0
        bytes_read = 0
        bytes_examined = 0
        records_read = 0
        quantum_deferred = False
        incomplete_trailing_record = False
        with path.open("rb") as handle:
            # Bind the checkpoint to the opened file, including a replacement
            # between discovery and open. Legacy checkpoints replay once so an
            # offset of unknown identity cannot skip a new transcript's header.
            stat = os.fstat(handle.fileno())
            stamp = _file_stamp(stat)
            rewound = offset < 0 or offset > stat.st_size or bool(ck) and (
                ck.get("file_identity") != stamp["file_identity"]
                or isinstance(ck.get("size"), int) and stat.st_size < ck["size"]
                or ck.get("size") == stat.st_size and (
                    ck.get("mtime_ns") != stat.st_mtime_ns or ck.get("ctime_ns") != stat.st_ctime_ns)
                or not _prefix_matches(handle, ck))
            if rewound:
                offset = 0
            handle.seek(offset)
            start = offset
            while True:
                if bytes_read >= max_bytes or records_read >= max_records:
                    quantum_deferred = start < stat.st_size
                    break
                remaining = max_bytes - bytes_read
                line = handle.readline(remaining)
                if not line:
                    break
                bytes_examined += len(line)
                if not line.endswith(b"\n"):
                    # Leave the whole record at its original offset. This also
                    # defers a valid-looking but unterminated JSON fragment.
                    quantum_deferred = True
                    incomplete_trailing_record = start + len(line) >= stat.st_size
                    break
                line_offset = start
                try:
                    value = json.loads(line.decode("utf-8"))
                    parsed_rows = list(_rows(value))
                    if len(parsed_rows) > max_records - records_read:
                        quantum_deferred = True
                        break
                    for record in parsed_rows:
                        enriched = dict(record)
                        enriched["__source_offset"] = line_offset
                        enriched["__source_byte_length"] = len(line)
                        rows.append(enriched)
                    records_read += len(parsed_rows)
                    start += len(line)
                    bytes_read += len(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    malformed += 1
                    start += len(line)
                    bytes_read += len(line)
                    continue
            # Compare only the previously committed prefix on the next read.
            # A normal append to a short file must not change its old fingerprint.
            fingerprint = _prefix_fingerprint(handle, start)
        final_stat = path.stat()
        changed = _file_stamp(final_stat) != stamp
        incomplete_trailing_record = incomplete_trailing_record and not changed
        return rows, {**stamp, **fingerprint, "offset": start,
                      "malformed_records": malformed, "pending_bytes": max(0, final_stat.st_size - start),
                      "batch_bytes_read": bytes_read, "batch_bytes_examined": bytes_examined,
                      "batch_records_read": records_read,
                      "batch_quantum_deferred": quantum_deferred,
                      "incomplete_trailing_record": incomplete_trailing_record,
                      "rewound": rewound, "changed_during_read": changed}, None
    try:
        with path.open("rb") as handle:
            stat = os.fstat(handle.fileno())
            stamp = _file_stamp(stat)
            if all(ck.get(key) == value for key, value in stamp.items()) and _prefix_matches(handle, ck):
                return [], {**stamp, **_prefix_fingerprint(handle, stat.st_size)}, None
            if stat.st_size > max_bytes:
                return [], ck, f"json_snapshot_exceeds_batch_byte_limit:{stat.st_size}"
            raw = handle.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return [], ck, f"json_snapshot_exceeds_batch_byte_limit:{len(raw)}"
            value = json.loads(raw.decode("utf-8"))
            fingerprint = _prefix_fingerprint(handle, len(raw))
        final_stat = path.stat()
        # Snapshot JSON is reprocessed on change; downstream event IDs dedupe it.
        snapshot_rows = []
        for index, record in enumerate(_rows(value)):
            if index >= max_records:
                return [], ck, f"json_snapshot_exceeds_batch_record_limit:{max_records}"
            enriched = dict(record)
            enriched["__source_index"] = index
            snapshot_rows.append(enriched)
        return snapshot_rows, {**stamp, **fingerprint, "rewound": bool(ck),
                               "batch_bytes_read": len(raw), "batch_bytes_examined": len(raw),
                               "batch_records_read": len(snapshot_rows),
                               "changed_during_read": _file_stamp(final_stat) != stamp}, None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], ck, f"unreadable_json:{type(exc).__name__}"


def iter_transcript_events(path: str | os.PathLike[str], checkpoint: Mapping[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Yield safe normalized events in bounded chunks from one transcript file."""
    file_path = Path(path)
    context = dict(checkpoint or {})
    offset = int(context.get("offset", 0) or 0)
    while True:
        rows, proposed, error = _parse_file(file_path, context)
        if error:
            return
        if proposed.get("rewound"):
            context.clear()
            offset = 0
        yield from _transcript_events(file_path, rows, "transcript", context)
        next_offset = int(proposed.get("offset", offset) or 0)
        if file_path.suffix.lower() not in {".jsonl", ".ndjson"} or next_offset <= offset:
            return
        offset = next_offset
        context.update(proposed)


def _discover_files(roots: Iterable[str | os.PathLike[str]]) -> tuple[list[Path], list[dict[str, str]]]:
    found: dict[str, Path] = {}
    issues: list[dict[str, str]] = []
    for root in roots:
        path = Path(root).expanduser()
        try:
            if path.is_file():
                if path.suffix.lower() in _TRANSCRIPT_SUFFIXES:
                    found[str(path.resolve())] = path
                continue
            if not path.is_dir():
                issues.append({"source": path.name or str(path), "reason": "root_missing_or_not_directory"})
                continue
            def onerror(exc: OSError) -> None:
                issues.append({"source": Path(getattr(exc, "filename", "") or path).name,
                               "reason": type(exc).__name__})
            for parent, dirs, names in os.walk(path, onerror=onerror, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
                for name in names:
                    item = Path(parent) / name
                    if item.suffix.lower() in _TRANSCRIPT_SUFFIXES:
                        try:
                            found[str(item.resolve())] = item
                        except OSError as exc:
                            issues.append({"source": item.name, "reason": type(exc).__name__})
        except OSError as exc:
            issues.append({"source": path.name or str(path), "reason": type(exc).__name__})
    return sorted(found.values(), key=lambda item: str(item.resolve()).casefold()), issues


def collect_transcripts(roots: Iterable[str | os.PathLike[str]], checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
                        limit_files: int | None = None, max_bytes_per_batch: int = 1024 * 1024,
                        max_records_per_batch: int = 256) -> dict[str, Any]:
    """Collect a finite batch; returned checkpoints are uncommitted proposals."""
    prior = checkpoints or {}
    events: list[dict[str, Any]] = []
    next_checkpoints: dict[str, dict[str, Any]] = {}
    paths, discovery_issues = _discover_files(roots)
    coverage = {"files_seen": len(paths), "files_discoverable": len(paths), "files_read": 0,
                "files_unchanged": 0, "files_skipped": 0, "files_deferred": 0,
                "events_emitted": 0, "bytes_read": 0, "bytes_committed": 0, "records_read": 0,
                "batch_byte_limit": max(0, int(max_bytes_per_batch)),
                "batch_record_limit": max(0, int(max_records_per_batch)),
                "unread_reasons": list(discovery_issues)}
    seen_ids: set[str] = set()
    collector_state = dict(prior.get("__collector__", {})) if isinstance(prior.get("__collector__"), Mapping) else {}
    dirty: list[tuple[bool, str, Path]] = []
    for path in paths:
        key = str(path.resolve())
        ck = prior.get(key) if isinstance(prior.get(key), Mapping) else None
        try:
            stat = path.stat()
            unchanged = ck is not None and _file_unchanged(path, ck, stat)
        except OSError as exc:
            coverage["files_skipped"] += 1
            coverage["unread_reasons"].append({"source": path.name, "reason": type(exc).__name__})
            continue
        if ck is None:
            dirty.append((True, key, path))
        elif (not unchanged
              or (path.suffix.lower() in {".jsonl", ".ndjson"} and int(ck.get("offset", 0) or 0) < stat.st_size)):
            dirty.append((False, key, path))
        else:
            coverage["files_unchanged"] += 1
    # Rotate one unified dirty set so a continuous arrival of new files cannot
    # starve changed history and every bounded call advances past its last path.
    prioritized = sorted(dirty, key=lambda item: (item[1].casefold(), item[1]))
    cursor = str(collector_state.get("cursor") or "")
    if cursor:
        cursor_key = (cursor.casefold(), cursor)
        cut = next((i for i, item in enumerate(prioritized)
                    if (item[1].casefold(), item[1]) > cursor_key), 0)
        prioritized = prioritized[cut:] + prioritized[:cut]
    cap = len(prioritized) if limit_files is None else max(0, int(limit_files))
    selected = prioritized[:cap]
    omitted = prioritized[cap:]
    coverage["files_deferred"] = len(omitted)
    if omitted:
        coverage["unread_reasons"].append({"reason": "batch_limit_deferred_dirty_files", "count": len(omitted)})
    for selected_index, (_, key, path) in enumerate(selected):
        bytes_left = max(0, int(max_bytes_per_batch) - coverage["bytes_read"])
        records_left = max(0, int(max_records_per_batch) - coverage["records_read"])
        if bytes_left <= 0 or records_left <= 0:
            deferred = len(selected) - selected_index
            coverage["files_deferred"] += deferred
            coverage["unread_reasons"].append({"reason": "batch_byte_or_record_quantum_deferred_files", "count": deferred})
            break
        collector_state["cursor"] = key
        try:
            rows, proposed, error = _parse_file(path, prior.get(key), max_bytes=bytes_left, max_records=records_left)
            if error:
                coverage["files_skipped"] += 1
                coverage["unread_reasons"].append({"source": path.name, "reason": error})
                continue
            coverage["files_read"] += 1
            coverage["bytes_read"] += int(proposed.get("batch_bytes_examined", proposed.get("batch_bytes_read", 0)) or 0)
            coverage["bytes_committed"] += int(proposed.get("batch_bytes_read", 0) or 0)
            coverage["records_read"] += int(proposed.get("batch_records_read", len(rows)) or 0)
            context = dict(prior.get(key, {})) if isinstance(prior.get(key), Mapping) else {}
            if proposed.get("rewound"):
                context = {}
            for event in _transcript_events(path, rows, "transcript", context):
                if event["event_id"] not in seen_ids:
                    seen_ids.add(event["event_id"])
                    events.append(event)
            proposed.update({field: context.get(field) for field in
                             ("session_id", "agent_id", "parent_agent_id", "provider", "model", "harness", "prior_usage")
                             if context.get(field) is not None})
            next_checkpoints[key] = proposed
            if proposed.get("malformed_records", 0):
                coverage["unread_reasons"].append({"source": path.name,
                    "reason": "malformed_jsonl_records", "count": proposed["malformed_records"]})
            if proposed.get("incomplete_trailing_record"):
                coverage["unread_reasons"].append({"source": path.name,
                    "reason": "incomplete_trailing_record", "bytes_pending": proposed["pending_bytes"]})
            if proposed.get("batch_quantum_deferred"):
                coverage["unread_reasons"].append({"source": path.name,
                    "reason": "batch_byte_or_record_quantum_deferred", "bytes_pending": proposed.get("pending_bytes", 0)})
            if proposed.get("changed_during_read"):
                coverage["unread_reasons"].append({"source": path.name, "reason": "source_changed_during_read"})
        except (OSError, PermissionError) as exc:
            coverage["files_skipped"] += 1
            coverage["unread_reasons"].append({"source": path.name, "reason": type(exc).__name__})
    coverage["events_emitted"] = len(events)
    coverage["complete"] = not coverage["unread_reasons"]
    next_checkpoints["__collector__"] = collector_state
    return {"events": events, "checkpoints": next_checkpoints, "coverage": coverage}


def normalize_slack(payload: Any) -> list[dict[str, Any]]:
    """Normalize Slack connector/API message shapes; reads are performed elsewhere."""
    output: list[dict[str, Any]] = []
    for row in _nested_rows(payload, ("messages", "replies", "threads", "events", "items", "data", "results")):
        message = row.get("message") if isinstance(row.get("message"), Mapping) else row
        channel = _text(_pick(message, "channel", "channel_id") or _pick(row, "channel", "channel_id"), 100)
        message_id = _text(_pick(message, "ts", "client_msg_id", "id") or _pick(row, "ts", "id"), 200)
        if not message_id:
            continue
        source_id = f"{channel}:{message_id}"
        user = _text(_pick(message, "user", "user_id"), 100)
        thread = _text(_pick(message, "thread_ts", "thread_id"), 100)
        permalink = _text(_pick(message, "permalink", "url") or _pick(row, "permalink"), 500)
        body = _pick(message, "text", "content")
        full_source = _visible_source_text(body)
        output.append(_base_event(source="slack", source_id=source_id, event_type="message",
            occurred_at=_iso(_pick(message, "ts", "timestamp")), session_id=thread or channel, agent_id=user,
            parent_agent_id=None, provider="slack", model=None, harness="slack", status="observed",
            summary=_visible_text(body), url=permalink, full_source=full_source,
            source_ref={"provider_message_id": message_id, "channel_id": channel or None,
                        "thread_id": thread or None, "body_byte_length": len(full_source.encode("utf-8"))},
            metadata={"channel_id": channel, "thread_id": thread} if thread else {"channel_id": channel}))
    # Deduplicate connector envelopes that contain the same provider message.
    return _dedupe(output)


def normalize_github(payload: Any, repo: str | None = None) -> list[dict[str, Any]]:
    """Normalize common GitHub API, webhook, and connector message objects."""
    output: list[dict[str, Any]] = []
    for row in _nested_rows(payload, ("events", "items", "data", "results", "issues", "pull_requests", "comments", "reviews", "review_comments")):
        issue = row.get("issue") if isinstance(row.get("issue"), Mapping) else row
        user = issue.get("user") if isinstance(issue.get("user"), Mapping) else row.get("user") if isinstance(row.get("user"), Mapping) else {}
        pull = row.get("pull_request") if isinstance(row.get("pull_request"), Mapping) else {}
        comment = next((row.get(key) for key in ("comment", "review", "review_comment") if isinstance(row.get(key), Mapping)), None)
        source_entity = comment or pull or issue
        repo_obj = row.get("repository") if isinstance(row.get("repository"), Mapping) else {}
        repository = _text(repo or _pick(repo_obj, "full_name", "name") or _pick(row, "repository", "repo"), 200)
        # Prefer provider-global or URL identity. Numeric issue numbers are only
        # stable when paired with a repository; never key on payload position.
        native_id = _text(_pick(source_entity, "html_url", "url", "node_id"), 240)
        if not native_id:
            issue_number = _pick(source_entity, "number", "issue_number", "id")
            if comment and issue_number is None:
                issue_number = _pick(comment, "id", "node_id")
            issue_number = issue_number or _pick(issue, "number", "issue_number") or _pick(row, "number", "issue_number")
            if issue_number is not None and repository:
                native_id = f"{ 'comment' if comment else 'pull' if pull else 'issue' }:{issue_number}"
            else:
                native_id = _text(_pick(issue, "id") or _pick(row, "id"), 240)
                if native_id and native_id.isdigit() and not repository:
                    continue
        if not native_id:
            continue
        source_id = f"{repository}:{native_id}" if repository else native_id
        body = _pick(source_entity, "body", "title", "text", "content") or _pick(issue, "body", "title", "text", "content") or _pick(row, "body", "title", "text", "content")
        full_source = _visible_source_text(body)
        author = _text(_pick(user, "login") or _pick(row, "sender", "author"), 120)
        when = _iso(_pick(source_entity, "created_at", "updated_at") or _pick(issue, "created_at", "updated_at") or _pick(row, "created_at", "updated_at", "timestamp"))
        url = _text(_pick(source_entity, "html_url", "url") or _pick(issue, "html_url", "url") or _pick(row, "html_url", "url"), 500)
        merged_at = _iso(_pick(pull, "merged_at", "mergedAt") or _pick(issue, "merged_at", "mergedAt") or _pick(row, "merged_at", "mergedAt"))
        raw_state = str(_pick(source_entity, "state") or _pick(issue, "state") or _pick(row, "state", "action") or "").lower()
        # REST pull-request records expose head/base directly, without a wrapper.
        is_rest_pr = isinstance(row.get("head"), Mapping) and isinstance(row.get("base"), Mapping)
        is_pr = is_rest_pr or bool(pull) or "pull" in str(_pick(row, "event", "type", "action") or "").lower() or "pull_request" in row
        is_comment = any(k in row for k in ("comment", "review", "review_comment")) or str(_pick(row, "type", "event") or "").lower() in {"issue_comment", "pull_request_review", "pull_request_review_comment"}
        event_type = "pr_merged" if is_pr and merged_at else "pr_activity" if is_pr else "comment" if is_comment else "activity"
        status = "merged" if merged_at else "closed" if raw_state == "closed" else "observed"
        output.append(_base_event(source="github", source_id=source_id, event_type=event_type,
            occurred_at=merged_at or when, session_id=repository or None, agent_id=author or None, parent_agent_id=None,
            provider="github", model=None, harness="github", status=status, summary=_visible_text(body),
            metadata={"repository": repository, "number": _pick(source_entity, "number") or _pick(issue, "number")}, full_source=full_source,
            source_ref={"repository": repository or None, "provider_record_id": native_id,
                        "url": url or None, "body_byte_length": len(full_source.encode("utf-8"))}))
        output[-1]["url"] = url or None
        kind = _text(_pick(row, "action", "event"), 100)
        if kind:
            output[-1]["metadata"]["action"] = kind
        if is_pr and not merged_at:
            output[-1]["metadata"]["merge_state"] = "closed_unmerged" if raw_state == "closed" else "unmerged_or_unknown"
    return _dedupe(output)


def _dedupe(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result, ids = [], set()
    for event in events:
        if event["event_id"] not in ids:
            ids.add(event["event_id"])
            result.append(event)
    return result

