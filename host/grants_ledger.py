#!/usr/bin/env python3
"""Validate and read the fail-closed public Commons grants ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("revenue/ip/grants_ledger.json")
SCHEMA_PATH = Path("revenue/ip/grants_ledger.schema.json")
BUILD_PATHS = (
    "revenue/ip/grants_ledger.schema.json",
    "revenue/ip/grants_ledger.json",
    "host/grants_ledger.py",
    "test_grants_ledger.py",
)
BASE_SHA = "e6ac397aa6f038bf83a89668c9118d63a3770d9f"
CHECKED_AT = "2026-08-26T20:50:00Z"
EXPECTED_LEDGER_SHA256 = "3ffed93834cfb09423f3936bbd57c77020cfaef6147ec32f56537bb8869a7201"
EXPECTED_SCHEMA_SHA256 = "c8590b90c3d4a68c0bd6eb1bf42f91304290de1be0f1337dd2666e107cd4b6ac"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIME_TEXT = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
ID_TEXT = re.compile(r"^[a-z0-9][a-z0-9-]{7,79}$")
DNS_HOST = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))+$"
)
PRIVATE_KEYS = {
    "application_draft",
    "bank_details",
    "collaboration_letter_files",
    "contact_email",
    "contact_phone",
    "entity_identifier",
    "payout_details",
    "research_portal_identity",
    "tax_identifier",
}
LEGAL_SCOPE_KEYS = {
    "applicant_eligibility_adjudicated",
    "submission_readiness_claimed",
    "award_claimed",
    "funding_success_claimed",
    "cash_received_claimed",
}
ROOT_KEYS = {
    "schema_version",
    "kind",
    "generated_at",
    "generated_from_main",
    "scope",
    "nonclaims",
    "legal_scope",
    "omitted_private_fields",
    "programs",
}
PROGRAM_KEYS = {
    "id",
    "funder",
    "program",
    "official_urls",
    "evidence_urls",
    "checked_at",
    "application_state",
    "application_state_basis",
    "opens_date",
    "deadline",
    "program_eligibility_text",
    "program_eligibility_evidence_state",
    "applicant_eligibility_state",
    "applicant_eligibility_public_evidence_url",
    "funding_text",
    "funding_evidence_state",
    "matching_state",
    "matching_basis",
    "ip_terms",
    "ip_evidence_state",
    "deliverables",
    "fit_note",
    "public_next_action",
    "owner",
    "private_blockers",
    "nonclaims",
    "submission_status",
    "award_status",
    "cash_received_usd",
}
EXPECTED_IDS = (
    "nsf-pesose-26-506",
    "nsf-sbir-sttr-26-510",
    "nlnet-restack-ois-2026",
)
EXPECTED_FACTS = {
    "nsf-pesose-26-506": {
        "official_urls": [
            "https://www.nsf.gov/funding/opportunities/pesose-pathways-enable-secure-open-source-ecosystems/nsf26-506/solicitation"
        ],
        "application_state": "OPEN",
        "opens_date": "UNKNOWN",
        "deadline": {
            "date": "2026-09-01",
            "time": "17:00",
            "timezone_basis": "submitting organization's local time; not a UTC instant",
        },
        "funding_evidence_state": "VERIFIED",
        "matching_state": "NOT_REQUIRED",
        "applicant_eligibility_state": "UNKNOWN",
    },
    "nsf-sbir-sttr-26-510": {
        "official_urls": [
            "https://www.nsf.gov/funding/opportunities/small-business-innovation-research-small-business-technology/nsf26-510/solicitation"
        ],
        "application_state": "OPEN",
        "opens_date": "UNKNOWN",
        "deadline": {
            "date": "2026-11-04",
            "time": "17:00",
            "timezone_basis": "submitting organization's local time; not a UTC instant",
        },
        "funding_evidence_state": "CONFLICT",
        "matching_state": "NOT_REQUIRED",
        "applicant_eligibility_state": "UNKNOWN",
    },
    "nlnet-restack-ois-2026": {
        "official_urls": [
            "https://nlnet.nl/propose/",
            "https://nlnet.nl/restack/",
            "https://nlnet.nl/restack/eligibility/",
        ],
        "application_state": "UPCOMING",
        "opens_date": "2026-09-03",
        "deadline": {
            "date": "2026-11-03",
            "time": "12:00",
            "timezone_basis": "CEST (noon), as labeled; no conversion performed",
        },
        "funding_evidence_state": "UNKNOWN",
        "matching_state": "UNKNOWN",
        "applicant_eligibility_state": "UNKNOWN",
    },
}


class LedgerError(ValueError):
    """The ledger does not match its public evidence contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LedgerError(message)


def _exact_keys(value, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), "%s must be an object" % at)
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, "%s missing keys %r" % (at, missing))
    _require(not extra, "%s has extra keys %r" % (at, extra))


def _walk_private_keys(value, at: str = "$") -> None:
    if isinstance(value, dict):
        found = sorted(PRIVATE_KEYS.intersection(value))
        _require(not found, "%s publishes private keys %r" % (at, found))
        for key, child in value.items():
            _walk_private_keys(child, "%s.%s" % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_keys(child, "%s[%d]" % (at, index))


def _assert_closed_schema(value, at: str = "$schema") -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            _require(value.get("additionalProperties") is False, "%s object schema is open" % at)
        for key, child in value.items():
            _assert_closed_schema(child, "%s.%s" % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_closed_schema(child, "%s[%d]" % (at, index))


def _nonempty_text(value, at: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), "%s must be nonempty text" % at)
    return value


def _string_list(value, at: str) -> list[str]:
    _require(isinstance(value, list) and bool(value), "%s must be a nonempty list" % at)
    _require(all(isinstance(item, str) and bool(item.strip()) for item in value), "%s has empty text" % at)
    _require(len(value) == len(set(value)), "%s has duplicates" % at)
    return value


def _canonical_sha256(value) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reject_duplicate_pairs(pairs):
    parsed = {}
    for key, value in pairs:
        _require(key not in parsed, "duplicate JSON key %r" % key)
        parsed[key] = value
    return parsed


def _reject_nonfinite(value: str):
    raise LedgerError("non-finite JSON constant %s" % value)


def _parse_json(raw: str, at: str):
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as exc:
        raise LedgerError("%s is malformed JSON" % at) from exc


def _timestamp(value, at: str) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "%s must be a UTC timestamp" % at)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerError("%s is malformed" % at) from exc
    _require(parsed.isoformat().endswith("+00:00"), "%s has no UTC offset" % at)
    return parsed


def _date(value, at: str) -> date:
    _require(isinstance(value, str) and bool(DATE_TEXT.fullmatch(value)), "%s is malformed" % at)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError("%s is malformed" % at) from exc
    return parsed


def _https(value, at: str) -> str:
    _require(isinstance(value, str), "%s must be text" % at)
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and bool(parsed.netloc), "%s must be HTTPS" % at)
    _require(parsed.username is None and parsed.password is None, "%s embeds private material" % at)
    try:
        port = parsed.port
    except ValueError as exc:
        raise LedgerError("%s has an invalid port" % at) from exc
    _require(port is None, "%s may not use a port" % at)
    _require(bool(parsed.hostname) and bool(DNS_HOST.fullmatch(parsed.hostname)), "%s has an invalid hostname" % at)
    _require(not any(character.isspace() for character in value), "%s contains whitespace" % at)
    return value


def _urls(value, at: str) -> list[str]:
    items = _string_list(value, at)
    for index, item in enumerate(items):
        _https(item, "%s[%d]" % (at, index))
    return items


def _deadline(value, checked: datetime, state: str, at: str):
    if value == "UNKNOWN":
        _require(state not in {"OPEN", "UPCOMING"}, "%s state requires a concrete deadline" % state)
        return value
    _exact_keys(value, {"date", "time", "timezone_basis"}, at)
    deadline_date = _date(value["date"], "%s.date" % at)
    _require(isinstance(value["time"], str) and bool(TIME_TEXT.fullmatch(value["time"])), "%s.time is malformed" % at)
    _nonempty_text(value["timezone_basis"], "%s.timezone_basis" % at)
    if state in {"OPEN", "UPCOMING"}:
        _require(deadline_date > checked.date(), "%s deadline is not future at checked_at" % at)
    return value


def _validate_program(program: dict, index: int) -> None:
    at = "programs[%d]" % index
    _walk_private_keys(program, at)
    _exact_keys(program, PROGRAM_KEYS, at)
    _require(isinstance(program["id"], str) and bool(ID_TEXT.fullmatch(program["id"])), "%s.id invalid" % at)
    _nonempty_text(program["funder"], "%s.funder" % at)
    _nonempty_text(program["program"], "%s.program" % at)
    official = _urls(program["official_urls"], "%s.official_urls" % at)
    evidence = _urls(program["evidence_urls"], "%s.evidence_urls" % at)
    _require(evidence == official, "%s evidence URLs must equal the inspected official URLs" % at)
    checked = _timestamp(program["checked_at"], "%s.checked_at" % at)
    _require(program["checked_at"] == CHECKED_AT, "%s checked_at drift" % at)
    states = {"OPEN", "UPCOMING", "ROLLING", "CLOSED", "UNKNOWN"}
    _require(program["application_state"] in states, "%s application_state invalid" % at)
    _nonempty_text(program["application_state_basis"], "%s.application_state_basis" % at)
    if program["opens_date"] != "UNKNOWN":
        _date(program["opens_date"], "%s.opens_date" % at)
    _deadline(program["deadline"], checked, program["application_state"], "%s.deadline" % at)
    evidence_states = {"VERIFIED", "PARTIAL", "CONFLICT", "UNKNOWN"}
    _require(program["program_eligibility_evidence_state"] in evidence_states, "%s eligibility evidence state invalid" % at)
    _require(isinstance(program["program_eligibility_text"], str), "%s eligibility text must be text" % at)
    if program["program_eligibility_evidence_state"] == "VERIFIED":
        _nonempty_text(program["program_eligibility_text"], "%s.program_eligibility_text" % at)
    _require(
        program["applicant_eligibility_state"] == "UNKNOWN",
        "%s may not adjudicate applicant eligibility" % at,
    )
    _require(
        program["applicant_eligibility_public_evidence_url"] == "UNKNOWN",
        "%s unknown applicant eligibility cannot cite a finding" % at,
    )
    _nonempty_text(program["funding_text"], "%s.funding_text" % at)
    _require(program["funding_evidence_state"] in evidence_states, "%s funding evidence state invalid" % at)
    _require(program["matching_state"] in {"REQUIRED", "NOT_REQUIRED", "UNKNOWN"}, "%s matching state invalid" % at)
    _nonempty_text(program["matching_basis"], "%s.matching_basis" % at)
    _nonempty_text(program["ip_terms"], "%s.ip_terms" % at)
    _require(program["ip_evidence_state"] in evidence_states, "%s IP evidence state invalid" % at)
    _string_list(program["deliverables"], "%s.deliverables" % at)
    _require(isinstance(program["fit_note"], str) and program["fit_note"].startswith("ANALYSIS:"), "%s fit note must start ANALYSIS:" % at)
    _nonempty_text(program["fit_note"][len("ANALYSIS:"):], "%s.fit_note" % at)
    _nonempty_text(program["public_next_action"], "%s.public_next_action" % at)
    _require(isinstance(program["owner"], str) and program["owner"].startswith("COMMONS_ANY_"), "%s owner must be nonexclusive" % at)
    _string_list(program["private_blockers"], "%s.private_blockers" % at)
    _string_list(program["nonclaims"], "%s.nonclaims" % at)
    _require(program["submission_status"] == "NOT_SUBMITTED", "%s fabricates filing status" % at)
    _require(program["award_status"] == "NOT_AWARDED", "%s fabricates award status" % at)
    _require(program["cash_received_usd"] == 0 and not isinstance(program["cash_received_usd"], bool), "%s fabricates cash" % at)


def load(root: Path = ROOT) -> tuple[dict, dict]:
    ledger = _parse_json((root / LEDGER_PATH).read_text(encoding="utf-8"), "ledger")
    schema = _parse_json((root / SCHEMA_PATH).read_text(encoding="utf-8"), "schema")
    return ledger, schema


def validate(root: Path, ledger: dict, schema: dict) -> dict:
    del root
    _require(_canonical_sha256(schema) == EXPECTED_SCHEMA_SHA256, "schema contract drift")
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/ip/grants_ledger.schema.json"), "schema id mismatch")
    _assert_closed_schema(schema)
    _walk_private_keys(ledger)
    _exact_keys(ledger, ROOT_KEYS, "ledger")
    _require(ledger["schema_version"] == "commons-grants-ledger/v1", "schema_version mismatch")
    _require(ledger["kind"] == "GRANTS_LEDGER", "kind mismatch")
    _timestamp(ledger["generated_at"], "generated_at")
    _require(ledger["generated_at"] == CHECKED_AT, "generated_at drift")
    _require(bool(HEX40.fullmatch(ledger["generated_from_main"])), "generated_from_main invalid")
    _require(ledger["generated_from_main"] == BASE_SHA, "generated_from_main base drift")
    _nonempty_text(ledger["scope"], "scope")
    _string_list(ledger["nonclaims"], "nonclaims")
    _exact_keys(ledger["legal_scope"], LEGAL_SCOPE_KEYS, "legal_scope")
    _require(
        all(value is False for value in ledger["legal_scope"].values()),
        "legal_scope values must be exact false booleans",
    )
    omitted = ledger["omitted_private_fields"]
    _require(isinstance(omitted, list) and len(omitted) == len(set(omitted)), "omitted_private_fields invalid")
    _require(set(omitted) == PRIVATE_KEYS, "omitted_private_fields incomplete")
    programs = ledger["programs"]
    _require(isinstance(programs, list) and bool(programs), "programs must be nonempty")
    for index, program in enumerate(programs):
        _validate_program(program, index)
    ids = [program["id"] for program in programs]
    _require(len(ids) == len(set(ids)), "duplicate program ids")
    _require(tuple(ids) == EXPECTED_IDS, "seed program ids drift")
    for program in programs:
        facts = EXPECTED_FACTS[program["id"]]
        for key, expected in facts.items():
            _require(program[key] == expected, "%s %s truth drift" % (program["id"], key))
    _require(_canonical_sha256(ledger) == EXPECTED_LEDGER_SHA256, "ledger evidence contract drift")
    state_counts = {}
    funding_counts = {}
    for program in programs:
        state_counts[program["application_state"]] = state_counts.get(program["application_state"], 0) + 1
        funding_counts[program["funding_evidence_state"]] = funding_counts.get(program["funding_evidence_state"], 0) + 1
    return {
        "status": "VALID",
        "programs": len(programs),
        "application_states": dict(sorted(state_counts.items())),
        "funding_evidence_states": dict(sorted(funding_counts.items())),
        "applicant_eligibility_states": {"UNKNOWN": len(programs)},
        "submission_statuses": {"NOT_SUBMITTED": len(programs)},
        "awards": 0,
        "cash_received_usd": 0,
    }


def _list_result(ledger: dict) -> dict:
    return {"status": "VALID", "programs": ledger["programs"]}


def _due_result(ledger: dict) -> dict:
    programs = []
    for program in ledger["programs"]:
        programs.append({
            "id": program["id"],
            "application_state": program["application_state"],
            "deadline": program["deadline"],
            "applicant_eligibility_state": program["applicant_eligibility_state"],
            "funding_evidence_state": program["funding_evidence_state"],
            "submission_status": program["submission_status"],
        })
    programs.sort(key=lambda item: item["deadline"]["date"] if isinstance(item["deadline"], dict) else "9999-12-31")
    return {"status": "VALID", "due": programs}


def _next_result(ledger: dict) -> dict:
    unknown = [
        program["id"]
        for program in ledger["programs"]
        if program["applicant_eligibility_state"] == "UNKNOWN"
    ]
    return {
        "status": "NONE_READY",
        "reason": "APPLICANT_ELIGIBILITY_UNKNOWN",
        "program_ids": unknown,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "list", "due", "next"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        ledger, schema = load(root)
        result = validate(root, ledger, schema)
        if args.command == "list":
            result = _list_result(ledger)
        elif args.command == "due":
            result = _due_result(ledger)
        elif args.command == "next":
            result = _next_result(ledger)
    except (LedgerError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("GRANTS LEDGER INVALID: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
