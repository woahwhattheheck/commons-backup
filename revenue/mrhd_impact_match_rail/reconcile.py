#!/usr/bin/env python3
"""Deterministic reconciliation core for MRHD 2026 Impact Match grant records.

No network access, credentials, or external dependencies are required.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
BPS_DENOMINATOR = 10_000
DEFAULT_MATCH_RATE_BPS = 2_500
DEFAULT_IN_KIND_CAP_BPS = 5_000
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class LedgerError(ValueError):
    """Raised when the input ledger is ambiguous or invalid."""


def _require_keys(obj: dict[str, Any], *, required: set[str], optional: set[str], where: str) -> None:
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing:
        raise LedgerError(f"{where}: missing keys: {', '.join(sorted(missing))}")
    if unknown:
        raise LedgerError(f"{where}: unknown keys: {', '.join(sorted(unknown))}")


def _require_int(value: Any, *, where: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(f"{where}: expected integer")
    if minimum is not None and value < minimum:
        raise LedgerError(f"{where}: must be >= {minimum}")
    return value


def _require_bool(value: Any, *, where: str) -> bool:
    if not isinstance(value, bool):
        raise LedgerError(f"{where}: expected boolean")
    return value


def _require_str(value: Any, *, where: str, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise LedgerError(f"{where}: expected string")
    if nonempty and not value.strip():
        raise LedgerError(f"{where}: must not be empty")
    return value


def _evidence(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where)
    if not SHA256_RE.fullmatch(text):
        raise LedgerError(f"{where}: expected 64-hex SHA-256")
    return text.lower()


def _ceil_fraction(value: int, numerator: int, denominator: int = BPS_DENOMINATOR) -> int:
    return (value * numerator + denominator - 1) // denominator


def _floor_fraction(value: int, numerator: int, denominator: int = BPS_DENOMINATOR) -> int:
    return (value * numerator) // denominator


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _event_ids_unique(groups: Iterable[tuple[str, list[dict[str, Any]]]], *, award_id: str) -> None:
    seen: dict[str, str] = {}
    for group_name, events in groups:
        for idx, event in enumerate(events):
            event_id = _require_str(event.get("event_id"), where=f"award {award_id}.{group_name}[{idx}].event_id")
            if event_id in seen:
                raise LedgerError(
                    f"award {award_id}: duplicate event_id {event_id!r} in {seen[event_id]} and {group_name}"
                )
            seen[event_id] = group_name


def _parse_amendments(items: Any, *, award_id: str) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not isinstance(items, list):
        raise LedgerError(f"award {award_id}.amendments: expected list")
    parsed: list[dict[str, Any]] = []
    approved_delta = 0
    holds: list[str] = []
    for idx, raw in enumerate(items):
        where = f"award {award_id}.amendments[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"event_id", "delta_cents", "approved", "effective_at", "evidence_sha256"}, optional=set(), where=where)
        event_id = _require_str(raw["event_id"], where=f"{where}.event_id")
        delta = _require_int(raw["delta_cents"], where=f"{where}.delta_cents")
        approved = _require_bool(raw["approved"], where=f"{where}.approved")
        effective_at = _require_str(raw["effective_at"], where=f"{where}.effective_at")
        evidence = _evidence(raw["evidence_sha256"], where=f"{where}.evidence_sha256")
        if approved:
            approved_delta += delta
        else:
            holds.append("UNAPPROVED_AMENDMENT_PRESENT")
        parsed.append({
            "event_id": event_id,
            "delta_cents": delta,
            "approved": approved,
            "effective_at": effective_at,
            "evidence_sha256": evidence,
        })
    parsed.sort(key=lambda x: (x["effective_at"], x["event_id"]))
    return parsed, approved_delta, holds


def _parse_contributions(items: Any, *, award_id: str) -> tuple[list[dict[str, Any]], int, int, int]:
    if not isinstance(items, list):
        raise LedgerError(f"award {award_id}.contributions: expected list")
    parsed: list[dict[str, Any]] = []
    realized_cash = 0
    realized_in_kind = 0
    committed_not_realized = 0
    for idx, raw in enumerate(items):
        where = f"award {award_id}.contributions[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"event_id", "kind", "amount_cents", "realized", "evidence_sha256"}, optional=set(), where=where)
        event_id = _require_str(raw["event_id"], where=f"{where}.event_id")
        kind = _require_str(raw["kind"], where=f"{where}.kind").lower()
        if kind not in {"cash", "in_kind"}:
            raise LedgerError(f"{where}.kind: expected cash or in_kind")
        amount = _require_int(raw["amount_cents"], where=f"{where}.amount_cents", minimum=0)
        realized = _require_bool(raw["realized"], where=f"{where}.realized")
        evidence = _evidence(raw["evidence_sha256"], where=f"{where}.evidence_sha256")
        if realized:
            if kind == "cash":
                realized_cash += amount
            else:
                realized_in_kind += amount
        else:
            committed_not_realized += amount
        parsed.append({
            "event_id": event_id,
            "kind": kind,
            "amount_cents": amount,
            "realized": realized,
            "evidence_sha256": evidence,
        })
    parsed.sort(key=lambda x: x["event_id"])
    return parsed, realized_cash, realized_in_kind, committed_not_realized


def _parse_expenses(items: Any, *, award_id: str) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(items, list):
        raise LedgerError(f"award {award_id}.expenses: expected list")
    parsed: list[dict[str, Any]] = []
    eligible = 0
    ineligible = 0
    for idx, raw in enumerate(items):
        where = f"award {award_id}.expenses[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"event_id", "amount_cents", "eligible", "evidence_sha256"}, optional=set(), where=where)
        event_id = _require_str(raw["event_id"], where=f"{where}.event_id")
        amount = _require_int(raw["amount_cents"], where=f"{where}.amount_cents", minimum=0)
        is_eligible = _require_bool(raw["eligible"], where=f"{where}.eligible")
        evidence = _evidence(raw["evidence_sha256"], where=f"{where}.evidence_sha256")
        if is_eligible:
            eligible += amount
        else:
            ineligible += amount
        parsed.append({
            "event_id": event_id,
            "amount_cents": amount,
            "eligible": is_eligible,
            "evidence_sha256": evidence,
        })
    parsed.sort(key=lambda x: x["event_id"])
    return parsed, eligible, ineligible


def _parse_reimbursements(items: Any, *, award_id: str) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(items, list):
        raise LedgerError(f"award {award_id}.reimbursements: expected list")
    parsed: list[dict[str, Any]] = []
    paid = 0
    pending = 0
    for idx, raw in enumerate(items):
        where = f"award {award_id}.reimbursements[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"event_id", "amount_cents", "status", "evidence_sha256"}, optional=set(), where=where)
        event_id = _require_str(raw["event_id"], where=f"{where}.event_id")
        amount = _require_int(raw["amount_cents"], where=f"{where}.amount_cents", minimum=0)
        status = _require_str(raw["status"], where=f"{where}.status").lower()
        if status not in {"pending", "paid", "void"}:
            raise LedgerError(f"{where}.status: expected pending, paid, or void")
        evidence = _evidence(raw["evidence_sha256"], where=f"{where}.evidence_sha256")
        if status == "paid":
            paid += amount
        elif status == "pending":
            pending += amount
        parsed.append({
            "event_id": event_id,
            "amount_cents": amount,
            "status": status,
            "evidence_sha256": evidence,
        })
    parsed.sort(key=lambda x: x["event_id"])
    return parsed, paid, pending


def _parse_milestones(items: Any, *, award_id: str) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(items, list):
        raise LedgerError(f"award {award_id}.milestones: expected list")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    complete = 0
    unresolved = 0
    for idx, raw in enumerate(items):
        where = f"award {award_id}.milestones[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(raw, required={"milestone_id", "status", "evidence_sha256"}, optional=set(), where=where)
        milestone_id = _require_str(raw["milestone_id"], where=f"{where}.milestone_id")
        if milestone_id in seen:
            raise LedgerError(f"award {award_id}: duplicate milestone_id {milestone_id!r}")
        seen.add(milestone_id)
        status = _require_str(raw["status"], where=f"{where}.status").lower()
        if status not in {"pending", "complete", "waived"}:
            raise LedgerError(f"{where}.status: expected pending, complete, or waived")
        evidence = _evidence(raw["evidence_sha256"], where=f"{where}.evidence_sha256")
        if status == "complete":
            complete += 1
        elif status == "pending":
            unresolved += 1
        parsed.append({"milestone_id": milestone_id, "status": status, "evidence_sha256": evidence})
    parsed.sort(key=lambda x: x["milestone_id"])
    return parsed, complete, unresolved


def reconcile(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and reconcile an Impact Match ledger into a deterministic receipt."""
    if not isinstance(payload, dict):
        raise LedgerError("root: expected object")
    _require_keys(
        payload,
        required={"schema_version", "cycle_id", "awards"},
        optional={"match_rate_bps", "in_kind_cap_bps_of_required_match"},
        where="root",
    )
    schema_version = _require_int(payload["schema_version"], where="root.schema_version", minimum=1)
    if schema_version != SCHEMA_VERSION:
        raise LedgerError(f"root.schema_version: unsupported version {schema_version}")
    cycle_id = _require_str(payload["cycle_id"], where="root.cycle_id")
    match_rate_bps = _require_int(payload.get("match_rate_bps", DEFAULT_MATCH_RATE_BPS), where="root.match_rate_bps", minimum=0)
    in_kind_cap_bps = _require_int(
        payload.get("in_kind_cap_bps_of_required_match", DEFAULT_IN_KIND_CAP_BPS),
        where="root.in_kind_cap_bps_of_required_match",
        minimum=0,
    )
    if match_rate_bps > BPS_DENOMINATOR:
        raise LedgerError("root.match_rate_bps: must be <= 10000")
    if in_kind_cap_bps > BPS_DENOMINATOR:
        raise LedgerError("root.in_kind_cap_bps_of_required_match: must be <= 10000")

    awards_raw = payload["awards"]
    if not isinstance(awards_raw, list):
        raise LedgerError("root.awards: expected list")
    seen_awards: set[str] = set()
    awards_out: list[dict[str, Any]] = []

    cycle_final_award = 0
    cycle_required_match = 0
    cycle_counted_match = 0
    cycle_eligible_expense = 0
    cycle_paid_reimbursement = 0
    held_awards = 0

    for idx, raw in enumerate(awards_raw):
        where = f"root.awards[{idx}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{where}: expected object")
        _require_keys(
            raw,
            required={
                "award_id",
                "base_award_cents",
                "amendments",
                "contributions",
                "expenses",
                "reimbursements",
                "milestones",
            },
            optional=set(),
            where=where,
        )
        award_id = _require_str(raw["award_id"], where=f"{where}.award_id")
        if award_id in seen_awards:
            raise LedgerError(f"root.awards: duplicate award_id {award_id!r}")
        seen_awards.add(award_id)
        base_award = _require_int(raw["base_award_cents"], where=f"{where}.base_award_cents", minimum=1)

        _event_ids_unique(
            (
                ("amendments", raw["amendments"]),
                ("contributions", raw["contributions"]),
                ("expenses", raw["expenses"]),
                ("reimbursements", raw["reimbursements"]),
            ),
            award_id=award_id,
        )

        amendments, approved_delta, holds = _parse_amendments(raw["amendments"], award_id=award_id)
        contributions, realized_cash, realized_in_kind, committed_match = _parse_contributions(raw["contributions"], award_id=award_id)
        expenses, eligible_expense, ineligible_expense = _parse_expenses(raw["expenses"], award_id=award_id)
        reimbursements, paid_reimbursement, pending_reimbursement = _parse_reimbursements(raw["reimbursements"], award_id=award_id)
        milestones, complete_milestones, pending_milestones = _parse_milestones(raw["milestones"], award_id=award_id)

        final_award = base_award + approved_delta
        if final_award <= 0:
            raise LedgerError(f"award {award_id}: approved amendments reduce award to non-positive value")

        required_match = _ceil_fraction(final_award, match_rate_bps)
        in_kind_cap = _floor_fraction(required_match, in_kind_cap_bps)
        counted_in_kind = min(realized_in_kind, in_kind_cap)
        counted_match = realized_cash + counted_in_kind
        required_project_spend = final_award + required_match

        if realized_in_kind > in_kind_cap:
            holds.append("IN_KIND_OVER_CAP")
        if counted_match < required_match:
            holds.append("MATCH_SHORTFALL")
        if eligible_expense < required_project_spend:
            holds.append("PROJECT_SPEND_BELOW_AWARD_PLUS_MATCH")
        if paid_reimbursement > final_award:
            holds.append("REIMBURSEMENT_EXCEEDS_AWARD")
        if paid_reimbursement > eligible_expense:
            holds.append("REIMBURSEMENT_EXCEEDS_ELIGIBLE_EXPENSE")
        if pending_milestones:
            holds.append("MILESTONES_PENDING")

        holds = sorted(set(holds))
        status = "PASS" if not holds else "HOLD"
        if holds:
            held_awards += 1

        awards_out.append({
            "award_id": award_id,
            "status": status,
            "holds": holds,
            "base_award_cents": base_award,
            "approved_amendment_delta_cents": approved_delta,
            "final_award_cents": final_award,
            "required_match_cents": required_match,
            "realized_cash_match_cents": realized_cash,
            "realized_in_kind_match_cents": realized_in_kind,
            "in_kind_counting_cap_cents": in_kind_cap,
            "counted_in_kind_match_cents": counted_in_kind,
            "counted_match_cents": counted_match,
            "committed_not_realized_match_cents": committed_match,
            "required_project_spend_cents": required_project_spend,
            "eligible_expense_cents": eligible_expense,
            "ineligible_expense_cents": ineligible_expense,
            "paid_reimbursement_cents": paid_reimbursement,
            "pending_reimbursement_cents": pending_reimbursement,
            "complete_milestones": complete_milestones,
            "pending_milestones": pending_milestones,
            "amendments": amendments,
            "contributions": contributions,
            "expenses": expenses,
            "reimbursements": reimbursements,
            "milestones": milestones,
        })

        cycle_final_award += final_award
        cycle_required_match += required_match
        cycle_counted_match += counted_match
        cycle_eligible_expense += eligible_expense
        cycle_paid_reimbursement += paid_reimbursement

    awards_out.sort(key=lambda x: x["award_id"])
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "rules": {
            "match_rate_bps": match_rate_bps,
            "in_kind_cap_bps_of_required_match": in_kind_cap_bps,
            "match_rounding": "ceil_to_cent",
            "in_kind_cap_rounding": "floor_to_cent",
            "commitments_count_toward_match": False,
        },
        "summary": {
            "award_count": len(awards_out),
            "held_award_count": held_awards,
            "status": "PASS" if held_awards == 0 else "HOLD",
            "final_award_cents": cycle_final_award,
            "required_match_cents": cycle_required_match,
            "counted_match_cents": cycle_counted_match,
            "eligible_expense_cents": cycle_eligible_expense,
            "paid_reimbursement_cents": cycle_paid_reimbursement,
        },
        "awards": awards_out,
    }
    receipt = hashlib.sha256(_canonical_bytes(result)).hexdigest()
    result["receipt_sha256"] = receipt
    return result


def verify_receipt(result: dict[str, Any]) -> bool:
    """Verify an emitted reconciliation receipt without accessing original inputs."""
    if not isinstance(result, dict) or "receipt_sha256" not in result:
        return False
    claimed = result.get("receipt_sha256")
    if not isinstance(claimed, str) or not SHA256_RE.fullmatch(claimed):
        return False
    unsigned = dict(result)
    del unsigned["receipt_sha256"]
    expected = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    return hmac.compare_digest(claimed.lower(), expected)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LedgerError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid JSON in {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="input ledger JSON")
    parser.add_argument("--output", type=Path, help="write canonical pretty JSON receipt")
    parser.add_argument("--require-pass", action="store_true", help="exit 3 if any award is held")
    parser.add_argument("--verify", type=Path, help="verify a previously emitted receipt and exit")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            result = _load_json(args.verify)
            ok = verify_receipt(result)
            print("VALID" if ok else "INVALID")
            return 0 if ok else 4
        if args.input is None:
            parser.error("input is required unless --verify is used")
        payload = _load_json(args.input)
        result = reconcile(payload)
    except LedgerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    if args.require_pass and result["summary"]["status"] != "PASS":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
