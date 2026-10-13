"""Strict public-procurement award-source adapters.

Converts retained, explicitly structured procurement source payloads into the
input schema consumed by the landed procurement award price-intelligence engine.
This layer preserves caller-retained source authority; it does not authenticate
that a URI is buyer-controlled. Exact caller locators are output only as SHA-256
custody evidence; memo/engine-facing source URIs are canonical HTTPS origins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import engine as price_engine

REQUEST = "procurement-award-source-adapter/request/v1"
PACKET = "procurement-award-source-adapter/packet/v1"
RECEIPT = "procurement-award-source-adapter/receipt/v1"
TRUTH = "CURATED_SOURCE_EXTRACTION_NOT_PROVIDER_AUTHENTICATION"
AUTHORITY = {"BUYER_OFFICIAL", "SECONDARY_INDEX", "SELF_AUTHORED", "SYNTHETIC_FIXTURE"}
BASIS = {"HOURLY_RATE", "UNIT_RATE", "LUMP_SUM", "CONTRACT_TOTAL"}
ADAPTERS = {
    "AWARD_NOTICE_JSON_V1": {"AWARD_NOTICE", "BOARD_AWARD"},
    "BID_TABULATION_JSON_V1": {"BID_TABULATION"},
    "EXECUTED_CONTRACT_JSON_V1": {"EXECUTED_CONTRACT"},
    "AMENDMENT_OPTION_JSON_V1": {"AMENDMENT"},
}
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
PRICE_SOURCE_KEYS = ("source_id", "uri", "sha256", "observed_at", "authority", "source_class", "title")


class Error(ValueError):
    pass


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise Error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value):
    raise Error(f"non-integer JSON number forbidden: {value}")


def load(raw: bytes, label: str = "request"):
    if not isinstance(raw, (bytes, bytearray)):
        raise Error(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Error(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except Error:
        raise
    except Exception as exc:
        raise Error(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise Error(f"{label}: object required")
    return value


def canon(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value, expected, where):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise Error(f"{where}: keys mismatch")


def _string(value, where, *, token=False, limit=4096):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise Error(f"{where}: invalid string")
    if any(ord(ch) < 32 for ch in value):
        raise Error(f"{where}: control character")
    if token and not TOKEN.fullmatch(value):
        raise Error(f"{where}: invalid token")
    return value


def _integer(value, where, low=0, high=10**15):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Error(f"{where}: integer required")
    return value


def _optional_integer(value, where, low=1, high=1200):
    if value is None:
        return None
    return _integer(value, where, low, high)


def _sha(value, where):
    value = _string(value, where, limit=64)
    if not SHA.fullmatch(value):
        raise Error(f"{where}: sha256 required")
    return value


def _currency(value, where):
    value = _string(value, where, limit=3)
    if not CURRENCY.fullmatch(value):
        raise Error(f"{where}: ISO-like uppercase currency required")
    return value


def _split_uri(value, where, encoded=False):
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise Error(f"{where}: invalid https URI") from exc
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "?" in value
        or "#" in value
    ):
        prefix = "encoded " if encoded else ""
        raise Error(f"{where}: {prefix}credential/query/fragment component forbidden")
    if port not in (None, 443):
        prefix = "encoded " if encoded else ""
        raise Error(f"{where}: {prefix}default HTTPS port required")
    return parts


def _canonical_origin_and_locator_digest(value, where):
    """Validate the exact locator, then export only a canonical HTTPS origin.

    Arbitrary caller path bytes are deliberately not classified as public/secret.
    They remain bound by SHA-256 in adapter-only audit/receipt evidence while the
    price engine and its memo receive no path bytes at all.
    """
    value = _string(value, where, limit=2048)
    decoded = value
    seen = set()
    parts = _split_uri(decoded, where)
    while "%" in decoded and decoded not in seen:
        seen.add(decoded)
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
        parts = _split_uri(decoded, where, encoded=True)

    host = parts.hostname or ""
    try:
        if ":" in host:
            authority = f"[{host.lower()}]"
        else:
            authority = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise Error(f"{where}: invalid hostname") from exc
    if not authority:
        raise Error(f"{where}: invalid hostname")
    return f"https://{authority}", digest(value.encode("utf-8"))


def _stable_id(prefix, *parts):
    return f"{prefix}-{digest(canon(list(parts)))[:24]}"


def _authority_flags():
    return {key: False for key in (
        "source_provider_authenticated", "buyer_officialness_authenticated",
        "quote_authorized", "bid_authorized", "submission_authorized",
        "buyer_or_partner_contact_authorized", "signature_authorized",
        "price_commitment_authorized", "award_recognized", "invoice_authorized",
        "payment_authorized", "revenue_recognized",
    )}


def _target(value):
    _keys(value, ("target_id", "currency", "basis", "unit", "term_months", "allowed_price_kinds"), "target")
    return {
        "target_id": _string(value["target_id"], "target.target_id", token=True),
        "currency": _currency(value["currency"], "target.currency"),
        "basis": _string(value["basis"], "target.basis", token=True),
        "unit": None if value["unit"] is None else _string(value["unit"], "target.unit", token=True),
        "term_months": _optional_integer(value["term_months"], "target.term_months"),
        "allowed_price_kinds": value["allowed_price_kinds"],
    }


def _source(value, where, adapter):
    _keys(value, ("source_id", "uri", "sha256", "observed_at", "authority", "source_class", "title"), where)
    authority = _string(value["authority"], where + ".authority", token=True, limit=32)
    source_class = _string(value["source_class"], where + ".source_class", token=True, limit=32)
    if authority not in AUTHORITY:
        raise Error(where + ": unsupported authority")
    if source_class not in ADAPTERS[adapter]:
        raise Error(where + ": source_class incompatible with adapter")
    origin, locator_sha = _canonical_origin_and_locator_digest(value["uri"], where + ".uri")
    return {
        "source_id": _string(value["source_id"], where + ".source_id", token=True),
        "uri": origin,
        "locator_sha256": locator_sha,
        "sha256": _sha(value["sha256"], where + ".sha256"),
        "observed_at": _string(value["observed_at"], where + ".observed_at", limit=20),
        "authority": authority,
        "source_class": source_class,
        "title": _string(value["title"], where + ".title", limit=256),
    }


def _price_source(source):
    return {key: source[key] for key in PRICE_SOURCE_KEYS}


def _basis_fields(payload, where):
    basis = _string(payload["basis"], where + ".basis", token=True, limit=32)
    if basis not in BASIS:
        raise Error(where + ": unsupported basis")
    unit = None if payload["unit"] is None else _string(payload["unit"], where + ".unit", token=True)
    term = _optional_integer(payload["term_months"], where + ".term_months")
    holds = []
    if term is None:
        holds.append("MISSING_TERM")
    if basis in {"HOURLY_RATE", "UNIT_RATE"} and unit is None:
        holds.append("MISSING_RATE_UNIT")
    if basis in {"LUMP_SUM", "CONTRACT_TOTAL"} and unit is not None:
        holds.append("UNEXPECTED_LUMP_UNIT")
    return basis, unit, term, holds


def _money(value, where):
    if value is None:
        return None
    return _integer(value, where, 0, 10**15)


def _hold(holds, source_id, code, detail, row_id=None):
    holds.append({"source_id": source_id, "row_id": row_id, "code": code, "detail": detail})


def _emit_observation(*, source, opportunity_id, vendor, amount, currency, basis, unit, term,
                      event_date, price_kind, identity_kind, identity_parts):
    return {
        "observation_id": _stable_id("obs", source["source_id"], price_kind, opportunity_id, vendor, *identity_parts),
        "claim_key": _stable_id(identity_kind, opportunity_id, vendor),
        "opportunity_id": opportunity_id,
        "vendor": vendor,
        "price_kind": price_kind,
        "amount_minor": amount,
        "currency": currency,
        "basis": basis,
        "unit": unit,
        "term_months": term,
        "event_date": event_date,
        "source_ids": [source["source_id"]],
    }


def _award_notice(source, payload, holds):
    where = source["source_id"] + ".payload"
    _keys(payload, ("opportunity_id", "award_id", "vendor", "award_amount_minor", "currency",
                    "basis", "unit", "term_months", "award_date"), where)
    opp = _string(payload["opportunity_id"], where + ".opportunity_id", token=True)
    award_id = _string(payload["award_id"], where + ".award_id", token=True)
    vendor = _string(payload["vendor"], where + ".vendor", limit=256)
    currency = _currency(payload["currency"], where + ".currency")
    basis, unit, term, basis_holds = _basis_fields(payload, where)
    amount = _money(payload["award_amount_minor"], where + ".award_amount_minor")
    if source["authority"] != "BUYER_OFFICIAL":
        _hold(holds, source["source_id"], "SOURCE_NOT_BUYER_OFFICIAL", "authority retained; source cannot anchor price evidence")
    if amount is None:
        _hold(holds, source["source_id"], "AMBIGUOUS_AMOUNT", "award amount is not explicit")
    for code in basis_holds:
        _hold(holds, source["source_id"], code, "basis/unit/term is incomplete or contradictory")
    if amount is None or basis_holds:
        return []
    return [_emit_observation(
        source=source,
        opportunity_id=opp,
        vendor=vendor,
        amount=amount,
        currency=currency,
        basis=basis,
        unit=unit,
        term=term,
        event_date=_string(payload["award_date"], where + ".award_date", limit=10),
        price_kind="AWARD",
        identity_kind="award",
        identity_parts=(award_id,),
    )]


def _bid_tabulation(source, payload, holds):
    where = source["source_id"] + ".payload"
    _keys(payload, ("opportunity_id", "tabulation_id", "currency", "basis", "unit", "term_months",
                    "bid_date", "rows"), where)
    opp = _string(payload["opportunity_id"], where + ".opportunity_id", token=True)
    tab = _string(payload["tabulation_id"], where + ".tabulation_id", token=True)
    currency = _currency(payload["currency"], where + ".currency")
    basis, unit, term, basis_holds = _basis_fields(payload, where)
    if not isinstance(payload["rows"], list) or not payload["rows"]:
        raise Error(where + ".rows: non-empty list required")
    if source["authority"] != "BUYER_OFFICIAL":
        _hold(holds, source["source_id"], "SOURCE_NOT_BUYER_OFFICIAL", "authority retained; source cannot anchor price evidence")
    out, seen = [], set()
    for index, row in enumerate(payload["rows"]):
        rw = f"{where}.rows[{index}]"
        _keys(row, ("row_id", "vendor", "bid_amount_minor", "responsive"), rw)
        row_id = _string(row["row_id"], rw + ".row_id", token=True)
        if row_id in seen:
            raise Error(rw + ": duplicate row_id")
        seen.add(row_id)
        vendor = _string(row["vendor"], rw + ".vendor", limit=256)
        if not isinstance(row["responsive"], bool):
            raise Error(rw + ".responsive: bool required")
        amount = _money(row["bid_amount_minor"], rw + ".bid_amount_minor")
        if not row["responsive"]:
            _hold(holds, source["source_id"], "NONRESPONSIVE_BID_EXCLUDED", "row explicitly marked nonresponsive", row_id)
            continue
        if amount is None:
            _hold(holds, source["source_id"], "AMBIGUOUS_AMOUNT", "bid amount is not explicit", row_id)
            continue
        if basis_holds:
            for code in basis_holds:
                _hold(holds, source["source_id"], code, "basis/unit/term is incomplete or contradictory", row_id)
            continue
        out.append(_emit_observation(
            source=source,
            opportunity_id=opp,
            vendor=vendor,
            amount=amount,
            currency=currency,
            basis=basis,
            unit=unit,
            term=term,
            event_date=_string(payload["bid_date"], where + ".bid_date", limit=10),
            price_kind="BID",
            identity_kind="bid",
            identity_parts=(tab, row_id),
        ))
    return out


def _executed_contract(source, payload, holds):
    where = source["source_id"] + ".payload"
    _keys(payload, ("opportunity_id", "contract_id", "vendor", "currency", "base_amount_minor",
                    "basis", "unit", "term_months", "effective_date", "option_amount_minor",
                    "option_term_months"), where)
    opp = _string(payload["opportunity_id"], where + ".opportunity_id", token=True)
    contract_id = _string(payload["contract_id"], where + ".contract_id", token=True)
    vendor = _string(payload["vendor"], where + ".vendor", limit=256)
    currency = _currency(payload["currency"], where + ".currency")
    basis, unit, term, basis_holds = _basis_fields(payload, where)
    base = _money(payload["base_amount_minor"], where + ".base_amount_minor")
    option = _money(payload["option_amount_minor"], where + ".option_amount_minor")
    option_term = _optional_integer(payload["option_term_months"], where + ".option_term_months")
    if source["authority"] != "BUYER_OFFICIAL":
        _hold(holds, source["source_id"], "SOURCE_NOT_BUYER_OFFICIAL", "authority retained; source cannot anchor price evidence")
    out = []
    if base is None:
        _hold(holds, source["source_id"], "AMBIGUOUS_AMOUNT", "executed base contract amount is not explicit")
    elif basis_holds:
        for code in basis_holds:
            _hold(holds, source["source_id"], code, "basis/unit/term is incomplete or contradictory")
    else:
        out.append(_emit_observation(
            source=source,
            opportunity_id=opp,
            vendor=vendor,
            amount=base,
            currency=currency,
            basis=basis,
            unit=unit,
            term=term,
            event_date=_string(payload["effective_date"], where + ".effective_date", limit=10),
            price_kind="AWARD",
            identity_kind="award",
            identity_parts=(contract_id, "base"),
        ))
    if option is not None:
        if option_term is None:
            _hold(holds, source["source_id"], "OPTION_TERM_MISSING", "option amount retained but option term is not explicit")
        else:
            out.append(_emit_observation(
                source=source,
                opportunity_id=opp,
                vendor=vendor,
                amount=option,
                currency=currency,
                basis="CONTRACT_TOTAL",
                unit=None,
                term=option_term,
                event_date=_string(payload["effective_date"], where + ".effective_date", limit=10),
                price_kind="OPTION",
                identity_kind="option",
                identity_parts=(contract_id, "option"),
            ))
            _hold(holds, source["source_id"], "OPTION_NON_ANCHOR", "option retained separately and never folded into base award")
    return out


def _amendment_option(source, payload, holds):
    where = source["source_id"] + ".payload"
    _keys(payload, ("opportunity_id", "contract_id", "amendment_id", "vendor", "currency",
                    "amount_minor", "term_months", "effective_date", "change_type"), where)
    opp = _string(payload["opportunity_id"], where + ".opportunity_id", token=True)
    contract_id = _string(payload["contract_id"], where + ".contract_id", token=True)
    amendment_id = _string(payload["amendment_id"], where + ".amendment_id", token=True)
    vendor = _string(payload["vendor"], where + ".vendor", limit=256)
    currency = _currency(payload["currency"], where + ".currency")
    change_type = _string(payload["change_type"], where + ".change_type", token=True, limit=16)
    if change_type not in {"OPTION", "AMENDMENT"}:
        raise Error(where + ".change_type: OPTION or AMENDMENT required")
    amount = _money(payload["amount_minor"], where + ".amount_minor")
    term = _optional_integer(payload["term_months"], where + ".term_months")
    if amount is None:
        _hold(holds, source["source_id"], "AMBIGUOUS_AMOUNT", "change amount is not explicit")
        return []
    if term is None:
        _hold(holds, source["source_id"], "MISSING_TERM", "change term is not explicit")
        return []
    if source["authority"] != "BUYER_OFFICIAL":
        _hold(holds, source["source_id"], "SOURCE_NOT_BUYER_OFFICIAL", "authority retained; source cannot anchor price evidence")
    _hold(holds, source["source_id"], "CHANGE_RECORD_NON_ANCHOR", "amendment/option is retained as OPTION, never promoted to AWARD")
    return [_emit_observation(
        source=source,
        opportunity_id=opp,
        vendor=vendor,
        amount=amount,
        currency=currency,
        basis="CONTRACT_TOTAL",
        unit=None,
        term=term,
        event_date=_string(payload["effective_date"], where + ".effective_date", limit=10),
        price_kind="OPTION",
        identity_kind="option",
        identity_parts=(contract_id, amendment_id, change_type),
    )]


_HANDLER = {
    "AWARD_NOTICE_JSON_V1": _award_notice,
    "BID_TABULATION_JSON_V1": _bid_tabulation,
    "EXECUTED_CONTRACT_JSON_V1": _executed_contract,
    "AMENDMENT_OPTION_JSON_V1": _amendment_option,
}


def compile(raw: bytes):
    request = load(raw)
    _keys(request, ("schema", "dataset_id", "generated_at", "max_source_age_seconds", "truth_boundary",
                    "documents", "target"), "request")
    if request["schema"] != REQUEST or request["truth_boundary"] != TRUTH:
        raise Error("request: unsupported schema/truth_boundary")
    dataset_id = _string(request["dataset_id"], "dataset_id", token=True)
    generated_at = _string(request["generated_at"], "generated_at", limit=20)
    max_age = _integer(request["max_source_age_seconds"], "max_source_age_seconds", 1, 31536000)
    if not isinstance(request["documents"], list) or not request["documents"]:
        raise Error("documents: non-empty list required")

    sources, observations, holds, audits = [], [], [], []
    seen_sources, seen_raw_sources, seen_payloads = set(), set(), set()
    for index, document in enumerate(request["documents"]):
        where = f"documents[{index}]"
        _keys(document, ("adapter", "source", "payload_sha256", "payload"), where)
        adapter = _string(document["adapter"], where + ".adapter", token=True, limit=64)
        if adapter not in ADAPTERS:
            raise Error(where + ": unsupported adapter")
        source = _source(document["source"], where + ".source", adapter)
        if source["source_id"] in seen_sources:
            raise Error(where + ": duplicate source_id")
        seen_sources.add(source["source_id"])
        if source["sha256"] in seen_raw_sources:
            raise Error(where + ": duplicate retained raw source")
        seen_raw_sources.add(source["sha256"])

        payload = document["payload"]
        if not isinstance(payload, dict):
            raise Error(where + ".payload: object required")
        payload_sha = _sha(document["payload_sha256"], where + ".payload_sha256")
        if payload_sha != digest(canon(payload)):
            raise Error(where + ": payload_sha256 mismatch")
        if payload_sha in seen_payloads:
            raise Error(where + ": duplicate structured source payload")
        seen_payloads.add(payload_sha)

        sources.append(_price_source(source))
        emitted = _HANDLER[adapter](source, payload, holds)
        observations.extend(emitted)
        audits.append({
            "source_id": source["source_id"],
            "adapter": adapter,
            "raw_source_sha256": source["sha256"],
            "source_locator_sha256": source["locator_sha256"],
            "payload_sha256": payload_sha,
            "authority": source["authority"],
            "source_class": source["source_class"],
            "emitted_observation_ids": sorted(row["observation_id"] for row in emitted),
        })

    if len({row["observation_id"] for row in observations}) != len(observations):
        raise Error("adapter produced duplicate observation_id")

    price_input = {
        "schema": price_engine.INPUT,
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "max_source_age_seconds": max_age,
        "truth_boundary": price_engine.BOUNDARY,
        "sources": sorted(sources, key=lambda row: row["source_id"]),
        "observations": sorted(observations, key=lambda row: row["observation_id"]),
        "target": _target(request["target"]),
    }
    price_bytes = canon(price_input)
    try:
        price_packet_bytes, _, _ = price_engine.compile(price_bytes)
    except price_engine.Error as exc:
        raise Error(f"price engine rejected adapter output: {exc}") from exc
    price_status = json.loads(price_packet_bytes.decode("utf-8"))["status"]

    audits = sorted(audits, key=lambda row: row["source_id"])
    packet = {
        "schema": PACKET,
        "truth_boundary": TRUTH,
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "source_authentication": "CALLER_RETAINED_SOURCE_METADATA_NOT_PROVIDER_AUTHENTICATED",
        "price_engine_status": price_status,
        "source_count": len(sources),
        "emitted_observation_count": len(observations),
        "holds": sorted(holds, key=lambda row: (row["source_id"], row["row_id"] or "", row["code"], row["detail"])),
        "source_audit": audits,
        "authority": _authority_flags(),
    }
    packet_bytes = canon(packet)
    receipt = {
        "schema": RECEIPT,
        "truth_boundary": TRUTH,
        "request_sha256": digest(raw),
        "price_input_sha256": digest(price_bytes),
        "packet_sha256": digest(packet_bytes),
        "source_locator_sha256s": [
            {"source_id": row["source_id"], "sha256": row["source_locator_sha256"]}
            for row in audits
        ],
        "authority": _authority_flags(),
    }
    return price_bytes, packet_bytes, canon(receipt)


def verify(raw: bytes, price_input: bytes, packet: bytes, receipt: bytes):
    expected_price, expected_packet, expected_receipt = compile(raw)
    if price_input != expected_price:
        raise Error("price input mismatch")
    if packet != expected_packet:
        raise Error("packet mismatch")
    if receipt != expected_receipt:
        raise Error("receipt mismatch")
    return {
        "verified": True,
        "price_input_sha256": digest(price_input),
        "packet_sha256": digest(packet),
        "receipt_sha256": digest(receipt),
    }


def _publish_generation(out: Path, files):
    """Create one output directory generation without overwriting an older one."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    created = []
    try:
        for name, data in files:
            path = out / name
            with path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            created.append(path)
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(str(out), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            out.rmdir()
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Strict procurement award-source adapters")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--input", required=True)
    c.add_argument("--out-dir", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True)
    v.add_argument("--price-input", required=True)
    v.add_argument("--packet", required=True)
    v.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            price_input, packet, receipt = compile(Path(args.input).read_bytes())
            out = Path(args.out_dir)
            _publish_generation(out, (
                ("price_input.json", price_input),
                ("adapter_packet.json", packet),
                ("adapter_receipt.json", receipt),
            ))
            print(json.dumps({"status": json.loads(packet)["price_engine_status"], "out_dir": str(out)}, sort_keys=True))
        else:
            result = verify(
                Path(args.input).read_bytes(),
                Path(args.price_input).read_bytes(),
                Path(args.packet).read_bytes(),
                Path(args.receipt).read_bytes(),
            )
            print(json.dumps(result, sort_keys=True))
        return 0
    except (Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())