#!/usr/bin/env python3
"""Every cross-harness tool call on the shared equipment road, one row each.

WHY THIS EXISTS
---------------
A seat in one harness can call a tool held by another. It posts a
`<commons_equipment_request>` envelope in the equipment thread, the carrier
attached to the owner-PC gateway executes it, and the answer comes back in the
same thread as `<commons_equipment_result>` parts
(integrations/shared_equipment/README.md, section 4). The carrier keeps its
own journal on the machine that runs it. The thread is the record every seat
can read, and nobody can read it by eye at the pace it moves: most of its
messages are envelopes, one answer can span many messages, and a request that
got no answer looks exactly like one whose answer is further down.

This module reads a copy of the thread and returns one row per request, keyed
by (request_id, call_id) the way the carrier journals it:

    DELIVERED        every part arrived, the joined answer reproduces the
                     digest the carrier stamped on it, and it reports success
    ERROR            the answer arrived whole and reports a failure
    UNCERTAIN        the answer arrived whole and says the effect is unknown;
                     inspect before issuing any new call, per the carrier
    PARTIAL          a part, or the end of a part, is not in the copy
    DIGEST_MISMATCH  every part is present but the joined text does not
                     reproduce the stamped digest; a rendering that altered
                     bytes does this, so read the thread through the API
    PENDING          no answer in the copy

Success and uncertainty are judged by integrations/shared_equipment/outcomes,
the same two functions the carrier uses, so the ledger cannot disagree with
the equipment about what counts as failed.

WHAT IT READS
-------------
Three shapes of the same thread, any number of pages:

  * Slack Web API JSON (`conversations.replies`). Its `text` escapes `<`, `>`
    and `&`; one layer is decoded, ampersand last, the rule the carrier
    applies to requests.
  * The Slack connector's `detailed` text (From / Time / Message TS blocks).
  * The connector's `concise` text. It carries no timestamps, so latency and
    age read UNKNOWN, never zero. Pass each concise page once: a reposted
    request is byte-identical to its first posting and is kept as a repost.

A tool-results file that wraps either connector text in JSON is read as-is.

THE COPY IS THE SEARCH SPACE
----------------------------
PENDING means "no answer in the pages supplied". It is not "failed". An
answer is always newer than its request, so a PENDING row is only as good as
the newest end of the copy. The Slack connector pages a thread newest first:
the page fetched without a cursor is the newest, and "There are no more
messages" marks the oldest (measured 2026-09-10). The Web API pages oldest
first, and `has_more: false` marks the newest. `source.pages` lists what each
supplied page said about the rest; `source.newest_end_seen` is true only when
an API page said nothing newer was left, and UNKNOWN otherwise, because a
saved connector page does not record whether it was fetched without a cursor.
The ledger cannot see a page missing from the middle either, and says so
rather than guessing. It can see one kind of hole: the connector's detailed
text counts the replies it fetched ("=== THREAD REPLIES (N total) ===") and
then prints only until its output budget (about 100,000 characters) runs
out, while still saying "There are no more messages" or handing back a
cursor that skips the unprinted span. A page that prints fewer replies than
it counted is listed in `source.gaps` with the last printed ts; read that
span again with oldest=<that ts> (and latest=<the page's upper bound> for a
cursor page). A PENDING row whose request is not newer than a gap is marked
`may_be_in_gap`, because its answer may be among the dropped replies.
A connector thread read has also returned an older
state while a search for the exact request id found the answer (ROWAN,
2026-09-07), so search the request_id before acting on a PENDING row. Ages are measured against the newest message in the
copy unless `--now` is given, and `overdue` marks a pending request older
than `--overdue-after` seconds (default 300; the carrier polls every 15).

A request posted again with the same ids is a repost, and the carrier answers
each posting from its journal, so one row can hold several answers. The row
reports the newest whole answer, or the newest answer when none is whole, and
counts them all.

In the copies read on 2026-09-10, a posted part longer than 4,000 characters
appears as consecutive messages of at most 4,000 characters from the same
poster. A part therefore continues through the following messages from its
poster until its closing tag, joined with nothing between them; on those
copies the joined text reproduced the carrier's digest for 36 of 36 complete
answers. The carrier executes an envelope only when it begins its message, so
an envelope quoted inside other text is listed under `quoted_envelopes`, not
as a request.

WHAT IT NEVER COPIES
--------------------
No result content and no argument values. A row carries the operation name,
the argument names, the credential reference name where one was asked for,
the harness named in the poster's footer, a 120-character note, sizes,
counts, states, error codes and timestamps. Sealed credential results stay in
the thread.

    python host/equipment_ledger.py PAGE [PAGE ...] [--now ISO] [--text]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from integrations.shared_equipment.outcomes import (  # noqa: E402
    effect_uncertain,
    tool_failed,
)

SCHEMA = "commons.equipment_ledger.v1"
STATES = ("PENDING", "PARTIAL", "UNCERTAIN", "ERROR", "DIGEST_MISMATCH", "DELIVERED")
OVERDUE_AFTER_S = 300
NOTE_CAP = 120

REQUEST_OPEN = "<commons_equipment_request>"
REQUEST_CLOSE = "</commons_equipment_request>"
ESCAPED_REQUEST_OPEN = "&lt;commons_equipment_request&gt;"
RESULT_CLOSE = "\n</commons_equipment_result>"
_JSON_STRING = r'"(?:[^"\\]|\\.)*"'
RESULT_OPEN = re.compile(
    r"<commons_equipment_result request_id=(" + _JSON_STRING + r") "
    r"call_id=(" + _JSON_STRING + r") "
    r'part="(\d+)/(\d+)" sha256="([0-9a-f]{64})">\n')
SENT_USING = re.compile(r"\*Sent using\* <@[A-Z0-9]+\|([^>]+)>")

DETAILED_HEADER = re.compile(
    r"(?m)^(?:=== THREAD PARENT MESSAGE ===|--- Reply \d+ of \d+ ---)\n"
    r"From: (.*)\nTime: .*\nMessage TS: (\d+\.\d+)\n")
DETAILED_REPLIES = re.compile(r"\n\n=== THREAD REPLIES \(\d+ total\) ===\n\n$")
REPLIES_TOTAL = re.compile(r"(?m)^=== THREAD REPLIES \((\d+) total\) ===$")
CONCISE_SPLIT = re.compile(r"\n> (?=[^\n<>]{1,120} <[^<>\s]+>: )")
CONCISE_AUTHOR = re.compile(r"^([^\n<>]{1,120}) <[^<>\s]+>: ")


# --------------------------------------------------------------- reading ---

def _message(ts, author, text):
    return {"ts": ts, "author": author, "text": text}


def _name_only(author):
    """Display name without the address a connector appends to it."""
    head = author.split(" <", 1)[0].strip()
    return head or author.strip() or "UNKNOWN"


def read_api(value):
    """(messages, more) from Web API JSON: a replies page or a bare list."""
    if isinstance(value, dict):
        rows = value.get("messages") or []
        has_more = value.get("has_more")
        cursor = (value.get("response_metadata") or {}).get("next_cursor")
        more = "UNKNOWN" if has_more is None else bool(has_more or cursor)
    else:
        rows, more = value, "UNKNOWN"
    out = []
    for row in rows:
        if not isinstance(row, dict) or "ts" not in row:
            continue
        text = str(row.get("text", ""))
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        author = (row.get("username") or (row.get("bot_profile") or {}).get("name")
                  or row.get("bot_id") or row.get("user") or "UNKNOWN")
        out.append(_message(str(row["ts"]), str(author), text))
    return out, more


def read_detailed(text):
    heads = list(DETAILED_HEADER.finditer(text))
    out = []
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        body = text[head.end():end]
        if index == 0 and DETAILED_REPLIES.search(body):
            body = DETAILED_REPLIES.sub("", body)
        elif index + 1 < len(heads):
            body = body[:-2] if body.endswith("\n\n") else body
        elif body.endswith("\n"):
            body = body[:-1]
        out.append(_message(head.group(2), _name_only(head.group(1)), body))
    return out


def read_concise(text):
    if text.startswith("THREAD: "):
        text = text[len("THREAD: "):]
    chunks = CONCISE_SPLIT.split(text)
    out = []
    parent = chunks[0]
    if parent.endswith("\n"):
        parent = parent[:-1]
    out.append(_message(None, "THREAD", parent))
    for index, chunk in enumerate(chunks[1:], start=1):
        if index == len(chunks) - 1 and chunk.endswith("\n"):
            chunk = chunk[:-1]
        author = CONCISE_AUTHOR.match(chunk)
        if author:
            out.append(_message(None, author.group(1).strip(), chunk[author.end():]))
        else:
            out.append(_message(None, "UNKNOWN", chunk))
    return out


def _cut(text, messages):
    """What a detailed page dropped: the connector counts the replies it
    fetched in its header, prints until its output budget runs out, and still
    says "There are no more messages" (or hands back a cursor that skips the
    dropped span). Measured 2026-09-11: 31 of 69 saved pages over ~97,000
    characters printed fewer replies than their header counted.
    """
    total = REPLIES_TOTAL.search(text)
    printed = len(messages) - 1
    if not total or printed >= int(total.group(1)):
        return None
    return {"dropped": int(total.group(1)) - printed,
            "resume_after": messages[-1]["ts"] if printed > 0 else None}


def _connector_text(text, pagination):
    cut = None
    if "Message TS: " in text and DETAILED_HEADER.search(text):
        messages, fmt = read_detailed(text), "slack-connector-detailed"
        cut = _cut(text, messages)
    else:
        messages, fmt = read_concise(text), "slack-connector-concise"
    if "There are no more messages" in pagination:
        more = False
    elif "There are more messages" in pagination:
        more = True
    else:
        more = "UNKNOWN"
    return messages, more, fmt, cut


def read_page(raw):
    """(messages, more, format, cut) from one saved page in any known shape.

    `more` is what the page said about messages beyond it: True, False, or
    UNKNOWN when it said nothing. `cut` is None, or what a detailed connector
    page silently dropped: {"dropped": n, "resume_after": ts}.
    """
    try:
        value = json.loads(raw)
    except ValueError:
        return _connector_text(raw, raw[-200:])
    if isinstance(value, list) and value and isinstance(value[0], dict) \
            and isinstance(value[0].get("text"), str) and "ts" not in value[0]:
        return read_page(value[0]["text"])
    if isinstance(value, dict) and isinstance(value.get("messages"), str):
        return _connector_text(value["messages"], str(value.get("pagination_info", "")))
    messages, more = read_api(value)
    return messages, more, "slack-api-json", None


def _ts_key(ts):
    whole, _, fraction = ts.partition(".")
    return int(whole), int((fraction + "000000")[:6])


def _filler(cut, index, pages):
    """Index of a page that provably holds the replies page `index` dropped.

    The connector's oldest= is exclusive and returns the next replies in time
    order (measured 2026-09-11), so a page fetched with oldest <= the last
    printed ts holds every reply after it up to its own last one. It fills
    the gap when it printed at least as many replies past that ts as were
    dropped, or reached the thread's newest end uncut.
    """
    after = _ts_key(cut["resume_after"])
    for other, page in enumerate(pages):
        oldest = page[4] if len(page) > 4 else None
        if other == index or not oldest or _ts_key(oldest) > after:
            continue
        own_cut = page[3] if len(page) > 3 else None
        past = sum(1 for m in page[0] if m["ts"] and _ts_key(m["ts"]) > after)
        if past >= cut["dropped"] or (page[1] is False and not own_cut):
            return other
    return None


def merge_pages(pages):
    """(messages, page summaries) for one ordered copy of several pages.

    With timestamps on every message the copy is sorted and de-duplicated by
    them. Without (concise pages) the supplied order stands and only the
    repeated thread parent is dropped.
    """
    messages, summaries = [], []
    for page in pages:
        page_messages, more, fmt = page[:3]
        cut = page[3] if len(page) > 3 else None
        oldest = page[4] if len(page) > 4 else None
        messages.extend(page_messages)
        summary = {"format": fmt, "messages": len(page_messages), "more": more}
        if cut:
            summary.update(cut)
        if oldest:
            summary["oldest"] = oldest
        summaries.append(summary)
    for index, page in enumerate(pages):
        cut = page[3] if len(page) > 3 else None
        if cut and cut["resume_after"]:
            filler = _filler(cut, index, pages)
            if filler is not None:
                summaries[index]["filled_by_page"] = filler
    if messages and all(m["ts"] for m in messages):
        unique = {}
        for m in messages:
            unique.setdefault(m["ts"], m)
        messages = [unique[ts] for ts in sorted(unique, key=_ts_key)]
    else:
        seen_parent, kept = set(), []
        for m in messages:
            if m["author"] == "THREAD":
                if m["text"] in seen_parent:
                    continue
                seen_parent.add(m["text"])
            kept.append(m)
        messages = kept
    return messages, summaries


# ----------------------------------------------------------------- parsing --

def _starts_envelope(text):
    t = _unfenced(text.strip())
    return (t.startswith(REQUEST_OPEN) or t.startswith(ESCAPED_REQUEST_OPEN)
            or t.startswith("<commons_equipment_result "))


def _unfenced(text):
    if text.startswith("```"):
        return text[3:].lstrip("\n")
    return text


def _note(footer):
    footer = SENT_USING.sub("", footer).strip()
    footer = " ".join(footer.split())
    if len(footer) > NOTE_CAP:
        footer = footer[:NOTE_CAP - 1] + "…"
    return footer or None


def parse_request(text):
    """The carrier's rule: an envelope counts only when it begins the message.

    Returns (request, footer) for an executable envelope, ("QUOTED", request)
    for an envelope found later in the text, (None, reason) for one that begins
    the message but cannot be read, or None when there is no envelope.
    """
    t = text.strip()
    if t.startswith(ESCAPED_REQUEST_OPEN):
        t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    if not t.startswith(REQUEST_OPEN):
        if REQUEST_OPEN in t:
            body = t.split(REQUEST_OPEN, 1)[1].partition(REQUEST_CLOSE)[0]
            try:
                value = json.loads(body)
            except ValueError:
                value = {}
            return "QUOTED", value if isinstance(value, dict) else {}
        return None
    body, found, footer = t[len(REQUEST_OPEN):].partition(REQUEST_CLOSE)
    if not found:
        return None, "envelope is incomplete"
    try:
        value = json.loads(body)
    except ValueError as exc:
        return None, "request is not JSON: " + str(exc)[:80]
    if not isinstance(value, dict):
        return None, "request must be an object"
    for key in ("request_id", "call_id", "name"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            return None, key + " must be a nonempty string"
    if not isinstance(value.get("arguments", {}), dict):
        return None, "arguments must be an object"
    return value, footer


def _error_code(value, depth=0):
    if not isinstance(value, dict) or depth > 5:
        return None
    for key in ("code", "error"):
        found = value.get(key)
        if isinstance(found, str) and found:
            return found[:80]
        if isinstance(found, dict):
            inner = _error_code(found, depth + 1)
            if inner:
                return inner
            if isinstance(found.get("class"), str):
                return found["class"][:80]
    for key in ("result", "structuredContent"):
        inner = _error_code(value.get(key), depth + 1)
        if inner:
            return inner
    return None


def _seconds(ts):
    if not ts:
        return None
    whole, fraction = _ts_key(ts)
    return whole + fraction / 1_000_000


# ------------------------------------------------------------------ ledger --

def build(messages, pages=(), now=None, overdue_after_s=OVERDUE_AFTER_S):
    """The ledger for one ordered copy of the thread.

    `pages` are the summaries merge_pages returns; a caller holding messages
    from elsewhere may pass none, and the copy's newest end is then UNKNOWN.
    """
    requests, order, answers = {}, [], {}
    quoted, unreadable = [], []
    index = 0
    while index < len(messages):
        message = messages[index]
        text = message["text"]
        parsed = parse_request(text)
        if parsed is not None:
            request, extra = parsed
            if request == "QUOTED":
                rid, name = extra.get("request_id"), extra.get("name")
                quoted.append({"ts": message["ts"], "by": message["author"],
                    "request_id": rid if isinstance(rid, str) else None,
                    "name": name if isinstance(name, str) else None})
            elif request is None:
                unreadable.append({"ts": message["ts"], "by": message["author"], "reason": extra})
            else:
                key = (request["request_id"], request["call_id"])
                via = SENT_USING.search(extra)
                ask = {"ts": message["ts"], "by": message["author"],
                       "via": via.group(1) if via else None, "note": _note(extra)}
                if key not in requests:
                    arguments = request.get("arguments") or {}
                    ref = arguments.get("credential_ref")
                    requests[key] = {"name": request["name"],
                        "argument_names": sorted(str(k) for k in arguments),
                        "credential_ref": ref if isinstance(ref, str) else None,
                        "asked": []}
                    order.append(key)
                requests[key]["asked"].append(ask)
            index += 1
            continue
        opened = RESULT_OPEN.match(_unfenced(text.lstrip()))
        if not opened:
            index += 1
            continue
        content = _unfenced(text.lstrip())[opened.end():]
        last = index
        while RESULT_CLOSE not in content and last + 1 < len(messages):
            follower = messages[last + 1]
            if follower["author"] != message["author"] or _starts_envelope(follower["text"]):
                break
            last += 1
            content += follower["text"]
        closed = RESULT_CLOSE in content
        if closed:
            content = content.split(RESULT_CLOSE, 1)[0]
        key = (json.loads(opened.group(1)), json.loads(opened.group(2)))
        number, total, digest = int(opened.group(3)), int(opened.group(4)), opened.group(5)
        attempts = answers.setdefault(key, [])
        current = attempts[-1] if attempts else None
        if (current is None or number in current["parts"]
                or current["total"] != total or current["digest"] != digest):
            current = {"total": total, "digest": digest, "parts": {},
                       "first_ts": message["ts"], "order": index}
            attempts.append(current)
        current["parts"][number] = {"content": content, "closed": closed,
                                    "last_ts": messages[last]["ts"]}
        index = last + 1

    stamps = [m["ts"] for m in messages if m["ts"]]
    if now is not None:
        reference, reference_source = now, "now"
    elif stamps:
        reference, reference_source = max(_seconds(s) for s in stamps), "newest_message"
    else:
        reference, reference_source = None, "UNKNOWN"

    rows = [_row(key, requests[key], answers.get(key, []), reference, overdue_after_s)
            for key in order]
    gaps = []
    for page in pages:
        if not page.get("dropped"):
            continue
        gap = {"after_ts": page["resume_after"], "dropped": page["dropped"]}
        if page.get("filled_by_page") is not None:
            gap["filled_by_page"] = page["filled_by_page"]
        gaps.append(gap)
    open_gaps = [g for g in gaps if "filled_by_page" not in g]
    for row in rows:
        if row["state"] != "PENDING" or not open_gaps:
            continue
        asked = [a["ts"] for a in row["asked"] if a["ts"]]
        newest = max(asked, key=_ts_key) if asked else None
        row["may_be_in_gap"] = any(
            g["after_ts"] is None or newest is None
            or _ts_key(g["after_ts"]) >= _ts_key(newest) for g in open_gaps)
    orphans = [_row(key, None, answers[key], reference, overdue_after_s)
               for key in sorted(answers, key=lambda k: answers[k][0]["order"])
               if key not in requests]

    by_state = {state: 0 for state in STATES}
    by_name = {}
    for row in rows:
        by_state[row["state"]] += 1
        tally = by_name.setdefault(row["name"], {})
        tally[row["state"]] = tally.get(row["state"], 0) + 1
    return {
        "schema": SCHEMA,
        "source": {
            "pages": list(pages),
            "messages": len(messages),
            "first_ts": min(stamps, key=_ts_key) if stamps else "UNKNOWN",
            "last_ts": max(stamps, key=_ts_key) if stamps else "UNKNOWN",
            "newest_end_seen": True if any(
                p["format"] == "slack-api-json" and p["more"] is False for p in pages
            ) else "UNKNOWN",
            "gaps": gaps,
            "reference_source": reference_source,
            "reference_ts": _iso(reference) if reference is not None else "UNKNOWN",
        },
        "counts": {
            "requests": len(rows),
            "by_state": by_state,
            "by_name": {name: by_name[name] for name in sorted(by_name)},
            "reposted": sum(1 for row in rows if len(row["asked"]) > 1),
            "orphan_results": len(orphans),
            "quoted_envelopes": len(quoted),
            "unreadable_requests": len(unreadable),
        },
        "rows": rows,
        "orphan_results": orphans,
        "quoted_envelopes": quoted,
        "unreadable_requests": unreadable,
    }


def _row(key, request, attempts, reference, overdue_after_s):
    rid, cid = key
    row = {"request_id": rid, "call_id": cid,
           "name": request["name"] if request else "UNKNOWN",
           "asked": request["asked"] if request else [],
           "argument_names": request["argument_names"] if request else [],
           "credential_ref": request["credential_ref"] if request else None,
           "answers": len(attempts)}
    if not attempts:
        row.update(state="PENDING", error=None, parts=None, answered_ts=None,
                   answer_after_s=None, answer_chars=None, digest="NOT_CHECKED")
        asked = [_seconds(a["ts"]) for a in row["asked"] if a["ts"]]
        if asked and reference is not None:
            row["age_s"] = round(reference - max(asked), 3)
            row["overdue"] = row["age_s"] > overdue_after_s
        else:
            row["age_s"], row["overdue"] = "UNKNOWN", "UNKNOWN"
        return row
    judged = [_judge(attempt, row["asked"]) for attempt in attempts]
    whole = [j for j in judged if j["state"] != "PARTIAL"]
    row.update(whole[-1] if whole else judged[-1])
    return row


def _judge(attempt, asked):
    """State of one answer: its parts, its digest, then what it reports."""
    total, parts = attempt["total"], attempt["parts"]
    present = sorted(parts)
    closed = [i for i in present if parts[i]["closed"]]
    last_ts = [parts[i]["last_ts"] for i in present if parts[i]["last_ts"]]
    first = _seconds(attempt["first_ts"])
    before = [_seconds(a["ts"]) for a in asked
              if a["ts"] and first is not None and _seconds(a["ts"]) <= first]
    out = {"state": "PARTIAL", "error": None,
           "parts": {"expected": total, "present": len(present), "closed": len(closed)},
           "answered_ts": max(last_ts, key=_ts_key) if last_ts else None,
           "answer_after_s": round(first - max(before), 3) if before else "UNKNOWN",
           "answer_chars": None, "digest": "NOT_CHECKED"}
    if present != list(range(1, total + 1)) or len(closed) != total:
        return out
    joined = "".join(parts[i]["content"] for i in present)
    out["answer_chars"] = len(joined)
    if hashlib.sha256(joined.encode("utf-8")).hexdigest() != attempt["digest"]:
        out.update(state="DIGEST_MISMATCH", digest="MISMATCH")
        return out
    out["digest"] = "MATCH"
    try:
        envelope = json.loads(joined)
    except ValueError:
        out.update(state="DIGEST_MISMATCH", error="answer is not JSON")
        return out
    result = envelope.get("result") if isinstance(envelope, dict) else None
    if effect_uncertain(result):
        out.update(state="UNCERTAIN", error=_error_code(result))
    elif tool_failed(result):
        out.update(state="ERROR", error=_error_code(result))
    else:
        out["state"] = "DELIVERED"
    return out


def _iso(seconds):
    return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_now(value):
    moment = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    return moment.timestamp()


def page_argument(argument):
    """(path, oldest) from PAGE or PAGE@oldest=TS, the ts a follow-up read
    started after. Only a page named this way can close a gap."""
    path, marker, oldest = argument.rpartition("@oldest=")
    if marker and re.fullmatch(r"\d+\.\d+", oldest):
        return path, oldest
    return argument, None


def from_files(paths, now=None, overdue_after_s=OVERDUE_AFTER_S):
    pages = []
    for argument in paths:
        path, oldest = page_argument(argument)
        with open(path, encoding="utf-8") as handle:
            pages.append(tuple(read_page(handle.read())) + (oldest,))
    messages, summaries = merge_pages(pages)
    return build(messages, summaries, now, overdue_after_s)


# --------------------------------------------------------------------- CLI --

def as_text(ledger):
    counts, source = ledger["counts"], ledger["source"]
    lines = ["%d requests in %d messages from %d page(s); newest end seen: %s" % (
        counts["requests"], source["messages"], len(source["pages"]),
        source["newest_end_seen"])]
    lines.append("  " + "  ".join("%s %d" % (s, counts["by_state"][s]) for s in STATES))
    for gap in source.get("gaps", []):
        head = "%d repl%s dropped after %s" % (
            gap["dropped"], "y" if gap["dropped"] == 1 else "ies", gap["after_ts"] or "the parent")
        if "filled_by_page" in gap:
            lines.append("GAP FILLED: %s; page %d holds them" % (head, gap["filled_by_page"] + 1))
        else:
            lines.append("GAP: %s; read again with oldest=%s and pass that page as PAGE@oldest=%s" % (
                head, gap["after_ts"] or "the parent ts", gap["after_ts"] or "TS"))
    rank = {state: i for i, state in enumerate(STATES)}
    for row in sorted(ledger["rows"], key=lambda r: rank[r["state"]]):
        asked = row["asked"][-1] if row["asked"] else {}
        detail = row.get("error") or ""
        if row["state"] == "PENDING":
            age = row["age_s"]
            detail = "age " + (age if isinstance(age, str) else "%ds" % age)
            if row["overdue"] is True:
                detail += " OVERDUE"
            if row.get("may_be_in_gap"):
                detail += " (answer may be in a GAP)"
        elif row["state"] == "PARTIAL":
            detail = "%(present)d/%(expected)d parts, %(closed)d closed" % row["parts"]
        lines.append("%-15s %-28s %s  %s %s" % (row["state"], row["name"][:28],
            row["request_id"], asked.get("ts") or "", detail))
    for orphan in ledger["orphan_results"]:
        lines.append("%-15s %-28s %s  answer with no request in this copy" % (
            orphan["state"], "UNKNOWN", orphan["request_id"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pages", nargs="+",
                        help="saved thread pages, any known shape; PAGE@oldest=TS names a "
                             "follow-up page fetched with oldest=TS")
    parser.add_argument("--now", help="measure ages against this ISO time")
    parser.add_argument("--overdue-after", type=float, default=OVERDUE_AFTER_S)
    parser.add_argument("--text", action="store_true", help="one line per request")
    args = parser.parse_args(argv)
    now = _parse_now(args.now) if args.now else None
    ledger = from_files(args.pages, now, args.overdue_after)
    if args.text:
        print(as_text(ledger))
    else:
        print(json.dumps(ledger, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
