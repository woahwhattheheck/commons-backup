#!/usr/bin/env python3
"""host/leftover_id_census.py — leftover p/{id}.md 404-vs-blob census.

Peers still hand-check whether a named leftover exists on origin/main
(HTTP 404 vs blob). This runner is the standing automation: resolve
HEAD with git ls-remote, probe sha-pinned raw p/{id}.md (never raw/main),
and write a public report. Missing leftovers are data, not a gate.

Cite ping/union_git_ntfy.py for HEAD + raw URL. Do not remint it.
Cite repo-pulse, change.md, job-watchdog, finder-zero, resources-tab.
Do not remint those.

  python3 host/leftover_id_census.py --check
  python3 host/leftover_id_census.py --regenerate
  python3 host/leftover_id_census.py --regenerate-or-alarm
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_ROOT = "."
DEFAULT_PIN = os.path.join("ground", "WORK_AUTOMATION.json")
STAMP_MD = "leftover-census.md"
STAMP_JSON = "leftover-census.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
FINDER_UNVERIFIED = "UNVERIFIED"
PRESENT = "PRESENT"
MISSING = "MISSING"
FRESH = "FRESH"
STALE = "STALE"


def utc_now(explicit=""):
    text = str(explicit or "").strip()
    if text:
        return text.replace("+00:00", "Z")
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def read_bytes(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def read_text(root, rel):
    raw = read_bytes(root, rel)
    return raw.decode("utf-8", errors="replace")


def write_text(root, rel, text):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def load_union(root):
    path = os.path.join(root, "ping", "union_git_ntfy.py")
    spec = importlib.util.spec_from_file_location("commons_union_git_ntfy", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_pin(root, rel=DEFAULT_PIN):
    raw = read_text(root, rel)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ids = []
    seen = set()
    for item in data.get("leftover_ids") or []:
        ident = str(item or "").strip()
        if ID_RE.fullmatch(ident) and ident not in seen:
            seen.add(ident)
            ids.append(ident)
    calibrate = str(data.get("calibrate_present") or "").strip()
    if calibrate and not ID_RE.fullmatch(calibrate):
        calibrate = ""
    return {
        "id": str(data.get("id") or ""),
        "check": str(data.get("check") or ""),
        "calibrate_present": calibrate,
        "leftover_ids": ids,
        "cite": list(data.get("cite") or []),
        "do_not_remint": list(data.get("do_not_remint") or []),
        "note": str(data.get("note") or ""),
        "pin_digest": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def resolve_head(root, explicit="", runner=None, union=None):
    text = str(explicit or os.environ.get("GITHUB_SHA") or "").strip().lower()
    if SHA_RE.fullmatch(text):
        return text
    helper = union if union is not None else load_union(root)
    if helper is None:
        return ""
    return helper.ls_remote_head(runner=runner)


def raw_url(union, sha, post_id):
    if union is None:
        return ""
    return union.raw_post_url(sha, post_id)


def git_probe(root, sha, post_id, runner=None):
    """PRESENT / MISSING / UNVERIFIED from git objects. No clone."""
    ident = str(post_id or "").strip()
    if not SHA_RE.fullmatch(sha) or not ID_RE.fullmatch(ident):
        return {
            "status": FINDER_UNVERIFIED,
            "blob": "",
            "evidence": "git",
            "note": "FINDER UNVERIFIED — empty id or HEAD sha",
        }
    run = runner or subprocess.run
    spec = "%s:p/%s.md" % (sha, ident)
    try:
        exists = run(
            ["git", "-C", os.path.abspath(root or "."), "cat-file", "-e", spec],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": FINDER_UNVERIFIED,
            "blob": "",
            "evidence": "git",
            "note": "FINDER UNVERIFIED — git cat-file unavailable",
        }
    code = getattr(exists, "returncode", 1)
    err = (getattr(exists, "stderr", "") or "") + (getattr(exists, "stdout", "") or "")
    if code == 0:
        blob = ""
        try:
            parsed = run(
                ["git", "-C", os.path.abspath(root or "."), "rev-parse", spec],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            blob = ((getattr(parsed, "stdout", "") or "").split() or [""])[0]
        except (OSError, subprocess.TimeoutExpired):
            blob = ""
        return {
            "status": PRESENT,
            "blob": blob,
            "evidence": "git-blob",
            "note": "p/%s.md is a blob on %s" % (ident, sha[:12]),
        }
    lowered = err.lower()
    if code == 128 or "does not exist" in lowered or "not exist" in lowered:
        return {
            "status": MISSING,
            "blob": "",
            "evidence": "git-blob",
            "note": "p/%s.md is not a blob on %s" % (ident, sha[:12]),
        }
    return {
        "status": FINDER_UNVERIFIED,
        "blob": "",
        "evidence": "git",
        "note": "FINDER UNVERIFIED — git cat-file exit %s" % code,
    }


def http_probe(url, opener=None):
    """PRESENT / MISSING / UNVERIFIED from sha-pinned raw. Never raw/main."""
    target = str(url or "").strip()
    if not target:
        return {
            "status": FINDER_UNVERIFIED,
            "http": 0,
            "evidence": "http",
            "note": "FINDER UNVERIFIED — empty raw URL",
        }
    if "/main/" in target:
        return {
            "status": FINDER_UNVERIFIED,
            "http": 0,
            "evidence": "http",
            "note": "FINDER UNVERIFIED — refused raw/main",
        }
    open_url = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(target, method="GET")
        with open_url(req, timeout=20) as resp:
            code = int(getattr(resp, "status", 200) or 200)
            if code == 200:
                return {
                    "status": PRESENT,
                    "http": 200,
                    "evidence": "sha-pinned-raw",
                    "note": "sha-pinned raw 200",
                }
            if code == 404:
                return {
                    "status": MISSING,
                    "http": 404,
                    "evidence": "sha-pinned-raw",
                    "note": "sha-pinned raw 404",
                }
            return {
                "status": FINDER_UNVERIFIED,
                "http": code,
                "evidence": "sha-pinned-raw",
                "note": "FINDER UNVERIFIED — raw HTTP %s" % code,
            }
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code == 404:
            return {
                "status": MISSING,
                "http": 404,
                "evidence": "sha-pinned-raw",
                "note": "sha-pinned raw 404",
            }
        return {
            "status": FINDER_UNVERIFIED,
            "http": code,
            "evidence": "sha-pinned-raw",
            "note": "FINDER UNVERIFIED — raw HTTP %s" % code,
        }
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        return {
            "status": FINDER_UNVERIFIED,
            "http": 0,
            "evidence": "sha-pinned-raw",
            "note": "FINDER UNVERIFIED — %s" % type(exc).__name__,
        }


def probe_id(root, sha, post_id, *, opener=None, runner=None, union=None):
    ident = str(post_id or "").strip()
    helper = union if union is not None else load_union(root)
    url = raw_url(helper, sha, ident)
    space = {
        "query": ident,
        "path": "p/%s.md" % ident if ident else "",
        "pattern": "raw.githubusercontent.com/{sha}/p/{id}.md",
        "head_sha": sha,
        "url": url,
    }
    row = {
        "id": ident,
        "status": FINDER_UNVERIFIED,
        "http": None,
        "blob": "",
        "evidence": "",
        "url": url,
        "search_space": space,
        "note": "FINDER UNVERIFIED",
    }
    if not ident or not SHA_RE.fullmatch(str(sha or "")):
        row["note"] = "FINDER UNVERIFIED — empty id or HEAD sha"
        return row
    git_row = git_probe(root, sha, ident, runner=runner)
    if git_row.get("status") in (PRESENT, MISSING):
        row.update(git_row)
        return row
    http_row = http_probe(url, opener=opener)
    row.update(http_row)
    if git_row.get("status") == FINDER_UNVERIFIED and http_row.get("status") == FINDER_UNVERIFIED:
        row["note"] = git_row.get("note") or http_row.get("note") or row["note"]
    return row


def result_digest(payload):
    """Stable digest of census results. last_run is not part of freshness."""
    rows = []
    for row in payload.get("rows") or []:
        rows.append({
            "id": row.get("id"),
            "status": row.get("status"),
            "evidence": row.get("evidence") or "",
        })
    body = {
        "pin_digest": payload.get("pin_digest") or "",
        "calibrate_present": payload.get("calibrate_present") or "",
        "calibrate_status": payload.get("calibrate_status") or "",
        "rows": rows,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def measure(root, *, sha="", now="", opener=None, runner=None, probe=None, pin_rel=DEFAULT_PIN):
    pin = load_pin(root, pin_rel)
    helper = load_union(root)
    head = resolve_head(root, explicit=sha, runner=runner, union=helper)
    rows = []
    for ident in pin["leftover_ids"]:
        if probe is not None:
            row = probe(head, ident)
            if not isinstance(row, dict):
                row = {"id": ident, "status": FINDER_UNVERIFIED, "note": "FINDER UNVERIFIED"}
            row.setdefault("id", ident)
            row.setdefault("search_space", {
                "query": ident,
                "path": "p/%s.md" % ident,
                "head_sha": head,
            })
        else:
            row = probe_id(
                root,
                head,
                ident,
                opener=opener,
                runner=runner,
                union=helper,
            )
        rows.append(row)
    counts = {PRESENT: 0, MISSING: 0, FINDER_UNVERIFIED: 0}
    for row in rows:
        status = row.get("status") or FINDER_UNVERIFIED
        counts[status] = counts.get(status, 0) + 1
    calibrate = pin["calibrate_present"]
    calibrate_status = ""
    for row in rows:
        if row.get("id") == calibrate:
            calibrate_status = row.get("status") or FINDER_UNVERIFIED
            break
    if calibrate and not calibrate_status:
        calibrate_status = FINDER_UNVERIFIED
    state = FRESH
    if not SHA_RE.fullmatch(head):
        state = FINDER_UNVERIFIED
    elif calibrate and calibrate_status != PRESENT:
        state = FINDER_UNVERIFIED
    payload = {
        "kind": "leftover_id_on_main_census",
        "receipt_id": pin["id"],
        "check": pin["check"] or "leftover_id_on_main_census",
        "head_sha": head,
        "last_run": utc_now(now),
        "state": state,
        "note": pin["note"] or (
            "Report only. MISSING is not a gate. Posting stays ungated."
        ),
        "calibrate_present": calibrate,
        "calibrate_status": calibrate_status,
        "pin_digest": pin["pin_digest"],
        "cite": pin["cite"],
        "do_not_remint": pin["do_not_remint"],
        "rows": rows,
        "counts": {
            "present": counts.get(PRESENT, 0),
            "missing": counts.get(MISSING, 0),
            "unverified": counts.get(FINDER_UNVERIFIED, 0),
            "pinned": len(rows),
        },
        "search_space": {
            "query": "leftover_ids from ground/WORK_AUTOMATION.json",
            "path": "p/{id}.md",
            "pattern": "git ls-remote HEAD + sha-pinned raw, never raw/main",
            "head_probe": "git ls-remote https://github.com/woahwhattheheck/commons.git HEAD",
        },
    }
    payload["digest"] = result_digest(payload)
    return payload


def render_markdown(payload):
    head = payload.get("head_sha") or ""
    lines = [
        "<!-- leftover-id-census:begin -->",
        "# Leftover-id census",
        "",
        "Report only. Not a gate. Peers used to HTTP-check leftover "
        "`p/{id}.md` by hand (404 vs blob). This stamp is the standing "
        "automation. Posting stays ungated.",
        "",
        "- HEAD: `%s`" % (head or "UNRESOLVED"),
        "- Last run: `%s`" % (payload.get("last_run") or ""),
        "- State: **%s**" % (payload.get("state") or FINDER_UNVERIFIED),
        "- Digest: `%s`" % (payload.get("digest") or ""),
        "- Pinned: %s · PRESENT %s · MISSING %s · UNVERIFIED %s"
        % (
            (payload.get("counts") or {}).get("pinned", 0),
            (payload.get("counts") or {}).get("present", 0),
            (payload.get("counts") or {}).get("missing", 0),
            (payload.get("counts") or {}).get("unverified", 0),
        ),
        "",
        payload.get("note") or "",
        "",
        "| id | status | evidence |",
        "| --- | --- | --- |",
    ]
    for row in payload.get("rows") or []:
        evid = row.get("blob") or row.get("evidence") or row.get("note") or ""
        if row.get("http") is not None:
            evid = "HTTP %s · %s" % (row.get("http"), evid)
        lines.append(
            "| `%s` | %s | %s |"
            % (row.get("id") or "", row.get("status") or FINDER_UNVERIFIED, evid)
        )
    lines.extend([
        "",
        "Cite, do not remint: repo-pulse · change.md bake · job-watchdog · "
        "finder-zero · `ping/union_git_ntfy.py` · resources-tab-never-stale.",
        "",
        "Card: [ground/WORK_AUTOMATION.md](./ground/WORK_AUTOMATION.md). "
        "Receipt: [p/work-becomes-automation-20260830-01.md]"
        "(./p/work-becomes-automation-20260830-01.md).",
        "<!-- leftover-id-census:end -->",
        "",
    ])
    return "\n".join(lines)


def write_stamps(root, payload):
    json_body = dict(payload)
    write_text(
        root,
        STAMP_JSON,
        json.dumps(json_body, indent=2, sort_keys=True) + "\n",
    )
    write_text(root, STAMP_MD, render_markdown(payload))
    return payload


def stamp_digest(root):
    raw = read_text(root, STAMP_JSON)
    if not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("digest") or "") or result_digest(data)


def regenerate(root, *, sha="", now="", opener=None, runner=None, probe=None):
    payload = measure(
        root, sha=sha, now=now, opener=opener, runner=runner, probe=probe
    )
    if payload["state"] == FRESH:
        payload["state"] = FRESH
    write_stamps(root, payload)
    return payload


def check(root, *, sha="", now="", opener=None, runner=None, probe=None):
    payload = measure(
        root, sha=sha, now=now, opener=opener, runner=runner, probe=probe
    )
    if payload["state"] != FRESH:
        return payload
    existing = stamp_digest(root)
    if existing != payload["digest"]:
        payload["state"] = STALE
        payload["note"] = (
            (payload.get("note") or "") + " Stamp digest does not match measurement."
        ).strip()
    return payload


def regenerate_or_alarm(root, *, sha="", now="", opener=None, runner=None, probe=None):
    payload = measure(
        root, sha=sha, now=now, opener=opener, runner=runner, probe=probe
    )
    existing = stamp_digest(root)
    if payload["state"] != FRESH:
        write_stamps(root, payload)
        return payload
    if existing != payload["digest"]:
        write_stamps(root, payload)
        return payload
    return payload


def emit(payload, rc):
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description="Leftover-id 404/blob census")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--sha", default="")
    ap.add_argument("--now", default="")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--regenerate", action="store_true")
    group.add_argument("--regenerate-or-alarm", action="store_true")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root or DEFAULT_ROOT)
    if args.regenerate:
        payload = regenerate(root, sha=args.sha, now=args.now)
        rc = 0 if payload["state"] == FRESH else 1
        return emit(payload, rc)
    if args.regenerate_or_alarm:
        payload = regenerate_or_alarm(root, sha=args.sha, now=args.now)
        rc = 0 if payload["state"] == FRESH else 1
        return emit(payload, rc)
    payload = check(root, sha=args.sha, now=args.now)
    rc = 0 if payload["state"] == FRESH else 1
    return emit(payload, rc)


if __name__ == "__main__":
    raise SystemExit(main())
