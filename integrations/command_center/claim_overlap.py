"""Advisory operation/path overlap view over saved Slack observations.

No provider calls or claim mutations are made.  ``build_claim_overlap`` accepts
decoded detailed MCP responses, Slack message arrays, or dictionaries containing
``messages``.  The CLI reads those JSON snapshots (or detailed rendered text).
Source timestamps are retained; operation dates and worker liveness are never
inferred.  Output can contain private source excerpts and belongs with its input.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit


SCHEMA = "commons-claim-overlap/v1"
_OP = r"[A-Za-z0-9][A-Za-z0-9_.]*(?:[-:][A-Za-z0-9_.]+)+"
# Slack receipts use "TAKE · OP" and "TAKE BUILD/SHIP · OP".
# A bounded role needs a bullet; arbitrary prose never becomes a claim.
_CLAIM_BULLET_PREFIX = r"(?:[A-Za-z]+(?:\s*[/ -]\s*[A-Za-z]+){0,2}\s*)?[·•]\s*"
_DECLARATION = re.compile(
    rf"^\s*(?:CLAIM|TAKE|Taking|I claim|I(?: am|'m|’m) taking)\s+"
    rf"(?:{_CLAIM_BULLET_PREFIX})?({_OP})(?=\s|[.,:;—·•]|$)",
    re.IGNORECASE,
)
_EXT = r"(?:py|mjs|cjs|js|jsx|ts|tsx|kt|java|md|json|html|css|yaml|yml|toml|sh|ps1|rs|go|cs|cpp|c|h|txt|sql|ipynb|vue|svelte|proto)"
_PATH = re.compile(
    rf"(?<![\w/:])(?:/?[\w.@+()-]+/)*[\w.@+()-]+\.{_EXT}\b"
    r"(?:::[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(\))?)?"
)
_TS = re.compile(r"\d+\.\d+\Z")
_SCOPE = re.compile(r"^(?:exact\s+)?(?:scope|owned(?:\s+paths?)?)\s*(?::|is\b|[—-])\s*", re.I)
_OWN = re.compile(r"^I\s+(?:own|retain only|am keeping|will own)\s+", re.I)
_URL = re.compile(r"https?://[^\s<>]+")
# An explicitly named sponsored issue is an independent ownership identity.
_ISSUE_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)"
    r"(?=$|[^A-Za-z0-9/])", re.I,
)
_ISSUE_SHORT = re.compile(
    r"(?<![A-Za-z0-9_./])([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\s*#([1-9][0-9]*)\b"
)
_REFERENCE_START = re.compile(r"^(?:For\b|Please\b|Existing\b|Other\b|No\b|Your\b|The (?:later|earlier)\b|>)", re.I)


class SnapshotError(ValueError):
    """Unreadable, malformed, or unsupported source input."""


def _sentences(text: str) -> list[str]:
    # A dot inside a path/member is not a sentence boundary.
    return [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()]


def _clean(text: str) -> str:
    return text.replace("**", "").replace(chr(96), "").strip()


def _channel(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("id")
    return value if isinstance(value, str) and re.fullmatch(r"[CDG][A-Z0-9]+", value) else None


def _repository_key(repository: str | None) -> str | None:
    # GitHub repository identity ignores case; retained labels and paths do not.
    return repository.casefold() if repository is not None else None


def _permalink_ids(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parsed = urlsplit(value)
    match = re.fullmatch(r"/archives/([CDG][A-Z0-9]+)/p(\d+)", parsed.path)
    if not match or parsed.scheme not in {"http", "https"}:
        return {}
    # Do not reconstruct a timestamp from the URL: retain only its exact channel.
    return {"channel_id": match[1], "workspace_url": f"{parsed.scheme}://{parsed.netloc}"}


def _message(raw: dict[str, Any], context: dict[str, Any], position: int) -> dict[str, Any]:
    body = raw.get("text", raw.get("body", raw.get("message")))
    if not isinstance(body, str):
        raise SnapshotError(f"{context['snapshot']}: message {position} has no string text/body")
    url = raw.get("permalink", raw.get("url"))
    url = url if isinstance(url, str) else None
    ids = _permalink_ids(url)
    channel = _channel(raw.get("channel_id", raw.get("channel"))) or ids.get("channel_id") or context.get("channel_id")
    workspace = raw.get("workspace_url", raw.get("team_url")) or ids.get("workspace_url") or context.get("workspace_url")
    ts = raw.get("ts", raw.get("message_ts"))
    ts = ts if isinstance(ts, str) else None
    reference_kind = "supplied_permalink" if url else "snapshot_location"
    if not url and workspace and channel and ts and _TS.fullmatch(ts):
        url = f"{workspace.rstrip('/')}/archives/{channel}/p{ts.replace('.', '')}"
        reference_kind = "source_ids_with_supplied_workspace"
    source = {
        "snapshot": context["snapshot"], "position": position,
        "channel_id": channel, "message_ts": ts,
        "source_time": raw.get("time", raw.get("timestamp")),
        "thread_ts": raw.get("thread_ts", context.get("thread_ts")),
        "permalink": url, "reference_kind": reference_kind,
    }
    repository = raw.get("repository", raw.get("repo_full_name", context.get("repository")))
    if isinstance(repository, dict):
        repository = repository.get("full_name")
    if repository is not None and not isinstance(repository, str):
        raise SnapshotError(f"{context['snapshot']}: repository context must be a name or full_name object")
    return {
        "text": body, "source": source, "workspace_url": workspace,
        "repository": repository,
    }


def _rendered(text: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    # Detailed thread/history and search renderings expose the source TS.  Concise
    # renderings usually omit it and must not silently become an empty snapshot.
    marker = re.compile(r"^\s*(?:Message TS|Message_ts):\s*(\S+)\s*$", re.M)
    positions = list(marker.finditer(text))
    if not positions:
        empty = text.strip()
        if not empty or re.fullmatch(r"(?:There are )?(?:no messages (?:found|available)|no more messages(?: in this (?:thread|channel))?)[.!\s]*", empty, re.I):
            return []
        if empty.startswith("# Search Results") and re.search(r"^## Messages \(0 results\)", empty, re.M):
            return []
        if re.fullmatch(r"# Search Results[^\n]*\n\s*No results found\.\s*", empty):
            return []
        raise SnapshotError(f"{context['snapshot']}: unsupported rendering; use a detailed Slack response or structured message array")
    records: list[dict[str, Any]] = []
    parent_ts = positions[0][1] if "THREAD PARENT MESSAGE" in text else context.get("thread_ts")
    for index, match in enumerate(positions):
        before = text[positions[index - 1].end() if index else 0:match.start()]
        after = text[match.end():positions[index + 1].start() if index + 1 < len(positions) else len(text)]
        # The next message's headers follow one of these structural boundaries.
        after = re.split(r"\n(?:=== THREAD REPLIES|--- Reply \d+|---\s*\n|### Result \d+|From:)", after, maxsplit=1)[0]
        url_match = re.search(r"^Permalink:\s*(?:\[link\]\()?([^\s)]+)", after, re.M)
        url = url_match[1] if url_match else None
        after = re.sub(r"^Permalink:.*\n?", "", after, flags=re.M)
        after = re.sub(r"^Reply count:.*\n?", "", after, flags=re.M)
        after = re.sub(r"^Text:\s*\n?", "", after.lstrip(), count=1)
        times = re.findall(r"^Time:\s*(.+)$", before, re.M)
        channels = re.findall(r"^Channel:.*?\(ID:\s*([CDG][A-Z0-9]+)\)", before, re.M)
        raw = {"text": after.strip(), "ts": match[1], "time": times[-1] if times else None,
               "channel_id": channels[-1] if channels else None, "permalink": url, "thread_ts": parent_ts}
        records.append(_message(raw, context, index + 1))
    return records


def _unwrap(value: Any, context: dict[str, Any], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return _rendered(value, context)
        if decoded == value:
            raise SnapshotError(f"{context['snapshot']}: unsupported nested string")
        return _unwrap(decoded, context, coverage)
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise SnapshotError(f"{context['snapshot']}: messages must be objects")
        return [_message(item, context, index + 1) for index, item in enumerate(value)]
    if not isinstance(value, dict):
        raise SnapshotError(f"{context['snapshot']}: expected a Slack response or message array")
    if value.get("isError") is True or value.get("ok") is False or value.get("error"):
        raise SnapshotError(f"{context['snapshot']}: saved provider response reports an error")
    context = dict(context)
    for key in ("workspace_url", "team_url", "repository", "thread_ts"):
        if value.get(key):
            context["workspace_url" if key == "team_url" else key] = value[key]
    context["channel_id"] = _channel(value.get("channel_id", value.get("channel"))) or context.get("channel_id")
    for key in ("pagination_info", "has_more", "response_metadata", "coverage"):
        if key in value:
            coverage[key] = value[key]
    for key in ("messages", "results"):
        if key in value:
            return _unwrap(value[key], context, coverage)
    structured = value.get("structuredContent")
    if isinstance(structured, dict) and any(key in structured for key in ("messages", "results", "data")):
        return _unwrap(structured, context, coverage)
    if "content" in value:
        content = value["content"]
        if not isinstance(content, list):
            raise SnapshotError(f"{context['snapshot']}: MCP content must be an array")
        items = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not items:
            raise SnapshotError(f"{context['snapshot']}: no readable text in MCP response")
        result: list[dict[str, Any]] = []
        for item in items:
            result.extend(_unwrap(item, context, coverage))
        return result
    if "data" in value:
        return _unwrap(value["data"], context, coverage)
    if any(key in value for key in ("text", "body", "message")):
        return [_message(value, context, 1)]
    raise SnapshotError(f"{context['snapshot']}: unsupported snapshot object")


def _symbols(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"\b[A-Z]\w*\.[A-Za-z_]\w*(?:/[A-Za-z_]\w*)*|(?<![\w.])[A-Za-z_]\w*_[A-Za-z0-9_]*\b|\b[A-Za-z_]\w*\(\)", text):
        name = match[0].removesuffix("()")
        if "/" in name and "." in name:
            first, *others = name.split("/")
            values.extend([first, *(first.rsplit(".", 1)[0] + "." + other for other in others)])
        else:
            values.append(name)
    return sorted(set(values))


def _scope_paths(clause: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    # Mask URLs without shifting offsets.  A link to another source is not an
    # owned path, and unqualified filenames retain their qualification limits.
    masked = _URL.sub(lambda m: " " * len(m[0]), clause)
    matches = list(_PATH.finditer(masked))
    result: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        literal = match[0]
        path, _, member = literal.partition("::")
        tail = masked[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(masked)]
        symbols = sorted(set(([member.removesuffix("()")] if member else []) + _symbols(tail)))
        result.append({
            "path": path, "literal": literal,
            "qualification": "qualified" if "/" in path else "unqualified_filename",
            "symbols": symbols,
            "explicit_symbols_only": bool(symbols and re.search(r"\bonly\b", tail, re.I)),
            "scope_text": clause, "source": source,
        })
    return result


def _scope_clauses(body: str, remainder: str | None = None) -> list[str]:
    clauses: list[str] = []
    if remainder:
        header = _sentences(remainder.lstrip(" .:—–-·•"))
        if header and not _REFERENCE_START.match(header[0]):
            clauses.append(header[0])
    for sentence in _sentences(body):
        if _REFERENCE_START.match(sentence):
            continue
        if _SCOPE.match(sentence) or _OWN.match(sentence):
            clauses.append(sentence)
    return list(dict.fromkeys(clauses))


def _issue_targets(body: str) -> list[dict[str, Any]]:
    """Extract exact sponsor issue names from the claim's opening paragraph.

    Bare issue numbers could be PRs; later reference paragraphs may name
    competing work. Neither should silently become an ownership declaration.
    """
    opening = re.split(r"\n\s*\n", body, maxsplit=1)[0][:1800]
    targets: dict[tuple[str, int], dict[str, Any]] = {}
    for pattern in (_ISSUE_URL, _ISSUE_SHORT):
        for match in pattern.finditer(opening):
            repo = f"{match[1]}/{match[2]}".casefold()
            issue = int(match[3])
            targets.setdefault((repo, issue), {
                "repository": repo,
                "issue": issue,
                "issue_url": f"https://github.com/{repo}/issues/{issue}",
                "literal": match[0],
            })
    return list(targets.values())


def _event(kind: str, operation: str, body: str, record: dict[str, Any], clauses: list[str] | None = None) -> dict[str, Any]:
    return {"kind": kind, "operation_id": operation.rstrip("."), "text": body,
            "source": record["source"], "repository": record["repository"],
            "scope_clauses": clauses or []}


def _events(record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    body = _clean(record["text"])
    sentences = _sentences(body)
    events: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    terminal_prefix = re.compile(
        rf"^(?:(?:DONE|LANDED|RELEASED?|Completed|SHIPPED)"
        rf"(?:\s*/\s*(?:DONE|LANDED|RELEASED?|COMPLETE(?:D)?))?"
        rf"|COLLISION\s*/\s*RELEASED?)\s+"
        rf"(?:{_CLAIM_BULLET_PREFIX})?({_OP})(?=\s|[.,:;—·•]|$)", re.I)
    terminal_suffix = re.compile(rf"^({_OP})\s+(?:[—–-]\s+)?(?:(?:is|has been)\s+)?(?:complete(?:d)?|done|landed|released)\b", re.I)
    terminal_own = re.compile(rf"^I\s+(?:have\s+)?(?:completed|released|landed)\s+({_OP})(?=\s|[.,:;—]|$)", re.I)
    for sentence in sentences:
        match = terminal_prefix.match(sentence) or terminal_suffix.match(sentence) or terminal_own.match(sentence)
        if match:
            events.append(_event("terminal", match[1], sentence, record))
    first = sentences[0] if sentences else ""
    declaration = _DECLARATION.match(first)
    if declaration:
        remainder = body[declaration.end():]
        events.append(_event("claim", declaration[1], body, record, _scope_clauses(body, remainder)))
    elif re.match(r"^Taking (?:two|three|multiple|the following)\b", first, re.I):
        bullets = re.split(r"(?m)^\s*[•*-]\s+", body)[1:]
        for bullet in bullets:
            match = re.match(rf"({_OP})(?=\s|:|[.,;—]|$)", bullet)
            if match:
                events.append(_event("claim", match[1], bullet, record, _scope_clauses(bullet, bullet[match.end():])))
            else:
                unresolved.append({"reason": "unrecognized declaration in a multi-operation claim", "text": bullet, "source": record["source"]})
    elif sentences:
        operation = re.match(rf"^({_OP})(?=\s|[.,:;—]|$)", first)
        if operation and re.search(r"\b(?:composition|scope|I own|I retain)\b", body, re.I):
            clauses = _scope_clauses(body)
            if clauses:
                events.append(_event("scope_refinement", operation[1], body, record, clauses))
    candidate = re.search(r"(?:^|\n)\s*(?:CLAIM\b|TAKE\b|Taking\b|Continuing\b|RESUME\b|I\s+(?:claim|own|have)\b|My\s+" + _OP + r")", body, re.I)
    candidate = candidate or re.search(r"\b(?:I have\s+" + _OP + r"\s+scoped|My\s+" + _OP + r"\s+(?:adds|owns|covers))\b", body, re.I)
    if not events and candidate:
        unresolved.append({"reason": "ownership language is not an explicit operation-bound declaration", "text": body, "source": record["source"]})
    elif not events and re.search(r"\b(?:landed|released|completed|merged)\b", body, re.I):
        unresolved.append({"reason": "completion/reference is not bound to an exact operation declaration", "text": body, "source": record["source"]})
    return events, unresolved


def _ts(event: dict[str, Any]) -> Decimal | None:
    ts = event["source"].get("message_ts")
    return Decimal(ts) if isinstance(ts, str) and _TS.fullmatch(ts) else None


def _resolve_aliases(events: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> None:
    declarations = [event for event in events if event["kind"] == "claim"]
    for event in events:
        if event["kind"] == "claim":
            continue
        operation = event["operation_id"]
        eligible = [claim for claim in declarations
                    if _repository_key(claim["repository"]) == _repository_key(event["repository"])
                    and _ts(claim) is not None and _ts(event) is not None
                    and _ts(claim) <= _ts(event)]
        if any(claim["operation_id"] == operation for claim in eligible):
            continue
        candidates = [claim for claim in eligible
                      if claim["operation_id"].startswith(operation + "-")
                      and re.fullmatch(r"-(?:19|20)\d{6}(?:-[A-Za-z0-9_.]+)*", claim["operation_id"][len(operation):])]
        names = {claim["operation_id"] for claim in candidates}
        if len(names) == 1:
            event["operation_alias"] = operation
            event["operation_id"] = next(iter(names))
            event["alias_resolution"] = {"rule": "unique previously declared dated operation in the same repository context",
                                         "declaration_sources": [claim["source"] for claim in candidates]}
        elif len(names) > 1:
            unresolved.append({"reason": "short operation name matches multiple earlier declarations",
                               "operation_alias": operation, "candidates": sorted(names), "source": event["source"], "text": event["text"]})


def _reduce(operation: str, events: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> dict[str, Any]:
    timed = all(_ts(event) is not None for event in events)
    if timed:
        events.sort(key=lambda event: _ts(event))
    by_time: dict[str, set[str]] = defaultdict(set)
    for event in events:
        by_time[str(event["source"].get("message_ts"))].add(event["kind"])
    uncertain_order = (not timed and len({event["kind"] for event in events}) > 1) or any(len(kinds) > 1 for kinds in by_time.values())
    scopes: list[dict[str, Any]] = []
    issue_targets: dict[tuple[str, int], dict[str, Any]] = {}
    state = "unknown_active"
    evidence: list[dict[str, Any]] = []
    repositories = sorted({str(event["repository"]) for event in events if event.get("repository")})
    for event in events:
        if event["kind"] == "claim":
            for target in _issue_targets(event["text"]):
                issue_targets.setdefault((target["repository"], target["issue"]), {
                    **target, "source": event["source"],
                })
        evidence.append({"kind": event["kind"], "source": event["source"], "text": event["text"],
                         "scope_clauses": event["scope_clauses"], "operation_alias": event.get("operation_alias"),
                         "alias_resolution": event.get("alias_resolution")})
        if event["kind"] == "terminal":
            state = "terminal_observed"
            continue
        extracted = [path for clause in event["scope_clauses"] for path in _scope_paths(clause, event["source"])]
        if event["kind"] == "scope_refinement" and not extracted:
            unique_paths = {scope["path"] for scope in scopes}
            if len(unique_paths) == 1:
                previous = next(scope for scope in scopes if scope["path"] in unique_paths)
                for clause in event["scope_clauses"]:
                    symbols = _symbols(clause)
                    if symbols:
                        extracted.append({**previous, "symbols": symbols,
                            "explicit_symbols_only": bool(re.search(r"\bonly\b", clause, re.I)),
                            "scope_text": clause, "source": event["source"],
                            "path_origin": "prior declaration of this exact operation",
                            "path_source": previous.get("path_source", previous["source"])})
        if not extracted:
            unresolved.append({"operation_id": operation, "reason": "no explicit file scope could be derived", "text": event["text"], "source": event["source"]})
        if any(re.search(r"\b(?:its|existing|the)\s+(?:README|guide|documentation)\b", clause, re.I) for clause in event["scope_clauses"]):
            unresolved.append({"operation_id": operation, "reason": "relative documentation scope has no exact path", "text": "\n".join(event["scope_clauses"]), "source": event["source"]})
        if event["kind"] == "scope_refinement" and extracted and not uncertain_order:
            scopes = extracted
        else:
            scopes.extend(extracted)
        state = "unknown_active"
    if uncertain_order:
        state = "lifecycle_unresolved"
        unresolved.append({"operation_id": operation, "reason": "source times do not establish declaration/refinement/completion order", "sources": [event["source"] for event in events]})
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for scope in scopes:
        unique[(scope["path"], tuple(scope["symbols"]), scope["scope_text"])] = scope
    repository = repositories[0] if len({_repository_key(repo) for repo in repositories}) == 1 else None
    return {"operation_id": operation, "claim_key": [repository, operation], "state": state, "repositories": repositories,
            "scopes": list(unique.values()), "issue_targets": list(issue_targets.values()),
            "evidence": evidence,
            "claim_urls": list(dict.fromkeys(event["source"]["permalink"] for event in events if event["kind"] == "claim" and event["source"].get("permalink")))}


def _path_relation(left: str, right: str) -> str | None:
    if left == right:
        return "same_explicit_path" if "/" in left else "same_unqualified_filename"
    if "/" not in left and right.rsplit("/", 1)[-1] == left:
        return "unqualified_filename_candidate"
    if "/" not in right and left.rsplit("/", 1)[-1] == right:
        return "unqualified_filename_candidate"
    return None


def _overlaps(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [claim for claim in claims if claim["state"] != "terminal_observed"]
    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(active):
        for right in active[index + 1:]:
            lr, rr = left["repositories"], right["repositories"]
            shared_explicit_repository = bool(
                {_repository_key(repo) for repo in lr}
                & {_repository_key(repo) for repo in rr}
            )
            issue_matches = []
            for li in left["issue_targets"]:
                for ri in right["issue_targets"]:
                    if (li["repository"], li["issue"]) == (ri["repository"], ri["issue"]):
                        issue_matches.append({
                            "issue_url": li["issue_url"],
                            "relation": "same_explicit_issue_target",
                            "left_source": li["source"],
                            "right_source": ri["source"],
                        })
            # Coordination repository context can differ from the sponsor.
            if lr and rr and not shared_explicit_repository and not issue_matches:
                continue
            matches: list[dict[str, Any]] = []
            for ls in left["scopes"]:
                for rs in right["scopes"]:
                    relation = _path_relation(ls["path"], rs["path"])
                    if not relation:
                        continue
                    lsymbols, rsymbols = set(ls["symbols"]), set(rs["symbols"])
                    member_relation = "scope_needs_reconciliation"
                    if lsymbols and rsymbols:
                        if lsymbols & rsymbols:
                            member_relation = "shared_explicit_symbol"
                        elif ls["explicit_symbols_only"] and rs["explicit_symbols_only"]:
                            member_relation = "different_explicit_symbols"
                    matches.append({"left_scope": ls, "right_scope": rs,
                                    "path_relation": relation, "symbol_relation": member_relation})
            if issue_matches or matches:
                pairs.append({
                    "left_operation_id": left["operation_id"],
                    "right_operation_id": right["operation_id"],
                    "left_claim_key": left["claim_key"],
                    "right_claim_key": right["claim_key"],
                    "repository_relation": (
                        "matching_explicit_repository" if shared_explicit_repository
                        else "disjoint_explicit_repositories" if lr and rr
                        else "not_established"
                    ),
                    "matches": matches, "issue_matches": issue_matches,
                    "interpretation": "Advisory overlap of explicit issue target or source scope; "
                                      "source text does not establish semantic conflict, incompatibility, or worker liveness.",
                })
    return pairs


def _pagination_state(coverage: dict[str, Any]) -> str:
    metadata = coverage.get("response_metadata")
    cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else None
    phrase = str(coverage.get("pagination_info", "")).strip()
    if coverage.get("has_more") is True or cursor:
        return "partial"
    if re.search(r"(?:There are more messages|next page.*(?:cursor|results)|use cursor:)", phrase, re.I):
        return "partial"
    if coverage.get("has_more") is False or re.search(r"(?:There are no more messages|End of results|No more pages available)", phrase, re.I):
        return "source_end_observed"
    return "unknown"


def build_claim_overlap(
    snapshots: Iterable[Any], *, source_names: Sequence[str] | None = None,
    workspace_url: str | None = None, channel_id: str | None = None,
    path_filters: Sequence[str] = (), operation_filters: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a passive view from decoded snapshots; filters are substrings.

    ``workspace_url`` and ``channel_id`` supply known metadata omitted by detailed
    renderings.  They do not supply time or identity.  Ambiguous lifecycle evidence
    remains active for this advisory, with its reason in ``unresolved``.
    """
    snapshots = list(snapshots)
    if not snapshots:
        raise SnapshotError("at least one snapshot is required")
    if source_names is not None and len(source_names) != len(snapshots):
        raise SnapshotError("source_names must contain one name per snapshot")
    if channel_id is not None and not _channel(channel_id):
        raise SnapshotError("channel_id must be an observed Slack C, D, or G conversation ID")
    if workspace_url is not None:
        parsed = urlsplit(workspace_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise SnapshotError("workspace_url must be a workspace origin, such as https://example.slack.com")
    messages: list[dict[str, Any]] = []
    input_coverage: list[dict[str, Any]] = []
    for index, snapshot in enumerate(snapshots):
        name = source_names[index] if source_names else f"snapshot-{index + 1}"
        coverage: dict[str, Any] = {"snapshot": name}
        context = {"snapshot": name, "workspace_url": workspace_url, "channel_id": channel_id}
        records = _unwrap(snapshot, context, coverage)
        coverage["messages_read"] = len(records)
        coverage["pagination_state"] = _pagination_state(coverage)
        input_coverage.append(coverage)
        messages.extend(records)
    seen: set[tuple[Any, ...]] = set()
    duplicates = 0
    groups: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    all_events: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    versions: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in messages:
        source = record["source"]
        identity = (record["workspace_url"], source["channel_id"], source["message_ts"])
        if not source["channel_id"] or not source["message_ts"]:
            identity = (*identity, source["snapshot"], source["position"])
        digest = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
        key = (*identity, digest, _repository_key(record["repository"]))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        versions[identity].append(source)
        events, unknown = _events(record)
        unresolved.extend(unknown)
        all_events.extend(events)
    _resolve_aliases(all_events, unresolved)
    for event in all_events:
        groups[(_repository_key(event["repository"]), event["operation_id"])].append(event)
    claims = [_reduce(operation, events, unresolved) for (_, operation), events in sorted(groups.items(), key=lambda item: (item[0][0] or "", item[0][1]))]
    pairs = _overlaps(claims)
    selected = {claim["operation_id"] for claim in claims
                if (not operation_filters or any(value.lower() in claim["operation_id"].lower() for value in operation_filters))
                and (not path_filters or any(value in scope["path"] for value in path_filters for scope in claim["scopes"]))}
    if path_filters or operation_filters:
        pairs = [pair for pair in pairs if pair["left_operation_id"] in selected or pair["right_operation_id"] in selected]
        selected.update(operation for pair in pairs for operation in (pair["left_operation_id"], pair["right_operation_id"]))
        claims = [claim for claim in claims if claim["operation_id"] in selected]
        unresolved = [item for item in unresolved if item.get("operation_id") in selected
                      or (not item.get("operation_id") and any(value.lower() in item.get("text", "").lower() for value in [*operation_filters, *path_filters]))]
    active_count = sum(claim["state"] != "terminal_observed" for claim in claims)
    return {
        "schema": SCHEMA, "advisory_only": True,
        "coverage": {"scope": "input_snapshots_only", "snapshots": input_coverage,
            "messages_read": len(messages), "exact_duplicate_messages": duplicates,
            "read_extent": "partial_source_history" if any(item["pagination_state"] == "partial" for item in input_coverage) else "supplied_messages_only",
            "different_versions_of_message": [sources for sources in versions.values() if len(sources) > 1],
            "global_work_state": "not_assessed", "worker_liveness": "not_assessed",
            "notes": ["Only supplied snapshot messages are covered; no global empty-work conclusion follows.",
                      "A source-end marker applies to its supplied page and does not prove that all preceding history was supplied.",
                      "Source timestamps order explicit statements when present; no times are inferred from operation IDs.",
                      "A shortened name resolves only to a unique earlier dated declaration in the same repository context; evidence records that resolution.",
                      "Unbound completion text remains unresolved. unknown_active means no resolved terminal statement was found, not a claim of current liveness.",
                      "Unqualified filenames and unknown repositories require source reconciliation.",
                      "This view does not grant, revoke, assign, block, or require a claim."]},
        "filters": {"paths": list(path_filters), "operations": list(operation_filters)},
        "summary": {"operations": len(claims), "active_or_unresolved": active_count,
                    "terminal_observed": len(claims) - active_count, "potential_overlap_pairs": len(pairs),
                    "unresolved_records": len(unresolved)},
        "claims": claims, "overlaps": pairs, "unresolved": unresolved,
    }


def _read(path: str) -> Any:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise SnapshotError(f"{path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if re.search(r"^\s*(?:Message TS|Message_ts):", text, re.M):
            return text
        raise SnapshotError(f"{path}: invalid JSON or unsupported detailed text: {exc}") from exc


def _as_text(result: dict[str, Any]) -> str:
    summary = result["summary"]
    coverage = result["coverage"]
    lines = ["Advisory claim overlap — supplied snapshots only",
        f"Coverage: {coverage['read_extent']}; supplied messages: {coverage['messages_read']}; "
        f"exact duplicates: {coverage['exact_duplicate_messages']}."]
    lines.extend(
        f"  {snapshot['snapshot']}: {snapshot['messages_read']} messages; {snapshot['pagination_state']}"
        for snapshot in coverage["snapshots"]
    )
    for name, values in result["filters"].items():
        if values:
            lines.append(f"Filter {name}: {', '.join(values)}")
    lines.extend([
        f"Operations: {summary['operations']}; active or unresolved: {summary['active_or_unresolved']}; "
        f"terminal observations: {summary['terminal_observed']}; potential pairs: {summary['potential_overlap_pairs']}.",
        "A source-end marker describes its supplied page; earlier history may still be omitted.",
        "No liveness, semantic conflict, permission, or global queue conclusion is made."])
    if result["claims"]:
        lines.extend(["", "Operation details:"])
    else:
        lines.append("No selected operations were found in these supplied messages.")
    for claim in result["claims"]:
        repository = ", ".join(claim["repositories"]) or "repository unknown"
        lines.append(f"  {claim['operation_id']} [{claim['state']}; {repository}]")
        scopes = dict.fromkeys(
            scope["literal"] + ("; symbols: " + ", ".join(scope["symbols"]) if scope["symbols"] else "")
            for scope in claim["scopes"]
        )
        lines.extend(f"    scope: {scope}" for scope in scopes)
        lines.extend(f"    sponsor issue: {target['issue_url']}" for target in claim["issue_targets"])
        if not scopes:
            lines.append("    scope: unresolved in the supplied statements")
        references = dict.fromkeys(
            (event["kind"], event["source"]["permalink"] or
             str(event["source"]["snapshot"]) + ":" + str(event["source"]["position"]))
            for event in claim["evidence"]
        )
        lines.extend(f"    {kind}: {reference}" for kind, reference in references)
    for pair in result["overlaps"]:
        lines.extend(["", f"{pair['left_operation_id']} / {pair['right_operation_id']}"])
        for match in pair["issue_matches"]:
            lines.append(f"  sponsor issue: {match['issue_url']} ({match['relation']})")
            for key in ("left_source", "right_source"):
                source = match[key]
                lines.append(f"    {source['permalink'] or str(source['snapshot']) + ':' + str(source['position'])}")
        for match in pair["matches"]:
            left, right = match["left_scope"], match["right_scope"]
            lines.append(f"  {left['literal']} / {right['literal']}: {match['path_relation']}; {match['symbol_relation']}")
            for scope in (left, right):
                source = scope["source"]
                lines.append(f"    {source['permalink'] or str(source['snapshot']) + ':' + str(source['position'])}")
    lines.extend(["", f"Unresolved source records: {summary['unresolved_records']} (full reasons and evidence in JSON output)."])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", help="saved detailed Slack JSON/text or structured messages; '-' reads stdin")
    parser.add_argument("--workspace-url", help="observed Slack workspace origin when absent from saved messages")
    parser.add_argument("--channel-id", help="observed conversation ID when absent from saved messages")
    parser.add_argument("--path", action="append", default=[], help="path substring filter; repeat for alternatives")
    parser.add_argument("--operation", action="append", default=[], help="operation substring filter; repeat for alternatives")
    parser.add_argument("--text", action="store_true", help="print a short human-readable overlap view instead of full JSON")
    args = parser.parse_args(argv)
    try:
        if args.snapshots.count("-") > 1:
            raise SnapshotError("stdin may be supplied only once")
        result = build_claim_overlap([_read(path) for path in args.snapshots], source_names=args.snapshots,
            workspace_url=args.workspace_url, channel_id=args.channel_id,
            path_filters=args.path, operation_filters=args.operation)
        print(_as_text(result) if args.text else json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SnapshotError, RecursionError) as exc:
        print(f"claim_overlap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
