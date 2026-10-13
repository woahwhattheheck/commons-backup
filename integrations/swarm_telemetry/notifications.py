"""Passive, deterministic notifications; optional enrichment and delivery outbox.

The baseline uses only supplied events and Python's standard library. It never
retrieves credentials, calls Jev, waits for enrichment, or dispatches work.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit


_KINDS = {
    "merge": ("info", "Work merged"),
    "merged": ("info", "Work merged"),
    "pr_merged": ("info", "Work merged"),
    "artifact": ("info", "Artifact available"),
    "artifact_published": ("info", "Artifact available"),
    "result": ("info", "Result available"),
    "result_available": ("info", "Result available"),
    "dependency_change": ("info", "Dependency changed"),
    "dependency_changed": ("info", "Dependency changed"),
    "rate_limit": ("attention", "Service rate limit observed"),
    "rate_limited": ("attention", "Service rate limit observed"),
    "service_recovery": ("info", "Service recovered"),
    "service_recovered": ("info", "Service recovered"),
    "owner_instruction": ("attention", "Owner instruction available"),
    "handoff": ("info", "Work handoff available"),
    "request_answer": ("info", "Requested answer available"),
    "explicit_request_answer": ("info", "Requested answer available"),
    "renewal_imminent": ("attention", "Renewal approaching"),
    "signature_needed": ("attention", "Owner signature needed"),
    "money_commitment": ("attention", "New money commitment needs owner attention"),
    "urgent": ("urgent", "Urgent work update"),
    "blocker_resolved": ("info", "Blocker resolved"),
    "resolution": ("info", "Work update resolved"),
}
_SECRET_KEY = re.compile(
    r"(?:^|[_\s-])(?:password|passwd|secret|token|api[_-]?key|credential|"
    r"private[_-]?key|recovery[_-]?code|authorization|cookie|card[_-]?number|cvv)(?:$|[_\s-])",
    re.I,
)
_SECRET_TEXT = (
    re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?-----END (?:[A-Z ]*PRIVATE KEY)-----", re.S),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_.=:-]+", re.I),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|cookie)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@", re.I),
    re.compile(r"(?i)([?&](?:token|key|api_key|access_token|secret|password)=)[^&#\s]+"),
)
_REFERENCE_FIELDS = frozenset({
    "credential_ref", "credential_refs", "credential_reference", "credential_references",
    "vault_ref", "vault_reference", "keyring_ref", "keyring_reference",
    "token_reference", "key_reference", "secret_reference",
})


def redact(value: Any) -> Any:
    """Return JSON-safe redacted content before persistence or any delivery.

    Callers must also omit source secrets. Pattern redaction does not discover
    arbitrary unlabelled secret values; a shared vault-aware redactor may be
    supplied to Outbox for values known by that credential facility.
    """
    if isinstance(value, Mapping):
        return {str(k): "[REDACTED]" if str(k) not in _REFERENCE_FIELDS and _SECRET_KEY.search(str(k)) else redact(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        values = sorted(value, key=str) if isinstance(value, set) else value
        return [redact(v) for v in values]
    if isinstance(value, str):
        for pattern in _SECRET_TEXT:
            value = pattern.sub("[REDACTED]", value)
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value))


def _list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _unique(values: Iterable[Any]) -> list:
    by_value = {json.dumps(v, sort_keys=True, default=str): v for v in values}
    return [by_value[k] for k in sorted(by_value)]


def _notification_id(event_id: str) -> str:
    return "notification:" + hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:32]


def _event_id(event: Mapping) -> str:
    # Source connectors should carry the original source event ID through all
    # mirrors. A mirror-local ID must not replace original_event_id.
    metadata = event.get("metadata") or {}
    identity = event.get("original_event_id") or metadata.get("original_event_id") or event.get("event_id")
    if identity:
        return str(identity)
    semantic = {k: event.get(k) for k in ("work_id", "occurred_at", "title", "body", "summary")}
    semantic["type"] = event.get("type") or event.get("event_type")
    semantic["source_id"] = event.get("source_id")
    semantic["source_operation_id"] = event.get("operation_id") or metadata.get("operation_id")
    return "derived:" + hashlib.sha256(json.dumps(semantic, sort_keys=True, default=str).encode()).hexdigest()


def merge_notification_metadata(previous: Mapping, incoming: Mapping) -> dict:
    """Merge mirrored notices without treating an audience dictionary as a list.

    Identity and the historical occurrence remain fixed. Parallel audience
    lists and source references accumulate; resolved notices remain resolved.
    Provider delivery state/receipts stay with the caller's delivery record.
    """
    old, new = dict(previous or {}), dict(incoming or {})
    if old.get("notification_id") and new.get("notification_id") and old["notification_id"] != new["notification_id"]:
        raise ValueError("notification_identity_mismatch")
    merged = {**old, **new}
    for field in ("notification_id", "event_id", "work_id", "occurred_at"):
        if old.get(field) is not None:
            merged[field] = old[field]
    for field in ("source_refs", "supersedes"):
        merged[field] = _unique(_list(old.get(field)) + _list(new.get(field)))
    old_audience = old.get("audience") if isinstance(old.get("audience"), Mapping) else {"peers": _list(old.get("audience"))}
    new_audience = new.get("audience") if isinstance(new.get("audience"), Mapping) else {"peers": _list(new.get("audience"))}
    audience = {}
    for field in sorted(set(old_audience) | set(new_audience) | {"peers", "channels", "work_refs"}):
        left, right = old_audience.get(field), new_audience.get(field)
        if field == "owner_attention" or isinstance(left, bool) or isinstance(right, bool):
            audience[field] = bool(left or right)
        else:
            audience[field] = _unique(_list(left) + _list(right))
    merged["audience"] = audience
    old_meta, new_meta = dict(old.get("metadata") or {}), dict(new.get("metadata") or {})
    metadata = {**old_meta, **new_meta}
    for field in ("parent_source_event_ids", "parent_source_record_refs", "source_refs", "account_refs"):
        if field in old_meta or field in new_meta:
            metadata[field] = _unique(_list(old_meta.get(field)) + _list(new_meta.get(field)))
    if old_meta.get("enrichment") == "available" and new_meta.get("enrichment") in {None, "none"}:
        metadata["enrichment"] = "available"
        if "optional_context" in old_meta:
            metadata["optional_context"] = old_meta["optional_context"]
    if old.get("status") == "resolved" or new.get("status") == "resolved":
        merged["status"] = "resolved"
        if old_meta.get("resolved_by"):
            metadata["resolved_by"] = old_meta["resolved_by"]
        if old.get("resolved_by"):
            merged["resolved_by"] = old["resolved_by"]
    merged["metadata"] = metadata
    return redact(merged)


def _source_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, TypeError, OverflowError):
            return None


def _source_objects(value):
    """Traverse only provider object/collection fields, never body prose."""
    if isinstance(value, list):
        for child in value:
            yield from _source_objects(child)
    elif isinstance(value, Mapping):
        yield value
        child_pr = value.get("pull_request")
        if isinstance(child_pr, Mapping):
            yield {**value, **child_pr, "__typename": "PullRequest"}
        for key in ("data", "repository", "pullRequests", "releases", "nodes", "edges", "node", "payload", "release", "items", "results"):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                yield from _source_objects(child)


def notification_events_for_source(event: Mapping, full_source: Any) -> list[dict]:
    """Project passive GitHub notices from an already captured sealed response.

    Only structured PR merge/release publication fields and explicit HTTP rate
    evidence are read. Parent ciphertext references remain untouched. Derived
    IDs exclude mirror account labels for provider merge/publication events;
    rate-limit IDs retain the actual quota account. No provider/model call occurs.
    """
    if event.get("source") != "github" or not isinstance(full_source, Mapping):
        return []
    payload = full_source.get("parsed_json")
    if not isinstance(payload, (dict, list)):
        # Non-JSON responses still carry authoritative HTTP rate evidence.
        # Their body is neither parsed nor searched for prose claims.
        payload = {}
    parent_metadata = dict(event.get("metadata") or {})
    source_kind = str(parent_metadata.get("kind") or "").lower()
    source_ref = event.get("source_record_ref")
    parent_refs = _list(event.get("source_refs")) + ([source_ref] if source_ref else [])
    if event.get("url"):
        parent_refs.append(event["url"])
    projections = {}

    def project(kind, identity, occurred_at, title, body, url=None, details=None):
        stable = "github-observation:" + hashlib.sha256(json.dumps([kind, identity, None if kind == "rate_limit" else occurred_at], sort_keys=True, default=str).encode()).hexdigest()
        metadata = {"notification_type": kind, "original_event_id": stable, "basis": "structured_provider_source",
                    "parent_source_event_ids": [event.get("event_id")], "parent_source_record_refs": [source_ref] if source_ref else [],
                    "account_ref": parent_metadata.get("account_ref"), "repository": details.get("repository") if details else parent_metadata.get("repository"),
                    "account_refs": [parent_metadata["account_ref"]] if parent_metadata.get("account_ref") else [],
                    "occurrence_timestamp_available": occurred_at is not None, **(details or {})}
        audience = event.get("audience") or parent_metadata.get("audience") or {}
        item = {"event_id": stable, "original_event_id": stable, "event_type": kind, "source": "github",
                "source_id": stable, "occurred_at": occurred_at, "observed_at": event.get("observed_at"),
                "work_id": event.get("work_id") or metadata.get("repository"), "title": title, "body": body,
                "source_refs": _unique(parent_refs + ([url] if url else [])), "audience": audience,
                "metadata": metadata}
        if stable in projections:
            projections[stable]["source_refs"] = _unique(projections[stable]["source_refs"] + item["source_refs"])
        else:
            projections[stable] = redact(item)

    for row in _source_objects(payload):
        marker = str(row.get("__typename") or "")
        url = row.get("html_url") or row.get("url")
        parsed_url = urlsplit(url) if isinstance(url, str) else None
        repo = parent_metadata.get("repository")
        base = row.get("base") if isinstance(row.get("base"), Mapping) else {}
        base_repo = base.get("repo") if isinstance(base.get("repo"), Mapping) else {}
        repository = row.get("repository") if isinstance(row.get("repository"), Mapping) else {}
        repo = base_repo.get("full_name") or repository.get("nameWithOwner") or repository.get("full_name") or repo
        number = row.get("number")
        pr_context = marker == "PullRequest" or isinstance(row.get("pull_request"), Mapping) or bool(base and row.get("head")) or (
            parsed_url is not None and bool(re.search(r"/(?:pull|pulls)/\d+(?:/|$)", parsed_url.path))) or source_kind in {"pulls", "pull_requests", "pull_request", "pr_detail"}
        merged_at = _source_time(row.get("merged_at") or row.get("mergedAt"))
        merged = row.get("merged")
        if pr_context and merged is not False and (merged_at or merged is True):
            target = [parsed_url.hostname.lower(), parsed_url.path.rstrip("/").lower()] if parsed_url and "/pull/" in parsed_url.path else [str(repo or "").lower(), number or row.get("node_id") or row.get("id")]
            if any(target):
                occurrence = merged_at or _source_time(event.get("occurred_at"))
                label = str(repo or "GitHub") + (" #" + str(number) if number is not None else " pull request")
                project("merge", target, occurrence, "Merged " + label, label + " merged" + (" at " + occurrence if occurrence else "; occurrence timestamp unavailable"), url,
                        {"repository": repo, "pull_request_number": number, "merged_at": merged_at, "merged": merged})
        release_context = marker == "Release" or "tag_name" in row or bool(parsed_url and "/releases/" in parsed_url.path) or source_kind in {"releases", "release"}
        published_at = _source_time(row.get("published_at") or row.get("publishedAt"))
        if release_context and published_at and row.get("draft") is not True and row.get("isDraft") is not True:
            target = [parsed_url.hostname.lower(), parsed_url.path.rstrip("/")] if parsed_url and "/releases/" in parsed_url.path else [str(repo or "").lower(), row.get("node_id") or row.get("id") or row.get("tag_name") or row.get("tagName")]
            label = str(repo or "GitHub") + " release " + str(row.get("tag_name") or row.get("tagName") or row.get("id") or "")
            project("artifact_published", target, published_at, "Published " + label, label + " published at " + published_at, url,
                    {"repository": repo, "release_id": row.get("id") or row.get("node_id"), "published_at": published_at})

    headers = {str(key).lower(): str(value) for key, value in (full_source.get("headers") or parent_metadata.get("response_headers") or {}).items()}
    status = full_source.get("status") or (event.get("metrics") or {}).get("http_status")
    try:
        status = int(status)
    except (ValueError, TypeError):
        status = None
    provider_message = str(payload.get("message") or full_source.get("provider_message") or "") if isinstance(payload, Mapping) else ""
    explicit_message = any(phrase in provider_message.lower() for phrase in ("rate limit exceeded", "secondary rate limit", "abuse detection mechanism"))
    rate_limited = status == 429 or status == 403 and (bool(headers.get("retry-after")) or headers.get("x-ratelimit-remaining") == "0" or explicit_message)
    if rate_limited:
        occurrence = _source_time(headers.get("date")) or _source_time(event.get("occurred_at")) or _source_time(event.get("observed_at"))
        quota_window = headers.get("x-ratelimit-reset") or occurrence
        window_basis = "provider_reset_header" if headers.get("x-ratelimit-reset") else "provider_response_date" if headers.get("date") else "source_occurrence" if event.get("occurred_at") else "reader_observation; provider reset unavailable"
        url = full_source.get("url") or event.get("url")
        host = urlsplit(url).hostname if isinstance(url, str) else "github"
        identity = [host, parent_metadata.get("account_ref"), headers.get("x-ratelimit-resource"), quota_window, status]
        # Quota-window identity is stable across repeated endpoints; keep the
        # first historical occurrence when notices are subsequently merged.
        project("rate_limit", identity, _source_time(event.get("occurred_at")) if not occurrence else occurrence,
                "GitHub rate limit observed", "GitHub returned HTTP " + str(status) + " with explicit rate-limit evidence", url,
                {"http_status": status, "retry_after": headers.get("retry-after"), "rate_limit_reset": headers.get("x-ratelimit-reset"),
                 "rate_limit_resource": headers.get("x-ratelimit-resource"), "provider_message": provider_message})
        for item in projections.values():
            if item["event_type"] == "rate_limit":
                item["metadata"]["quota_window_basis"] = window_basis
    return sorted(projections.values(), key=lambda item: (str(item.get("occurred_at") or ""), item["event_id"]))


def notifications_for_events(events: Iterable[Mapping]) -> list[dict]:
    """Derive updates from relevant supplied events, merging mirror audiences.

    Unknown kinds yield no notification. Resolutions refer to source event IDs
    in resolves_event_ids or prior notification IDs in supersedes. They update
    matching notifications in this batch; the outbox carries this across runs.
    """
    notifications: dict[str, dict] = {}
    candidates = []
    for event in events:
        metadata = dict(event.get("metadata") or {})
        kind = str(metadata.get("notification_type") or event.get("type") or event.get("event_type") or "").lower().replace("-", "_")
        if kind not in _KINDS:
            continue
        # Ordinary authorized token/model usage is not a new money commitment.
        if kind == "money_commitment" and (metadata.get("authorized_token_usage") is True or metadata.get("commitment_scope") == "authorized_token_usage"):
            continue
        candidates.append((event, metadata, kind))
    # Whole source pages and other unknown kinds need no notification sort key.
    # Preserve the existing canonical order among actual notification candidates.
    for event, metadata, kind in sorted(candidates, key=lambda item: json.dumps(redact(item[0]), sort_keys=True, default=str)):
        event_id = _event_id(event)
        nid = _notification_id(event_id)
        severity, default_title = _KINDS[kind]
        audience = dict(event.get("audience") or metadata.get("audience") or {})
        for field in ("peers", "channels", "work_refs"):
            audience[field] = _unique(_list(audience.get(field)) + _list(metadata.get(field)))
        if event.get("peer_id"):
            audience["peers"] = _unique(audience["peers"] + [str(event["peer_id"])])
        work_id = str(event.get("work_id") or "")
        if work_id:
            audience["work_refs"] = _unique(audience["work_refs"] + [work_id])
        attention = kind in {"signature_needed", "money_commitment", "urgent"} or metadata.get("urgent") is True
        audience["owner_attention"] = attention
        supersedes = _unique(_list(event.get("supersedes")) + _list(metadata.get("supersedes")) + [
            _notification_id(str(eid)) for eid in _list(event.get("resolves_event_ids") or metadata.get("resolves_event_ids"))
        ])
        body = event.get("body") or event.get("summary") or metadata.get("summary") or default_title
        notification = redact({
            "notification_id": nid, "event_id": event_id, "work_id": work_id,
            "type": kind, "severity": "urgent" if metadata.get("urgent") is True else severity,
            "title": event.get("title") or default_title, "body": str(body),
            "occurred_at": event.get("occurred_at"),
            "source_refs": _unique(_list(event.get("source_refs")) + _list(metadata.get("source_refs")) + _list(event.get("url"))),
            "audience": audience, "supersedes": supersedes, "status": "active",
            "metadata": {**metadata, "basis": "supplied_event", "enrichment": "none"},
        })
        previous = notifications.get(nid)
        if previous:
            notifications[nid] = merge_notification_metadata(previous, notification)
        else:
            notifications[nid] = notification
    for notification in notifications.values():
        for nid in notification["supersedes"]:
            if nid in notifications:
                notifications[nid]["status"] = "resolved"
                notifications[nid]["metadata"]["resolved_by"] = notification["notification_id"]
    return sorted(notifications.values(), key=lambda n: (str(n["occurred_at"] or ""), n["notification_id"]))


def enrich_available(notification: Mapping, answer: Mapping | None) -> dict:
    """Accept an already available optional Jev answer without initiating work.

    Enrichment may add context but cannot change identity, audience, status,
    severity or resolution. The sender remains the baseline delivery path.
    """
    enriched = redact(dict(notification))
    if answer:
        enriched["metadata"] = {**enriched.get("metadata", {}),
                                "enrichment": "available", "optional_context": redact(dict(answer))}
    return enriched


class Outbox:
    """Single-writer durable outbox with a pluggable delivery/readback adapter.

    dispatch(notification) returns status sent, failed, or uncertain plus exact
    provider receipt fields. Only a definite failed result is retryable. A
    sending record after restart is uncertain. readback(notification, receipt)
    returns status sent, not_sent, or uncertain. Inconclusive readbacks retain
    the delivery receipt; their result is saved separately as last_readback.
    not_sent permits a retry using the same notification ID. Actual Slack/email
    adapters live with the existing service road; this module neither gets
    credentials nor chooses a provider.
    """

    def __init__(self, path: str | Path, redactor: Callable[[Any], Any] = redact):
        self.path = Path(path)
        self.redactor = redactor
        self.records: dict[str, dict] = {}
        if self.path.exists():
            self.records = json.loads(self.path.read_text(encoding="utf-8"))
            for record in self.records.values():
                if record["delivery_status"] == "sending":
                    record["delivery_status"] = "uncertain"

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.redactor(self.records), sort_keys=True, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def enqueue(self, notifications: Iterable[Mapping]) -> list[str]:
        added = []
        for supplied in notifications:
            notification = self.redactor(redact(dict(supplied)))
            nid = notification["notification_id"]
            existing = self.records.get(nid)
            if existing:
                prior = existing["notification"]
                existing["notification"] = merge_notification_metadata(prior, notification)
            else:
                self.records[nid] = {"notification": notification, "delivery_status": "pending", "attempts": 0, "receipt": None}
                added.append(nid)
            for old_id in notification.get("supersedes", []):
                if old_id in self.records:
                    old = self.records[old_id]["notification"]
                    old["status"] = "resolved"
                    old.setdefault("metadata", {})["resolved_by"] = nid
        # A resolution can arrive before its referenced event.
        for nid, record in self.records.items():
            for old_id in record["notification"].get("supersedes", []):
                if old_id in self.records:
                    old = self.records[old_id]["notification"]
                    old["status"] = "resolved"
                    old.setdefault("metadata", {})["resolved_by"] = nid
        self._save()
        return added

    def deliver(self, dispatch: Callable[[dict], Mapping], readback: Callable[[dict, Any], Mapping] | None = None) -> list[dict]:
        outcomes = []
        for nid in sorted(self.records):
            record = self.records[nid]
            notification = self.redactor(redact(record["notification"]))
            if record["delivery_status"] == "uncertain":
                if readback is None:
                    continue
                try:
                    result = dict(readback(notification, record.get("receipt")))
                except Exception as error:
                    result = {"status": "uncertain", "error": str(error)}
                record["last_readback"] = self.redactor(redact(result))
                status = result.get("status")
                # An outage or partial readback must not erase the provider
                # identifiers and destination receipts needed for recovery.
                if status in {"sent", "not_sent"}:
                    record["receipt"] = record["last_readback"]
                record["delivery_status"] = "sent" if status == "sent" else "pending" if status == "not_sent" else "uncertain"
                self._save()
                if record["delivery_status"] != "pending":
                    outcomes.append({"notification_id": nid, **record["last_readback"]})
                    continue
            if record["delivery_status"] not in {"pending", "failed"} or notification.get("status") == "resolved":
                continue
            previous_status, previous_attempts = record["delivery_status"], record["attempts"]
            record["delivery_status"] = "sending"
            record["attempts"] = previous_attempts + 1
            try:
                self._save()  # Persist before the external side effect.
            except Exception:
                # No delivery happened: a recovered writer must be able to retry
                # this same in-memory notice without restarting the outbox.
                record["delivery_status"] = previous_status
                record["attempts"] = previous_attempts
                raise
            try:
                result = dict(dispatch(notification))
            except Exception as error:
                result = {"status": "uncertain", "error": str(error)}
            status = result.get("status")
            record["delivery_status"] = status if status in {"sent", "failed"} else "uncertain"
            record["receipt"] = self.redactor(redact(result))
            self._save()
            outcomes.append({"notification_id": nid, **record["receipt"]})
        return outcomes
