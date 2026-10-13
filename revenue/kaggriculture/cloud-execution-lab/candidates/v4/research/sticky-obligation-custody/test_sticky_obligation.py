from __future__ import annotations

import copy
import unittest

import sticky_obligation as S


def water(**overrides):
    args = dict(
        site=(3, 4),
        created_step=23,
        replacement_op="FEED",
        replacement_effectful=True,
    )
    args.update(overrides)
    return S.issue_recovery_water(**args)


def carry(**overrides):
    args = dict(
        actor="hand-0",
        item="WHEAT",
        quantity=2,
        created_step=10,
        due_end=23,
        capacity_pressure_units=2,
    )
    args.update(overrides)
    return S.issue_carry_consumption(**args)


def row(step, actor="hand-0", op="PASS", **extra):
    payload = {"step": step, "actor": actor, "op": op}
    if "consumption_authenticated" not in extra:
        if op.upper() == "FEED":
            payload.update(
                consumption_authenticated=True,
                consumed_item="WHEAT",
                consumed_units=1,
            )
        elif op.upper() == "FERTILIZE":
            payload.update(
                consumption_authenticated=True,
                consumed_item="FERTILIZER",
                consumed_units=1,
            )
    payload.update(extra)
    return payload


class StickyObligationTests(unittest.TestCase):
    def test_water_obligation_uses_exact_next_day_window(self):
        ob = water()
        self.assertEqual(ob.kind, S.WATER_KIND)
        self.assertEqual(ob.site, (3, 4))
        self.assertEqual((ob.due_start, ob.due_end), (24, 47))
        self.assertEqual(ob.quantity, 1)

    def test_water_obligation_id_is_deterministic_and_serializable(self):
        a = water()
        b = water()
        self.assertEqual(a.obligation_id, b.obligation_id)
        self.assertEqual(S.validate_obligation(a.to_dict()), a)
        self.assertEqual(a.to_dict()["site"], [3, 4])

    def test_water_exchange_rejects_pass_water_and_unauthenticated_effect(self):
        for op in ("PASS", "WATER"):
            with self.subTest(op=op), self.assertRaises(S.UnsupportedObligation):
                water(replacement_op=op)
        with self.assertRaises(S.UnsupportedObligation):
            water(replacement_effectful=False)
        with self.assertRaises(S.UnsupportedObligation):
            water(replacement_effectful=1)

    def test_water_exchange_rejects_missing_next_day_callback_window(self):
        with self.assertRaises(S.UnsupportedObligation):
            water(created_step=718)

    def test_water_recovery_proves_exact_site_in_due_window(self):
        got = S.prove_recovery_water(
            water(),
            [row(24, op="WATER", site=[3, 4])],
        )
        self.assertTrue(got["proven"])
        self.assertEqual(got["sink_step"], 24)

    def test_water_recovery_waits_for_complete_callback_before_proof(self):
        got = S.prove_recovery_water(
            water(),
            [
                row(24, actor="hand-0", op="WATER", site=[3, 4]),
                row(24, actor="hand-1", op="DIG", site=[3, 4]),
            ],
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "site_invalidated_before_recovery")
        self.assertEqual(got["invalidating_step"], 24)
        self.assertEqual(got["invalidating_op"], "DIG")

    def test_water_recovery_same_callback_invalidator_then_water_is_not_proof(self):
        got = S.prove_recovery_water(
            water(),
            [
                row(24, actor="hand-0", op="DIG", site=[3, 4]),
                row(24, actor="hand-1", op="WATER", site=[3, 4]),
            ],
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "site_invalidated_before_recovery")
        self.assertEqual(got["invalidating_step"], 24)

    def test_water_recovery_same_callback_unrelated_site_after_water_stays_proven(self):
        got = S.prove_recovery_water(
            water(),
            [
                row(24, actor="hand-0", op="WATER", site=[3, 4]),
                row(24, actor="hand-1", op="DIG", site=[9, 9]),
                row(25, actor="hand-0", op="PASS"),
            ],
        )
        self.assertTrue(got["proven"])
        self.assertEqual(got["sink_step"], 24)

    def test_water_recovery_wrong_site_is_not_proof(self):
        got = S.prove_recovery_water(
            water(),
            [row(24, op="WATER", site=[3, 5])],
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "missing_due_window_recovery_water")

    def test_water_recovery_same_day_water_does_not_claim_next_day_custody(self):
        got = S.prove_recovery_water(
            water(),
            [row(23, op="WATER", site=[3, 4])],
        )
        self.assertFalse(got["proven"])

    def test_water_recovery_site_mutation_fails_before_later_water(self):
        got = S.prove_recovery_water(
            water(),
            [
                row(24, op="DIG", site=[3, 4]),
                row(25, op="WATER", site=[3, 4]),
            ],
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "site_invalidated_before_recovery")
        self.assertEqual(got["invalidating_step"], 24)

    def test_water_recovery_after_due_window_is_not_proof(self):
        got = S.prove_recovery_water(
            water(),
            [row(48, op="WATER", site=[3, 4])],
        )
        self.assertFalse(got["proven"])

    def test_carry_obligation_is_actor_local_and_same_day(self):
        ob = carry()
        self.assertEqual(ob.kind, S.CARRY_KIND)
        self.assertEqual(ob.actor, "hand-0")
        self.assertEqual(ob.item, "WHEAT")
        self.assertEqual((ob.due_start, ob.due_end), (11, 23))

    def test_carry_issue_rejects_pressure_shortfall(self):
        with self.assertRaises(S.UnsupportedObligation):
            carry(capacity_pressure_units=1)

    def test_carry_issue_rejects_cross_eod_custody(self):
        with self.assertRaises(S.UnsupportedObligation):
            carry(due_end=24)
        with self.assertRaises(S.UnsupportedObligation):
            carry(created_step=23, due_end=24)

    def test_bare_feed_and_fertilize_rows_do_not_prove_consumption(self):
        wheat = carry(quantity=1, capacity_pressure_units=1)
        got = S.prove_carry_consumption(
            wheat,
            [{"step": 11, "actor": "hand-0", "op": "FEED"}],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["sink_units"], 0)

        fertilizer = carry(item="FERTILIZER", quantity=1, capacity_pressure_units=1)
        got = S.prove_carry_consumption(
            fertilizer,
            [{"step": 11, "actor": "hand-0", "op": "FERTILIZE"}],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["sink_units"], 0)

    def test_unauthenticated_sink_is_not_counted(self):
        got = S.prove_carry_consumption(
            carry(quantity=1, capacity_pressure_units=1),
            [row(11, op="FEED", consumption_authenticated=False)],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["sink_units"], 0)

    def test_authenticated_sink_evidence_is_item_and_unit_bound(self):
        ob = carry(quantity=1, capacity_pressure_units=1)
        with self.assertRaisesRegex(S.UnsupportedObligation, "consumed_item mismatch"):
            S.prove_carry_consumption(
                ob,
                [
                    row(
                        11,
                        op="FEED",
                        consumed_item="FERTILIZER",
                    )
                ],
                current_inventory_units=0,
            )
        for poison in (True, 2):
            with self.subTest(consumed_units=poison), self.assertRaises(S.UnsupportedObligation):
                S.prove_carry_consumption(
                    ob,
                    [row(11, op="FEED", consumed_units=poison)],
                    current_inventory_units=0,
                )
        for poison in (1, 1.0, "true", [True], {"ok": True}):
            with self.subTest(authentication=poison), self.assertRaises(S.UnsupportedObligation):
                S.prove_carry_consumption(
                    ob,
                    [row(11, op="FEED", consumption_authenticated=poison)],
                    current_inventory_units=0,
                )

    def test_carry_two_new_wheat_units_need_two_free_feed_sinks(self):
        got = S.prove_carry_consumption(
            carry(),
            [row(11, op="FEED"), row(12, op="FEED")],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])
        self.assertEqual(got["sink_step"], 12)
        self.assertEqual(got["reserved_units"], 2)

    def test_existing_inventory_consumes_sink_capacity_first(self):
        got = S.prove_carry_consumption(
            carry(),
            [row(11, op="FEED"), row(12, op="FEED")],
            current_inventory_units=1,
        )
        self.assertFalse(got["proven"])
        got = S.prove_carry_consumption(
            carry(),
            [row(11, op="FEED"), row(12, op="FEED"), row(13, op="FEED")],
            current_inventory_units=1,
        )
        self.assertTrue(got["proven"])

    def test_future_same_item_pickup_consumes_sink_capacity(self):
        got = S.prove_carry_consumption(
            carry(),
            [
                row(11, op="PICKUP", item="WHEAT", quantity=1),
                row(12, op="FEED"),
                row(13, op="FEED"),
            ],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        got = S.prove_carry_consumption(
            carry(),
            [
                row(11, op="PICKUP", item="WHEAT", quantity=1),
                row(12, op="FEED"),
                row(13, op="FEED"),
                row(14, op="FEED"),
            ],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])

    def test_unrelated_pickup_does_not_consume_wheat_sink_capacity(self):
        got = S.prove_carry_consumption(
            carry(),
            [
                row(11, op="PICKUP", item="FERTILIZER", quantity=9),
                row(12, op="FEED"),
                row(13, op="FEED"),
            ],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])

    def test_other_actor_sinks_do_not_discharge_actor_local_custody(self):
        got = S.prove_carry_consumption(
            carry(),
            [
                row(11, actor="hand-1", op="FEED"),
                row(12, actor="hand-1", op="FEED"),
            ],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])

    def test_drop_before_reserved_sink_invalidates_carry(self):
        got = S.prove_carry_consumption(
            carry(),
            [row(11, op="DROP"), row(12, op="FEED"), row(13, op="FEED")],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "lossy_drop_before_reserved_sink")

    def test_unknown_wheat_harvest_gain_invalidates_proof(self):
        got = S.prove_carry_consumption(
            carry(),
            [row(11, op="HARVEST"), row(12, op="FEED"), row(13, op="FEED")],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        self.assertEqual(got["reason"], "unknown_wheat_harvest_acquisition_before_sink")

    def test_fertilizer_collection_is_competing_acquisition(self):
        ob = carry(item="FERTILIZER", quantity=1, capacity_pressure_units=1)
        got = S.prove_carry_consumption(
            ob,
            [row(11, op="COLLECT_FERTILIZER"), row(12, op="FERTILIZE")],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])
        got = S.prove_carry_consumption(
            ob,
            [
                row(11, op="COLLECT_FERTILIZER"),
                row(12, op="FERTILIZE"),
                row(13, op="FERTILIZE"),
            ],
            current_inventory_units=0,
        )
        self.assertTrue(got["proven"])

    def test_sink_after_due_window_is_not_proof(self):
        ob = carry(quantity=1, capacity_pressure_units=1, due_end=12)
        got = S.prove_carry_consumption(
            ob,
            [row(13, op="FEED")],
            current_inventory_units=0,
        )
        self.assertFalse(got["proven"])

    def test_replan_requires_byte_semantic_equivalent_obligation(self):
        ob = water()
        carried = S.carry_across_replan(ob, ob.to_dict(), now=24)
        self.assertEqual(carried, ob)

    def test_replan_rejects_tampered_obligation(self):
        ob = water()
        tampered = ob.to_dict()
        tampered["due_end"] += 1
        with self.assertRaises(S.UnsupportedObligation):
            S.carry_across_replan(ob, tampered, now=24)

    def test_missing_or_extra_obligation_fields_fail_closed(self):
        ob = water().to_dict()
        missing = dict(ob)
        missing.pop("item")
        extra = dict(ob, surprise=True)
        for value in (missing, extra):
            with self.subTest(value=value), self.assertRaises(S.UnsupportedObligation):
                S.validate_obligation(value)

    def test_bool_poison_is_rejected(self):
        with self.assertRaises(S.UnsupportedObligation):
            water(created_step=True)
        with self.assertRaises(S.UnsupportedObligation):
            carry(quantity=True)
        with self.assertRaises(S.UnsupportedObligation):
            carry(actor=True)
        with self.assertRaises(S.UnsupportedObligation):
            S.prove_carry_consumption(carry(), [], current_inventory_units=True)

    def test_projected_rows_must_be_sorted(self):
        with self.assertRaises(S.UnsupportedObligation):
            S.prove_recovery_water(
                water(),
                [row(25, op="PASS"), row(24, op="WATER", site=[3, 4])],
            )

    def test_proof_reports_never_emit_runtime_or_decision_authority(self):
        reports = [
            S.prove_recovery_water(water(), [row(24, op="WATER", site=[3, 4])]),
            S.prove_carry_consumption(
                carry(quantity=1, capacity_pressure_units=1),
                [row(11, op="FEED")],
                current_inventory_units=0,
            ),
        ]
        for report in reports:
            self.assertTrue(report["research_only"])
            self.assertFalse(report["decision_authority"])
            self.assertFalse(report["runtime_mutation_authority"])
            self.assertNotIn("allow", report)
            self.assertNotIn("choose", report)

    def test_wrong_obligation_kind_cannot_cross_proof_surfaces(self):
        with self.assertRaises(S.UnsupportedObligation):
            S.prove_recovery_water(carry(), [])
        with self.assertRaises(S.UnsupportedObligation):
            S.prove_carry_consumption(water(), [], current_inventory_units=0)

    def test_inputs_are_not_mutated(self):
        ob = carry(quantity=1, capacity_pressure_units=1)
        rows = [row(11, op="FEED")]
        before = copy.deepcopy(rows)
        S.prove_carry_consumption(ob, rows, current_inventory_units=0)
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()