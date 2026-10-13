"""Read existing Commons/provider projections into deterministic swarm events.

No network requests occur here. A single command-center collector refresh feeds
all workers; incomplete provider pagination remains explicit, never a claim DB.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from host import feed_delta, seat_census
from integrations.command_center.schema import _text
from memory_board import parse_record

from .identity import task_key
from .projector import _merge_sha, _order, _time, merge_facts

UNKNOWN = "UNKNOWN"
_ACTIONS = {"OPEN": "OPEN", "TAKE": "TAKE", "CLAIM": "TAKE",
            "ACTIVE": "TAKE", "HEARTBEAT": "HEARTBEAT", "SHIP": "SHIP",
            "SHIPPED": "SHIP", "DONE": "SHIP", "BLOCK": "BLOCK",
            "BLOCKED": "BLOCK", "SUPERSEDE": "SUPERSEDE",
            "SUPERSEDED": "SUPERSEDE", "ABANDON": "ABANDON",
            "ABANDONED": "ABANDON", "RECOVER": "RECOVER",
            "RELEASE": "RELEASE", "RELEASED": "RELEASE"}
_START = re.compile(r"^\s*(?:[#*`]+\s*)?(OPEN|TAKE|CLAIM|ACTIVE|HEARTBEAT|SHIP|SHIPPED|DONE|BLOCK|BLOCKED|SUPERSEDE|SUPERSEDED|ABANDON|ABANDONED|RECOVER|RELEASE|RELEASED)\b", re.I)
_REF = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/[1-9][0-9]*|(?:github:)?[\w.-]+/[\w.-]+:(?:issue|pr):[1-9][0-9]*|(?:issue|pr):[\w.-]+/[\w.-]+:[1-9][0-9]*", re.I)
_FIELDS = ("repo", "issue", "pr", "base_sha", "head_sha", "branch", "merge_sha",
           "artifact", "blocker", "next_action", "superseded_by", "model", "harness",
           "required_capabilities", "exact_error", "feed_cursor",
           "started_at", "heartbeat", "expected_started_at", "expected_worker",
           "expected_heartbeat")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, default=str).encode()).hexdigest()


def _read(path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _key(value):
    try:
        return task_key(value)
    except (ValueError, TypeError):
        return None


def _selected(value):
    """Bounded source metadata; never copy a Slack message body into the log."""
    # Lifecycle clocks and expectations belong to the source event. Dropping
    # them loses releases or lets recovery refer to a different claim; the
    # projector decides whether the supplied generation is still current.
    out = {}
    for name in _FIELDS:
        field = value.get(name)
        if isinstance(field, (str, int, float, bool)):
            out[name] = _text(field, 2000 if name in {"exact_error", "blocker"} else 500)
        elif name == "required_capabilities" and isinstance(field, list):
            out[name] = [_text(x, 120) for x in field[:30] if isinstance(x, str)]
        elif name == "artifact" and isinstance(field, dict):
            out[name] = {k: _text(v, 500) for k, v in field.items()
                         if k in {"url", "repo", "pr", "branch", "head_sha", "merge_sha",
                                  "path", "sha", "kind", "target_branch"}
                         and isinstance(v, (str, int))}
            # Completion is semantic, so preserve the Boolean without text coercion.
            if isinstance(field.get("complete"), bool):
                out[name]["complete"] = field["complete"]
    return out


def _structured(meta, body):
    supplied = meta.get("swarm_event")
    if isinstance(supplied, str):
        try:
            supplied = json.loads(supplied)
        except ValueError:
            supplied = None
    if isinstance(supplied, (dict, list)):
        return supplied if isinstance(supplied, list) else [supplied]
    # The machine entry format is explicit, never an interpretation of prose.
    candidates = [body.strip()]
    candidates.extend(re.findall(r"```(?:json|swarm_event)\s*\n(.*?)```", body, re.S))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("swarm_event"), (dict, list)):
            value = obj["swarm_event"]
            return value if isinstance(value, list) else [value]
        if isinstance(obj, dict) and obj.get("task_key") and obj.get("action"):
            return [obj]
    if meta.get("task_key") and str(meta.get("action") or meta.get("kind")).upper() in _ACTIONS:
        return [{**meta, "action": meta.get("action") or meta.get("kind")}]
    return []


def _events(meta, body, source_id, revision, *, private=False):
    normalized = _structured(meta, body)
    if not normalized:
        first = next((line for line in body.splitlines() if line.strip()), "")
        match = _START.match(first)
        action = _ACTIONS.get(str(meta.get("kind", "")).upper())
        action = _ACTIONS.get(match.group(1).upper()) if match else action
        if not action:
            return []
        refs = {key for raw in _REF.findall(body) if (key := _key(raw))}
        if meta.get("task_key") and (key := _key(meta["task_key"])):
            refs.add(key)
        if len(refs) != 1:
            return []  # Multiple references do not imply multiple jobs.
        normalized = [{"action": action, "task_key": refs.pop()}]
    out = []
    for index, value in enumerate(normalized):
        if not isinstance(value, dict):
            continue
        key = _key(value)
        action = _ACTIONS.get(str(value.get("action", "")).upper())
        if not key or not action:
            continue
        event = {"id": source_id + ":" + revision + ":" + str(index),
                 "action": action, "task_key": key,
                 "worker": _text(value.get("worker") or meta.get("from") or UNKNOWN, 200),
                 "at": value.get("at") or meta.get("ts") or meta.get("durable_ts") or UNKNOWN,
                 "source": source_id, "source_event_ids": [source_id],
                 **_selected(meta), **_selected(value)}
        if not private:
            event["summary"] = _text(body.splitlines()[0] if body.splitlines() else "", 240)
        if key.startswith("github:"):
            event.setdefault("required_capabilities", ["github-publish"])
        if meta.get("durable_ts") and meta.get("id"):
            event.setdefault("feed_cursor", feed_delta.cursor_of(meta))
        out.append(event)
    return out


def legacy_events(holdings, mirrored=None):
    """Adapt the existing state/claims holdings without assigning opaque keys."""
    mirrored = mirrored if isinstance(mirrored, dict) else {}
    rows = holdings.items() if isinstance(holdings, dict) else enumerate(holdings or [])
    events = []
    for path, record in rows:
        if not isinstance(record, dict) or record.get("unreadable"):
            continue
        revision = _digest(record)
        if mirrored.get(str(path)) == revision:
            continue
        raw = str(record.get("key") or Path(str(path)).stem)
        match = re.fullmatch(r"(?:repo-[0-9a-f]{24}-)?(issue|pr)-([1-9][0-9]*)", raw)
        repo = record.get("repository")
        if not repo and not raw.startswith("repo-"):
            repo = "woahwhattheheck/commons"
        key = _key(f"github:{repo}:{match[1]}:{match[2]}") if match and repo else None
        if not key and record.get("owner_command_id"):
            key = _key("commons:owner-command:" + str(record["owner_command_id"]))
        if not key:
            continue
        source = "legacy-claim:" + str(path)
        common = {"task_key": key, "source": source, "source_event_ids": [source],
                  "worker": record.get("holder") or UNKNOWN,
                  "at": record.get("taken_at") or record.get("heartbeat_at") or UNKNOWN}
        events.append({**common, "id": source + ":" + revision + ":open", "action": "OPEN"})
        if record.get("state") == "HELD":
            events.append({**common, "id": source + ":" + revision + ":take", "action": "TAKE",
                           "heartbeat": record.get("heartbeat_at") or UNKNOWN,
                           "started_at": record.get("taken_at") or UNKNOWN,
                           "legacy_ttl_s": record.get("ttl_s"),
                           "required_capabilities": ["github-publish"]})
            if record.get("heartbeat_at") and record["heartbeat_at"] != common["at"]:
                events.append({**common, "id": source + ":" + revision + ":heartbeat",
                               "action": "HEARTBEAT", "at": record["heartbeat_at"]})
        elif record.get("state") == "RELEASED":
            # Relinquishment is distinct from shipment, abandonment or completion.
            # Bind it to the exact take so an old release cannot clear a new one.
            events.append({**common, "id": source + ":" + revision + ":release",
                           "action": "RELEASE", "at": record.get("heartbeat_at") or UNKNOWN,
                           "expected_started_at": record.get("taken_at") or UNKNOWN})
    return events


def _git(root, *args):
    """Local object/index reads only; no fetch, provider request or ref mutation."""
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                                capture_output=True, text=True, timeout=15,
                                env={**os.environ, "GIT_NO_LAZY_FETCH": "1",
                                     "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _post_changes(root, files, prior):
    """Portable content boundary plus changed paths, independent of checkout age.

    HEAD:p identifies committed bytes. Only dirty/untracked post bodies need
    content hashes. Both travel safely between fresh workers, unlike mtimes.
    A missing old tree or a non-Git checkout widens the local read explicitly.
    """
    tree = _git(root, "rev-parse", "--verify", "HEAD:p")
    tree = tree.strip() if tree else ""
    raw_status = _git(root, "-c", "status.renames=false", "status", "--porcelain=v1",
                      "-z", "--untracked-files=all", "--", "p") if tree else None
    git_backed = bool(re.fullmatch(r"[0-9a-f]{40,64}", tree)) and raw_status is not None
    raw_bodies, unreadable, dirty, changed, deleted = {}, set(), {}, set(), set()

    def read(ident):
        try:
            raw = files[ident].read_text(encoding="utf-8")
        except (OSError, UnicodeError, KeyError):
            unreadable.add(ident)
            return "UNREADABLE"
        raw_bodies[ident] = raw
        return hashlib.sha256(raw.encode()).hexdigest()

    if not git_backed:
        # Without Git there is no portable cheap change index. Read actual bytes
        # instead of presenting a host clock or directory mtime as completeness.
        content = {ident: read(ident) for ident in sorted(files)}
        signature = _digest(content)
        changed = set(files) if signature != prior.get("post_catalog_signature") else set()
        return {"mode": "content-scan", "reason": "local_git_catalog_unavailable",
                "signature": signature, "tree": "", "dirty": {}, "changed": changed,
                "deleted": deleted, "raw_bodies": raw_bodies, "unreadable": unreadable,
                "full": bool(changed)}

    for entry in raw_status.split("\0"):
        if len(entry) < 4:
            continue
        path = Path(entry[3:])
        if path.parent.as_posix() != "p" or path.suffix != ".md":
            continue
        ident = path.stem
        if ident in files:
            dirty[ident] = read(ident)
        else:
            dirty[ident] = "DELETED"
            deleted.add(ident)
    old_dirty = prior.get("post_dirty", {})
    changed.update(ident for ident in set(old_dirty) | set(dirty)
                   if old_dirty.get(ident) != dirty.get(ident))
    old_tree = prior.get("post_tree", "")
    full, reason = False, ""
    if prior.get("post_catalog_version") != 2 or not re.fullmatch(r"[0-9a-f]{40,64}", old_tree):
        full, reason = True, "catalog_bootstrap"
    elif old_tree != tree:
        names = _git(root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames",
                     "-r", "-z", old_tree, tree, "--")
        if names is None:
            full, reason = True, "prior_post_tree_unavailable"
        else:
            for name in names.split("\0"):
                path = Path(name)
                if name and path.parent.as_posix() == "." and path.suffix == ".md":
                    changed.add(path.stem)
                    if path.stem not in files:
                        deleted.add(path.stem)
    if full:
        changed.update(files)
    return {"mode": "git-tree", "reason": reason,
            "signature": _digest({"tree": tree, "dirty": dirty}),
            "tree": tree, "dirty": dirty, "changed": changed, "deleted": deleted,
            "raw_bodies": raw_bodies, "unreadable": unreadable, "full": full}


def _commons(root, prior):
    """Consume changed post bytes while retaining incomplete feed coverage.

    The Git catalog supplies the complete local change boundary even when the
    feed remains unordered. A gap keeps fallback sources and missing-ID retries
    active without reparsing an unchanged corpus that the catalog already read.
    """
    pulse = _read(root / "pulse.json", {}) or {}
    cursor = prior.get("feed_cursor", "")
    delta = feed_delta.since(cursor, root=str(root))
    reads = ["feed/head.json"]
    if not cursor or delta.get("state") != "COMPLETE":
        delta = feed_delta.since(cursor, root=str(root), shard="window")
        reads.append("feed/window.json")
    needs_full = not cursor or delta.get("state") != "COMPLETE"
    recent = _read(root / "recent.json", []) if needs_full else []
    if needs_full:
        reads.append("recent.json")
    expected = {e["c"].split("|", 1)[1] for e in delta.get("events", [])
                if isinstance(e, dict) and "|" in str(e.get("c", ""))}
    expected.update(delta.get("undated", []))
    expected.update(prior.get("missing_ids", []))
    revisions = dict(prior.get("post_revisions", {}))
    files = {path.stem: path for path in sorted((root / "p").glob("*.md"))}
    catalog = _post_changes(root, files, prior)
    missing, unreadable = set(), set(catalog["unreadable"])
    selected = set(files) if catalog["full"] else catalog["changed"] | expected
    out, high = [], cursor
    full_rows = _read(root / "posts.json", []) if needs_full else []
    if needs_full:
        reads.append("posts.json")
        expected.update(row.get("id") for row in full_rows if isinstance(row, dict) and row.get("id"))
    missing.update(expected - set(files))
    missing.update(catalog["deleted"])
    if selected:
        reads.append("p/*.md" if catalog["full"] else "p/{changed-or-feed-id}.md")
        for ident in sorted(selected & set(files)):
            try:
                raw = catalog["raw_bodies"].get(ident)
                if raw is None:
                    raw = files[ident].read_text(encoding="utf-8")
                meta, body = parse_record(raw)
            except (OSError, UnicodeError, ValueError):
                unreadable.add(ident)
                continue
            meta.setdefault("id", ident)
            revision = _digest([meta, body])
            if revisions.get(ident) == revision:
                continue
            events = _events(meta, body, "commons:" + ident, revision)
            if events:
                revisions[ident] = revision
                out.extend(events)
    if needs_full:
        # Existing ingest snapshots can carry carrier events before p/ lands.
        for row in list(full_rows or []) + list(recent or []):
            if not isinstance(row, dict) or not row.get("id") or row["id"] in files:
                continue
            ident = row["id"]
            revision = _digest([row.get("body", ""), row.get("ts"), row.get("durable_ts")])
            if revisions.get(ident) != revision:
                events = _events(row, str(row.get("body", "")), "commons:" + ident, revision)
                if events:
                    revisions[ident] = revision
                    out.extend(events)
    for entry in delta.get("events", []):
        if isinstance(entry, dict) and "|" in str(entry.get("c", "")):
            ident = entry["c"].split("|", 1)[1]
            if ident in files and ident not in unreadable:
                high = max(high, entry["c"])
    # Never let a cursor erase unresolved holes. The exact missing IDs survive.
    gaps = []
    if delta.get("state") == "FINDER-FAILED":
        gaps.append({"kind": "feed_unreadable", "after": cursor})
    if missing or unreadable:
        gaps.append({"kind": "durable_posts_missing", "after": cursor,
                     "ids": sorted(missing | unreadable)})
    coverage = {"complete": not gaps, "scope": "available local Commons corpus; provider ingestion may lag",
                "reads": reads, "feed_state": delta.get("state", UNKNOWN),
                "complete_since": delta.get("complete_since", UNKNOWN),
                "pulse_seq": pulse.get("seq", UNKNOWN), "pulse_at": pulse.get("ts", UNKNOWN),
                "posts_available": len(files), "catalog_mode": catalog["mode"],
                "gaps": gaps}
    following = {"feed_cursor": high, "pulse_seq": pulse.get("seq", UNKNOWN),
                 "post_catalog_version": 2, "post_catalog_signature": catalog["signature"],
                 "post_tree": catalog["tree"], "post_dirty": catalog["dirty"],
                 "post_revisions": revisions,
                 "missing_ids": sorted(missing | unreadable), "gaps": gaps}
    return out, following, coverage


def _fact(row, source, repo=None):
    refs = row.get("refs") if isinstance(row.get("refs"), dict) else {}
    merged = {**refs, **row}
    repo = merged.get("repository") or merged.get("repo") or repo or row.get("project")
    number = merged.get("number") or merged.get("pr")
    key = _key({"repo": repo, "pr": number}) if repo and number else _key(row.get("url"))
    if not key or ":pr:" not in key:
        return None, None
    status = str(row.get("state") or row.get("status") or UNKNOWN).upper()
    is_merged = status == "MERGED" or _time(merged.get("merged_at")) is not None or merged.get("merged") is True
    head = merged.get("head") if isinstance(merged.get("head"), dict) else {}
    base = merged.get("base") if isinstance(merged.get("base"), dict) else {}
    merge_sha = _merge_sha(merged)
    if merge_sha == UNKNOWN and isinstance(merged.get("mergeCommit"), dict):
        merge_sha = merged["mergeCommit"].get("oid")
    fact = {"task_key": key, "repo": key.split(":")[1], "pr": int(key.rsplit(":", 1)[1]),
            "state": "MERGED" if is_merged else status, "merged": is_merged,
            "merged_at": merged.get("merged_at") or UNKNOWN,
            "merge_sha": merge_sha or UNKNOWN,
            "head_sha": merged.get("head_sha") or head.get("sha") or head.get("oid") or UNKNOWN,
            "branch": merged.get("branch") or merged.get("head_branch") or head.get("ref") or UNKNOWN,
            "base_sha": merged.get("base_sha") or base.get("sha") or UNKNOWN,
            "updated_at": merged.get("updated_at") or UNKNOWN,
            "observed_at": source.get("last_good_observed_at") or source.get("observed_at") or UNKNOWN,
            "source": source.get("id", UNKNOWN),
            "stale": source.get("data_stale", source.get("stale", UNKNOWN)),
            "degraded": source.get("status") in {"error", "degraded", "failed"} or bool(source.get("degraded"))}
    for name in ("issue", "issues", "closing_issues", "superseded_by"):
        if merged.get(name) is not None:
            fact[name] = copy.deepcopy(merged[name])
    return key, fact


def github_listing_facts(repository, *, open_rows=None, open_observed_at=None,
                         closed_rows=None, closed_observed_at=None):
    """Reuse successful provider reads with their explicit observation times.

    These transient facts make the already-read open PRs routable without
    changing the byte-stable feed bake or making another provider request.
    Missing or invalid timestamps never become a fresh observation.
    """
    from host.github_state import _closed

    facts = {}
    for status, rows, observed in (("OPEN", open_rows, open_observed_at),
                                   ("CLOSED", closed_rows, closed_observed_at)):
        if not isinstance(rows, list) or not isinstance(observed, str):
            continue
        try:
            moment = datetime.fromisoformat(observed.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            continue
        stamp = moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        source = {"id": "https://api.github.com/repos/" + str(repository) +
                        "/pulls?state=" + status.lower(),
                  "observed_at": stamp, "status": "ok"}
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = {**row, "state": status}
            if status == "CLOSED":
                # Reuse the bake's merge semantics: a branch head or speculative
                # merge commit on an unmerged PR is never a landed merge SHA.
                closure = _closed(row)
                normalized.update(state=closure["state"], merged_at=closure["merged_at"],
                                  merge_commit_sha=closure["merge_commit_sha"])
            else:
                normalized.update(merged=False, merged_at=None, merge_commit_sha=None)
            key, fact = _fact(normalized, source, repository)
            if key:
                merge_facts(facts, {key: fact})
    return facts


def github_listing_files(repository, directory):
    """Read this ingest job's existing JSONL/observation-sidecar pairs only."""
    from host.github_state import _read_pulls

    directory, inputs = Path(directory), {}
    for kind in ("open", "closed"):
        try:
            observed = (directory / (kind + "_pulls.observed_at")).read_text(encoding="utf-8").strip()
            rows = _read_pulls(str(directory / (kind + "_pulls.jsonl")))
        except (OSError, UnicodeError, ValueError):
            continue
        inputs[kind + "_rows"] = rows
        inputs[kind + "_observed_at"] = observed
    return github_listing_facts(repository, **inputs)


def _github(root):
    payload = _read(root / "feed/github.json", {}) or {}
    source = {"id": "commons:feed/github.json", "degraded": payload.get("degraded", [])}
    facts = {}
    for name in ("pulls", "newest", "oldest", "newest_pulls", "longest_open",
                 "open_pull_requests", "recently_closed"):
        rows = payload.get(name, [])
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                key, fact = _fact(row, source, payload.get("repository"))
                if key:
                    merge_facts(facts, {key: fact})
    for number, head in (payload.get("open_heads") or {}).items():
        row = head if isinstance(head, dict) else {"head_sha": head}
        key, fact = _fact({"number": number, "state": "OPEN", **row}, source, payload.get("repository"))
        if key:
            existing = facts.get(key)
            if existing and existing.get("merged"):
                continue
            if existing:
                # The compact map only asserts current head and open state;
                # don't erase branch/activity fields supplied by detailed rows.
                existing.update(head_sha=fact["head_sha"], state="OPEN", merged=False)
            else:
                merge_facts(facts, {key: fact})
    return facts, {"complete": payload.get("pulls_listing") == "COMPLETE" and not payload.get("degraded"),
                   "scope": "baked PR listing", "observed_at": UNKNOWN,
                   "unchanged_since": payload.get("unchanged_since", UNKNOWN),
                   "degraded": payload.get("degraded", []),
                   "note": "unchanged_since is a change timestamp, not a fresh provider observation"}


def _workstreams(snapshot, prior):
    sources = {str(s.get("id")): s for s in snapshot.get("sources", []) if isinstance(s, dict)}
    events, facts, following, coverage = [], {}, copy.deepcopy(prior), {}
    # Bump when parser changes should reconsider previously ignored messages.
    ignored_items_version = 1
    # Negative results cover only this snapshot, including when a source leaves it.
    # The selected event checkpoints in items remain durable.
    for checkpoint in following.values():
        checkpoint["ignored_items"] = {}
        checkpoint["ignored_items_version"] = ignored_items_version
    for ident, source in sources.items():
        old = prior.get(ident, {})
        metadata = source.get("metadata") or {}
        boundary = {key: metadata[key] for key in
                    ("next_cursor", "history", "thread_coverage", "threads_pending",
                     "threads_pending_count", "threads_pending_truncated", "github_reads") if key in metadata}
        # Keep exact opaque cursors/thread boundaries even when coverage is partial.
        following[ident] = {"observed_at": source.get("observed_at", UNKNOWN),
                            "items": dict(old.get("items", {})),
                            "ignored_items": {},
                            "ignored_items_version": ignored_items_version,
                            "provider_boundary": boundary or old.get("provider_boundary", {}),
                            "newest_message_ts": old.get("newest_message_ts", "")}
        coverage[ident] = {"provider": source.get("provider"), "scope": source.get("scope"),
                           "coverage": source.get("coverage", {"complete": False}),
                           "observed_at": source.get("observed_at", UNKNOWN),
                           "last_good_observed_at": source.get("last_good_observed_at", UNKNOWN),
                           "status": source.get("status", UNKNOWN),
                           "retained_last_good": source.get("retained_last_good", False),
                           "data_stale": source.get("data_stale", UNKNOWN)}
    for item in snapshot.get("items", []):
        if not isinstance(item, dict):
            continue
        sid, iid = str(item.get("source_id", "")), str(item.get("id", ""))
        source = sources.get(sid, {})
        if sid not in following or not iid:
            continue
        provider = str(item.get("provider") or source.get("provider", "")).lower()
        refs = item.get("refs") or {}
        # Exclude observation/age counters from event identity: observing the
        # same Slack message again is not an edit or another TAKE.
        revision = _digest({k: v for k, v in item.items() if k not in
                            {"first_seen_at", "last_seen_at", "owner_work"}})
        changed = following[sid]["items"].get(iid) != revision
        selected = False
        if provider == "github" and item.get("kind") == "pull_request":
            key, fact = _fact(item, source)
            if key:
                merge_facts(facts, {key: fact})
                selected = True
                if changed and fact["state"] == "OPEN":
                    events.append({"id": iid + ":" + revision, "action": "OPEN", "task_key": key,
                                   "source": iid, "source_event_ids": [iid],
                                   "at": item.get("created_at") or item.get("updated_at") or UNKNOWN,
                                   "required_capabilities": ["github-publish"]})
        elif provider == "slack" and changed:
            old = prior.get(sid, {})
            ignored = (old.get("ignored_items", {}) if
                       old.get("ignored_items_version") == ignored_items_version else {})
            if ignored.get(iid) != revision:
                meta = {"from": item.get("owner"), "ts": item.get("updated_at"),
                        "swarm_event": (item.get("metadata") or {}).get("swarm_event")}
                normalized = _events(meta, str(item.get("summary") or ""), iid, revision, private=True)
                events.extend(normalized)
                selected = bool(normalized)
            if not selected:
                following[sid]["ignored_items"][iid] = revision
        if provider in {"slack", "github"}:
            if selected:
                following[sid]["items"][iid] = revision
            if refs.get("message_ts"):
                following[sid]["newest_message_ts"] = max(
                    str(following[sid].get("newest_message_ts", "")), str(refs["message_ts"]))
    return events, facts, following, coverage


def _seats(root):
    payload = _read(root / "seats.json", {}) or {}
    declared, bad = seat_census.read_declared(str(root))
    rows = {str(r.get("seat")): r for r in payload.get("seats", []) if isinstance(r, dict)}
    for name, record in declared.items():
        rows[name] = {**rows.get(name, {}), "seat": name, "declared": record, "source": "declared"}
    payload["seats"] = [rows[k] for k in sorted(rows)]
    payload["roster"] = [r for r in payload.get("roster", []) if r.get("seat") not in rows]
    payload["unreadable_seat_files"] = bad
    return payload  # Dispatcher calls seat_census.recompute at its actual clock.


def collect(root: Path, cursors: dict, work_snapshot: dict | None = None) -> dict:
    """Collect existing state without spending provider quota or mutating files."""
    root = Path(root)
    cursors = cursors or {}
    events, commons_cursor, commons_coverage = _commons(root, cursors.get("commons", {}))
    facts, github_coverage = _github(root)
    more, provider_facts, source_cursors, source_coverage = _workstreams(
        work_snapshot or {}, cursors.get("sources", {}))
    merge_facts(facts, provider_facts)
    unique = {event["id"]: event for event in events + more}
    return {"events": sorted(unique.values(), key=_order),
            "provider_facts": facts,
            "cursors": {"commons": commons_cursor, "sources": source_cursors},
            "coverage": {"commons": commons_coverage, "github": github_coverage, **source_coverage},
            "seats": _seats(root)}
