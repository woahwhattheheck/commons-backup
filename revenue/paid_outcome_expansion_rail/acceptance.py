"""Deterministic synthetic acceptance for the paid-outcome expansion rail."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .rail import canonical_json, catalog_row_digest, digest_json, evaluate, verify_receipt

AS_OF = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
SCOPE = digest_json({"scope": "synthetic-paid-proof-v1"})
EXP_SCOPE = digest_json({"scope": "synthetic-expansion-v1"})
REN_SCOPE = digest_json({"scope": "synthetic-renewal-v1"})
METRIC_DEF = digest_json({"metric": "cycle_time_hours", "version": 1})


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_record(index: int, kind: str = "EXPANSION_REQUEST") -> dict[str, Any]:
    if kind not in {"EXPANSION_REQUEST", "RENEWAL_REQUEST"}:
        raise ValueError("unsupported kind")
    account = f"acct-{index:03d}"
    offer = f"offer-{index:03d}"
    catalog_id = f"catalog-{index:03d}"
    catalog_kind = "EXPANSION" if kind == "EXPANSION_REQUEST" else "RENEWAL"
    row_scope = EXP_SCOPE if catalog_kind == "EXPANSION" else REN_SCOPE
    issued = AS_OF - timedelta(days=40)
    settled = AS_OF - timedelta(days=25)
    accepted = AS_OF - timedelta(days=20)
    signal = AS_OF - timedelta(days=10)
    catalog_row = {
        "catalog_id": catalog_id,
        "version": "v1",
        "kind": catalog_kind,
        "currency": "USD",
        "price_cents": 50000 + index,
        "scope_digest": row_scope,
        "active_from": _ts(AS_OF - timedelta(days=30)),
        "active_until": _ts(AS_OF + timedelta(days=90)),
    }
    approved_row = {
        "catalog_id": catalog_id,
        "version": catalog_row["version"],
        "row_digest": catalog_row_digest(catalog_row),
    }
    return {
        "schema_version": "1",
        "account_id": account,
        "as_of": _ts(AS_OF),
        "offer": {
            "offer_id": offer,
            "version": "v1",
            "currency": "USD",
            "expected_cents": 100,
            "scope_digest": SCOPE,
            "issued_at": _ts(issued),
            "expires_at": _ts(AS_OF + timedelta(days=60)),
        },
        "settlement": {
            "evidence_id": f"settlement-{index:03d}",
            "account_id": account,
            "offer_id": offer,
            "offer_version": "v1",
            "currency": "USD",
            "net_cents": 100,
            "refunded_cents": 0,
            "disputed_cents": 0,
            "status": "SETTLED",
            "settled_at": _ts(settled),
            "captured_at": _ts(settled + timedelta(hours=1)),
        },
        "delivery_acceptance": {
            "evidence_id": f"acceptance-{index:03d}",
            "account_id": account,
            "offer_id": offer,
            "offer_version": "v1",
            "scope_digest": SCOPE,
            "status": "ACCEPTED",
            "accepted_by_class": "BUYER_HUMAN",
            "accepted_at": _ts(accepted),
        },
        "buyer_signal": {
            "evidence_id": f"signal-{index:03d}",
            "account_id": account,
            "kind": kind,
            "source_class": "BUYER_AUTHORED",
            "offer_id": offer,
            "observed_at": _ts(signal),
            "requested_catalog_ids": [catalog_id],
        },
        "owner_approval": {
            "evidence_id": f"approval-{index:03d}",
            "account_id": account,
            "approver_class": "OWNER_HUMAN",
            "approved_at": _ts(signal + timedelta(hours=1)),
            "approved_catalog_rows": [approved_row],
        },
        "catalog": [catalog_row],
        "outcomes": [{
            "metric_id": "cycle_time_hours",
            "definition_digest": METRIC_DEF,
            "unit": "hours",
            "baseline_value": "12.0",
            "observed_value": "8.0",
            "baseline_start": _ts(AS_OF - timedelta(days=35)),
            "baseline_end": _ts(AS_OF - timedelta(days=30)),
            "observed_start": _ts(AS_OF - timedelta(days=15)),
            "observed_end": _ts(AS_OF - timedelta(days=11)),
            "claim_class": "DESCRIPTIVE",
            "causal_claim": False,
            "source_evidence_ids": [f"metric-source-{index:03d}"],
        }],
        "event_log": [
            {"event_id": f"{account}:paid", "payload": {"status": "settled", "cents": 100}},
            {"event_id": f"{account}:accepted", "payload": {"status": "accepted"}},
            {"event_id": f"{account}:accepted", "payload": {"status": "accepted"}},
        ],
    }


def synthetic_suite() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(72):
        records.append(make_record(idx, "EXPANSION_REQUEST" if idx < 36 else "RENEWAL_REQUEST"))
    for idx in range(72, 80):
        r = make_record(idx); r["settlement"]["status"] = "PENDING"; records.append(r)
    for idx in range(80, 88):
        r = make_record(idx); r["settlement"]["refunded_cents"] = 1; records.append(r)
    for idx in range(88, 96):
        r = make_record(idx); r["delivery_acceptance"]["scope_digest"] = digest_json({"wrong": idx}); records.append(r)
    for idx in range(96, 104):
        r = make_record(idx)
        # Keep every other authority valid while isolating the stale-signal fence.
        r["offer"]["issued_at"] = _ts(AS_OF - timedelta(days=100))
        r["settlement"]["settled_at"] = _ts(AS_OF - timedelta(days=60))
        r["settlement"]["captured_at"] = _ts(AS_OF - timedelta(days=60) + timedelta(hours=1))
        r["delivery_acceptance"]["accepted_at"] = _ts(AS_OF - timedelta(days=50))
        r["buyer_signal"]["observed_at"] = _ts(AS_OF - timedelta(days=46))
        # The selected revision must already be active so this row isolates only
        # signal freshness. Rebind the approval to the adjusted exact row.
        r["catalog"][0]["active_from"] = _ts(AS_OF - timedelta(days=70))
        r["owner_approval"]["approved_catalog_rows"][0]["row_digest"] = catalog_row_digest(r["catalog"][0])
        records.append(r)
    for idx in range(104, 112):
        r = make_record(idx); r["outcomes"][0]["causal_claim"] = True; records.append(r)
    for idx in range(112, 120):
        r = make_record(idx); r["owner_approval"]["approved_catalog_rows"] = []; records.append(r)
    return records


def build_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    receipts = [evaluate(r) for r in records]
    if not all(verify_receipt(r) for r in receipts):
        raise ValueError("receipt verification failed")
    receipts.sort(key=lambda r: (r["account_id"], r["receipt_digest"]))
    decisions = Counter(r["decision"] for r in receipts)
    holds = Counter(code for r in receipts for code in r["hold_codes"])
    body = {
        "manifest_version": "1",
        "records": len(receipts),
        "decisions": dict(sorted(decisions.items())),
        "hold_codes": dict(sorted(holds.items())),
        "receipt_digests": [r["receipt_digest"] for r in receipts],
    }
    body["manifest_digest"] = digest_json(body)
    return body


def run_acceptance() -> dict[str, Any]:
    records = synthetic_suite()
    manifest = build_manifest(records)
    reverse_manifest = build_manifest(list(reversed(records)))
    expected_decisions = {"EXPANSION_READY": 36, "HOLD": 48, "RENEWAL_READY": 36}
    if manifest["decisions"] != expected_decisions:
        raise ValueError(f"decision counts differ: {manifest['decisions']}")
    expected_holds = {
        "ACCEPTANCE_SCOPE_MISMATCH": 8,
        "BUYER_SIGNAL_STALE": 8,
        "CATALOG_NOT_OWNER_APPROVED": 8,
        "CAUSAL_OUTCOME_CLAIM_FORBIDDEN": 8,
        "SETTLEMENT_NOT_FINAL": 8,
        "SETTLEMENT_REFUNDED": 8,
    }
    if manifest["hold_codes"] != expected_holds:
        raise ValueError(f"hold counts differ: {manifest['hold_codes']}")
    if manifest != reverse_manifest:
        raise ValueError("order invariance failed")
    result = dict(manifest)
    result["order_invariant"] = True
    result["all_receipts_verified"] = True
    return result


if __name__ == "__main__":
    print(canonical_json(run_acceptance()))
