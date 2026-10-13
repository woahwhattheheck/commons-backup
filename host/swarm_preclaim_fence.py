#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only source and PR coordination check before a swarm branch is bound.

The fence composes with ``coordination_state.py`` and never writes GitHub or
Slack. Internal TAKE/CLAIM labels and exact-target mentions remain advisory
coordination evidence, not exclusive authority or permission to bind a branch.
SAFE requires complete Slack, owner-PR-census, owner-default, and
upstream evidence; any incomplete absence proof fails closed. For ordinary
issues, a closed state or live upstream assignment still blocks branch binding.
Open cross-referenced PRs are retained as coordination context; their existence
alone does not establish a duplicate own PR or exclusive implementation claim.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

try:
    from coordination_state import GitHub, discover_token
except ImportError:
    from host.coordination_state import GitHub, discover_token

SAFE = "SAFE_TO_BIND_BRANCH"
OWNED = "OWNED"
ABSORBED = "ALREADY_ABSORBED"
MANUAL = "NEEDS_MANUAL_DIFF"
SAFE_TO_BIND_BRANCH = SAFE
ALREADY_ABSORBED = ABSORBED
NEEDS_MANUAL_DIFF = MANUAL
EXIT_CODE = {SAFE: 0, OWNED: 20, ABSORBED: 21, MANUAL: 22}

MAX_OWNER_PR_PAGES = 5
MAX_PR_FILE_PAGES = 10
CUSTODY_RE = re.compile(
    r"\b(?:TAKE|CLAIM(?:ED)?|CUSTODY|MERGE[- ]SUCCESSOR|SOURCE\+MERGE|I\s+OWN|OWNERSHIP)\b",
    re.I,
)
RELEASE_RE = re.compile(r"\b(?:YIELD|RELEASED?|UNCLAIMED)\b", re.I)
TARGET_RE = re.compile(
    r"^(?:https://github\.com/)?(?P<owner>[^/\s]+)/(?P<repo>[^/#\s]+)"
    r"(?:(?:/(?P<kind>pull|pulls|issue|issues)/)|#)(?P<number>\d+)/?$"
)


class EvidenceError(RuntimeError):
    pass


class SlackCollectionError(EvidenceError):
    """A failed query together with the completed queries from this read."""

    def __init__(self, error, evidence):
        super().__init__(str(error))
        self.error_type = type(error).__name__
        self.evidence = evidence


def parse_target(value):
    m = TARGET_RE.match(value.strip())
    if not m:
        raise ValueError("target must be a GitHub pull/issue URL or owner/repo#number")
    kind = m.group("kind")
    if kind:
        kind = "pull" if kind.startswith("pull") else "issue"
    return {
        "repo": f"{m.group('owner')}/{m.group('repo')}",
        "number": int(m.group("number")),
        "kind": kind,
    }


def _custody(hit, exact=False):
    if hit.get("custody") is not None:
        return bool(hit["custody"])
    text = str(hit.get("text") or "")
    if CUSTODY_RE.search(text):
        return True
    if RELEASE_RE.search(text):
        return False
    return exact and bool(text.strip())


def ownership_evidence(report):
    owned = []
    slack = report.get("slack") or {}
    for bucket, exact in (
        ("stable_id_hits", False),
        ("exact_target_hits", True),
        ("path_semantic_hits", False),
    ):
        for hit in slack.get(bucket) or []:
            if _custody(hit, exact):
                item = dict(hit)
                item["evidence_bucket"] = bucket
                owned.append(item)
    return owned


def _owner_census(report):
    value = report.get("owner_pr_census")
    return value if isinstance(value, dict) else {}


def decide(report):
    if report.get("errors"):
        return MANUAL
    # Slack activity stays in ownership_evidence for coordination; it does not
    # grant or restrict source-writing authority. Current own-PR checks follow.

    census = _owner_census(report)
    if census.get("complete") is not True:
        return MANUAL
    hits = census.get("hits") if isinstance(census.get("hits"), list) else []
    if any(hit.get("strength") == "exact" for hit in hits if isinstance(hit, dict)):
        return OWNED

    upstream = report.get("upstream") or {}
    if upstream.get("kind") == "pull":
        comparisons = report.get("blob_comparisons") or []
        typed = [x for x in comparisons if isinstance(x, dict)]
        if comparisons and len(typed) == len(comparisons) and all(
            x.get("comparable") and x.get("match") for x in typed
        ):
            return ABSORBED

    if hits:
        return MANUAL

    if upstream.get("kind") == "issue":
        state = str(upstream.get("state") or "").strip().lower()
        if state != "open":
            return MANUAL
        if upstream.get("assignees"):
            return MANUAL
        # An open timeline reference alone is advisory, not an admission gate.
        # Exact own-PR matches are handled by the owner census above.

    if upstream.get("kind") != "pull":
        inp = report.get("input") if isinstance(report.get("input"), dict) else {}
        if not (
            inp.get("stable_id")
            or inp.get("candidate_paths")
            or inp.get("semantic_tokens")
        ):
            return MANUAL
        return SAFE
    return MANUAL


def finalize(report):
    out = dict(report)
    out["ownership_evidence"] = ownership_evidence(report)
    out["decision"] = decide(report)
    out["branch_write_allowed"] = out["decision"] == SAFE
    out["exit_code"] = EXIT_CODE[out["decision"]]
    return out


def _search_limit(limit):
    # Slack's legacy endpoint supports at most 100 pages of 100 rows.
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise EvidenceError("Slack search limit must be an integer from 1 to 10000")
    return min(100, limit)


class SlackSearch:
    """Read-only bounded search; partial results are never absence evidence."""

    def __init__(self, token):
        self.token = token.strip()

    def search(self, query, limit=1000):
        count = _search_limit(limit)
        if not self.token:
            raise EvidenceError(
                "Slack search token missing; set SLACK_USER_TOKEN/SLACK_TOKEN "
                "or pass --slack-evidence"
            )
        out, seen, snapshot = [], set(), None
        # Keep count fixed: page offsets depend on it, including the last page.
        for page in range(1, (limit + count - 1) // count + 1):
            params = urllib.parse.urlencode(
                {"query": query, "count": count, "page": page}
            )
            req = urllib.request.Request(
                "https://slack.com/api/search.messages?" + params,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "User-Agent": "commons-swarm-preclaim-fence",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                raise EvidenceError(
                    f"Slack search failed for {query!r}: {exc}"
                ) from exc
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                error = payload.get("error", "invalid_response") if isinstance(payload, dict) else "invalid_response"
                raise EvidenceError(f"Slack search failed for {query!r}: {error}")
            messages = payload.get("messages")
            if not isinstance(messages, dict):
                raise EvidenceError("Slack search messages must be an object")
            matches, paging = messages.get("matches"), messages.get("paging")
            if not isinstance(matches, list) or not isinstance(paging, dict):
                raise EvidenceError("Slack search requires matches and explicit paging")
            for field in ("count", "page", "pages", "total"):
                if type(paging.get(field)) is not int or paging[field] < 0:
                    raise EvidenceError(f"Slack search invalid paging.{field}")
            total, pages = paging["total"], paging["pages"]
            if paging["count"] != count or paging["page"] != page:
                raise EvidenceError("Slack search returned a different page or page width")
            expected_pages = (total + count - 1) // count
            if pages != expected_pages and not (total == 0 and pages == 1):
                raise EvidenceError("Slack search page count contradicts total")
            if "total" in messages and (
                type(messages["total"]) is not int or messages["total"] != total
            ):
                raise EvidenceError("Slack search totals disagree")
            if "pagination" in messages:
                secondary = messages["pagination"]
                pairs = (("page", page), ("per_page", count),
                         ("page_count", pages), ("total_count", total))
                if not isinstance(secondary, dict) or any(
                    type(secondary.get(key)) is not int or secondary[key] != value
                    for key, value in pairs
                ):
                    raise EvidenceError("Slack search pagination objects disagree")
            if snapshot is not None and snapshot != (total, pages):
                raise EvidenceError("Slack search paging changed during collection")
            snapshot = (total, pages)
            if total > limit:
                raise EvidenceError(f"Slack search exceeds {limit}-result budget; tail not collected")
            expected_rows = min(count, max(0, total - (page - 1) * count))
            if len(matches) != expected_rows:
                raise EvidenceError("Slack search page is incomplete or inconsistent")
            for match in matches:
                if not isinstance(match, dict) or not isinstance(match.get("channel"), dict):
                    raise EvidenceError("Slack search malformed message/channel")
                channel = match["channel"]
                identity = channel.get("id") or channel.get("name")
                ts = match.get("ts")
                if not isinstance(identity, str) or not identity or not isinstance(ts, str) or not ts:
                    raise EvidenceError("Slack search message lacks channel/timestamp identity")
                if not isinstance(match.get("text"), str):
                    raise EvidenceError("Slack search message text must be a string")
                key = (identity, ts)
                if key in seen:
                    raise EvidenceError("Slack search repeated a message; coverage is incomplete")
                seen.add(key)
                out.append(
                    {
                        "query": query,
                        "ts": ts,
                        "channel": channel.get("name") or identity,
                        "username": match.get("username"),
                        "permalink": match.get("permalink"),
                        "text": match["text"],
                    }
                )
            if page >= pages:
                if len(out) != total:
                    raise EvidenceError("Slack search did not collect the reported total")
                return out
        raise EvidenceError("Slack search budget exhausted before completion")


class OfflineSlack:
    """Explicit query-to-hit mapping; a missing query is missing evidence."""

    def __init__(self, evidence):
        self.evidence = evidence

    def search(self, query, limit=1000):
        _search_limit(limit)
        if not isinstance(self.evidence, dict) or query not in self.evidence:
            raise EvidenceError(f"offline Slack evidence missing query {query!r}")
        hits = self.evidence[query]
        if not isinstance(hits, list) or len(hits) > limit:
            raise EvidenceError(f"offline Slack query {query!r} requires a bounded hit list")
        for hit in hits:
            if not isinstance(hit, dict) or not isinstance(hit.get("text"), str):
                raise EvidenceError(f"offline Slack query {query!r} has malformed hits")
            if hit.get("custody") is not None and type(hit["custody"]) is not bool:
                raise EvidenceError("offline Slack custody must be boolean or null")
            for key in ("channel", "ts", "query", "username", "permalink"):
                if hit.get(key) is not None and not isinstance(hit[key], str):
                    raise EvidenceError(f"offline Slack hit {key} must be a string or null")
        return [dict(hit) for hit in hits]


def _dedupe(hits):
    seen, out = set(), []
    for hit in hits:
        key = (hit.get("channel"), hit.get("ts"), hit.get("text"))
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out


def _semantic_queries(paths, tokens):
    values = []
    for path in paths:
        values.append(path)
        stem = PurePosixPath(path).stem
        if len(stem) >= 6:
            values.append(stem)
    values.extend(tokens)
    return list(dict.fromkeys(x for x in values if x))


def collect_slack(searcher, target, stable_id, candidate_paths, semantic_tokens):
    # Keep source progress when a later query fails. In particular, a rate
    # limit must not erase a claim already found by an earlier query.
    evidence = {
        "stable_id_hits": [],
        "exact_target_hits": [],
        "path_semantic_hits": [],
    }
    queries = {}

    def plan(query, bucket):
        queries.setdefault(query, []).append(bucket)

    if stable_id:
        plan(stable_id, "stable_id_hits")
    short = target["repo"].split("/", 1)[1]
    n = target["number"]
    for query in (
        f'"{target["repo"]}#{n}"',
        f'"{short}#{n}"',
        f'"{short}" "#{n}"',
    ):
        plan(query, "exact_target_hits")
    for query in _semantic_queries(candidate_paths, semantic_tokens):
        plan(f'"{query}"', "path_semantic_hits")
    coverage = {
        "scope": "planned_queries_only",
        "complete": False,
        "queries": [
            {"query": query, "buckets": buckets, "status": "unread"}
            for query, buckets in queries.items()
        ],
    }
    evidence["query_coverage"] = coverage
    for row in coverage["queries"]:
        try:
            hits = searcher.search(row["query"])
        except Exception as exc:
            row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            # Do not call further Slack queries after a failure. Remaining
            # queries stay explicitly unread, while GitHub can still advance.
            raise SlackCollectionError(exc, evidence) from exc
        row.update(status="complete", hit_count=len(hits))
        for bucket in row["buckets"]:
            evidence[bucket] = _dedupe(evidence[bucket] + hits)
    coverage["complete"] = True
    return evidence


def _owner_snapshot(github, repo):
    meta = github.rest(f"/repos/{repo}")
    branch = meta.get("default_branch") or "main"
    b = github.rest(f"/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}")
    commit = b.get("commit") or {}
    head = commit.get("sha")
    tree_sha = ((commit.get("commit") or {}).get("tree") or {}).get("sha")
    if not head or not tree_sha:
        raise EvidenceError(
            f"owner branch snapshot missing head/tree for {repo}:{branch}"
        )
    tree = github.rest(f"/repos/{repo}/git/trees/{tree_sha}", {"recursive": "1"})
    if tree.get("truncated"):
        raise EvidenceError(f"owner tree for {repo}:{branch} was truncated")
    blobs = {
        x["path"]: x["sha"]
        for x in tree.get("tree") or []
        if x.get("type") == "blob" and x.get("path") and x.get("sha")
    }
    return (
        {
            "repo": repo,
            "default_branch": branch,
            "head_sha": head,
            "tree_sha": tree_sha,
            "tree_blob_count": len(blobs),
        },
        blobs,
    )


def _pr_files(github, repo, number):
    files = []
    for page in range(1, MAX_PR_FILE_PAGES + 1):
        batch = github.rest(
            f"/repos/{repo}/pulls/{number}/files",
            {"per_page": 100, "page": page},
        )
        if not isinstance(batch, list):
            raise EvidenceError(f"non-list pull file inventory for {repo}#{number}")
        files += [
            {
                "path": x.get("filename"),
                "previous_path": x.get("previous_filename"),
                "status": x.get("status"),
                "blob_oid": x.get("sha"),
            }
            for x in batch
            if isinstance(x, dict)
        ]
        if len(batch) < 100:
            return files
    raise EvidenceError(
        f"pull file inventory exceeded {MAX_PR_FILE_PAGES * 100} rows for "
        f"{repo}#{number}"
    )


def _pull(github, repo, number):
    pr = github.rest(f"/repos/{repo}/pulls/{number}")
    files = _pr_files(github, repo, number)
    return {
        "kind": "pull",
        "repo": repo,
        "number": number,
        "state": pr.get("state"),
        "title": pr.get("title"),
        "html_url": pr.get("html_url"),
        "head_sha": (pr.get("head") or {}).get("sha"),
        "base_sha": (pr.get("base") or {}).get("sha"),
        "changed_files": files,
    }


def _issue(github, repo, number):
    issue = github.rest(f"/repos/{repo}/issues/{number}")
    if not isinstance(issue, dict) or "pull_request" in issue:
        raise EvidenceError(
            f"{repo}#{number} is not an ordinary issue; PR evidence must be collected"
        )
    cross = []
    for page in range(1, MAX_PR_FILE_PAGES + 1):
        batch = github.rest(
            f"/repos/{repo}/issues/{number}/timeline",
            {"per_page": 100, "page": page},
        )
        if not isinstance(batch, list):
            raise EvidenceError(f"non-list issue timeline for {repo}#{number}")
        for event in batch:
            if not isinstance(event, dict) or event.get("event") != "cross-referenced":
                continue
            source = event.get("source") if isinstance(event.get("source"), dict) else {}
            item = source.get("issue") if isinstance(source.get("issue"), dict) else {}
            if not isinstance(item.get("pull_request"), dict):
                continue
            html = str(item.get("html_url") or "")
            match = re.match(
                r"^https://github\.com/([^/]+/[^/]+)/pull/(\d+)(?:[/?#].*)?$",
                html,
                re.I,
            )
            if match:
                cross.append(
                    {
                        "repo": match.group(1),
                        "number": int(match.group(2)),
                        "state": str(item.get("state") or "").lower(),
                        "html_url": html,
                    }
                )
        if len(batch) < 100:
            break
    else:
        raise EvidenceError(
            f"issue timeline exceeded {MAX_PR_FILE_PAGES * 100} rows for "
            f"{repo}#{number}"
        )
    raw_assignees = issue.get("assignees") or []
    if not isinstance(raw_assignees, list):
        raise EvidenceError(f"issue assignees must be a list for {repo}#{number}")
    assignees = []
    for assignee in raw_assignees:
        login = assignee.get("login") if isinstance(assignee, dict) else None
        if not isinstance(login, str) or not login.strip():
            raise EvidenceError(f"issue assignee lacks login for {repo}#{number}")
        assignees.append(login.strip())
    return {
        "kind": "issue",
        "repo": repo,
        "number": number,
        "state": issue.get("state"),
        "title": issue.get("title"),
        "html_url": issue.get("html_url"),
        "head_sha": None,
        "changed_files": [],
        "assignees": assignees,
        "cross_referenced_prs": cross,
    }


def collect_github(github, owner_fork, target, candidate_paths):
    owner, owner_blobs = _owner_snapshot(github, owner_fork)
    if target.get("kind") == "pull":
        upstream = _pull(github, target["repo"], target["number"])
    elif target.get("kind") == "issue":
        upstream = _issue(github, target["repo"], target["number"])
    else:
        try:
            upstream = _pull(github, target["repo"], target["number"])
        except Exception as pull_error:
            try:
                upstream = _issue(github, target["repo"], target["number"])
            except Exception as issue_error:
                raise EvidenceError(
                    f"target could not be read as pull ({pull_error}) or "
                    f"issue ({issue_error})"
                ) from issue_error

    comparisons = []
    if upstream["kind"] == "pull":
        wanted = set(candidate_paths)
        changed = upstream.get("changed_files") or []
        relevant = [
            x for x in changed if not wanted or x.get("path") in wanted
        ]
        if wanted:
            present = {x.get("path") for x in relevant}
            for path in sorted(wanted - present):
                comparisons.append(
                    {
                        "path": path,
                        "upstream_status": "not_in_pr",
                        "upstream_blob_oid": None,
                        "owner_blob_oid": owner_blobs.get(path),
                        "comparable": False,
                        "match": False,
                        "reason": "candidate path is not in upstream PR changed files",
                    }
                )
        for item in relevant:
            path, status = item.get("path"), item.get("status")
            previous_path = item.get("previous_path") if status == "renamed" else None
            owner_oid = owner_blobs.get(path)
            previous_owner_oid = owner_blobs.get(previous_path) if previous_path else None
            donor_oid = None if status == "removed" else item.get("blob_oid")
            if status == "removed":
                comparable = True
                match = owner_oid is None
            elif status == "renamed":
                comparable = bool(donor_oid) and bool(previous_path)
                match = (
                    comparable
                    and donor_oid == owner_oid
                    and previous_owner_oid is None
                )
            else:
                comparable = bool(donor_oid)
                match = comparable and donor_oid == owner_oid
            comparisons.append(
                {
                    "path": path,
                    "previous_path": previous_path,
                    "upstream_status": status,
                    "upstream_blob_oid": donor_oid,
                    "owner_blob_oid": owner_oid,
                    "previous_owner_blob_oid": previous_owner_oid,
                    "comparable": bool(comparable),
                    "match": bool(match),
                }
            )
    return owner, upstream, comparisons


def _references_target(text, target):
    lowered = str(text or "").lower()
    repo = target["repo"].lower()
    n = target["number"]
    needles = (
        f"{repo}#{n}",
        f"https://github.com/{repo}/pull/{n}",
        f"https://github.com/{repo}/pulls/{n}",
        f"https://github.com/{repo}/issue/{n}",
        f"https://github.com/{repo}/issues/{n}",
    )
    # Neither an embedded repository name nor a longer issue number is exact.
    return any(
        re.search(r"(?<![\w./-])" + re.escape(needle) + r"(?![\w-])", lowered)
        for needle in needles
    )


def collect_owner_pr_census(
    github, owner_fork, target, stable_id, candidate_paths, semantic_tokens, upstream
):
    hits = []
    open_count = 0
    wanted_paths = set(candidate_paths)
    stable = str(stable_id or "").strip().lower()
    semantics = [str(x).strip().lower() for x in semantic_tokens if str(x).strip()]

    cross_refs = set()
    for item in upstream.get("cross_referenced_prs") or []:
        if (
            isinstance(item, dict)
            and str(item.get("repo") or "").lower() == owner_fork.lower()
            and str(item.get("state") or "").lower() == "open"
            and type(item.get("number")) is int
        ):
            cross_refs.add(item["number"])

    for page in range(1, MAX_OWNER_PR_PAGES + 1):
        batch = github.rest(
            f"/repos/{owner_fork}/pulls",
            {"state": "open", "per_page": 100, "page": page},
        )
        if not isinstance(batch, list):
            raise EvidenceError("owner open-PR census returned non-list payload")
        for pr in batch:
            if not isinstance(pr, dict) or type(pr.get("number")) is not int:
                continue
            open_count += 1
            number = pr["number"]
            text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
            lowered = text.lower()
            reasons = []
            exact = False
            if stable and stable in lowered:
                reasons.append("stable_id")
                exact = True
            if _references_target(text, target) or number in cross_refs:
                reasons.append("exact_target")
                exact = True

            shared_paths = []
            if wanted_paths:
                files = _pr_files(github, owner_fork, number)
                paths = {str(x.get("path")) for x in files if x.get("path")}
                shared_paths = sorted(wanted_paths & paths)
                if shared_paths:
                    reasons.append("path_overlap")

            semantic_hits = sorted(
                token for token in semantics if token and token in lowered
            )
            if semantic_hits:
                reasons.append("semantic_overlap")

            if reasons:
                hits.append(
                    {
                        "number": number,
                        "html_url": pr.get("html_url"),
                        "head_sha": (pr.get("head") or {}).get("sha"),
                        "strength": "exact" if exact else "overlap",
                        "reasons": reasons,
                        "shared_paths": shared_paths,
                        "semantic_tokens": semantic_hits,
                    }
                )
        if len(batch) < 100:
            return {"complete": True, "open_pr_count": open_count, "hits": hits}
    raise EvidenceError(
        f"owner open-PR census exceeded {MAX_OWNER_PR_PAGES * 100} rows"
    )


def collect_report(
    owner_fork,
    target_value,
    stable_id,
    candidate_paths,
    semantic_tokens,
    github,
    slack_searcher,
):
    target = parse_target(target_value)
    errors = []
    slack = {
        "stable_id_hits": [],
        "exact_target_hits": [],
        "path_semantic_hits": [],
    }
    owner = {}
    upstream = {
        "kind": None,
        "repo": target["repo"],
        "number": target["number"],
    }
    comparisons = []
    census = {"complete": False, "open_pr_count": None, "hits": []}
    github_complete = False

    try:
        slack = collect_slack(
            slack_searcher, target, stable_id, candidate_paths, semantic_tokens
        )
    except SlackCollectionError as exc:
        slack = exc.evidence
        errors.append(f"slack: {exc.error_type}: {exc}")
    except Exception as exc:
        errors.append(f"slack: {exc.__class__.__name__}: {exc}")
    try:
        owner, upstream, comparisons = collect_github(
            github, owner_fork, target, candidate_paths
        )
        github_complete = True
    except Exception as exc:
        errors.append(f"github: {exc.__class__.__name__}: {exc}")
    if github_complete:
        try:
            census = collect_owner_pr_census(
                github,
                owner_fork,
                target,
                stable_id,
                candidate_paths,
                semantic_tokens,
                upstream,
            )
        except Exception as exc:
            errors.append(f"owner_pr_census: {exc.__class__.__name__}: {exc}")

    return finalize(
        {
            "input": {
                "owner_fork": owner_fork,
                "upstream_pr_or_issue": target_value,
                "stable_id": stable_id,
                "candidate_paths": list(candidate_paths),
                "semantic_tokens": list(semantic_tokens),
            },
            "slack": slack,
            "owner": owner,
            "upstream": upstream,
            "owner_pr_census": census,
            "blob_comparisons": comparisons,
            "errors": errors,
        }
    )


def render_text(report):
    lines = [
        f"Decision: {report['decision']}",
        "Branch writes allowed: "
        + ("YES" if report["branch_write_allowed"] else "NO"),
        f"Exit code: {report['exit_code']}",
    ]
    if report.get("errors"):
        lines += ["Evidence errors:"] + [f"  - {x}" for x in report["errors"]]
    lines.append("Slack evidence:")
    for bucket in (
        "stable_id_hits",
        "exact_target_hits",
        "path_semantic_hits",
    ):
        hits = (report.get("slack") or {}).get(bucket) or []
        lines.append(f"  {bucket}: {len(hits)}")
        for hit in hits[:10]:
            parts = [hit.get("channel"), hit.get("ts"), hit.get("text")]
            lines.append(
                "    - "
                + " | ".join(str(x) for x in parts if x)[:500]
            )
    coverage = (report.get("slack") or {}).get("query_coverage")
    if isinstance(coverage, dict):
        queries = coverage.get("queries") or []
        lines.append(
            "Slack query coverage: "
            f"complete={coverage.get('complete')} "
            f"completed={sum(row.get('status') == 'complete' for row in queries)} "
            f"planned={len(queries)}"
        )
        for row in queries:
            if row.get("status") != "complete":
                lines.append(f"  {row.get('status')}: {row.get('query')}")
    census = _owner_census(report)
    lines.append(
        "Owner PR census: "
        f"complete={census.get('complete')} "
        f"open={census.get('open_pr_count')} "
        f"hits={len(census.get('hits') or [])}"
    )
    for hit in (census.get("hits") or [])[:10]:
        lines.append(
            f"  PR #{hit.get('number')} strength={hit.get('strength')} "
            f"reasons={','.join(hit.get('reasons') or [])}"
        )
    owner, upstream = report.get("owner") or {}, report.get("upstream") or {}
    lines.append(
        "Owner snapshot: "
        + (
            f"{owner.get('repo')} {owner.get('default_branch')}@"
            f"{owner.get('head_sha')} tree={owner.get('tree_sha')}"
            if owner
            else "unavailable"
        )
    )
    lines.append(
        f"Upstream snapshot: {upstream.get('kind')} {upstream.get('repo')}#"
        f"{upstream.get('number')} state={upstream.get('state')} "
        f"head={upstream.get('head_sha')} "
        f"changed={len(upstream.get('changed_files') or [])}"
    )
    if upstream.get("kind") == "issue":
        assignees = upstream.get("assignees") or []
        open_cross_refs = [
            item for item in (upstream.get("cross_referenced_prs") or [])
            if isinstance(item, dict)
            and str(item.get("state") or "").strip().lower() == "open"
        ]
        lines.append(
            f"Issue collision evidence: assignees={len(assignees)} "
            f"open_cross_referenced_prs={len(open_cross_refs)}"
        )
    lines.append("Blob comparisons:")
    for item in report.get("blob_comparisons") or []:
        lines.append(
            f"  {item.get('path')}: owner={item.get('owner_blob_oid')} "
            f"upstream={item.get('upstream_blob_oid')} "
            f"status={item.get('upstream_status')} "
            f"match={item.get('match')} comparable={item.get('comparable')}"
        )
    if not report.get("blob_comparisons"):
        lines.append("  (none)")
    return "\n".join(lines)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner-fork")
    p.add_argument("--target")
    p.add_argument("--stable-id")
    p.add_argument("--candidate-path", action="append", default=[])
    p.add_argument("--semantic-token", action="append", default=[])
    p.add_argument("--slack-token", default="")
    p.add_argument(
        "--slack-evidence",
        help="JSON mapping Slack query strings to normalized read-only hits",
    )
    p.add_argument(
        "--offline-report", help="evaluate a collected report without network access"
    )
    p.add_argument("--json", action="store_true", dest="json_output")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.offline_report:
        with open(args.offline_report, encoding="utf-8") as fh:
            report = finalize(json.load(fh))
    else:
        if not args.owner_fork or not args.target:
            raise SystemExit(
                "--owner-fork and --target are required unless --offline-report is used"
            )
        bits = args.owner_fork.strip("/").split("/")
        if len(bits) != 2 or not all(bits):
            raise SystemExit("--owner-fork must be owner/repo")
        github = GitHub(repo=args.owner_fork, token=discover_token())
        if args.slack_evidence:
            with open(args.slack_evidence, encoding="utf-8") as fh:
                evidence = json.load(fh)

            slack = OfflineSlack(evidence)
        else:
            token = (
                args.slack_token
                or os.environ.get("SLACK_USER_TOKEN", "")
                or os.environ.get("SLACK_TOKEN", "")
            )
            slack = SlackSearch(token)
        report = collect_report(
            args.owner_fork,
            args.target,
            args.stable_id,
            args.candidate_path,
            args.semantic_token,
            github,
            slack,
        )
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json_output
        else render_text(report)
    )
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
