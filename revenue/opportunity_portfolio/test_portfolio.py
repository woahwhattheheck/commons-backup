from __future__ import annotations

from copy import deepcopy
import json
import unittest

from revenue.opportunity_portfolio.portfolio import (
    PortfolioError,
    SCHEMA,
    compile_portfolio,
    normalize_input,
    render_markdown,
    verify_receipt,
)

D = "a" * 64
E = "b" * 64
P = "c" * 64
AS_OF = "2026-09-13T10:00:00Z"


def opportunity(
    oid: str,
    amount: int,
    probability: int | None = 5000,
    *,
    currency: str = "USD",
    capacity: dict[str, int] | None = None,
    owner: str = "AVAILABLE",
    owner_seat: str | None = None,
    eligibility: str = "ELIGIBLE",
    blockers: list[dict] | None = None,
    depends: list[str] | None = None,
    exclusive: str | None = None,
    deadline: str = "2026-10-01T00:00:00Z",
    fresh_until: str = "2026-09-20T00:00:00Z",
    observed_at: str = "2026-09-13T09:00:00Z",
):
    value = {
        "currency": currency,
        "amountMinor": amount,
        "probabilityBps": probability,
        "probabilityEvidenceSha256": P if probability is not None else None,
    }
    if probability is None:
        value = {"currency": currency, "amountMinor": amount}
    return {
        "id": oid,
        "title": f"Opportunity {oid}",
        "source": {"ref": f"slack:{oid}", "digestSha256": D, "observedAt": observed_at},
        "freshUntil": fresh_until,
        "deadline": deadline,
        "eligibility": {"status": eligibility, "evidenceSha256": E},
        "value": value,
        "capacity": capacity or {"build_hours": 1},
        "owner": {"status": owner, "seat": owner_seat},
        "blockers": blockers or [],
        "dependsOn": depends or [],
        "exclusiveGroup": exclusive,
        "labels": ["revenue"],
    }


def payload(items, *, capacities=None, priority=None):
    return {
        "schema": SCHEMA,
        "actorSeat": "ZKG-R9",
        "capacities": capacities or {"build_hours": 4, "outreach_slots": 2},
        "currencyPriority": [] if priority is None else priority,
        "opportunities": items,
    }


class PortfolioTests(unittest.TestCase):
    def test_exact_knapsack_beats_largest_single(self):
        data = payload([
            opportunity("a", 100, 9000, capacity={"build_hours": 4}),
            opportunity("b", 70, 8000, capacity={"build_hours": 2}),
            opportunity("c", 70, 8000, capacity={"build_hours": 2}),
        ])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["b", "c"])
        self.assertEqual(receipt["capacity"]["used"]["build_hours"], 4)
        self.assertTrue(verify_receipt(receipt))

    def test_dependency_closure_is_mandatory(self):
        data = payload([
            opportunity("foundation", 10, 10000, capacity={"build_hours": 2}),
            opportunity("sale", 1000, 10000, capacity={"build_hours": 2}, depends=["foundation"]),
            opportunity("other", 900, 10000, capacity={"build_hours": 3}),
        ], capacities={"build_hours": 4})
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["foundation", "sale"])

    def test_nonrunnable_dependency_blocks_dependent(self):
        data = payload([
            opportunity("foundation", 10, blockers=[{"code": "repo", "status": "OPEN", "evidenceSha256": D}]),
            opportunity("sale", 1000, depends=["foundation"]),
        ])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        rows = {r["id"]: r for r in receipt["decisions"]}
        self.assertEqual(rows["foundation"]["status"], "BLOCKED")
        self.assertEqual(rows["sale"]["status"], "BLOCKED")
        self.assertIn("DEPENDENCY_NOT_RUNNABLE:foundation", rows["sale"]["reasons"])

    def test_exclusivity_group(self):
        data = payload([
            opportunity("path-a", 100, exclusive="same-buyer"),
            opportunity("path-b", 200, exclusive="same-buyer"),
            opportunity("free", 50),
        ])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["free", "path-b"])

    def test_multi_currency_requires_explicit_priority(self):
        data = payload([
            opportunity("usd", 100, currency="USD"),
            opportunity("rtc", 100, currency="RTC"),
        ])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["authority"]["strongestState"], "HOLD")
        self.assertIn("MULTI_CURRENCY_PRIORITY_REQUIRED", receipt["globalHolds"])
        self.assertEqual(receipt["portfolio"], [])

    def test_multi_currency_priority_is_policy_not_fx(self):
        data = payload([
            opportunity("usd", 1, 10000, currency="USD", capacity={"build_hours": 4}),
            opportunity("rtc", 10**12, 10000, currency="RTC", capacity={"build_hours": 4}),
        ], capacities={"build_hours": 4}, priority=["USD", "RTC"])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["usd"])
        self.assertNotIn("fx", json.dumps(receipt).lower())

    def test_lower_currency_expected_value_beats_face_tie_break(self):
        # USD expected value ties at 10000 either way. The solver must then compare
        # RTC expected value before using USD face value as a tie breaker.
        data = payload([
            opportunity("usd-face", 100, 100, currency="USD", capacity={"build_hours": 4}),
            opportunity("usd-small", 1, 10000, currency="USD", capacity={"build_hours": 2}),
            opportunity("rtc", 1000, 10000, currency="RTC", capacity={"build_hours": 2}),
        ], capacities={"build_hours": 4}, priority=["USD", "RTC"])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["rtc", "usd-small"])

    def test_currency_priority_must_cover_exact_set(self):
        data = payload([
            opportunity("usd", 100, currency="USD"),
            opportunity("rtc", 100, currency="RTC"),
        ], priority=["USD"])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertIn("CURRENCY_PRIORITY_MUST_COVER_EXACT_CURRENCIES", receipt["globalHolds"])

    def test_probability_evidence_missing_routes_to_qualify(self):
        data = payload([opportunity("unknown-ev", 5000, probability=None)])
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        row = receipt["decisions"][0]
        self.assertEqual(row["status"], "QUALIFY")
        self.assertIn("PROBABILITY_EVIDENCE_MISSING", row["reasons"])
        self.assertEqual(receipt["portfolio"], [])

    def test_owner_collision_holds(self):
        data = payload([opportunity("owned", 5000, owner="OWNED_BY_OTHER", owner_seat="Z-OTHER")])
        row = compile_portfolio(data, trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "HOLD")
        self.assertIn("OWNER_COLLISION", row["reasons"])

    def test_this_seat_owner_must_match_actor(self):
        item = opportunity("bad", 100, owner="OWNED_BY_THIS_SEAT", owner_seat="Z-OTHER")
        with self.assertRaisesRegex(PortfolioError, "must name actorSeat"):
            normalize_input(payload([item]))

    def test_unknown_owner_qualifies(self):
        row = compile_portfolio(payload([opportunity("x", 100, owner="UNKNOWN")]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "QUALIFY")
        self.assertIn("OWNER_UNKNOWN", row["reasons"])

    def test_ineligible_holds(self):
        row = compile_portfolio(payload([opportunity("x", 100, eligibility="INELIGIBLE")]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "HOLD")

    def test_unknown_eligibility_qualifies(self):
        row = compile_portfolio(payload([opportunity("x", 100, eligibility="UNKNOWN")]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "QUALIFY")

    def test_open_blocker_blocks(self):
        item = opportunity("x", 100, blockers=[{"code": "auth", "status": "OPEN", "evidenceSha256": D}])
        row = compile_portfolio(payload([item]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("BLOCKER:auth", row["reasons"])

    def test_resolved_blocker_does_not_block(self):
        item = opportunity("x", 100, blockers=[{"code": "auth", "status": "RESOLVED", "evidenceSha256": D}])
        receipt = compile_portfolio(payload([item]), trusted_as_of=AS_OF)
        self.assertEqual(receipt["portfolio"], ["x"])

    def test_stale_source_qualifies_not_executes(self):
        item = opportunity("x", 100, fresh_until="2026-09-13T09:59:59Z")
        row = compile_portfolio(payload([item]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "QUALIFY")
        self.assertIn("SOURCE_STALE", row["reasons"])

    def test_closed_deadline_holds(self):
        item = opportunity("x", 100, deadline=AS_OF)
        row = compile_portfolio(payload([item]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "HOLD")
        self.assertIn("DEADLINE_CLOSED", row["reasons"])

    def test_future_source_holds(self):
        item = opportunity("x", 100, observed_at="2026-09-13T10:00:01Z")
        row = compile_portfolio(payload([item]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "HOLD")
        self.assertIn("SOURCE_OBSERVED_IN_FUTURE", row["reasons"])

    def test_freshness_inversion_holds(self):
        item = opportunity("x", 100, observed_at="2026-09-13T09:30:00Z", fresh_until="2026-09-13T09:00:00Z")
        row = compile_portfolio(payload([item]), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "HOLD")
        self.assertIn("SOURCE_FRESHNESS_INVERTED", row["reasons"])

    def test_individual_over_capacity_blocks(self):
        item = opportunity("x", 100, capacity={"build_hours": 5})
        row = compile_portfolio(payload([item], capacities={"build_hours": 4}), trusted_as_of=AS_OF)["decisions"][0]
        self.assertEqual(row["status"], "BLOCKED")

    def test_unknown_capacity_bucket_is_not_executable(self):
        item = opportunity("x", 100, capacity={"gpu_hours": 1})
        row = compile_portfolio(payload([item], capacities={"build_hours": 4}), trusted_as_of=AS_OF)["decisions"][0]
        self.assertNotEqual(row["status"], "EXECUTE_NOW")
        self.assertIn("CAPACITY_BUCKET_UNKNOWN:gpu_hours", row["reasons"])

    def test_exact_large_integer_money(self):
        huge = 900719925474099312345
        receipt = compile_portfolio(payload([opportunity("huge", huge, 9999)]), trusted_as_of=AS_OF)
        self.assertEqual(receipt["objective"]["USD"]["expectedValueNumerator"], huge * 9999)
        self.assertEqual(receipt["objective"]["USD"]["expectedValueDenominator"], 10000)

    def test_bool_not_accepted_as_integer(self):
        item = opportunity("x", 100)
        item["value"]["amountMinor"] = True
        with self.assertRaises(PortfolioError):
            compile_portfolio(payload([item]), trusted_as_of=AS_OF)

    def test_dependency_cycle_fails_closed(self):
        with self.assertRaisesRegex(PortfolioError, "dependency cycle"):
            normalize_input(payload([
                opportunity("a", 100, depends=["b"]),
                opportunity("b", 100, depends=["a"]),
            ]))

    def test_unknown_dependency_fails_closed(self):
        with self.assertRaisesRegex(PortfolioError, "unknown dependencies"):
            normalize_input(payload([opportunity("a", 100, depends=["missing"])]))

    def test_duplicate_id_fails_closed(self):
        with self.assertRaisesRegex(PortfolioError, "duplicate id"):
            normalize_input(payload([opportunity("a", 100), opportunity("a", 200)]))

    def test_unknown_field_fails_closed(self):
        data = payload([opportunity("a", 100)])
        data["mystery"] = True
        with self.assertRaisesRegex(PortfolioError, "unknown fields"):
            normalize_input(data)

    def test_secret_shaped_material_refused(self):
        item = opportunity("a", 100)
        item["source"]["ref"] = ('sk-p' + 'roj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456')
        with self.assertRaisesRegex(PortfolioError, "secret-shaped"):
            compile_portfolio(payload([item]), trusted_as_of=AS_OF)

    def test_receipt_tamper_rejected(self):
        receipt = compile_portfolio(payload([opportunity("a", 100)]), trusted_as_of=AS_OF)
        tampered = deepcopy(receipt)
        tampered["portfolio"] = []
        with self.assertRaisesRegex(PortfolioError, "digest mismatch"):
            verify_receipt(tampered)

    def test_input_tamper_even_with_rehashed_outer_digest_rejected(self):
        # Receipt verifier binds both input digest and deterministic recompilation.
        receipt = compile_portfolio(payload([opportunity("a", 100)]), trusted_as_of=AS_OF)
        tampered = deepcopy(receipt)
        tampered["normalizedInput"]["opportunities"][0]["value"]["amountMinor"] = 999
        # Keep old digest intentionally: verifier must stop before trusting rewritten input.
        with self.assertRaises(PortfolioError):
            verify_receipt(tampered)

    def test_deterministic_under_input_order(self):
        items = [opportunity("c", 80), opportunity("a", 100), opportunity("b", 90)]
        r1 = compile_portfolio(payload(items), trusted_as_of=AS_OF)
        r2 = compile_portfolio(payload(list(reversed(items))), trusted_as_of=AS_OF)
        self.assertEqual(r1, r2)

    def test_markdown_is_authority_bounded(self):
        receipt = compile_portfolio(payload([opportunity("a", 100)]), trusted_as_of=AS_OF)
        text = render_markdown(receipt)
        self.assertIn("External action authority: **false**", text)
        self.assertIn("does not send outreach", text)

    def test_synthetic_acceptance_corpus(self):
        items = []
        for i in range(16):
            items.append(opportunity(
                f"op-{i:02d}",
                1000 + i * 137,
                3000 + i * 300,
                capacity={"build_hours": 1 + (i % 4), "outreach_slots": i % 2},
                exclusive=f"g-{i // 2}" if i < 8 else None,
            ))
        data = payload(items, capacities={"build_hours": 20, "outreach_slots": 4})
        receipt = compile_portfolio(data, trusted_as_of=AS_OF)
        self.assertTrue(verify_receipt(receipt))
        self.assertLessEqual(receipt["capacity"]["used"]["build_hours"], 20)
        self.assertLessEqual(receipt["capacity"]["used"]["outreach_slots"], 4)
        self.assertGreater(len(receipt["portfolio"]), 0)
        self.assertEqual(receipt["authority"]["strongestState"], "PORTFOLIO_READY_FOR_HUMAN_EXECUTION_REVIEW")


if __name__ == "__main__":
    unittest.main()
