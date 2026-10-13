"""Source-bound procurement outcome learning without buyer-rationale invention.

This module compiles redacted, source-bound outcome evidence into deterministic
internal learning packets. It does not contact buyers, infer hidden evaluation
rationale, or create award/payment/revenue authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

INPUT_SCHEMA = "procurement-win-loss-evidence/input/v1"
OUTPUT_SCHEMA = "procurement-win-loss-evidence/output/v1"
PORTFOLIO_SCHEMA = "procurement-win-loss-evidence/portfolio/v1"
TRUTH_BOUNDARY = "INTERNAL_REVENUE_PLANNING_ONLY"

STATUSES = {"WON", "LOST", "NO_DECISION", "UNKNOWN"}
SOURCE_CLASSES = {"BUYER_NOTICE", "PROCUREMENT_PORTAL", "PUBLIC_AWARD_NOTICE", "REVIEWED_RECORD"}
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EMAIL = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9._%+-])")
URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]*)?(?:\(?\d{3}\)?[\s.-]*)\d{3}[\s.-]*\d{4}(?!\d)")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SCORE = re.compile(r"^(?:\d{1,4}(?:\.\d{1,2})?%|\d{1,4}(?:\.\d{1,2})?/\d{1,4}(?:\.\d{1,2})?)$")

LOST_PATTERNS = (
    re.compile(r"(?i)\b(?:not|wasn['’]?t|were not)\s+(?:selected|successful|awarded)\b"),
    re.compile(r"(?i)\b(?:selected|move forward with|awarded to)\s+(?:another|a different|other)\s+(?:vendor|offeror|proposer|firm)\b"),
    re.compile(r"(?i)\b(?:another|a different|other)\s+(?:vendor|offeror|proposer|firm)\s+(?:was\s+|has been\s+|is\s+)?selected\b"),
    re.compile(r"(?i)\bunsuccessful\b"),
)
WON_PATTERNS = (
    re.compile(r"(?i)\b(?:your|the)\s+(?:proposal|offer|firm)\s+(?:has been|was|is)\s+selected\s+for\s+award\b"),
    re.compile(r"(?i)\byou\s+(?:have been|were|are)\s+selected\s+for\s+award\b"),
    re.compile(r"(?i)\b(?:contract|award)\s+(?:has been|was|is)\s+awarded\s+to\s+(?:you|your firm|your company)\b"),
)
NO_DECISION_PATTERNS = (
    re.compile(r"(?i)\b(?:solicitation|procurement|rfp|rfq|bid)\s+(?:has been|was|is)\s+(?:cancelled|canceled|withdrawn)\b"),
    re.compile(r"(?i)\bno\s+award\s+(?:will be|was|is being|is)\s+made\b"),
    re.compile(r"(?i)\b(?:cancelled|canceled|withdrawn)\s+without\s+award\b"),
)

INPUT_KEYS = {"schema", "truth_boundary", "as_of", "opportunity", "evidence", "internal_hypotheses"}
OPPORTUNITY_KEYS = {"opportunity_id", "buyer_key", "proposal_sha256", "submitted_at"}
EVIDENCE_KEYS = {
    "evidence_id", "opportunity_id", "source_class", "observed_at", "source_sha256",
    "redacted_text", "status", "status_quote", "winner", "winner_quote",
    "reason", "reason_quote", "score", "score_quote",
}
HYPOTHESIS_KEYS = {"hypothesis_id", "statement", "test"}
AUTHORITY = {
    "buyer_contact_authorized": False,
    "award_established": False,
    "contract_established": False,
    "payment_established": False,
    "receivable_established": False,
    "revenue_established": False,
}


class OutcomeError(ValueError):
    pass


def canon(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(raw: bytes, where: str):
    if not isinstance(raw, (bytes, bytearray)):
        raise OutcomeError(f"{where}: bytes required")
    try:
        value = json.loads(bytes(raw))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OutcomeError(f"{where}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise OutcomeError(f"{where}: object required")
    return value


def _exact(value, keys, where):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise OutcomeError(f"{where}: keys mismatch")


def _safe_text(value, where, *, limit=4000, allow_empty=False):
    if not isinstance(value, str) or len(value) > limit or (not value and not allow_empty):
        raise OutcomeError(f"{where}: invalid text")
    if CONTROL.search(value):
        raise OutcomeError(f"{where}: control character")
    if EMAIL.search(value) or URL.search(value) or PHONE.search(value):
        raise OutcomeError(f"{where}: private contact/locator material forbidden")
    return value


def _token(value, where):
    if not isinstance(value, str) or not SAFE_TOKEN.fullmatch(value):
        raise OutcomeError(f"{where}: invalid token")
    return value


def _sha(value, where):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise OutcomeError(f"{where}: sha256 required")
    return value


def _timestamp(value, where):
    if not isinstance(value, str):
        raise OutcomeError(f"{where}: timestamp required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise OutcomeError(f"{where}: UTC timestamp required") from exc
    return parsed


def _optional_exact_claim(value, quote, text, where, *, score=False):
    if value is None or quote is None:
        if value is not None or quote is not None:
            raise OutcomeError(f"{where}: value/quote must both be null or strings")
        return None
    value = _safe_text(value, where + ".value", limit=512)
    quote = _safe_text(quote, where + ".quote", limit=512)
    if quote not in text or value != quote:
        raise OutcomeError(f"{where}: claim must equal an exact source quote")
    if score and not SCORE.fullmatch(value):
        raise OutcomeError(f"{where}: score must be a source-quoted numeric score")
    return value


def _status_supported(status, quote):
    if status == "UNKNOWN":
        return quote == ""
    patterns = LOST_PATTERNS if status == "LOST" else WON_PATTERNS if status == "WON" else NO_DECISION_PATTERNS
    return any(pattern.search(quote) for pattern in patterns)


def _normalize_input(raw: bytes):
    value = _load(raw, "input")
    _exact(value, INPUT_KEYS, "input")
    if value["schema"] != INPUT_SCHEMA or value["truth_boundary"] != TRUTH_BOUNDARY:
        raise OutcomeError("input: unsupported schema/truth boundary")
    as_of = _timestamp(value["as_of"], "as_of")

    opportunity = value["opportunity"]
    _exact(opportunity, OPPORTUNITY_KEYS, "opportunity")
    opportunity_id = _token(opportunity["opportunity_id"], "opportunity.opportunity_id")
    buyer_key = _token(opportunity["buyer_key"], "opportunity.buyer_key")
    proposal_sha = _sha(opportunity["proposal_sha256"], "opportunity.proposal_sha256")
    submitted_at = _timestamp(opportunity["submitted_at"], "opportunity.submitted_at")
    if submitted_at > as_of:
        raise OutcomeError("opportunity.submitted_at: future relative to as_of")

    evidence = value["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 1000:
        raise OutcomeError("evidence: invalid list")

    normalized_evidence = []
    seen_ids = set()
    seen_source_shas = set()
    seen_claims = set()
    terminal_statuses = set()
    for index, row in enumerate(evidence):
        where = f"evidence[{index}]"
        _exact(row, EVIDENCE_KEYS, where)
        evidence_id = _token(row["evidence_id"], where + ".evidence_id")
        if evidence_id in seen_ids:
            raise OutcomeError("evidence: duplicate evidence_id")
        seen_ids.add(evidence_id)
        if row["opportunity_id"] != opportunity_id:
            raise OutcomeError(where + ": wrong opportunity")
        source_class = _token(row["source_class"], where + ".source_class")
        if source_class not in SOURCE_CLASSES:
            raise OutcomeError(where + ": unsupported source_class")
        observed_at = _timestamp(row["observed_at"], where + ".observed_at")
        if observed_at < submitted_at:
            raise OutcomeError(where + ": outcome evidence predates proposal submission")
        if observed_at > as_of:
            raise OutcomeError(where + ": outcome evidence is future relative to as_of")
        text = _safe_text(row["redacted_text"], where + ".redacted_text", limit=12000)
        source_sha = _sha(row["source_sha256"], where + ".source_sha256")
        if digest(text.encode("utf-8")) != source_sha:
            raise OutcomeError(where + ": source_sha256 does not bind redacted_text")
        if source_sha in seen_source_shas:
            raise OutcomeError("evidence: duplicate/reminted source")
        seen_source_shas.add(source_sha)

        status = row["status"]
        if status not in STATUSES:
            raise OutcomeError(where + ": unsupported status")
        status_quote = row["status_quote"]
        if status == "UNKNOWN":
            if status_quote is not None:
                raise OutcomeError(where + ": UNKNOWN requires null status_quote")
            status_quote_norm = ""
        else:
            status_quote_norm = _safe_text(status_quote, where + ".status_quote", limit=1000)
            if status_quote_norm not in text:
                raise OutcomeError(where + ": status_quote not found in redacted_text")
            if not _status_supported(status, status_quote_norm):
                raise OutcomeError(where + ": status quote does not support asserted status")
            terminal_statuses.add(status)

        winner = _optional_exact_claim(row["winner"], row["winner_quote"], text, where + ".winner")
        reason = _optional_exact_claim(row["reason"], row["reason_quote"], text, where + ".reason")
        score = _optional_exact_claim(row["score"], row["score_quote"], text, where + ".score", score=True)

        claim_signature = (status, status_quote_norm, winner, reason, score)
        if claim_signature in seen_claims:
            raise OutcomeError("evidence: duplicate/reminted semantic claim")
        seen_claims.add(claim_signature)

        normalized_evidence.append({
            "evidence_id": evidence_id,
            "source_class": source_class,
            "observed_at": row["observed_at"],
            "source_sha256": source_sha,
            "status": status,
            "status_quote": None if status == "UNKNOWN" else status_quote_norm,
            "winner": winner,
            "reason": reason,
            "score": score,
        })

    if len(terminal_statuses) > 1:
        raise OutcomeError("evidence: contradictory terminal outcomes")

    hypotheses = value["internal_hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) > 200:
        raise OutcomeError("internal_hypotheses: invalid list")
    normalized_hypotheses = []
    hypothesis_ids = set()
    for index, item in enumerate(hypotheses):
        where = f"internal_hypotheses[{index}]"
        _exact(item, HYPOTHESIS_KEYS, where)
        hid = _token(item["hypothesis_id"], where + ".hypothesis_id")
        if hid in hypothesis_ids:
            raise OutcomeError("internal_hypotheses: duplicate hypothesis_id")
        hypothesis_ids.add(hid)
        normalized_hypotheses.append({
            "hypothesis_id": hid,
            "statement": _safe_text(item["statement"], where + ".statement", limit=1000),
            "test": _safe_text(item["test"], where + ".test", limit=1000),
            "classification": "INTERNAL_HYPOTHESIS_NOT_BUYER_FACT",
        })

    return {
        "as_of": value["as_of"],
        "opportunity": {
            "opportunity_id": opportunity_id,
            "buyer_key": buyer_key,
            "proposal_sha256": proposal_sha,
            "submitted_at": opportunity["submitted_at"],
        },
        "evidence": normalized_evidence,
        "terminal_statuses": terminal_statuses,
        "internal_hypotheses": normalized_hypotheses,
    }


def compile_packet(raw: bytes) -> bytes:
    data = _normalize_input(raw)
    status = next(iter(data["terminal_statuses"])) if data["terminal_statuses"] else "UNKNOWN"
    terminal = [item for item in data["evidence"] if item["status"] == status] if status != "UNKNOWN" else []
    winner_values = sorted({item["winner"] for item in terminal if item["winner"] is not None})
    reason_values = sorted({item["reason"] for item in terminal if item["reason"] is not None})
    score_values = sorted({item["score"] for item in terminal if item["score"] is not None})
    if len(winner_values) > 1:
        raise OutcomeError("evidence: conflicting source-bound winner claims")
    if len(reason_values) > 1:
        raise OutcomeError("evidence: conflicting source-bound reason claims")
    if len(score_values) > 1:
        raise OutcomeError("evidence: conflicting source-bound score claims")

    packet = {
        "schema": OUTPUT_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "as_of": data["as_of"],
        "opportunity": data["opportunity"],
        "outcome": {
            "status": status,
            "winner": {"known": bool(winner_values), "value": winner_values[0] if winner_values else None},
            "reason": {"known": bool(reason_values), "value": reason_values[0] if reason_values else None},
            "score": {"known": bool(score_values), "value": score_values[0] if score_values else None},
            "evidence_ids": sorted(item["evidence_id"] for item in terminal),
        },
        "evidence_receipts": [
            {
                "evidence_id": item["evidence_id"],
                "source_class": item["source_class"],
                "observed_at": item["observed_at"],
                "source_sha256": item["source_sha256"],
                "status": item["status"],
            }
            for item in sorted(data["evidence"], key=lambda x: x["evidence_id"])
        ],
        "internal_hypotheses": sorted(data["internal_hypotheses"], key=lambda x: x["hypothesis_id"]),
        "authority": dict(AUTHORITY),
        "learning_rule": "SOURCE_BOUND_FACTS_ONLY__HYPOTHESES_NEVER_PROMOTED",
    }
    return canon(packet)


def verify_packet(raw: bytes, packet_bytes: bytes) -> bool:
    expected = compile_packet(raw)
    if bytes(packet_bytes) != expected:
        raise OutcomeError("packet bytes mismatch")
    return True


def compile_portfolio(packet_blobs) -> bytes:
    if not isinstance(packet_blobs, (list, tuple)) or not packet_blobs:
        raise OutcomeError("portfolio: one or more packets required")
    packets = []
    seen_opportunities = set()
    counts = {status: 0 for status in sorted(STATUSES)}
    for index, blob in enumerate(packet_blobs):
        packet = _load(blob, f"portfolio[{index}]")
        if packet.get("schema") != OUTPUT_SCHEMA or packet.get("truth_boundary") != TRUTH_BOUNDARY:
            raise OutcomeError(f"portfolio[{index}]: unsupported packet")
        opp = packet.get("opportunity")
        outcome = packet.get("outcome")
        authority = packet.get("authority")
        if not isinstance(opp, dict) or not isinstance(outcome, dict) or authority != AUTHORITY:
            raise OutcomeError(f"portfolio[{index}]: malformed packet")
        opportunity_id = _token(opp.get("opportunity_id"), f"portfolio[{index}].opportunity_id")
        if opportunity_id in seen_opportunities:
            raise OutcomeError("portfolio: duplicate opportunity")
        seen_opportunities.add(opportunity_id)
        status = outcome.get("status")
        if status not in STATUSES:
            raise OutcomeError(f"portfolio[{index}]: bad status")
        counts[status] += 1
        packets.append({
            "opportunity_id": opportunity_id,
            "buyer_key": _token(opp.get("buyer_key"), f"portfolio[{index}].buyer_key"),
            "proposal_sha256": _sha(opp.get("proposal_sha256"), f"portfolio[{index}].proposal_sha256"),
            "status": status,
            "winner_known": bool(outcome.get("winner", {}).get("known")),
            "reason_known": bool(outcome.get("reason", {}).get("known")),
            "score_known": bool(outcome.get("score", {}).get("known")),
            "packet_sha256": digest(bytes(blob)),
        })
    portfolio = {
        "schema": PORTFOLIO_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "counts": counts,
        "opportunities": sorted(packets, key=lambda x: x["opportunity_id"]),
        "learning_rule": "OUTCOME_COUNTS_ARE_FACTS__CAUSES_REQUIRE_SOURCE_BOUND_REASON_EVIDENCE",
        "authority": dict(AUTHORITY),
    }
    return canon(portfolio)


def _write_exclusive(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--input", required=True)
    compile_p.add_argument("--output", required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--input", required=True)
    verify_p.add_argument("--packet", required=True)
    portfolio_p = sub.add_parser("portfolio")
    portfolio_p.add_argument("--output", required=True)
    portfolio_p.add_argument("packets", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            raw = Path(args.input).read_bytes()
            packet = compile_packet(raw)
            _write_exclusive(Path(args.output), packet)
            print(json.dumps({"packet_sha256": digest(packet), "status": json.loads(packet)["outcome"]["status"]}, sort_keys=True))
            return 0
        if args.cmd == "verify":
            verify_packet(Path(args.input).read_bytes(), Path(args.packet).read_bytes())
            print(json.dumps({"verified": True}, sort_keys=True))
            return 0
        blobs = [Path(path).read_bytes() for path in args.packets]
        portfolio = compile_portfolio(blobs)
        _write_exclusive(Path(args.output), portfolio)
        print(json.dumps({"portfolio_sha256": digest(portfolio), "count": len(blobs)}, sort_keys=True))
        return 0
    except (OSError, OutcomeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
