#!/usr/bin/env python3
"""Buyer-neutral Abbotsford RFP 1220-2026-4235 evidence carrier."""
from __future__ import annotations
import hashlib, json, math, re, argparse, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
SCHEMA = "tjlabs.abbotsford-1220-2026-4235/v1"
DEMO_SCHEMA = "tjlabs.abbotsford-waste-demo-case/v1"
RESULT_SCHEMA = "tjlabs.abbotsford-waste-demo-result/v1"
QUAL_SCHEMA = "tjlabs.abbotsford-1220-qualification/v1"
QUAL_RESULT_SCHEMA = "tjlabs.abbotsford-1220-qualification-result/v1"
BID_NUMBER = "RFP 1220-2026-4235"
BUYER = "City of Abbotsford"
TITLE = "City of Abbotsford - Digital Waste Collection Calendar & Resident Engagement Platform"
DETAIL_URL = "https://abbotsford.bidsandtenders.ca/Module/Tenders/en/Tender/Detail/254ac4d7-b135-44c6-99d9-44203c732790"
CLOSE_UTC = "2026-10-07T21:00:00Z"
QUESTION_UTC = "2026-09-24T21:00:00Z"
OPENED_DATE = "2026-09-11"
SOURCE_CAPTURED_UTC = "2026-09-16T22:52:49Z"
OPERATION = "ABBOTSFORD-DIGITAL-WASTE-PLATFORM-SOLZ-20260916"
CARRIER_ROOT = "revenue/opportunities/abbotsford_1220_2026_4235"
AUTHORITY_FALSE = {"buyer_contact_authorized": False, "question_authorized": False, "plan_taker_registration_authorized": False, "proposal_submission_authorized": False, "signature_authorized": False, "certification_authorized": False, "price_acceptance_authorized": False, "award_authorized": False, "payment_authorized": False, "revenue_recognized": False}
UNKNOWN_PACKET_GAPS = ("insurance_legal_entity_reference_gates", "privacy_data_residency_hosting_security_accessibility_retention_integration", "required_mobile_web_channels_and_notification_mechanics", "sla_support_migration_service_term", "exact_evaluation_weights", "pricing_form", "contract_language", "mandatory_certifications_staffing_canadian_footprint", "exact_submission_attachments_plan_taker_conditions")
DEMO_CAPABILITIES = ("address_lookup", "collection_schedule_calendar", "holiday_exception_override", "reminder_preference_simulation", "multilingual_accessibility_metadata", "admin_content_change_receipts", "deterministic_api_import_export", "privacy_minimized_resident_identifiers", "observability_receipts")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
STREAMS = ("garbage", "recycling", "organics", "yard")
class ContractError(ValueError):
    pass
def _pairs_no_dupes(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate key {key!r}")
        out[key] = value
    return out
def load_strict_json(text):
    return json.loads(text, object_pairs_hook=_pairs_no_dupes)
def reject_nonfinite(value, path="$"):
    if type(value) is float and (math.isnan(value) or math.isinf(value)):
        raise ContractError(f"nonfinite number at {path}")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError(f"non-string key at {path}")
            reject_nonfinite(item, f"{path}.{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            reject_nonfinite(item, f"{path}[{index}]")
def canonical_bytes(value):
    reject_nonfinite(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
def parse_utc(stamp, field):
    if type(stamp) is not str or not ISO_RE.match(stamp):
        raise ContractError(f"{field} must be YYYY-MM-DDTHH:MM:SSZ")
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
def require_id(value, field):
    if type(value) is not str or not ID_RE.match(value):
        raise ContractError(f"{field} is not a stable id")
    return value
def require_sha(value, field):
    if type(value) is not str or not SHA_RE.match(value):
        raise ContractError(f"{field} is not sha256 hex")
    return value
def public_facts():
    facts = {"bid_number": BID_NUMBER, "buyer": BUYER, "title": TITLE, "status": "Open", "classification": "Services / Request for Proposal", "category": "Information Technology / Services", "closing_utc": CLOSE_UTC, "question_deadline_utc": QUESTION_UTC, "opened_date": OPENED_DATE, "submission": "Online submissions only", "language": "English unless specified in the bid document", "detail_url": DETAIL_URL, "addenda_public_state": "No Addenda Available", "appendix_b_recovered": False, "authorized_packet_present": False, "canadabuys_independent_listing": True, "operation": OPERATION, "source_captured_utc": SOURCE_CAPTURED_UTC, "pursuit_state": "OPEN_PUBLIC_OPPORTUNITY"}
    facts["facts_digest"] = digest(facts)
    return facts
def qualify(packet=None, now_utc=None):
    facts = public_facts()
    now = parse_utc(now_utc or SOURCE_CAPTURED_UTC, "now_utc")
    close = parse_utc(CLOSE_UTC, "closing_utc")
    question = parse_utc(QUESTION_UTC, "question_deadline_utc")
    captured = parse_utc(SOURCE_CAPTURED_UTC, "source_captured_utc")
    if now < captured:
        raise ContractError("now_utc precedes source capture")
    packet_present = False
    packet_digest = None
    if packet is not None:
        if type(packet) is not dict:
            raise ContractError("packet must be an object")
        reject_nonfinite(packet)
        if packet.get("schema") != QUAL_SCHEMA or packet.get("bid_number") != BID_NUMBER:
            raise ContractError("packet identity mismatch")
        evidence = packet.get("authorized_package_evidence")
        if evidence is True:
            packet_present = False
        elif type(evidence) is dict:
            require_sha(evidence.get("sha256"), "authorized_package_evidence.sha256")
            if type(evidence.get("bytes_present")) is not bool:
                raise ContractError("authorized_package_evidence.bytes_present must be bool")
            packet_present = bool(evidence["bytes_present"])
            packet_digest = evidence["sha256"]
        elif evidence not in (False, None):
            raise ContractError("authorized_package_evidence type mismatch")
    missing = list(UNKNOWN_PACKET_GAPS)
    disposition = "PARTNER_REVIEW_REQUIRED" if packet_present else "HOLD_PACKET_REQUIRED"
    if packet_present:
        missing = []
    result = {"schema": QUAL_RESULT_SCHEMA, "bid_number": BID_NUMBER, "qualification": disposition, "pursuit_state": "OPEN_PUBLIC_OPPORTUNITY / " + disposition, "public_facts_digest": facts["facts_digest"], "authorized_packet_present": packet_present, "authorized_packet_digest": packet_digest, "missing_authorized_facts": missing, "question_window_open": now < question, "submission_window_open": now < close, "demo_capabilities": list(DEMO_CAPABILITIES), "demo_satisfies_unknown_mandatory": False, "source_freshness": {"captured_utc": SOURCE_CAPTURED_UTC, "evaluated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "stale_if_after_close": now >= close}, **AUTHORITY_FALSE}
    result["receipt_sha256"] = digest(result)
    return result
def _hash_resident(token):
    return hashlib.sha256(("abbotsford-demo|" + token).encode("utf-8")).hexdigest()
def evaluate_demo_case(raw):
    if type(raw) is not dict:
        raise ContractError("demo case must be an object")
    reject_nonfinite(raw)
    expected = {"schema","case_id","address_query","zone_id","as_of_utc","holiday_dates","exception_streams","reminder_channels","locale","accessibility","admin_change","export_format"}
    if set(raw) != expected or raw["schema"] != DEMO_SCHEMA:
        raise ContractError("demo case shape mismatch")
    case_id = require_id(raw["case_id"], "case_id")
    if type(raw["address_query"]) is not str or not raw["address_query"].strip():
        raise ContractError("address_query required")
    zone_id = require_id(raw["zone_id"], "zone_id")
    as_of = parse_utc(raw["as_of_utc"], "as_of_utc")
    if type(raw["holiday_dates"]) is not list or any(type(d) is not str for d in raw["holiday_dates"]):
        raise ContractError("holiday_dates must be string list")
    if type(raw["exception_streams"]) is not list:
        raise ContractError("exception_streams must be a list")
    for stream in raw["exception_streams"]:
        if stream not in STREAMS:
            raise ContractError(f"unknown stream {stream!r}")
    if type(raw["reminder_channels"]) is not list or any(type(c) is not str for c in raw["reminder_channels"]):
        raise ContractError("reminder_channels must be string list")
    if type(raw["locale"]) is not str or len(raw["locale"]) < 2:
        raise ContractError("locale required")
    acc = raw["accessibility"]
    if type(acc) is not dict or set(acc) != {"lang", "text_alternates", "contrast"}:
        raise ContractError("accessibility shape mismatch")
    if type(acc["lang"]) is not str or type(acc["text_alternates"]) is not bool or type(acc["contrast"]) is not str:
        raise ContractError("accessibility types mismatch")
    change = raw["admin_change"]
    if type(change) is not dict or set(change) != {"actor_token", "field", "from_value", "to_value"}:
        raise ContractError("admin_change shape mismatch")
    for key in ("actor_token", "field", "from_value", "to_value"):
        if type(change[key]) is not str:
            raise ContractError(f"admin_change.{key} must be string")
    if raw["export_format"] not in ("json", "ics"):
        raise ContractError("export_format must be json or ics")
    weekday = as_of.strftime("%A")
    holiday = as_of.strftime("%Y-%m-%d") in raw["holiday_dates"]
    schedule = [{"stream": stream, "weekday": weekday, "status": "SKIPPED_EXCEPTION" if (holiday or stream in raw["exception_streams"]) else "SCHEDULED", "capability": "DEMO_CAPABILITY"} for stream in STREAMS]
    result = {"schema": RESULT_SCHEMA, "case_id": case_id, "label": "DEMO_CAPABILITY", "not_a_buyer_requirement": True, "resident_id": _hash_resident(raw["address_query"].strip().lower()), "address_lookup": {"query": raw["address_query"].strip(), "zone_id": zone_id, "matched": True, "capability": "DEMO_CAPABILITY"}, "schedule": schedule, "holiday_applied": holiday, "reminders": [{"channel": channel, "enabled": True, "capability": "DEMO_CAPABILITY"} for channel in raw["reminder_channels"]], "locale": raw["locale"], "accessibility": acc, "admin_receipt": {"actor_id": _hash_resident(change["actor_token"]), "field": change["field"], "from_value": change["from_value"], "to_value": change["to_value"], "capability": "DEMO_CAPABILITY"}, "export": {"zone_id": zone_id, "as_of_utc": raw["as_of_utc"], "schedule": schedule, "format": raw["export_format"], "capability": "DEMO_CAPABILITY"}, "observability": {"events": ["lookup", "schedule", "reminder_sim", "admin_change", "export"], "capability": "DEMO_CAPABILITY"}, **AUTHORITY_FALSE}
    result["receipt_sha256"] = digest(result)
    return result
def verify_demo(raw, claimed):
    recomputed = evaluate_demo_case(raw)
    if type(claimed) is not dict:
        raise ContractError("claimed result must be an object")
    reject_nonfinite(claimed)
    if claimed.get("receipt_sha256") != recomputed["receipt_sha256"] or digest(claimed) != digest(recomputed):
        raise ContractError("claimed result does not recompile")
    return recomputed
def compile_bundle(cases, now_utc=None):
    if type(cases) is not list:
        raise ContractError("cases must be a list")
    seen = set()
    results = []
    for case in cases:
        evaluated = evaluate_demo_case(case)
        if evaluated["case_id"] in seen:
            raise ContractError(f"duplicate case_id {evaluated['case_id']}")
        seen.add(evaluated["case_id"])
        results.append(evaluated)
    bundle = {"schema": SCHEMA, "carrier_root": CARRIER_ROOT, "public_facts": public_facts(), "qualification": qualify(now_utc=now_utc), "demo_results": results, "demo_count": len(results), **AUTHORITY_FALSE}
    bundle["bundle_sha256"] = digest(bundle)
    return bundle
def load_fixture_cases(path=None):
    target = path or (Path(__file__).resolve().parent / "fixtures" / "demo_cases.json")
    raw = load_strict_json(target.read_text(encoding="utf-8"))
    if type(raw) is not dict or set(raw) != {"schema", "cases"} or raw["schema"] != "tjlabs.abbotsford-waste-demo-fixture/v1" or type(raw["cases"]) is not list:
        raise ContractError("fixture envelope mismatch")
    return raw["cases"]
def main(argv=None):
    parser = argparse.ArgumentParser(description="Abbotsford 1220-2026-4235 carrier")
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--demo-fixture", action="store_true")
    parser.add_argument("--now-utc", default=SOURCE_CAPTURED_UTC)
    args = parser.parse_args(argv)
    if args.qualify:
        sys.stdout.buffer.write(canonical_bytes(qualify(now_utc=args.now_utc))); return 0
    if args.demo_fixture:
        sys.stdout.buffer.write(canonical_bytes(compile_bundle(load_fixture_cases(), now_utc=args.now_utc))); return 0
    parser.print_help(); return 2
if __name__ == "__main__":
    raise SystemExit(main())
