#!/usr/bin/env python3
"""First-party pack waitlist. Consent + CCPA. JSONL. Counts only. Zero sends.

SCOUT scout-demand-pack-door-waitlist-20260902-01: shared packs/waitlist.html
with email, tier-of-interest, and state. Consent at the form (what is
collected; may be used to reach on X / TikTok / Meta; unsubscribe any time).
Do Not Sell or Share My Personal Information on the form (required before any
pixel fires). Storage is owner-local append-only JSONL the owner can export.
This helper does not steal revenue/swarm_mail or AgentMail engines. Public
readback is a count per tier with zero addresses. The list is an unsent
asset. Sending is owner-gated. No auth, no gate, no pixel mint, no spend.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_WAITLIST.json"
DEFAULT_DOOR = ROOT / "packs" / "waitlist.html"
DEFAULT_COUNTS = ROOT / "packs" / "waitlist-counts.json"
DEFAULT_SLOT = ROOT / "packs" / "_template" / "waitlist-slot.md"

DO_NOT_STEAL = (
    "revenue/swarm_mail",
    "packs/thanks.html",
    "ground/BUSINESS_PACK_THANKS.json",
    "host/business_pack_thanks.py",
    "host/business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/lotribbon-greetings-20260902-01",
    "revenue/business_packs_marketing/DATA_BUYING.md",
)

TIERS = ("keep", "shop", "unique", "desk", "plant", "enterprise", "other")
US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SRC_RE = re.compile(r"""\bsrc\s*=\s*['\"]([^'\"]+)['\"]""", re.I)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result"
)
THIRD_PARTY_SRC = (
    "ads-twitter.com",
    "static.ads-twitter.com",
    "analytics.tiktok.com",
    "facebook.net",
    "connect.facebook.net",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
)
CCPA_PHRASE = "Do Not Sell or Share My Personal Information"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    return data


def load_law(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_LAW)


def third_party_script_srcs(html: str) -> list[str]:
    found: list[str] = []
    for match in SRC_RE.finditer(html or ""):
        src = match.group(1)
        lowered = src.lower()
        if any(marker in lowered for marker in THIRD_PARTY_SRC):
            found.append(src)
    return found


def empty_counts() -> dict[str, Any]:
    return {
        "addresses_public": False,
        "sends": 0,
        "total": 0,
        "tiers": {name: 0 for name in TIERS},
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_email(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def normalize_tier(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_state(value: Any) -> str:
    return str(value or "").strip().upper()


def public_counts_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Last record per email wins. Opt-out drops the address from counts."""
    latest: dict[str, dict[str, Any]] = {}
    for row in records:
        email = normalize_email(row.get("email"))
        if not email:
            continue
        latest[email] = row
    counts = empty_counts()
    for row in latest.values():
        kind = str(row.get("kind") or "signup").strip().lower()
        if kind == "opt_out":
            continue
        if row.get("consent") is not True:
            continue
        if row.get("ccpa_do_not_sell") is True and kind != "signup":
            continue
        tier = normalize_tier(row.get("tier"))
        if tier not in counts["tiers"]:
            continue
        counts["tiers"][tier] += 1
        counts["total"] += 1
    counts["addresses_public"] = False
    counts["sends"] = 0
    return counts


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        if isinstance(row, dict):
            out.append(row)
    return out


def public_counts(jsonl_path: Path) -> dict[str, Any]:
    counts = public_counts_from_records(read_jsonl(jsonl_path))
    dumped = json.dumps(counts)
    if "@" in dumped:
        raise RuntimeError("public counts leaked an address")
    return counts


def write_public_counts(jsonl_path: Path, counts_path: Path) -> dict[str, Any]:
    counts = public_counts(jsonl_path)
    counts_path.write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    return counts


def pixel_allowed(ccpa_do_not_sell: bool, pixel_id: str | None) -> bool:
    """CCPA opt-out and empty slots both load nothing."""
    if ccpa_do_not_sell:
        return False
    return bool(str(pixel_id or "").strip())


def sends() -> int:
    """The list is an unsent asset. This helper never mails."""
    return 0


def validate_signup(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    kind = str(data.get("kind") or "signup").strip().lower()
    email = normalize_email(data.get("email"))
    tier = normalize_tier(data.get("tier"))
    state = normalize_state(data.get("state"))
    consent = data.get("consent") is True or str(data.get("consent") or "").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }
    ccpa = data.get("ccpa_do_not_sell") is True or str(
        data.get("ccpa_do_not_sell") or ""
    ).lower() in {"1", "true", "on", "yes"}
    missing: list[str] = []
    if not EMAIL_RE.match(email):
        missing.append("email")
    if kind == "opt_out":
        if missing:
            return {"verdict": "WAITLIST_INVALID", "missing": missing, "kind": kind}
        return {
            "verdict": "OPT_OUT_OK",
            "kind": "opt_out",
            "email": email,
            "tier": "",
            "state": "",
            "consent": False,
            "ccpa_do_not_sell": True,
            "pixel_allowed": False,
            "sends": 0,
        }
    if tier not in TIERS:
        missing.append("tier")
    if state not in US_STATES:
        missing.append("state")
    if not consent:
        missing.append("consent")
    if missing:
        return {"verdict": "WAITLIST_INVALID", "missing": missing, "kind": kind}
    return {
        "verdict": "SIGNUP_OK",
        "kind": "signup",
        "email": email,
        "tier": tier,
        "state": state,
        "consent": True,
        "ccpa_do_not_sell": ccpa,
        "pixel_allowed": pixel_allowed(ccpa, ""),
        "sends": 0,
    }


def append_signup(jsonl_path: Path, raw: dict[str, Any] | None) -> dict[str, Any]:
    checked = validate_signup(raw)
    if checked["verdict"] not in {"SIGNUP_OK", "OPT_OUT_OK"}:
        checked["counts"] = public_counts(jsonl_path)
        return checked
    record = {
        "ts": _now(),
        "kind": checked["kind"],
        "email": checked["email"],
        "tier": checked.get("tier") or "",
        "state": checked.get("state") or "",
        "consent": checked["consent"],
        "ccpa_do_not_sell": checked["ccpa_do_not_sell"],
        "sends": 0,
    }
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    counts = public_counts(jsonl_path)
    return {
        "verdict": checked["verdict"],
        "kind": checked["kind"],
        "sends": 0,
        "pixel_allowed": False if checked["ccpa_do_not_sell"] else checked["pixel_allowed"],
        "counts": counts,
        "addresses_public": False,
    }


def parse_body(raw: bytes, content_type: str) -> dict[str, Any]:
    text = (raw or b"").decode("utf-8")
    if "application/json" in (content_type or "") or text.lstrip().startswith("{"):
        loaded = json.loads(text or "{}")
        return loaded if isinstance(loaded, dict) else {}
    parsed = parse_qs(text, keep_blank_values=True)
    out: dict[str, Any] = {}
    for key, values in parsed.items():
        out[key] = values[-1] if values else ""
    if str(out.get("consent") or "").lower() in {"1", "true", "on", "yes"}:
        out["consent"] = True
    if str(out.get("ccpa_do_not_sell") or "").lower() in {"1", "true", "on", "yes"}:
        out["ccpa_do_not_sell"] = True
    return out


def handle_http(
    method: str,
    path: str,
    body: bytes = b"",
    content_type: str = "application/json",
    jsonl_path: Path | None = None,
) -> dict[str, Any]:
    target = jsonl_path or Path("/tmp/tjlabs-waitlist-signups.jsonl")
    route = (path or "/").split("?", 1)[0]
    if method.upper() == "POST" and route in {
        "/waitlist", "/waitlist/", "/", "/waitlist/opt-out", "/opt-out"
    }:
        try:
            payload = parse_body(body, content_type)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {
                "status": 400,
                "body": {
                    "verdict": "WAITLIST_INVALID",
                    "sends": 0,
                    "addresses_public": False,
                    "counts": public_counts(target),
                    "pixel_allowed": False,
                },
            }
    if method.upper() == "GET" and route in {"/waitlist/counts", "/counts", "/waitlist"}:
        counts = public_counts(target)
        return {"status": 200, "body": counts}
    if method.upper() == "POST" and route in {"/waitlist", "/waitlist/", "/"}:
        result = append_signup(target, payload)
        status = 200 if result["verdict"] in {"SIGNUP_OK", "OPT_OUT_OK"} else 400
        public = {
            "verdict": result["verdict"],
            "sends": 0,
            "addresses_public": False,
            "counts": result["counts"],
        }
        dumped = json.dumps(public)
        if "@" in dumped:
            raise RuntimeError("http body leaked an address")
        return {"status": status, "body": public}
    if method.upper() == "POST" and route in {"/waitlist/opt-out", "/opt-out"}:
        payload["kind"] = "opt_out"
        payload["ccpa_do_not_sell"] = True
        result = append_signup(target, payload)
        status = 200 if result["verdict"] == "OPT_OUT_OK" else 400
        public = {
            "verdict": result["verdict"],
            "sends": 0,
            "addresses_public": False,
            "counts": result["counts"],
            "pixel_allowed": False,
        }
        return {"status": status, "body": public}
    return {"status": 404, "body": {"verdict": "NOT_FOUND", "sends": 0}}


def classify_door(html: str | None = None) -> dict[str, Any]:
    if html is None:
        if not DEFAULT_DOOR.is_file():
            return {
                "gate": False,
                "commons_admission": False,
                "verdict": "WAITLIST_DOOR_MISSING",
                "present": False,
            }
        body = DEFAULT_DOOR.read_text(encoding="utf-8")
    else:
        body = html
    lowered = body.lower()
    scripts = third_party_script_srcs(body)
    has_email = 'type="email"' in lowered or "type='email'" in lowered
    has_tier = 'name="tier"' in lowered or 'id="tier"' in lowered
    has_state = 'name="state"' in lowered or 'id="state"' in lowered
    consent = (
        "unsubscribe any time" in lowered
        and "tiktok" in lowered
        and "meta" in lowered
        and (" x" in lowered or "twitter" in lowered or ">x<" in lowered or " x," in lowered)
    )
    ccpa = CCPA_PHRASE.lower() in lowered
    password = 'type="password"' in lowered
    earnings = bool(EARNINGS_RE.search(body))
    form = "<form" in lowered
    robots = "index, follow" in lowered
    missing: list[str] = []
    if not has_email:
        missing.append("email")
    if not has_tier:
        missing.append("tier")
    if not has_state:
        missing.append("state")
    if not consent:
        missing.append("consent")
    if not ccpa:
        missing.append("ccpa")
    if not form:
        missing.append("form")
    if password:
        missing.append("password_field")
    if scripts:
        missing.append("third_party_scripts")
    if earnings:
        missing.append("earnings_claim")
    if not robots:
        missing.append("robots")
    ok = not missing
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": "WAITLIST_DOOR_OK" if ok else "WAITLIST_DOOR_INCOMPLETE",
        "present": True,
        "missing": missing,
        "has_email_field": has_email,
        "has_tier_field": has_tier,
        "has_state_field": has_state,
        "consent_at_form": consent,
        "ccpa_link_present": ccpa,
        "unsubscribe_any_time": "unsubscribe any time" in lowered,
        "password_field": password,
        "static_third_party_scripts": scripts,
        "earnings_claim": earnings,
        "robots_index_follow": robots,
        "sends": 0,
        "list_is_unsent_asset": True,
        "sending_owner_gated": True,
    }


def classify(law: dict[str, Any] | None = None, html: str | None = None) -> dict[str, Any]:
    card = law if isinstance(law, dict) else (load_law() if DEFAULT_LAW.is_file() else {})
    door = classify_door(html)
    slot = DEFAULT_SLOT.is_file()
    slot_text = DEFAULT_SLOT.read_text(encoding="utf-8") if slot else ""
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": door["verdict"],
        "door": door,
        "template_slot_present": slot,
        "template_slot_points_at_shared_door": "packs/waitlist.html" in slot_text,
        "storage": "owner_local_jsonl",
        "did_not_steal_swarm_mail": True,
        "did_not_steal_agentmail": True,
        "did_not_overwrite_thanks_door": True,
        "do_not_steal": list(DO_NOT_STEAL),
        "sends": 0,
        "list_is_unsent_asset": True,
        "sending_owner_gated": True,
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
        "checkout": str(card.get("checkout") or "NOT_MINTED"),
        "law_id": str(card.get("id") or ""),
        "scout_demand_id": str(card.get("scout_demand_id") or ""),
        "post_url_empty_by_default": str(card.get("post_url") or "") == "",
    }


class WaitlistHandler(BaseHTTPRequestHandler):
    jsonl_path: Path = Path("/tmp/tjlabs-waitlist-signups.jsonl")

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        result = handle_http("GET", self.path, jsonl_path=self.jsonl_path)
        self._write(int(result["status"]), result["body"])

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        result = handle_http(
            "POST",
            self.path,
            body=raw,
            content_type=str(self.headers.get("Content-Type") or ""),
            jsonl_path=self.jsonl_path,
        )
        self._write(int(result["status"]), result["body"])


def serve(host: str, port: int, jsonl_path: Path) -> None:
    WaitlistHandler.jsonl_path = jsonl_path
    httpd = ThreadingHTTPServer((host, port), WaitlistHandler)
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="classify")
    parser.add_argument("--jsonl", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=43148)
    parser.add_argument("--email", default="")
    parser.add_argument("--tier", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--consent", action="store_true")
    parser.add_argument("--opt-out", action="store_true")
    args = parser.parse_args(argv)
    jsonl = Path(args.jsonl) if args.jsonl else Path.home() / ".tjlabs" / "waitlist-signups.jsonl"
    if args.command == "serve":
        serve(args.host, args.port, jsonl)
        return 0
    if args.command == "append":
        payload: dict[str, Any] = {
            "email": args.email,
            "tier": args.tier,
            "state": args.state,
            "consent": args.consent,
            "kind": "opt_out" if args.opt_out else "signup",
            "ccpa_do_not_sell": args.opt_out,
        }
        print(json.dumps(append_signup(jsonl, payload), indent=2))
        print("", end="")
        return 0
    if args.command == "counts":
        print(json.dumps(public_counts(jsonl), indent=2))
        print("", end="")
        return 0
    print(json.dumps(classify(), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
