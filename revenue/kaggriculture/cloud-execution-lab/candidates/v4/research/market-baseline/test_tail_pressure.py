import unittest

import tail_pressure as T


SHOPS_380 = (
    "BRUNCH_SPOT",
    "ICE_CREAM_SHOP",
    "SMOOTHIE_SHOP",
    "FARMERS_MARKET",
    "BRUNCH_SPOT",
)
NONSTRAW_SHOPS_402 = (
    "BAKERY",
    "PIZZA_SHOP",
    "YARN_STORE",
    "PET_CAFE",
    "BAKERY",
)
ONE_STRAW_SHOPS_402 = (
    "BRUNCH_SPOT",
    "PIZZA_SHOP",
    "YARN_STORE",
    "PET_CAFE",
    "BAKERY",
)


class TailPressureTests(unittest.TestCase):
    def test_helpers_are_pinned_to_authenticated_snapshots(self):
        self.assertEqual(
            T.verify_helpers(),
            {
                "market_baseline": T.MARKET_BASELINE_BLOB,
                "demand_velocity": T.DEMAND_VELOCITY_BLOB,
                "counter_ambush": T.COUNTER_AMBUSH_BLOB,
            },
        )
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_000,
            own_units=8,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertTrue(r["helper_snapshots_authenticated_before_execution"])
        self.assertEqual(r["helper_identities"], T.verify_helpers())
        self.assertIs(T.d.m, T.m)

    def test_apex_380_reachable_current_shops_have_guaranteed_headroom(self):
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_000,
            own_units=8,
            rival_units=8,
            pre_step=380,
            unlocked_shops=SHOPS_380,
        )
        self.assertEqual(r["expected_current_shop_count"], 5)
        self.assertEqual(r["residual_event_public_supply_units"], 16)
        self.assertEqual(r["guaranteed_remaining_absorption"]["current_shop_units"], 420)
        self.assertEqual(r["guaranteed_remaining_absorption"]["town_center_units"], 14)
        self.assertEqual(r["guaranteed_remaining_absorption"]["guaranteed_units"], 434)
        self.assertEqual(
            r["remaining_absorption_tail_context"]["quantile_units"], 132.8
        )
        self.assertFalse(
            r["remaining_absorption_tail_context"]["authority_for_certificate"]
        )
        self.assertFalse(r["pressure_warning"])
        self.assertEqual(
            r["disposition"],
            "POSITIVE_IMMEDIATE_COUNTER_WITH_GUARANTEED_TAIL_HEADROOM",
        )

    def test_apex_402_no_current_strawberry_shops_flips_to_not_certified(self):
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_000,
            own_units=8,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertEqual(r["expected_current_shop_count"], 5)
        self.assertEqual(r["residual_event_public_supply_units"], 16)
        self.assertEqual(r["guaranteed_remaining_absorption"]["current_shop_units"], 0)
        self.assertEqual(r["guaranteed_remaining_absorption"]["town_center_units"], 13)
        self.assertEqual(r["guaranteed_remaining_absorption"]["guaranteed_units"], 13)
        self.assertEqual(
            r["remaining_absorption_tail_context"]["quantile_units"], 127.3
        )
        self.assertEqual(r["tail_slack_units"], -3)
        self.assertTrue(r["pressure_warning"])
        self.assertEqual(
            r["disposition"],
            "POSITIVE_IMMEDIATE_COUNTER_TAIL_UNWIND_NOT_CERTIFIED",
        )

    def test_current_strawberry_shop_increases_only_guaranteed_budget(self):
        base = T.guaranteed_remaining_absorption(
            "STRAWBERRY", 403, NONSTRAW_SHOPS_402
        )
        one = T.guaranteed_remaining_absorption(
            "STRAWBERRY", 403, ONE_STRAW_SHOPS_402
        )
        self.assertEqual(base["guaranteed_units"], 13)
        self.assertEqual(one["current_shop_units"], 79)
        self.assertEqual(one["guaranteed_units"], 92)
        self.assertGreater(one["guaranteed_units"], base["guaranteed_units"])

    def test_positive_immediate_counter_can_fail_guaranteed_unwind(self):
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=9_700,
            own_units=128,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertGreater(r["immediate"]["gross_relative_margin_swing"], 0)
        self.assertEqual(r["residual_event_public_supply_units"], 136)
        self.assertEqual(r["guaranteed_remaining_absorption"]["guaranteed_units"], 13)
        self.assertEqual(r["tail_slack_units"], -123)
        self.assertTrue(r["pressure_warning"])
        self.assertEqual(
            r["disposition"],
            "POSITIVE_IMMEDIATE_COUNTER_TAIL_UNWIND_NOT_CERTIFIED",
        )

    def test_price_floor_event_does_not_invent_public_supply(self):
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_493,
            own_units=8,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertEqual(r["residual_event_public_supply_units"], 0)
        self.assertEqual(r["immediate"]["gross_relative_margin_swing"], 0)
        self.assertEqual(r["disposition"], "NO_POSITIVE_IMMEDIATE_COUNTER")

    def test_certificate_never_claims_action_or_unconditional_tail_authority(self):
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_000,
            own_units=8,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertFalse(r["decision_authority"])
        self.assertFalse(r["timing_authority"])
        self.assertFalse(r["opponent_future_supply_accounted"])
        self.assertTrue(r["public_state_only"])
        self.assertEqual(
            r["unwind_budget_authority"],
            "guaranteed_current_shops_plus_town_center",
        )
        self.assertFalse(
            r["remaining_absorption_tail_context"]["authority_for_certificate"]
        )

    def test_scope_stays_on_authenticated_strawberry_counter(self):
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="MELON",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=248,
                unlocked_shops=(),
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=100,
                unlocked_shops=("BAKERY",),
            )

    def test_rival_quantity_is_conditional_source_max_not_arbitrary(self):
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=7,
                pre_step=402,
                unlocked_shops=NONSTRAW_SHOPS_402,
            )
        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=10_000,
            own_units=8,
            rival_units=8,
            pre_step=402,
            unlocked_shops=NONSTRAW_SHOPS_402,
        )
        self.assertEqual(r["source_event_custody"]["source_max_sell"], 8)
        self.assertFalse(
            r["source_event_custody"]["realized_rival_quantity_authenticated"]
        )

    def test_certificate_rejects_noncanonical_tail_context(self):
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=NONSTRAW_SHOPS_402,
                q=1.0,
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=NONSTRAW_SHOPS_402,
                q=True,
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=NONSTRAW_SHOPS_402,
                seeds=(1,),
            )

    def test_custom_tail_is_labelled_context_only(self):
        r = T.remaining_absorption_tail("STRAWBERRY", 403, seeds=(1,))
        self.assertFalse(r["canonical_panel"])
        self.assertFalse(r["state_conditioned"])
        self.assertFalse(r["authority_for_certificate"])
        self.assertTrue(r["context_only"])
        with self.assertRaises(ValueError):
            T.remaining_absorption_tail("STRAWBERRY", 403, seeds=(True,))

    def test_current_shop_state_contract_fails_closed(self):
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=(),
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=380,
                unlocked_shops=SHOPS_380 + ("BRUNCH_SPOT",) * 3,
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=("BAKERY", "PIZZA_SHOP", "NOPE", "PET_CAFE", "BAKERY"),
            )
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=8,
                rival_units=8,
                pre_step=402,
                unlocked_shops=list(NONSTRAW_SHOPS_402),
            )

    def test_reduced_helper_underflow_domain_fails_closed_at_engine_mismatch(self):
        for starting_inventory in (0, 4):
            with self.subTest(starting_inventory=starting_inventory):
                with self.assertRaises(ValueError):
                    T.pressure_certificate(
                        item="STRAWBERRY",
                        starting_inventory=starting_inventory,
                        own_units=8,
                        rival_units=8,
                        pre_step=380,
                        unlocked_shops=SHOPS_380,
                    )

        r = T.pressure_certificate(
            item="STRAWBERRY",
            starting_inventory=5,
            own_units=8,
            rival_units=8,
            pre_step=380,
            unlocked_shops=SHOPS_380,
        )
        domain = r["reduced_helper_domain_custody"]
        self.assertEqual(domain["pre_step_town_drain_units"], 5)
        self.assertEqual(domain["post_rival_town_drain_units"], 0)
        self.assertEqual(
            domain["minimum_starting_inventory_for_unclamped_reduced_helper"], 5
        )
        self.assertTrue(domain["reduced_helper_town_clamp_inactive"])
        self.assertFalse(domain["official_negative_inventory_domain_certified"])
        self.assertEqual(r["no_event_inventory_after_t_plus_1"], 0)

    def test_numeric_bool_aliases_and_terminal_overrun_fail_closed(self):
        with self.assertRaises(ValueError):
            T.pressure_certificate(
                item="STRAWBERRY",
                starting_inventory=10_000,
                own_units=True,
                rival_units=8,
                pre_step=402,
                unlocked_shops=NONSTRAW_SHOPS_402,
            )
        with self.assertRaises(ValueError):
            T.remaining_absorption_tail("STRAWBERRY", 719)
        with self.assertRaises(ValueError):
            T.guaranteed_remaining_absorption(
                "STRAWBERRY", True, NONSTRAW_SHOPS_402
            )


if __name__ == "__main__":
    unittest.main()
