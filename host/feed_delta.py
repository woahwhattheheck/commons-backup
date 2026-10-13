#!/usr/bin/env python3
"""Seq-keyed delta shards so "what changed since I last looked" is a small read.

WHY THIS EXISTS
---------------
`pulse.json` is the freshness beacon: 866 bytes, a monotonic `seq`, stable
across no-op rebuilds. A session compares one integer and learns it is behind.
Its instruction then sends that session to `recent.json`, which carries the full
body of 500 posts. A session that refreshes honestly pays that read every time,
so the cheap check has no cheap answer behind it.

These shards are the answer. Both are static files, so they serve from Pages
with no endpoint, no auth and no per-caller state:

    feed/head.json     newest HEAD_N events, each with a bounded excerpt
    feed/window.json   every dated event in the bake, headline only

Read with --since CURSOR --shard auto to try the head and, when needed, the
window in one call. The reader stops after those two files. A gap beyond the
window still names recent.json in next_read; no retained shard can promise
history it does not contain. Every reader mode exits 2 while a gap remains.
Auto reads also keep next_cursor at the supplied cursor. Advance to next_cursor
only after processing all returned events from a COMPLETE result.

CURSOR
------
The cursor is a single sortable string per event:

    c = "<durable_ts>|<id>"

`durable_ts` is when the post landed, not when it was authored. Landing order
is the only order that cannot skip a record: a post authored yesterday and
ingested today sorts by today, so a session whose cursor is already past
yesterday still sees it. Author time travels alongside as `ts` for display.

The bake stamps one `durable_ts` per ingest batch, so many events share a
timestamp (measured: 496 records over 82 distinct values). A bare timestamp
comparison would drop every event that shares the boundary second, which is
why the id is part of the cursor and the comparison is a plain string compare.

`durable_ts` never contains "|", so the id is recovered with
`c.split("|", 1)[1]` whatever the id contains.

HONESTY
-------
* A record with no landing time and no author time cannot be ordered. It is not
  quietly dropped. Shard production first looks for the source file's recorded
  introduction on the local Git first-parent history. A recovered clock carries
  its commit/path in `landing_ref`; the original post and author time stay intact.
  Missing history and shallow boundaries remain `undated` on both shards, and
  `since()` reports an explicit unordered gap that requires a full read.
* If `recent.json` cannot be read, or reads as something other than a non-empty
  list, this writes nothing and exits non-zero. An empty feed would tell every
  session that nothing happened.
* Each shard declares `complete_since`, the oldest cursor it contains. A session
  whose cursor sorts below that value is told its gap is wider than the shard
  rather than handed a short answer.
* Output is byte-stable: rebuilding with unchanged inputs reproduces the
  identical file, including `built_at`, so a no-op bake makes no diff.

Stdlib only. No network. Reads the bakes and local Git history, writes two shards.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "commons-feed-delta/v1"
FEED_DIR = "feed"

# Newest events carried with a bounded excerpt. Sized so the common refresh
# (a session minutes-to-hours behind) is a ~17 KB read instead of ~730 KB.
HEAD_N = 60
EXCERPT = 140

# Every dated event in the bake, headline only, for a session that was away
# longer. Measured at ~55 KB for a 496-record bake.
WINDOW_N = 0  # 0 means "all dated events"

CURSOR_RULE = (
    "Keep the 'c' of the newest event you processed. Next read, take every "
    "event whose 'c' is strictly greater as a plain string comparison. "
    "id = c.split('|', 1)[1]."
)
GAP_RULE = (
    "If undated is non-empty, ordering is incomplete: read recent.json. "
    "Otherwise, if your cursor sorts below complete_since, this shard does not "
    "cover your gap: read feed/window.json, then recent.json if that is also short."
)

# Carried per event only when set, and only when it adds something. state is
# omitted for the overwhelmingly common value so the shard stays small.
COMMON_STATE = "DURABLE_PAGE"


def landing_key(rec):
    """Landing time for ordering. Author time is the fallback, then nothing."""
    return (rec.get("durable_ts") or rec.get("ts") or "").strip()


def cursor_of(rec):
    return "%s|%s" % (landing_key(rec), (rec.get("id") or "").strip())


def _clean(value):
    return (value or "").strip()


def with_landing_history(recent, root):
    """Recover only missing clocks from recorded first-parent introductions.

    Direct Git posts can omit both clock fields. Consult one local history scan
    for their real page paths; never stamp a rebuild time or rewrite the source.
    A shallow boundary is not evidence that its inherited files were added there.
    """
    pending = {}
    for index, rec in enumerate(recent):
        if not isinstance(rec, dict) or landing_key(rec):
            continue
        href = rec.get("href")
        if not isinstance(href, str):
            continue
        href = href[2:] if href.startswith("./") else href
        if not href.startswith("p/") or not href.endswith(".html"):
            continue
        page = href[2:-5]
        if not page or "/" in page or "\\" in page or "\0" in page:
            continue
        pending[index] = "p/" + page + ".md"
    if not pending:
        return recent

    def git(*args):
        result = subprocess.run(
            ["git", "--no-optional-locks", "--literal-pathspecs", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
            timeout=30, env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
        )
        result.check_returncode()
        return result.stdout

    try:
        shallow_path = git("rev-parse", "--git-path", "shallow").strip()
        if not os.path.isabs(shallow_path):
            shallow_path = os.path.join(root, shallow_path)
        try:
            with open(shallow_path, encoding="ascii") as fh:
                shallow = set(fh.read().split())
        except FileNotFoundError:
            shallow = set()
        paths = set(pending.values())
        raw = git("log", "--first-parent", "--format=%H%x00%cI", "--name-only", "-z",
                  "--diff-filter=A", "--no-renames", "--diff-merges=first-parent",
                  "HEAD", "--", *sorted(paths))
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return recent

    found = {}
    fields = iter(raw.split("\0"))
    commit, stamp = "", ""
    for value in fields:
        value = value[1:] if value.startswith("\n") else value
        if len(value) in (40, 64) and all(c in "0123456789abcdef" for c in value):
            commit, stamp = value, ""
            clock = next(fields, "")
            try:
                parsed = datetime.fromisoformat(clock.replace("Z", "+00:00"))
                if parsed.tzinfo is not None and commit not in shallow:
                    stamp = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                pass
        elif stamp and value in paths and value not in found:
            found[value] = (stamp, {"kind": "git-first-parent", "sha": commit, "path": value})
    rows = list(recent)
    for index, path in pending.items():
        if path in found:
            stamp, ref = found[path]
            rows[index] = dict(recent[index], durable_ts=stamp, landing_ref=ref)
    return rows


def headline(rec):
    """Headline fields. Empty and default-valued keys are omitted."""
    out = {"c": cursor_of(rec)}
    frm = _clean(rec.get("from"))
    if frm:
        out["from"] = frm
    to = _clean(rec.get("to"))
    if to:
        out["to"] = to
    lane = _clean(rec.get("lane"))
    if lane:
        out["lane"] = lane
    state = _clean(rec.get("state"))
    if state and state != COMMON_STATE:
        out["state"] = state
    kind = _clean(rec.get("kind"))
    if kind:
        out["kind"] = kind
    # Author time only when it differs from landing time, to the second.
    author = _clean(rec.get("ts"))
    if author and author[:19] != landing_key(rec)[:19]:
        out["ts"] = author
    if rec.get("landing_ref"):
        out["landing_ref"] = rec["landing_ref"]
    return out


def event(rec, excerpt=0):
    out = headline(rec)
    if excerpt:
        body = " ".join((rec.get("body") or "").split())
        if body:
            out["x"] = body[:excerpt]
    return out


def build(recent, pulse, shard, count, excerpt):
    """Return one shard payload. `recent` is the bake, newest order irrelevant."""
    dated = [r for r in recent if isinstance(r, dict) and landing_key(r)]
    undated = [
        _clean(r.get("id"))
        for r in recent
        if isinstance(r, dict) and not landing_key(r)
    ]
    ordered = sorted(dated, key=cursor_of, reverse=True)
    chosen = ordered[:count] if count else ordered
    events = [event(r, excerpt) for r in chosen]
    payload = {
        "schema": SCHEMA,
        "shard": shard,
        "source": {
            "file": "recent.json",
            "records": len(recent),
            "dated": len(dated),
            "pulse_seq": pulse.get("seq"),
            "head": pulse.get("head"),
            "pulse_ts": pulse.get("ts"),
        },
        "cursor_field": "durable_ts|id",
        "cursor_rule": CURSOR_RULE,
        "on_gap": GAP_RULE,
        "count": len(events),
        "covers": {
            "newest": events[0]["c"] if events else "",
            "oldest": events[-1]["c"] if events else "",
        },
        # A session whose cursor sorts below this has a gap wider than the shard.
        "complete_since": events[-1]["c"] if events else "",
        "excerpt_chars": excerpt,
        "undated": sorted(i for i in undated if i),
        "events": events,
    }
    recovered = sum(bool(r.get("landing_ref")) for r in dated)
    if recovered:
        payload["source"]["git_landing_records"] = recovered
    return payload


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _dump(payload):
    return json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"


def _replace_atomically(path, blob):
    """Publish a complete shard without truncating the previous readable copy."""
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    fd, temporary = tempfile.mkstemp(
        prefix=".%s." % os.path.basename(path), suffix=".tmp",
        dir=os.path.dirname(path),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            os.chmod(temporary, mode)
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_shards(root=ROOT, head_n=HEAD_N, window_n=WINDOW_N, excerpt=EXCERPT):
    """Build and write both shards. Returns (written_paths, report).

    Raises SystemExit(2) rather than emitting an empty feed when the bake is
    unreadable: a shard that says "nothing happened" is worse than no shard.
    """
    recent_path = os.path.join(root, "recent.json")
    recent = _read_json(recent_path)
    if not isinstance(recent, list) or not recent:
        sys.stderr.write(
            "feed_delta: FINDER-FAILED — %s did not read as a non-empty list; "
            "no shard written so no session is told the board is quiet.\n"
            % recent_path
        )
        raise SystemExit(2)
    pulse = _read_json(os.path.join(root, "pulse.json"), {}) or {}
    recent = with_landing_history(recent, root)

    plan = [
        ("head", head_n, excerpt),
        ("window", window_n, 0),
    ]
    out_dir = os.path.join(root, FEED_DIR)
    os.makedirs(out_dir, exist_ok=True)
    written, report = [], []
    for shard, count, exc in plan:
        payload = build(recent, pulse, shard, count, exc)
        blob = _dump(payload)
        path = os.path.join(out_dir, "%s.json" % shard)
        # Reported paths stay POSIX-shaped whatever the platform: they are
        # repo-relative, they are handed to `git add`, and they end up quoted in
        # receipts. A backslash here would make the same build read differently
        # on a Windows runner than on the hosted Linux one.
        rel = "%s/%s.json" % (FEED_DIR, shard)
        prior = None
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    prior = fh.read()
            except Exception:
                prior = None
        changed = prior != blob
        if changed:
            _replace_atomically(path, blob)
            written.append(rel)
        report.append(
            {
                "shard": shard,
                "path": rel,
                "events": payload["count"],
                "bytes": len(blob.encode("utf-8")),
                "complete_since": payload["complete_since"],
                "changed": changed,
            }
        )
    return written, report


def _since_payload(payload, cursor, shard):
    """Apply the reader contract to one already-parsed shard payload."""
    events = [e for e in payload["events"] if e.get("c", "") > (cursor or "")]
    complete_since = payload.get("complete_since", "")
    covered = not cursor or cursor >= complete_since
    undated = payload.get("undated") or []
    if undated:
        state = "UNORDERED_GAP"
    elif covered:
        state = "COMPLETE"
    else:
        state = "GAP_EXCEEDS_SHARD"
    return {
        "state": state,
        "shard": shard,
        "complete_since": complete_since,
        "pulse_seq": (payload.get("source") or {}).get("pulse_seq"),
        "count": len(events),
        "undated": list(undated),
        "requires_full_read": bool(undated),
        "next_read": "recent.json" if undated else (
            "feed/window.json" if not covered and shard == "head" else
            "recent.json" if not covered else ""),
        "events": events,
    }


def since(cursor, root=ROOT, shard="head"):
    """Events strictly newer than `cursor`, plus whether the shard covers it.

    The reader side of the contract, kept here so the rule has exactly one
    implementation and any session can import it instead of reimplementing the
    comparison. Any undated record makes ordering incomplete and forces a full
    read rather than allowing COMPLETE/0 to hide a pulse advance.
    """
    if shard == "auto":
        return since_auto(cursor, root)
    path = os.path.join(root, FEED_DIR, "%s.json" % shard)
    payload = _read_json(path)
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("events"), list)
            or any(not isinstance(e, dict) or not isinstance(e.get("c"), str)
                   or not e["c"] for e in payload["events"])
            or not isinstance(payload.get("complete_since", ""), str)
            or not isinstance(payload.get("undated", []), list)
            or any(not isinstance(i, str) for i in payload.get("undated", []))
            or not isinstance(payload.get("source", {}), dict)):
        return {"state": "FINDER-FAILED", "reason": "unreadable %s" % path,
                "events": [], "undated": [], "requires_full_read": True,
                "next_read": "feed/window.json" if shard == "head" else "recent.json"}
    return _since_payload(payload, cursor, shard)


def since_auto(cursor, root=ROOT):
    """Read the smallest covering shard, without advancing across a gap.

    Follow only the known head-to-window fallback. An unordered result still
    requires recent.json, whose full bodies belong to the caller's full-read
    path. Neither a missing shard nor limited retention becomes an empty,
    successful refresh. Explicit head/window calls retain their existing API.
    """
    sources_read = []
    for shard in ("head", "window"):
        result = since(cursor, root, shard)
        sources_read.append("%s/%s.json" % (FEED_DIR, shard))
        if result.get("next_read") != "feed/window.json":
            break
    result["sources_read"] = sources_read
    result["next_cursor"] = cursor or ""
    if result["state"] == "COMPLETE":
        result["next_cursor"] = max(
            [cursor or ""] + [row["c"] for row in result["events"]]
        )
    return result


# --------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------

def self_test():
    """Contract, runnable without the repository bake."""
    recent = [
        {"id": "c", "durable_ts": "2026-09-10T10:00:00Z", "ts": "2026-09-10T09:00:00Z",
         "from": "ONE", "to": "TABLE", "state": "DURABLE_PAGE", "body": "third  post"},
        {"id": "a", "durable_ts": "2026-09-10T10:00:00Z", "ts": "2026-09-10T08:00:00Z",
         "from": "TWO", "state": "INTEGRATED", "body": "shares the landing second"},
        {"id": "old", "durable_ts": "2026-09-01T00:00:00Z", "from": "THREE",
         "body": "x" * 500},
        {"id": "nodate", "from": "FOUR", "body": "cannot be ordered"},
    ]
    pulse = {"seq": 7, "head": "abc", "ts": "2026-09-10T10:00:01Z"}

    head = build(recent, pulse, "head", 60, 140)
    order = [e["c"] for e in head["events"]]
    assert order == sorted(order, reverse=True), order
    # Two events share a landing second; both survive, id breaks the tie.
    assert order[0] == "2026-09-10T10:00:00Z|c", order
    assert order[1] == "2026-09-10T10:00:00Z|a", order
    assert head["count"] == 3, head["count"]
    # The undated record is named, not dropped, and makes the reader explicitly
    # fail closed even when the caller's dated cursor is already current.
    assert head["undated"] == ["nodate"], head["undated"]
    unordered = _since_payload(head, head["covers"]["newest"], "head")
    assert unordered["state"] == "UNORDERED_GAP", unordered
    assert unordered["count"] == 0, unordered
    assert unordered["undated"] == ["nodate"], unordered
    assert unordered["requires_full_read"] is True, unordered
    assert unordered["next_read"] == "recent.json", unordered
    assert head["source"]["records"] == 4 and head["source"]["dated"] == 3

    # Excerpts are bounded and whitespace-collapsed.
    long_event = [e for e in head["events"] if e["c"].endswith("|old")][0]
    assert len(long_event["x"]) == 140, len(long_event["x"])
    third = [e for e in head["events"] if e["c"].endswith("|c")][0]
    assert third["x"] == "third post", third["x"]

    # The common state is omitted; anything else is carried.
    assert "state" not in third, third
    tagged = [e for e in head["events"] if e["c"].endswith("|a")][0]
    assert tagged["state"] == "INTEGRATED", tagged

    # Author time is carried only when it differs from landing time.
    assert third.get("ts") == "2026-09-10T09:00:00Z", third

    # The window shard is headline-only and carries every dated event.
    window = build(recent, pulse, "window", 0, 0)
    assert window["count"] == 3, window["count"]
    assert all("x" not in e for e in window["events"]), window["events"]

    # id recovery works whatever the id contains.
    assert "2026-09-10T10:00:00Z|a".split("|", 1)[1] == "a"
    piped = build([{"id": "we|ird", "durable_ts": "2026-09-10T10:00:00Z"}],
                  pulse, "head", 60, 0)
    assert piped["events"][0]["c"].split("|", 1)[1] == "we|ird"

    # complete_since is the oldest cursor present.
    assert head["complete_since"] == "2026-09-01T00:00:00Z|old", head

    # Byte-stability: same inputs, same bytes.
    assert _dump(build(recent, pulse, "head", 60, 140)) == _dump(head)

    print("feed_delta self-test: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--write", action="store_true",
                    help="build and write feed/head.json and feed/window.json")
    ap.add_argument("--check", action="store_true",
                    help="report shard sizes without writing")
    ap.add_argument("--since", metavar="CURSOR",
                    help="print events newer than CURSOR from the chosen shard")
    ap.add_argument("--shard", default="head", choices=("head", "window", "auto"),
                    help="auto follows head to window and returns a safe next_cursor")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.since is not None:
        result = since(args.since, args.root, args.shard)
        print(json.dumps(result, indent=2))
        # Every reader mode must signal incomplete coverage to shell callers.
        # Keep the partial events and next_read so they can finish the read.
        return 0 if result["state"] == "COMPLETE" else 2

    if args.check:
        recent = _read_json(os.path.join(args.root, "recent.json"))
        if not isinstance(recent, list) or not recent:
            print("FINDER-FAILED: recent.json unreadable or empty")
            return 2
        pulse = _read_json(os.path.join(args.root, "pulse.json"), {}) or {}
        recent = with_landing_history(recent, args.root)
        for shard, count, exc in (("head", HEAD_N, EXCERPT), ("window", WINDOW_N, 0)):
            payload = build(recent, pulse, shard, count, exc)
            print("%-7s %4d events  %7d bytes  since %s"
                  % (shard, payload["count"], len(_dump(payload).encode("utf-8")),
                     payload["complete_since"] or "(empty)"))
        return 0

    written, report = write_shards(args.root)
    for row in report:
        print("%-7s %4d events  %7d bytes  %s"
              % (row["shard"], row["events"], row["bytes"],
                 "written" if row["changed"] else "unchanged"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
