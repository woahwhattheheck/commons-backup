#!/usr/bin/env python3
"""host/explee_autogtm_local.py — local AutoGTM loop, sends 0.

Matches the public MIT skill cluster Sheshiyer/explee-skills
(explee-autogtm composes search + enrichment):

  1. research the pasted site
  2. nl-to-filters / ICP segments with fit scores
  3. companies + people (role-level, UNVERIFIED)
  4. enrich status only (never a live api.explee.com call)
  5. rank FIT / ROLE / EMAIL_OK
  6. personalized drafts + demo queue in need_owner_review

Does not remint Harborline leftover cursor-explee-qualify-clone-20260902-01.
Does not write qualify.html. Does not call Explee. Does not send mail.
Does not copy Explee testimonials. Checkout NOT_MINTED. No card.

  python3 host/explee_autogtm_local.py --html-file page.html
  python3 host/explee_autogtm_local.py --self-test
  python3 host/explee_autogtm_local.py --send     # REFUSED
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import urllib.error
import urllib.request


SOURCE_SKILL = "https://github.com/Sheshiyer/explee-skills"
SOURCE_COMMIT = "b08318527782ab834317c09f4938381f00b90fe8"
API_HOST = "https://api.explee.com"
COMPOSED_ENDPOINTS = (
    "POST /public/api/v1/search/nl-to-filters",
    "POST /public/api/v1/search/companies",
    "POST /public/api/v1/search/people",
    "POST /public/api/v1/enrich/email",
)
DO_NOT_REMINT = (
    "cursor-explee-qualify-clone-20260902-01",
    "cursor-autogtm-explee-same-loop-20260902-01",
    "cursor-lead-clan-mark-20260902-01",
)
DO_NOT_WRITE = (
    "qualify.html",
    "autogtm.html",
    os.path.join("host", "autogtm_same_loop.py"),
    os.path.join(".agents", "skills", "autogtm", "SKILL.md"),
    "integrations/grok_slack/bridge.py",
    "docs/GROKCOM_REVENUE_ORCHESTRATOR.md",
)
SEND_FLAGS = ("send", "apply", "go")
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
META_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    re.I | re.S,
)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.I | re.S)
MAILTO_RE = re.compile(r"mailto:([^\"'\s>]+)", re.I)

# (pattern, icp_label, buyer_role, company_kind, fit)
ICP_RULES = (
    (r"\b(agent|cursor|commons|leftover|board)\b", "AI agent operators", "Cloud agent lead", "public agent desk", 92),
    (r"\b(revops|gtm|outbound|prospect|icp)\b", "RevOps / GTM operators", "Head of RevOps", "B2B GTM shop", 88),
    (r"\b(founder|startup|saas|software)\b", "SaaS founders", "Founder", "early SaaS team", 85),
    (r"\b(lab|lims|clinic|medical)\b", "Lab / clinic operators", "Lab director", "independent lab", 74),
    (r"\b(florist|floral|wedding|event)\b", "Event designers", "Owner", "event studio", 79),
    (r"\b(wholesale|b2b|supply)\b", "Wholesale buyers", "Buyer", "wholesale account", 70),
)


def _plain(blob):
    text = html_lib.unescape(TAG_RE.sub(" ", blob or ""))
    return WS_RE.sub(" ", text).strip()


def parse_page(html_text, url=""):
    raw = html_text or ""
    title_m = TITLE_RE.search(raw)
    meta_m = META_RE.search(raw)
    title = _plain(title_m.group(1) if title_m else "")
    meta = _plain(meta_m.group(1) if meta_m else "")
    h1s = [_plain(m.group(1)) for m in H1_RE.finditer(raw)]
    h2s = [_plain(m.group(1)) for m in H2_RE.finditer(raw)]
    body = _plain(raw)
    mailtos = [m.group(1).strip() for m in MAILTO_RE.finditer(raw)]
    return {
        "url": url or "",
        "title": title,
        "description": meta,
        "h1": h1s[:3],
        "h2": h2s[:5],
        "body": body,
        "seller_email": mailtos[0] if mailtos else "",
        "word_count": len(body.split()) if body else 0,
    }


def research(page):
    title = page.get("title") or (page.get("h1") or [""])[0] or "Untitled site"
    pitch = page.get("description") or " ".join(page.get("h1") or []) or ""
    what = pitch or (page.get("body") or "")[:180]
    return {
        "company": title,
        "what_they_sell": what.strip(),
        "signals": [s for s in (page.get("h1") or []) + (page.get("h2") or []) if s][:6],
        "word_count": int(page.get("word_count") or 0),
        "seller_email_on_page": page.get("seller_email") or "",
    }


def icp_segments(page):
    hay = " ".join(
        [
            page.get("title") or "",
            page.get("description") or "",
            " ".join(page.get("h1") or []),
            " ".join(page.get("h2") or []),
            (page.get("body") or "")[:4000],
        ]
    ).lower()
    rows = []
    seen = set()
    for pattern, label, role, kind, fit in ICP_RULES:
        if re.search(pattern, hay) and label not in seen:
            seen.add(label)
            rows.append(
                {
                    "label": label,
                    "fit": fit,
                    "buyer_role": role,
                    "company_kind": kind,
                    "reason": "keyword hit %s" % pattern,
                }
            )
    if not rows:
        rows.append(
            {
                "label": "Unscoped buyers",
                "fit": 40,
                "buyer_role": "Owner",
                "company_kind": "unscoped account",
                "reason": "no ICP keyword hit; low-confidence default",
            }
        )
    rows.sort(key=lambda r: -int(r["fit"]))
    return rows


def nl_to_filters(segments):
    titles = [row["buyer_role"] for row in segments]
    kinds = [row["company_kind"] for row in segments]
    query = "; ".join("%s (%s)" % (row["label"], row["fit"]) for row in segments)
    return {
        "query": query,
        "companies_filters": {"kinds": kinds, "fit_min": 70},
        "people_filters": {"titles": titles, "fit_min": 70},
    }


def prospects(segments, seller):
    found = []
    company_name = seller.get("company") or "Seller"
    for idx, row in enumerate(segments, start=1):
        slug = re.sub(r"[^a-z0-9]+", "-", row["label"].lower()).strip("-") or "buyer"
        account = {
            "id": "acct-%02d" % idx,
            "name": "Example %s" % row["company_kind"],
            "kind": row["company_kind"],
            "fit": row["fit"],
            "source": "local-heuristic",
            "note": "UNVERIFIED stand-in for %s. Not a harvested person." % row["label"],
        }
        person = {
            "id": "ppl-%02d" % idx,
            "name": "Role lead %02d" % idx,
            "title": row["buyer_role"],
            "account_id": account["id"],
            "email": "",
            "email_status": "UNVERIFIED",
            "source": "local-heuristic",
            "seller": company_name,
            "icp": row["label"],
            "slug": slug,
        }
        found.append({"account": account, "person": person, "icp": row})
    return found


def enrich_status(rows):
    out = []
    for item in rows:
        person = dict(item["person"])
        person["email_status"] = "UNVERIFIED"
        person["enrichment"] = "skipped-no-explee-key"
        out.append({**item, "person": person})
    return out


def rank(rows):
    ranked = []
    for item in rows:
        reasons = []
        fit = int(item["icp"]["fit"])
        if fit >= 80:
            reasons.append("FIT")
        if item["person"].get("title"):
            reasons.append("ROLE")
        if item["person"].get("email_status") == "OK":
            reasons.append("EMAIL_OK")
        tier = "high" if "FIT" in reasons and "ROLE" in reasons else "watch"
        ranked.append({**item, "reasons": reasons, "tier": tier, "score": fit})
    ranked.sort(key=lambda r: -int(r["score"]))
    return ranked


def draft_email(item, seller):
    person = item["person"]
    account = item["account"]
    icp = item["icp"]
    company = seller.get("company") or "us"
    what = seller.get("what_they_sell") or "the product"
    subject = "%s x %s" % (company, account["name"])
    body = (
        "Hi %s,\n\n"
        "Saw %s operating as %s. %s is built for that motion: %s\n\n"
        "Draft only. Not sent. Reply if a 20-minute walkthrough is useful.\n"
    ) % (
        person["title"],
        account["name"],
        icp["label"],
        company,
        what,
    )
    return {
        "to_role": person["title"],
        "account": account["name"],
        "subject": subject,
        "body": body,
        "send": 0,
        "state": "owner-review",
    }


def demo_queue(ranked):
    queue = []
    for item in ranked:
        if item["tier"] != "high":
            continue
        queue.append(
            {
                "account": item["account"]["name"],
                "role": item["person"]["title"],
                "status": "need_owner_review",
                "booked": False,
            }
        )
    return queue


def refuse_send(flag):
    return {
        "state": "REFUSED",
        "flag": flag,
        "sent": 0,
        "note": (
            "%s is refused on this leftover. Drafts stay owner-review. "
            "No api.explee.com call. No card. FINDER-FAILED plus search "
            "space if you expected a live send, never silent 0." % flag
        ),
        "search_space": list(SEND_FLAGS) + ["api.explee.com", SOURCE_SKILL],
    }


def empty_page_failure():
    return {
        "state": "FINDER-FAILED",
        "sent": 0,
        "counts": {"found": None, "enriched": None, "prioritized": None},
        "note": (
            "No page text. FINDER-FAILED plus search space "
            "(--html-file / --url / title / description), never silent 0."
        ),
        "search_space": ["--html-file", "--url", "<title>", "meta description"],
    }


def run_pipeline(html_text, url=""):
    page = parse_page(html_text, url=url)
    if page["word_count"] < 8 and not page["title"]:
        return empty_page_failure()
    seller = research(page)
    segments = icp_segments(page)
    filters = nl_to_filters(segments)
    found = prospects(segments, seller)
    enriched = enrich_status(found)
    ranked = rank(enriched)
    drafts = [draft_email(item, seller) for item in ranked]
    queue = demo_queue(ranked)
    return {
        "state": "DRAFT",
        "source_skill": SOURCE_SKILL,
        "source_commit": SOURCE_COMMIT,
        "api_host_not_called": API_HOST,
        "endpoints_composed_not_called": list(COMPOSED_ENDPOINTS),
        "objective": filters["query"],
        "filters": filters,
        "seller": seller,
        "icp": segments,
        "candidates": [
            {
                "account": item["account"]["name"],
                "role": item["person"]["title"],
                "fit": item["score"],
                "tier": item["tier"],
                "reasons": item["reasons"],
                "email_status": item["person"]["email_status"],
            }
            for item in ranked
        ],
        "drafts": drafts,
        "demo_queue": queue,
        "counts": {
            "found": len(found),
            "enriched": len(enriched),
            "prioritized": len(ranked),
            "high": sum(1 for item in ranked if item["tier"] == "high"),
            "drafts": len(drafts),
            "queue": len(queue),
        },
        "sent": 0,
        "checkout": "NOT_MINTED",
        "do_not_remint": list(DO_NOT_REMINT),
        "do_not_write": list(DO_NOT_WRITE),
    }


def fetch_url(url, opener=None):
    target = str(url or "").strip()
    if not target:
        raise ValueError("empty url")
    open_url = opener or urllib.request.urlopen
    req = urllib.request.Request(target, method="GET", headers={"User-Agent": "commons-explee-autogtm-local/1"})
    with open_url(req, timeout=20) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def self_test():
    html = (
        "<html><head><title>Open Bench Packs</title>"
        "<meta name='description' content='Public commons leftover board for agent GTM.'>"
        "</head><body><h1>Ship leftover work</h1>"
        "<p>Cursor cloud seats, RevOps, and SaaS founders paste a URL and get ICP drafts.</p>"
        "<h2>Outbound without a card</h2></body></html>"
    )
    row = run_pipeline(html, url="https://example.test/packs")
    if row.get("state") != "DRAFT":
        return "fail-state"
    if row.get("sent") != 0:
        return "fail-sent"
    if not row.get("icp"):
        return "fail-icp"
    if not row.get("drafts"):
        return "fail-drafts"
    labels = {item["label"] for item in row["icp"]}
    if "AI agent operators" not in labels:
        return "fail-agent-icp"
    refuse = refuse_send("send")
    if refuse.get("state") != "REFUSED" or refuse.get("sent") != 0:
        return "fail-refuse"
    empty = run_pipeline("   ")
    if empty.get("state") != "FINDER-FAILED":
        return "fail-empty"
    if empty.get("counts", {}).get("found") == 0:
        return "fail-silent-zero"
    return "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local AutoGTM. Sends 0.")
    ap.add_argument("--html-file", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--go", action="store_true")
    args = ap.parse_args(argv)
    if args.send or args.apply or args.go:
        flag = "send" if args.send else "apply" if args.apply else "go"
        json.dump(refuse_send(flag), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    if args.self_test:
        result = self_test()
        json.dump({"self_test": result, "sent": 0}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if result == "ok" else 1
    html_text = ""
    url = args.url
    if args.html_file:
        path = os.path.abspath(args.html_file)
        with open(path, encoding="utf-8") as handle:
            html_text = handle.read()
        url = url or path
    elif args.url:
        try:
            html_text = fetch_url(args.url)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            json.dump(
                {
                    "state": "FINDER-FAILED",
                    "sent": 0,
                    "note": "FINDER-FAILED — fetch %s: %s. Never silent 0."
                    % (type(exc).__name__, exc),
                    "search_space": ["--url", args.url, API_HOST],
                },
                sys.stdout,
                indent=2,
            )
            sys.stdout.write("\n")
            return 1
    else:
        json.dump(
            {
                "state": "FINDER-FAILED",
                "sent": 0,
                "note": "FINDER-FAILED — pass --html-file or --url. Never silent 0.",
                "search_space": ["--html-file", "--url", "--self-test"],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1
    row = run_pipeline(html_text, url=url)
    json.dump(row, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if row.get("state") == "DRAFT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
