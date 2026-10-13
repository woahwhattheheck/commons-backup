"""Deterministic contract tests; engine differential tests live in validate_engine.py."""
import unittest
from livestock_ledger import ServiceAction as A, project_calendar, compare_species, purchase_checkpoint


def daily_feed_care(last_day=28):
    return [event for day in range(last_day + 1) for event in
            (A(day * 24, "FEED", wheat_available=1), A(day * 24 + 1, "CARE"))]


class LivestockLedgerTests(unittest.TestCase):
    def test_maturity_and_current_care_order(self):
        r = project_calendar("COW", 0, daily_feed_care(7), last_action_step=192)
        first = r["production_events"][0]
        self.assertEqual((first["step"], first["available_step"], first["care_units"]), (191, 192, 7))
        self.assertEqual((r["terminal_held_units"], r["lost_to_cap"]), (6, 2))
        self.assertEqual(r["terminal_tile"]["pending_care_bonus"], 1)

    def test_sheep_produces_earlier_not_at_same_interval(self):
        r = compare_species(0, daily_feed_care(11), last_action_step=288)
        self.assertEqual([p["available_step"] for p in r["baseline"]["production_events"]], [192, 240, 288])
        self.assertEqual([p["available_step"] for p in r["candidate"]["production_events"]], [144, 216, 288])
        self.assertEqual(r["candidate_minus_baseline"]["purchase_cost"], 100)
        self.assertIsNone(r["candidate_minus_baseline"]["cash"])

    def test_unfed_production_retains_base_discards_old_bonus(self):
        events = daily_feed_care(6)  # Fed on day 6, unfed on first production day 7.
        r = project_calendar("COW", 0, events, last_action_step=192)
        self.assertEqual(r["harvested_units"], 0)
        self.assertEqual(r["terminal_held_units"], 1)
        self.assertEqual(r["discarded_care_bonus"], 7)
        self.assertEqual(r["terminal_tile"]["pending_care_bonus"], 0)

    def test_escape_precedes_production(self):
        events = daily_feed_care(5)  # Days 6 and 7 both unfed.
        r = project_calendar("COW", 0, events, last_action_step=192)
        self.assertEqual(r["escape_step"], 191)
        self.assertEqual(r["terminal_tile"], {"kind": "PASTURE"})
        self.assertEqual(r["production_events"], [])

    def test_multiple_workers_feed_once_and_harvest_in_order(self):
        events = daily_feed_care(8)
        events.extend([A(192, "FEED", unit=1, wheat_available=10),
                       A(192, "HARVEST", unit=2), A(192, "HARVEST", unit=3)])
        r = project_calendar("COW", 0, reversed(events), last_action_step=216)
        self.assertEqual(r["feed_units"], 9)
        self.assertEqual(r["harvest_receipts"], [{"step": 192, "unit": 2, "product": "MILK", "units": 6}])
        self.assertFalse([a for a in r["action_results"] if a["step"] == 192 and a["unit"] == 3][0]["applied"])

    def test_no_implicit_feed_from_shed(self):
        r = project_calendar("SHEEP", 0, [A(0, "FEED")], last_action_step=47)
        self.assertEqual(r["feed_units"], 0)
        self.assertEqual(r["escape_step"], 47)

    def test_final_unexecuted_boundary_not_credited(self):
        # Placed day 24: sheep first output would be at decision 719, which never runs.
        events = [A(day * 24 + 1, "FEED", wheat_available=1) for day in range(24, 30)]
        r = project_calendar("SHEEP", 576, events)
        self.assertEqual(r["last_action_step"], 718)
        self.assertEqual(r["production_events"], [])
        self.assertEqual(r["terminal_held_units"], 0)
        self.assertIsNone(r["cash_receipts"])
        with self.assertRaises(ValueError):
            project_calendar("SHEEP", 576, events, last_action_step=719)

    def test_harvest_before_boundary_cannot_take_later_output(self):
        events = daily_feed_care(7) + [A(191, "HARVEST"), A(192, "HARVEST")]
        r = project_calendar("COW", 0, events, last_action_step=192)
        self.assertEqual([x["step"] for x in r["harvest_receipts"]], [192])

    def test_fertilizer_not_available_until_refresh(self):
        r = project_calendar("COW", 0, [A(0, "COLLECT_FERTILIZER"), A(24, "COLLECT_FERTILIZER")], last_action_step=24)
        self.assertEqual(r["fertilizer_receipts"], [{"step": 24, "unit": 0, "units": 1}])

    def test_generator_reused_and_input_not_mutated(self):
        events = daily_feed_care(8)
        before = list(events)
        r = compare_species(0, (event for event in events), last_action_step=216)
        self.assertEqual(events, before)
        self.assertEqual(r["baseline"]["feed_receipts"], r["candidate"]["feed_receipts"])

    def test_cash_capacity_and_displaced_obligation(self):
        r = purchase_checkpoint(499, 99, reserve_after_buy=50)
        self.assertTrue(r["baseline"]["engine_purchase_possible"])
        self.assertFalse(r["candidate"]["engine_purchase_possible"])
        r = purchase_checkpoint(550, 99, reserve_after_buy=100)
        self.assertTrue(r["candidate"]["engine_purchase_possible"])
        self.assertFalse(r["candidate"]["preserves_cash_reserve"])
        self.assertTrue(r["baseline"]["preserves_cash_reserve"])
        self.assertFalse(purchase_checkpoint(1000, 100)["candidate"]["engine_purchase_possible"])

    def test_reverse_substitution_and_invalid_calendar(self):
        self.assertEqual(purchase_checkpoint(700, 0, baseline="SHEEP", candidate="COW")["capital_delta"], -100)
        with self.assertRaises(ValueError):
            project_calendar("COW", 0, [A(1, "CARE"), A(1, "FEED", wheat_available=1)])
        with self.assertRaises(ValueError):
            project_calendar("COW", 2, [A(1, "CARE")])
        with self.assertRaises(ValueError):
            project_calendar("GOOSE", 0, [])
        with self.assertRaises(ValueError):
            purchase_checkpoint(True, 0)


if __name__ == "__main__":
    unittest.main()
