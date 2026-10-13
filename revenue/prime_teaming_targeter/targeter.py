from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "prime-teaming-targeter/input/v1"
RECEIPT_SCHEMA = "prime-teaming-targeter/receipt/v1"
MAX_EVIDENCE_AGE_DAYS = 45
MAX_INPUT_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
STATUSES = {"MEETS", "PARTIAL", "UNKNOWN"}
SOURCE_KINDS = {"PUBLIC_OFFICIAL", "CANDIDATE_PUBLIC", "OWNER_PROVIDED"}


class TargeterError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, (bytes, bytearray)) else _canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise TargeterError(f"{field} must be UTC ISO-8601 ending in Z")
    try:
        dt = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise TargeterError(f"{field} is not valid ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise TargeterError(f"{field} must be UTC")
    return dt


def _format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise TargeterError("trusted_now must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargeterError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise TargeterError(f"{field} must be an array")
    return value


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise TargeterError(f"{field} must match {ID_RE.pattern}")
    return value


def _require_text(value: Any, field: str, *, max_len: int = 400) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise TargeterError(f"{field} must be non-empty text <= {max_len} chars")
    return value.strip()


def _require_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
        raise TargeterError(f"{field} must be integer in [{minimum}, {maximum}]")
    return value


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise TargeterError(f"{field} must be lowercase SHA-256 hex")
    return value


def _normalize_input(payload: Any) -> dict[str, Any]:
    root = _require_dict(payload, "input")
    if root.get("schema") != SCHEMA:
        raise TargeterError(f"schema must equal {SCHEMA}")

    opportunity = _require_dict(root.get("opportunity"), "opportunity")
    opportunity_id = _require_id(opportunity.get("opportunity_id"), "opportunity.opportunity_id")
    title = _require_text(opportunity.get("title"), "opportunity.title", max_len=240)
    source_ref = _require_text(opportunity.get("source_ref"), "opportunity.source_ref", max_len=1000)
    source_sha256 = _require_sha(opportunity.get("source_sha256"), "opportunity.source_sha256")
    observed_at = _format_utc(_parse_utc(opportunity.get("observed_at"), "opportunity.observed_at"))
    deadline_at = _format_utc(_parse_utc(opportunity.get("deadline_at"), "opportunity.deadline_at"))

    requirements_raw = _require_list(opportunity.get("requirements"), "opportunity.requirements")
    if not requirements_raw:
        raise TargeterError("opportunity.requirements must not be empty")
    requirements: list[dict[str, Any]] = []
    requirement_ids: set[str] = set()
    weight_sum = 0
    for index, raw in enumerate(requirements_raw):
        item = _require_dict(raw, f"opportunity.requirements[{index}]")
        rid = _require_id(item.get("requirement_id"), f"opportunity.requirements[{index}].requirement_id")
        if rid in requirement_ids:
            raise TargeterError(f"duplicate requirement_id: {rid}")
        requirement_ids.add(rid)
        weight = _require_int(item.get("weight_bps"), f"opportunity.requirements[{index}].weight_bps", minimum=1, maximum=10000)
        weight_sum += weight
        mandatory = item.get("mandatory")
        if not isinstance(mandatory, bool):
            raise TargeterError(f"opportunity.requirements[{index}].mandatory must be boolean")
        requirements.append({
            "requirement_id": rid,
            "label": _require_text(item.get("label"), f"opportunity.requirements[{index}].label", max_len=240),
            "weight_bps": weight,
            "mandatory": mandatory,
        })
    if weight_sum != 10000:
        raise TargeterError("requirement weight_bps must sum to 10000")

    authority_raw = _require_list(root.get("evidence_authority"), "evidence_authority")
    authority: list[dict[str, Any]] = []
    authority_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(authority_raw):
        item = _require_dict(raw, f"evidence_authority[{index}]")
        evidence_id = _require_id(item.get("evidence_id"), f"evidence_authority[{index}].evidence_id")
        if evidence_id in authority_by_id:
            raise TargeterError(f"duplicate evidence_id: {evidence_id}")
        kind = item.get("source_kind")
        if kind not in SOURCE_KINDS:
            raise TargeterError(f"evidence_authority[{index}].source_kind invalid")
        record = {
            "evidence_id": evidence_id,
            "opportunity_id": _require_id(item.get("opportunity_id"), f"evidence_authority[{index}].opportunity_id"),
            "candidate_id": _require_id(item.get("candidate_id"), f"evidence_authority[{index}].candidate_id"),
            "requirement_id": _require_id(item.get("requirement_id"), f"evidence_authority[{index}].requirement_id"),
            "source_kind": kind,
            "source_ref": _require_text(item.get("source_ref"), f"evidence_authority[{index}].source_ref", max_len=1000),
            "source_sha256": _require_sha(item.get("source_sha256"), f"evidence_authority[{index}].source_sha256"),
            "observed_at": _format_utc(_parse_utc(item.get("observed_at"), f"evidence_authority[{index}].observed_at")),
            "status": item.get("status"),
            "note": _require_text(item.get("note"), f"evidence_authority[{index}].note", max_len=500),
        }
        if record["status"] not in STATUSES:
            raise TargeterError(f"evidence_authority[{index}].status invalid")
        if record["opportunity_id"] != opportunity_id:
            raise TargeterError(f"evidence {evidence_id} transplanted from another opportunity")
        if record["requirement_id"] not in requirement_ids:
            raise TargeterError(f"evidence {evidence_id} references unknown requirement")
        authority.append(record)
        authority_by_id[evidence_id] = record

    candidates_raw = _require_list(root.get("candidates"), "candidates")
    if not candidates_raw:
        raise TargeterError("candidates must not be empty")
    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for index, raw in enumerate(candidates_raw):
        item = _require_dict(raw, f"candidates[{index}]")
        candidate_id = _require_id(item.get("candidate_id"), f"candidates[{index}].candidate_id")
        if candidate_id in candidate_ids:
            raise TargeterError(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        refs_raw = _require_list(item.get("evidence_ids"), f"candidates[{index}].evidence_ids")
        if len(refs_raw) != len(set(refs_raw)):
            raise TargeterError(f"candidates[{index}].evidence_ids contains duplicate references")
        refs: list[str] = []
        for evidence_id_raw in refs_raw:
            evidence_id = _require_id(evidence_id_raw, f"candidates[{index}].evidence_ids[]")
            record = authority_by_id.get(evidence_id)
            if record is None:
                raise TargeterError(f"candidate {candidate_id} references missing evidence {evidence_id}")
            if record["candidate_id"] != candidate_id:
                raise TargeterError(f"evidence {evidence_id} transplanted across candidates")
            refs.append(evidence_id)

        paid_scope = _require_dict(item.get("paid_scope"), f"candidates[{index}].paid_scope")
        amount_minor = _require_int(paid_scope.get("amount_minor"), f"candidates[{index}].paid_scope.amount_minor", minimum=1, maximum=1_000_000_000_000)
        currency = paid_scope.get("currency")
        if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
            raise TargeterError(f"candidates[{index}].paid_scope.currency must be uppercase 3-letter code")
        deliverables = [_require_text(v, f"candidates[{index}].paid_scope.deliverables[]", max_len=500) for v in _require_list(paid_scope.get("deliverables"), f"candidates[{index}].paid_scope.deliverables")]
        acceptance = [_require_text(v, f"candidates[{index}].paid_scope.acceptance_criteria[]", max_len=500) for v in _require_list(paid_scope.get("acceptance_criteria"), f"candidates[{index}].paid_scope.acceptance_criteria")]
        if not deliverables or not acceptance:
            raise TargeterError("paid_scope deliverables and acceptance_criteria must not be empty")
        candidates.append({
            "candidate_id": candidate_id,
            "name": _require_text(item.get("name"), f"candidates[{index}].name", max_len=240),
            "evidence_ids": refs,
            "paid_scope": {
                "title": _require_text(paid_scope.get("title"), f"candidates[{index}].paid_scope.title", max_len=240),
                "amount_minor": amount_minor,
                "currency": currency,
                "deliverables": deliverables,
                "acceptance_criteria": acceptance,
                "status": "PROPOSED_NOT_ACCEPTED",
            },
        })

    return {
        "schema": SCHEMA,
        "opportunity": {
            "opportunity_id": opportunity_id,
            "title": title,
            "source_ref": source_ref,
            "source_sha256": source_sha256,
            "observed_at": observed_at,
            "deadline_at": deadline_at,
            "requirements": requirements,
        },
        "evidence_authority": sorted(authority, key=lambda row: row["evidence_id"]),
        "candidates": sorted(candidates, key=lambda row: row["candidate_id"]),
    }


def compile_targeter(payload: Any, *, trusted_now: datetime | None = None) -> dict[str, Any]:
    normalized = _normalize_input(payload)
    now = trusted_now or datetime.now(timezone.utc)
    evaluated_at = _format_utc(now)
    opportunity = normalized["opportunity"]
    deadline = _parse_utc(opportunity["deadline_at"], "opportunity.deadline_at")
    opportunity_observed = _parse_utc(opportunity["observed_at"], "opportunity.observed_at")
    if opportunity_observed > now:
        global_hold = "HOLD_FUTURE_OPPORTUNITY_SOURCE"
    elif deadline <= now:
        global_hold = "HOLD_DEADLINE_PASSED"
    else:
        global_hold = None

    requirements = {row["requirement_id"]: row for row in opportunity["requirements"]}
    authority = {row["evidence_id"]: row for row in normalized["evidence_authority"]}
    rows: list[dict[str, Any]] = []
    for candidate in normalized["candidates"]:
        per_requirement: dict[str, list[dict[str, Any]]] = {rid: [] for rid in requirements}
        stale_ids: list[str] = []
        future_ids: list[str] = []
        for evidence_id in candidate["evidence_ids"]:
            record = authority[evidence_id]
            observed = _parse_utc(record["observed_at"], f"evidence {evidence_id}.observed_at")
            age_seconds = (now - observed).total_seconds()
            if age_seconds < 0:
                future_ids.append(evidence_id)
            elif age_seconds > MAX_EVIDENCE_AGE_DAYS * 86400:
                stale_ids.append(evidence_id)
            per_requirement[record["requirement_id"]].append(record)

        score = 0
        missing: list[str] = []
        mandatory_not_met: list[str] = []
        coverage: list[dict[str, Any]] = []
        for rid, req in requirements.items():
            records = per_requirement[rid]
            effective = [row for row in records if row["evidence_id"] not in stale_ids and row["evidence_id"] not in future_ids]
            statuses = {row["status"] for row in effective}
            if "MEETS" in statuses:
                factor = 10000
                status = "MEETS"
            elif "PARTIAL" in statuses:
                factor = 5000
                status = "PARTIAL"
            elif "UNKNOWN" in statuses:
                factor = 0
                status = "UNKNOWN"
            else:
                factor = 0
                status = "MISSING"
                missing.append(rid)
            if req["mandatory"] and status != "MEETS":
                mandatory_not_met.append(rid)
            score += req["weight_bps"] * factor // 10000
            coverage.append({
                "requirement_id": rid,
                "status": status,
                "mandatory": req["mandatory"],
                "evidence_ids": sorted(row["evidence_id"] for row in effective),
            })

        reasons: list[str] = []
        if global_hold:
            reasons.append(global_hold)
        if future_ids:
            reasons.append("HOLD_FUTURE_EVIDENCE")
        if stale_ids:
            reasons.append("HOLD_STALE_EVIDENCE")
        if mandatory_not_met:
            reasons.append("HOLD_MANDATORY_EVIDENCE")
        if missing:
            reasons.append("HOLD_MISSING_EVIDENCE")
        state = "ELIGIBLE_FOR_OWNER_OUTREACH_REVIEW" if not reasons else "HOLD_NEEDS_EVIDENCE"
        rows.append({
            "candidate_id": candidate["candidate_id"],
            "name": candidate["name"],
            "state": state,
            "score_bps": score,
            "coverage": sorted(coverage, key=lambda row: row["requirement_id"]),
            "missing_requirement_ids": sorted(missing),
            "mandatory_not_met_ids": sorted(mandatory_not_met),
            "stale_evidence_ids": sorted(stale_ids),
            "future_evidence_ids": sorted(future_ids),
            "hold_reasons": sorted(set(reasons)),
            "paid_scope": candidate["paid_scope"],
            "outreach_authorized": False,
            "prime_participation_confirmed": False,
            "buyer_acceptance_confirmed": False,
            "payment_confirmed": False,
            "revenue_recognized": False,
        })

    rows.sort(key=lambda row: (row["state"] != "ELIGIBLE_FOR_OWNER_OUTREACH_REVIEW", -row["score_bps"], row["candidate_id"]))
    eligible = [row for row in rows if row["state"] == "ELIGIBLE_FOR_OWNER_OUTREACH_REVIEW"]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "evaluated_at": evaluated_at,
        "policy": {
            "max_evidence_age_days": MAX_EVIDENCE_AGE_DAYS,
            "mandatory_requires": "MEETS",
            "partial_factor_bps": 5000,
            "outreach_authorized": False,
        },
        "input_sha256": _sha256(normalized),
        "evidence_authority_sha256": _sha256(normalized["evidence_authority"]),
        "opportunity_id": opportunity["opportunity_id"],
        "opportunity_deadline_at": opportunity["deadline_at"],
        "decision": "READY_FOR_OWNER_TARGET_REVIEW" if eligible else "HOLD_NO_EVIDENCE_COMPLETE_TARGET",
        "selected_candidate_id": eligible[0]["candidate_id"] if eligible else None,
        "ranked_candidates": rows,
        "authority_ceiling": {
            "external_send": False,
            "prime_commitment": False,
            "bid_submission": False,
            "contract_acceptance": False,
            "payment": False,
            "recognized_revenue": False,
        },
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def verify_receipt(payload: Any, receipt: Any, *, trusted_now: datetime | None = None) -> dict[str, Any]:
    provided = _require_dict(receipt, "receipt")
    digest = provided.get("receipt_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        return {"integrity_valid": False, "reason": "BAD_RECEIPT_SHA256"}
    unsigned = dict(provided)
    unsigned.pop("receipt_sha256", None)
    if _sha256(unsigned) != digest:
        return {"integrity_valid": False, "reason": "RECEIPT_DIGEST_MISMATCH"}
    try:
        historical_at = _parse_utc(provided.get("evaluated_at"), "receipt.evaluated_at")
        expected = compile_targeter(payload, trusted_now=historical_at)
    except TargeterError as exc:
        return {"integrity_valid": False, "reason": f"RECOMPILE_ERROR:{exc}"}
    if expected != provided:
        return {"integrity_valid": False, "reason": "RECEIPT_RECOMPILE_MISMATCH"}
    current = compile_targeter(payload, trusted_now=trusted_now or datetime.now(timezone.utc))
    return {
        "integrity_valid": True,
        "reason": "OK",
        "historical_decision": provided["decision"],
        "current_decision": current["decision"],
        "current_selected_candidate_id": current["selected_candidate_id"],
        "current_receipt_sha256": current["receipt_sha256"],
    }



def render_markdown(receipt: Any) -> str:
    row = _require_dict(receipt, "receipt")
    if row.get("schema") != RECEIPT_SCHEMA:
        raise TargeterError(f"receipt.schema must equal {RECEIPT_SCHEMA}")
    selected = row.get("selected_candidate_id")
    lines = [
        "# Prime / Teaming Target Brief",
        "",
        f"- Opportunity: `{row.get('opportunity_id')}`",
        f"- Evaluated: `{row.get('evaluated_at')}`",
        f"- Deadline: `{row.get('opportunity_deadline_at')}`",
        f"- Decision: **{row.get('decision')}**",
        f"- Selected candidate: `{selected}`" if selected else "- Selected candidate: _none_",
        "- External outreach authorized: **NO**",
        "- Prime participation confirmed: **NO**",
        "- Payment / recognized revenue authority: **NO**",
        "",
        "## Ranked candidates",
        "",
    ]
    for candidate in row.get("ranked_candidates") or []:
        paid = candidate.get("paid_scope") or {}
        lines.extend([
            f"### {candidate.get('name')} (`{candidate.get('candidate_id')}`)",
            "",
            f"- State: **{candidate.get('state')}**",
            f"- Evidence score: **{candidate.get('score_bps')} / 10000 bps**",
            f"- Paid-scope status: **{paid.get('status')}**",
            f"- Proposed amount: **{paid.get('amount_minor')} minor units {paid.get('currency')}**",
            f"- Hold reasons: {', '.join(candidate.get('hold_reasons') or []) or 'none'}",
            f"- Missing requirements: {', '.join(candidate.get('missing_requirement_ids') or []) or 'none'}",
            "",
            "Deliverables:",
        ])
        for item in paid.get("deliverables") or []:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Acceptance criteria:")
        for item in paid.get("acceptance_criteria") or []:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend([
        "## Authority ceiling",
        "",
        "This brief is owner-review decision support only. It does not authorize provider contact, prime commitment, bid submission, contract acceptance, payment, or revenue recognition.",
        "",
        f"Receipt SHA-256: `{row.get('receipt_sha256')}`",
        "",
    ])
    return "\n".join(lines)

def _load_json(path: Path) -> Any:
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise TargeterError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargeterError(f"invalid JSON: {exc}") from exc


def _write_exclusive(path: Path, value: Any) -> None:
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-bound prime/teaming target selector")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("input", type=Path)
    compile_cmd.add_argument("output", type=Path)
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("input", type=Path)
    verify_cmd.add_argument("receipt", type=Path)
    render_cmd = sub.add_parser("render")
    render_cmd.add_argument("input", type=Path)
    render_cmd.add_argument("receipt", type=Path)
    render_cmd.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            payload = _load_json(args.input)
            receipt = _load_json(args.receipt)
            verified = verify_receipt(payload, receipt)
            if not verified.get("integrity_valid"):
                raise TargeterError(f"refusing to render invalid receipt: {verified.get('reason')}")
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(render_markdown(receipt))
            return 0
        payload = _load_json(args.input)
        if args.command == "compile":
            _write_exclusive(args.output, compile_targeter(payload))
            return 0
        result = verify_receipt(payload, _load_json(args.receipt))
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("integrity_valid") else 2
    except (OSError, TargeterError) as exc:
        print(f"prime-teaming-targeter: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
