#!/usr/bin/env python3
"""Compile GPT oversight packets from the right-now queue without sending mail."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT / "revenue" / "right_now" / "action_packets.json"
DEMAND = ROOT / "revenue" / "right_now" / "demand_ledger.json"
EXPERIMENTS = ROOT / "revenue" / "right_now" / "experiments.json"
CONTROL = ROOT / "revenue" / "right_now" / "control.json"

ALLOWED_STATUS = {
    "safe research/build action",
    "ready-to-draft",
    "ready-to-send under existing authorization",
    "owner-sensitive external action",
    "do-not-contact",
    "do-not-resend",
    "needs more evidence",
    "disqualified",
}


class PacketError(ValueError):
    """Packet ledger drifted from the no-fiction contract."""


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PacketError(f"{path} must be an object")
    return value


def validate_packets(value: dict[str, Any]) -> None:
    if value.get("kind") != "GPT_ACTION_PACKETS":
        raise PacketError("unsupported packet kind")
    cash = value.get("cash") or {}
    if cash.get("collected_cash_usd") != 0 or cash.get("cash_claimed") is not False:
        raise PacketError("packets must not invent cash")
    packets = value.get("packets")
    if not isinstance(packets, list) or not packets:
        raise PacketError("packets must be a non-empty list")
    seen = set()
    for row in packets:
        cid = row.get("candidate_id")
        if not isinstance(cid, str) or cid in seen:
            raise PacketError("packet ids must be unique")
        seen.add(cid)
        status = row.get("status")
        if status not in ALLOWED_STATUS:
            raise PacketError(f"unknown status: {status}")
        if row.get("lane") == "do-not-resend" and "do-not-resend" not in str(row.get("status")):
            raise PacketError(f"{cid} DNR lane without DNR status")
        if row.get("economic_state_if_successful") in {"SETTLED", "BANK_AVAILABLE"}:
            raise PacketError("packets must not skip to cash states")
        if status == "ready-to-send under existing authorization":
            receipt = row.get("live_first_party_receipt")
            if not isinstance(receipt, dict) or receipt.get("state") != "LIVE" or not receipt.get("evidence"):
                raise PacketError(f"{cid} ready-to-send requires a live first-party receipt")
            if row.get("confirm_before_send") is not True:
                raise PacketError(f"{cid} ready-to-send must retain confirm_before_send")
        if row.get("concise_proposed_message") and status in {"do-not-resend", "do-not-contact"}:
            raise PacketError(f"{cid} must not carry a send body")


def validate_experiments(value: dict[str, Any]) -> None:
    rows = value.get("experiments")
    if not isinstance(rows, list) or len(rows) < 8:
        raise PacketError("need at least eight experiments")
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        raise PacketError("experiment ids must be unique")
    for row in rows:
        if row.get("observed_result") in {"PAID", "CASH", "SOLD"}:
            raise PacketError("experiment result invented cash")
        for field in ("hypothesis", "buyer", "channel", "offer", "page", "cta", "next_action", "success_event", "kill_condition", "observed_result", "source_evidence"):
            if not str(row.get(field) or "").strip():
                raise PacketError(f"experiment missing {field}")


def validate_demand(value: dict[str, Any]) -> None:
    if value.get("collected_cash_usd") != 0:
        raise PacketError("demand ledger must not invent cash")
    for row in value.get("candidates") or []:
        if not row.get("url") or not row.get("source_date"):
            raise PacketError("demand rows need url and date")
        if row.get("purchasing_ability") not in {"missing", "unverified", "present"}:
            raise PacketError("purchasing_ability must stay exact")


def next_external_action(control: dict[str, Any], packets: dict[str, Any]) -> str:
    for row in packets["packets"]:
        if row["status"] == "ready-to-send under existing authorization":
            return f"confirm once, then send authorized packet {row['candidate_id']}"
    for item in control.get("execution_queue") or []:
        if item.get("decision") == "READY_TO_DRAFT":
            return f"draft packet for {item['prospect_id']} without sending"
    return (
        "Keep inbound doors live (agent-triage.html, "
        "tokenjunkielabs@gmail.com). Do not resend held prospects. "
        "Founder still must evidence a chargeable processor path."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "next"))
    args = parser.parse_args()
    try:
        packets = read_object(PACKETS)
        demand = read_object(DEMAND)
        experiments = read_object(EXPERIMENTS)
        control = read_object(CONTROL)
        validate_packets(packets)
        validate_demand(demand)
        validate_experiments(experiments)
        if control["truth"]["collected_cash_usd"] != 0:
            raise PacketError("control cash drifted")
        if args.command == "validate":
            print(
                "VALID "
                f"{len(packets['packets'])} packets "
                f"{len(demand['candidates'])} demand "
                f"{len(experiments['experiments'])} experiments "
                "USD 0 cash"
            )
        else:
            print(next_external_action(control, packets))
    except (OSError, json.JSONDecodeError, PacketError, KeyError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
