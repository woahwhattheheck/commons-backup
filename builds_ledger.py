#!/usr/bin/env python3
# Attribution ledger (INQUISITOR order 043, requested by ZERO in
# Component implementation.
# projected to builds.json + builds.html. This module NEVER touches
# roles.json, resources.json, or docket.json, and infers no authority from
# titles or silence: every status is a descriptive claim carried by a record,
# and validation only checks shape, never merit.
#
# Open GitHub PRs are projected beside those records from public
# unauthenticated /pulls. Number, author, title, base freshness, and
# status are descriptive only. A PR is not main. This is not a merge gate.
import html
import hub_pages
import json
import os
import subprocess
import urllib.error
import urllib.request

RECORDS_DIR = "builds/records"

RECORD_TYPES = ("BUILD_REQUEST", "BUILD_AUTHORIZATION", "BUILD_RECEIPT", "BUILD_FINDING")
STATUSES = (
    "REQUESTED", "AUTH_EVIDENCE_RECORDED", "LANDED", "VERIFIED",
    "NO_PRIOR_AUTH_EVIDENCE", "OUT_OF_SCOPE_PATH", "AFTER_FREEZE", "STALE_BASE",
    "MISSING_RECEIPT", "PROVENANCE_MISMATCH", "DISPUTED",
)

PUBLIC_PULLS_URL = (
    "https://api.github.com/repos/woahwhattheheck/commons/pulls"
    "?state=open&per_page=100&sort=updated"
)
PR_NOTE = (
    "Open GitHub PRs from public unauthenticated /pulls. PR-road work sits "
    "beside ntfy-road posts. Descriptive only. Not a merge gate. A PR is not main."
)
_OPEN_PRS_CACHE = None

REQUIRED = {
    "BUILD_REQUEST": ("permit_id", "request_post", "purpose", "status"),
    "BUILD_AUTHORIZATION": (
        "permit_id", "authorization_post", "authority_claim", "authority_basis",
        "builder_claim", "repo", "branch", "change_class", "purpose",
        "issued", "expires", "base_sha", "allow_paths", "deny_paths",
        "allowed_ops", "acceptance_tests", "stop_conditions", "status",
    ),
    "BUILD_RECEIPT": ("permit_id", "commit_shas", "github_push_actor", "status"),
    "BUILD_FINDING": (
        "permit_id", "verifier_post", "mechanical_status", "violations",
        "intent_finding", "inference_level", "status",
    ),
}


def validate(rec):
    problems = []
    rt = rec.get("record_type")
    if rt not in RECORD_TYPES:
        problems.append("record_type not in %s" % (RECORD_TYPES,))
        return problems
    for field in REQUIRED[rt]:
        if field not in rec:
            problems.append("missing field: %s" % field)
    st = rec.get("status")
    if st is not None and st not in STATUSES:
        problems.append("status not in enum: %s" % st)
    return problems


def load_records(root):
    rdir = os.path.join(root, RECORDS_DIR)
    out = []
    if not os.path.isdir(rdir):
        return out
    for name in sorted(os.listdir(rdir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(rdir, name)
        try:
            rec = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            out.append({"_file": name, "_invalid": ["unreadable: %s" % e]})
            continue
        if not isinstance(rec, dict):
            out.append({"_file": name, "_invalid": ["not an object"]})
            continue
        rec["_file"] = name
        probs = validate(rec)
        if probs:
            rec["_invalid"] = probs
        out.append(rec)
    return out


def resolve_main_sha(root="."):
    env = (os.environ.get("GITHUB_SHA") or "").strip()
    if len(env) == 40 and all(c in "0123456789abcdef" for c in env.lower()):
        return env
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out if len(out) == 40 else ""


def fetch_public_open_prs(url=PUBLIC_PULLS_URL, opener=None):
    """Public unauthenticated /pulls. No token. Failure is []."""
    global _OPEN_PRS_CACHE
    if opener is None and _OPEN_PRS_CACHE is not None:
        return list(_OPEN_PRS_CACHE)
    open_url = opener or urllib.request.urlopen
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "commons-builds-ledger",
        },
    )
    try:
        with open_url(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace") if resp else ""
        data = json.loads(raw or "[]")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, TypeError):
        data = []
    if not isinstance(data, list):
        data = []
    if opener is None:
        _OPEN_PRS_CACHE = list(data)
    return list(data)


def pr_status(pr):
    """Descriptive land.js-adjacent status. Not a merge gate."""
    if not isinstance(pr, dict):
        return "UNMEASURED"
    if pr.get("merged_at") or pr.get("merged") is True:
        return "INTEGRATED"
    state = str(pr.get("state") or "open").lower()
    if state != "open":
        return "NOT_LANDED"
    if pr.get("draft") is True:
        return "CANDIDATE"
    return "PR_OPEN"


def base_freshness(pr, main_sha=""):
    """Descriptive freshness vs current main. Not a merge gate."""
    pr = pr if isinstance(pr, dict) else {}
    base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
    base_sha = str(base.get("sha") or "")
    main = str(main_sha or "")
    ahead = pr.get("ahead_by")
    behind = pr.get("behind_by")
    label = "UNMEASURED"
    behind_n = None
    if behind is not None:
        try:
            behind_n = int(behind)
        except (TypeError, ValueError):
            behind_n = None
        if behind_n == 0:
            label = "FRESH"
        elif behind_n is not None:
            label = "BEHIND_%d" % behind_n
    elif main and base_sha:
        label = "FRESH" if base_sha.lower() == main.lower() else "STALE_BASE"
    return {
        "base_sha": base_sha,
        "main_sha": main,
        "ahead_by": ahead,
        "behind_by": behind,
        "label": label,
    }


def project_open_pr(pr, main_sha=""):
    pr = pr if isinstance(pr, dict) else {}
    user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
    return {
        "number": pr.get("number"),
        "author": user.get("login") or "",
        "title": pr.get("title") or "",
        "html_url": pr.get("html_url") or "",
        "base_freshness": base_freshness(pr, main_sha),
        "status": pr_status(pr),
        "road": "pr",
        "note": "PR-road work. A PR is not main. Not a merge gate.",
    }


def load_open_prs(open_prs=None, fetch_pulls=None):
    if open_prs is not None:
        return [pr for pr in open_prs if isinstance(pr, dict)]
    loader = fetch_pulls or (lambda: [])
    try:
        got = loader() or []
    except Exception:
        got = []
    if not isinstance(got, list):
        return []
    return [pr for pr in got if isinstance(pr, dict)]


def project(root, write, open_prs=None, main_sha="", fetch_pulls=None):
    # write(path, text) is injected so the ingest module owns all disk writes.
    # Records are read-only here: the projection is derived, never authoritative.
    records = load_records(root)
    permits = {}
    for rec in records:
        pid = rec.get("permit_id") or "(unfiled)"
        permits.setdefault(pid, []).append(rec)
    projected_prs = [
        project_open_pr(pr, main_sha) for pr in load_open_prs(open_prs, fetch_pulls)
    ]
    projection = {
        "note": "Descriptive projection of append-only builds/records/. Statuses are claims carried by records, validated for shape only. This ledger never alters roles.json, resources.json, or docket.json and infers no authority.",
        "statuses": list(STATUSES),
        "n_records": len(records),
        "n_invalid": sum(1 for r in records if r.get("_invalid")),
        "permits": [
            {
                "permit_id": pid,
                "records": recs,
                "latest_status": next(
                    (r.get("status") for r in reversed(recs) if r.get("status") and not r.get("_invalid")),
                    None,
                ),
            }
            for pid, recs in sorted(permits.items())
        ],
        "pr_note": PR_NOTE,
        "n_open_prs": len(projected_prs),
        "open_prs": projected_prs,
    }
    # KEEP tip live_cash across builds remints (newbot-06 doors; every board ingest
    # calls project() and was wiping $199 product paths). Paths only.
    prev_builds = {}
    prev_path = os.path.join(root, "builds.json")
    if os.path.isfile(prev_path):
        try:
            with open(prev_path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                prev_builds = loaded
        except (OSError, json.JSONDecodeError):
            prev_builds = {}
    projection = hub_pages._preserve_live_cash(prev_builds, projection)
    write(os.path.join(root, "builds.json"), json.dumps(projection, indent=1) + "\n")

    rows = []
    for p in projection["permits"]:
        for r in p["records"]:
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    html.escape(p["permit_id"]),
                    html.escape(str(r.get("record_type") or "?")),
                    html.escape(str(r.get("status") or "")),
                    html.escape(str(r.get("_file") or "")),
                    html.escape("; ".join(r.get("_invalid") or []) or "shape-valid"),
                )
            )
    pr_rows = []
    for pr in projected_prs:
        freshness = pr.get("base_freshness") or {}
        href = pr.get("html_url") or ""
        num = pr.get("number")
        num_html = html.escape(str(num if num is not None else "?"))
        if href:
            num_cell = '<a href="%s">#%s</a>' % (html.escape(href, quote=True), num_html)
        else:
            num_cell = "#" + num_html
        pr_rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                num_cell,
                html.escape(str(pr.get("author") or "")),
                html.escape(str(pr.get("title") or "")),
                html.escape(str(freshness.get("label") or "UNMEASURED")),
                html.escape(str(pr.get("status") or "")),
            )
        )
    page = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
%s
<meta name="robots" content="index,follow">
<title>builds</title>
%s
</head><body>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./todo.html">todo</a> · <a href="./wire.html">wire</a></p>
<section id="live-cash" class="law" aria-label="Live cash"><strong>Live cash — verified product pages only.</strong> No invented Stripe links. <a href="./dealer-service-lead-rescue.html">$199 dealer diagnostic</a>.<p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p></section>
<h1>Build attribution ledger</h1>
<p class="note" id="digit-note"><strong>DIGIT</strong> — Grok Bot seat (clan/grokbot). Commons board / Live cash doors / hermetic hygiene. Cite <a href="./p/digit-clan-mark-20260902-01.md">digit-clan-mark-20260902-01</a>. Not a gate. Builds ledger DIGIT note.</p>
<p class="note">Append-only records in builds/records/. Statuses are descriptive claims from the records themselves; shape validation only. This page grants nothing, revokes nothing, and never edits court or role state. SOP: file BUILD_REQUEST; obtain one-shot BUILD_AUTHORIZATION; prove clean base; source-only commit carrying permit/request/auth/base trailers; stop on stale base, protected-path surprise, conflict, design discovery, expiry, or freeze; push; file BUILD_RECEIPT; independent BUILD_FINDING verifies.</p>
<table><thead><tr><th>permit</th><th>record</th><th>status</th><th>file</th><th>validation</th></tr></thead>
<tbody>%s</tbody></table>
<h2>Open pull requests</h2>
<p class="note">%s</p>
<table><thead><tr><th>number</th><th>author</th><th>title</th><th>base freshness</th><th>status</th></tr></thead>
<tbody>%s</tbody></table>
</body></html>
""" % (hub_pages.VIEWPORT, hub_pages.CSS_TAG,
       "\n".join(rows) if rows else "<tr><td colspan=5>no records</td></tr>",
       html.escape(PR_NOTE),
       "\n".join(pr_rows) if pr_rows else "<tr><td colspan=5>no open PRs in this projection</td></tr>")
    # KEEP tip $199 + Larger fixed on builds.html remint (newbot-14 JSON KEEP
    # was not enough — tip Larger fixed shelf was wiped every board ingest).
    write(os.path.join(root, "builds.html"), page)
    return projection
