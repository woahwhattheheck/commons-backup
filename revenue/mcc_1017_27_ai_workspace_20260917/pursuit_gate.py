from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

OPPORTUNITY_ID = "MCC-1017-27"
SCHEMA = "mcc-1017-27-pursuit-gate/v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ROOT = {
    "opportunity_id",
    "buyer_authoritative_sources",
    "secondary_sources",
    "prime_evidence",
    "partner_candidates",
    "deadlines",
    "workshare",
}
_AUTHORITY = {
    "buyer_contact_authorized": False,
    "partner_contact_authorized": False,
    "portal_mutation_authorized": False,
    "proposal_submission_authorized": False,
    "contract_signature_authorized": False,
    "spend_authorized": False,
    "award_verified": False,
    "payment_received": False,
    "revenue_recognized": False,
}


class GateError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateError("non-canonical input") from exc


def _detached(packet: Any) -> dict[str, Any]:
    raw = _canonical(packet)
    if len(raw) > 256_000:
        raise GateError("packet too large")
    out = json.loads(raw)
    if not isinstance(out, dict) or set(out) != _ALLOWED_ROOT:
        raise GateError("root schema mismatch")
    if out.get("opportunity_id") != OPPORTUNITY_ID:
        raise GateError("opportunity mismatch")
    return out


def _source(source: Any, *, kind: str) -> dict[str, str]:
    if not isinstance(source, dict) or set(source) != {
        "kind",
        "locator",
        "sha256",
        "captured_at",
    }:
        raise GateError("source schema mismatch")
    if source["kind"] != kind:
        raise GateError("source kind mismatch")
    if not isinstance(source["locator"], str) or not source["locator"].startswith(
        ("https://", "file:")
    ):
        raise GateError("source locator invalid")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(
        source["sha256"]
    ):
        raise GateError("source digest invalid")
    if not isinstance(source["captured_at"], str):
        raise GateError("source captured_at invalid")
    return source


def _deadline(value: Any) -> datetime:
    if not isinstance(value, str):
        raise GateError("deadline must be string")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GateError("deadline invalid") from exc
    if dt.tzinfo is None:
        raise GateError("deadline must be offset-aware")
    return dt.astimezone(timezone.utc)


def _deadline_binding(
    value: Any,
    *,
    buyer_digests: set[str],
    secondary_digests: set[str],
) -> tuple[datetime, str, bool]:
    if not isinstance(value, dict) or set(value) != {
        "at",
        "authority",
        "source_sha256",
    }:
        raise GateError("deadline binding schema mismatch")
    when = _deadline(value["at"])
    digest = value["source_sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise GateError("deadline source digest invalid")
    authority = value["authority"]
    if authority == "BUYER_PACKAGE":
        if digest not in buyer_digests:
            raise GateError("buyer deadline source is not retained buyer authority")
        return when, authority, True
    if authority == "SECONDARY_DISCOVERY":
        if digest not in secondary_digests:
            raise GateError("secondary deadline source is not retained discovery evidence")
        return when, authority, False
    raise GateError("deadline authority invalid")


def _evidence_record(item: Any, expected_kind: str) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != {
        "kind",
        "subject",
        "sha256",
        "locator",
    }:
        raise GateError("evidence schema mismatch")
    if item["kind"] != expected_kind:
        raise GateError("evidence kind mismatch")
    if not isinstance(item["subject"], str) or not item["subject"].strip():
        raise GateError("evidence subject invalid")
    if not isinstance(item["sha256"], str) or not _SHA256.fullmatch(item["sha256"]):
        raise GateError("evidence digest invalid")
    if not isinstance(item["locator"], str) or not item["locator"].startswith(
        ("https://", "file:")
    ):
        raise GateError("evidence locator invalid")
    return item


def compile_packet(packet: Any, *, evaluated_at: str) -> dict[str, Any]:
    p = _detached(packet)
    now = _deadline(evaluated_at)

    buyer = p["buyer_authoritative_sources"]
    secondary = p["secondary_sources"]
    if not isinstance(buyer, list) or not isinstance(secondary, list):
        raise GateError("source sets must be lists")
    buyer_records = [_source(x, kind="BUYER_PACKAGE") for x in buyer]
    secondary_records = [_source(x, kind="SECONDARY_DISCOVERY") for x in secondary]
    buyer_digests = {x["sha256"] for x in buyer_records}
    secondary_digests = {x["sha256"] for x in secondary_records}

    deadlines = p["deadlines"]
    if not isinstance(deadlines, dict) or set(deadlines) != {
        "questions_due",
        "response_due",
    }:
        raise GateError("deadline schema mismatch")
    questions_due, question_authority, question_authoritative = _deadline_binding(
        deadlines["questions_due"],
        buyer_digests=buyer_digests,
        secondary_digests=secondary_digests,
    )
    response_due, response_authority, response_authoritative = _deadline_binding(
        deadlines["response_due"],
        buyer_digests=buyer_digests,
        secondary_digests=secondary_digests,
    )
    if not questions_due < response_due:
        raise GateError("deadline order invalid")
    deadline_authority_complete = question_authoritative and response_authoritative

    prime = p["prime_evidence"]
    if not isinstance(prime, dict) or set(prime) != {
        "experience_evidence",
        "higher_ed_reference_evidence",
    }:
        raise GateError("prime evidence schema mismatch")
    experience = [
        _evidence_record(x, "RELEVANT_EXPERIENCE")
        for x in prime["experience_evidence"]
    ]
    references = [
        _evidence_record(x, "HIGHER_ED_REFERENCE")
        for x in prime["higher_ed_reference_evidence"]
    ]
    distinct_refs = {x["subject"] for x in references}

    partners = p["partner_candidates"]
    if not isinstance(partners, list):
        raise GateError("partner_candidates must be list")
    partner_rows = []
    for candidate in partners:
        if not isinstance(candidate, dict) or set(candidate) != {
            "name",
            "public_fit_sources",
            "solicitation_qualification_evidence",
        }:
            raise GateError("partner candidate schema mismatch")
        if not isinstance(candidate["name"], str) or not candidate["name"].strip():
            raise GateError("partner name invalid")
        public_fit = [
            _evidence_record(x, "PUBLIC_CAPABILITY")
            for x in candidate["public_fit_sources"]
        ]
        solicitation = [
            _evidence_record(x, "SOLICITATION_QUALIFICATION")
            for x in candidate["solicitation_qualification_evidence"]
        ]
        status = (
            "QUALIFICATION_EVIDENCE_PRESENT"
            if solicitation
            else ("PUBLIC_FIT_ONLY" if public_fit else "UNSCREENED")
        )
        partner_rows.append(
            {
                "name": candidate["name"],
                "status": status,
                "public_fit_count": len(public_fit),
                "solicitation_qualification_count": len(solicitation),
            }
        )

    workshare = p["workshare"]
    if not isinstance(workshare, dict) or set(workshare) != {
        "amount_cents",
        "currency",
        "accepted",
    }:
        raise GateError("workshare schema mismatch")
    if type(workshare["amount_cents"]) is not int or workshare["amount_cents"] <= 0:
        raise GateError("amount_cents invalid")
    if workshare["currency"] != "USD" or type(workshare["accepted"]) is not bool:
        raise GateError("workshare fields invalid")

    buyer_package_present = bool(buyer_records)
    prime_evidence_present = bool(experience) and len(distinct_refs) >= 3
    direct_prime_ready = (
        buyer_package_present and prime_evidence_present and deadline_authority_complete
    )

    if not buyer_package_present:
        state = "HOLD_MISSING_BUYER_PACKAGE"
    elif not deadline_authority_complete:
        state = "HOLD_DEADLINE_AUTHORITY"
    elif not prime_evidence_present:
        state = "HOLD_PRIME_QUALIFICATION"
    else:
        state = "INTERNAL_PRIME_EVIDENCE_REVIEW_ONLY"

    out = {
        "schema": SCHEMA,
        "opportunity_id": OPPORTUNITY_ID,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "state": state,
        "buyer_package_present": buyer_package_present,
        "buyer_authoritative_source_count": len(buyer_records),
        "secondary_source_count": len(secondary_records),
        "deadline_authority_complete": deadline_authority_complete,
        "question_deadline_authority": question_authority,
        "response_deadline_authority": response_authority,
        "prime_evidence_present": prime_evidence_present,
        "direct_prime_ready": direct_prime_ready,
        "question_window_open": (
            now < questions_due if question_authoritative else None
        ),
        "response_window_open": (
            now < response_due if response_authoritative else None
        ),
        "partner_candidates": partner_rows,
        "workshare": {
            "amount_cents": workshare["amount_cents"],
            "currency": workshare["currency"],
            "accepted": workshare["accepted"],
            "status": (
                "ACCEPTED_EVIDENCE_SUPPLIED"
                if workshare["accepted"]
                else "PROPOSED_NOT_ACCEPTED"
            ),
        },
        "authority": dict(_AUTHORITY),
    }
    out["receipt_sha256"] = hashlib.sha256(_canonical(out)).hexdigest()
    return out


def verify_packet(packet: Any, compiled: Any, *, evaluated_at: str) -> bool:
    if not isinstance(compiled, dict):
        return False
    try:
        expected = compile_packet(packet, evaluated_at=evaluated_at)
    except GateError:
        return False
    return _canonical(expected) == _canonical(compiled)


def loads_strict(raw: str) -> dict[str, Any]:
    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise GateError("duplicate JSON key")
            out[key] = value
        return out

    try:
        obj = json.loads(
            raw,
            object_pairs_hook=hook,
            parse_constant=lambda _: (_ for _ in ()).throw(
                GateError("non-finite JSON")
            ),
        )
    except GateError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise GateError("invalid JSON") from exc
    if not isinstance(obj, dict):
        raise GateError("JSON root must be object")
    return obj


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise GateError("input read failed") from exc
    if len(raw.encode("utf-8")) > 256_000:
        raise GateError("input too large")
    return loads_strict(raw)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="MCC 1017-27 internal pursuit readiness gate"
    )
    parser.add_argument("packet")
    parser.add_argument("--evaluated-at", required=True)
    parser.add_argument("--verify")
    args = parser.parse_args(argv)

    packet = _read_json(args.packet)
    if args.verify:
        compiled = _read_json(args.verify)
        ok = verify_packet(packet, compiled, evaluated_at=args.evaluated_at)
        print(json.dumps({"verified": ok}, sort_keys=True, separators=(",", ":")))
        return 0 if ok else 2

    compiled = compile_packet(packet, evaluated_at=args.evaluated_at)
    print(json.dumps(compiled, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
