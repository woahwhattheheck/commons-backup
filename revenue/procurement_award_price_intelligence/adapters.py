"""Live, source-bound adapters for procurement award price intelligence.

Adapters fetch code-owned buyer-hosted sources themselves. Caller-authored extraction
may describe a complete reviewed PDF table, but may not mint buyer authority: the
exact fetched source bytes, allowlisted host, content type, lineage, and extraction
state are receipt-bound before rows reach the price-intelligence engine.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from revenue.procurement_award_price_intelligence import engine

ADAPTER_INPUT = "procurement-award-source-adapters/input/v1"
ADAPTER_RECEIPT = "procurement-award-source-adapters/receipt/v1"
TRUTH_BOUNDARY = "INTERNAL_PRICE_RESEARCH_ONLY"
MAX_FETCH_BYTES = 8 * 1024 * 1024

PROFILES = {
    "LEGISTAR_AWARD_HTML_V1": {
        "hosts": {
            "coralgables.legistar.com",
            "mwrd.legistar.com",
            "aurora-il.legistar.com",
            "ocala.legistar.com",
        },
        "content_types": {"text/html", "application/xhtml+xml"},
        "source_class": "BOARD_AWARD",
        "base_price_kind": "AWARD",
        "parser": "LEGISTAR",
    },
    "BUYER_BID_TABULATION_PDF_V1": {
        "hosts": {"www.cityofcoweta-ok.gov", "files.topeka.gov"},
        "content_types": {"application/pdf"},
        "source_class": "BID_TABULATION",
        "base_price_kind": "BID",
        "parser": "REVIEWED_ROWS",
    },
}
RELATIONS = {"ORIGINAL", "AMENDMENT", "OPTION", "RENEWAL"}
MODES = {"LIVE_HTML", "TABULAR_PDF_TEXT", "OCR"}
STATES = {"EXACT", "REVIEWED", "AMBIGUOUS"}
COVERAGE = {"COMPLETE_RECORD", "COMPLETE_TABLE", "PARTIAL", "UNKNOWN"}
DISPOSITIONS = {"INCLUDED_BY_SOURCE", "REJECTED_BY_SOURCE", "UNKNOWN"}

# Buyer-hosted source pages legitimately use a narrow set of public routing
# parameters. Keep those code-owned rather than accepting arbitrary query
# strings that could contain signed URLs, bearer tokens, or caller secrets.
PUBLIC_QUERY_VALUE = {
    "guid": re.compile(r"^[0-9a-f-]{1,64}$", re.I),
    "id": re.compile(r"^[0-9]{1,20}$"),
    "options": re.compile(r"^$"),
    "search": re.compile(r"^$"),
    "bidid": re.compile(r"^[0-9]{0,20}$"),
}
PUBLIC_QUERY_KEYS = {
    "coralgables.legistar.com": {"guid", "id", "options", "search"},
    "mwrd.legistar.com": {"guid", "id", "options", "search"},
    "aurora-il.legistar.com": {"guid", "id", "options", "search"},
    "ocala.legistar.com": {"guid", "id", "options", "search"},
    "www.cityofcoweta-ok.gov": {"bidid"},
    "files.topeka.gov": set(),
}

# Host ownership alone is not an endpoint boundary. These exact public paths
# prevent caller- or redirect-controlled opaque path segments from becoming
# durable evidence fields. Adding a new buyer route requires a code change.
PUBLIC_PATHS = {
    "coralgables.legistar.com": {"/LegislationDetail.aspx"},
    "mwrd.legistar.com": {"/LegislationDetail.aspx"},
    "aurora-il.legistar.com": {"/LegislationDetail.aspx"},
    "ocala.legistar.com": {"/LegislationDetail.aspx"},
    "www.cityofcoweta-ok.gov": {"/DocumentCenter/View/2084/260427-Bid-Tab-PDF"},
    "files.topeka.gov": {"/business/procurement/bid-tabulations/2026/Bid%206.pdf"},
}

INPUT_KEYS = {
    "schema", "dataset_id", "max_source_age_seconds", "truth_boundary",
    "source", "lineage", "extraction", "records", "target",
}
SOURCE_KEYS = {"profile", "uri"}
LINEAGE_KEYS = {"relation", "sequence", "parent_source_sha256"}
EXTRACTION_KEYS = {"mode", "state", "coverage"}
TARGET_KEYS = {"target_id", "currency", "basis", "unit", "term_months", "allowed_price_kinds"}
RECORD_KEYS = {
    "record_id", "claim_key", "opportunity_id", "vendor", "amount_minor",
    "currency", "basis", "unit", "term_months", "event_date", "disposition",
}
FILE_NO = re.compile(r"\bFile\s*#:\s*([A-Za-z0-9._/-]+)", re.I)
FINAL_ACTION = re.compile(r"\bFinal Action:\s*(\d{1,2}/\d{1,2}/\d{4})\b", re.I)
AMOUNT_PHRASE = re.compile(
    r"\b(?:estimated\s+amount\s+of|amount\s+not\s+to\s+exceed|not\s+to\s+exceed|"
    r"in\s+the\s+amount\s+of|amount\s+of)\s+\$([0-9][0-9,]*(?:\.[0-9]{2})?)",
    re.I,
)


class AdapterError(ValueError):
    pass


def _exact(value, keys, where):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise AdapterError(f"{where}: keys mismatch")


def _text(value, where, *, limit=4096):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise AdapterError(f"{where}: invalid string")
    if any(ord(ch) < 32 for ch in value):
        raise AdapterError(f"{where}: control character")
    return value


def _integer(value, where, lo=0, hi=10**15):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise AdapterError(f"{where}: integer required")
    return value


def _optional_int(value, where):
    return None if value is None else _integer(value, where, 1, 1200)


def _optional_token(value, where):
    return None if value is None else engine.s(value, where, True, 128)


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value, where):
    try:
        return datetime.strptime(engine.ts(value, where), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, engine.Error) as exc:
        raise AdapterError(f"{where}: invalid UTC timestamp") from exc


def _validate_public_query(parsed, value, where):
    if "#" in value or parsed.fragment:
        raise AdapterError(f"{where}: fragment forbidden in durable public source URI")
    if not parsed.query:
        if "?" in value:
            raise AdapterError(f"{where}: empty query delimiter forbidden")
        return
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise AdapterError(f"{where}: malformed public query") from exc
    allowed = PUBLIC_QUERY_KEYS.get(parsed.hostname.lower(), set())
    seen = set()
    if not pairs:
        raise AdapterError(f"{where}: empty public query forbidden")
    for key, query_value in pairs:
        folded = key.casefold()
        if folded in seen or folded not in allowed:
            raise AdapterError(f"{where}: non-public query key forbidden")
        pattern = PUBLIC_QUERY_VALUE[folded]
        if not pattern.fullmatch(query_value):
            raise AdapterError(f"{where}: non-public query value forbidden")
        seen.add(folded)


def _validate_uri(value, allowed_hosts, where="source.uri"):
    value = _text(value, where, limit=2048)
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AdapterError(f"{where}: valid public HTTPS port required") from exc
    host = parsed.hostname.lower() if parsed.hostname else None
    if (
        parsed.scheme != "https"
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or host not in allowed_hosts
        or port not in (None, 443)
    ):
        raise AdapterError(f"{where}: HTTPS code-owned buyer host required")
    if parsed.path not in PUBLIC_PATHS.get(host, set()):
        raise AdapterError(f"{where}: code-owned buyer path required")
    _validate_public_query(parsed, value, where)
    return value


def _fetch_https(uri, allowed_hosts):
    request = Request(uri, headers={"User-Agent": "TokenJunkieLabs-procurement-source-adapter/1"})
    try:
        with urlopen(request, timeout=20) as response:
            final_uri = response.geturl()
            _validate_uri(final_uri, allowed_hosts, "source.final_uri")
            content_type = (response.headers.get_content_type() or "").lower()
            body = response.read(MAX_FETCH_BYTES + 1)
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(f"source fetch failed: {type(exc).__name__}") from exc
    if not body or len(body) > MAX_FETCH_BYTES:
        raise AdapterError("source fetch returned invalid byte length")
    return body, final_uri, content_type


def _lineage(value):
    _exact(value, LINEAGE_KEYS, "lineage")
    relation = engine.s(value["relation"], "lineage.relation", True, 32)
    if relation not in RELATIONS:
        raise AdapterError("lineage.relation: unsupported relation")
    sequence = _integer(value["sequence"], "lineage.sequence", 0, 1_000_000)
    parent = value["parent_source_sha256"]
    if relation == "ORIGINAL":
        if sequence != 0 or parent is not None:
            raise AdapterError("ORIGINAL requires sequence=0 and null parent")
    else:
        if sequence < 1:
            raise AdapterError("non-original lineage requires positive sequence")
        try:
            parent = engine.sha(parent, "lineage.parent_source_sha256")
        except engine.Error as exc:
            raise AdapterError(str(exc)) from exc
    return {"relation": relation, "sequence": sequence, "parent_source_sha256": parent}


def _extraction(value, profile):
    _exact(value, EXTRACTION_KEYS, "extraction")
    mode = engine.s(value["mode"], "extraction.mode", True, 32)
    state = engine.s(value["state"], "extraction.state", True, 32)
    coverage = engine.s(value["coverage"], "extraction.coverage", True, 32)
    if mode not in MODES or state not in STATES or coverage not in COVERAGE:
        raise AdapterError("extraction: unsupported mode/state/coverage")
    if profile["parser"] == "LEGISTAR":
        if (mode, state, coverage) != ("LIVE_HTML", "EXACT", "COMPLETE_RECORD"):
            raise AdapterError("LEGISTAR requires LIVE_HTML/EXACT/COMPLETE_RECORD")
        return mode, state, coverage, None
    if mode == "OCR":
        return mode, state, coverage, "OCR-derived price rows cannot promote evidence"
    if state == "AMBIGUOUS":
        return mode, state, coverage, "ambiguous tabular extraction cannot promote evidence"
    if coverage != "COMPLETE_TABLE":
        return mode, state, coverage, "partial/unknown table coverage cannot promote a comparable range"
    if (mode, state) != ("TABULAR_PDF_TEXT", "REVIEWED"):
        raise AdapterError("PDF requires TABULAR_PDF_TEXT/REVIEWED/COMPLETE_TABLE or explicit HOLD mode")
    return mode, state, coverage, None


class _VisibleText(HTMLParser):
    BLOCK = {"br", "div", "p", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        lines = [re.sub(r"\s+", " ", x).strip() for x in unescape("".join(self.parts)).splitlines()]
        return "\n".join(x for x in lines if x)


def _title(visible):
    flat = re.sub(r"\s+", " ", visible)
    match = re.search(
        r"\bTitle:\s*(.+?)(?=\s+(?:Attachments:|History\b|Date\s|Lobbyist:|Body\b|Recommended Action\b))",
        flat, re.I,
    )
    if not match:
        raise AdapterError("LEGISTAR: Title field not found")
    return match.group(1).strip()


def _money_minor(value):
    if not re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]{2})?", value):
        raise AdapterError("LEGISTAR: invalid money")
    value = value.replace(",", "")
    dollars, cents = (value.split(".", 1) + ["00"])[:2]
    return _integer(int(dollars) * 100 + int(cents), "LEGISTAR.amount")


def _parse_legistar(body, source_id, price_kind):
    try:
        source = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError("LEGISTAR: non-UTF-8 response") from exc
    parser = _VisibleText()
    parser.feed(source)
    parser.close()
    visible = parser.text()
    file_match = FILE_NO.search(visible)
    action_match = FINAL_ACTION.search(visible)
    title = _title(visible)
    amount_match = AMOUNT_PHRASE.search(title)
    if not file_match or not action_match or not amount_match:
        raise AdapterError("LEGISTAR: required award fields not found")
    prefix = title[:amount_match.start()]
    parts = re.split(r"\bto\s+", prefix, flags=re.I)
    if len(parts) < 2:
        raise AdapterError("LEGISTAR: awarded vendor not found")
    vendor = parts[-1].split(",", 1)[0].strip()
    if not vendor or len(vendor) > 160:
        raise AdapterError("LEGISTAR: awarded vendor parse ambiguous")
    try:
        event_date = datetime.strptime(action_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise AdapterError("LEGISTAR: invalid final action date") from exc
    file_no = engine.s(file_match.group(1), "LEGISTAR.file_no", True, 128)
    row = {
        "observation_id": f"legistar:{file_no}:award",
        "claim_key": f"legistar:{file_no}:award",
        "opportunity_id": file_no,
        "vendor": vendor,
        "price_kind": price_kind,
        "amount_minor": _money_minor(amount_match.group(1)),
        "currency": "USD",
        "basis": "CONTRACT_TOTAL",
        "unit": None,
        "term_months": None,
        "event_date": event_date,
        "source_ids": [source_id],
    }
    return [row], f"Legistar file {file_no} award record"


def _reviewed_row(value, index, source_id, price_kind):
    where = f"records[{index}]"
    _exact(value, RECORD_KEYS, where)
    basis = engine.s(value["basis"], where + ".basis", True, 32)
    if basis not in engine.BASIS:
        raise AdapterError(where + ": unsupported basis")
    currency = _text(value["currency"], where + ".currency", limit=3)
    if not engine.CUR.fullmatch(currency):
        raise AdapterError(where + ": invalid currency")
    unit = _optional_token(value["unit"], where + ".unit")
    if basis in {"HOURLY_RATE", "UNIT_RATE"} and unit is None:
        raise AdapterError(where + ": rate basis requires unit")
    if basis in {"LUMP_SUM", "CONTRACT_TOTAL"} and unit is not None:
        raise AdapterError(where + ": lump/total basis forbids unit")
    event_date = _text(value["event_date"], where + ".event_date", limit=10)
    try:
        datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError as exc:
        raise AdapterError(where + ": bad event_date") from exc
    disposition = engine.s(value["disposition"], where + ".disposition", True, 32)
    if disposition not in DISPOSITIONS:
        raise AdapterError(where + ": unsupported disposition")
    return {
        "observation_id": engine.s(value["record_id"], where + ".record_id", True, 128),
        "claim_key": engine.s(value["claim_key"], where + ".claim_key", True, 128),
        "opportunity_id": engine.s(value["opportunity_id"], where + ".opportunity_id", True, 128),
        "vendor": _text(value["vendor"], where + ".vendor", limit=256),
        "price_kind": price_kind,
        "amount_minor": _integer(value["amount_minor"], where + ".amount_minor"),
        "currency": currency,
        "basis": basis,
        "unit": unit,
        "term_months": _optional_int(value["term_months"], where + ".term_months"),
        "event_date": event_date,
        "source_ids": [source_id],
        "_disposition": disposition,
    }


def _decode(raw):
    try:
        value = engine.load(raw, "adapter request")
    except engine.Error as exc:
        raise AdapterError(str(exc)) from exc
    _exact(value, INPUT_KEYS, "input")
    if value["schema"] != ADAPTER_INPUT or value["truth_boundary"] != TRUTH_BOUNDARY:
        raise AdapterError("input: unsupported schema/truth boundary")
    source = value["source"]
    _exact(source, SOURCE_KEYS, "source")
    profile_name = engine.s(source["profile"], "source.profile", True, 64)
    profile = PROFILES.get(profile_name)
    if profile is None:
        raise AdapterError("source.profile: unsupported profile")
    uri = _validate_uri(source["uri"], profile["hosts"])
    lineage = _lineage(value["lineage"])
    extraction = _extraction(value["extraction"], profile)
    records = value["records"]
    if not isinstance(records, list) or len(records) > 10_000:
        raise AdapterError("records: invalid list")
    if profile["parser"] == "LEGISTAR" and records:
        raise AdapterError("LEGISTAR rows are code-derived; records must be empty")
    if profile["parser"] == "REVIEWED_ROWS" and not records:
        raise AdapterError("PDF profile requires reviewed/held rows")
    target = value["target"]
    _exact(target, TARGET_KEYS, "target")
    return {
        "value": value,
        "profile_name": profile_name,
        "profile": profile,
        "uri": uri,
        "lineage": lineage,
        "extraction": extraction,
        "records": records,
        "target": target,
        "dataset_id": engine.s(value["dataset_id"], "dataset_id", True, 128),
        "max_age": _integer(value["max_source_age_seconds"], "max_source_age_seconds", 1, 31_536_000),
    }


# Private compatibility hook used by hostile tests; this is not external authority.
_decode_request = _decode


def _compile_fetched(raw, decoded, body, final_uri, content_type, captured_at):
    profile = decoded["profile"]
    final_uri = _validate_uri(final_uri, profile["hosts"], "source.final_uri")
    content_type = _text(content_type, "source.content_type", limit=128).split(";", 1)[0].strip().lower()
    if content_type not in profile["content_types"]:
        raise AdapterError("source.content_type: unexpected media type")
    if not isinstance(body, (bytes, bytearray)) or not body or len(body) > MAX_FETCH_BYTES:
        raise AdapterError("source body: invalid bytes")
    body = bytes(body)
    if profile["parser"] == "LEGISTAR" and b"<html" not in body[:16384].lower():
        raise AdapterError("LEGISTAR: HTML marker missing")
    if profile["parser"] == "REVIEWED_ROWS" and not body.lstrip().startswith(b"%PDF-"):
        raise AdapterError("bid tabulation: PDF marker missing")
    captured_at = engine.ts(captured_at, "captured_at")
    source_sha = engine.digest(body)
    source_id = f"{decoded['profile_name'].lower()}:{source_sha[:24]}"
    relation = decoded["lineage"]["relation"]
    price_kind = "OPTION" if relation == "OPTION" else "RENEWAL" if relation == "RENEWAL" else profile["base_price_kind"]
    source_class = "AMENDMENT" if relation == "AMENDMENT" else profile["source_class"]
    mode, state, coverage, hold_reason = decoded["extraction"]
    held, excluded = [], []

    if profile["parser"] == "LEGISTAR":
        observations, title = _parse_legistar(body, source_id, price_kind)
        method = "CODE_DERIVED_FROM_LIVE_HTTPS_HTML"
    else:
        title = f"Buyer-hosted bid tabulation snapshot {source_sha[:12]}"
        method = "HUMAN_REVIEWED_ROWS_BOUND_TO_LIVE_HTTPS_DOCUMENT_SHA256"
        candidates, seen, unknown = [], set(), False
        for index, raw_row in enumerate(decoded["records"]):
            if not isinstance(raw_row, dict):
                raise AdapterError(f"records[{index}]: object required")
            row = _reviewed_row(raw_row, index, source_id, price_kind)
            rid = row["observation_id"]
            if rid in seen:
                raise AdapterError("records: duplicate record_id")
            seen.add(rid)
            disposition = row.pop("_disposition")
            if disposition == "UNKNOWN":
                unknown = True
                held.append(rid)
            elif disposition == "REJECTED_BY_SOURCE":
                excluded.append(rid)
            else:
                candidates.append(row)
        if unknown:
            hold_reason = "one or more bid rows have UNKNOWN source disposition"
        if hold_reason:
            held.extend(row["observation_id"] for row in candidates)
            observations = []
        else:
            observations = candidates

    normalized = {
        "schema": engine.INPUT,
        "dataset_id": decoded["dataset_id"],
        "generated_at": captured_at,
        "max_source_age_seconds": decoded["max_age"],
        "truth_boundary": TRUTH_BOUNDARY,
        "sources": [{
            "source_id": source_id,
            "uri": final_uri,
            "sha256": source_sha,
            "observed_at": captured_at,
            "authority": "BUYER_OFFICIAL",
            "source_class": source_class,
            "title": title,
        }],
        "observations": observations,
        "target": decoded["target"],
    }
    try:
        engine.normalize(normalized)
    except engine.Error as exc:
        raise AdapterError(f"normalized engine input invalid: {exc}") from exc
    normalized_bytes = engine.canon(normalized)
    receipt = {
        "schema": ADAPTER_RECEIPT,
        "truth_boundary": TRUTH_BOUNDARY,
        "status": "HOLD_AMBIGUOUS_EXTRACTION" if hold_reason else "ADAPTER_READY",
        "profile": decoded["profile_name"],
        "request_sha256": engine.digest(bytes(raw)),
        "normalized_sha256": engine.digest(normalized_bytes),
        "source_sha256": source_sha,
        "source_uri": final_uri,
        "source_content_type": content_type,
        "source_authentication": "LIVE_HTTPS_FETCH_CODE_OWNED_BUYER_HOST_ALLOWLIST",
        "captured_at": captured_at,
        "lineage": decoded["lineage"],
        "extraction": {"mode": mode, "state": state, "coverage": coverage, "method": method},
        "observation_count": len(observations),
        "held_record_ids": sorted(set(held)),
        "excluded_record_ids": sorted(excluded),
        "hold_reason": hold_reason,
        "authority": engine.authority(),
    }
    return normalized_bytes, engine.canon(receipt)


def compile_adapter(raw):
    decoded = _decode(raw)
    body, final_uri, content_type = _fetch_https(decoded["uri"], decoded["profile"]["hosts"])
    return _compile_fetched(raw, decoded, body, final_uri, content_type, _now_utc())


def verify_adapter(raw, normalized_bytes, receipt_bytes):
    decoded = _decode(raw)
    try:
        receipt = engine.load(receipt_bytes, "adapter receipt")
    except engine.Error as exc:
        raise AdapterError(str(exc)) from exc
    if receipt.get("schema") != ADAPTER_RECEIPT:
        raise AdapterError("receipt: unsupported schema")
    captured_at = receipt.get("captured_at")
    if _parse_utc(captured_at, "receipt.captured_at") > datetime.now(timezone.utc):
        raise AdapterError("receipt.captured_at: future timestamp")
    body, final_uri, content_type = _fetch_https(decoded["uri"], decoded["profile"]["hosts"])
    expected_normalized, expected_receipt = _compile_fetched(
        raw, decoded, body, final_uri, content_type, captured_at
    )
    if bytes(normalized_bytes) != expected_normalized:
        raise AdapterError("normalized bytes mismatch")
    if bytes(receipt_bytes) != expected_receipt:
        raise AdapterError("receipt bytes mismatch")
    return True


def _write_exclusive(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("--input", required=True)
    comp.add_argument("--out-dir", required=True)
    ver = sub.add_parser("verify")
    ver.add_argument("--input", required=True)
    ver.add_argument("--normalized", required=True)
    ver.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        raw = Path(args.input).read_bytes()
        if args.cmd == "compile":
            normalized, receipt = compile_adapter(raw)
            out = Path(args.out_dir)
            _write_exclusive(out / "normalized.json", normalized)
            _write_exclusive(out / "adapter-receipt.json", receipt)
            state = json.loads(receipt)
            print(json.dumps({
                "status": state["status"],
                "source_sha256": state["source_sha256"],
                "normalized_sha256": state["normalized_sha256"],
            }, sort_keys=True))
            return 0
        verify_adapter(raw, Path(args.normalized).read_bytes(), Path(args.receipt).read_bytes())
        print(json.dumps({"verified": True}, sort_keys=True))
        return 0
    except (AdapterError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())