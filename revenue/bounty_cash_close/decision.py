from __future__ import annotations

from typing import Any

from .core import ACTIONS, ZERO_SHA256, CloseBoardError, format_utc, parse_utc

def _latest(receipts: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for receipt in reversed(receipts):
        if receipt["kind"] == kind:
            return receipt
    return None

def _row(bounty: dict[str, Any], policy: dict[str, int], as_of_epoch: int) -> dict[str, Any]:
    receipts = bounty["receipts"]
    for receipt in receipts:
        if parse_utc(receipt["observed_at_utc"], "receipt observed_at") > as_of_epoch:
            raise CloseBoardError("future receipt relative to trusted evaluation time")
    terminal = _latest(receipts, "TERMINAL_NONPAY")
    settlement = _latest(receipts, "SETTLEMENT_OBSERVED")
    payout = _latest(receipts, "PAYOUT_ACKNOWLEDGED")
    ask = _latest(receipts, "COMPENSATION_ASK_SENT")
    comp_follow = _latest(receipts, "COMPENSATION_FOLLOWUP_SENT")
    accepted = _latest(receipts, "TECHNICAL_ACCEPTED")
    delivered = _latest(receipts, "SUBMISSION_DELIVERED")
    gate_blocked = _latest(receipts, "GATE_BLOCKED")
    gate_cleared = _latest(receipts, "GATE_CLEARED")
    gate_follow = _latest(receipts, "GATE_FOLLOWUP_SENT")
    failed_attempt = _latest(receipts, "SUBMISSION_ATTEMPT_FAILED")
    unresolved_gate = gate_blocked is not None and (
        gate_cleared is None
        or parse_utc(gate_cleared["observed_at_utc"], "gate clear time")
        < parse_utc(gate_blocked["observed_at_utc"], "gate blocked time")
    )
    unresolved_attempt = failed_attempt is not None and (
        gate_cleared is None
        or parse_utc(gate_cleared["observed_at_utc"], "gate clear time")
        < parse_utc(failed_attempt["observed_at_utc"], "failed attempt time")
    )

    reasons: list[str] = []
    state: str
    action: str
    next_eligible_at: str | None = None

    if terminal is not None:
        state = "TERMINAL_NONPAY"
        action = "WAIT_DNR"
        reasons.append("TERMINAL_NONPAY_RECEIPT")
    elif settlement is not None:
        state = "SETTLED"
        action = "CLOSE_SETTLED"
        reasons.append("INDEPENDENT_PAYMENT_RAIL_SETTLEMENT_OBSERVED")
    elif payout is not None:
        state = "PAYOUT_ACK_SETTLEMENT_PENDING"
        action = "RECONCILE_SETTLEMENT"
        reasons.append("SPONSOR_PAYOUT_ACK_IS_NOT_SETTLEMENT")
    elif accepted is not None:
        if ask is None:
            state = "ACCEPTED_COMPENSATION_UNASKED"
            action = "ASK_COMPENSATION"
            reasons.append("TECHNICAL_ACCEPTANCE_WITHOUT_COMPENSATION_ASK")
        elif comp_follow is not None:
            state = "COMPENSATION_PENDING"
            action = "WAIT_DNR"
            reasons.append("COMPENSATION_FOLLOWUP_ALREADY_USED")
        else:
            ask_time = parse_utc(ask["observed_at_utc"], "compensation ask time")
            due = ask_time + policy["compensation_followup_after_seconds"]
            state = "COMPENSATION_PENDING"
            if as_of_epoch >= due:
                action = "FOLLOW_UP_COMPENSATION"
                reasons.append("COMPENSATION_FOLLOWUP_WINDOW_OPEN")
            else:
                action = "WAIT_DNR"
                next_eligible_at = format_utc(due)
                reasons.append("COMPENSATION_WAIT_WINDOW_ACTIVE")
    elif unresolved_gate:
        # The same follow-up budget applies before delivery: a failed send
        # must not turn one outstanding support case into repeated outreach.
        state = "SUBMITTED_GATE_BLOCKED" if delivered is not None else "SUBMISSION_BLOCKED"
        blocked_time = parse_utc(gate_blocked["observed_at_utc"], "gate blocked time")
        due = blocked_time + policy["gate_followup_after_seconds"]
        if gate_follow is not None:
            action = "WAIT_DNR"
            reasons.append("GATE_FOLLOWUP_ALREADY_USED")
        elif as_of_epoch >= due:
            action = "UNBLOCK_EXTERNAL_GATE"
            reasons.append("ONE_GATE_FOLLOWUP_WINDOW_OPEN")
        else:
            action = "WAIT_DNR"
            next_eligible_at = format_utc(due)
            reasons.append("GATE_WAIT_WINDOW_ACTIVE")
    elif delivered is not None:
        state = "SUBMITTED_PENDING_ACCEPTANCE"
        action = "WAIT_DNR"
        reasons.append("DELIVERED_SUBMISSION_NOT_YET_TECHNICALLY_ACCEPTED")
    elif unresolved_attempt:
        state = "SUBMISSION_BLOCKED"
        if gate_follow is not None:
            action = "WAIT_DNR"
            reasons.append("GATE_FOLLOWUP_ALREADY_USED")
        else:
            action = "UNBLOCK_EXTERNAL_GATE"
            reasons.append("FAILED_OR_HELD_TRANSPORT_IS_NOT_DELIVERY")
    else:
        state = "READY_TO_SUBMIT"
        action = "SUBMIT"
        reasons.append("NO_AUTHORITATIVE_DELIVERED_SUBMISSION_RECEIPT")

    if action not in ACTIONS:
        raise AssertionError(action)
    value = bounty["advertised_value"]
    return {
        "canonical_bounty_key": bounty["canonical_bounty_key"],
        "sponsor_ref": bounty["sponsor_ref"],
        "program_ref": bounty["program_ref"],
        "bounty_ref": bounty["bounty_ref"],
        "claimant_ref": bounty["claimant_ref"],
        "advertised_value": value,
        "state": state,
        "next_action": action,
        "reason_codes": reasons,
        "next_action_eligible_at_utc": next_eligible_at,
        "receipt_count": len(receipts),
        "chain_tip_sha256": receipts[-1]["receipt_sha256"] if receipts else ZERO_SHA256,
        "technical_acceptance_observed": accepted is not None,
        "payout_acknowledged": payout is not None,
        "settlement_observed": settlement is not None,
    }

def render_markdown(output: dict[str, Any]) -> str:
    lines = [
        "# Bounty Cash Close Board",
        "",
        f"Board: `{output['board_id']}`",
        f"Evaluated: `{output['evaluated_at_utc']}`",
        "",
        "> Decision support only. This board does not submit work, contact maintainers, ask for payout, create invoices, move money, or recognize revenue.",
        "",
        "| Bounty | Value | State | Next action | Reason |",
        "|---|---:|---|---|---|",
    ]
    for row in output["rows"]:
        value = row["advertised_value"]
        if value["state"] == "FIXED":
            amount = value["amount_minor"]
            rendered_value = f"{value['currency']} {amount // 100}.{amount % 100:02d}"
        else:
            rendered_value = "UNPRICED"
        reason = ", ".join(row["reason_codes"])
        lines.append(f"| `{row['bounty_ref']}` | {rendered_value} | `{row['state']}` | `{row['next_action']}` | {reason} |")
    lines.extend([
        "",
        "## Truth boundary",
        "",
        "- Merge/issue closure is technical acceptance only when an explicit `TECHNICAL_ACCEPTED` receipt says so.",
        "- Sponsor payout acknowledgement is not settlement.",
        "- `SETTLED` requires a later independent processor/wallet/bank/ledger observation.",
        "- Failed/held transport, provider setup, and payment-link creation never count as delivered submission or settlement.",
        "",
    ])
    return "\n".join(lines)
