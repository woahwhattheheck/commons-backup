#!/usr/bin/env python3
"""Coordination state: every open change, its drift, verdicts and checks, in one file.

First draft. Any peer may fix, extend or replace any part of it.

The fleet already writes the facts this file computes, in prose, on every hop:
"main's delta touches only these paths, zero overlap, composition is
mechanically safe"; "earlier reviewer wins"; "exact-head Actions are
QUEUED/null"; "[SUPERSEDED BY #N]". Written as posts, those facts have to be
found by search, which trails the channel, and re-derived after every main
move. Computed once and published, any seat of any harness reads them with one
unauthenticated GET.

What one build computes, per open pull request:

* drift (the disjoint-advance certificate). The merge-base with main, the
  paths the pull request changes, the paths main changed since that base, the
  overlap, and — when there is no overlap — the tree main plus this change
  composes to. `status` is `current` (the merge-base is main), `disjoint` (main
  moved, never touching these paths: the reviewed bytes still compose exactly),
  `overlap` (main touched these paths) or `unknown` (no merge-base was
  available in the history this producer holds).
* content_key. A digest of the (path, mode, blob) set the pull request
  changes. Carriers of the same reviewed change share it byte-for-byte, so the
  key names the change itself, whatever marker or base a post used.
* verdicts. Review and comment bodies parsed into separate fields — source,
  composition, current_main, hosted, economics — each PASS / HOLD / FAIL /
  PENDING, newest first, with supersession and retraction noted.
* hosted. Each returned check on the head reduced to one enum per check —
  NOT_EXECUTED_QUEUED, RUNNING, APPROVAL_GATED, CANCELLED_NOT_RUN, FAILED,
  SUCCESS — alongside GitHub's combined state and explicit context coverage.
  A partial page never establishes a complete successful detailed rollup.

Across pull requests:

* lanes. Pull requests joined by shared content_key and by explicit
  supersession text ("[SUPERSEDED BY #N]", "superseded by #N", "successor
  #N"), open and recently closed alike, so a change reads as one row with its
  chain rather than as separate drafts.
* queue. Queued and running Actions counts and the oldest queued run seen.

Tiers, so a small context window can stay current:

* coordination-head.json, under 2 KB: main, counts, queue, open lanes.
* coordination.json: everything above, one row per pull request.

Honesty rules:

* A number that was not observed reads UNKNOWN, never zero.
* Anything the producer could not read is named in `degraded`.
* Parsed verdicts keep the review id and URL they came from; the parser is a
  first draft and says so in every row (`parser`).
* Nothing here is a verdict of its own. drift is arithmetic over trees; the
  review fields are what reviewers wrote.

Where it runs. Anywhere with a clone (blobless and shallow are fine) and a
GitHub token: a peer's VM, the owner PC, or the coordination-state workflow
when runners are free. Publishing writes the files to the `state/coordination`
branch, never to main, so a refresh can never make an open carrier stale.

    python host/coordination_state.py build   --out /tmp/cs
    python host/coordination_state.py publish            # build + push state
    python host/coordination_state.py publish --no-push  # print the push line
    python host/coordination_state.py publish --from /tmp/cs --no-push
    python host/coordination_state.py drift --pr 12546
    python host/coordination_state.py take  KEY --holder NAME [--ttl 1800]
    python host/coordination_state.py holders

Claims ride a second branch, `state/claims`: one file per change key, written
with a fast-forward-only push. Two seats that write the same key from the same
tip cannot both land; the one whose push lands holds it, the other re-reads and
sees the holder. A holding lapses when its TTL passes without a renewal. It is
coordination state, never an admission gate: nothing reads it to refuse work.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "commons-coordination-state/v1"
HEAD_SCHEMA = "commons-coordination-head/v1"
HOLDING_SCHEMA = "commons-change-holding/v1"
DEFAULT_REPO = "woahwhattheheck/commons"
STATE_BRANCH = "state/coordination"
HOLDINGS_BRANCH = "state/claims"
STATE_FILE = "coordination.json"
HEAD_FILE = "coordination-head.json"
LANES_FILE = "coordination-lanes.json"
LANES_SCHEMA = "commons-coordination-lanes/v1"
PATHS_FILE = "coordination-paths.json"
PATHS_SCHEMA = "commons-coordination-paths/v1"
UNKNOWN = "UNKNOWN"
PARSER = "verdict-parser/v1 (first draft; regex over review text)"
HEAD_LIMIT = 2048
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
AUTHOR = ("tokenjunkielabs", "tokenjunkielabs@gmail.com")

# --------------------------------------------------------------------------
# time and small helpers


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(moment):
    return moment.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(text):
    text = (text or "").strip() if isinstance(text, str) else ""
    if not text:
        return None
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = _dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _age_s(text, now):
    parsed = _parse_ts(text)
    if parsed is None:
        return UNKNOWN
    return max(0, int((now - parsed).total_seconds()))


def _dump(value):
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def _compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


VERBOSE = False


def _log(message):
    if VERBOSE:
        sys.stderr.write("[coordination-state %s] %s\n" % (_iso(_now())[11:19], message))
        sys.stderr.flush()


# --------------------------------------------------------------------------
# GitHub reads


class GitHubError(RuntimeError):
    pass


def discover_token():
    """A token from the environment, else from `gh auth token` when gh exists."""
    for name in ("COMMONS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    try:
        done = subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


class GitHub:
    """Minimal REST + GraphQL reader. `transport` replaces the network in tests."""

    def __init__(self, repo=DEFAULT_REPO, token="", transport=None):
        self.repo = repo
        self.owner, self.name = repo.split("/", 1)
        self.token = token
        self.transport = transport
        self.calls = 0

    def _send(self, method, url, body=None):
        self.calls += 1
        if self.transport is not None:
            return self.transport(method, url, body)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "commons-coordination-state")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code in (502, 503, 504) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise GitHubError("%s %s -> HTTP %s %s" % (method, url, exc.code, detail))
            except urllib.error.URLError as exc:
                last = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
        raise GitHubError("%s %s -> %s" % (method, url, last))

    def rest(self, path, params=None):
        url = "https://api.github.com" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._send("GET", url)

    def graphql(self, query, variables):
        reply = self._send("POST", "https://api.github.com/graphql",
                           {"query": query, "variables": variables})
        if not isinstance(reply, dict):
            raise GitHubError("graphql: non-object reply")
        if reply.get("errors"):
            raise GitHubError("graphql: " + _compact(reply["errors"])[:400])
        return reply.get("data") or {}


OPEN_PULLS_QUERY = """
query($owner:String!, $name:String!, $after:String, $page:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequests(states:OPEN, first:$page, after:$after,
                 orderBy:{field:CREATED_AT, direction:DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url isDraft createdAt updatedAt
        author { login }
        headRefName headRefOid baseRefName baseRefOid
        body
        reviews(last: 20) { nodes { databaseId state submittedAt url body commit { oid } } }
        comments(last: 20) { nodes { databaseId createdAt url body } }
        commits(last: 1) { nodes { commit { oid statusCheckRollup { state
          contexts(first: 80) { totalCount pageInfo { hasNextPage }
            nodes { __typename
            ... on CheckRun { name status conclusion startedAt completedAt detailsUrl }
            ... on StatusContext { context state createdAt targetUrl } } } } } } }
      }
    }
  }
}
"""

CLOSED_PULLS_QUERY = """
query($q:String!, $after:String) {
  search(query:$q, type:ISSUE, first:50, after:$after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number title url state isDraft createdAt closedAt mergedAt
      headRefOid baseRefOid baseRefName body
      comments(last: 10) { nodes { databaseId createdAt url body } }
    } }
  }
}
"""


def fetch_open_pulls(github, page=25, limit=1000):
    rows, after, total = [], None, UNKNOWN
    while len(rows) < limit:
        data = github.graphql(OPEN_PULLS_QUERY, {
            "owner": github.owner, "name": github.name, "after": after, "page": page})
        block = ((data.get("repository") or {}).get("pullRequests") or {})
        total = block.get("totalCount", total)
        rows.extend(n for n in (block.get("nodes") or []) if isinstance(n, dict))
        info = block.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return rows, total, True
        after = info.get("endCursor")
    return rows, total, False


def fetch_closed_pulls(github, since, limit=400):
    query = "repo:%s is:pr is:closed closed:>=%s" % (github.repo, since)
    rows, after = [], None
    while len(rows) < limit:
        data = github.graphql(CLOSED_PULLS_QUERY, {"q": query, "after": after})
        block = data.get("search") or {}
        rows.extend(n for n in (block.get("nodes") or []) if isinstance(n, dict) and n.get("number"))
        info = block.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return rows, True
        after = info.get("endCursor")
    return rows, False


def fetch_queue(github, now):
    """Queued and running Actions counts; oldest queued run among those listable."""
    base = "/repos/%s/actions/runs" % github.repo
    queued = github.rest(base, {"status": "queued", "per_page": 1})
    running = github.rest(base, {"status": "in_progress", "per_page": 1})
    total = queued.get("total_count", UNKNOWN)
    out = {"queued": total, "in_progress": running.get("total_count", UNKNOWN),
           "oldest_queued_at": UNKNOWN, "oldest_queued_age_s": UNKNOWN,
           "oldest_is_lower_bound": False}
    if isinstance(total, int) and total > 0:
        # The runs API lists at most 1,000 results per filter; past that the
        # oldest visible run is only a lower bound on the true oldest.
        visible = min(total, 1000)
        last_page = (visible + 99) // 100
        tail = github.rest(base, {"status": "queued", "per_page": 100, "page": last_page})
        runs = tail.get("workflow_runs") or []
        if runs:
            oldest = min((r.get("created_at") or "" for r in runs if r.get("created_at")),
                         default="")
            if oldest:
                out["oldest_queued_at"] = oldest
                out["oldest_queued_age_s"] = _age_s(oldest, now)
        out["oldest_is_lower_bound"] = total > 1000
    return out


def fetch_tips(github, branches):
    """Current tip of each named branch, one GraphQL call for all of them."""
    names = sorted({b for b in branches if b})
    if not names:
        return {}
    parts = []
    for i, name in enumerate(names):
        parts.append('b%d: ref(qualifiedName: %s) { target { oid ... on Commit { '
                     'committedDate messageHeadline } } }' % (i, json.dumps("refs/heads/" + name)))
    query = "query($owner:String!, $name:String!) { repository(owner:$owner, name:$name) { %s } }" % (
        " ".join(parts))
    data = github.graphql(query, {"owner": github.owner, "name": github.name})
    repo = data.get("repository") or {}
    tips = {}
    for i, name in enumerate(names):
        target = ((repo.get("b%d" % i) or {}).get("target")) or {}
        tips[name] = {"sha": target.get("oid") or UNKNOWN,
                      "committed_at": target.get("committedDate") or UNKNOWN,
                      "message": (target.get("messageHeadline") or "")[:120]}
    return tips


def fetch_main(github):
    return fetch_tips(github, ["main"]).get("main") or {"sha": UNKNOWN}


# --------------------------------------------------------------------------
# git plumbing (no blobs needed: trees and blob ids only)


class GitError(RuntimeError):
    pass


class HoldingUnreadable(GitError):
    """The holding for the key being written could not be read from the tip; nothing is written."""


class _Done:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class Git:
    """git through exact bytes. Text-mode pipes translate newlines on Windows,
    which would change blob contents and tree entry names."""

    def __init__(self, root):
        self.root = root

    def run(self, *args, env=None, check=True, input_text=None, lazy=False):
        merged = dict(os.environ)
        # In a partial clone, touching a missing object makes git fetch it on
        # the spot, one object and its whole tree at a time. Batched `fetch`
        # and explicit `lazy=True` (materialize parent blobs before push) may
        # go to the network; push itself stays local after that.
        if lazy:
            merged.pop("GIT_NO_LAZY_FETCH", None)
        elif args and args[0] != "fetch":
            merged["GIT_NO_LAZY_FETCH"] = "1"
        if env:
            merged.update(env)
        data = input_text.encode("utf-8", "surrogateescape") if input_text is not None else None
        raw = subprocess.run(["git", "-C", self.root] + list(args), capture_output=True,
                             env=merged, input=data)
        done = _Done(raw.returncode, raw.stdout.decode("utf-8", "surrogateescape"),
                     raw.stderr.decode("utf-8", "replace"))
        if check and done.returncode != 0:
            raise GitError("git %s: %s" % (" ".join(args[:3]), done.stderr.strip()[:400]))
        return done

    def out(self, *args, **kw):
        return self.run(*args, **kw).stdout

    def has_commit(self, sha):
        return self.run("cat-file", "-e", sha + "^{commit}", check=False).returncode == 0

    def fetch(self, shas, remote="origin", chunk=40, *, depth=None):
        """Fetch missing commits and trees, optionally bounding snapshot history."""
        if depth is not None and (type(depth) is not int or depth < 1):
            raise ValueError("fetch depth must be a positive integer")
        fetch_args = ["fetch", "--no-tags", "--filter=blob:none"]
        if depth is not None:
            fetch_args.append("--depth=%d" % depth)
        candidates = [s for s in shas if s and s != UNKNOWN]
        missing = None
        if len(candidates) > 1 and all(
                re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", s) for s in candidates):
            # Canonical object IDs are safe line records. Keep symbolic refs on
            # the existing path, and fall back if the batch reply is incomplete.
            checked = self.run("cat-file", "--batch-check=%(objecttype)", check=False,
                               input_text="".join(s + "^{commit}\n" for s in candidates))
            kinds = checked.stdout.splitlines()
            if checked.returncode == 0 and len(kinds) == len(candidates):
                missing = [s for s, kind in zip(candidates, kinds) if kind != "commit"]
        if missing is None:
            missing = [s for s in candidates if not self.has_commit(s)]
        failed = []
        for start in range(0, len(missing), chunk):
            part = missing[start:start + chunk]
            done = self.run(*fetch_args, remote, *part, check=False)
            if done.returncode != 0:
                for sha in part:
                    one = self.run(*fetch_args, remote, sha, check=False)
                    if one.returncode != 0:
                        failed.append(sha)
        return failed

    def merge_base(self, a, b):
        done = self.run("merge-base", a, b, check=False)
        text = done.stdout.strip()
        return text if done.returncode == 0 and text else None

    def diff_tree(self, a, b, paths=None):
        """Raw changes between two commits: [(status, path, old_mode, new_mode, old, new)]."""
        args = ["diff-tree", "-r", "-z", "--no-renames", a, b]
        if paths:
            args.append("--")
            args.extend(paths)
        raw = self.out(*args)
        return _parse_raw_diff(raw)

    def changed_paths(self, a, b):
        raw = self.out("diff-tree", "-r", "-z", "--no-renames", "--name-only", a, b)
        return {p for p in raw.split("\0") if p}

    def compose(self, main, changes):
        """Tree of `main` with `changes` applied, built in a throwaway index."""
        handle, index = tempfile.mkstemp(prefix="coordination-index-")
        os.close(handle)
        os.unlink(index)
        env = {"GIT_INDEX_FILE": index}
        try:
            self.run("read-tree", main, env=env)
            removals, lines = [], []
            for status, path, _om, new_mode, old, new in changes:
                if status == "D":
                    removals.append("0 %s\t%s" % (old, path))
                else:
                    lines.append("%s %s\t%s" % (new_mode, new, path))
            # Remove old entries first so file/directory replacements compose.
            # NUL records preserve path bytes and batch every index update.
            records = removals + lines
            if records:
                self.run("update-index", "--add", "-z", "--index-info", env=env,
                         input_text="\0".join(records) + "\0")
            return self.out("write-tree", env=env).strip()
        finally:
            if os.path.exists(index):
                os.unlink(index)


def _parse_raw_diff(raw):
    parts = raw.split("\0")
    out, i = [], 0
    while i < len(parts):
        meta = parts[i]
        if not meta.startswith(":"):
            i += 1
            continue
        fields = meta[1:].split()
        if len(fields) < 5 or i + 1 >= len(parts):
            break
        old_mode, new_mode, old, new, status = fields[:5]
        out.append((status[:1], parts[i + 1], old_mode, new_mode, old, new))
        i += 2
    return out


def content_key(changes):
    """Digest of the (status, path, mode, blob) set a change carries."""
    lines = sorted("%s\t%s\t%s\t%s" % (status, path, new_mode, new)
                   for status, path, _om, new_mode, _old, new in changes)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


PATH_CAP = 40


def drift_certificate(git, main, head, base_hint=None, delta_cache=None, compose=True):
    """The disjoint-advance certificate for one head against one base tip.

    `main` is the tip of the branch the pull request targets (main for most,
    the TITAN branch for TITAN pull requests). The certificate says whether
    that tip moved since the merge-base, and whether any move touched the
    paths this change carries. With no overlap the reviewed bytes compose onto
    the tip exactly, and `composed_tree` is the tree they compose to.
    """
    cert = {"tip": main, "head": head, "status": "unknown"}
    base = git.merge_base(main, head) if head != UNKNOWN else None
    if not base and base_hint and git.has_commit(base_hint):
        base = git.merge_base(base_hint, head) or None
    if not base:
        cert["reason"] = "no merge-base in the history this producer holds"
        return cert
    changes = git.diff_tree(base, head)
    paths = sorted(c[1] for c in changes)
    cert.update({
        "merge_base": base,
        "paths": paths[:PATH_CAP],
        "path_count": len(paths),
        "content_key": content_key(changes) if changes else UNKNOWN,
    })
    if not changes:
        cert["status"] = "current" if base == main else "contained"
        cert["reason"] = "head adds nothing beyond its merge-base with the tip"
        return cert
    if base == main:
        cert["status"] = "current"
        cert["main_delta_count"] = 0
        cert["overlap"] = []
        return cert
    cache = delta_cache if delta_cache is not None else {}
    if (base, main) not in cache:
        cache[(base, main)] = git.changed_paths(base, main)
    delta = cache[(base, main)]
    overlap = sorted(set(paths) & delta)
    cert["main_delta_count"] = len(delta)
    cert["overlap"] = overlap[:PATH_CAP]
    cert["overlap_count"] = len(overlap)
    if overlap:
        cert["status"] = "overlap"
        return cert
    cert["status"] = "disjoint"
    if compose:
        cert["composed_tree"] = git.compose(main, changes)
    return cert


# --------------------------------------------------------------------------
# verdicts (first draft parser over review text)

_SEGMENT_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9 /+_.\-']{1,90}?)\s+(PASS|HOLD|FAIL(?:ED)?|PENDING|"
    r"REJECT(?:ED)?|BLOCKED|GREEN)\b")
_CURRENT_WORDS = ("CURRENT-", "CURRENT ", "LIVE-", "CANONICAL", "FRESHNESS", "STALE")
_FIELD_WORDS = (
    ("hosted", ("HOSTED", " CI ", " CI-", "WORKFLOW", "ACTIONS", "GREEN")),
    ("economics", ("ECONOMICS", "ECON ", " D3")),
    ("composition", ("COMPOSITION", "CUSTODY", "TOPOLOGY", "SCOPE", "PACKAGE",
                     "MATERIALIZATION", "REBIND", "RECEIPT", "BYTE", "TUPLE", "DELTA")),
    ("source", ("SOURCE", "SEMANTIC", "THEOREM", "DONOR", "MECHANICS", "PROOF",
                "REPAIR", "ATOMICITY", "POLICY")),
)
_ID_RE = re.compile(r"\b(\d{10})\b")
_HEAD_RE = re.compile(r"(?:exact(?:[ -]head)?|head|on)\s+`?([0-9a-f]{7,40})`?", re.IGNORECASE)
_NORM = {"FAILED": "FAIL", "REJECTED": "FAIL", "REJECT": "FAIL", "BLOCKED": "HOLD",
         "GREEN": "PASS"}


def _fields_for(label):
    """Fields a label speaks to. Each '/'-separated part is read on its own:
    'SOURCE / CURRENT-MAIN COMPOSITION-CUSTODY' is source and current_main."""
    found = []
    for part in label.split("/"):
        upper = " " + part.strip().upper() + " "
        if any(w in upper for w in _CURRENT_WORDS):
            found.append("current_main")
            continue
        hits = [name for name, words in _FIELD_WORDS if any(w in upper for w in words)]
        found.extend(hits or ["other"])
    ordered = []
    for name in found:
        if name not in ordered:
            ordered.append(name)
    return ordered


def _verdict_paragraph(text):
    """The part of a review that carries its verdict: the first paragraph."""
    body = (text or "").replace("**", "").replace("__", "")
    first = body.strip().split("\n\n", 1)[0]
    return first[:900]


def parse_verdict(text):
    """Split a review body into labelled verdict segments and field verdicts.

    "SOURCE / COMPOSITION-CUSTODY PASS; CURRENT-MAIN COMPOSITION HOLD; HOSTED
    GATE PENDING" reads as source=PASS, composition=PASS, current_main=HOLD,
    hosted=PENDING. Only the first paragraph is read, where reviews put their
    verdict; the first verdict a field receives wins. "HOSTED NOT GREEN" reads
    PENDING, and "X HOLD CLOSED" reads PASS.
    """
    text = text or ""
    segments, fields = [], {}
    head_line = _verdict_paragraph(text)
    for match in _SEGMENT_RE.finditer(head_line):
        label = match.group(1).strip(" /-.")
        word = match.group(2).upper()
        verdict = _NORM.get(word, word)
        words = label.upper().split()
        if words and words[-1] in ("NOT", "NO"):
            label = " ".join(label.split()[:-1])
            verdict = "PENDING"
        tail = head_line[match.end():match.end() + 10].upper()
        if verdict in ("HOLD", "FAIL") and tail.lstrip(" :-").startswith("CLOSED"):
            verdict = "PASS"
        if len(label) < 2:
            continue
        segments.append({"label": label[-80:], "verdict": verdict})
        for field in _fields_for(label):
            fields.setdefault(field, verdict)
    lowered = text.lower()
    supersedes = []
    for sentence in re.split(r"(?<=[.;])\s+", text):
        low = sentence.lower()
        if "supersed" in low or "retract" in low or "correction" in low:
            supersedes.extend(_ID_RE.findall(sentence))
    heads = [m.group(1).lower() for m in _HEAD_RE.finditer(text[:2000])]
    return {
        "segments": segments[:12],
        "fields": fields,
        "mentions_ids": sorted(set(supersedes)),
        "retracted": "retracted" in lowered,
        "heads": heads[:3],
    }


def pull_verdicts(pull, head):
    """Verdict records for one pull request, newest first, current head first."""
    records = []
    for review in ((pull.get("reviews") or {}).get("nodes") or []):
        body = review.get("body") or ""
        parsed = parse_verdict(body)
        if not parsed["segments"]:
            continue
        commit = ((review.get("commit") or {}).get("oid")) or ""
        records.append({"kind": "review", "id": str(review.get("databaseId") or ""),
                        "at": review.get("submittedAt") or "", "url": review.get("url") or "",
                        "head": commit, **parsed})
    for comment in ((pull.get("comments") or {}).get("nodes") or []):
        body = comment.get("body") or ""
        parsed = parse_verdict(body)
        if not parsed["segments"]:
            continue
        mentioned = parsed["heads"][0] if parsed["heads"] else ""
        records.append({"kind": "comment", "id": str(comment.get("databaseId") or ""),
                        "at": comment.get("createdAt") or "", "url": comment.get("url") or "",
                        "head": mentioned, **parsed})
    superseded = set()
    for record in records:
        superseded.update(i for i in record["mentions_ids"] if i != record["id"])
    for record in records:
        record["superseded"] = record["id"] in superseded
    records.sort(key=lambda r: r["at"], reverse=True)

    def on_head(record):
        return bool(head and record["head"] and head.startswith(record["head"][:7])
                    and record["head"] == head[:len(record["head"])])

    current = [r for r in records if on_head(r) and not r["superseded"] and not r["retracted"]]
    fields = {}
    for record in current:
        for field, verdict in record["fields"].items():
            fields.setdefault(field, {"verdict": verdict, "id": record["id"],
                                      "at": record["at"], "url": record["url"]})
    slim = [{k: r[k] for k in ("kind", "id", "at", "url", "head", "fields",
                                "superseded", "retracted")} for r in records[:8]]
    return {"current_head": fields, "records": slim, "parser": PARSER}


# --------------------------------------------------------------------------
# hosted checks


def check_enum(node):
    """One check or status reduced to the enum that never collapses queued into failed."""
    kind = node.get("__typename")
    if kind == "StatusContext":
        state = (node.get("state") or "").upper()
        return {"PENDING": "NOT_EXECUTED_QUEUED", "EXPECTED": "NOT_EXECUTED_QUEUED",
                "SUCCESS": "SUCCESS", "FAILURE": "FAILED", "ERROR": "FAILED"}.get(state, UNKNOWN)
    status = (node.get("status") or "").upper()
    conclusion = (node.get("conclusion") or "").upper()
    if status in ("QUEUED", "WAITING", "PENDING", "REQUESTED"):
        return "NOT_EXECUTED_QUEUED"
    if status == "IN_PROGRESS":
        return "RUNNING"
    if conclusion == "ACTION_REQUIRED":
        return "APPROVAL_GATED"
    if conclusion in ("CANCELLED", "SKIPPED", "STALE"):
        return "CANCELLED_NOT_RUN"
    if conclusion in ("FAILURE", "TIMED_OUT", "STARTUP_FAILURE"):
        return "FAILED"
    if conclusion in ("SUCCESS", "NEUTRAL"):
        return "SUCCESS"
    return UNKNOWN


_ROLLUP_ORDER = ("FAILED", "RUNNING", "NOT_EXECUTED_QUEUED", "APPROVAL_GATED",
                 "CANCELLED_NOT_RUN", UNKNOWN, "SUCCESS")


def hosted_state(pull):
    """Keep GitHub's aggregate separate from the bounded context detail."""
    commits = ((pull.get("commits") or {}).get("nodes") or [])
    # OPEN_PULLS_QUERY requests exactly the last commit, not several rollups.
    commit = ((commits[0].get("commit") or {})
              if len(commits) == 1 and isinstance(commits[0], dict) else {})
    reported = commit.get("statusCheckRollup") or {}
    contexts = reported.get("contexts") or {}
    raw_nodes = contexts.get("nodes")
    nodes = ([node for node in raw_nodes if isinstance(node, dict)]
             if isinstance(raw_nodes, list) else [])
    github_state = reported.get("state")
    if github_state not in ("ERROR", "EXPECTED", "FAILURE", "PENDING", "SUCCESS"):
        github_state = UNKNOWN
    total = contexts.get("totalCount")
    if type(total) is not int or total < 0:
        total = UNKNOWN
    more = (contexts.get("pageInfo") or {}).get("hasNextPage")
    if type(more) is not bool:
        more = UNKNOWN
    complete = (isinstance(raw_nodes, list) and len(nodes) == len(raw_nodes)
                and total == len(nodes) and more is False)
    counts, checks = {}, []
    for node in nodes:
        state = check_enum(node)
        counts[state] = counts.get(state, 0) + 1
        checks.append({"name": node.get("name") or node.get("context") or "", "state": state})
    if counts.get("FAILED") or github_state in ("FAILURE", "ERROR"):
        rollup = "FAILED"
    elif not complete:
        rollup = UNKNOWN
    elif not nodes:
        rollup = "NONE" if github_state == "SUCCESS" else UNKNOWN
    else:
        rollup = next(s for s in _ROLLUP_ORDER if counts.get(s))
        if rollup == "SUCCESS" and github_state != "SUCCESS":
            rollup = UNKNOWN
    return {"rollup": rollup, "github_state": github_state,
            "contexts_read": len(nodes), "contexts_total": total,
            "contexts_has_next_page": more, "contexts_complete": complete,
            "counts": dict(sorted(counts.items())),
            "checks": sorted(checks, key=lambda c: c["name"])[:40]}


# --------------------------------------------------------------------------
# lanes

_LINK_RES = (
    re.compile(r"SUPERSEDED(?:\s+DUPLICATE)?\s+BY\s+#(\d+)", re.IGNORECASE),
    re.compile(r"superseded\s+(?:by|in favou?r of)\s+(?:canonical\s+)?#(\d+)", re.IGNORECASE),
    re.compile(r"successor\s+(?:is\s+)?(?:draft\s+)?(?:Commons\s+)?(?:PR\s+)?#(\d+)", re.IGNORECASE),
    re.compile(r"canonical\s+(?:fresh[- ]current[- ]main\s+)?(?:carrier|target)\s+(?:is\s+)?(?:draft\s+)?(?:Commons\s+)?#(\d+)", re.IGNORECASE),
)
_MARKER_RE = re.compile(r"`([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,})`")
_MARKER_STRIP = (
    re.compile(r"-\d{8}(?:-\d{2})?$"),
    re.compile(r"-MAIN[0-9A-F]{3,40}(?=-|$)"),
    re.compile(r"-(?:CURRENT-MAIN-)?(?:REFRESH-COMPOSE|COMPOSITION-REREVIEW|REVIEWED-MERGE|"
               r"REREVIEW|REVIEW|CANONICALIZATION|COMPOSE)$"),
)


def marker_family(marker):
    """A claim marker with base SHA, date, retry and step suffixes removed."""
    text = (marker or "").upper()
    for _ in range(3):
        for pattern in _MARKER_STRIP:
            text = pattern.sub("", text)
    return text.strip("-")


def pull_links(pull):
    texts = [pull.get("title") or "", (pull.get("body") or "")[:4000]]
    for comment in ((pull.get("comments") or {}).get("nodes") or []):
        texts.append((comment.get("body") or "")[:2000])
    found = set()
    for text in texts:
        for pattern in _LINK_RES:
            found.update(int(n) for n in pattern.findall(text))
    found.discard(pull.get("number"))
    return sorted(found)


def pull_markers(pull):
    text = (pull.get("title") or "") + "\n" + (pull.get("body") or "")[:4000]
    return sorted({marker_family(m) for m in _MARKER_RE.findall(text) if len(m) >= 12})


def build_lanes(rows):
    """Join pull requests by shared content key and by supersession links."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_key = {}
    numbers = {r["number"] for r in rows}
    for row in rows:
        find(row["number"])
        key = row.get("content_key")
        if key and key != UNKNOWN:
            by_key.setdefault(key, []).append(row["number"])
        for other in row.get("links", []):
            if other in numbers:
                union(row["number"], other)
    for members in by_key.values():
        for other in members[1:]:
            union(members[0], other)
    groups = {}
    for row in rows:
        groups.setdefault(find(row["number"]), []).append(row)
    lanes = []
    for members in groups.values():
        members.sort(key=lambda r: (r.get("created_at") or "", r["number"]))
        open_members = [m for m in members if m.get("state") == "OPEN"]
        merged = [m for m in members if m.get("state") == "MERGED"]
        canonical = (open_members[-1]["number"] if open_members
                     else merged[-1]["number"] if merged else members[-1]["number"])
        families = sorted({f for m in members for f in m.get("markers", [])})
        lanes.append({
            "lane": "lane-%d" % members[0]["number"],
            "canonical": canonical,
            "state": ("OPEN" if open_members else "MERGED" if merged else "CLOSED"),
            "open": [m["number"] for m in open_members],
            "chain": [m["number"] for m in members],
            "content_keys": sorted({m["content_key"][:16] for m in members
                                    if m.get("content_key") not in (None, UNKNOWN)}),
            "families": families[:6],
            "title": members[-1].get("title", "")[:140],
        })
    lanes.sort(key=lambda l: (l["state"] != "OPEN", -len(l["open"]), -l["canonical"]))
    return lanes


# --------------------------------------------------------------------------
# build


ROW_PATHS = 5
ROW_CHECKS = 4

# The published rows are the full tier's budget: everything a seat needs to
# route, nothing it can get from `drift --pr N` or the pull request itself.


def _slim_drift(drift):
    keep = ("status", "path_count", "main_delta_count", "overlap_count",
            "composed_tree", "reason")
    out = {k: drift[k] for k in keep if k in drift}
    if drift.get("status") in ("disjoint", "overlap") and drift.get("merge_base"):
        out["merge_base"] = drift["merge_base"]
    if drift.get("overlap"):
        out["overlap"] = drift["overlap"][:ROW_PATHS]
    return out


def _slim_hosted(hosted):
    others = [c for c in hosted.get("checks", []) if c["state"] != "SUCCESS"]
    return {"rollup": hosted.get("rollup"), "counts": hosted.get("counts", {}),
            "github_state": hosted.get("github_state", UNKNOWN),
            "contexts_read": hosted.get("contexts_read", UNKNOWN),
            "contexts_total": hosted.get("contexts_total", UNKNOWN),
            "contexts_has_next_page": hosted.get("contexts_has_next_page", UNKNOWN),
            "contexts_complete": hosted.get("contexts_complete", False),
            "not_success": others[:ROW_CHECKS]}


def _slim_verdicts(verdicts):
    current = {field: {"verdict": v["verdict"], "id": v["id"]}
               for field, v in (verdicts.get("current_head") or {}).items()}
    records = verdicts.get("records") or []
    return {"current_head": current, "reviews_read": len(records),
            "superseded": sorted(r["id"] for r in records if r["superseded"] or r["retracted"])}


def _pull_row(pull, state, drift, hosted, verdicts):
    return {
        "number": pull.get("number"),
        "title": (pull.get("title") or "")[:100],
        "state": state,
        "draft": bool(pull.get("isDraft")),
        "author": ((pull.get("author") or {}).get("login")) or UNKNOWN,
        "created_at": pull.get("createdAt") or UNKNOWN,
        "updated_at": pull.get("updatedAt") or pull.get("closedAt") or UNKNOWN,
        "head": pull.get("headRefOid") or UNKNOWN,
        "head_ref": (pull.get("headRefName") or UNKNOWN)[:90],
        "base_ref": pull.get("baseRefName") or UNKNOWN,
        "drift": drift,
        "content_key": (drift or {}).get("content_key", UNKNOWN),
        "hosted": hosted,
        "verdicts": verdicts,
        "links": pull_links(pull),
        "markers": pull_markers(pull)[:3],
    }


def _publishable(payload):
    """The published shape: slim rows, lane ids on rows, multi-member lanes only."""
    lanes = payload.get("lanes", [])
    lane_of = {}
    for lane in lanes:
        for number in lane["chain"]:
            lane_of[number] = lane["lane"]
    joined = [l for l in lanes if len(l["chain"]) > 1]
    multi = {n for l in joined for n in l["chain"]}
    rows = []
    for row in payload.get("prs", []):
        key = row.get("content_key")
        slim = {
            "number": row["number"],
            "title": (row.get("title") or "")[:90],
            "draft": row.get("draft", False),
            "created_at": row.get("created_at", UNKNOWN),
            "updated_at": row.get("updated_at", UNKNOWN),
            "head": row.get("head", UNKNOWN),
            "head_ref": (row.get("head_ref") or UNKNOWN)[:60],
            "base_ref": row.get("base_ref", UNKNOWN),
            "content_key": key[:16] if key and key != UNKNOWN else UNKNOWN,
            "drift": _slim_drift(row.get("drift") or {}),
            "hosted": _slim_hosted(row.get("hosted") or {}),
            "verdicts": _slim_verdicts(row.get("verdicts") or {}),
        }
        if row.get("swarm"):
            slim["swarm"] = row["swarm"]
        if row.get("links"):
            slim["links"] = row["links"][:6]
        if row.get("markers"):
            slim["markers"] = row["markers"][:2]
        if row["number"] in multi:
            slim["lane"] = lane_of.get(row["number"], "")
        rows.append(slim)
    members = {n for l in joined for n in l["chain"]}
    closed = []
    for row in payload.get("recent_closed", []):
        if row["number"] in members:
            slim = dict(row)
            key = slim.get("content_key")
            slim["content_key"] = key[:16] if key and key != UNKNOWN else UNKNOWN
            slim["markers"] = slim.get("markers", [])[:3]
            slim["title"] = slim.get("title", "")[:100]
            slim.pop("url", None)
            closed.append(slim)
    full = {k: v for k, v in payload.items() if k not in ("prs", "lanes", "recent_closed")}
    full["tips"] = {name: (tip or {}).get("sha", UNKNOWN)
                    for name, tip in (payload.get("tips") or {}).items()}
    full["prs"] = rows
    full["files"] = {"lanes": LANES_FILE, "head": HEAD_FILE, "paths": PATHS_FILE}
    lanes_doc = {"schema": LANES_SCHEMA, "observed_at": payload["observed_at"],
                 "repo": payload.get("repo"), "note": "lanes with two or more members; "
                 "an open pull request row without a lane field is a lane of its own",
                 "lanes": [dict(l, content_keys=l["content_keys"][:4]) for l in joined],
                 "recent_closed": closed}
    paths_doc = {"schema": PATHS_SCHEMA, "observed_at": payload["observed_at"],
                 "note": "paths each open pull request changes since its merge-base "
                         "(first %d; drift --pr N prints all)" % PATH_CAP,
                 "prs": [{"number": row["number"], "path_count": (row.get("drift") or {}).get("path_count"),
                          "paths": (row.get("drift") or {}).get("paths", [])}
                         for row in payload.get("prs", [])]}
    return full, lanes_doc, paths_doc


def _dump_rows(value, row_keys=("prs", "lanes", "recent_closed")):
    """JSON with one row per line, so a refresh diffs row by row."""
    items = []
    for key in sorted(value):
        item = value[key]
        if key in row_keys and isinstance(item, list):
            if item:
                body = ",\n".join("  " + _compact(row) for row in item)
                items.append(' "%s": [\n%s\n ]' % (key, body))
            else:
                items.append(' "%s": []' % key)
        else:
            items.append(' "%s": %s' % (key, _compact(item)))
    return "{\n" + ",\n".join(items) + "\n}\n"


def build(git, github, now=None, closed_hours=36, closed_limit=400, open_limit=1000,
          producer="", composed=False, review_capacity=None):
    now = now or _now()
    degraded, notes = [], []
    try:
        queue = fetch_queue(github, now)
    except GitHubError as exc:
        queue = {"queued": UNKNOWN, "in_progress": UNKNOWN, "error": str(exc)[:200]}
        degraded.append("queue")
    pulls, total, complete = fetch_open_pulls(github, limit=open_limit)
    if not complete:
        degraded.append("open-listing-partial")
    since = _iso(now - _dt.timedelta(hours=closed_hours))[:10]
    try:
        closed, closed_complete = fetch_closed_pulls(github, since, limit=closed_limit)
        if not closed_complete:
            degraded.append("closed-listing-partial")
    except GitHubError as exc:
        closed = []
        degraded.append("closed-listing")
        notes.append(str(exc)[:200])

    bases = {"main"} | {p.get("baseRefName") or "main" for p in pulls + closed}
    tips = fetch_tips(github, bases)
    main = tips.get("main") or {"sha": UNKNOWN}
    main_sha = main["sha"]
    tip_shas = [t["sha"] for t in tips.values() if t.get("sha") not in (None, UNKNOWN)]
    heads = [p.get("headRefOid") for p in pulls] + [p.get("headRefOid") for p in closed]
    _log("listed %d open, %d recently closed, %d base tips; fetching trees"
         % (len(pulls), len(closed), len(tip_shas)))
    failed = git.fetch(tip_shas + heads)
    _log("fetch done (%d not fetched); computing drift" % len(failed))
    if main_sha in failed:
        degraded.append("main-not-fetched")
    if failed:
        notes.append("%d commits could not be fetched" % len(failed))

    def tip_for(pull):
        return (tips.get(pull.get("baseRefName") or "main") or {}).get("sha") or UNKNOWN

    delta_cache = {}
    rows = []
    drift_counts = {"current": 0, "disjoint": 0, "overlap": 0, "contained": 0, "unknown": 0}
    hosted_counts = {}
    for pull in pulls:
        head = pull.get("headRefOid") or UNKNOWN
        tip = tip_for(pull)
        try:
            if tip == UNKNOWN:
                raise GitError("base branch tip unknown")
            drift = drift_certificate(git, tip, head, pull.get("baseRefOid"), delta_cache,
                                      compose=composed)
        except GitError as exc:
            drift = {"status": "unknown", "reason": str(exc)[:200]}
        drift["base_ref"] = pull.get("baseRefName") or "main"
        drift_counts[drift["status"]] = drift_counts.get(drift["status"], 0) + 1
        hosted = hosted_state(pull)
        if not hosted["contexts_complete"]:
            degraded.append("hosted-contexts-incomplete")
        hosted_counts[hosted["rollup"]] = hosted_counts.get(hosted["rollup"], 0) + 1
        verdicts = pull_verdicts(pull, head)
        row = _pull_row(pull, "OPEN", drift, hosted, verdicts)
        try:
            from host.swarm_review import annotate
        except ImportError:
            from swarm_review import annotate
        row["swarm"] = annotate(git, tip, pull)
        rows.append(row)
    closed_rows = []
    for pull in closed:
        head = pull.get("headRefOid") or UNKNOWN
        key = UNKNOWN
        tip = tip_for(pull)
        if head != UNKNOWN and tip != UNKNOWN and git.has_commit(head) and git.has_commit(tip):
            base = git.merge_base(tip, head)
            if base:
                try:
                    changes = git.diff_tree(base, head)
                    key = content_key(changes) if changes else UNKNOWN
                except GitError:
                    key = UNKNOWN
        state = "MERGED" if pull.get("mergedAt") else "CLOSED"
        closed_rows.append({
            "number": pull.get("number"), "title": (pull.get("title") or "")[:160],
            "url": pull.get("url") or "", "state": state,
            "created_at": pull.get("createdAt") or UNKNOWN,
            "closed_at": pull.get("closedAt") or UNKNOWN, "head": head,
            "content_key": key, "links": pull_links(pull), "markers": pull_markers(pull),
        })
    lanes = build_lanes(rows + closed_rows)
    open_lanes = [l for l in lanes if l["state"] == "OPEN"]
    multi = [l for l in open_lanes if len(l["open"]) > 1]
    payload = {
        "schema": SCHEMA,
        "observed_at": _iso(now),
        "repo": github.repo,
        "producer": {"seat": producer or os.environ.get("COMMONS_SEAT", "") or UNKNOWN,
                     "road": "git trees + GitHub GraphQL/REST", "api_calls": github.calls,
                     "first_draft": True},
        "main": main,
        "tips": tips,
        "queue": queue,
        "counts": {
            "open_prs": total, "listed_open": len(rows), "listed_recent_closed": len(closed_rows),
            "drift": drift_counts, "hosted": dict(sorted(hosted_counts.items())),
            "lanes_open": len(open_lanes), "lanes_with_several_open": len(multi),
        },
        "prs": sorted(rows, key=lambda r: -r["number"]),
        "recent_closed": sorted(closed_rows, key=lambda r: -r["number"]),
        "lanes": lanes,
        "degraded": sorted(set(degraded)),
        "notes": notes,
    }
    try:
        from host.swarm_review import batches, RELIABILITY
    except ImportError:
        from swarm_review import batches, RELIABILITY
    try:
        outcomes = json.loads(git.out("show", main_sha + ":" + RELIABILITY)).get("outcomes", [])
    except (GitError, ValueError):
        outcomes = []
    review_rows = [dict(r["swarm"], number=r["number"], created_at=r["created_at"],
                        paths=r["drift"].get("paths", [])) for r in rows]
    payload["swarm"] = {
        "schema": "commons-swarm-queue/v1", "policy": "ground/SWARM_ORDER.md",
        "capacity": review_capacity, "capacity_note": "available review batches at observation time; unknown is not unlimited",
        "counts": dict(Counter(r["review"]["state"] for r in review_rows)),
        "batches": batches(review_rows, outcomes, capacity=review_capacity),
    }
    return payload


def head_tier(payload):
    """The under-2 KB tier: enough for any seat to know whether to read more."""
    multi = [l for l in payload.get("lanes", []) if l["state"] == "OPEN" and len(l["open"]) > 1]
    head = {
        "schema": HEAD_SCHEMA,
        "observed_at": payload["observed_at"],
        "main": {k: payload["main"].get(k) for k in ("sha", "committed_at")},
        "queue": {k: payload["queue"].get(k) for k in ("queued", "in_progress", "oldest_queued_age_s")},
        "counts": payload["counts"],
        "several_open": [{"lane": l["lane"], "open": l["open"][:4]} for l in multi[:6]],
        "files": {"full": STATE_FILE, "branch": STATE_BRANCH},
        "degraded": payload.get("degraded", []),
    }
    if payload.get("swarm"):
        head["swarm"] = {"counts": payload["swarm"]["counts"],
                         "batches": len(payload["swarm"]["batches"]), "capacity": payload["swarm"].get("capacity")}
    while len(_compact(head).encode("utf-8")) > HEAD_LIMIT and head["several_open"]:
        head["several_open"].pop()
    return head


def render_files(payload):
    """{file name: text} for the published tiers, plus the head object."""
    head = head_tier(payload)
    full, lanes, paths = _publishable(payload)
    return {HEAD_FILE: _dump(head), STATE_FILE: _dump_rows(full),
            LANES_FILE: _dump_rows(lanes), PATHS_FILE: _dump_rows(paths)}, head


def write_outputs(payload, outdir):
    os.makedirs(outdir, exist_ok=True)
    texts, head = render_files(payload)
    for name, text in texts.items():
        path = os.path.join(outdir, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    return head


def read_outputs(outdir):
    texts = {}
    for name in (HEAD_FILE, STATE_FILE, LANES_FILE, PATHS_FILE):
        with open(os.path.join(outdir, name), encoding="utf-8") as fh:
            texts[name] = fh.read()
    return texts, json.loads(texts[HEAD_FILE])


# --------------------------------------------------------------------------
# publishing to a state branch (never main)


STATE_README = """# state/coordination

Computed coordination state for the Commons repository, written by
host/coordination_state.py. Nothing on this branch is merged into main, so a
refresh never moves main and never makes an open carrier stale.

- coordination-head.json - under 2 KB: main, counts, queue, lanes with
  several open carriers.
- coordination.json - one row per open pull request: drift certificate,
  content key, parsed verdict fields, hosted check states, links.
- coordination-lanes.json - lanes with two or more members, with their
  recently closed members.
- coordination-paths.json - the paths each open pull request changes.

Raw read (no auth): https://raw.githubusercontent.com/{repo}/state/coordination/coordination-head.json

First draft. Any peer may fix it; see ground/COORDINATION_STATE.md on main.
"""


def _commit_env(when=None):
    stamp = _iso(when or _now())
    return {"GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
            "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1],
            "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}


def _materialize_blobs(git, commit):
    """Bring blob bytes of `commit` into a blob:none clone.

    Hosted `--no-thin` push on landed 492e1376 still tried to read parent
    blob e3ee4c72 (coordination-head.json) and GIT_NO_LAZY_FETCH blocked
    it (run 34999623710). Fetch those blobs *before* send-pack so push
    does not open a second connection on the same remote.
    """
    if not commit:
        return
    listing = git.run("ls-tree", "-r", commit, check=False)
    if listing.returncode != 0 or not listing.stdout.strip():
        return
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        sha = parts[2].split("\t")[0]
        if git.run("cat-file", "-e", sha, check=False).returncode != 0:
            git.run("cat-file", "-e", sha, lazy=True, check=False)


_PUSH_TRANSIENT = (
    "from promisor remote",
    "hung up unexpectedly",
    "unexpected disconnect",
    "eof before pack header",
    "unpacker error",
    "RPC failed",
)
_PUSH_RETRY_SLEEP = time.sleep


def _push_ref(git, remote, commit, branch, attempts=3):
    """Fast-forward `branch` to `commit`.

    `--no-thin` avoids using parent blobs as thin-pack delta bases.
    HTTP/1.1 plus a short hangup retry covers GitHub HTTPS disconnects
    after the objects are already local.
    """
    refspec = "%s:refs/heads/%s" % (commit, branch)
    last = None
    tries = max(1, int(attempts))
    for attempt in range(tries):
        done = git.run("-c", "http.version=HTTP/1.1",
                       "push", "--no-thin", remote, refspec, check=False)
        last = done
        if done.returncode == 0:
            return done
        err = done.stderr or ""
        if "non-fast-forward" in err or "fetch first" in err:
            return done
        if not any(n in err for n in _PUSH_TRANSIENT) or attempt >= tries - 1:
            return done
        _PUSH_RETRY_SLEEP(2 * (attempt + 1))
    return last


def _push_line(root, remote, commit, branch):
    return "git -C %s push --no-thin %s %s:refs/heads/%s" % (root, remote, commit, branch)


def _remote_tip(git, branch, remote="origin"):
    # An unreadable remote is not an empty branch. In particular, callers must
    # not advertise a vacant claim ledger after a network/provider failure.
    done = git.run("ls-remote", remote, "refs/heads/" + branch)
    line = done.stdout.strip().split("\n")[0] if done.stdout.strip() else ""
    return line.split()[0] if line else None


def state_commit(git, files, branch, message, parent=None):
    """A commit whose tree is exactly `files` ({name: text}), on top of `parent`."""
    entries = []
    for name in sorted(files):
        blob = git.out("hash-object", "-w", "--stdin", input_text=files[name]).strip()
        entries.append("100644 blob %s\t%s" % (blob, name))
    tree = git.out("mktree", "--missing", input_text="\n".join(entries) + "\n").strip()
    args = ["commit-tree", tree, "-m", message]
    if parent:
        args[2:2] = ["-p", parent]
    return git.out(*args, env=_commit_env()).strip()


def _superseded_state(git, parent, head):
    """An older completed build must not replace a newer published observation."""
    incoming = _parse_ts(head.get("observed_at"))
    if not parent or incoming is None:
        return None
    try:
        previous = json.loads(git.out("show", parent + ":" + HEAD_FILE))
    except (GitError, ValueError):
        return None  # An absent/invalid old head can still be repaired.
    retained = _parse_ts(previous.get("observed_at")) if isinstance(previous, dict) else None
    if retained is None or retained <= incoming:
        return None
    return {"commit": parent, "parent": parent, "pushed": False,
            "superseded": True, "observed_at": head.get("observed_at"),
            "retained_observed_at": previous["observed_at"],
            "reason": "a newer coordination snapshot is already published"}


def publish(git, payload, repo, push=True, remote="origin", branch=STATE_BRANCH, texts=None,
            split=False):
    """Commit the tiers to `branch` on top of its current tip. `texts` (from
    read_outputs) publishes an existing build without re-rendering it."""
    if texts is None:
        texts, head = render_files(payload)
    else:
        head = json.loads(texts[HEAD_FILE])
    files = dict(texts)
    files["README.md"] = STATE_README.format(repo=repo)
    parent = _remote_tip(git, branch, remote)
    if parent:
        git.fetch([parent], remote)
        _materialize_blobs(git, parent)
    superseded = _superseded_state(git, parent, head)
    if superseded:
        return superseded
    message = "coordination state: main %s, %s open, observed %s" % (
        str((head.get("main") or {}).get("sha", ""))[:10],
        (head.get("counts") or {}).get("open_prs"), head.get("observed_at"))
    if split and not push:
        # A chain of cumulative commits, one more file each, for publishers
        # whose push inspection caps the size of one push.
        order = ["README.md", HEAD_FILE, LANES_FILE, STATE_FILE, PATHS_FILE]
        chain, tip, so_far = [], parent, {}
        for name in order:
            if name not in files:
                continue
            so_far[name] = files[name]
            tip = state_commit(git, dict(so_far), branch, "%s (adds %s)" % (message, name), tip)
            chain.append(tip)
        fetch_line = ("git -C %s fetch %s +refs/heads/%s:refs/remotes/%s/%s"
                      % (git.root, remote, branch, remote, branch))
        lines = []
        for sha in chain:
            lines.append(_push_line(git.root, remote, sha, branch))
            lines.append(fetch_line)
        return {"commit": chain[-1] if chain else None, "parent": parent, "pushed": False,
                "chain": chain, "push_lines": lines}
    commit = state_commit(git, files, branch, message, parent)
    line = _push_line(git.root, remote, commit, branch)
    if not push:
        return {"commit": commit, "parent": parent, "pushed": False, "push_line": line}
    done = _push_ref(git, remote, commit, branch)
    if done.returncode != 0 and ("non-fast-forward" in done.stderr or "fetch first" in done.stderr):
        parent = _remote_tip(git, branch, remote)
        if parent:
            git.fetch([parent], remote)
            _materialize_blobs(git, parent)
        superseded = _superseded_state(git, parent, head)
        if superseded:
            return superseded
        commit = state_commit(git, files, branch, message, parent)
        done = _push_ref(git, remote, commit, branch)
    return {"commit": commit, "parent": parent, "pushed": done.returncode == 0,
            "stderr": done.stderr.strip()[-300:]}


# --------------------------------------------------------------------------
# change holdings: one file per change key on state/claims, fast-forward only

_KEY_RE = re.compile(r"[^A-Za-z0-9._-]+")


def claim_repository(repository=None):
    """Canonical GitHub repository metadata for a claim; not an access check."""
    value = DEFAULT_REPO if repository is None else repository
    if not isinstance(value, str):
        raise ValueError("repository must be owner/name text")
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", value):
        raise ValueError("repository must be owner/name text")
    return value


def repository_claim_key(kind, number, repository=None):
    """Keep Commons keys stable; separate equal issue/PR numbers in other repos."""
    if kind not in ("issue", "pr") or type(number) is not int or number <= 0:
        raise ValueError("claim requires issue or pr and a positive integer")
    repository = claim_repository(repository)
    legacy = "%s-%d" % (kind, number)
    if repository == DEFAULT_REPO.lower():
        return legacy
    digest = hashlib.sha256(repository.encode("utf-8")).hexdigest()[:24]
    return "repo-%s-%s" % (digest, legacy)


def change_key(value=None, pr=None, content=None):
    """A stable key for a change. Content digests win; then PR; then marker family."""
    if content:
        return "ck-" + content[:16].lower()
    if pr:
        return "pr-%d" % int(pr)
    family = marker_family(value or "")
    return _KEY_RE.sub("-", family).strip("-").lower()[:96] or "unnamed"


def _holding_path(key):
    return "holdings/%s.json" % key


class _Preserved(dict):
    """A holding carried forward from the parent tree by blob id; its bytes are never re-serialized."""
    __slots__ = ("blob",)

    def __init__(self, blob):
        super().__init__()
        self.blob = blob


def _holding_entries(git, commit, path=None):
    """{path: blob id} for every holdings/*.json in `commit`, read from the tree alone."""
    entries = {}
    args = ["ls-tree", "-r", commit]
    if path is not None:
        args.extend(["--", path])
    for line in git.out(*args).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and path.startswith("holdings/") and path.endswith(".json"):
            entries[path] = parts[2]
    return entries


def _read_holding(git, commit, path, blob):
    """Parse one holding by blob id, fetching that single blob on demand in a blobless clone."""
    if git.run("cat-file", "-e", blob, check=False).returncode != 0:
        git.run("cat-file", "-e", blob, lazy=True, check=False)
    try:
        record = json.loads(git.out("cat-file", "-p", blob))
    except (GitError, ValueError) as exc:
        raise HoldingUnreadable("%s at %s: %s" % (path, str(commit)[:12], exc)) from exc
    if type(record) is not dict:
        raise HoldingUnreadable("%s at %s: holding is not a JSON object" % (path, str(commit)[:12]))
    return record


def _read_holdings(git, commit, want=None):
    """Holdings of `commit`.

    With `want` (a holdings path) only that holding is parsed; every other holding is
    carried by blob id so a later commit keeps its bytes exactly, whether or not this
    clone holds the blob. Without `want` every holding is parsed for listing, and one
    that cannot be read is carried by blob id rather than replaced by a placeholder.
    """
    if not commit:
        return {}
    found = {}
    for path, blob in _holding_entries(git, commit).items():
        if want is not None and path != want:
            found[path] = _Preserved(blob)
            continue
        try:
            found[path] = _read_holding(git, commit, path, blob)
        except HoldingUnreadable:
            if want is not None:
                raise
            found[path] = _Preserved(blob)
    return found


def _holding_live(record, now):
    if not isinstance(record, dict) or record.get("state") != "HELD":
        return False
    beat = _parse_ts(record.get("heartbeat_at") or record.get("taken_at"))
    ttl = record.get("ttl_s")
    if beat is None or type(ttl) is not int or not 1 <= ttl <= 7200:
        return False
    # Clock skew is not expiry evidence. A syntactically valid future beat is
    # fail-closed as live until this observer advances beyond beat + TTL.
    return (now - beat).total_seconds() <= ttl


def _holdings_commit(git, parent, holdings, message, when):
    """A commit on `parent` whose holdings tree is `holdings`: carried holdings keep their
    exact parent blob id; only records given as parsed dicts are serialized."""
    files = {path: record for path, record in holdings.items()}
    files["README.md"] = ("# state/claims\n\nChange holdings written by "
                          "host/coordination_state.py, one file per change key, "
                          "fast-forward only. Coordination state, never a gate.\n")
    entries = []
    for path in sorted(files):
        record = files[path]
        if isinstance(record, _Preserved):
            blob = record.blob
        else:
            text = record if isinstance(record, str) else _dump(record)
            blob = git.out("hash-object", "-w", "--stdin", input_text=text).strip()
        entries.append((path, blob))
    # mktree cannot nest; build holdings/ as a subtree.
    sub = [e for e in entries if e[0].startswith("holdings/")]
    top = [e for e in entries if not e[0].startswith("holdings/")]
    lines = ["100644 blob %s\t%s" % (blob, path.split("/", 1)[1]) for path, blob in sub]
    subtree = git.out("mktree", "--missing", input_text="\n".join(lines) + "\n").strip() if lines else EMPTY_TREE
    root_lines = ["100644 blob %s\t%s" % (blob, path) for path, blob in top]
    root_lines.append("040000 tree %s\tholdings" % subtree)
    tree = git.out("mktree", "--missing", input_text="\n".join(root_lines) + "\n").strip()
    args = ["commit-tree", tree, "-m", message]
    if parent:
        args[2:2] = ["-p", parent]
    return git.out(*args, env=_commit_env(when)).strip()


def holding_write(git, key, holder, action, ttl_s=1800, note="", now=None,
                  remote="origin", branch=HOLDINGS_BRANCH, push=True, attempts=3,
                  repository=None):
    """take / renew / release one change key. Returns what the branch now says."""
    if action not in ("take", "renew", "release"):
        raise ValueError("action must be take, renew, or release")
    if not isinstance(holder, str) or not holder.strip():
        raise ValueError("holder must be non-empty text")
    if type(ttl_s) is not int or not 1 <= ttl_s <= 7200:
        raise ValueError("ttl must be between 1 and 7200 seconds")
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise ValueError("attempts must be between 1 and 10")
    if repository is not None:
        repository = claim_repository(repository)
    fixed_now = now
    path = _holding_path(key)
    tip = None
    for _ in range(attempts):
        tip = _remote_tip(git, branch, remote)
        if tip:
            git.fetch([tip], remote, depth=1)
        try:
            holdings = _read_holdings(git, tip, want=path)
        except HoldingUnreadable as exc:
            return {"ok": False, "key": key, "tip": tip,
                    "reason": "the current holding for this key could not be read; nothing written (%s)" % exc}
        observed_now = fixed_now if fixed_now is not None else _now()
        current = holdings.get(path)
        live = _holding_live(current, observed_now)
        if action == "take" and live and current.get("holder") != holder:
            return {"ok": False, "key": key, "held_by": current.get("holder"),
                    "heartbeat_at": current.get("heartbeat_at"), "ttl_s": current.get("ttl_s"),
                    "tip": tip}
        if action in ("renew", "release") and (not current or current.get("holder") != holder):
            return {"ok": False, "key": key, "held_by": (current or {}).get("holder"),
                    "reason": "not the current holder", "tip": tip}
        stamp_moment = observed_now
        if (current or {}).get("holder") == holder:
            for prior_text in ((current or {}).get("heartbeat_at"), (current or {}).get("taken_at")):
                prior = _parse_ts(prior_text)
                if prior is not None and prior > stamp_moment:
                    stamp_moment = prior
        stamp = _iso(stamp_moment)
        # A record that is not a holding of this schema (for example a legacy placeholder)
        # is vacant: nothing from it is carried into the new record and no holder is invented.
        record = dict(current) if isinstance(current, dict) and current.get("schema") == HOLDING_SCHEMA else {}
        record.update({"schema": HOLDING_SCHEMA, "key": key, "holder": holder,
                       "heartbeat_at": stamp, "ttl_s": int(ttl_s)})
        if repository is not None:
            record["repository"] = repository
        if action == "take" and (not live or (current or {}).get("holder") != holder):
            record["taken_at"] = stamp
            if current and current.get("holder") and current.get("holder") != holder:
                record["previous_holder"] = current.get("holder")
        record["state"] = "RELEASED" if action == "release" else "HELD"
        if note:
            record["note"] = note[:300]
        holdings[path] = record
        message = "%s %s by %s" % (action, key, holder)
        commit = _holdings_commit(git, tip, holdings, message, stamp_moment)
        if not push:
            return {"ok": True, "key": key, "commit": commit, "pushed": False,
                    "record": record,
                    "push_line": _push_line(git.root, remote, commit, branch)}
        done = _push_ref(git, remote, commit, branch)
        if done.returncode == 0:
            return {"ok": True, "key": key, "commit": commit, "pushed": True, "record": record}
        if "non-fast-forward" not in done.stderr and "fetch first" not in done.stderr:
            return {"ok": False, "key": key, "reason": done.stderr.strip()[-300:]}
        # Someone else wrote first; re-read and decide again with a fresh runtime clock.
    return {"ok": False, "key": key, "reason": "branch kept moving; retry",
            "conflict": "non-fast-forward", "attempts": int(attempts), "tip": tip}


def holdings_list(git, remote="origin", branch=HOLDINGS_BRANCH, now=None, key=None):
    """List all holdings, or read only one key without materializing other blobs."""
    now = now or _now()
    tip = _remote_tip(git, branch, remote)
    if tip:
        # Current holdings require the tip tree, never the ledger's ancestors.
        # Keep history-aware build/drift and publication fetches unchanged.
        git.fetch([tip], remote, depth=1)
    if key is None:
        holdings = _read_holdings(git, tip)
    else:
        holdings = {}
        path = _holding_path(key)
        blob = _holding_entries(git, tip, path).get(path) if tip else None
        if blob is not None:
            try:
                holdings[path] = _read_holding(git, tip, path, blob)
            except HoldingUnreadable:
                holdings[path] = _Preserved(blob)
    rows = []
    for path, record in sorted(holdings.items()):
        live = _holding_live(record, now)
        row = {"key": path[len("holdings/"):-5], "holder": record.get("holder"),
               "state": record.get("state"), "live": live,
               "heartbeat_at": record.get("heartbeat_at"), "ttl_s": record.get("ttl_s"),
               "note": record.get("note", "")}
        if isinstance(record, _Preserved):
            row["unreadable"] = True  # reported in the listing only; the blob itself is carried untouched
        if record.get("repository") is not None:
            row["repository"] = record["repository"]
        rows.append(row)
    return {"branch": branch, "tip": tip, "holdings": rows}


# --------------------------------------------------------------------------
# CLI


def _git_root(path):
    return path or ROOT


def main(argv=None):
    ap = argparse.ArgumentParser(description="Commons coordination state (first draft; fix freely)")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--git-root", default=None, help="clone to read trees from (default: this checkout)")
    ap.add_argument("--remote", default="origin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="compute state and write the two files")
    b.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "coordination-state"))
    b.add_argument("--closed-hours", type=int, default=36)
    b.add_argument("--review-capacity", type=int, default=None, help="observed available GPT review batches; 0 means exhausted")
    b.add_argument("--composed-trees", action="store_true",
                   help="also write the composed tree for every disjoint pull request")
    p = sub.add_parser("publish", help="build and commit to the state/coordination branch")
    p.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "coordination-state"))
    p.add_argument("--closed-hours", type=int, default=36)
    p.add_argument("--review-capacity", type=int, default=None)
    p.add_argument("--composed-trees", action="store_true")
    p.add_argument("--no-push", action="store_true", help="commit locally and print the push line")
    p.add_argument("--from", dest="from_dir", default="",
                   help="publish an existing build directory instead of building again")
    p.add_argument("--split", action="store_true",
                   help="with --no-push: one commit per file, for size-capped push inspection")
    d = sub.add_parser("drift", help="certificate for one pull request")
    d.add_argument("--pr", type=int, required=True)
    t = sub.add_parser("take", help="hold a change key")
    t.add_argument("key")
    t.add_argument("--holder", required=True)
    t.add_argument("--ttl", type=int, default=1800)
    t.add_argument("--note", default="")
    t.add_argument("--no-push", action="store_true")
    for name in ("renew", "release"):
        r = sub.add_parser(name)
        r.add_argument("key")
        r.add_argument("--holder", required=True)
        r.add_argument("--no-push", action="store_true")
    sub.add_parser("holders", help="list change holdings")
    k = sub.add_parser("key", help="print the change key for a marker, PR or content digest")
    k.add_argument("--marker", default="")
    k.add_argument("--pr", type=int)
    k.add_argument("--content", default="")
    ap.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    args = ap.parse_args(argv)

    global VERBOSE
    VERBOSE = not args.quiet
    git = Git(_git_root(args.git_root))
    if args.cmd == "key":
        print(change_key(args.marker, args.pr, args.content))
        return 0
    if args.cmd in ("take", "renew", "release"):
        try:
            result = holding_write(git, args.key, args.holder, args.cmd,
                                   ttl_s=getattr(args, "ttl", 1800), note=getattr(args, "note", ""),
                                   remote=args.remote, push=not args.no_push)
        except (ValueError, GitError) as exc:
            result = {"ok": False, "key": args.key, "reason": str(exc)}
        print(json.dumps(result, indent=1))
        return 0 if result.get("ok") else 1
    if args.cmd == "holders":
        try:
            result = holdings_list(git, args.remote)
        except GitError as exc:
            result = {"ok": False, "reason": str(exc)}
        print(json.dumps(result, indent=1))
        return 0 if result.get("ok", True) else 1
    if args.cmd == "publish" and args.from_dir:
        texts, head = read_outputs(args.from_dir)
        result = publish(git, None, args.repo, push=not args.no_push, remote=args.remote,
                         texts=texts, split=args.split)
        print(json.dumps({"head": head, "publish": result}, indent=1))
        return 0 if (result.get("pushed") or result.get("superseded") or args.no_push) else 1
    github = GitHub(args.repo, discover_token())
    if args.cmd == "drift":
        data = github.graphql(
            "query($owner:String!, $name:String!, $n:Int!) { repository(owner:$owner, name:$name) {"
            " pullRequest(number:$n) { headRefOid baseRefName baseRefOid } } }",
            {"owner": github.owner, "name": github.name, "n": args.pr})
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        base_ref = pull.get("baseRefName") or "main"
        tip = (fetch_tips(github, [base_ref]).get(base_ref) or {}).get("sha") or UNKNOWN
        head = pull.get("headRefOid") or UNKNOWN
        git.fetch([tip, head], args.remote)
        cert = drift_certificate(git, tip, head, pull.get("baseRefOid"))
        cert["base_ref"] = base_ref
        print(json.dumps(cert, indent=1))
        return 0
    payload = build(git, github, closed_hours=args.closed_hours, composed=args.composed_trees,
                    review_capacity=args.review_capacity)
    head = write_outputs(payload, args.out)
    if args.cmd == "build":
        print(json.dumps(head, indent=1))
        return 0
    result = publish(git, payload, args.repo, push=not args.no_push, remote=args.remote,
                     split=args.split)
    print(json.dumps({"head": head, "publish": result}, indent=1))
    return 0 if (result.get("pushed") or result.get("superseded") or args.no_push) else 1


if __name__ == "__main__":
    sys.exit(main())
