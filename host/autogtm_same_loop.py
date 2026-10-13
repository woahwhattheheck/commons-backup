#!/usr/bin/env python3
"""Same AutoGTM loop as Explee public mechanism + cmn-labs/autogtm.

Bryce 2026-09-02 Slack C0BU51F1PL3 `1788376550.004339`: use Explee or find
their repo/skill and do the exact same thing.

Public mechanism (explee.com): paste website → research market → sharpen ICP
→ find high-intent people → write personal email → handle replies / book.

Open-source twin (github.com/cmn-labs/autogtm, AGPL, cited not copied):
set context → generate queries → search/extract → enrich/score → draft
campaign → approve or Autopilot sweep → status sync.

This lane composes existing website-people-email-book + smart_outreach.
It does not remint those ids. Live send stays STAGED. Explee HTTP API
without a private key is FINDER-FAILED (401 Missing API key), never a
Commons door lock and never silent 0.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = ROOT / "revenue" / "website_people_email_book" / "fixture_seller.html"
DEFAULT_PROSPECTS = ROOT / "revenue" / "smart_outreach" / "candidates.json"
EXPLEE_PROJECTS = "https://api.explee.com/public/api/v1/autogtm/projects"
OPEN_TWIN = "https://github.com/cmn-labs/autogtm"
EXPLEE_DOOR = "https://explee.com/"
MCP_TWIN = "https://github.com/digitaldrreamer/explee-mcp"
STEPS = (
    "set_context",
    "choose_mode",
    "generate_queries",
    "search_extract",
    "enrich_score",
    "draft_campaign",
    "approve_or_autopilot",
    "sync_status",
)
DO_NOT_REMINT = (
    "website-people-email-book-20260830-01",
    "host/website_people_email_book.py",
    "host/smart_outreach.py",
    "cursor-claude-peer-check-refuse-as-graduate-readback-20260902-01",
)


Opener = Callable[[str], tuple[int, str]]
WPEB_PATH = ROOT / "host" / "website_people_email_book.py"


class CatalogError(ValueError):
    """The local prospect catalog does not match the AutoGTM input contract."""


def _load_wpeb() -> Any:
    spec = importlib.util.spec_from_file_location("website_people_email_book", WPEB_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("FINDER-FAILED: host/website_people_email_book.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_opener(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "commons-autogtm-same-loop/1", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")[:800]
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:800]
        return int(error.code), body
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, str(error)


def probe_explee(opener: Opener = live_opener) -> dict[str, Any]:
    code, body = opener(EXPLEE_PROJECTS)
    missing = code == 401 and "Missing API key" in body
    return {
        "asked": True,
        "url": EXPLEE_PROJECTS,
        "http": code,
        "body_snip": body[:200],
        "state": "FINDER-FAILED" if missing or code in (0, 401, 403, 404) else "HIT",
        "permission": False,
        "note": (
            "Explee AutoGTM HTTP API is a private-credential agent road. "
            "401 Missing API key is FINDER-FAILED, never a Commons posting lock, never silent 0."
        ),
        "external": "EXTERNAL_PROVIDER_ACTION",
        "door": EXPLEE_DOOR,
    }


def set_context(html: str, source: str) -> dict[str, Any]:
    website = _load_wpeb().extract_website(html, source)
    offer = website.get("headline") or website.get("title") or "unspecified offer"
    icp = website.get("icp") or "unspecified ICP"
    return {
        "source": source,
        "offer": str(offer)[:200],
        "icp": str(icp)[:200],
        "book_url": website.get("book_url"),
        "composed_from": "host/website_people_email_book.py#extract_website",
        "state": "INTEGRATED",
    }


def choose_mode(asked_autopilot: bool) -> str:
    return "autopilot" if asked_autopilot else "run_now"


def generate_queries(context: dict[str, Any]) -> list[str]:
    offer = context["offer"]
    icp = context["icp"]
    return [
        f"decision makers who buy {offer}",
        f"{icp} owner",
        f"CEO of teams that need {offer}",
    ]


def enrich_score(prospect: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    blob = json.dumps(prospect, sort_keys=True).lower() + " " + context["icp"].lower()
    needles = ("agent", "crash", "resume", "production", "founder", "owner")
    hits = sum(1 for n in needles if n in blob)
    score = min(10, 4 + hits)
    email = prospect.get("recipient_email")
    ready = bool(email) and not prospect.get("do_not_contact") and not prospect.get("occupied_by")
    return {
        "prospect_id": prospect.get("prospect_id"),
        "organization": prospect.get("organization"),
        "email": email,
        "fit": score,
        "ready": ready,
        "occupied_by": prospect.get("occupied_by"),
        "evidence": (prospect.get("evidence") or {}).get("source_url"),
    }


def draft_campaign(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    org = row["organization"] or row["prospect_id"]
    return {
        "prospect_id": row["prospect_id"],
        "to": row["email"],
        "subject": f"{context['offer'][:72]} — crash-resume receipt",
        "body": (
            f"Hi {org},\n\n"
            f"Saw {row.get('evidence') or 'your public page'}. "
            f"{context['offer']} is a same-day crash-resume proof for production agents. "
            "No invented buyers. Draft only until an owner mailbox exists.\n"
        ),
        "state": "DRAFT",
        "sent": False,
    }


def search_extract(catalog: Any) -> list[dict[str, Any]]:
    if not isinstance(catalog, dict):
        raise CatalogError("prospect catalog must be an object")
    prospects = catalog.get("prospects")
    if prospects is None:
        return []
    if not isinstance(prospects, list):
        raise CatalogError("prospect catalog prospects must be a list")
    result: list[dict[str, Any]] = []
    for index, prospect in enumerate(prospects):
        if not isinstance(prospect, dict):
            raise CatalogError(f"prospect catalog row {index} must be an object")
        evidence = prospect.get("evidence")
        if evidence is not None and not isinstance(evidence, dict):
            raise CatalogError(f"prospect catalog row {index} evidence must be an object or null")
        result.append(prospect)
    return result


def approve_or_autopilot(asked_autopilot: bool) -> dict[str, Any]:
    if asked_autopilot:
        return {
            "asked": True,
            "state": "REFUSED",
            "sent": False,
            "booked": 0,
            "note": "Autopilot send is refused until an owner mailbox exists. Refuse is not a send.",
        }
    return {
        "asked": False,
        "state": "UNASKED",
        "sent": False,
        "booked": 0,
        "note": "Unasked Autopilot is not a send and not permission.",
    }


def sync_status(
    drafts: list[dict[str, Any]],
    autopilot: dict[str, Any],
    explee: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sent": False,
        "booked": 0,
        "cash_usd": 0,
        "drafts": len(drafts),
        "autopilot": autopilot["state"],
        "explee": explee["state"],
        "state": "INTEGRATED",
    }


def measure(
    *,
    html: str,
    source: str,
    catalog: dict[str, Any],
    asked_autopilot: bool = False,
    opener: Opener = live_opener,
) -> dict[str, Any]:
    context = set_context(html, source)
    mode = choose_mode(asked_autopilot)
    queries = generate_queries(context)
    prospects = search_extract(catalog)
    scored = [enrich_score(p, context) for p in prospects]
    drafts = [draft_campaign(row, context) for row in scored if row["ready"] and row["fit"] >= 6]
    autopilot = approve_or_autopilot(asked_autopilot)
    explee = probe_explee(opener)
    status = sync_status(drafts, autopilot, explee)
    return {
        "kind": "AUTOGTM_SAME_LOOP",
        "schema": "commons-autogtm-same-loop/v1",
        "no_auth": True,
        "no_gate": True,
        "posting": "OPEN",
        "permission": False,
        "steps": list(STEPS),
        "twin": {"autogtm": OPEN_TWIN, "explee_mcp": MCP_TWIN, "explee": EXPLEE_DOOR},
        "context": context,
        "mode": mode,
        "queries": queries,
        "search": {
            "local_catalog": str(DEFAULT_PROSPECTS.relative_to(ROOT)),
            "exa": "EXTERNAL_PROVIDER_ACTION",
            "instantly": "EXTERNAL_PROVIDER_ACTION",
            "found": len(prospects),
        },
        "scored": scored,
        "drafts": drafts,
        "autopilot": autopilot,
        "explee_api": explee,
        "sent": status["sent"],
        "booked": status["booked"],
        "cash_usd": status["cash_usd"],
        "status": status,
        "do_not_remint": list(DO_NOT_REMINT),
        "state": status["state"],
        "x": list(STEPS) + [EXPLEE_PROJECTS, OPEN_TWIN],
        "y": {
            "drafts": len(drafts),
            "sent": False,
            "explee": explee["state"],
            "autopilot": autopilot["state"],
        },
        "z": {
            "explee": explee["state"],
            "autopilot": autopilot["state"],
            "sent": False,
        },
    }


def load_html(url: str | None, html_path: Path) -> tuple[str, str]:
    if url:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("url must be https")
        req = urllib.request.Request(url, headers={"User-Agent": "commons-autogtm-same-loop/1"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace"), url
    return html_path.read_text(encoding="utf-8"), str(html_path.relative_to(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--url")
    parser.add_argument("--prospects", type=Path, default=DEFAULT_PROSPECTS)
    parser.add_argument("--autopilot", action="store_true")
    parser.add_argument("--use-explee", action="store_true", dest="use_explee")
    args = parser.parse_args(argv)
    html, source = load_html(args.url, args.html)
    catalog = json.loads(args.prospects.read_text(encoding="utf-8"))
    row = measure(
        html=html,
        source=source,
        catalog=catalog,
        asked_autopilot=args.autopilot,
        opener=live_opener,
    )
    if os.environ.get("EXPLEE_API_KEY"):
        row["explee_api"]["note"] = (
            row["explee_api"]["note"]
            + " A private key may exist in this agent environment; it is never copied onto Commons."
        )
    if args.json or True:
        sys.stdout.write(json.dumps(row, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
