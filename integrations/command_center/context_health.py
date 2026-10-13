"""Opt-in all-source health for an existing context page.

The default context response and its revision stay byte-for-byte the caller's
page. This envelope is a separate object with its own revision.
"""
from __future__ import annotations

import hashlib
import json


def page_condition(page):
    """Name why this page is empty or reused. Item filters are not coverage."""
    counts = page.get("counts") or {}
    pagination = page.get("pagination") or {}
    offset = pagination.get("offset") or 0
    if page.get("unchanged") is True:
        return "unchanged_page"
    if counts.get("inventory_records") == 0 and counts.get("inventory_sources") == 0:
        return "no_cached_records"
    if counts.get("matching_records") == 0:
        return "no_matches"
    if counts.get("page_records") == 0 and offset > 0:
        return "past_end"
    return "page"


def _revision(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def envelope(page, summary_sources):
    """Bounded summary or canonical page health, including zero-item sources."""
    sources = summary_sources if isinstance(summary_sources, dict) else {}
    freshness = sources.get("freshness") or {}
    body = {
        "schema": "commons-context-source-health/v1",
        "scope": "all_cached_sources",
        "independent_of_item_filters": True,
        "page_condition": page_condition(page),
        "page_revision": page.get("revision"),
        "sources": {
            "total": sources.get("total"),
            "health_state": sources.get("health_state", sources.get("state")),
            "freshness": {
                key: (sources.get(key) if key in sources else freshness.get(key, 0))
                for key in ("fresh", "retained", "stale", "unknown")
            },
            "coverage_debt_count": sources.get("coverage_debt_count"),
            "coverage_debt": sources.get("coverage_debt") or [],
            "coverage_debt_omitted": sources.get("coverage_debt_omitted"),
        },
    }
    body["revision"] = _revision({key: value for key, value in body.items() if key != "revision"})
    return body


def with_source_health(center, page):
    """Reuse canonical page health with complete bounded debt detail.

    Record counts and ingestion ages come from the page's own source generation.
    Older pages without those details retain the summary fallback.
    Does not replace page['revision'] and does not read a provider.
    """
    sources = page.get("source_health")
    debt = sources.get("coverage_debt") if isinstance(sources, dict) else None
    count = sources.get("coverage_debt_count") if isinstance(sources, dict) else None
    omitted = sources.get("coverage_debt_omitted") if isinstance(sources, dict) else None
    if not (isinstance(sources, dict)
            and sources.get("schema") == "commons-source-health/v1"
            and sources.get("independent_of_item_filters") is True
            and isinstance(debt, list)
            and type(count) is int and count >= 0
            and type(omitted) is int and omitted >= 0
            and count == len(debt) + omitted
            and all(isinstance(row, dict) and all(key in row for key in
                    ("records", "retained_records", "oldest_ingested_at"))
                    for row in debt)):
        sources = center.work_summary().get("sources") or {}
    attached = dict(page)
    attached["source_health_opt_in"] = envelope(page, sources)
    return attached
