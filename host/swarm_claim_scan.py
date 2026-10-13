#!/usr/bin/env python3
"""Read scoped work declarations from retained Slack responses, without actions.

This is an advisory over supplied observations. It is not the canonical claims
ledger, an ownership decision, a provider client, or a message sender.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "commons.slack_claim_scan/v1"
MAX_INPUT_BYTES = 64 * 1024 * 1024
STAMP = re.compile(r"[0-9]{1,12}\.[0-9]{1,6}\Z")
GITHUB_ISSUE_OPERATION = (
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/"
    r"(?!\.{1,2}#)[A-Za-z0-9_.-]{1,100}#[1-9][0-9]{0,19}")
OPERATION = r"(?:[A-Za-z0-9][A-Za-z0-9_.:/#-]{5,190}|" + GITHUB_ISSUE_OPERATION + r")"
TERMINAL_ID = r"(?P<code>`?)(?P<operation>" + OPERATION + r")(?P=code)"
DECLARATION = re.compile(
    r"^(?:CLAIM|TAKE|RESUME|TAKING)"
    r"(?:[ \t]+BUILD(?:/PUBLISH)?(?=[ \t]*[:·—–]))?"
    r"(?:\s*[:·—–]\s*|\s+)(?P<code>`?)"
    r"(?P<operation>" + OPERATION + r")(?P=code)(?=\s|$|[—–,;])", re.I)
DECLARATION_START = re.compile(r"^(?:CLAIM|TAKE|RESUME|RESUMING|TAKING|CONTINUE|CONTINUING)\b", re.I)
QUALIFIED_DECLARATION = re.compile(
    # Fleet headers qualify the action (QA, DIAGNOSE, INTERNAL QUALIFICATION).
    # Only a bounded alphabetic phrase followed by an explicit separator is
    # syntax; an ordinary prose continuation must not become a declaration.
    r"^(?:CLAIM|TAKE|RESUME|TAKING)[ \t]+"
    r"(?!(?:[A-Za-z]{2,24}[ \t]+){0,2}"
    r"(?:if|when|unless|until|pending|awaiting|proposed|planned)\b)"
    r"[A-Za-z]{2,24}(?:[ \t]+[A-Za-z]{2,24}){0,2}"
    r"[ \t]*[:·—–][ \t]*(?P<code>`?)"
    r"(?P<operation>" + OPERATION + r")(?P=code)(?=\s|$|[—–,;])", re.I)
LABELED_OPERATION = re.compile(
    r"(?:^[ \t]*|(?<=[.!?])[ \t]+)Operation(?:[ \t]+ID)?[ \t]*:[ \t]*`?(" + OPERATION
    + r")`?(?=\s|$|[—–,;])", re.I | re.M)
STATEMENT_HEADER = re.compile(
    # A leading actor label is coverage only, never an inferred claim or release.
    r"^[ \t*`]*(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}[ \t]+)?"
    r"(?:CLAIM|TAKE|RESUME|RESUMING|TAKING|CONTINUE|CONTINUING|"
    r"LANDED|DONE|COMPLETED?|RELEASED?|SHIP(?:PED)?)\b[^\n]*", re.I | re.M)
TERMINAL = re.compile(
    r"^(LANDED|DONE|COMPLETED?|RELEASED?)"
    r"(?:\s*/\s*(?:LANDED|DONE|COMPLETED?|RELEASED?)(?:\s+[—–])?)?"
    r"(?:\s*[:·—–]\s*|\s+)" + TERMINAL_ID + r"(?=\s|$|[—–,;])", re.I)
TERMINAL_AFTER = re.compile(r"^(" + OPERATION + r")\s+(?:is\s+)?(LANDED|DONE|COMPLETED?|RELEASED?)\b", re.I)
SOURCE_TERMINAL = re.compile(
    r"^(DONE)[ \t]+SOURCE[ \t]*/[ \t]*RELEASED?"
    r"(?:[ \t]*[:·—–][ \t]*|[ \t]+)" + TERMINAL_ID + r"(?=\s|$|[—–,;])", re.I)
SHIP_RELEASE_TERMINAL = re.compile(
    r"^(SHIP(?:PED)?)[ \t]*/[ \t]*RELEASED?"
    r"(?:[ \t]*[:·—–][ \t]*|[ \t]+)" + TERMINAL_ID + r"(?=\s|$|[—–,;])", re.I)
TERMINAL_LAND_RELEASE = re.compile(
    r"^TERMINAL[ \t]+LAND[ \t]*/[ \t]*(RELEASED?)"
    r"(?:[ \t]*[:·—–][ \t]*|[ \t]+)" + TERMINAL_ID + r"(?=\s|$|[—–,;])", re.I)
SLASH_TERMINAL = re.compile(
    r"^(LANDED|DONE|COMPLETED?|RELEASED?)[ \t]*/[ \t]*"
    + TERMINAL_ID + r"(?=\s|$|[—–,;])", re.I)
HEADER = re.compile(
    r"^(?:=== THREAD PARENT MESSAGE ===|--- Reply [0-9]+ of [0-9]+ ---|"
    r"=== Message from .+? ===[^\n]*|### Result [0-9]+ of [0-9]+)\s*$", re.M)
MESSAGE_STAMP = re.compile(r"^Message(?: TS|_ts):\s*([0-9]+\.[0-9]+)\s*$", re.M)
SEARCH_CONTEXT = re.compile(r"^Context (before|after):[ \t]*(?:\n|$)", re.M)
CHANNEL = re.compile(r"(?:\(ID:\s*|\()([CGD][A-Z0-9]+)\)")
FILE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./:-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9]{0,9})"
    r"(?=$|[^A-Za-z0-9_/-])")
BARE_FILE = re.compile(
    r"(?<![A-Za-z0-9_./:-])([A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9]{0,9})"
    r"(?=$|[^A-Za-z0-9_/-])")
BRACES = re.compile(r"((?:[A-Za-z0-9_.-]+/)+)\{([^{}\n]+)\}")
SCOPED_PATH = re.compile(
    r"(?<![A-Za-z0-9_./:-])(?P<path>(?:[A-Za-z0-9_.-]+/)*"
    r"[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9]{0,9})::"
    r"(?P<symbols>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
    r"(?:/[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)*)")
ADJACENT_SYMBOL = re.compile(
    r"(?<![A-Za-z0-9_./:-])(?P<path>(?:[A-Za-z0-9_.-]+/)*"
    r"[A-Za-z0-9_.-]+\.(?:py|pyi|js|mjs|cjs|ts|tsx|jsx|rs|go|java|kt|swift|rb|php|c|h|cpp|hpp|sh))"
    r"`?[ \t]+(?P<symbol>`?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(\))?`?)")


GITHUB_WORK_REFERENCE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(issues|pull)/"
    r"([1-9][0-9]*)(?=[/?#\s<>|)\].,;:]|$)", re.I)
GITHUB_ISSUE_SHORTHAND = re.compile(
    r"(?<![A-Za-z0-9_./:-])([A-Za-z0-9][A-Za-z0-9-]{0,38})/"
    r"([A-Za-z0-9_.-]{1,100})[ \t]*#([1-9][0-9]{0,19})"
    r"(?=$|[^A-Za-z0-9_])", re.I)

AVAILABLE_WORK = re.compile(
    r"^(?:available(?:[ \t]+(?:next|implementation|product|work)){0,3}[ \t]+"
    r"(?:scope|follow-on)|next[ \t]+usable[ \t]+work)\b", re.I)
DECLARATION_CONTEXT = re.compile(
    r"\b(?:workspace|cloud[ \t]+(?:context|harness))(?:[ \t]+id)?"
    r"(?:[ \t]+|[ \t]*[:=][ \t]*)`?([0-9a-f]{12,64})`?"
    r"(?=$|[\s.,;:)])", re.I)


class ScanError(ValueError):
    pass


def _load(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ScanError("duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ScanError("input is not an unambiguous UTF-8 JSON response") from exc


def _stamp(value):
    if not isinstance(value, str) or STAMP.fullmatch(value) is None:
        raise ScanError("message timestamp must retain its Slack string value")
    seconds, fraction = value.split(".")
    return str(int(seconds)) + "." + fraction.ljust(6, "0")


def _channel(value):
    if not isinstance(value, str) or re.fullmatch(r"[CGD][A-Z0-9]+", value) is None:
        raise ScanError("message channel is missing; supply --channel-id for a thread export")
    return value


def _workspace(value):
    if not value:
        return None
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ("", "/")
            or not parts.hostname.endswith(".slack.com") or parts.port is not None):
        raise ScanError("--workspace-url must be the HTTPS Slack workspace root")
    return "https://" + parts.hostname


def _message(row, fallback_channel, source):
    if not isinstance(row, dict) or not isinstance(row.get("text"), str):
        raise ScanError("Slack messages must contain text and an exact timestamp")
    channel = row.get("channel", fallback_channel)
    if isinstance(channel, dict):
        channel = channel.get("id")
    stamp = _stamp(row.get("ts"))
    return {"channel_id": _channel(channel), "message_ts": stamp,
            "text": row["text"].strip(), "source": source,
            "permalink": row.get("permalink") if isinstance(row.get("permalink"), str) else None}


def _pagination(page, source, count):
    info = page.get("pagination_info")
    cursor, terminal = None, None
    if isinstance(info, str):
        normalized = info.strip().replace("\\n", "").strip()
        if re.fullmatch(r"(?:There are no more messages (?:in this thread|available)\.?|"
                        r"End of results - No more pages available\.?)", normalized, re.I):
            terminal = True
        else:
            match = re.search(r"\bcursor\s*:?[ \t]*`([^`]+)`", normalized, re.I)
            if match:
                cursor, terminal = match[1], False
    else:
        metadata = page.get("response_metadata", {})
        if isinstance(metadata, dict) and isinstance(metadata.get("next_cursor"), str):
            cursor = metadata["next_cursor"] or None
        if cursor or page.get("has_more") is True:
            terminal = False
        elif page.get("has_more") is False:
            terminal = True
    return {"source": source, "message_count": count, "terminal_page": terminal,
            "next_cursor": cursor, "pagination_known": terminal is not None}


def _search_matched_text(body, source, channel, stamp):
    """Keep native context out of the matched message's declarations."""
    sections = list(SEARCH_CONTEXT.finditer(body))
    if not sections:
        return body, []
    if (len(sections) > 2 or (len(sections) == 2
            and [section[1] for section in sections] != ["before", "after"])):
        raise ScanError(f"{source}: native search context sections repeat or are out of order")
    omitted = []
    for index, section in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(body)
        content = body[section.end():end]
        if not re.match(r"^- (?:From: |\[See result above\] From: )", content):
            raise ScanError(f"{source}: unsupported native search context framing")
        omitted.append({"channel_id": _channel(channel), "message_ts": _stamp(stamp),
                        "kind": section[1], "characters": end - section.start()})
    return body[:sections[0].start()], omitted


def _rendered(page, fallback_channel, source):
    text = page.get("messages", page.get("results"))
    if not isinstance(text, str):
        raise ScanError("rendered Slack response must contain a messages or results string")
    if text.lstrip().startswith("THREAD:"):
        raise ScanError(
            'concise Slack thread responses omit exact message timestamps; '
            'repeat the thread read with response_format="detailed" '
            'and retain the returned JSON response')
    matches = list(HEADER.finditer(text))
    declared = re.search(r"^=== THREAD REPLIES \(([0-9]+) total\) ===\s*$", text, re.M)
    if declared:
        reply_count = sum(heading[0].startswith("--- Reply ") for heading in matches)
        if int(declared[1]) != reply_count:
            raise ScanError(
                f"{source}: rendered Slack thread page declares {declared[1]} replies "
                f"but contains {reply_count}; retain this source response and repeat "
                'the same thread/cursor/time window with a smaller limit and '
                'response_format="detailed"')
    rows, search_contexts = [], []
    prefix = text[:matches[0].start()] if matches else text
    search_declared = re.search(r"^## Messages \(([0-9]+) results\)[ \t]*$", prefix, re.M)
    search_numbers = []
    if search_declared:
        total = int(search_declared[1])
        for heading in matches:
            number = re.fullmatch(r"### Result ([1-9][0-9]*) of ([1-9][0-9]*)", heading[0].strip())
            if (not number or int(number[2]) != total or int(number[1]) > total
                    or (search_numbers and int(number[1]) <= search_numbers[-1])):
                raise ScanError(f"{source}: inconsistent rendered search result numbering")
            search_numbers.append(int(number[1]))
    channel_match = CHANNEL.search(prefix)
    default_channel = channel_match[1] if channel_match else fallback_channel
    for index, heading in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[heading.end():end]
        stamp = MESSAGE_STAMP.search(block)
        if not stamp:
            raise ScanError("a rendered message header is missing its timestamp")
        meta = block[:stamp.start()]
        channel_match = CHANNEL.search(meta)
        channel = channel_match[1] if channel_match else default_channel
        body = block[stamp.end():].lstrip("\n")
        if heading[0].startswith("### Result"):
            marker = re.search(r"^Text:\s*\n?", body, re.M)
            if not marker:
                raise ScanError("rendered search result is missing its Text field")
            link = re.search(r"^Permalink: \[link\]\((https://[^)]+)\)", body[:marker.start()], re.M)
            permalink = link[1] if link else None
            body = body[marker.end():]
            body = re.sub(r"\n---\s*$", "", body)
            body, omitted = _search_matched_text(body, source, channel, stamp[1])
            search_contexts.extend(omitted)
        else:
            permalink = None
            body = re.sub(r"\n=== THREAD REPLIES \([^\n]*\) ===\s*$", "", body)
            body = re.sub(r"\nThread: [0-9]+ replies[^\n]*\s*$", "", body)
        rows.append(_message({"ts": stamp[1], "text": body, "channel": channel,
                              "permalink": permalink}, default_channel, source))
    if not matches and not re.search(r"(?:No results found|No messages|no messages)", text):
        # Some native empty-history responses carry an empty messages field.
        if text.strip():
            raise ScanError("unsupported rendered Slack message layout")
    coverage = _pagination(page, source, len(rows))
    if search_declared:
        declared_count = int(search_declared[1])
        coverage.update({"declared_results": declared_count, "parsed_results": len(rows),
                         "rendered_result_numbers": search_numbers,
                         "unrendered_results": declared_count - len(rows),
                         "search_rendering_complete": len(rows) == declared_count,
                         "search_context_handling": "matched_text_only",
                         "excluded_context_sections": search_contexts,
                         "excluded_context_characters": sum(item["characters"] for item in search_contexts)})
    return rows, coverage


def read_responses(value, *, channel_id=None, source="input"):
    """Accept raw Slack pages or native MCP text/structured response envelopes."""
    messages, pages = [], []
    def visit(node, depth=0):
        if depth > 20:
            raise ScanError("response envelope nesting exceeds 20 levels")
        if isinstance(node, list):
            if not node:
                return False
            found = False
            for child in node:
                found = visit(child, depth + 1) or found
            return found
        if not isinstance(node, dict):
            return False
        if node.get("isError") is True or node.get("ok") is False:
            raise ScanError("source records a failed provider read")
        if isinstance(node.get("messages"), list):
            channel = node.get("channel", channel_id)
            rows = [_message(row, channel, source) for row in node["messages"]]
            messages.extend(rows)
            pages.append(_pagination(node, source, len(rows)))
            return True
        if isinstance(node.get("messages"), str) or isinstance(node.get("results"), str):
            rows, page = _rendered(node, channel_id, source)
            messages.extend(rows)
            pages.append(page)
            return True
        # Structured content takes precedence over its textual mirror.
        if "structuredContent" in node and visit(node["structuredContent"], depth + 1):
            return True
        if "content" in node:
            return visit(node["content"], depth + 1)
        # Native Slack tools also return a bare {"text": "<JSON>"} envelope.
        # Keep this shape exact; authored message objects are not envelopes.
        if ((node.get("type") == "text" or set(node) == {"text"})
                and isinstance(node.get("text"), str)):
            content = node["text"].strip()
            if content.startswith(("{", "[")):
                return visit(_load(content), depth + 1)
        return False
    if not visit(value):
        raise ScanError("no supported Slack response found")
    return messages, pages


def _scopes(text):
    """Retain explicit selectors and adjacent code-shaped symbol observations."""
    text = re.sub(r"https?://[^\s<>]+", "", text)
    scoped = defaultdict(set)
    notations = defaultdict(set)
    for match in SCOPED_PATH.finditer(text):
        path = match["path"].removeprefix("./")
        scoped[path].update(match["symbols"].split("/"))
        notations[path].add("double_colon")
    for match in ADJACENT_SYMBOL.finditer(text):
        candidate = match["symbol"]
        # Ordinary words such as "only", "and" or "metadata" do not identify
        # a method. Retain code spelling rather than inferring it from prose.
        if not ("_" in candidate or "." in candidate or candidate.endswith("()")
                or (candidate.startswith("`") and candidate.endswith("`"))):
            continue
        path = match["path"].removeprefix("./")
        scoped[path].add(candidate.strip("`").removesuffix("()"))
        notations[path].add("adjacent_code_symbol")
    return [{"path": path, "symbols": sorted(symbols),
             "notations": sorted(notations[path]),
             "path_resolution": "relative_path" if "/" in path else "basename_only"}
            for path, symbols in sorted(scoped.items())]


def _paths(text, scopes=None):
    # URL paths describe links, not a declaration's source-file scope.
    text = re.sub(r"https?://[^\s<>]+", "", text)
    expanded = []
    for match in BRACES.finditer(text):
        members = [member.strip(" `") for member in match[2].split(",")]
        if all(re.fullmatch(r"[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9]{0,9}", member) for member in members):
            expanded.extend(match[1] + member for member in members)
    return sorted(set(expanded) | {match[1].removeprefix("./") for match in FILE_PATH.finditer(text)}
                  | {scope["path"] for scope in (_scopes(text) if scopes is None else scopes)})


def _is_operation(operation):
    # Preserve legacy work-order IDs and admit explicit owner/repo#issue IDs.
    return ("-" in operation or ":" in operation
            or re.fullmatch(GITHUB_ISSUE_OPERATION, operation) is not None)


def _statement(text, *, source_release=False):
    first = text.lstrip(" *`\n")
    match = QUALIFIED_DECLARATION.match(first) or DECLARATION.match(first)
    if match:
        operation = match["operation"].rstrip(".:;")
        if _is_operation(operation):
            return "declaration", operation
    if DECLARATION_START.match(first):
        operations = {match[1].rstrip(".:;") for match in LABELED_OPERATION.finditer(first)}
        if len(operations) == 1:
            operation = next(iter(operations))
            if _is_operation(operation):
                return "declaration", operation
    match = TERMINAL.match(first)
    if match:
        operation = match["operation"].rstrip(".:;")
        if _is_operation(operation):
            return match[1].lower(), operation
    match = (SOURCE_TERMINAL.match(first) or SHIP_RELEASE_TERMINAL.match(first)
             or SLASH_TERMINAL.match(first) or TERMINAL_LAND_RELEASE.match(first))
    if match:
        if not source_release:
            return None
        # These observed source-release forms must not turn a proposed or
        # conditional header into a completed operation.
        header = re.split(r"(?<=[.!?])\s+|\n", first, maxsplit=1)[0]
        if re.search(r"\b(?:if|when|unless|until|pending|awaiting|proposed|planned)\b",
                     header, re.I):
            return None
        operation = match["operation"].rstrip(".:;")
        if _is_operation(operation):
            return match[1].lower(), operation
        return None
    match = TERMINAL_AFTER.match(first)
    if match:
        operation = match[1].rstrip(".:;")
        if _is_operation(operation):
            return match[2].lower(), operation
    return None


def _statements(text):
    """Read explicit terminal clauses without attributing them to an addressee."""
    prose, fence = [], None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            continue
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence is None:
            prose.append(line)
    visible = "\n".join(prose)
    visible = re.sub(r'"[^"\n]*"|“[^”\n]*”', "", visible)
    first = _statement(visible, source_release=True)
    statements = [first] if first else []
    # A message may address one operation, then explicitly release another.
    # Only the ID in each terminal clause changes state; mention/order is not
    # an ownership or completion signal. Secondary declarations stay unparsed.
    for clause in re.split(r"(?<=[.!?])\s+|\n", visible):
        statement = _statement(clause)
        if statement is None or statement[0] == "declaration":
            continue
        if re.search(r"\b(?:if|when|unless|until|pending|awaiting)\b", clause, re.I):
            continue
        if statement not in statements:
            statements.append(statement)
    return statements


def _terminal_candidates(operation, operations, channel_id):
    """Use the existing overlap view's dated-suffix convention, without guessing."""
    return sorted(name for name, row in operations.items()
                  if name.startswith(operation + "-")
                  and re.fullmatch(r"-(?:19|20)\d{6}(?:-[A-Za-z0-9_.]+)*", name[len(operation):])
                  and any(ref["channel_id"] == channel_id for ref in row["declarations"]))


def _comparison_text(text):
    """Ignore only the known trailing connector signature for duplicate IDs."""
    return re.sub(r"\n\*Sent using\* <@U[A-Z0-9]+\|ChatGPT>\Z", "", text)


def _work_urls(text):
    """Keep issue/PR identity explicit; a URL never becomes a source-file scope."""
    return sorted({f"https://github.com/{match[1].lower()}/{match[2].lower()}/"
                   f"{match[3].lower()}/{match[4]}"
                   for match in GITHUB_WORK_REFERENCE.finditer(text)})


def _issue_targets(text):
    """Extract explicit GitHub *issue* identities; do not guess from bare #N."""
    targets = {
        f"{match[1].lower()}/{match[2].lower()}#{match[4]}"
        for match in GITHUB_WORK_REFERENCE.finditer(text)
        if match[3].lower() == "issues"
    }
    for match in GITHUB_ISSUE_SHORTHAND.finditer(text):
        targets.add(f"{match[1].lower()}/{match[2].lower()}#{match[3]}")
    return sorted(targets)


def _issue_target_overlaps(messages, operations):
    """Advisory collision signal across distinct TAKE IDs citing one issue."""
    by_message = {(row["channel_id"], row["message_ts"]): row for row in messages}
    by_issue = defaultdict(list)
    for operation_id, operation in sorted(operations.items()):
        if operation["state"] != "declaration_observed":
            continue
        for declaration in operation["declarations"]:
            message = by_message[(declaration["channel_id"], declaration["message_ts"])]
            for issue in _issue_targets(message["text"]):
                by_issue[issue].append({"operation_id": operation_id, **declaration})
    overlaps = []
    for issue, observations in sorted(by_issue.items()):
        operation_ids = sorted({row["operation_id"] for row in observations})
        if len(operation_ids) > 1:
            overlaps.append({
                "issue_target": issue,
                "operation_ids": operation_ids,
                "declaration_observations": observations,
                "status": "possible_same_issue_overlap",
                "basis": "Distinct active TAKE IDs explicitly reference one GitHub issue; "
                         "the text alone cannot prove their source scopes conflict.",
            })
    return overlaps


def _availability_hints(messages, operations):
    """Join availability wording and declaration references, without claiming work."""
    declarations_by_message = defaultdict(list)
    for operation in operations.values():
        for declaration in operation["declarations"]:
            declarations_by_message[(declaration["channel_id"], declaration["message_ts"])].append(operation)
    available, declared = defaultdict(list), defaultdict(list)
    for message in messages:
        reference = {key: message[key] for key in ("channel_id", "message_ts", "permalink", "source")}
        declarations = declarations_by_message.get((message["channel_id"], message["message_ts"]), ())
        if declarations:
            for url in _work_urls(message["text"]):
                for operation in declarations:
                    declared[url].append({"operation_id": operation["operation_id"],
                                          "observed_state": operation["state"], **reference})
            continue
        for paragraph in re.split(r"\n[ \t]*\n", message["text"]):
            if not AVAILABLE_WORK.match(paragraph.strip(" *\n")):
                continue
            for url in _work_urls(paragraph):
                available[url].append({"availability_text": paragraph.strip(), **reference})
    return [{"github_url": url, "status": "availability_has_declaration_reference",
             "availability_observations": available[url],
             "declaration_observations": declared[url]}
            for url in sorted(available.keys() & declared.keys())]


def _repeated_declarations(messages, operations):
    """Expose same-ID declarations without inferring ownership or incompatibility."""
    by_message = {(row["channel_id"], row["message_ts"]): row for row in messages}
    repeated = []
    for operation_id, operation in sorted(operations.items()):
        if len(operation["declarations"]) < 2:
            continue
        contexts, unlabeled = defaultdict(list), []
        for declaration in operation["declarations"]:
            message = by_message[(declaration["channel_id"], declaration["message_ts"])]
            context_ids = sorted({match[1].lower()
                                  for match in DECLARATION_CONTEXT.finditer(message["text"])})
            if not context_ids:
                unlabeled.append(declaration)
            for context_id in context_ids:
                contexts[context_id].append(declaration)
        repeated.append({
            "operation_id": operation_id,
            "observed_state": operation["state"],
            "status": "multiple_declaration_contexts_observed" if len(contexts) > 1
                      else "repeated_declarations_observed",
            "declaration_count": len(operation["declarations"]),
            "distinct_context_count": len(contexts),
            "contexts": [{"context_id": key, "declarations": contexts[key]}
                         for key in sorted(contexts)],
            "unlabeled_declarations": unlabeled,
        })
    return repeated


def _basename_hints(messages, operations, by_path):
    """Retain unresolved filename spellings separately from exact path scopes."""
    by_message = {(row["channel_id"], row["message_ts"]): row for row in messages}
    observations, active = [], defaultdict(list)
    for operation_id, operation in sorted(operations.items()):
        for declaration in operation["declarations"]:
            message = by_message[(declaration["channel_id"], declaration["message_ts"])]
            text = re.sub(r"https?://[^\s<>]+", "", message["text"])
            for basename in sorted({match[1] for match in BARE_FILE.finditer(text)}):
                observation = {"basename": basename, "operation_id": operation_id,
                    "observed_state": operation["state"], "path_resolution": "basename_only",
                    **declaration}
                observations.append(observation)
                if operation["state"] == "declaration_observed":
                    active[basename].append(observation)

    paths_by_basename = defaultdict(list)
    for path, operation_ids in sorted(by_path.items()):
        paths_by_basename[path.rsplit("/", 1)[-1]].append({
            "path": path, "operation_ids": sorted(operation_ids),
            "declaration_links": sorted({declaration["permalink"] for op in operation_ids
                for declaration in operations[op]["declarations"] if declaration["permalink"]}),
        })
    hints = []
    for basename, declarations in sorted(active.items()):
        paths = paths_by_basename[basename]
        operation_ids = {row["operation_id"] for row in declarations}
        operation_ids.update(op for row in paths for op in row["operation_ids"])
        if len(operation_ids) > 1:
            hints.append({"basename": basename, "operation_ids": sorted(operation_ids),
                "basename_observations": declarations, "observed_path_groups": paths,
                "status": "possible_basename_reference_overlap", "path_resolution": "unresolved",
                "basis": "Same filename spelling only; directory, repository identity and ownership are not established."})
    return observations, hints


def scan(messages, pages, *, workspace_url=None):
    workspace = _workspace(workspace_url)
    identities = defaultdict(dict)
    for message in messages:
        digest = hashlib.sha256(_comparison_text(message["text"]).encode("utf-8")).hexdigest()
        identities[(message["channel_id"], message["message_ts"])][digest] = message
    ambiguous, ordered = [], []
    for (channel, stamp), versions in identities.items():
        if len(versions) != 1:
            ambiguous.append({"channel_id": channel, "message_ts": stamp,
                              "observed_versions": len(versions)})
            continue
        message = dict(next(iter(versions.values())))
        if not message["permalink"] and workspace:
            message["permalink"] = f"{workspace}/archives/{channel}/p{stamp.replace('.', '')}"
        ordered.append(message)
    ordered.sort(key=lambda row: (int(row["message_ts"].split(".")[0]), row["message_ts"].split(".")[1], row["channel_id"]))
    operations = {}
    terminals, unparsed = [], []
    for message in ordered:
        statements = _statements(message["text"])
        if not statements:
            for header in STATEMENT_HEADER.finditer(message["text"]):
                unparsed.append({"channel_id": message["channel_id"], "message_ts": message["message_ts"],
                                 "permalink": message["permalink"], "statement_header": header[0].strip()})
            continue
        reference = {key: message[key] for key in ("channel_id", "message_ts", "permalink", "source")}
        for kind, operation in statements:
            if kind == "declaration":
                row = operations.setdefault(operation, {"operation_id": operation,
                    "observed_paths": [], "declarations": [], "terminal_observations": [],
                    "observed_scopes": [],
                    "state": "declaration_observed"})
                scopes = _scopes(message["text"])
                row["observed_paths"] = sorted(set(row["observed_paths"]) | set(_paths(message["text"], scopes)))
                for scope in scopes:
                    row["observed_scopes"].append({**scope, **reference})
                row["declarations"].append(reference)
                row["state"] = "declaration_observed"
            else:
                terminal = {"operation_id": operation, "kind": kind, **reference}
                target = operation
                if operation not in operations:
                    candidates = _terminal_candidates(operation, operations, message["channel_id"])
                    if candidates:
                        terminal["alias_candidates"] = candidates
                    if len(candidates) == 1:
                        target = candidates[0]
                        terminal["resolved_operation_id"] = target
                        terminal["alias_resolution"] = "unique_prior_dated_operation_same_channel"
                terminals.append(terminal)
                if target in operations:
                    operations[target]["terminal_observations"].append(terminal)
                    operations[target]["state"] = "explicit_terminal_observed"
    by_path = defaultdict(list)
    for operation, row in operations.items():
        if row["state"] == "declaration_observed":
            for path in row["observed_paths"]:
                by_path[path].append(operation)
    overlaps = [{"path": path, "operation_ids": sorted(ops),
                 "declaration_links": sorted({declaration["permalink"] for op in ops
                    for declaration in operations[op]["declarations"] if declaration["permalink"]}),
                 "status": "possible_file_overlap"}
                for path, ops in sorted(by_path.items()) if len(ops) > 1]
    # File co-occurrence alone cannot distinguish work on unrelated methods.
    # Keep the original file observations, and expose observed symbols separately.
    scoped_overlaps, scoped_files = [], []
    for path, ops in sorted(by_path.items()):
        if len(ops) < 2:
            continue
        by_symbol, symbols_by_operation = defaultdict(set), {}
        for operation in sorted(ops):
            symbols = {symbol for scope in operations[operation]["observed_scopes"]
                       if scope["path"] == path for symbol in scope["symbols"]}
            symbols_by_operation[operation] = sorted(symbols)
            for symbol in symbols:
                by_symbol[symbol].add(operation)
        for symbol, symbol_ops in sorted(by_symbol.items()):
            if len(symbol_ops) > 1:
                scoped_overlaps.append({"path": path, "symbol": symbol,
                    "operation_ids": sorted(symbol_ops),
                    "declaration_links": sorted({scope["permalink"] for op in symbol_ops
                        for scope in operations[op]["observed_scopes"]
                        if scope["path"] == path and symbol in scope["symbols"] and scope["permalink"]}),
                    "status": "possible_same_symbol_overlap",
                    "path_resolution": "relative_path" if "/" in path else "basename_only"})
        if any(symbols_by_operation.values()):
            scoped_files.append({"path": path, "symbols_by_operation": symbols_by_operation,
                "unscoped_operation_ids": sorted(op for op, symbols in symbols_by_operation.items() if not symbols),
                "shared_symbols": sorted(symbol for symbol, symbol_ops in by_symbol.items() if len(symbol_ops) > 1),
                "path_resolution": "relative_path" if "/" in path else "basename_only"})
    availability_hints = _availability_hints(ordered, operations)
    repeated_declarations = _repeated_declarations(ordered, operations)
    basename_observations, basename_hints = _basename_hints(ordered, operations, by_path)
    issue_target_overlaps = _issue_target_overlaps(ordered, operations)
    return {"schema": SCHEMA, "advisory_only": True,
        "scope": "Supplied Slack observations only. Declarations do not establish ownership; shared files can contain compatible work. Refresh the linked sources and existing ledger before acting.",
        "counts": {"messages_supplied": len(messages), "distinct_message_ids": len(identities),
                   "interpreted_message_ids": len(ordered), "operations": len(operations),
                   "declarations_without_exact_paths": sum(not row["observed_paths"] for row in operations.values()),
                   "possible_overlap_paths": len(overlaps), "possible_symbol_overlaps": len(scoped_overlaps),
                   "unparsed_statement_headers": len(unparsed),
                   "availability_hints": len(availability_hints),
                   "repeated_operation_declarations": len(repeated_declarations),
                   "basename_observations": len(basename_observations),
                   "possible_basename_overlaps": len(basename_hints),
                   "possible_issue_target_overlaps": len(issue_target_overlaps)},
        "coverage": {"provider_history_complete": False,
                     "basis": "Caller-supplied pages; terminal pages alone do not prove the history or all claims were supplied.",
                     "pages": pages, "pages_with_continuation": sum(page["terminal_page"] is False for page in pages),
                     "pages_with_unknown_pagination": sum(page["terminal_page"] is None for page in pages),
                     "ambiguous_message_versions": sorted(ambiguous, key=lambda row: (row["channel_id"], row["message_ts"])),
                     "unparsed_statement_headers": unparsed},
        "operations": [operations[key] for key in sorted(operations)],
        "terminal_observations": terminals,
        "possible_overlaps": overlaps,
        "possible_symbol_overlaps": scoped_overlaps,
        "shared_file_scopes": scoped_files,
        "availability_hints": availability_hints,
        "repeated_operation_declarations": repeated_declarations,
        "basename_observations": basename_observations,
        "possible_basename_overlaps": basename_hints,
        "possible_issue_target_overlaps": issue_target_overlaps,
        "unmatched_terminal_observations": [row for row in terminals
            if row.get("resolved_operation_id", row["operation_id"]) not in operations]}


def _read_bounded(handle):
    with io.BytesIO() as buffer:
        remaining = MAX_INPUT_BYTES + 1
        while remaining:
            chunk = handle.read(min(64 * 1024, remaining))
            if not chunk:
                break
            buffer.write(chunk)
            remaining -= len(chunk)
        return buffer.getvalue()


def _select_report(report, *, operation_ids=(), paths=()):
    requested_operations, requested_paths = set(operation_ids), set(paths)
    if not requested_operations and not requested_paths:
        return report
    matching = {row["operation_id"] for row in report["operations"]
                if (not requested_operations or row["operation_id"] in requested_operations)
                and (not requested_paths or requested_paths.intersection(row["observed_paths"]))}

    def relevant_group(row, operations):
        return (not requested_paths or row["path"] in requested_paths) and bool(matching.intersection(operations))

    overlaps = [row for row in report["possible_overlaps"]
                if relevant_group(row, row["operation_ids"])]
    symbol_overlaps = [row for row in report["possible_symbol_overlaps"]
                       if relevant_group(row, row["operation_ids"])]
    shared = [row for row in report["shared_file_scopes"]
              if relevant_group(row, row["symbols_by_operation"])]
    included = set(matching)
    for row in overlaps + symbol_overlaps:
        included.update(row["operation_ids"])
    for row in shared:
        included.update(row["symbols_by_operation"])

    def relevant_terminal(row):
        return (row.get("resolved_operation_id", row["operation_id"]) in included
                or (not requested_paths and row["operation_id"] in requested_operations))

    selected = dict(report)
    selected.update({
        "operations": [row for row in report["operations"] if row["operation_id"] in included],
        "repeated_operation_declarations": [row for row in report["repeated_operation_declarations"]
                                             if row["operation_id"] in included],
        "terminal_observations": [row for row in report["terminal_observations"] if relevant_terminal(row)],
        "possible_overlaps": overlaps,
        "possible_symbol_overlaps": symbol_overlaps,
        "shared_file_scopes": shared,
        "unmatched_terminal_observations": [row for row in report["unmatched_terminal_observations"]
                                            if relevant_terminal(row)],
    })
    selected["selection"] = {
        "operation_ids": sorted(requested_operations),
        "paths": sorted(requested_paths),
        "match_mode": "Exact, case-sensitive; any value within each selector, both selectors when combined.",
        "matching_operation_ids": sorted(matching),
        "related_operation_ids": sorted(included - matching),
        "returned_counts": {key: len(selected[key]) for key in (
            "operations", "terminal_observations", "possible_overlaps", "possible_symbol_overlaps",
            "shared_file_scopes", "unmatched_terminal_observations", "repeated_operation_declarations")},
        "global_evidence_retained": ["counts", "coverage", "inputs", "availability_hints",
                                     "basename_observations", "possible_basename_overlaps"],
        "basis": "Selected observations and their possible-overlap peers; absent matches do not establish available work.",
    }
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Retained Slack JSON response paths; - reads stdin")
    parser.add_argument("--channel-id", help="Channel ID omitted by a native thread response")
    parser.add_argument("--workspace-url", help="Workspace root used to construct missing message links")
    parser.add_argument("--operation", action="append", default=[], metavar="OPERATION_ID",
                        help="Select an exact observed operation ID; repeat to select any listed ID")
    parser.add_argument("--path", action="append", default=[], metavar="OBSERVED_PATH",
                        help="Select an exact observed source path; repeat to select any listed path")
    args = parser.parse_args(argv)
    try:
        if args.inputs.count("-") > 1:
            raise ScanError("stdin can be read only once")
        if args.channel_id is not None:
            _channel(args.channel_id)
        _workspace(args.workspace_url)
        messages, pages, inputs = [], [], []
        for name in args.inputs:
            if name == "-":
                raw = _read_bounded(sys.stdin.buffer)
            else:
                with Path(name).open("rb") as handle:
                    raw = _read_bounded(handle)
            if len(raw) > MAX_INPUT_BYTES:
                raise ScanError("input exceeds the 64 MiB per-response limit")
            rows, observed = read_responses(_load(raw), channel_id=args.channel_id, source=name)
            messages.extend(rows)
            pages.extend(observed)
            inputs.append({"source": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        report = scan(messages, pages, workspace_url=args.workspace_url)
        report["inputs"] = inputs
        report = _select_report(report, operation_ids=args.operation, paths=args.path)
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        return 0
    except (ScanError, OSError, UnicodeError, RecursionError, ValueError) as exc:
        print("swarm-claim-scan: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

