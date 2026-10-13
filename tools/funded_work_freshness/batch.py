"""Bounded batch execution and short-lived receipt caching for funded-work preflight."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Iterable, Mapping

from engine import preflight
from errors import PreflightInputError
from models import Candidate, Response, Transport
from receipt import receipt_hash

CACHE_SCHEMA = "funded-work-freshness-cache/v1"
BATCH_SCHEMA = "funded-work-freshness-batch/v1"
_ALLOWED_STATUSES = {"actionable", "occupied", "stale", "ambiguous"}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def candidate_fingerprint(candidate: Candidate) -> str:
    payload = {
        "candidate_url": candidate.candidate_url,
        "platform": candidate.platform,
        "advertised_amount": candidate.advertised_amount,
        "currency": candidate.currency,
        "canonical_url": candidate.canonical_url,
        "max_age_days": candidate.max_age_days,
        "max_visible_claims": candidate.max_visible_claims,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_entry_hash(entry: Mapping[str, Any]) -> str:
    """Bind cache-envelope identity, age, policy fingerprint, and receipt bytes."""

    payload = dict(entry)
    payload.pop("entry_sha256", None)
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _receipt_is_persistently_cacheable(receipt: object) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    if receipt.get("freshness_status") not in {"occupied", "stale", "ambiguous"}:
        return False
    checks = receipt.get("checks")
    if not isinstance(checks, Mapping) or checks.get("evidence_complete") is not True:
        return False
    expected = receipt.get("receipt_sha256")
    try:
        return isinstance(expected, str) and receipt_hash(receipt) == expected
    except (TypeError, ValueError):
        return False


def _cache_entry_is_valid(key: object, entry: object) -> bool:
    if not isinstance(key, str) or not isinstance(entry, Mapping):
        return False
    if entry.get("candidate_fingerprint") != key:
        return False
    expected = entry.get("entry_sha256")
    try:
        if not isinstance(expected, str) or cache_entry_hash(entry) != expected:
            return False
    except (TypeError, ValueError):
        return False
    receipt = entry.get("receipt")
    if not _receipt_is_persistently_cacheable(receipt):
        return False
    cached_at = _parse_iso(entry.get("cached_at"))
    generated_at = _parse_iso(receipt.get("generated_at"))
    return cached_at is not None and cached_at == generated_at


class MemoizingTransport:
    """Share immutable GET-equivalent responses within one batch execution."""

    def __init__(self, transport: Transport):
        self.transport = transport
        self._responses: dict[tuple[str, str], Response] = {}
        self.network_fetches = 0
        self.memo_hits = 0

    def fetch(self, url: str, *, accept: str) -> Response:
        key = (url, accept)
        cached = self._responses.get(key)
        if cached is not None:
            self.memo_hits += 1
            return cached
        response = self.transport.fetch(url, accept=accept)
        self.network_fetches += 1
        self._responses[key] = response
        return response


@dataclass
class CacheLookup:
    receipt: dict[str, Any] | None
    age_seconds: float | None = None


class ReceiptCache:
    """Best-effort local cache; invalid entries are misses and force fresh evidence."""

    def __init__(self, entries: Mapping[str, Any] | None = None):
        self.entries: dict[str, dict[str, Any]] = {}
        if entries:
            for key, value in entries.items():
                if isinstance(key, str) and isinstance(value, Mapping):
                    self.entries[key] = dict(value)

    @classmethod
    def from_payload(cls, payload: object) -> "ReceiptCache":
        if not isinstance(payload, Mapping) or payload.get("schema") != CACHE_SCHEMA:
            return cls()
        entries = payload.get("entries")
        if not isinstance(entries, Mapping):
            return cls()
        return cls(
            {key: value for key, value in entries.items() if _cache_entry_is_valid(key, value)}
        )

    def to_payload(self, *, max_entries: int) -> dict[str, Any]:
        if isinstance(max_entries, bool) or max_entries < 1:
            raise PreflightInputError("max_cache_entries must be a positive integer")
        valid = (
            (key, value)
            for key, value in self.entries.items()
            if _cache_entry_is_valid(key, value)
        )
        ordered = sorted(
            valid,
            key=lambda item: str(item[1].get("cached_at") or ""),
            reverse=True,
        )[:max_entries]
        return {"schema": CACHE_SCHEMA, "entries": dict(ordered)}

    def get(
        self,
        candidate: Candidate,
        *,
        now: datetime,
        ttl_seconds: float,
    ) -> CacheLookup:
        if ttl_seconds <= 0:
            return CacheLookup(None)
        fingerprint = candidate_fingerprint(candidate)
        entry = self.entries.get(fingerprint)
        if not _cache_entry_is_valid(fingerprint, entry):
            return CacheLookup(None)
        assert isinstance(entry, Mapping)
        cached_at = _parse_iso(entry.get("cached_at"))
        receipt = entry.get("receipt")
        assert cached_at is not None and isinstance(receipt, Mapping)
        age = (now - cached_at).total_seconds()
        if age < 0 or age > ttl_seconds:
            return CacheLookup(None, age_seconds=age)
        candidate_block = receipt.get("candidate")
        if not isinstance(candidate_block, Mapping):
            return CacheLookup(None, age_seconds=age)
        expected_candidate = {
            "url": candidate.candidate_url,
            "platform": candidate.platform,
            "advertised_amount": candidate.advertised_amount,
            "currency": candidate.currency,
            "canonical_url_hint": candidate.canonical_url,
        }
        if any(candidate_block.get(key) != value for key, value in expected_candidate.items()):
            return CacheLookup(None, age_seconds=age)
        return CacheLookup(dict(receipt), age_seconds=age)

    def put(self, candidate: Candidate, receipt: Mapping[str, Any], *, cached_at: datetime) -> None:
        if not _receipt_is_persistently_cacheable(receipt):
            return
        fingerprint = candidate_fingerprint(candidate)
        entry: dict[str, Any] = {
            "candidate_fingerprint": fingerprint,
            "cached_at": _iso(cached_at),
            "receipt": dict(receipt),
        }
        entry["entry_sha256"] = cache_entry_hash(entry)
        self.entries[fingerprint] = entry


def _validate_now(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PreflightInputError("observed_at must be timezone-aware")
    return now.astimezone(timezone.utc)


def process_batch(
    candidates: Iterable[Candidate],
    transport: Transport,
    *,
    observed_at: datetime | None = None,
    cache: ReceiptCache | None = None,
    cache_ttl_seconds: float = 60.0,
    max_cache_entries: int = 256,
    evaluator: Callable[..., dict[str, Any]] = preflight,
) -> tuple[dict[str, Any], ReceiptCache]:
    """Evaluate a batch while coalescing exact inputs and canonical HTTP evidence reads."""

    if (
        isinstance(cache_ttl_seconds, bool)
        or not isinstance(cache_ttl_seconds, (int, float))
        or not math.isfinite(float(cache_ttl_seconds))
        or cache_ttl_seconds < 0
        or cache_ttl_seconds > 3600
    ):
        raise PreflightInputError("cache_ttl_seconds must be finite and between 0 and 3600")
    if isinstance(max_cache_entries, bool) or max_cache_entries < 1:
        raise PreflightInputError("max_cache_entries must be a positive integer")
    now = _validate_now(observed_at)
    persistent = cache or ReceiptCache()
    memo = MemoizingTransport(transport)
    exact: dict[str, tuple[dict[str, Any], int]] = {}
    rows: list[dict[str, Any]] = []
    cache_hits = 0
    duplicate_hits = 0
    evaluations = 0

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Candidate):
            raise PreflightInputError(f"batch item {index} is not a validated Candidate")
        fingerprint = candidate_fingerprint(candidate)
        previous = exact.get(fingerprint)
        if previous is not None:
            receipt, first_index = previous
            rows.append(
                {
                    "index": index,
                    "source": "batch_duplicate",
                    "duplicate_of": first_index,
                    "receipt": receipt,
                }
            )
            duplicate_hits += 1
            continue

        lookup = persistent.get(candidate, now=now, ttl_seconds=cache_ttl_seconds)
        if lookup.receipt is not None:
            receipt = lookup.receipt
            rows.append(
                {
                    "index": index,
                    "source": "persistent_cache",
                    "cache_age_seconds": round(lookup.age_seconds or 0.0, 3),
                    "receipt": receipt,
                }
            )
            cache_hits += 1
        else:
            receipt = evaluator(candidate, memo, observed_at=now)
            if not isinstance(receipt, dict) or receipt.get("freshness_status") not in _ALLOWED_STATUSES:
                raise PreflightInputError(f"batch item {index} evaluator returned an invalid receipt")
            persistent.put(candidate, receipt, cached_at=now)
            rows.append({"index": index, "source": "fresh", "receipt": receipt})
            evaluations += 1
        exact[fingerprint] = (receipt, index)

    canonical_groups: dict[str, list[int]] = {}
    for row in rows:
        receipt = row["receipt"]
        canonical = receipt.get("canonical")
        url = canonical.get("url") if isinstance(canonical, Mapping) else None
        if isinstance(url, str) and url:
            canonical_groups.setdefault(url, []).append(row["index"])

    counts = {status: 0 for status in sorted(_ALLOWED_STATUSES)}
    for row in rows:
        counts[row["receipt"]["freshness_status"]] += 1

    result = {
        "schema": BATCH_SCHEMA,
        "generated_at": _iso(now),
        "authority": "canonical_github_state",
        "financial_status": "advertised_not_accepted_awarded_or_paid",
        "stats": {
            "items": len(rows),
            "unique_inputs": len(exact),
            "fresh_evaluations": evaluations,
            "persistent_cache_hits": cache_hits,
            "batch_duplicate_hits": duplicate_hits,
            "http_network_fetches": memo.network_fetches,
            "http_memo_hits": memo.memo_hits,
            "canonical_groups": len(canonical_groups),
            "canonical_duplicate_items": sum(max(0, len(v) - 1) for v in canonical_groups.values()),
            "status_counts": counts,
            "cache_ttl_seconds": cache_ttl_seconds,
            "max_cache_entries": max_cache_entries,
        },
        "canonical_groups": canonical_groups,
        "items": rows,
    }
    # Bound the in-memory cache before handing it back to callers for persistence.
    persistent = ReceiptCache.from_payload(persistent.to_payload(max_entries=max_cache_entries))
    return result, persistent
