"""Bounded Slack history/reply reads through the collector's existing budget.

Rows are ephemeral provider observations. Only selected metadata is persisted by
collectors.py; errors never carry raw exception text or arbitrary provider data.
"""
from __future__ import annotations

import re
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit


class SlackReadFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _stamp(value):
    return (isinstance(value, str)
            and re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?", value) is not None
            and int(value.split(".")[0]) <= 253402300799)


def _order(value):
    seconds, _, fraction = value.partition(".")
    return int(seconds), int(fraction.ljust(6, "0") or "0")



def resolve_thread_root(message, channel_id=None):
    """Resolve *structured* message metadata, never text or an empty reply read.

    A permalink must identify this very message/channel before its thread_ts is
    usable. Missing metadata stays unknown. This is consistency checking on an
    observation, not authentication or an election in the atomic claim ledger.
    """
    result = {"message_ts": None, "thread_ts": None, "state": "UNKNOWN",
              "reason": "root_metadata_missing", "sources": []}
    if not isinstance(message, dict) or not _stamp(message.get("ts")):
        return {**result, "reason": "message_identity_invalid"}
    stamp = message["ts"]
    result["message_ts"] = stamp
    roots = {}
    broadcast = message.get("subtype") in ("thread_broadcast", "reply_broadcast")
    try:
        if message.get("thread_ts") is not None:
            roots["thread_ts"] = message["thread_ts"]
        if "root" in message:
            parent = message["root"]
            if not isinstance(parent, dict) or not _stamp(parent.get("ts")):
                raise ValueError
            if parent.get("thread_ts", parent["ts"]) != parent["ts"]:
                raise ValueError
            if ("reply_count" in parent and (type(parent["reply_count"]) is not int
                    or not 0 <= parent["reply_count"] <= 2147483647)):
                raise ValueError
            if parent.get("latest_reply") is not None and not _stamp(parent["latest_reply"]):
                raise ValueError
            roots["root.ts"] = parent["ts"]
        if "permalink" in message:
            link = message["permalink"]
            if (not isinstance(link, str) or len(link) > 4096
                    or any(ord(c) < 33 for c in link)):
                raise ValueError
            url = urlsplit(link)
            path = re.fullmatch(r"/archives/([CDG][A-Z0-9]+)/p([0-9]{7,18})", url.path)
            if (url.scheme != "https" or not url.hostname
                    or not re.fullmatch(r"[A-Za-z0-9-]+[.]slack[.]com", url.netloc)
                    or not path or url.fragment):
                raise ValueError
            digits = path[2]
            linked_stamp = digits[:-6] + "." + digits[-6:]
            query = parse_qs(url.query, keep_blank_values=True, max_num_fields=16)
            if (not _stamp(linked_stamp) or _order(linked_stamp) != _order(stamp)
                    or (channel_id is not None and path[1] != channel_id)
                    or ("cid" in query and query["cid"] != [path[1]])):
                raise ValueError
            if "thread_ts" in query:
                if len(query["thread_ts"]) != 1:
                    raise ValueError
                roots["permalink.thread_ts"] = query["thread_ts"][0]
        if any(not _stamp(root) for root in roots.values()):
            raise ValueError
        if len({_order(root) for root in roots.values()}) > 1:
            return {**result, "state": "CONFLICT", "reason": "root_metadata_conflict",
                    "sources": sorted(roots)}
        if roots:
            root = next(iter(roots.values()))
            if _order(root) > _order(stamp) or (broadcast and _order(root) == _order(stamp)):
                raise ValueError
            return {**result, "thread_ts": root, "state": "RESOLVED",
                    "reason": None, "sources": sorted(roots)}
        if not broadcast and type(message.get("reply_count")) is int and 0 <= message["reply_count"] <= 2147483647:
            return {**result, "thread_ts": stamp, "state": "RESOLVED",
                    "reason": None, "sources": ["reply_count"]}
    except (ValueError, TypeError, KeyError):
        return {**result, "state": "CONFLICT", "reason": "root_metadata_invalid"}
    return result


def _prior_evidence(messages, root):
    """Combine every structured observation of one root without losing anchors.

    Nested broadcast roots are provider observations, not just identity hints.
    Counts use the greatest observed value; all latest-reply identities survive
    separately, even when only the newest is shown in the compact pending row.
    """
    counts, anchors = [], set()
    for message in messages:
        observations = [message] if message.get("ts") == root else []
        nested = message.get("root")
        if (isinstance(nested, dict) and _stamp(nested.get("ts"))
                and _order(nested["ts"]) == _order(root)):
            observations.append(nested)
        for observation in observations:
            count = observation.get("reply_count")
            if type(count) is int and 0 <= count <= 2147483647:
                counts.append(count)
            anchor = observation.get("latest_reply")
            if _stamp(anchor):
                anchors.add(anchor)
    return {"reply_count": max(counts) if counts else None,
            "latest_reply": max(anchors, key=_order) if anchors else None}, anchors


def _thread_evidence(replies, report, root, prior, required=()):
    """Bind completeness to root, known replies, counts and latest-reply anchors."""
    # Reply pages may carry nested root observations too. They constrain the
    # same observation, even when the top-level parent has a smaller count.
    fetched, fetched_anchors = _prior_evidence(replies.values(), root)
    counts = [count for count in (prior.get("reply_count"), fetched.get("reply_count")) if count is not None]
    expected = max(counts) if counts else None
    observed = set(replies) - {root}
    anchors = fetched_anchors | ({prior["latest_reply"]} if prior.get("latest_reply") else set())
    if report["complete"] and (root not in replies or expected is None
            or len(observed) != expected or not (anchors | set(required)).issubset(observed)):
        report.update(complete=False, reason="reply_evidence_mismatch")
    return {"thread_ts": root, "expected_replies": expected,
            "observed_replies": len(observed), **report}


def read_thread_context(read, channel_id, message, *, page_size=100, max_pages=2):
    """Read a resolved root using the collector's existing budgeted callback.

    Return (rows, coverage, complete). UNKNOWN/CONFLICT performs no provider call.
    Even complete coverage is a bounded observation, never proof of no claimant.
    Callers must retain their observation time and refresh before coordination.
    """
    for name, value, high in (("page_size", page_size, 100), ("max_pages", max_pages, 10)):
        if type(value) is not int or not 1 <= value <= high:
            raise ValueError(name + " is outside its integer bounds.")
    if not isinstance(channel_id, str) or not re.fullmatch(r"[CDG][A-Z0-9]+", channel_id):
        raise ValueError("channel_id must be an existing provider ID.")
    _page({"ok": True, "messages": [message]}, 1)
    message = deepcopy(message)
    resolution = resolve_thread_root(message, channel_id)
    metadata = {"root_resolution": resolution, "complete": False, "pages_read": 0,
                "next_cursor": "", "error": None, "reason": resolution["reason"],
                "claim_authority": False, "provider_write_authority": False}
    if resolution["state"] != "RESOLVED":
        return [dict(message)], metadata, False
    root = resolution["thread_ts"]
    replies, report = _read_pages(read, "conversations.replies",
        {"channel": channel_id, "ts": root, "limit": page_size}, max_pages, root=root)
    prior, anchors = _prior_evidence([message], root)
    required = ({message["ts"]} if message["ts"] != root else set()) | anchors
    metadata.update(_thread_evidence(replies, report, root, prior, required))
    return list(replies.values()), metadata, metadata["complete"]


def _page(response, limit, root=None):
    if not isinstance(response, dict) or response.get("ok") is not True:
        code = response.get("error") if isinstance(response, dict) else None
        known = {"thread_not_found", "channel_not_found", "missing_scope", "not_in_channel"}
        raise SlackReadFailure(code if isinstance(code, str) and code in known else "slack_response_shape")
    rows = response.get("messages")
    if not isinstance(rows, list) or len(rows) > limit:
        raise SlackReadFailure("slack_messages_shape")
    for row in rows:
        if not isinstance(row, dict) or not _stamp(row.get("ts")):
            raise SlackReadFailure("slack_messages_shape")
        for field in ("thread_ts", "latest_reply"):
            if row.get(field) is not None and not _stamp(row[field]):
                raise SlackReadFailure("slack_messages_shape")
        if ("reply_count" in row and (type(row["reply_count"]) is not int
                or not 0 <= row["reply_count"] <= 2147483647)):
            raise SlackReadFailure("slack_messages_shape")
        if "edited" in row and (not isinstance(row["edited"], dict)
                or not _stamp(row["edited"].get("ts"))):
            raise SlackReadFailure("slack_messages_shape")
        for field in ("subtype", "user", "bot_id"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise SlackReadFailure("slack_messages_shape")
        if "text" in row and not isinstance(row["text"], str):
            raise SlackReadFailure("slack_messages_shape")
        if root is not None and resolve_thread_root(row)["state"] == "CONFLICT":
            raise SlackReadFailure("slack_thread_identity")
        if root is not None and row["ts"] == root and row.get("subtype") in ("thread_broadcast", "reply_broadcast"):
            raise SlackReadFailure("slack_thread_identity")
        if root is not None and ((row["ts"] != root and row.get("thread_ts") != root)
                or (row["ts"] == root and row.get("thread_ts", root) != root)):
            raise SlackReadFailure("slack_thread_identity")
    metadata = response.get("response_metadata", {})
    if (not isinstance(metadata, dict)
            or not isinstance(metadata.get("next_cursor", ""), str)
            or len(metadata.get("next_cursor", "")) > 4000
            or type(response.get("has_more", False)) is not bool
            or type(response.get("is_limited", False)) is not bool):
        raise SlackReadFailure("slack_pagination_shape")
    return rows, metadata.get("next_cursor", ""), response.get("has_more", False), response.get("is_limited", False)


def _error(exc):
    known = {"slack_rate_limited", "collector_read_deferred", "refresh_cancelled",
             "refresh_deadline_reached", "thread_not_found", "channel_not_found",
             "missing_scope", "not_in_channel", "slack_response_shape",
             "slack_messages_shape", "slack_pagination_shape", "slack_thread_identity"}
    code = getattr(exc, "code", None)
    result = {"code": code if isinstance(code, str) and code in known else "slack_read_failed"}
    retry = getattr(exc, "retry_not_before", None)
    if retry is None and code == "slack_rate_limited":
        metadata = getattr(exc, "metadata", {})
        retry = metadata.get("retry_not_before") if isinstance(metadata, dict) else None
    # Retry times are generated by RequestBudget, never copied from provider text.
    if isinstance(retry, str) and re.fullmatch(r"[0-9T:.+Z-]{1,40}", retry):
        result["retry_not_before"] = retry
    return result


def _generation(row):
    """Capture immutable message evidence before the next provider read.

    Broadcast wrappers and a root's explicit self-thread reference are transport
    representations of the same message, not changed work. Presentation-only
    metadata (reactions, profiles) is intentionally outside this comparison.
    These signatures stay in memory; coverage metadata never includes content.
    """
    subtype = row.get("subtype")
    if subtype in ("thread_broadcast", "reply_broadcast"):
        subtype = None
    return (row.get("reply_count"), row.get("latest_reply"),
            row.get("thread_ts") or row["ts"], row.get("text"),
            row.get("user"), row.get("bot_id"), subtype,
            row.get("edited", {}).get("ts"))


def _read_pages(read, method, payload, max_pages, *, root=None, propagate_first=False):
    rows, seen, cursor, limited, changed = {}, set(), "", False, False
    generations = {}
    report = {"pages_read": 0, "complete": False, "next_cursor": "", "error": None}
    for _ in range(max_pages):
        request = {**payload, **({"cursor": cursor} if cursor else {})}
        try:
            page, next_cursor, has_more, page_limited = _page(read(method, request), payload["limit"], root)
        except Exception as exc:
            if propagate_first and not report["pages_read"]:
                raise
            report.update(error=_error(exc), reason="read_failed", next_cursor=cursor)
            break
        report["pages_read"] += 1
        for row in page:
            old = rows.get(row["ts"])
            generation = _generation(row)
            if (row["ts"] in generations and generations[row["ts"]] != generation
                    or old is not None and any(old.get(key) != row.get(key)
                        for key in ("root", "permalink", "subtype"))):
                changed = True
            generations[row["ts"]] = generation
            # Keep nested root observations stable if a callback reuses a dict.
            rows[row["ts"]] = deepcopy(row)
        limited = limited or page_limited
        report["next_cursor"] = next_cursor
        if not next_cursor:
            report.update(complete=not has_more and not limited,
                          reason="history_limited" if limited else "cursor_missing" if has_more else None)
            break
        if next_cursor in seen:
            report["reason"] = "cursor_cycle"
            break
        seen.add(next_cursor)
        cursor = next_cursor
    else:
        report["reason"] = "page_limit"
    if changed:
        report["complete"] = False
        report["reason"] = report.get("reason") or "thread_evidence_changed"
    report["is_limited"] = limited
    return rows, report


def read_channel(read, channel_id, *, page_size, max_pages, max_threads=0, max_thread_pages=2):
    """Return observed rows and honest bounded coverage, without provider writes.

    A first-history failure propagates for the existing source error/deferred
    path. Later failures retain valid pages; per-slice errors belong in metadata
    so WorkstreamStore can ingest those rows without replacing unobserved ones.
    """
    for name, value, low, high in (("page_size", page_size, 1, 100),
            ("max_pages", max_pages, 1, 10), ("max_threads", max_threads, 0, 8),
            ("max_thread_pages", max_thread_pages, 1, 10)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(name + " is outside its integer bounds.")
    rows, history = _read_pages(read, "conversations.history",
        {"channel": channel_id, "limit": page_size}, max_pages, propagate_first=True)
    candidates, required, unresolved, observations = {}, {}, [], {}
    for row in rows.values():
        resolution = resolve_thread_root(row, channel_id)
        if resolution["state"] != "RESOLVED":
            if (row.get("subtype") in ("thread_broadcast", "reply_broadcast")
                    or resolution["state"] == "CONFLICT" or row.get("thread_ts")
                    or row.get("latest_reply") or "root" in row):
                unresolved.append(resolution)
            continue
        root = resolution["thread_ts"]
        observations.setdefault(root, []).append(row)
        if row.get("reply_count", 0) or row.get("latest_reply") or root != row["ts"]:
            candidates.setdefault(root, {"thread_ts": root, "reply_count": None, "latest_reply": None})
            required.setdefault(root, set())
            if root != row["ts"]:
                required[root].add(row["ts"])
                # Preserve the resolved identity for downstream work-item refs.
                row["thread_ts"] = root
    for root, candidate in candidates.items():
        prior, anchors = _prior_evidence(observations[root], root)
        candidate.update(prior)
        required[root].update(anchors)
    # Snapshot after root resolution so a nested broadcast and its ordinary
    # reply share the same identity, while later content changes stay visible.
    generations = {stamp: _generation(row) for stamp, row in rows.items()}
    ordered = sorted(candidates, key=lambda root: (_order(candidates[root]["latest_reply"] or root), _order(root)), reverse=True)
    evidence, finished = [], set()
    for root in ordered[:max_threads]:
        replies, report = _read_pages(read, "conversations.replies",
            {"channel": channel_id, "ts": root, "limit": page_size}, max_thread_pages, root=root)
        report = _thread_evidence(replies, report, root, candidates[root], required[root])
        if any(stamp in generations and generations[stamp] != _generation(row)
                for stamp, row in replies.items()):
            report["complete"] = False
            report["reason"] = report.get("reason") or "thread_evidence_changed"
        if report["complete"]:
            finished.add(root)
        # A broadcast and its reply have the same stable message identity.
        rows.update(replies)
        generations.update((stamp, _generation(row)) for stamp, row in replies.items())
        evidence.append(report)
    pending = [candidates[root] for root in ordered if root not in finished]
    metadata = {"history_complete": history["complete"], "next_cursor": history["next_cursor"],
        "history": history, "thread_expansion_enabled": max_threads > 0,
        "threads_observed_count": len(candidates), "threads_read_count": len(evidence),
        "threads_complete_count": len(finished), "thread_coverage": evidence,
        "threads_pending": pending[:100], "threads_pending_count": len(pending),
        "threads_pending_truncated": len(pending) > 100,
        "unresolved_thread_roots": sorted(unresolved, key=lambda row: _order(row["message_ts"]))[:100],
        "unresolved_thread_roots_count": len(unresolved),
        "unresolved_thread_roots_truncated": len(unresolved) > 100}
    return list(rows.values()), metadata, history["complete"] and not pending and not unresolved
