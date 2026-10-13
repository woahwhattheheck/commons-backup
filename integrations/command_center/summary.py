"""Compact Deathstar observations over the existing command-center store.

No provider requests, dispatch, or raw conversation bodies. Counts describe
retained observations, not complete provider history or business acceptance.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import re
from urllib.parse import urlsplit

from .observability import _heartbeat_state, LIVE_S, QUIET_S, STALE_S

WINDOWS = (("15m", 900), ("1h", 3600), ("24h", 86400))
ACTIVE = {"open", "running", "active", "in_progress", "in progress", "assigned", "queued", "pending", "ready", "blocked", "ready for prospecting", "qualified", "prospect", "purchase intent"}
ATTENTION = {"error", "failed", "failure", "blocked", "uncertain", "rejected", "needs_attention"}
MONEY_KINDS = {"payment", "payout", "invoice", "bounty", "revenue"}
MONEY_STATES = {"awarded", "payable", "payment_pending", "pending", "paid", "settled", "reported_paid"}
MAX_ROWS = 12


def epoch(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.timestamp() if stamp.tzinfo else None
    except (ValueError, OverflowError):
        return None


def short(value, size=180):
    return str(value or "")[:size]


def source_freshness(source, current):
    stamp = epoch(source.get("last_good_observed_at"))
    threshold = source.get("stale_after_seconds", 900)
    if (stamp is None or current - stamp < -300 or threshold is None
            or isinstance(threshold, bool) or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold) or threshold < 0):
        return "unknown"
    if source.get("error") or source.get("retained_last_good") or str(source.get("status", "")).lower() in {"error", "failed", "offline", "unavailable"}:
        return "retained"
    return "fresh" if current - stamp <= threshold else "stale"


def item_freshness(item, source, current):
    state = source_freshness(source, current)
    if state != "fresh":
        return state
    # Both fields are the SAME ingestion clock in WorkstreamStore.ingest.
    # They establish inclusion, not provider read time or worker liveness.
    if not item.get("last_seen_at") or not source.get("last_success_at"):
        return "unknown"
    return "fresh" if item["last_seen_at"] == source["last_success_at"] else "retained"


def priority(item):
    value = (item.get("owner_work") or {}).get("priority")
    if value is None:
        value = item.get("priority")
    try:
        number = float(value)
        return number if not isinstance(value, bool) and math.isfinite(number) and number >= 0 else math.inf
    except (TypeError, ValueError):
        return math.inf


def canonical_pr(item, refs):
    parsed = urlsplit(str(item.get("url") or ""))
    match = re.fullmatch(r"/([^/]+)/([^/]+)/pull/([0-9]+)/?", parsed.path)
    if parsed.hostname == "github.com" and match:
        return (match[1].lower() + "/" + match[2].lower(), str(int(match[3])))
    repo, number = refs.get("repository") or item.get("project"), refs.get("number")
    if (isinstance(repo, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            and not isinstance(number, bool) and re.fullmatch(r"[1-9][0-9]*", str(number))):
        return repo.lower(), str(int(number))
    return None


def scalar(value, limit=160):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    return short(value, limit) if isinstance(value, str) else None


def reduce_source_health(sources, tick, max_rows=MAX_ROWS):
    """Bounded all-source health / coverage debt. Independent of item filters.

    `sources` is a dict of id -> raw source objects (WorkstreamStore shape).
    Distinguishes fresh-complete observation from unknown/degraded. Exception
    details stay bounded; raw errors and credentials never leave.
    Shared by Deathstar summary and context discovery pages.
    """
    if isinstance(sources, dict):
        pairs = list(sources.items())
    else:
        pairs = []
        for row in sources or []:
            if not isinstance(row, dict):
                continue
            key = row.get("id")
            if isinstance(key, str) and key:
                pairs.append((key, row))
    counts = Counter()
    debt = []
    for key, source in pairs:
        if not isinstance(source, dict):
            continue
        fresh = source_freshness(source, tick)
        counts[fresh] += 1
        declared = (source.get("coverage") or {}).get("complete")
        meta = source.get("metadata") or {}
        if fresh != "fresh" or declared is not True:
            debt.append({
                "id": short(key, 512), "label": short(source.get("label") or key),
                "freshness": fresh, "complete": declared is True,
                "mode": short(source.get("sync_mode") or "unknown", 40),
                "last_good_observed_at": source.get("last_good_observed_at"),
                "last_attempt_at": source.get("last_attempt_at"),
                "pagination_remaining": scalar((source.get("coverage") or {}).get("pagination_remaining")),
                "threads_pending": scalar(meta.get("threads_pending_count")),
                "repositories_pending": scalar(meta.get("action_repositories_pending_count")),
                "has_error": bool(source.get("error")),
                "retained_last_good": source.get("retained_last_good") is True,
            })
    total = len(pairs)
    if total == 0:
        state = "unknown"
    elif not debt:
        state = "fresh_complete"
    elif counts.get("unknown", 0) == total:
        state = "unknown"
    else:
        state = "degraded"
    return {
        "schema": "commons-source-health/v1",
        "total": total,
        "freshness": {key: counts.get(key, 0) for key in ("fresh", "retained", "stale", "unknown")},
        "state": state,
        "coverage_debt_count": len(debt),
        "coverage_debt": debt[:max_rows],
        "coverage_debt_omitted": max(0, len(debt) - max_rows),
        "independent_of_item_filters": True,
    }


def compact_counts(values):
    counted = Counter(values)
    pairs = counted.most_common(MAX_ROWS)
    return {"values": dict(pairs), "other": sum(counted.values()) - sum(v for _, v in pairs)}


def build_summary(work, now=None):
    current = datetime.now(timezone.utc) if now is None else now
    tick = current.timestamp()
    sources = {source["id"]: source for source in work.get("sources", [])}
    items = work.get("items", [])
    source_counts = Counter()
    work_counts = {key: 0 for key in ("fresh", "retained", "stale", "unknown")}
    open_counts = dict(work_counts)
    attention_counts = dict(work_counts)
    source_rows = {key: {"records": 0, "retained_records": 0, "oldest_ingested_at": None}
                   for key in sources}
    choices, choice_keys, payments, heartbeats = [], [], {}, {}
    events = {name: set() for name, _ in WINDOWS}
    missing_merge_time = set()
    unknown_merge_identity = set()
    money_conflicts = set()
    statuses = Counter()
    total_work = controls = choice_count = 0
    for item in items:
        source = sources.get(item.get("source_id"), {})
        fresh = item_freshness(item, source, tick)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        refs = item.get("refs") if isinstance(item.get("refs"), dict) else {}
        kind = short(item.get("kind")).lower()
        status = short(item.get("status") or "unknown").lower()
        stats = source_rows.get(item.get("source_id"))
        if stats is not None:
            stats["records"] += 1
            stats["retained_records"] += int(fresh == "retained")
            seen = item.get("last_seen_at")
            if epoch(seen) is not None and (stats["oldest_ingested_at"] is None or seen < stats["oldest_ingested_at"]):
                stats["oldest_ingested_at"] = seen
        control = (item.get("countable") is False or item.get("control")
                   or item.get("row_type") == "control" or item.get("record_type") == "control")
        if control:
            controls += 1
            continue
        total_work += 1
        work_counts[fresh] += 1
        statuses[status] += 1
        active = status in ACTIVE
        attention = bool(re.search(r"failed|failure|error|blocked|uncertain|needs_attention|rejected", status)) or item.get("needs_attention") is True
        if active and kind not in {"email", "slack_thread", "feature"}:
            open_counts[fresh] += 1
        if attention:
            attention_counts[fresh] += 1
        rank = priority(item)
        if attention or ((active or kind == "email" and status in {"unread", "received"})
                         and (kind not in {"email", "slack_thread", "feature"} or math.isfinite(rank))):
            choice_count += 1
            key = (rank, fresh != "fresh", not attention, short(item.get("id")))
            # Inserting after equal keys preserves the original stable sort order.
            index = bisect_right(choice_keys, key)
            if index < MAX_ROWS:
                if len(choices) == MAX_ROWS:
                    choice_keys.pop()
                    choices.pop()
                choice_keys.insert(index, key)
                choices.insert(index, {
                    "id": short(item.get("id"), 512), "source_id": short(item.get("source_id"), 512),
                    "title": short(item.get("title")), "status": status, "freshness": fresh,
                    "owner": short(item.get("owner")), "priority": None if not math.isfinite(rank) else rank,
                    "next_action": short((item.get("owner_work") or {}).get("next_action") or item.get("next_action"), 280),
                    "url": short(item.get("url"), 1024), "last_ingested_at": item.get("last_seen_at"),
                    "source_observed_at": source.get("last_good_observed_at"),
                })
        if kind == "pull_request":
            identity = canonical_pr(item, refs)
            merged = epoch(refs.get("merged_at"))
            if merged is not None and identity is None:
                unknown_merge_identity.add((item.get("source_id"), item.get("id")))
            if merged is not None and merged <= tick and identity is not None:
                for name, seconds in WINDOWS:
                    if tick - seconds <= merged:
                        events[name].add(identity)
            elif merged is None and status == "merged":
                missing_merge_time.add(identity or (item.get("source_id"), item.get("id")))
        # Only an explicit heartbeat is a heartbeat; a claim or ingest is not.
        beat = meta.get("heartbeat_at") or refs.get("heartbeat_at")
        if beat is not None:
            identity = str(meta.get("session_id") or refs.get("session_id") or item.get("id"))
            if identity not in heartbeats or (epoch(beat) or 0) > (epoch(heartbeats[identity]) or 0):
                heartbeats[identity] = beat
        if kind in MONEY_KINDS and status in MONEY_STATES:
            currency = short(item.get("currency"), 8).upper()
            try:
                amount = Decimal(str(item.get("amount")))
            except (InvalidOperation, ValueError):
                continue
            if not amount.is_finite() or amount < 0 or not currency:
                continue
            identity = (str(item.get("provider") or source.get("provider") or "").lower(),
                        str(refs.get("payment_id") or refs.get("transaction_id") or item.get("id")))
            # Duplicated connector observations of the same payment count once.
            seen = (epoch(item.get("updated_at")) or epoch(item.get("activity_observed_at"))
                    or epoch(item.get("last_seen_at")) or 0)
            if identity not in payments or seen > payments[identity][0]:
                payments[identity] = (seen, currency, status, amount)
                money_conflicts.discard(identity)
            elif seen == payments[identity][0] and (currency, status, amount) != payments[identity][1:]:
                money_conflicts.add(identity)

    health = reduce_source_health(sources, tick)
    source_counts.update(health["freshness"])
    coverage = []
    for row in health["coverage_debt"]:
        key = row["id"]
        coverage.append({**row, **source_rows.get(key, {"records": 0, "retained_records": 0, "oldest_ingested_at": None})})
    # Preserve omitted count after record merge (same bound).
    coverage_omitted = health["coverage_debt_omitted"]
    sums = {}
    for identity, (_, currency, status, amount) in payments.items():
        if identity in money_conflicts:
            continue
        key = (currency, status)
        sums[key] = sums.get(key, Decimal(0)) + amount
    revenue = [{"currency": currency, "status": status, "amount": str(amount)}
               for (currency, status), amount in sorted(sums.items())]
    live = Counter(_heartbeat_state(beat, current, (LIVE_S, QUIET_S, STALE_S))[0]
                   for beat in heartbeats.values())
    refresh = work.get("refresh") or {}
    # Only selected scalar/provider-budget fields leave the private store.
    raw_budget = refresh.get("request_budget") or {}
    budget = {key: scalar(raw_budget.get(key)) for key in ("observed_attempts", "deferred_reads", "rate_limit_responses", "persistence")}
    budget["scopes"] = []
    for row in list(raw_budget.get("scopes") or [])[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        clean = {key: scalar(row.get(key)) for key in ("scope", "retry_not_before", "last_attempt_at", "last_rate_limit_at", "retry_basis", "total_observed_attempts", "total_deferred_reads", "total_rate_limit_responses")}
        deadline = epoch(clean["retry_not_before"])
        clean["retry_remaining_seconds"] = max(0, deadline - tick) if deadline is not None else None
        clean["state"] = "rate_limited" if deadline is not None and deadline > tick else "ready" if deadline is not None else "unknown"
        budget["scopes"].append(clean)
    budget["scope_count"] = scalar(raw_budget.get("scope_count"))
    budget["scopes_truncated"] = scalar(raw_budget.get("scopes_truncated"))
    count = raw_budget.get("scope_count")
    count = count if type(count) is int and count >= 0 else len(raw_budget.get("scopes") or [])
    budget["omitted_scopes"] = max(0, count - len(budget["scopes"]))
    return {
        "ok": True, "schema": "commons-deathstar-summary/v1",
        "generated_at": current.isoformat().replace("+00:00", "Z"),
        "provider_requests": 0,
        "sources": {"total": len(sources), **{k: source_counts[k] for k in work_counts},
                    "coverage_debt_count": health["coverage_debt_count"], "coverage_debt": coverage[:MAX_ROWS],
                    "coverage_debt_omitted": coverage_omitted,
                    "health_state": health["state"]},
        "work": {"total": total_work, "control_records": controls, "freshness": work_counts,
                 "open": open_counts, "attention": attention_counts,
                 "statuses": compact_counts(statuses),
                 "top_attention": choices,
                 "attention_omitted": max(0, choice_count - MAX_ROWS)},
        "workers": {"explicit_heartbeats": len(heartbeats), "liveness": dict(live),
                    "coverage": "observed_subset" if heartbeats else "unknown",
                    "note": "No heartbeat is inferred from a claim, document edit, or ingestion."},
        "throughput": {"merged_prs": {name: len(events[name]) for name, _ in WINDOWS},
                       "basis": "observed_lower_bound", "missing_merge_timestamps": len(missing_merge_time),
                       "unresolved_identity_records": len(unknown_merge_identity),
                       "note": "Unique PRs with actual merged_at in retained data; not a complete provider history, tests, deployed features, or payments."},
        "revenue": {"observed_amounts": revenue[:MAX_ROWS], "omitted_groups": max(0, len(revenue) - MAX_ROWS),
                    "records": len(payments), "conflicting_records": len(money_conflicts), "coverage": "observed_subset" if payments else "unknown",
                    "note": "Typed payment/bounty records by reported status; quoted prices and message prose excluded. Not a reconciled account statement."},
        "refresh": {"status": refresh.get("status", "unknown"),
                    "last_completed_at": refresh.get("last_completed_at"),
                    "deferred_sources": [{key: scalar(row.get(key)) for key in ("source_id", "provider", "scope", "reason", "retry_not_before")} for row in list(refresh.get("deferred_sources") or [])[:MAX_ROWS] if isinstance(row, dict)],
                    "observed_deferred_readers_count": len(refresh.get("deferred_sources") or []),
                    "request_budget": budget},
        "decisions": "/api/decisions",
        "scope": "Existing command-center observations. Direct peer access and existing queues are unchanged.",
    }
