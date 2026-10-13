#!/usr/bin/env python3
"""Deterministic synthetic acceptance fixture generator for the Huntington rail."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOMS = [f"ROOM-{i:03d}" for i in range(1, 144)]
SPA = [f"SPA-{i:02d}" for i in range(1, 13)]
DINING = [f"DINING-{i:02d}" for i in range(1, 21)]
BAR = [f"BAR-{i:02d}" for i in range(1, 11)]


def generate(journeys: int = 15000) -> dict[str, Any]:
    if isinstance(journeys, bool) or not isinstance(journeys, int) or journeys < 1:
        raise ValueError("journeys must be a positive integer")
    events: list[dict[str, Any]] = []
    seq = 1
    for surface, ids in (("ROOM", ROOMS), ("SPA", SPA), ("DINING", DINING), ("BAR", BAR)):
        for resource_id in ids:
            events.append({"event_id": f"RES-{surface}-{resource_id}", "type": "resource", "sequence": seq, "surface": surface, "resource_id": resource_id, "state": "AVAILABLE"})
            seq += 1

    seq = 1000
    for i in range(journeys):
        j = i + 1
        pid = f"P-{j:05d}"
        jid = f"J-{j:05d}"
        expected = ["ROOM"]
        if j % 10 == 0:
            expected.append("SPA")
        if j % 15 == 0:
            expected.append("DINING")
        if j % 25 == 0:
            expected.append("BAR")
        events.append({"event_id": f"E-{j}-P", "type": "promise", "sequence": seq, "promise_id": pid, "journey_id": jid, "expected_surfaces": expected})
        seq += 1

        room = ROOMS[i % len(ROOMS)]
        slot = f"NIGHT-{j:05d}"
        room_outcome = "REJECTED" if j == 124 else "APPLIED"
        if j == 124:
            events.append({"event_id": f"E-{j}-RH", "type": "resource", "sequence": seq, "surface": "ROOM", "resource_id": room, "state": "HOLD"}); seq += 1
        op = {"event_id": f"E-{j}-BR", "type": "booking", "sequence": seq, "operation_id": f"OP-BR-{j}", "promise_id": pid, "surface": "ROOM", "resource_id": room, "slot_id": slot, "action": "RESERVE", "outcome": room_outcome}
        events.append(op); seq += 1
        if j % 37 == 0:
            retry = dict(op); retry["event_id"] = f"E-{j}-BR-RETRY"; retry["sequence"] = seq; events.append(retry); seq += 1
        if j == 124:
            events.append({"event_id": f"E-{j}-RA", "type": "resource", "sequence": seq, "surface": "ROOM", "resource_id": room, "state": "AVAILABLE"}); seq += 1
            events.append({"event_id": f"E-{j}-BR2", "type": "booking", "sequence": seq, "operation_id": f"OP-BR2-{j}", "promise_id": pid, "surface": "ROOM", "resource_id": room, "slot_id": slot, "action": "RESERVE", "outcome": "APPLIED"}); seq += 1
        if j % 97 == 0:
            events.append({"event_id": f"E-{j}-NS", "type": "booking", "sequence": seq, "operation_id": f"OP-NS-{j}", "promise_id": pid, "surface": "ROOM", "resource_id": room, "slot_id": slot, "action": "NO_SHOW", "outcome": "APPLIED"}); seq += 1

        for surface, enabled, ids in (("SPA", j % 10 == 0, SPA), ("DINING", j % 15 == 0, DINING), ("BAR", j % 25 == 0, BAR)):
            if enabled:
                rid = ids[i % len(ids)]
                events.append({"event_id": f"E-{j}-H-{surface}", "type": "handoff", "sequence": seq, "handoff_id": f"H-{surface}-{j}", "promise_id": pid, "from_surface": "ROOM", "to_surface": surface, "state": "ACKED"}); seq += 1
                events.append({"event_id": f"E-{j}-B-{surface}", "type": "booking", "sequence": seq, "operation_id": f"OP-B-{surface}-{j}", "promise_id": pid, "surface": surface, "resource_id": rid, "slot_id": f"SLOT-{surface}-{j:05d}", "action": "RESERVE", "outcome": "APPLIED"}); seq += 1

        outcome = "UNKNOWN" if j in {5000, 10000, 15000} else "APPLIED"
        money = {"event_id": f"E-{j}-M", "type": "money", "sequence": seq, "operation_id": f"OP-M-{j}", "promise_id": pid, "account_type": "FOLIO", "account_id": f"FOLIO-{j:05d}", "kind": "CHARGE", "amount_cents": 20000 + (j % 5000), "related_operation_id": None, "outcome": outcome}
        events.append(money); seq += 1
        if j % 41 == 0:
            retry = dict(money); retry["event_id"] = f"E-{j}-M-RETRY"; retry["sequence"] = seq; events.append(retry); seq += 1
        if j % 211 == 0 and outcome == "APPLIED":
            events.append({"event_id": f"E-{j}-REF", "type": "money", "sequence": seq, "operation_id": f"OP-REF-{j}", "promise_id": pid, "account_type": "FOLIO", "account_id": f"FOLIO-{j:05d}", "kind": "REFUND", "amount_cents": 1000, "related_operation_id": f"OP-M-{j}", "outcome": "APPLIED"}); seq += 1

        if j % 40 == 0:
            acct = f"GIFT-{j:05d}"
            events.append({"event_id": f"E-{j}-GL", "type": "money", "sequence": seq, "operation_id": f"OP-GL-{j}", "promise_id": pid, "account_type": "GIFT_CARD", "account_id": acct, "kind": "LOAD", "amount_cents": 10000, "related_operation_id": None, "outcome": "APPLIED"}); seq += 1
            events.append({"event_id": f"E-{j}-GR", "type": "money", "sequence": seq, "operation_id": f"OP-GR-{j}", "promise_id": pid, "account_type": "GIFT_CARD", "account_id": acct, "kind": "REDEEM", "amount_cents": 3500, "related_operation_id": None, "outcome": "APPLIED"}); seq += 1
        if j % 50 == 0:
            acct = f"PACKAGE-{j:05d}"
            events.append({"event_id": f"E-{j}-PL", "type": "money", "sequence": seq, "operation_id": f"OP-PL-{j}", "promise_id": pid, "account_type": "PACKAGE", "account_id": acct, "kind": "LOAD", "amount_cents": 15000, "related_operation_id": None, "outcome": "APPLIED"}); seq += 1
            events.append({"event_id": f"E-{j}-PR", "type": "money", "sequence": seq, "operation_id": f"OP-PR-{j}", "promise_id": pid, "account_type": "PACKAGE", "account_id": acct, "kind": "REDEEM", "amount_cents": 5000, "related_operation_id": None, "outcome": "APPLIED"}); seq += 1
        if j % 100 == 0:
            rid = f"REC-{j:05d}"
            events.append({"event_id": f"E-{j}-RO", "type": "recovery", "sequence": seq, "recovery_id": rid, "promise_id": pid, "state": "OPEN", "reason_code": "SERVICE_RECOVERY"}); seq += 1
            final = "HOLD" if j in {5000, 10000, 15000} else "RESOLVED"
            events.append({"event_id": f"E-{j}-RC", "type": "recovery", "sequence": seq, "recovery_id": rid, "promise_id": pid, "state": final, "reason_code": "SERVICE_RECOVERY"}); seq += 1

    return {"review_owner_role": "Highgate guest-operations reviewer", "events": events}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journeys", type=int, default=15000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = generate(args.journeys)
    Path(args.output).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "journey_count": args.journeys, "event_count": len(payload["events"])}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
