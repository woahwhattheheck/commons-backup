"""Readable fictional scenarios executed by the existing collection compiler.

Run with ``python -m tools.revenue_collection_desk.rehearsal [--json]``.
Writes only stdout; performs no contact, payment, file mutation or network call.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Context, localcontext
import hashlib
import json

from . import core


def _claim(cid, kinds, *, instrument="USD", amount="90.00"):
    events = []
    for index, kind in enumerate(kinds):
        event = {
            "event_id": f"fiction-{cid}-{index}",
            "at": f"2026-09-01T{index:02d}:00:00Z",
            "kind": kind,
            "source_ref": f"fictional-evidence-{cid}-{index}",
            "source_digest": hashlib.sha256(f"FICTION:{cid}:{index}:{kind}".encode()).hexdigest(),
        }
        if kind == "ENTITLEMENT_CONFIRMED":
            event.update(entitlement_instrument=instrument, entitlement_amount=amount)
        elif kind == "PAYMENT_ASSERTED":
            event["hold_until"] = "2026-09-20T00:00:00Z"
        elif kind == "COLLECTION_CONTACT_SENT":
            event["cooldown_until"] = "2026-09-02T00:00:00Z"
        elif kind == "SETTLED_CASH":
            event.update(settlement_currency="EUR", settlement_amount="1.25")
        events.append(event)
    return {
        "claim_id": cid, "counterparty_id": "fictional-counterparty",
        "work_ref": f"fictional-work-{cid}", "instrument": instrument,
        "amount": amount, "events": events,
    }


def cases():
    accepted = ["WORK_SUBMITTED", "ACCEPTED"]
    entitled = accepted + ["ENTITLEMENT_CONFIRMED"]
    contact = entitled + ["COLLECTION_CONTACT_SENT"]
    records = [
        ("acceptance-only", _claim("unconfirmed", accepted), "VERIFY_ENTITLEMENT",
         "Acceptance alone leaves compensation unconfirmed, not outstanding cash."),
        ("bound-entitlement", _claim("entitled", entitled), "COLLECTION_ELIGIBLE",
         "A matching compensation record makes the queue eligible, but sends nothing."),
        ("instrument-mismatch", _claim("wrong-instrument", entitled), "REJECTED",
         "An entitlement for RTC cannot support a USD claim."),
        ("amount-mismatch", _claim("wrong-amount", entitled), "REJECTED",
         "An entitlement for 91 cannot support a claim for 90."),
        ("asserted-payment-hold", _claim("hold", accepted + ["PAYMENT_ASSERTED"]), "WAIT_HOLD",
         "A statement that payment was sent remains a hold, not settled cash."),
        ("available-token-balance", _claim("available", accepted + ["PAYMENT_AVAILABLE"], instrument="RTC", amount="25"), "VERIFY_SETTLEMENT",
         "The available RTC balance and its USD reference value are not cash."),
        ("explicit-settlement", _claim("settled", accepted + ["SETTLED_CASH"], instrument="RTC", amount="25"), "DONE",
         "Only the supplied fictional EUR 1.25 settlement is counted as cash; no RTC conversion occurs."),
        ("silence-after-delivery", _claim("silence", contact + ["DELIVERY_CONFIRMED"]), "WAIT_REPLY",
         "The cooldown has passed, but silence never releases the prior-contact hold."),
        ("bounced-contact", _claim("bounce", contact + ["DELIVERY_BOUNCED"]), "ROUTE_REPAIR_REQUIRED",
         "A bounce leaves a dead route, not a delivered collection attempt."),
        ("closed-without-payment", _claim("closed", accepted + ["CLOSED_NO_PAY"]), "DONE",
         "DONE can mean closed without payment; read the financial state and cash fields."),
        ("disputed-work", _claim("disputed", accepted + ["DISPUTED"]), "HOLD_CONFLICT",
         "Disputed amounts stay separately identified and do not become cash."),
    ]
    result = []
    for name, row, action, explanation in records:
        expected_error = None
        if name == "instrument-mismatch":
            row["events"][-1]["entitlement_instrument"] = "RTC"
            expected_error = "entitlement instrument does not match claim instrument"
        elif name == "amount-mismatch":
            row["events"][-1]["entitlement_amount"] = "91"
            expected_error = "entitlement amount does not match claim amount"
        elif name == "available-token-balance":
            row["reference_valuation"] = {
                "currency": "USD", "amount": "4.25", "source_ref": "fictional-reference-only",
                "source_digest": hashlib.sha256(b"FICTION:reference-only").hexdigest(),
            }
        result.append({
            "id": name, "explanation": explanation, "expected_actions": [action],
            "expected_error": expected_error, "expected_cash": {"EUR": "1.25"} if name == "explicit-settlement" else {},
            "ledger": {"schema": core.LEDGER_SCHEMA, "as_of": "2026-09-18T00:00:00Z", "claims": [row]},
        })
    result.append({
        "id": "exact-money-across-contexts",
        "explanation": "A large unconfirmed amount plus 0.09 retains every cent at precision 3, 28 and 80. It remains unconfirmed, not cash.",
        "expected_actions": ["VERIFY_ENTITLEMENT", "VERIFY_ENTITLEMENT"],
        "expected_error": None, "expected_cash": {},
        "expected_unconfirmed_usd": "1234567890123456789012345678.1",
        "ledger": {
            "schema": core.LEDGER_SCHEMA, "as_of": "2026-09-18T00:00:00Z",
            "claims": [
                _claim("large", accepted, amount="1234567890123456789012345678.01"),
                _claim("small", accepted, amount="0.09"),
            ],
        },
    })
    return result


def run():
    results = []
    for case in cases():
        outcomes = []
        for precision in (3, 28, 80):
            with localcontext(Context(prec=precision)):
                try:
                    report = core.compile_ledger(copy.deepcopy(case["ledger"]))
                    outcomes.append({"report": report})
                except core.ContractError as exc:
                    outcomes.append({"error": str(exc)})
        same = all(core.canonical_bytes(item) == core.canonical_bytes(outcomes[0]) for item in outcomes)
        actual = outcomes[0]
        report = actual.get("report")
        actions = [row["next_action"] for row in report["claims"]] if report is not None else ["REJECTED"]
        passed = same and actions == case["expected_actions"]
        replay_verified = tampered_report_rejected = None
        if case["expected_error"] is not None:
            passed = passed and case["expected_error"] in actual.get("error", "")
        elif report is None:
            passed = False
        else:
            with localcontext(Context(prec=3)):
                replay_verified = core.verify_ledger(case["ledger"], report)
                tampered = copy.deepcopy(report)
                tampered["mixed_currency_sum"] = "1"
                tampered_report_rejected = not core.verify_ledger(case["ledger"], tampered)
            passed = passed and replay_verified and tampered_report_rejected
            passed = passed and report["settled_cash_by_currency"] == case["expected_cash"]
            passed = passed and report["mixed_currency_sum"] is None
            passed = passed and not report["reference_valuations_recognized_as_cash"]
            passed = passed and all(value is False for value in report["authority"].values())
            if "expected_unconfirmed_usd" in case:
                passed = passed and report["totals_by_instrument"]["USD"]["accepted_unconfirmed"] == case["expected_unconfirmed_usd"]
        results.append({
            **case, "actual": actual, "context_invariant": same,
            "replay_verified": replay_verified, "tampered_report_rejected": tampered_report_rejected,
            "passed": bool(passed),
        })
    payload = {
        "schema": "commons.revenue_collection_rehearsal/v1", "synthetic": True,
        "notice": "All records, counterparties, source references and digests are fictional. This is executable behavior, not real collection, settlement or source authenticity.",
        "precisions_exercised": [3, 28, 80], "cases": results,
        "all_passed": all(item["passed"] for item in results),
    }
    payload["rehearsal_receipt_sha256"] = core.sha256_value(payload)
    return payload


def markdown(payload):
    lines = ["# Revenue Collection Desk: fictional operator rehearsal", "", payload["notice"], ""]
    for item in payload["cases"]:
        lines += [f"## {item['id']}", "", item["explanation"]]
        report = item["actual"].get("report")
        if report is None:
            lines.append("Observed rejection: " + item["actual"]["error"])
        else:
            for row in report["claims"]:
                lines.append(f"Observed: {row['claim_id']} | {row['state']} | {row['next_action']}")
            lines.append("Settled cash by currency: " + json.dumps(report["settled_cash_by_currency"], sort_keys=True))
            if "expected_unconfirmed_usd" in item:
                lines.append("Actual unconfirmed USD total: " + report["totals_by_instrument"]["USD"]["accepted_unconfirmed"])
        lines += [f"Same outcome at precision 3/28/80: {item['context_invariant']}; expected behavior: {item['passed']}", ""]
    lines += [f"All twelve scenarios passed: {payload['all_passed']}", f"Rehearsal receipt: {payload['rehearsal_receipt_sha256']}", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="include exact fictional inputs and real compiler outputs")
    args = parser.parse_args(argv)
    payload = run()
    print(json.dumps(payload, sort_keys=True, indent=2) if args.json else markdown(payload), end="\n")
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
