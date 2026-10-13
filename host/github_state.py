#!/usr/bin/env python3
"""Repository state as a small static file the board can read.

The board mirrors what was said. This is what the repository is doing: how many
pull requests are open, how deep the runner queue is, which lanes are waiting
and which have been waiting longest. None of that is visible from the Commons
bakes, and at this pace the queue depth in particular changes what a session
should do next.

Network stays in the workflow. This module takes what a `gh api` call already
returned and normalises it, so it is stdlib-only, testable offline, and cannot
invent a number it did not receive.

 python3 -m host.github_state --write \
 --pulls pulls.json --closed closed.json --open-prs 106 --open-issues 3 \
 --counts-source graphql --runs-queued 2284 --runs-in-progress 18 \
 --observed-at 2026-09-10T21:00:00Z

What a session gets from one read, besides the counts:

* Every listed pull carries `head_sha`, `updated_at` and `base`. A session that
  reviewed, claimed or composed a head can tell whether it has moved without a
  GitHub call of its own. `updated_at` is GitHub's clock for that pull, not the
  moment this file was built.
* `open_heads` maps every listed open pull to its head SHA. When
  `pulls_listing` is COMPLETE, a number missing from it is not open.
* `recently_closed` names the newest closures, MERGED or CLOSED, with the head
  that closed and, for merges, GitHub's `merge_commit_sha`. The branch head is
  not the landed commit after a merge, squash or rebase. It comes from the most
  recently updated page of closed pulls, so it shows recent transitions. It is
  not a history.

Honesty rules, the same ones the delta shards keep:

* A count that was not supplied reads UNKNOWN. It never reads zero, because
  "no open pull requests" and "nobody asked" are different facts.
* If the pull request listing cannot be read, the listing sections are absent
  and named in `degraded` rather than rendered as an empty queue.
  A successful zero-result JSON Lines export is an empty file; it is accepted
  only when the caller explicitly supplies `--pulls-complete`.
* The listing says whether it is every open pull request (`pulls_listing`
  COMPLETE) or a subset (PARTIAL). "Longest open" is only published from a
  complete listing: the oldest row of a newest-first page is not the oldest
  open pull request, so a partial listing names itself in `degraded` and leaves
  that section out instead of mislabelling it.
* The open count and the listing are separate observations. When the listing
  holds more unique open pulls than the count supplied, the count is the stale
  one, and `degraded` says `open-count-below-listing`. The count is still
  published exactly as given, and `counts_source` names the road it came from
  (`graphql` is the repository's own count; `search` is an index that can
  lag).
* `unchanged_since` is the moment the content last actually moved. A rebuild
  that observed the same state leaves the file completely alone, so a quiet
  cycle produces no diff and the timestamp keeps meaning something. The file
  carries no observation time of its own, because one would change on every
  bake and put a commit on main every cycle. When the bake last ran is the
  newest run of `.github/workflows/commons-board.yml` in the Actions API.
* The file is replaced atomically. An interrupted or failed write leaves the
  previous bytes exactly as they were, so a masked producer failure in the
  workflow can never stage half a file.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "commons-github-state/v1"
OUT = "feed/github.json"

# Enough to act on without turning the file into a listing of everything.
NEWEST_N = 10
OLDEST_N = 5
CLOSED_N = 15

UNKNOWN = "UNKNOWN"

_HEX = frozenset("0123456789abcdef")


def _parse_ts(text):
    text = (text or "").strip()
    if not text:
        return None
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = _dt.datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _count(value):
    if value is None:
        return UNKNOWN
    try:
        return int(value)
    except (TypeError, ValueError):
        return UNKNOWN


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _sha(value):
    """A full commit id as GitHub sent it, or UNKNOWN.

    Only a complete hexadecimal object id is kept (40 characters, or 64 for a
    SHA-256 repository). Anything shorter would let two heads look equal.
    """
    text = _text(value).lower()
    if len(text) in (40, 64) and set(text) <= _HEX:
        return text
    return UNKNOWN


def _ref(side):
    return (_text((side or {}).get("ref")) if isinstance(side, dict) else "") or UNKNOWN


def _pull(row):
    """One pull request, carrying only durable facts.

    Deliberately no age field. An age is computed against the moment of
    observation, so carrying one would make this file differ on every rebuild
    and commit a fresh diff every five minutes forever. The viewer has a clock;
    `created_at` plus that clock is a better age than a stamped one anyway.

    `head_sha` and `updated_at` are the pull's own facts, not observation
    times. They move when the pull moves, which is what a session holding a
    reviewed or claimed head needs to see.
    """
    user = row.get("user") or {}
    head = row.get("head") if isinstance(row.get("head"), dict) else {}
    return {
        "number": row.get("number"),
        "title": _text(row.get("title"))[:120],
        "author": _text(user.get("login") if isinstance(user, dict) else "") or UNKNOWN,
        "draft": bool(row.get("draft")),
        # Kept verbatim when present, and only ordered when it truly parses.
        "created_at": _text(row.get("created_at")) or UNKNOWN,
        "updated_at": _text(row.get("updated_at")) or UNKNOWN,
        "branch": _ref(head),
        "head_sha": _sha(head.get("sha")),
        "base": _ref(row.get("base")),
    }


def _closed(row):
    """One closure with its source head and provider-reported landed commit."""
    pull = _pull(row)
    merged_at = _text(row.get("merged_at"))
    merged = _parse_ts(merged_at) is not None
    return {
        "number": pull["number"],
        "title": pull["title"],
        "author": pull["author"],
        "state": "MERGED" if merged else "CLOSED",
        "closed_at": _text(row.get("closed_at")) or UNKNOWN,
        "updated_at": pull["updated_at"],
        "merged_at": merged_at if merged else None,
        "branch": pull["branch"],
        "head_sha": pull["head_sha"],
        # GitHub can return a speculative merge commit for an unmerged pull.
        # Only retain this as a landed commit when merged_at confirms a merge.
        "merge_commit_sha": _sha(row.get("merge_commit_sha")) if merged else None,
        "base": pull["base"],
    }


def _recently_closed(closed):
    """Newest closures first, each pull once, ordered only on a real closed_at."""
    rows, seen = [], set()
    for row in closed:
        if not isinstance(row, dict):
            continue
        item = _closed(row)
        key = item["number"]
        if key is None or key in seen:
            continue
        seen.add(key)
        if _parse_ts(item["closed_at"]) is None:
            continue
        rows.append(item)
    rows.sort(key=lambda r: (_parse_ts(r["closed_at"]),
                             r["number"] if isinstance(r["number"], int) else -1),
              reverse=True)
    return rows[:CLOSED_N]


def _listing_state(rows, open_prs, complete):
    """COMPLETE, PARTIAL or UNKNOWN for a listing of `rows` open pull requests.

    `complete` means the pagination command reached its end successfully, not
    that a moving API represented one atomic snapshot. When an independently
    measured numeric open count says there are more open PRs than the unique
    rows we retained, that contradiction wins and coverage is PARTIAL. This is
    the page-shift race: a PR opening/closing between pages can duplicate a row
    even though `gh api --paginate` exits successfully.
    """
    if isinstance(open_prs, int) and len(rows) < open_prs:
        return "PARTIAL"
    if complete is True:
        return "COMPLETE"
    if isinstance(open_prs, int):
        return "COMPLETE"
    return UNKNOWN


def build(pulls, counts, now=None, degraded=None, complete=None, closed=None):
    """Normalise a pulls listing plus supplied counts into the payload.

    `now` is accepted and deliberately unused. Nothing observation-relative is
    allowed into the payload, so two builds of the same state at different
    clocks are byte-identical and a quiet rebuild produces no diff. The
    parameter stays so callers do not have to know that.

    `closed` is the closed-pull listing, or None when it was not read. Only a
    listing that was read produces `recently_closed`; the caller names an
    unreadable one in `degraded`.
    """
    payload = {
        "schema": SCHEMA,
        "repository": counts.get("repository") or UNKNOWN,
        "counts": {
            "open_pull_requests": _count(counts.get("open_prs")),
            "open_issues": _count(counts.get("open_issues")),
            "runs_queued": _count(counts.get("runs_queued")),
            "runs_in_progress": _count(counts.get("runs_in_progress")),
        },
        "counts_source": _text(counts.get("source")) or UNKNOWN,
        "degraded": list(degraded or []),
    }
    if closed is not None:
        payload["recently_closed"] = _recently_closed(closed)

    queued = payload["counts"]["runs_queued"]
    running = payload["counts"]["runs_in_progress"]
    # Reported so a session can decide whether waiting on a check is realistic.
    # It is a ratio of two observations, not a prediction of anything.
    if isinstance(queued, int) and isinstance(running, int) and running > 0:
        payload["queue_depth_per_runner"] = round(queued / running, 1)
    else:
        payload["queue_depth_per_runner"] = UNKNOWN

    if pulls is None:
        payload["pulls_listed"] = UNKNOWN
        payload["pulls_listing"] = UNKNOWN
        payload["degraded"] = sorted(set(payload["degraded"]))
        return payload

    rows, seen = [], set()
    for row in pulls:
        if not isinstance(row, dict):
            continue
        pull = _pull(row)
        # A pull that opens or closes between page reads shifts every later
        # page by one, so the same row can arrive twice. Count it once.
        key = pull["number"]
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        rows.append(pull)
    # Order only on a timestamp that actually parses. A non-empty but malformed
    # value sorts as a plain string, and most malformed values sort above every
    # real ISO date, which would put the one broken row at the top of the page.
    dated = [r for r in rows if _parse_ts(r["created_at"])]
    dated.sort(key=lambda r: r["created_at"], reverse=True)
    open_count = payload["counts"]["open_pull_requests"]
    listing = _listing_state(rows, open_count, complete)
    if isinstance(open_count, int) and len(rows) > open_count:
        # More unique open pulls were listed than the count says exist. The
        # listing is a direct read, so the count is the stale observation;
        # publish it as given and say that it disagrees.
        payload["degraded"].append("open-count-below-listing")
    payload["pulls_listed"] = len(rows)
    payload["pulls_listing"] = listing
    payload["undatable_pulls"] = sorted(
        r["number"] for r in rows if r not in dated and r["number"] is not None)
    # Every listed open pull and its head, one line each, so "has the head I
    # hold moved, and is the pull still open?" is a single read.
    payload["open_heads"] = {
        str(r["number"]): r["head_sha"] for r in rows
        if isinstance(r["number"], int) and not isinstance(r["number"], bool)
    }
    payload["newest_pulls"] = dated[:NEWEST_N]
    if listing == "COMPLETE":
        payload["longest_open"] = list(reversed(dated[-OLDEST_N:])) if dated else []
    else:
        # The oldest row of a subset is not the longest-open pull request.
        payload["degraded"].append("pulls-partial" if listing == "PARTIAL"
                                   else "pulls-coverage-unknown")
    payload["drafts"] = sum(1 for r in rows if r["draft"])
    payload["degraded"] = sorted(set(payload["degraded"]))
    return payload


def _dump(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _stable_view(payload):
    """Everything except the moment it was written."""
    return {k: v for k, v in payload.items() if k != "unchanged_since"}


def write(root, payload, now):
    path = os.path.join(root, *OUT.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prior = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                prior = json.load(fh)
        except Exception:
            prior = None

    if isinstance(prior, dict) and _stable_view(prior) == _stable_view(payload):
        # Same state as last time. Leaving the file untouched keeps the diff
        # clean and keeps unchanged_since meaning "when this last moved".
        return False

    payload = dict(payload, unchanged_since=now)
    _replace_atomically(path, _dump(payload))
    return True


def _replace_atomically(path, text):
    """Write `text` to `path` so a reader sees the old bytes or the new, never half.

    Same directory, flushed and fsynced, then os.replace. Any failure removes
    the temporary file and leaves the previous file untouched.
    """
    folder = os.path.dirname(path)
    tmp = os.path.join(folder, ".%s.%d.tmp" % (os.path.basename(path), os.getpid()))
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_pulls(path, *, empty_complete=False):
    """A JSON array, or JSON Lines containing pull objects or page arrays.

    Returns None when the file holds neither, so the caller names the listing
    as degraded instead of reading garbage as an empty queue.
    An empty JSON Lines export is valid only with explicit completion evidence.
    Each row must carry a positive integer GitHub number; other provider JSON
    must not become a complete listing without usable pull identities.
    """
    def valid_rows(value):
        return isinstance(value, list) and all(
            isinstance(row, dict) and type(row.get("number")) is int
            and row["number"] > 0 for row in value)

    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.strip()
    if not stripped:
        return [] if empty_complete else None
    if stripped[0] == "[":
        try:
            value = json.loads(stripped)
        except ValueError:
            # Multiple page arrays may be exported one per JSON Lines record.
            # The line reader below still rejects an invalid or partial page.
            pass
        else:
            return value if valid_rows(value) else None
    rows = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            return None
        if isinstance(value, list):
            rows.extend(value)
        elif isinstance(value, dict):
            rows.append(value)
        else:
            return None
    return rows if valid_rows(rows) else None


def _read_closed(path):
    """The closed-pull listing, [] for a successful read of nothing, or None.

    The workflow deletes the file when its API call fails, so a missing file
    means unread. An empty file is a call that succeeded with no closed pulls.
    """
    try:
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            if not fh.read().strip():
                return []
        return _read_pulls(path)
    except Exception:
        return None


def self_test():
    now = "2026-09-10T21:00:00Z"
    pulls = [
        {"number": 3, "title": "newest", "user": {"login": "a"},
         "created_at": "2026-09-10T20:00:00Z", "head": {"ref": "b3"}},
        {"number": 1, "title": "oldest", "user": {"login": "b"}, "draft": True,
         "created_at": "2026-09-01T00:00:00Z", "head": {"ref": "b1"}},
        {"number": 2, "title": "middle", "user": {"login": "c"},
         "created_at": "2026-09-05T00:00:00Z", "head": {"ref": "b2"}},
        {"number": 4, "title": "undated", "user": {"login": "d"}},
    ]
    counts = {"repository": "o/r", "open_prs": 106, "open_issues": 3,
              "runs_queued": 2284, "runs_in_progress": 18}
    complete_counts = dict(counts, open_prs=len(pulls))
    out = build(pulls, complete_counts, now, complete=True)

    assert out["counts"]["open_pull_requests"] == len(pulls)
    assert out["counts"]["runs_queued"] == 2284
    assert out["queue_depth_per_runner"] == round(2284 / 18, 1)
    assert [p["number"] for p in out["newest_pulls"]] == [3, 2, 1], out["newest_pulls"]
    assert out["longest_open"][0]["number"] == 1, out["longest_open"]
    assert out["pulls_listed"] == 4
    assert out["pulls_listing"] == "COMPLETE"
    assert out["undatable_pulls"] == [4], out["undatable_pulls"]
    assert out["drafts"] == 1
    assert out["newest_pulls"][0]["branch"] == "b3"
    assert _dump(build(pulls, complete_counts, "2026-09-11T09:00:00Z", complete=True)) == _dump(out)

    # Four rows against 106 counted open: a subset, so no longest-open claim,
    # even if the pagination command itself reached its end successfully.
    partial = build(pulls, counts, now, complete=True)
    assert partial["pulls_listing"] == "PARTIAL", partial["pulls_listing"]
    assert "longest_open" not in partial
    assert partial["degraded"] == ["pulls-partial"], partial["degraded"]
    assert [p["number"] for p in partial["newest_pulls"]] == [3, 2, 1]

    # A row repeated across a page boundary is counted once. If the independent
    # count says the unique listing is short, successful pagination still does
    # not authorize longest_open.
    twice = build(pulls + pulls[:2], complete_counts, now, complete=True)
    assert twice["pulls_listed"] == 4, twice["pulls_listed"]
    shifted = build(pulls[:3] + pulls[1:2], complete_counts, now, complete=True)
    assert shifted["pulls_listing"] == "PARTIAL", shifted["pulls_listing"]
    assert shifted["pulls_listed"] == 3, shifted["pulls_listed"]
    assert "longest_open" not in shifted

    sparse = build(None, {"repository": "o/r"}, now)
    assert sparse["counts"]["open_pull_requests"] == UNKNOWN
    assert sparse["counts"]["runs_queued"] == UNKNOWN
    assert sparse["queue_depth_per_runner"] == UNKNOWN
    assert sparse["pulls_listed"] == UNKNOWN
    assert "newest_pulls" not in sparse

    zeroed = build([], {"open_prs": 0, "runs_queued": 0, "runs_in_progress": 0}, now)
    assert zeroed["counts"]["open_pull_requests"] == 0
    assert zeroed["pulls_listed"] == 0
    assert zeroed["queue_depth_per_runner"] == UNKNOWN

    named = build(None, {}, now, degraded=["pulls"])
    assert named["degraded"] == ["pulls"]

    # Heads, bases and GitHub's own update clock ride on every listed pull, and
    # only a complete object id is kept.
    headed = [dict(pulls[0], updated_at="2026-09-10T20:30:00Z",
                   head={"ref": "b3", "sha": "A" * 40}, base={"ref": "main"}),
              dict(pulls[1], head={"ref": "b1", "sha": "abc"})]
    heads = build(headed, {"open_prs": 2}, now, complete=True)
    assert heads["newest_pulls"][0]["head_sha"] == "a" * 40, heads["newest_pulls"]
    assert heads["newest_pulls"][0]["updated_at"] == "2026-09-10T20:30:00Z"
    assert heads["newest_pulls"][0]["base"] == "main"
    assert heads["open_heads"] == {"3": "a" * 40, "1": UNKNOWN}, heads["open_heads"]

    # A listing longer than the count: the count is the stale observation. It
    # is published as given, with the road it came from and a named mismatch.
    low = build(pulls, dict(counts, open_prs=2, source="search"), now, complete=True)
    assert "open-count-below-listing" in low["degraded"], low["degraded"]
    assert low["counts"]["open_pull_requests"] == 2
    assert low["counts_source"] == "search"
    assert "longest_open" in low
    assert out["counts_source"] == UNKNOWN

    # Closures: newest first, a merge named as a merge, an undated row left out.
    closed = [
        {"number": 7, "closed_at": "2026-09-10T19:00:00Z", "merged_at": None,
         "head": {"sha": "b" * 40}},
        {"number": 8, "closed_at": "2026-09-10T20:00:00Z",
         "merged_at": "2026-09-10T20:00:00Z", "head": {"sha": "c" * 40}},
        {"number": 9, "closed_at": ""},
    ]
    shut = build(pulls, complete_counts, now, complete=True, closed=closed)
    assert [(r["number"], r["state"]) for r in shut["recently_closed"]] == \
        [(8, "MERGED"), (7, "CLOSED")], shut["recently_closed"]
    assert shut["recently_closed"][1]["merged_at"] is None
    assert shut["recently_closed"][0]["head_sha"] == "c" * 40
    assert "recently_closed" not in out

    assert _dump(build(pulls, complete_counts, now, complete=True)) == _dump(out)
    print("github_state self-test: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--pulls", help="open pull requests: a JSON array, or JSON "
                    "Lines as `gh api --paginate --jq '.[]|...'` writes them")
    ap.add_argument("--pulls-complete", action="store_true",
                    help="pagination reached its end; a contradictory numeric "
                    "--open-prs count still downgrades coverage")
    ap.add_argument("--closed", help="recently updated closed pull requests, "
                    "in the same shapes as --pulls; a missing or unreadable "
                    "file is named in degraded as closed-pulls")
    ap.add_argument("--counts-source", default="",
                    help="the road the open counts came from, e.g. graphql or search")
    ap.add_argument("--repository", default="")
    ap.add_argument("--open-prs")
    ap.add_argument("--open-issues")
    ap.add_argument("--runs-queued")
    ap.add_argument("--runs-in-progress")
    ap.add_argument("--observed-at", default="")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    now = args.observed_at.strip() or _dt.datetime.now(
        _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pulls, degraded = None, []
    if args.pulls:
        try:
            pulls = _read_pulls(args.pulls, empty_complete=args.pulls_complete)
            if pulls is None:
                degraded = ["pulls"]
        except Exception:
            pulls, degraded = None, ["pulls"]
    else:
        degraded = ["pulls"]

    closed = None
    if args.closed:
        closed = _read_closed(args.closed)
        if closed is None:
            degraded.append("closed-pulls")

    payload = build(pulls, {
        "repository": args.repository,
        "open_prs": args.open_prs,
        "open_issues": args.open_issues,
        "runs_queued": args.runs_queued,
        "runs_in_progress": args.runs_in_progress,
        "source": args.counts_source,
    }, now, degraded, complete=True if args.pulls_complete else None,
        closed=closed)

    if args.write:
        changed = write(args.root, payload, now)
        counts = payload["counts"]
        print("github_state: %s open PRs, %s queued runs, %s in progress — %s"
              % (counts["open_pull_requests"], counts["runs_queued"],
                 counts["runs_in_progress"], "written" if changed else "unchanged"))
        if payload["degraded"]:
            sys.stderr.write("github_state: degraded sources: %s\n"
                             % ", ".join(payload["degraded"]))
        return 0

    print(_dump(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
