#!/usr/bin/env python3
"""Website → external prospects → email drafts → staged call bookings.

Commons composition of the Explee auto-GTM loop. The website is the seed.
Live send is refused until an owner mailbox exists. This lane does not remint
revenue/smart_outreach, revenue/subzero_gtm, or Swarm Mail.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "revenue" / "website_people_email_book" / "fixture_seller.html"
DEFAULT_LOOP = ROOT / "revenue" / "website_people_email_book" / "loop.json"
DEFAULT_PROSPECTS = ROOT / "revenue" / "smart_outreach" / "candidates.json"
DEFAULT_RECEIPTS = ROOT / "revenue" / "payment_ready" / "outreach_receipts"
SCHEMA_VERSION = "commons-website-people-email-book/v2"
KIND = "WEBSITE_PEOPLE_EMAIL_BOOK_LOOP"
MEASURED_AT = "2026-08-30T15:20:37Z"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
ICP_RE = re.compile(r"data-icp[^>]*>(.*?)</", re.I | re.S)
CAL_RE = re.compile(r"https://(?:www\.)?(?:cal\.com|calendly\.com)/[^\s\"']+", re.I)
PERSON_RE = re.compile(
    r"<(?P<tag>article|div|section|li)(?P<attrs>[^>]*\bdata-person\b[^>]*)>(?P<body>.*?)</(?P=tag)>",
    re.I | re.S,
)
JSONLD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S,
)
MAILTO_RE = re.compile(r"mailto:([^\"'\s>]+)", re.I)
NAME_RE = re.compile(r"itemprop=[\"']name[\"'][^>]*>([^<]+)", re.I)
H2_RE = re.compile(r"<h2[^>]*>([^<]+)", re.I)
ROLE_PROP_RE = re.compile(r"itemprop=[\"']jobTitle[\"'][^>]*>([^<]+)", re.I)
ROLE_DATA_RE = re.compile(r"data-role[^>]*>([^<]+)", re.I)
NEED_RE = re.compile(r"data-need[^>]*>([^<]+)", re.I)
DOES_NOT_REPLACE = [
    "revenue/smart_outreach",
    "host/smart_outreach.py",
    "revenue/subzero_gtm",
    "host/swarm_mail.py",
    "revenue/reply_to_revenue",
]
COMPOSE = {
    "smart_outreach": "current evidence-bound prospect discovery and collision qualification",
    "swarm_mail": "later exact-once transport after owner mailbox",
    "subzero_gtm": "different surface; SUBZERO SKU architecture; that leftover forbids outreach",
    "reply_to_revenue": "inbound cash truth after replies exist",
}


class LoopError(ValueError):
    """The website loop input is incomplete or contradictory."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def squeeze(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(value: str) -> str:
    return squeeze(re.sub(r"<[^>]+>", " ", value))


def normalize_email(value: str) -> str | None:
    text = value.strip()
    if text.lower().startswith("mailto:"):
        text = text[7:]
    text = text.split("?", 1)[0].strip().lower()
    if EMAIL_RE.fullmatch(text) and len(text) <= 254:
        return text
    return None


def person_id(name: str, email: str | None) -> str:
    raw = email.replace("@", "-").replace(".", "-") if email else name.casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if len(slug) < 3:
        slug = f"person-{slug or 'unknown'}"
    return slug[:80]


def _first(regex: re.Pattern[str], text: str) -> str:
    match = regex.search(text)
    if not match:
        return ""
    return strip_tags(match.group(1))


def _is_person_type(value: Any) -> bool:
    if isinstance(value, str):
        return value == "Person" or value.endswith("Person")
    if isinstance(value, list):
        return any(_is_person_type(item) for item in value)
    return False


def _ld_people(blob: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return []
    nodes: list[Any]
    if isinstance(payload, list):
        nodes = payload
    elif isinstance(payload, dict):
        graph = payload.get("@graph")
        nodes = graph if isinstance(graph, list) else [payload]
    else:
        return []
    found: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not _is_person_type(node.get("@type")):
            continue
        email = None
        raw_email = node.get("email")
        if isinstance(raw_email, str):
            email = normalize_email(raw_email)
        name = squeeze(str(node.get("name") or ""))
        role = squeeze(str(node.get("jobTitle") or node.get("role") or ""))
        need = squeeze(str(node.get("description") or ""))
        if not name and not email:
            continue
        found.append(
            {
                "name": name or (email.split("@", 1)[0] if email else ""),
                "role": role or None,
                "email": email,
                "need": need or None,
                "source": "json-ld",
            }
        )
    return found


def _page_people(html: str) -> list[dict[str, Any]]:
    people: list[dict[str, Any]] = []
    seen_email: set[str] = set()
    seen_name: set[str] = set()
    for match in PERSON_RE.finditer(html):
        body = match.group("body")
        email_match = MAILTO_RE.search(body)
        email = normalize_email(email_match.group(1)) if email_match else None
        name = _first(NAME_RE, body) or _first(H2_RE, body)
        role = _first(ROLE_PROP_RE, body) or _first(ROLE_DATA_RE, body) or None
        need = _first(NEED_RE, body) or None
        if not name and not email:
            continue
        if not name and email:
            name = email.split("@", 1)[0]
        # Apply the same first-seen identity rule as the JSON-LD fallback below.
        if email and email in seen_email:
            continue
        if not email and name.casefold() in seen_name:
            continue
        person = {
            "name": name,
            "role": role,
            "email": email,
            "need": need,
            "source": "page-person",
        }
        people.append(person)
        if email:
            seen_email.add(email)
        seen_name.add(name.casefold())
    for blob in JSONLD_RE.findall(html):
        for person in _ld_people(blob):
            email = person["email"]
            if email and email in seen_email:
                continue
            if not email and person["name"].casefold() in seen_name:
                continue
            people.append(person)
            if email:
                seen_email.add(email)
            seen_name.add(person["name"].casefold())
    for match in MAILTO_RE.finditer(html):
        email = normalize_email(match.group(1))
        if not email or email in seen_email:
            continue
        name = email.split("@", 1)[0]
        people.append(
            {
                "name": name,
                "role": None,
                "email": email,
                "need": None,
                "source": "mailto",
            }
        )
        seen_email.add(email)
    return people


class _WebsiteAttributes(HTMLParser):
    """Read metadata and explicit booking links independently of attribute order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.description = ""
        self.og_description = ""
        self.book_url = ""
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Keep the first occurrence, as HTML does for duplicate attributes.
        values: dict[str, str] = {}
        for name, value in attrs:
            values.setdefault(name, value or "")
        if tag == "meta":
            content = squeeze(values.get("content", ""))
            if values.get("name", "").strip().casefold() == "description":
                if not self.description:
                    self.description = content
            if values.get("property", "").strip().casefold() == "og:description":
                if not self.og_description:
                    self.og_description = content
        elif tag == "base" and self.base_href is None and "href" in values:
            self.base_href = values["href"].strip()
        elif tag == "a" and "data-book-url" in values and not self.book_url:
            self.book_url = values.get("href", "").strip()


def extract_website(html: str, source: str) -> dict[str, Any]:
    title = _first(TITLE_RE, html)
    headline = _first(H1_RE, html) or title
    attributes = _WebsiteAttributes()
    attributes.feed(html)
    attributes.close()
    description = attributes.description or attributes.og_description
    icp = _first(ICP_RE, html)
    book = attributes.book_url
    if not book:
        cal = CAL_RE.search(html)
        if cal:
            book = cal.group(0).rstrip(">\"'")
    if book:
        # A draft leaves the source page, so relative hrefs need its document URL.
        # File fixtures have no known web origin; keep their original URL text.
        try:
            origin = urlparse(source)
            if origin.scheme in {"http", "https"} and origin.netloc:
                base = source
                if attributes.base_href is not None:
                    base = urljoin(source, attributes.base_href)
                book = urljoin(base, book)
        except ValueError:
            # An invalid source/base URL must not discard other extracted data.
            pass
    return {
        "source": source,
        "title": title,
        "headline": headline,
        "description": description,
        "icp": icp,
        "book_url": book or None,
    }


def _finish_seller_contact(raw: dict[str, Any]) -> dict[str, Any]:
    email = raw["email"]
    name = raw["name"]
    return {
        "contact_id": person_id(name, email),
        "name": name,
        "role": raw["role"],
        "email": email,
        "need": raw["need"],
        "source": raw["source"],
        "route": {
            "kind": "EMAIL",
            "value": email,
            "state": "VERIFIED" if email else "UNVERIFIED",
        },
        "next_action": "seller context only; never treat this site's own contact as a prospect",
    }


def _draft(prospect: dict[str, Any], website: dict[str, Any]) -> dict[str, str]:
    organization = prospect["organization"]
    role = prospect["owner_role"] or f"{organization} team"
    need = prospect["evidence"]["exact_quote"]
    book = website["book_url"] or "reply with a time (owner calendar not attached yet)"
    subject = f"One bounded proof for {organization}"
    body = (
        f"Hi {role},\n\n"
        f"Your public page says: \"{need}\"\n"
        f"Source: {prospect['evidence']['source_url']}\n\n"
        f"{website['headline']}. {website['description']}\n"
        f"This is for: {website['icp']}\n\n"
        f"If that is still true, book a call: {book}\n\n"
        f"If this is not relevant, reply no or opt out and I will close it.\n\n"
        f"— Commons draft only. Not sent. Live send waits on the owner mailbox."
    )
    return {"subject": subject, "body": body}


def _booking(prospect: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    book_url = website["book_url"]
    return {
        "prospect_id": prospect["prospect_id"],
        "state": "STAGED_NOT_BOOKED",
        "book_url": book_url,
        "calendar": "SITE_BOOK_URL" if book_url else "NEEDS_OWNER_CALENDAR",
        "calls_booked": 0,
        "next_action": "copy the book URL into the draft; do not write a live calendar event",
    }


_GTM_INDEX = None


def _load_gtm_index() -> Any:
    global _GTM_INDEX
    if _GTM_INDEX is not None:
        return _GTM_INDEX
    path = ROOT / "host" / "lm_gtm_index.py"
    spec = importlib.util.spec_from_file_location("commons_lm_gtm_index", path)
    if spec is None or spec.loader is None:
        raise LoopError("cannot load LLM-native GTM index")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _GTM_INDEX = module
    return module


def _load_smart_outreach() -> Any:
    path = ROOT / "host" / "smart_outreach.py"
    spec = importlib.util.spec_from_file_location("commons_smart_outreach", path)
    if spec is None or spec.loader is None:
        raise LoopError("cannot load evidence-bound smart outreach planner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seller_domains(source: str, contacts: list[dict[str, Any]]) -> set[str]:
    domains = {
        contact["email"].rsplit("@", 1)[1]
        for contact in contacts
        if isinstance(contact.get("email"), str)
    }
    if source.startswith("https://"):
        hostname = (urlparse(source).hostname or "").casefold()
        if hostname:
            domains.add(hostname.removeprefix("www."))
    return domains


def _prospects(
    catalog: dict[str, Any],
    receipt_directory: Path,
    seller_contacts: list[dict[str, Any]],
    source: str,
) -> list[dict[str, Any]]:
    planner = _load_smart_outreach()
    plan = planner.build_plan(catalog, receipt_directory)
    seller_emails = {
        contact["email"] for contact in seller_contacts if isinstance(contact.get("email"), str)
    }
    seller_domains = _seller_domains(source, seller_contacts)
    results: list[dict[str, Any]] = []
    for item in plan["items"]:
        recipient = item["recipient_email"]
        decision = item["decision"]
        next_action = item["next_action"]
        recipient_domain = recipient.rsplit("@", 1)[1] if isinstance(recipient, str) else None
        if recipient in seller_emails or recipient_domain in seller_domains:
            decision = "HOLD_SELLER_CONTACT"
            next_action = "seller contact is context, not an external prospect; do not draft"
        elif decision == "READY_TO_DRAFT" and (
            not isinstance(recipient, str)
            or item["route"].get("kind") != "EMAIL"
            or item["route"].get("state") != "VERIFIED"
        ):
            decision = "RESEARCH_REQUIRED"
            next_action = "find one verified first-party email route; do not invent a mailbox"
        results.append(
            {
                "prospect_id": item["prospect_id"],
                "organization": item["organization"],
                "owner_role": item["owner_role"],
                "recipient_email": recipient,
                "evidence": dict(item["evidence"]),
                "route": dict(item["route"]),
                "score": item["score"],
                "decision": decision,
                "collision_receipts": list(item["collision_receipts"]),
                "occupied_by": item["occupied_by"],
                "next_action": next_action,
            }
        )
    return results


def _mailbox_state(status: dict[str, Any] | None) -> str:
    if status is None:
        return "NEEDS_OWNER_MAILBOX"
    if not isinstance(status, dict):
        raise LoopError("mailbox status must be one redacted Swarm Mail status object")
    if set(status) != {"kind", "inboxes", "counts", "commercial_success"}:
        raise LoopError("mailbox status fields differ from the Swarm Mail redacted projection")
    if status["kind"] != "SWARM_MAIL_PRIVATE_RUNTIME_STATUS":
        raise LoopError("mailbox status kind is invalid")
    if status["commercial_success"] != "UNMEASURED_BY_MAIL":
        raise LoopError("mailbox status cannot claim commercial success")
    if "@" in canonical_text(status):
        raise LoopError("mailbox status must not contain an email address")
    inboxes = status["inboxes"]
    counts = status["counts"]
    if not isinstance(inboxes, list) or not isinstance(counts, dict):
        raise LoopError("mailbox status inboxes and counts are invalid")
    measured_count = counts.get("measured_inboxes")
    if type(measured_count) is not int or measured_count < 0:
        raise LoopError("mailbox measured_inboxes must be one non-negative integer")
    measured = 0
    codex: list[dict[str, Any]] = []
    for index, inbox in enumerate(inboxes):
        if not isinstance(inbox, dict) or set(inbox) != {
            "inbox_id", "model_family", "state", "address_ref"
        }:
            raise LoopError(f"mailbox status inboxes[{index}] fields are invalid")
        if inbox["state"] not in {"UNPROVISIONED", "MEASURED"}:
            raise LoopError(f"mailbox status inboxes[{index}].state is invalid")
        address_ref = inbox["address_ref"]
        if inbox["state"] == "MEASURED":
            measured += 1
            if not isinstance(address_ref, str) or not address_ref.startswith("opaque:"):
                raise LoopError("measured mailbox needs one opaque address reference")
        elif address_ref is not None:
            raise LoopError("unprovisioned mailbox cannot expose an address reference")
        if inbox["inbox_id"] == "codex-sales":
            codex.append(inbox)
    if measured_count != measured:
        raise LoopError("mailbox measured_inboxes count does not match inbox states")
    if len(codex) != 1 or codex[0]["model_family"] != "CODEX":
        raise LoopError("mailbox status must contain exactly one Codex sales inbox")
    if codex[0]["state"] == "MEASURED":
        return "OWNER_MAILBOX_MEASURED"
    return "NEEDS_OWNER_MAILBOX"


def build_loop(
    html: str,
    source: str,
    prospect_catalog: dict[str, Any] | None = None,
    receipt_directory: Path = DEFAULT_RECEIPTS,
    generated_at: str = MEASURED_AT,
    mailbox_status: dict[str, Any] | None = None,
    owner: str | None = None,
    enforce_sales_occupancy: bool = False,
    index_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    if not isinstance(html, str) or not html.strip():
        raise LoopError("html must be non-empty")
    website = extract_website(html, source)
    seller_contacts = [_finish_seller_contact(raw) for raw in _page_people(html)]
    if prospect_catalog is None:
        prospect_catalog = json.loads(DEFAULT_PROSPECTS.read_text(encoding="utf-8"))
    prospects = _prospects(prospect_catalog, receipt_directory, seller_contacts, source)
    mailbox_state = _mailbox_state(mailbox_status)
    emails: list[dict[str, Any]] = []
    bookings: list[dict[str, Any]] = []
    gtm = _load_gtm_index() if enforce_sales_occupancy else None
    for prospect in prospects:
        if prospect["decision"] != "READY_TO_DRAFT":
            continue
        if gtm is not None:
            gtm.assert_sales_owner(
                subject_id=prospect["prospect_id"],
                owner=owner or "",
                paths=index_paths,
            )
        emails.append(
            {
                "prospect_id": prospect["prospect_id"],
                "to": prospect["recipient_email"],
                "draft": _draft(prospect, website),
                "transport": "STAGED_NOT_SENT",
            }
        )
        bookings.append(_booking(prospect, website))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "website": website,
        "seller_contacts": seller_contacts,
        "prospects": prospects,
        "emails": emails,
        "bookings": bookings,
        "mailbox_runtime": mailbox_status,
        "truth": {
            "websites_ingested": 1,
            "prospects_found": len(prospects),
            "seller_contacts_observed": len(seller_contacts),
            "people_with_verified_email": len(emails),
            "emails_drafted": len(emails),
            "calls_booked": 0,
            "transport_actions": 0,
            "contacts_claimed": 0,
            "cash_usd": 0,
            "mailbox": mailbox_state,
        },
        "compose": dict(COMPOSE),
        "does_not_replace": list(DOES_NOT_REPLACE),
    }


def validate_loop(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != KIND:
        raise LoopError("unsupported loop version or kind")
    truth = value.get("truth")
    if not isinstance(truth, dict):
        raise LoopError("truth must be an object")
    if truth.get("transport_actions") != 0:
        raise LoopError("this lane cannot claim transport actions")
    if truth.get("calls_booked") != 0:
        raise LoopError("this lane cannot claim live bookings")
    if truth.get("cash_usd") != 0:
        raise LoopError("this lane cannot claim cash")
    mailbox_state = _mailbox_state(value.get("mailbox_runtime"))
    if truth.get("mailbox") != mailbox_state:
        raise LoopError("mailbox truth must match the redacted Swarm Mail runtime status")
    emails = value.get("emails")
    if not isinstance(emails, list):
        raise LoopError("emails must be an array")
    prospects = value.get("prospects")
    if not isinstance(prospects, list):
        raise LoopError("prospects must be an array")
    ready = {
        item.get("prospect_id"): item
        for item in prospects
        if isinstance(item, dict) and item.get("decision") == "READY_TO_DRAFT"
    }
    seller_emails = {
        item.get("email")
        for item in value.get("seller_contacts", [])
        if isinstance(item, dict) and isinstance(item.get("email"), str)
    }
    for item in emails:
        if not isinstance(item, dict) or item.get("transport") != "STAGED_NOT_SENT":
            raise LoopError("every email must remain STAGED_NOT_SENT")
        to = item.get("to")
        if not isinstance(to, str) or normalize_email(to) is None:
            raise LoopError("email to= must be one verified external prospect address")
        prospect = ready.get(item.get("prospect_id"))
        if prospect is None or prospect.get("recipient_email") != to:
            raise LoopError("every email must map to one READY_TO_DRAFT prospect")
        if to in seller_emails:
            raise LoopError("seller contacts cannot be used as outreach prospects")
    return value


def fetch_url(url: str) -> str:
    if not url.startswith("https://"):
        raise LoopError("url must be https")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Commons website-people-email-book/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LoopError(f"cannot fetch {url}: {error}") from error


def summary(loop: dict[str, Any]) -> str:
    truth = loop["truth"]
    return (
        f"VALID {truth['websites_ingested']} website {truth['prospects_found']} prospects "
        f"{truth['emails_drafted']} drafts {truth['calls_booked']} booked {truth['transport_actions']} sent"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--html", type=Path, default=DEFAULT_FIXTURE)
    run.add_argument("--url")
    run.add_argument("--prospects", type=Path, default=DEFAULT_PROSPECTS)
    run.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    run.add_argument(
        "--mailbox-status",
        type=Path,
        help="redacted output from swarm_mail.py status; never an address or credential file",
    )
    run.add_argument("--output", type=Path)
    run.add_argument("--generated-at", default=MEASURED_AT)
    run.add_argument("--owner", default="", help="live occupant; sales/draft/outreach without a match exits 4")
    subparsers.add_parser("validate").add_argument("--input", type=Path, default=DEFAULT_LOOP)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--send" in argv or (argv[:1] == ["send"]):
        sys.stderr.write(
            "REFUSED live send: this planner never transports mail. "
            "Use Swarm Mail after measured provisioning; drafts and bookings stay staged.\n"
        )
        return 3
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        validate_loop(raw)
        print(summary(raw))
        return 0
    if args.url:
        html = fetch_url(args.url)
        source = args.url
    else:
        html = args.html.read_text(encoding="utf-8")
        try:
            source = args.html.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            source = str(args.html)
    catalog = json.loads(args.prospects.read_text(encoding="utf-8"))
    mailbox_status = (
        json.loads(args.mailbox_status.read_text(encoding="utf-8"))
        if args.mailbox_status
        else None
    )
    gtm = _load_gtm_index()
    try:
        loop = build_loop(
            html,
            source,
            prospect_catalog=catalog,
            receipt_directory=args.receipts,
            generated_at=args.generated_at,
            mailbox_status=mailbox_status,
            owner=args.owner,
            enforce_sales_occupancy=True,
        )
    except gtm.UnclaimedSales as error:
        sys.stderr.write(str(error) + "\n")
        return 4
    except gtm.IndexError_ as error:
        sys.stderr.write(str(error) + "\n")
        return 1
    validate_loop(loop)
    rendered = canonical_text(loop)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
