#!/usr/bin/env python3
"""host/resources_tab.py — resources.html last-reviewed stamp + regenerate-or-alarm.

The Common Resources tab is a living directory. Staleness used to be caught
by hand. This helper hashes the resource sources, stamps last-reviewed
(git SHA + UTC time), regenerates the stamp when sources drift, and alarms
(fails + writes a visible STALE mark) when the page is stale vs its inputs.

Source files and the inventory directory must be readable before a stamp is
written. An unavailable input reports UNMEASURED and exits 2 with its path.

No gate. Does not block posting or seats. Talk is not a land.

  python3 host/resources_tab.py --check
  python3 host/resources_tab.py --regenerate
  python3 host/resources_tab.py --regenerate-or-alarm
  python3 host/resources_tab.py --alarm
  python3 host/resources_tab.py --self-test
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys


DEFAULT_PAGE = "resources.html"
STAMP_BEGIN = "<!-- resources-tab-freshness:begin -->"
STAMP_END = "<!-- resources-tab-freshness:end -->"
STAMP_RE = re.compile(
    re.escape(STAMP_BEGIN) + r".*?" + re.escape(STAMP_END),
    re.DOTALL,
)
H1_MARK = "<h1>Common Resources</h1>"
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
FIXED_SOURCES = (
    os.path.join("ground", "RESOURCE_LEDGER.json"),
    os.path.join("ground", "RESOURCE_LEDGER.md"),
    os.path.join("ci", "provider_quotas.json"),
    os.path.join("revenue", "outcome_commerce", "manifest.json"),
    os.path.join("revenue", "outcome_commerce", "catalog.json"),
    os.path.join("orchestration", "jeffersonville", "frameworks.json"),
    os.path.join("orchestration", "jeffersonville", "topology.json"),
)
INVENTORY_RECORDS = os.path.join("inventory", "resources", "records")


def utc_now(explicit=""):
    text = str(explicit or "").strip()
    if text:
        return text.replace("+00:00", "Z")
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha(root, explicit=""):
    text = str(explicit or "").strip()
    if SHA_RE.match(text):
        return text
    try:
        out = subprocess.check_output(
            ["git", "-C", os.path.abspath(root or "."), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        out = ""
    got = out.strip()
    if SHA_RE.match(got):
        return got
    # An Actions event SHA can predate a moving-branch checkout or rebase.
    # Keep it only as a fallback for source exports without Git metadata.
    fallback = str(os.environ.get("GITHUB_SHA") or "").strip()
    return fallback if SHA_RE.match(fallback) else ""


def read_bytes(root, rel):
    path = os.path.join(root, rel)
    with open(path, "rb") as handle:
        return handle.read()


def read_text(root, rel):
    raw = read_bytes(root, rel)
    return raw.decode("utf-8", errors="replace")


def digest_relpath(rel):
    """Return the repository-style path hashed on every operating system."""
    return str(rel or "").replace("\\", "/")


def digest_source_bytes(raw):
    """Normalize text source line endings before hashing."""
    return bytes(raw or b"").replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def write_text(root, rel, text):
    path = os.path.join(root, rel)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def source_relpaths(root):
    rels = list(FIXED_SOURCES)
    records = os.path.join(root, INVENTORY_RECORDS)
    for name in sorted(os.listdir(records)):
        if name.endswith(".json"):
            rels.append(os.path.join(INVENTORY_RECORDS, name))
    return rels


def strip_stamp(html):
    return STAMP_RE.sub("", str(html or ""))


def source_digest(root, body=""):
    hasher = hashlib.sha256()
    for rel in source_relpaths(root):
        hasher.update(digest_relpath(rel).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest_source_bytes(read_bytes(root, rel)))
        hasher.update(b"\n")
    hasher.update(b"resources.html#body\0")
    hasher.update(digest_source_bytes(strip_stamp(body).encode("utf-8")))
    hasher.update(b"\n")
    return hasher.hexdigest()


def ledger_snapshot(root):
    catalog = {}
    try:
        catalog = json.loads(read_text(root, FIXED_SOURCES[0]) or "{}")
    except ValueError:
        catalog = {}
    surfaces = catalog.get("surfaces") if isinstance(catalog, dict) else None
    if not isinstance(surfaces, list):
        surfaces = []
    producing = 0
    for row in surfaces:
        if isinstance(row, dict) and str(row.get("stage") or "").upper() == "PRODUCING":
            producing += 1
    records = os.path.join(root, INVENTORY_RECORDS)
    inventory = len([name for name in os.listdir(records) if name.endswith(".json")])
    return {
        "resource_count": len(surfaces),
        "producing_count": producing,
        "inventory_records": inventory,
    }


def render_stamp(sha, reviewed_at, digest, state, snapshot=None):
    snapshot = snapshot or {}
    short = (sha or "UNMEASURED")[:12]
    digest_short = (digest or "UNMEASURED")[:16]
    state = "STALE" if str(state or "").upper() == "STALE" else "FRESH"
    color = "#a43e35" if state == "STALE" else "#555"
    href = ""
    if SHA_RE.match(sha or ""):
        href = (
            ' · git <a href="https://github.com/woahwhattheheck/commons/commit/%s">%s</a>'
            % (sha, short)
        )
    elif sha:
        href = " · git %s" % short
    metrics = " · ledger %s resources / %s producing · %s inventory records" % (
        snapshot.get("resource_count", 0),
        snapshot.get("producing_count", 0),
        snapshot.get("inventory_records", 0),
    )
    label = "STALE" if state == "STALE" else "LAST REVIEWED"
    note = (
        " · source digest does not match current inputs. Do not treat this tab as current."
        if state == "STALE"
        else ""
    )
    return (
        "%s<p id=\"resources-last-reviewed\" class=\"stamp%s\" "
        "data-resources-freshness=\"%s\" data-reviewed-sha=\"%s\" "
        "data-reviewed-at=\"%s\" data-source-digest=\"%s\" "
        "style=\"color:%s;font-weight:%s\">%s %s%s%s · source digest %s… · %s%s</p>%s"
        % (
            STAMP_BEGIN,
            " stale" if state == "STALE" else "",
            state,
            sha or "",
            reviewed_at or "",
            digest or "",
            color,
            "700" if state == "STALE" else "400",
            label,
            reviewed_at or "UNMEASURED",
            href,
            metrics,
            digest_short,
            state,
            note,
            STAMP_END,
        )
    )


def apply_stamp(html, stamp):
    html = str(html or "")
    if STAMP_RE.search(html):
        return STAMP_RE.sub(stamp, html, count=1)
    if H1_MARK in html:
        return html.replace(H1_MARK, H1_MARK + stamp, 1)
    return stamp + html


def parse_stamp(html):
    match = STAMP_RE.search(str(html or ""))
    if not match:
        return {}
    block = match.group(0)

    def attr(name):
        found = re.search(r'data-%s="([^"]*)"' % re.escape(name), block)
        return found.group(1) if found else ""

    return {
        "present": True,
        "state": attr("resources-freshness") or "UNMEASURED",
        "sha": attr("reviewed-sha"),
        "reviewed_at": attr("reviewed-at"),
        "digest": attr("source-digest"),
        "block": block,
    }


def measure(root, page=DEFAULT_PAGE, sha="", reviewed_at=""):
    root = os.path.abspath(root or ".")
    html = read_text(root, page)
    body = strip_stamp(html)
    digest = source_digest(root, body)
    stamp = parse_stamp(html)
    present = bool(stamp.get("present"))
    matching = present and stamp.get("digest") == digest
    state = "FRESH" if matching and stamp.get("state") == "FRESH" else "STALE"
    if not present:
        reason = "resources.html has no generated last-reviewed stamp"
    elif stamp.get("digest") != digest:
        reason = "resources.html source digest does not match current inputs"
    elif stamp.get("state") != "FRESH":
        reason = "resources.html stamp is marked STALE"
    else:
        reason = "resources.html last-reviewed stamp matches current inputs"
    return {
        "state": state,
        "page": page,
        "present": present,
        "digest": digest,
        "page_digest": stamp.get("digest") or "",
        "sha": stamp.get("sha") or "",
        "reviewed_at": stamp.get("reviewed_at") or "",
        "checkout_sha": git_sha(root, sha),
        "now": utc_now(reviewed_at),
        "snapshot": ledger_snapshot(root),
        "sources": source_relpaths(root),
        "reason": reason,
        "html": html,
        "body": body,
    }


def regenerate(root, page=DEFAULT_PAGE, sha="", reviewed_at="", state="FRESH"):
    row = measure(root, page=page, sha=sha, reviewed_at=reviewed_at)
    stamp = render_stamp(
        row["checkout_sha"],
        row["now"],
        row["digest"],
        state,
        row["snapshot"],
    )
    html = apply_stamp(row["html"], stamp)
    write_text(root, page, html)
    return measure(root, page=page, sha=sha, reviewed_at=reviewed_at)


def alarm(root, page=DEFAULT_PAGE, sha="", reviewed_at=""):
    row = measure(root, page=page, sha=sha, reviewed_at=reviewed_at)
    if row["state"] == "FRESH":
        return row
    stamp = render_stamp(
        row["checkout_sha"] or row["sha"],
        row["now"] or row["reviewed_at"],
        row["digest"],
        "STALE",
        row["snapshot"],
    )
    html = apply_stamp(row["html"], stamp)
    write_text(root, page, html)
    return measure(root, page=page, sha=sha, reviewed_at=reviewed_at)


def regenerate_or_alarm(root, page=DEFAULT_PAGE, sha="", reviewed_at=""):
    row = measure(root, page=page, sha=sha, reviewed_at=reviewed_at)
    if row["state"] == "FRESH":
        return row
    regenerated = regenerate(root, page=page, sha=sha, reviewed_at=reviewed_at, state="FRESH")
    if regenerated["state"] == "FRESH":
        regenerated["action"] = "REGENERATED"
        return regenerated
    alarmed = alarm(root, page=page, sha=sha, reviewed_at=reviewed_at)
    alarmed["action"] = "ALARMED"
    return alarmed


def self_test():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="resources-tab-") as tmp:
        os.makedirs(os.path.join(tmp, "ground"))
        os.makedirs(os.path.join(tmp, "inventory", "resources", "records"))
        os.makedirs(os.path.join(tmp, "ci"))
        os.makedirs(os.path.join(tmp, "revenue", "outcome_commerce"))
        os.makedirs(os.path.join(tmp, "orchestration", "jeffersonville"))
        write_text(
            tmp,
            FIXED_SOURCES[0],
            json.dumps({"surfaces": [{"name": "a", "stage": "PRODUCING"}]}, indent=2) + "\n",
        )
        for rel in FIXED_SOURCES[1:]:
            write_text(tmp, rel, "{}\n")
        write_text(tmp, DEFAULT_PAGE, "<h1>Common Resources</h1><p>directory</p>\n")
        missing = measure(tmp, sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        if missing["state"] != "STALE" or missing["present"]:
            raise SystemExit("missing stamp must be STALE")
        fresh = regenerate(
            tmp,
            sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            reviewed_at="2026-08-31T00:00:00Z",
        )
        if fresh["state"] != "FRESH" or not fresh["present"]:
            raise SystemExit("regenerate must produce a FRESH stamp")
        if "LAST REVIEWED 2026-08-31T00:00:00Z" not in read_text(tmp, DEFAULT_PAGE):
            raise SystemExit("stamp must be visible")
        write_text(tmp, FIXED_SOURCES[0], json.dumps({"surfaces": [{"name": "b"}]}, indent=2) + "\n")
        stale = measure(tmp)
        if stale["state"] != "STALE":
            raise SystemExit("source drift must be STALE")
        alarmed = alarm(tmp, sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        page = read_text(tmp, DEFAULT_PAGE)
        if alarmed["state"] != "STALE" or 'data-resources-freshness="STALE"' not in page:
            raise SystemExit("alarm must write a visible STALE mark")
        if "directory" not in page:
            raise SystemExit("alarm must keep the directory body")
        again = regenerate_or_alarm(
            tmp,
            sha="cccccccccccccccccccccccccccccccccccccccc",
            reviewed_at="2026-08-31T00:01:00Z",
        )
        if again["state"] != "FRESH":
            raise SystemExit("regenerate-or-alarm must refresh a stale page")
    print("resources_tab self-test ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="resources.html last-reviewed stamp. No gate."
    )
    parser.add_argument("--root", default=".", help="commons checkout root")
    parser.add_argument("--page", default=DEFAULT_PAGE)
    parser.add_argument("--sha", default="", help="review git SHA (default checkout HEAD)")
    parser.add_argument("--reviewed-at", default="", help="UTC stamp; default now")
    parser.add_argument("--check", action="store_true", help="fail if stale; do not write")
    parser.add_argument("--regenerate", action="store_true", help="rewrite the generated stamp")
    parser.add_argument("--alarm", action="store_true", help="write STALE mark if stale and fail")
    parser.add_argument(
        "--regenerate-or-alarm",
        action="store_true",
        help="regenerate when stale; if still stale, write STALE and fail",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    root = os.path.abspath(args.root)
    try:
        if args.regenerate:
            row = regenerate(root, page=args.page, sha=args.sha, reviewed_at=args.reviewed_at)
            row.setdefault("action", "REGENERATED")
        elif args.alarm:
            row = alarm(root, page=args.page, sha=args.sha, reviewed_at=args.reviewed_at)
            row.setdefault("action", "ALARMED" if row["state"] == "STALE" else "CHECKED")
        elif args.regenerate_or_alarm:
            row = regenerate_or_alarm(root, page=args.page, sha=args.sha, reviewed_at=args.reviewed_at)
            row.setdefault("action", "CHECKED")
        else:
            row = measure(root, page=args.page, sha=args.sha, reviewed_at=args.reviewed_at)
            row.setdefault("action", "CHECKED")
    except OSError as exc:
        error = {"state": "UNMEASURED", "action": "FAILED",
                 "page": args.page, "reason": str(exc), "path": exc.filename}
        json.dump(error, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        sys.stderr.write("resources-tab: %s\n" % exc)
        return 2
    out = {key: row[key] for key in (
        "state",
        "page",
        "present",
        "digest",
        "page_digest",
        "sha",
        "reviewed_at",
        "checkout_sha",
        "snapshot",
        "reason",
        "action",
    ) if key in row}
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row["state"] == "FRESH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
