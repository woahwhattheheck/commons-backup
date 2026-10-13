from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.revenue_proof_ledger.ledger import (
    INPUT_SCHEMA,
    InputError,
    inventory_digest,
    main,
    reduce_ledger,
    render_summary,
)

OID = "github:acme/widget#42"
DID = "github:acme/widget@abc"
OBSERVED = "2026-09-13T07:30:00Z"


def dg(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def opportunity(source: str, *, amount="500.00", authority="complete", digest=None):
    return {
        "kind": "opportunity",
        "opportunity_id": OID,
        "source": source,
        "authority": authority,
        "evidence_digest": digest or dg("opportunity-" + source),
        "currency": "USD",
        "expected_amount": amount,
        "identity_status": "canonical",
    }


def lookup(
    scope: str,
    *,
    authority="complete",
    digest=None,
    snapshot_id=None,
    observed_at=OBSERVED,
    inventory_ids=None,
):
    snapshot_id = snapshot_id or f"{scope}-snapshot"
    row = {
        "kind": "lookup",
        "opportunity_id": OID,
        "source": "reader:" + scope,
        "authority": authority,
        "evidence_digest": digest or dg(f"lookup-{scope}-{authority}-{snapshot_id}"),
        "scope": scope,
        "snapshot_id": snapshot_id,
        "observed_at": observed_at,
    }
    if inventory_ids is not None:
        row["inventory_ids"] = sorted(inventory_ids)
        row["inventory_digest"] = inventory_digest(
            scope, snapshot_id, observed_at, row["inventory_ids"]
        )
    return row


def delivery(*, current=True, state="accepted", amount="500", delivery_id=DID, authority="complete"):
    value = {
        "kind": "delivery",
        "opportunity_id": OID,
        "delivery_id": delivery_id,
        "source": "github:pull/99",
        "authority": authority,
        "evidence_digest": dg("delivery-" + delivery_id + state + str(current)),
        "state": state,
        "current": current,
        "currency": "USD",
        "credit": {
            "source_authors": ["Builder-A"],
            "reviewers": ["Reviewer-B"],
            "mergers": ["Merger-C"],
        },
    }
    if state == "accepted":
        value["earned_amount"] = amount
    return value


def settlement(
    settlement_id: str,
    amount: str,
    *,
    movement="payment",
    state="settled",
    delivery_id=DID,
    source="payment:stripe",
    authority="complete",
):
    return {
        "kind": "settlement",
        "opportunity_id": OID,
        "delivery_id": delivery_id,
        "settlement_id": settlement_id,
        "source": source,
        "authority": authority,
        "evidence_digest": dg(source + settlement_id + movement + amount),
        "movement": movement,
        "state": state,
        "currency": "USD",
        "amount": amount,
    }


def payload(*rows):
    """Build a coherent packet; lookup rows omitted inventory auto-bind to packet ids."""
    values = copy.deepcopy(list(rows))
    deliveries_by_oid = {}
    settlements_by_oid = {}
    for item in values:
        if item.get("kind") == "delivery":
            deliveries_by_oid.setdefault(item["opportunity_id"], set()).add(item["delivery_id"])
        elif item.get("kind") == "settlement":
            settlements_by_oid.setdefault(item["opportunity_id"], set()).add(item["settlement_id"])
    for item in values:
        if item.get("kind") != "lookup" or "inventory_ids" in item:
            continue
        ids = sorted(
            deliveries_by_oid.get(item["opportunity_id"], set())
            if item["scope"] == "delivery"
            else settlements_by_oid.get(item["opportunity_id"], set())
        )
        item["inventory_ids"] = ids
        item["inventory_digest"] = inventory_digest(
            item["scope"], item["snapshot_id"], item["observed_at"], ids
        )
    return {"schema": INPUT_SCHEMA, "receipts": values}


def row(ledger):
    return ledger["opportunities"][0]


class RevenueProofLedgerTests(unittest.TestCase):
    def test_cross_source_opportunity_dedupes_once(self):
        ledger = reduce_ledger(
            payload(
                opportunity("slack:thread"),
                opportunity("github:issue"),
                delivery(),
                lookup("delivery"),
                lookup("settlement"),
            )
        )
        proof = row(ledger)
        self.assertEqual(len(ledger["opportunities"]), 1)
        self.assertEqual(proof["pipeline_expected"], "500")
        self.assertEqual(proof["earned_unsettled"], "500")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertEqual(proof["authority"], "complete")

    def test_accepted_without_payment_is_earned_unsettled_only(self):
        proof = row(
            reduce_ledger(
                payload(opportunity("github"), delivery(), lookup("delivery"), lookup("settlement"))
            )
        )
        self.assertEqual(proof["earned_unsettled"], "500")
        self.assertEqual(proof["cash_settled"], "0")

    def test_duplicate_identical_settlement_id_counts_once(self):
        first = settlement("stripe:pi_1", "500", source="payment:a")
        duplicate = settlement("stripe:pi_1", "500", source="payment:b")
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    first,
                    duplicate,
                )
            )
        )
        self.assertEqual(proof["cash_settled"], "500")
        self.assertEqual(proof["settlement_ids"], ["stripe:pi_1"])

    def test_partial_multi_payment_remains_partial_cash(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement("stripe:pi_a", "125.25"),
                    settlement("stripe:pi_b", "74.75"),
                )
            )
        )
        self.assertEqual(proof["cash_settled"], "200")
        self.assertEqual(proof["earned_unsettled"], "300")

    def test_refund_backs_cash_out_without_erasing_delivery(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement("stripe:pi_1", "500"),
                    settlement("stripe:re_1", "125", movement="refund"),
                )
            )
        )
        self.assertEqual(proof["cash_settled"], "375")
        self.assertEqual(proof["reversed_or_disputed"], "125")
        self.assertEqual(proof["earned_unsettled"], "125")
        self.assertEqual(proof["delivery_id"], DID)

    def test_unknown_payment_lookup_mints_zero_cash(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement", authority="unknown"),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertEqual(proof["observed_net_cash"], "500")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertEqual(proof["earned_unsettled"], "500")

    def test_missing_payment_lookup_is_unknown_and_zero_cash(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("settlement_lookup_missing", proof["issues"])
        self.assertEqual(proof["cash_settled"], "0")

    def test_lookup_inventory_omitting_refund_fails_closed(self):
        packet = payload(
            opportunity("github"),
            delivery(),
            lookup("delivery"),
            lookup("settlement"),
            settlement("stripe:pi_1", "500"),
            settlement("stripe:re_1", "125", movement="refund"),
        )
        lookup_row = next(
            item
            for item in packet["receipts"]
            if item["kind"] == "lookup" and item["scope"] == "settlement"
        )
        lookup_row["inventory_ids"] = ["stripe:pi_1"]
        lookup_row["inventory_digest"] = inventory_digest(
            "settlement",
            lookup_row["snapshot_id"],
            lookup_row["observed_at"],
            lookup_row["inventory_ids"],
        )
        proof = row(reduce_ledger(packet))
        self.assertEqual(proof["authority"], "unknown")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertIn("settlement_lookup_inventory_mismatch", proof["issues"])

    def test_lookup_listing_missing_refund_receipt_fails_closed(self):
        packet = payload(
            opportunity("github"),
            delivery(),
            lookup("delivery"),
            lookup("settlement"),
            settlement("stripe:pi_1", "500"),
        )
        lookup_row = next(
            item
            for item in packet["receipts"]
            if item["kind"] == "lookup" and item["scope"] == "settlement"
        )
        lookup_row["inventory_ids"] = ["stripe:pi_1", "stripe:re_1"]
        lookup_row["inventory_digest"] = inventory_digest(
            "settlement",
            lookup_row["snapshot_id"],
            lookup_row["observed_at"],
            lookup_row["inventory_ids"],
        )
        proof = row(reduce_ledger(packet))
        self.assertEqual(proof["authority"], "unknown")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertIn("settlement_lookup_inventory_mismatch", proof["issues"])

    def test_delivery_inventory_mismatch_fails_closed(self):
        packet = payload(
            opportunity("github"),
            delivery(),
            lookup("delivery", inventory_ids=[]),
            lookup("settlement"),
        )
        proof = row(reduce_ledger(packet))
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("delivery_lookup_inventory_mismatch", proof["issues"])

    def test_newer_complete_lookup_supersedes_older_partial_snapshot(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup(
                        "settlement",
                        authority="partial",
                        observed_at="2026-09-13T07:00:00Z",
                        snapshot_id="old",
                    ),
                    lookup(
                        "settlement",
                        authority="complete",
                        observed_at=OBSERVED,
                        snapshot_id="new",
                    ),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "complete")
        self.assertEqual(proof["cash_settled"], "500")
        self.assertEqual(proof["lookup_snapshots"]["settlement"]["snapshot_id"], "new")

    def test_newer_partial_lookup_overrides_older_complete_snapshot(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup(
                        "settlement",
                        authority="complete",
                        observed_at="2026-09-13T07:00:00Z",
                        snapshot_id="old",
                    ),
                    lookup(
                        "settlement",
                        authority="partial",
                        observed_at=OBSERVED,
                        snapshot_id="new",
                    ),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "partial")
        self.assertEqual(proof["cash_settled"], "0")

    def test_conflicting_latest_lookup_snapshots_fail_closed(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement", snapshot_id="a"),
                    lookup("settlement", snapshot_id="b"),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertEqual(proof["cash_settled"], "0")
        self.assertIn("settlement_lookup_snapshot_conflict", proof["issues"])

    def test_lookup_inventory_digest_tamper_rejected(self):
        packet = payload(
            opportunity("github"),
            delivery(),
            lookup("delivery"),
            lookup("settlement"),
            settlement("stripe:pi_1", "500"),
        )
        target = next(
            item
            for item in packet["receipts"]
            if item["kind"] == "lookup" and item["scope"] == "settlement"
        )
        target["inventory_digest"] = dg("wrong")
        with self.assertRaisesRegex(InputError, "inventory_digest mismatch"):
            reduce_ledger(packet)

    def test_lookup_duplicate_inventory_id_rejected(self):
        item = lookup("settlement", inventory_ids=["stripe:pi_1"])
        item["inventory_ids"] = ["stripe:pi_1", "stripe:pi_1"]
        item["inventory_digest"] = inventory_digest(
            "settlement", item["snapshot_id"], item["observed_at"], item["inventory_ids"]
        )
        with self.assertRaisesRegex(InputError, "must not contain duplicates"):
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    item,
                    settlement("stripe:pi_1", "500"),
                )
            )

    def test_lookup_timestamp_is_normalized_and_exposed(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery", observed_at="2026-09-13T03:30:00-04:00"),
                    lookup("settlement", observed_at="2026-09-13T03:30:00-04:00"),
                )
            )
        )
        self.assertEqual(
            proof["lookup_snapshots"]["delivery"]["observed_at"],
            "2026-09-13T07:30:00Z",
        )

    def test_credit_lineage_does_not_remint_source_authorship(self):
        duplicate = delivery()
        duplicate["source"] = "github:merge"
        duplicate["evidence_digest"] = dg("delivery-second-source")
        duplicate["credit"] = {
            "source_authors": ["Builder-A"],
            "reviewers": ["Reviewer-B", "Reviewer-D"],
            "mergers": ["Merger-C", "Merger-E"],
        }
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    duplicate,
                    lookup("delivery"),
                    lookup("settlement"),
                )
            )
        )
        credit = proof["credit_lineage"]
        self.assertEqual(credit["source_authors"], ["Builder-A"])
        self.assertEqual(credit["reviewers"], ["Reviewer-B", "Reviewer-D"])
        self.assertEqual(credit["mergers"], ["Merger-C", "Merger-E"])

    def test_reused_settlement_identity_fails_closed(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement("stripe:pi_1", "500"),
                    settlement("stripe:pi_1", "400"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("settlement_id_reused:stripe:pi_1", proof["issues"])
        self.assertEqual(proof["cash_settled"], "0")

    def test_settlement_on_superseded_delivery_fails_closed(self):
        old = delivery(current=False, delivery_id="github:acme/widget@old")
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("github"),
                    old,
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement(
                        "stripe:pi_old", "500", delivery_id="github:acme/widget@old"
                    ),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("settlement_on_noncurrent_delivery:stripe:pi_old", proof["issues"])
        self.assertEqual(proof["cash_settled"], "0")

    def test_ambiguous_opportunity_identity_fails_closed(self):
        ambiguous = opportunity("slack")
        ambiguous["identity_status"] = "ambiguous"
        proof = row(
            reduce_ledger(
                payload(
                    ambiguous,
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("opportunity_identity_ambiguous", proof["issues"])
        self.assertEqual(proof["cash_settled"], "0")

    def test_unknown_receipt_field_is_rejected(self):
        bad = opportunity("github")
        bad["curreny"] = "USD"
        with self.assertRaisesRegex(InputError, "unknown fields: curreny"):
            reduce_ledger(payload(bad))

    def test_amount_mismatch_between_discovery_sources_fails_closed(self):
        proof = row(
            reduce_ledger(
                payload(
                    opportunity("slack", amount="500"),
                    opportunity("github", amount="450"),
                    delivery(),
                    lookup("delivery"),
                    lookup("settlement"),
                    settlement("stripe:pi_1", "500"),
                )
            )
        )
        self.assertEqual(proof["authority"], "unknown")
        self.assertIn("opportunity_amount_mismatch", proof["issues"])
        self.assertEqual(proof["pipeline_expected"], "0")
        self.assertEqual(proof["cash_settled"], "0")

    def test_permutation_is_deterministic(self):
        receipts = [
            opportunity("slack"),
            opportunity("github"),
            delivery(),
            lookup("delivery"),
            lookup("settlement"),
            settlement("stripe:pi_a", "200"),
        ]
        left = reduce_ledger(payload(*receipts))
        right = reduce_ledger(payload(*reversed(receipts)))
        self.assertEqual(left, right)
        self.assertEqual(render_summary(left), render_summary(right))

    def test_cli_outputs_are_create_exclusive(self):
        source = payload(
            opportunity("github"), delivery(), lookup("delivery"), lookup("settlement")
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            src = root / "input.json"
            out = root / "ledger.json"
            summary = root / "ledger.md"
            src.write_text(json.dumps(source), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        str(src),
                        "--json-out",
                        str(out),
                        "--summary-out",
                        str(summary),
                    ]
                ),
                0,
            )
            before_json = out.read_bytes()
            before_summary = summary.read_bytes()
            with self.assertRaises(SystemExit) as caught:
                main(
                    [
                        str(src),
                        "--json-out",
                        str(out),
                        "--summary-out",
                        str(summary),
                    ]
                )
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(out.read_bytes(), before_json)
            self.assertEqual(summary.read_bytes(), before_summary)

    def test_ledger_digest_is_bound_to_content(self):
        ledger = reduce_ledger(
            payload(opportunity("github"), delivery(), lookup("delivery"), lookup("settlement"))
        )
        clone = copy.deepcopy(ledger)
        digest = clone.pop("ledger_digest")
        canonical = json.dumps(
            clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        self.assertEqual(digest, "sha256:" + hashlib.sha256(canonical).hexdigest())


if __name__ == "__main__":
    unittest.main()
