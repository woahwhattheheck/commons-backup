#!/usr/bin/env python3
"""repo-pulse: lossless 5-minute change index for Commons, posted to Slack.

The engine is a real file so the regression battery can import it. The
workflow fetches this one file (and its tests) over the API — it does not
clone the ~1GB tree every five minutes.

Load-bearing rules:

* previous_head...current_head is the commit authority. The events feed is
  only for what a diff cannot show, queried with overlap and deduped by
  stable event id.
* Quiet windows follow ``PULSE_REPORT_IDLE``: the owner lane reports every scheduled
  window; opt-out lanes retain the once-an-hour heartbeat.
* Every digest leads with ``from: COMMONS_SLACK_MIRROR`` so slack_ingest
  refuses to mirror it into a board issue (loop safety).
* Evidence is a run artifact at repo-pulse/latest.json, never committed
  back onto main.
* Missing fields are omitted. Never print "no title" or "?".
* Sprint integration is additive: every digest teaches MERGE DEFAULT and
  lists open-PR verdicts CLEAR_TO_MERGE / COMPOSE_AND_MERGE / DEDUPED /
  CONFLICT with SHAs, overlapping paths, blob hashes, and rule ids. The
  exact checker is host/sprint_integration.py. Policy:
  ground/SPRINT_INTEGRATION.json. This does not change CLEAR/ATTENTION/BROKEN.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from commons_publication_policy import require_publication

API = "https://api.github.com"
MIRROR_CLAIM = "COMMONS_SLACK_MIRROR"
UA = "repo-pulse/2.1"
SPRINT_CHECKER = "host/sprint_integration.py"
SPRINT_POLICY = "ground/SPRINT_INTEGRATION.json"
SPRINT_LAW = "ground/SPRINT_INTEGRATION.md"
# Exact Actions artifact from open-repo-backup.yml. The unfiltered
# artifacts collection is large enough for GitHub to answer HTTP 500.
BACKUP_ARTIFACT = "commons-open-repo-backup"
SPRINT_TEACH = (
    "MERGE DEFAULT. Parallel branches are not collisions. "
    "CONFLICT only when same effective code disagrees. "
    "Busy main, stale base, unrelated checks are not stops."
)

# First match wins. Generated board records are not "board/UI".
SURFACES = [
    (
        "generated artifacts",
        (
            "p/",
            "by/",
            "to/",
            "chunks/",
            "excerpts/",
            "conflicts/",
            "posts.json",
            "recent.json",
            "pulse.json",
            "fresh.md",
            "orient.json",
            "sync.json",
            "live.html",
        ),
    ),
    ("Muhlnickel", ("muhl/", "muhlnickel")),
    ("revenue", ("revenue/",)),
    (
        "agents/connectors",
        (
            "integrations/",
            "host/",
            "mesh/",
            "protocol/",
            "actions/",
            "memory/",
            "wake_jobs/",
            "independent_commons_mcp/",
            "commons_mcp.py",
            "slack_ingest.py",
            "harness_wake/",
            "ping/",
        ),
    ),
    ("CI/tests", (".github/",)),
    ("docs/ground", ("ground/", "evidence/", "docs/", "AGENTS.md", "START.md", "ENTRY.md", "WRITING.md")),
    (
        "board/UI",
        (
            "board.js",
            "board_ingest.py",
            "index.html",
            "door.js",
            "carrier.js",
            "reply.js",
            "observatory",
            "visual.",
            "the-world",
        ),
    ),
]
WEB_EXT = (".html", ".js", ".css", ".webmanifest")
DOC_EXT = (".md", ".txt")

EVENT_LABEL = {
    "IssuesEvent": "issues",
    "IssueCommentEvent": "comments",
    "PullRequestEvent": "PRs",
    "PullRequestReviewEvent": "reviews",
    "PullRequestReviewCommentEvent": "review-comments",
    "PushEvent": "pushes",
    "CreateEvent": "creates",
    "DeleteEvent": "deletes",
    "ReleaseEvent": "releases",
    "ForkEvent": "forks",
    "WatchEvent": "stars",
    "GollumEvent": "wiki",
    "CommitCommentEvent": "commit-comments",
    "MemberEvent": "members",
    "PublicEvent": "visibility",
}

# Tests replace GET. Live main() leaves it None and uses urllib.
GET = None
NOTES = []
RATE = {"remaining": None, "limit": None, "truncated": False}


class GitHubRateLimited(RuntimeError):
    """The current read pass must stop without advancing its cursor."""


def reset_io():
    NOTES.clear()
    RATE.clear()
    RATE.update({"remaining": None, "limit": None, "truncated": False})


def surface_of(path):
    path = path or ""
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return "CI/tests"
    for label, keys in SURFACES:
        for key in keys:
            if path == key or path.startswith(key):
                return label
    if path.endswith(WEB_EXT):
        return "board/UI"
    if path.endswith(DOC_EXT):
        return "docs/ground"
    return "other"


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def human_delta(seconds):
    seconds = int(max(seconds, 0))
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        return "%dh%02dm" % (seconds // 3600, (seconds % 3600) // 60)
    return "%dd%02dh" % (seconds // 86400, (seconds % 86400) // 3600)


def short_sha(value):
    value = (value or "").strip()
    return value[:7] if value else None


def first_line(message):
    raw = str(message or "")
    line = raw.split("\n", 1)[0].strip()
    text = " ".join(line.split())
    return text[:72] if text else None


def actor_of(commit):
    login = ((commit.get("author") or {}) or {}).get("login")
    if login:
        return login
    name = ((commit.get("commit") or {}).get("author") or {}).get("name")
    return name or None


def esc(text):
    out = str(text or "")
    out = out.replace("&", "&" + "amp;")
    out = out.replace("<", "&" + "lt;")
    out = out.replace(">", "&" + "gt;")
    return out


def ident(text):
    """Quote a token or GitHub string as an identifier, not pulse prose."""
    return "`%s`" % esc(text).replace("`", "'")


# ---------------------------------------------------------------- http

def _req(url, headers=None, data=None, method=None):
    hdrs = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith(API):
        hdrs["Authorization"] = "Bearer " + token
        hdrs["X-GitHub-Api-Version"] = "2022-11-28"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers, resp.read()


def gh(path, **params):
    if GET is not None:
        return GET(path, **params)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = API + path.format(repo=repo)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        _, headers, body = _req(url)
        remaining = headers.get("X-RateLimit-Remaining") if headers else None
        limit = headers.get("X-RateLimit-Limit") if headers else None
        if remaining is not None:
            try:
                RATE["remaining"] = int(remaining)
                RATE["limit"] = int(limit) if limit is not None else RATE["limit"]
            except (TypeError, ValueError):
                pass
        return json.loads(body.decode("utf-8")), headers
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            headers = exc.headers or {}
            detail = exc.read().decode("utf-8", "replace").lower()
            retry_after = headers.get("Retry-After")
            if (exc.code == 429 or headers.get("X-RateLimit-Remaining") == "0"
                    or retry_after is not None or "rate limit" in detail):
                RATE.update(limited=True, http_status=exc.code,
                            retry_after=retry_after,
                            reset_at=headers.get("X-RateLimit-Reset"))
                if headers.get("X-RateLimit-Remaining") == "0":
                    RATE["remaining"] = 0
                note = "GitHub HTTP %s rate limit on %s" % (exc.code, path.split("?")[0])
                if retry_after is not None:
                    note += "; Retry-After=%s" % retry_after
                if RATE["reset_at"]:
                    note += "; reset=%s" % RATE["reset_at"]
                NOTES.append(note)
                raise GitHubRateLimited(note) from exc
        if exc.code in (403, 404, 409, 422, 451):
            if exc.code == 403:
                NOTES.append("GitHub HTTP 403 on %s" % path.split("?")[0])
            return None, None
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        NOTES.append("network error on %s" % path.split("?")[0])
        return None, None


def count_via_link(path, **params):
    params.setdefault("per_page", 1)
    payload, headers = gh(path, **params)
    if payload is None:
        return None
    link = (headers or {}).get("Link", "") if headers else ""
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link or "")
    if match:
        return int(match.group(1))
    if isinstance(payload, list):
        return len(payload)
    return None


def search_total(query):
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    payload, _ = gh("/search/issues", q="repo:%s %s" % (repo, query), per_page=1)
    if isinstance(payload, dict) and "total_count" in payload:
        return payload["total_count"]
    return None


# ---------------------------------------------------------------- state

def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)


# ---------------------------------------------------------------- events / overlap

def fetch_events(seen_ids, first_run, now, lookback_min=5, max_pages=3, overlap_ids=None):
    """Return unseen events. Dedupe is by stable id so a small overlap cannot
    double-report, and a delayed run cannot miss an id still in the feed."""
    seen = set(seen_ids or [])
    if overlap_ids:
        seen |= set(overlap_ids)
    fresh, all_ids, pages = [], [], 0
    exhausted = False
    truncated = False
    horizon = now - timedelta(minutes=lookback_min)
    for page in range(1, max_pages + 1):
        batch, _ = gh("/repos/{repo}/events", per_page=100, page=page)
        pages = page
        if not batch:
            break
        if not isinstance(batch, list):
            truncated = True
            break
        all_ids.extend(str(e.get("id")) for e in batch if e.get("id") is not None)
        page_all_seen = True
        page_reached_horizon = False
        for event in batch:
            eid = str(event.get("id")) if event.get("id") is not None else None
            if not eid:
                continue
            if eid in seen:
                continue
            page_all_seen = False
            created = parse_iso(event.get("created_at")) or now
            if first_run and created <= horizon:
                # The public event feed is newest-first. Once a first-run page
                # crosses the bounded bootstrap horizon, older pages cannot add
                # eligible events and must not be reported as feed exhaustion.
                page_reached_horizon = True
                continue
            fresh.append(event)
        if page_all_seen or (first_run and page_reached_horizon) or len(batch) < 100:
            break
        if page == max_pages:
            exhausted = not page_all_seen
            truncated = exhausted
    fresh.sort(key=lambda e: int(str(e.get("id") or "0")), reverse=True)
    if truncated:
        RATE["truncated"] = True
        NOTES.append("event feed truncated (page cap %d)" % max_pages)
    return fresh, exhausted, pages, all_ids


def dedupe_event_ids(previous_ids, incoming_ids, cap=1200):
    """Stable ids, newest first, overlap-safe union."""
    out = []
    seen = set()
    for eid in list(incoming_ids or []) + list(previous_ids or []):
        key = str(eid)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= cap:
            break
    return out


# ---------------------------------------------------------------- compare

def parse_commit(raw, files_for_sha=None):
    sha = raw.get("sha") or ""
    title = first_line((raw.get("commit") or {}).get("message"))
    author = actor_of(raw)
    html = raw.get("html_url") or None
    stats = raw.get("stats") or {}
    files = files_for_sha or raw.get("files") or []
    paths = [f.get("filename") for f in files if f.get("filename")]
    adds = stats.get("additions")
    dels = stats.get("deletions")
    if adds is None and files:
        adds = sum(f.get("additions", 0) for f in files)
        dels = sum(f.get("deletions", 0) for f in files)
    parsed = {
        "sha": sha,
        "short": short_sha(sha),
        "title": title,
        "author": author,
        "url": html,
        "adds": adds,
        "dels": dels,
        "paths": paths,
        "pr": None,
    }
    return parsed


def parse_compare(payload):
    blank = {
        "commits": [],
        "files": {},
        "paths": [],
        "total": 0,
        "adds": 0,
        "dels": 0,
        "status": "identical",
        "truncated": False,
        "available": False,
    }
    if not isinstance(payload, dict):
        return dict(blank, status="compare-failed")
    commits_raw = payload.get("commits") or []
    files = payload.get("files") or []
    surfaces = {}
    paths = []
    adds = dels = 0
    for entry in files:
        filename = entry.get("filename") or ""
        if filename:
            paths.append(filename)
        label = surface_of(filename)
        bucket = surfaces.setdefault(label, {"files": 0, "adds": 0, "dels": 0})
        bucket["files"] += 1
        bucket["adds"] += entry.get("additions", 0)
        bucket["dels"] += entry.get("deletions", 0)
        adds += entry.get("additions", 0)
        dels += entry.get("deletions", 0)
    commits = [parse_commit(c) for c in commits_raw]
    total = payload.get("total_commits", len(commits))
    truncated = bool(payload.get("truncated")) or total > len(commits) or len(files) >= 300
    return {
        "commits": commits,
        "files": surfaces,
        "paths": paths,
        "total": total,
        "adds": adds,
        "dels": dels,
        "status": payload.get("status") or "ahead",
        "truncated": truncated,
        "available": True,
    }


def commit_range(previous_head, head):
    blank = parse_compare(None)
    blank["status"] = "identical"
    blank["available"] = False
    if not head:
        return blank
    if not previous_head:
        return dict(blank, status="no-baseline")
    if previous_head == head:
        return dict(blank, available=True, status="identical")
    payload, _ = gh("/repos/{repo}/compare/%s...%s" % (previous_head, head))
    if not isinstance(payload, dict):
        NOTES.append(
            "compare unavailable (%s...%s)"
            % (short_sha(previous_head) or "none", short_sha(head) or "none")
        )
        return dict(blank, status="compare-failed")
    parsed = parse_compare(payload)
    if parsed["truncated"]:
        RATE["truncated"] = True
        NOTES.append("compare truncated at API cap")
    return parsed


def attach_pulls(commits, pulls):
    """Stamp merged/open/closed PR state onto commits when the SHA matches."""
    by_sha = {}
    for pr in pulls or []:
        head_sha = ((pr.get("head") or {}).get("sha")) or ""
        merge_sha = pr.get("merge_commit_sha") or ""
        item = {
            "number": pr.get("number"),
            "title": first_line(pr.get("title")),
            "state": "merged" if pr.get("merged_at") or pr.get("merged") else (pr.get("state") or None),
            "url": pr.get("html_url") or None,
            "user": ((pr.get("user") or {}) or {}).get("login"),
        }
        for sha in (head_sha, merge_sha):
            if sha:
                by_sha[sha] = item
    for commit in commits:
        pr = by_sha.get(commit.get("sha"))
        if pr:
            commit["pr"] = pr
    return commits


def list_open_pulls(payload):
    out = []
    for pr in payload or []:
        number = pr.get("number")
        title = first_line(pr.get("title"))
        url = pr.get("html_url")
        user = ((pr.get("user") or {}) or {}).get("login")
        state = "draft" if pr.get("draft") else (pr.get("state") or "open")
        item = {}
        if number is not None:
            item["number"] = number
        if title:
            item["title"] = title
        if url:
            item["url"] = url
        if user:
            item["user"] = user
        if state:
            item["state"] = state
        if item:
            out.append(item)
    return out


def load_sprint_module():
    try:
        import sprint_integration as si
        return si
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    host = os.path.join(here, "host")
    if os.path.isdir(host) and host not in sys.path:
        sys.path.insert(0, host)
        try:
            import sprint_integration as si
            return si
        except ImportError:
            pass
    return None


def scan_sprint(head):
    """Classify open PRs. Never raises; never changes CLEAR/ATTENTION/BROKEN."""
    repo = os.environ.get("GITHUB_REPOSITORY", "") or "woahwhattheheck/commons"
    policy = "https://github.com/%s/blob/main/%s" % (repo, SPRINT_POLICY)
    law = "https://github.com/%s/blob/main/%s" % (repo, SPRINT_LAW)
    teach_line = "*sprint* %s · <%s|policy> · <%s|law>" % (SPRINT_TEACH, policy, law)
    blank = {
        "teach": SPRINT_TEACH,
        "policy": policy,
        "law": law,
        "pairs": [],
        "prs": [],
        "slack_lines": [teach_line],
        "available": False,
        "verdicts": ["CLEAR_TO_MERGE", "COMPOSE_AND_MERGE", "DEDUPED", "CONFLICT"],
    }
    si = load_sprint_module()
    if si is None or not hasattr(si, "pulse_scan"):
        return blank

    def fetch_json(path, **params):
        mapped = path
        if repo and path.startswith("/repos/" + repo):
            mapped = "/repos/{repo}" + path[len("/repos/" + repo):]
        payload, _ = gh(mapped, **params)
        return payload

    try:
        scan = si.pulse_scan(fetch_json, repo, head)
    except Exception:
        NOTES.append("sprint scan failed")
        return blank
    out = dict(blank)
    out.update(scan or {})
    out["available"] = True
    out["teach"] = SPRINT_TEACH
    out["policy"] = policy
    out["law"] = law
    if not out.get("slack_lines"):
        fmt = getattr(si, "format_slack_lines", None)
        out["slack_lines"] = fmt(out, repo) if callable(fmt) else [teach_line]
    return out


def sprint_lines(ctx):
    sprint = ctx.get("sprint") or {}
    lines = list(sprint.get("slack_lines") or [])
    if lines:
        return lines[:8]
    repo = ctx.get("repo") or os.environ.get("GITHUB_REPOSITORY", "") or "woahwhattheheck/commons"
    policy = "https://github.com/%s/blob/main/%s" % (repo, SPRINT_POLICY)
    law = "https://github.com/%s/blob/main/%s" % (repo, SPRINT_LAW)
    return ["*sprint* %s · <%s|policy> · <%s|law>" % (SPRINT_TEACH, policy, law)]


# ---------------------------------------------------------------- health / backup / pages

def parse_check_runs(payload):
    out = {"checks": {}, "failing": [], "pending": 0}
    runs = (payload or {}).get("check_runs") if isinstance(payload, dict) else []
    for run in runs or []:
        status = run.get("status")
        if status != "completed":
            out["pending"] += 1
            continue
        conclusion = run.get("conclusion")
        if not conclusion:
            continue
        out["checks"][conclusion] = out["checks"].get(conclusion, 0) + 1
        if conclusion in ("failure", "timed_out", "action_required"):
            name = run.get("name") or None
            url = run.get("html_url") or run.get("details_url") or None
            suite = run.get("check_suite") or {}
            app = (run.get("app") or {}).get("name") or None
            workflow = suite.get("head_branch") and None
            # Prefer the GitHub Actions job name; keep the app as a qualifier.
            label = name or app
            if not label:
                continue
            item = {"name": label, "conclusion": conclusion}
            if url:
                item["url"] = url
            if app and app != label:
                item["workflow"] = app
            out["failing"].append(item)
    return out


def parse_pages(build, head):
    if not isinstance(build, dict) or not build:
        return {"pages": None, "pages_drift": False}
    sha = build.get("commit") or ""
    url = build.get("url") or build.get("html_url") or None
    pages = {"status": build.get("status") or None, "sha": short_sha(sha), "full_sha": sha or None}
    if url:
        pages["url"] = url
    drift = bool(sha) and bool(head) and sha != head
    return {"pages": pages, "pages_drift": drift}


def parse_backup_age(artifacts, now):
    """Newest verified backup among Actions artifacts. Omit if none."""
    newest = None
    for art in artifacts or []:
        name = (art.get("name") or "").lower()
        if "backup" not in name and "bundle" not in name:
            continue
        if art.get("expired"):
            continue
        created = parse_iso(art.get("created_at") or art.get("updated_at"))
        if not created:
            continue
        if newest is None or created > newest["created"]:
            item = {
                "name": art.get("name"),
                "created": created,
                "age_seconds": int((now - created).total_seconds()),
            }
            url = art.get("archive_download_url") or art.get("url")
            if url:
                item["url"] = url
            if art.get("id") is not None:
                item["id"] = art.get("id")
            newest = item
    return newest


def classify_status(health, gaps, exhausted, settings, backup):
    if health.get("failing"):
        return "BROKEN"
    backup_stale = False
    if backup and backup.get("age_seconds", 0) > 36 * 3600:
        backup_stale = True
    if gaps or health.get("pending") or health.get("pages_drift") or exhausted or settings or backup_stale:
        return "ATTENTION"
    return "CLEAR"


# ---------------------------------------------------------------- gaps / velocity / post decision

def event_gaps(events, prev_snapshot, snapshot):
    gaps = []
    if not prev_snapshot:
        return gaps

    def moved_without(counter, event_type, action, label):
        before = prev_snapshot.get(counter)
        after = snapshot.get(counter)
        if not isinstance(before, int) or not isinstance(after, int):
            return
        delta = after - before
        if delta <= 0:
            return
        observed = 0
        for event in events or []:
            if event.get("type") != event_type:
                continue
            if action and (event.get("payload") or {}).get("action") != action:
                continue
            observed += 1
        missing = delta - observed
        if missing > 0:
            gaps.append("EVENT_GAP +%d %s" % (missing, label))

    moved_without("issues_total", "IssuesEvent", "opened", "issues")
    moved_without("prs_total", "PullRequestEvent", "opened", "PRs")
    return gaps


def velocity(history, events_now, commits_now, now):
    cutoff_1h = now - timedelta(hours=1)
    cutoff_24h = now - timedelta(hours=24)
    ev1 = cm1 = ev24 = cm24 = 0
    for row in history or []:
        stamp, evs, cms = row[0], row[1], row[2]
        when = parse_iso(stamp)
        if not when:
            continue
        if when > cutoff_24h:
            ev24 += evs
            cm24 += cms
        if when > cutoff_1h:
            ev1 += evs
            cm1 += cms
    return {
        "ev_5m": events_now,
        "ev_1h": ev1 + events_now,
        "ev_24h": ev24 + events_now,
        "cm_5m": commits_now,
        "cm_1h": cm1 + commits_now,
        "cm_24h": cm24 + commits_now,
        "samples": len(history or []),
    }


def window_changed(events, diff, gaps, health, settings):
    return bool(
        events
        or (diff or {}).get("total")
        or gaps
        or (health or {}).get("failing")
        or settings
    )


def decide_post(changed, last_post_at, now, heartbeat_min=60, report_idle=False):
    """Post every quiet window when requested; otherwise keep an hourly heartbeat."""
    if changed:
        return True, "changed"
    if report_idle:
        return True, "idle-forced"
    if last_post_at is None:
        return True, "first-run"
    if (now - last_post_at) >= timedelta(minutes=heartbeat_min):
        return True, "heartbeat"
    return False, "quiet"


# ---------------------------------------------------------------- render

def commit_line(repo, commit):
    parts = []
    short = commit.get("short")
    url = commit.get("url") or (
        "https://github.com/%s/commit/%s" % (repo, commit.get("sha")) if commit.get("sha") else None
    )
    if short and url:
        parts.append("<%s|`%s`>" % (url, short))
    elif short:
        parts.append("`%s`" % short)
    if commit.get("title"):
        parts.append(ident(commit["title"]))
    if commit.get("author"):
        parts.append("— `%s`" % esc(commit["author"]))
    extras = []
    if isinstance(commit.get("adds"), int) and isinstance(commit.get("dels"), int):
        extras.append("+%d/-%d" % (commit["adds"], commit["dels"]))
    pr = commit.get("pr") or {}
    if pr.get("number") is not None:
        label = ["#%s" % pr["number"]]
        if pr.get("state"):
            label.append(pr["state"])
        if pr.get("title"):
            label.append(ident(pr["title"]))
        shown = " ".join(label)
        if pr.get("url"):
            extras.append("<%s|%s>" % (pr["url"], shown))
        else:
            extras.append(shown)
    if extras:
        parts.append(" ".join(extras))
    surfaces = []
    seen = []
    for path in commit.get("paths") or []:
        label = surface_of(path)
        if label not in seen:
            seen.append(label)
            surfaces.append(label)
    if surfaces:
        parts.append("· " + ", ".join(surfaces[:4]))
    if not parts:
        return None
    return "• " + " ".join(parts)


def render(ctx):
    events, diff, hp, snap = ctx["events"], ctx["diff"], ctx["health"], ctx["snapshot"]
    vel, gaps = ctx["velocity"], ctx["gaps"]
    settings = ctx.get("settings") or []
    repo = ctx.get("repo") or os.environ.get("GITHUB_REPOSITORY", "")
    now = ctx["now"]
    status = ctx["status"]
    head_short = short_sha(snap.get("head"))
    prev_short = short_sha(ctx.get("previous_head"))
    evidence = ctx.get("evidence_url") or ctx.get("run_url")

    L = [
        "from: %s" % MIRROR_CLAIM,
        "to: TABLE",
        "id: repo-pulse-%s" % now.strftime("%Y%m%dT%H%M%SZ"),
        "carrier: github-actions/repo-pulse",
        "",
    ]

    span = "%s→%s" % (str(ctx.get("window_from") or "")[11:19], now.strftime("%H:%M:%S"))
    quiet = ctx.get("quiet_for")
    lead = [ident(status)]
    if repo:
        lead.append("`%s`" % repo.split("/")[-1])
    if span.strip("→"):
        lead.append(span)
    if quiet:
        lead.append("heartbeat" if ctx.get("reason") == "heartbeat" else "no changes")
        lead.append("quiet %s" % quiet)
        if head_short:
            lead.append("main `%s`" % head_short)
    else:
        lead.append("%d events" % len(events))
        if diff.get("total"):
            bits = []
            if prev_short and head_short:
                bits.append("main `%s`→`%s`" % (prev_short, head_short))
            elif head_short:
                bits.append("main `%s`" % head_short)
            bits.append("+%d commits" % diff["total"])
            bits.append("+%d/-%d" % (diff.get("adds", 0), diff.get("dels", 0)))
            lead.append(" ".join(bits))
        elif head_short:
            lead.append("main `%s` unchanged" % head_short)
    L.append(" · ".join(lead))

    if hp.get("failing"):
        for job in hp["failing"][:3]:
            name = job.get("name")
            if not name:
                continue
            if job.get("workflow"):
                name = "%s / %s" % (job["workflow"], name)
            if job.get("url"):
                L.append(":red_circle: %s <%s|job log>" % (ident(name), job["url"]))
            else:
                L.append(":red_circle: %s" % ident(name))
    for gap in gaps:
        L.append(":warning: `%s`" % gap)
    pages = hp.get("pages") or {}
    if hp.get("pages_drift") and pages:
        bits = [":warning: pages"]
        if pages.get("sha"):
            bits.append("built `%s`" % pages["sha"])
        if head_short:
            bits.append("main `%s`" % head_short)
        if pages.get("url"):
            bits.append("<%s|build>" % pages["url"])
        L.append(" ".join(bits))
    if ctx.get("exhausted"):
        L.append(":warning: event feed truncated — window exceeds retained pages")
    for line in settings[:4]:
        L.append(":gear: %s" % line)

    backup = ctx.get("backup")
    if backup:
        age = human_delta(backup.get("age_seconds", 0))
        bits = ["*backup* verified %s ago" % age]
        if backup.get("url"):
            bits.append("<%s|artifact>" % backup["url"])
        elif backup.get("name"):
            bits.append("`%s`" % backup["name"])
        L.append(" ".join(bits))

    open_prs = ctx.get("open_prs") or []
    if open_prs:
        shown = []
        for pr in open_prs[:5]:
            label = []
            if pr.get("number") is not None:
                label.append("#%s" % pr["number"])
            if pr.get("title"):
                label.append(ident(pr["title"]))
            if pr.get("state") and pr["state"] not in ("open",):
                label.append("(%s)" % pr["state"])
            text = " ".join(label)
            if not text:
                continue
            if pr.get("url"):
                shown.append("<%s|%s>" % (pr["url"], text))
            else:
                shown.append(text)
        if shown:
            L.append("*open PRs* " + " · ".join(shown))

    for line in sprint_lines(ctx):
        L.append(line)

    if diff.get("files"):
        top = sorted(diff["files"].items(), key=lambda kv: -(kv[1]["adds"] + kv[1]["dels"]))[:5]
        L.append(
            "*surfaces* "
            + " · ".join(
                "%s %df +%d/-%d" % (name, b["files"], b["adds"], b["dels"]) for name, b in top
            )
        )

    L.append(
        "*velocity* ev %d/5m %d/1h %d/24h · commits %d/5m %d/1h %d/24h"
        % (
            vel.get("ev_5m", 0),
            vel.get("ev_1h", 0),
            vel.get("ev_24h", 0),
            vel.get("cm_5m", 0),
            vel.get("cm_1h", 0),
            vel.get("cm_24h", 0),
        )
    )

    if events:
        by_type = {}
        actors = {}
        for event in events:
            by_type[event.get("type") or "unknown"] = by_type.get(event.get("type") or "unknown", 0) + 1
            login = ((event.get("actor") or {}) or {}).get("login")
            if login:
                actors[login] = actors.get(login, 0) + 1
        L.append(
            "*events* "
            + " · ".join(
                "%s %d" % (EVENT_LABEL.get(k, k.replace("Event", "").lower()), v)
                for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])
            )
        )
        if actors:
            L.append(
                "*who* "
                + " · ".join(
                    "`%s` %d" % (esc(a), n)
                    for a, n in sorted(actors.items(), key=lambda kv: -kv[1])[:5]
                )
            )

    if diff.get("commits"):
        L.append("*commits*")
        max_lines = int(ctx.get("max_commit_lines") or 8)
        shown = 0
        for commit in diff["commits"]:
            line = commit_line(repo, commit)
            if not line:
                continue
            L.append(line)
            shown += 1
            if shown >= max_lines:
                break
        rest = diff.get("total", 0) - shown
        if rest > 0 and evidence:
            L.append("• …%d more in <%s|the run evidence>" % (rest, evidence))

    checks = " ".join("%s %d" % (ident(k), v) for k, v in sorted((hp.get("checks") or {}).items()))
    check_bits = []
    if checks:
        check_bits.append(checks)
    if hp.get("pending"):
        check_bits.append("%d pending" % hp["pending"])
    if check_bits:
        L.append("*checks* " + " · ".join(check_bits))

    coverage = []
    coverage.append("window %s" % (ctx.get("window_from") or "unset"))
    if prev_short or head_short:
        coverage.append("range %s → %s" % (prev_short or "none", head_short or "none"))
    coverage.append("%d events" % len(events))
    coverage.append("cursor %s" % (ctx.get("cursor") or (ctx.get("window_from") or "unset")))
    coverage.append("%d feed page(s)" % ctx.get("pages", 0))
    if RATE.get("remaining") is not None:
        if RATE.get("limit") is not None:
            coverage.append("rate-limit %s/%s" % (RATE["remaining"], RATE["limit"]))
        else:
            coverage.append("rate-limit remaining %s" % RATE["remaining"])
    if RATE.get("truncated") or diff.get("truncated"):
        coverage.append("truncated")
    if not diff.get("available"):
        coverage.append("compare %s" % (diff.get("status") or "n/a"))
    coverage.extend(NOTES[:2])
    if ctx.get("reason"):
        coverage.append("emit %s" % ctx["reason"])
    tail = "facts: " + " · ".join(coverage)
    if evidence:
        tail += " · <%s|evidence>" % evidence
    L.append("_%s_" % tail)
    L.append("_inference: %s is the action lead; EVENT_GAP is an accounting remainder, not a missing SHA._" % ident(status))
    return "\n".join(L)


# ---------------------------------------------------------------- slack / evidence

def post_slack(text, webhook, bot_token, channel, summary_path, dry_run=False):
    require_publication(text)
    if dry_run:
        print(text)
        return "dry-run"
    if webhook:
        data = json.dumps({"text": text, "unfurl_links": False, "unfurl_media": False}).encode("utf-8")
        status, _, body = _req(webhook, headers={"Content-Type": "application/json"}, data=data, method="POST")
        if status != 200:
            raise SystemExit("slack webhook failed: %s %s" % (status, body[:200]))
        return "webhook"
    if bot_token and channel:
        data = json.dumps({"channel": channel, "text": text, "unfurl_links": False}).encode("utf-8")
        _, _, body = _req(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer " + bot_token,
            },
            data=data,
            method="POST",
        )
        payload = json.loads(body.decode("utf-8"))
        if not payload.get("ok"):
            raise SystemExit("slack api failed: %s" % payload.get("error"))
        return "bot"
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("### repo-pulse (no Slack destination configured)\n\n```\n%s\n```\n" % text)
    print(
        "NOTE: no SLACK_WEBHOOK_URL / SLACK_BOT_TOKEN set — digest written to the job "
        "summary instead. Add the secret and it starts posting to Slack."
    )
    return "summary"


def write_evidence(path, payload):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str)


# ---------------------------------------------------------------- snapshot / orchestration

SETTING_LABELS = {
    "default_branch": "default branch",
    "visibility": "visibility",
    "archived": "archived",
    "description": "description",
    "homepage": "homepage",
    "topics": "topics",
    "has_issues": "issues enabled",
    "has_wiki": "wiki enabled",
    "has_pages": "pages enabled",
    "has_discussions": "discussions enabled",
}


def settings_delta(old, new):
    out = []
    for key, label in SETTING_LABELS.items():
        before, after = (old or {}).get(key), (new or {}).get(key)
        if before is not None and before != after:
            out.append("%s %r → %r" % (label, before, after))
    return out


def repo_snapshot():
    repo, _ = gh("/repos/{repo}")
    if repo is None:
        return {}
    default_branch = repo.get("default_branch") or "main"
    head = ""
    ref, _ = gh("/repos/{repo}/commits/%s" % default_branch)
    if isinstance(ref, dict):
        head = ref.get("sha") or ""
    issues_total = search_total("is:issue")
    issues_open = search_total("is:issue is:open")
    prs_total = search_total("is:pr")
    prs_merged = search_total("is:pr is:merged")
    prs_open = count_via_link("/repos/{repo}/pulls", state="open")

    def closed(total, *parts):
        if not isinstance(total, int):
            return None
        acc = total
        for part in parts:
            if not isinstance(part, int):
                return None
            acc -= part
        return acc

    return {
        "head": head,
        "default_branch": default_branch,
        "commits_total": count_via_link("/repos/{repo}/commits"),
        "issues_total": issues_total,
        "issues_open": issues_open,
        "issues_closed": closed(issues_total, issues_open),
        "prs_total": prs_total,
        "prs_open": prs_open,
        "prs_merged": prs_merged,
        "prs_closed_unmerged": closed(prs_total, prs_merged, prs_open),
        "branches": count_via_link("/repos/{repo}/branches"),
        "tags": count_via_link("/repos/{repo}/tags"),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "visibility": repo.get("visibility", ""),
        "archived": bool(repo.get("archived")),
        "description": repo.get("description") or "",
        "homepage": repo.get("homepage") or "",
        "topics": sorted(repo.get("topics") or []),
        "has_issues": bool(repo.get("has_issues")),
        "has_wiki": bool(repo.get("has_wiki")),
        "has_pages": bool(repo.get("has_pages")),
        "has_discussions": bool(repo.get("has_discussions")),
    }


def health(head):
    out = {"checks": {}, "failing": [], "pending": 0, "pages": None, "pages_drift": False}
    if not head:
        return out
    payload, _ = gh("/repos/{repo}/commits/%s/check-runs" % head, per_page=100)
    parsed = parse_check_runs(payload if isinstance(payload, dict) else {})
    out.update(parsed)
    build, _ = gh("/repos/{repo}/pages/builds/latest")
    pages = parse_pages(build if isinstance(build, dict) else None, head)
    out.update(pages)
    return out


def newest_backup(now):
    """Age of the named open-repo backup.

    Ask for that artifact by name. One transient HTTP 5xx is retried.
    A second 5xx is recorded and the age is omitted so the digest still posts.
    Other HTTP statuses still propagate.
    """
    payload = None
    for attempt in range(2):
        try:
            payload, _ = gh(
                "/repos/{repo}/actions/artifacts",
                name=BACKUP_ARTIFACT,
                per_page=20,
            )
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504):
                raise
            if attempt:
                NOTES.append("backup probe HTTP %s" % exc.code)
                return None
    artifacts = (payload or {}).get("artifacts") if isinstance(payload, dict) else []
    return parse_backup_age(artifacts, now)


def build_context(state, now=None, lookback_min=5):
    now = now or now_utc()
    first_run = not state.get("seen_ids")
    events, exhausted, pages, all_ids = fetch_events(
        state.get("seen_ids"), first_run, now, lookback_min=lookback_min
    )
    snapshot = repo_snapshot()
    previous_head = state.get("previous_head") or ""
    diff = commit_range(previous_head, snapshot.get("head") or "")
    pulls_payload, _ = gh("/repos/{repo}/pulls", state="all", sort="updated", per_page=50)
    attach_pulls(diff.get("commits") or [], pulls_payload if isinstance(pulls_payload, list) else [])
    open_raw, _ = gh("/repos/{repo}/pulls", state="open", per_page=20)
    open_prs = list_open_pulls(open_raw if isinstance(open_raw, list) else [])
    hp = health(snapshot.get("head") or "")
    backup = newest_backup(now)
    prev_snapshot = state.get("snapshot") or {}
    gaps = event_gaps(events, prev_snapshot, snapshot)
    settings = settings_delta(prev_snapshot, snapshot)
    history = state.get("history") or []
    sprint = scan_sprint(snapshot.get("head") or "")
    return {
        "now": now,
        "events": events,
        "exhausted": exhausted,
        "pages": pages,
        "all_ids": all_ids,
        "snapshot": snapshot,
        "prev_snapshot": prev_snapshot,
        "diff": diff,
        "health": hp,
        "backup": backup,
        "open_prs": open_prs,
        "gaps": gaps,
        "settings": settings,
        "previous_head": previous_head,
        "velocity": velocity(history, len(events), diff.get("total") or 0, now),
        "window_from": state.get("last_run_at")
        or iso(now - timedelta(minutes=lookback_min)),
        "cursor": state.get("last_event_at") or state.get("last_run_at"),
        "last_event_at": state.get("last_event_at"),
        "history": history,
        "sprint": sprint,
        "status": classify_status(hp, gaps, exhausted, settings, backup),
    }


def next_state(state, ctx, posted, now):
    newest = ctx["events"][0] if ctx["events"] else None
    lifetime = state.get("lifetime") or {
        "since": now.strftime("%Y-%m-%d"),
        "events": 0,
        "commits": 0,
        "digests": 0,
    }
    lifetime["events"] = lifetime.get("events", 0) + len(ctx["events"])
    lifetime["commits"] = lifetime.get("commits", 0) + int(ctx["diff"].get("total") or 0)
    lifetime["digests"] = lifetime.get("digests", 0) + (1 if posted else 0)
    history = (list(ctx.get("history") or []) + [[iso(now), len(ctx["events"]), int(ctx["diff"].get("total") or 0)]])[-300:]
    seen = dedupe_event_ids(state.get("seen_ids"), ctx.get("all_ids"))
    return {
        "last_run_at": iso(now),
        "last_post_at": iso(now) if posted else state.get("last_post_at"),
        "previous_head": ctx["snapshot"].get("head") or ctx.get("previous_head"),
        "seen_ids": seen,
        "last_event_at": (newest or {}).get("created_at") or state.get("last_event_at"),
        "snapshot": ctx["snapshot"] or ctx.get("prev_snapshot") or {},
        "history": history,
        "lifetime": lifetime,
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    del argv
    reset_io()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is not set")
    state_path = os.environ.get("PULSE_STATE", ".pulse-state.json")
    evidence_path = os.environ.get("PULSE_EVIDENCE", "repo-pulse/latest.json")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = "https://github.com/%s/actions/runs/%s" % (repo, run_id) if run_id else ""
    report_idle = os.environ.get("PULSE_REPORT_IDLE", "false").lower() == "true"
    heartbeat_min = int(os.environ.get("PULSE_IDLE_HEARTBEAT_MINUTES", "60"))
    lookback_min = int(os.environ.get("PULSE_FALLBACK_MINUTES", "5"))
    dry_run = os.environ.get("PULSE_DRY_RUN", "").lower() == "true"
    now = now_utc()

    state = load_state(state_path)
    try:
        ctx = build_context(state, now=now, lookback_min=lookback_min)
    except GitHubRateLimited as exc:
        write_evidence(evidence_path, {
            "generated_at": iso(now), "status": "RATE_LIMITED",
            "reason": "provider_backoff", "rate_limit": dict(RATE),
            "notes": list(NOTES), "cursor": state.get("last_event_at"),
        })
        print("repo-pulse deferred: %s; cursor unchanged" % exc, file=sys.stderr)
        return 2
    ctx["repo"] = repo
    ctx["run_url"] = run_url
    ctx["evidence_url"] = run_url
    ctx["max_commit_lines"] = int(os.environ.get("PULSE_MAX_COMMIT_LINES", "8"))
    changed = window_changed(ctx["events"], ctx["diff"], ctx["gaps"], ctx["health"], ctx["settings"])
    last_post = parse_iso(state.get("last_post_at"))
    should, reason = decide_post(changed, last_post, now, heartbeat_min, report_idle)
    ctx["reason"] = reason
    if not changed:
        last_event = parse_iso(ctx.get("last_event_at"))
        ctx["quiet_for"] = human_delta((now - last_event).total_seconds()) if last_event else "since first run"

    text = render(ctx)
    evidence = {
        "generated_at": iso(now),
        "status": ctx["status"],
        "reason": reason,
        "window_from": ctx["window_from"],
        "cursor": ctx.get("cursor"),
        "range": [ctx.get("previous_head"), ctx["snapshot"].get("head")],
        "from_sha": ctx.get("previous_head"),
        "to_sha": ctx["snapshot"].get("head"),
        "event_count": len(ctx["events"]),
        "pages": ctx["pages"],
        "rate_limit": dict(RATE),
        "notes": list(NOTES),
        "events": ctx["events"],
        "diff": ctx["diff"],
        "health": ctx["health"],
        "backup": {
            k: (iso(v) if isinstance(v, datetime) else v)
            for k, v in (ctx.get("backup") or {}).items()
        },
        "open_prs": ctx.get("open_prs"),
        "sprint": ctx.get("sprint"),
        "gaps": ctx["gaps"],
        "velocity": ctx["velocity"],
        "snapshot": ctx["snapshot"],
        "digest": text,
    }
    write_evidence(evidence_path, evidence)

    posted = None
    if should:
        posted = post_slack(
            text,
            os.environ.get("SLACK_WEBHOOK_URL", "").strip(),
            os.environ.get("SLACK_BOT_TOKEN", "").strip(),
            os.environ.get("SLACK_CHANNEL_ID", "").strip(),
            os.environ.get("GITHUB_STEP_SUMMARY"),
            dry_run=dry_run,
        )
        print("posted via %s: %d events, %d commits (%s)" % (posted, len(ctx["events"]), ctx["diff"].get("total") or 0, reason))
    else:
        print("quiet window, heartbeat not due — nothing posted")

    save_state(state_path, next_state(state, ctx, posted, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
