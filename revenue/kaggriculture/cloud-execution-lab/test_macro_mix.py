# SPDX-License-Identifier: Apache-2.0
"""Contracts for identity-free deterministic S09 macro mixing."""
import unittest

from macro_mix import (
    MACROS,
    MacroMixer,
    PublicFeedback,
    STEP_MAX,
    UnsafeMacroFeedback,
    WEIGHT_TOTAL,
    compare_policies,
    expected_loss_bp,
    worst_family_regret_bp,
)


def loss(**changes):
    row = {
        "conservative_expansion": 5_000,
        "production_acceleration": 5_000,
        "market_pressure": 5_000,
        "survival": 5_000,
    }
    row.update(changes)
    return row


class MacroMixTests(unittest.TestCase):
    def test_uniform_initial_state_and_tie_are_deterministic(self):
        mixer = MacroMixer.uniform()
        self.assertEqual(sum(mixer.weights), WEIGHT_TOTAL)
        self.assertEqual(mixer.deterministic_macro(), MACROS[0])
        self.assertEqual(mixer.distribution_ppm(), {macro: 250_000 for macro in MACROS})

    def test_public_feedback_accepts_only_step_and_loss_vector(self):
        row = {"step": 1, "loss_bp": loss()}
        parsed = PublicFeedback.from_mapping(row)
        self.assertEqual(parsed.step, 1)
        for forbidden in ("opponent", "opponent_id", "name", "uuid", "email", "family"):
            bad = dict(row); bad[forbidden] = "leak"
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(UnsafeMacroFeedback):
                    PublicFeedback.from_mapping(bad)

    def test_loss_vector_requires_exact_fixed_macro_vocabulary(self):
        missing = loss(); missing.pop("survival")
        extra = loss(debug=1)
        for row in (missing, extra):
            with self.subTest(row=row):
                with self.assertRaises(UnsafeMacroFeedback):
                    PublicFeedback.from_mapping({"step": 1, "loss_bp": row})

    def test_direct_public_feedback_object_obeys_step_bound(self):
        valid_loss = loss()
        accepted = PublicFeedback(step=STEP_MAX, loss_bp=valid_loss)
        self.assertEqual(accepted.step, STEP_MAX)
        mixer = MacroMixer.uniform().observe(accepted)
        self.assertEqual(mixer.last_step, STEP_MAX)
        for bad_step in (STEP_MAX + 1, -1, True, False):
            with self.subTest(step=bad_step):
                with self.assertRaises(UnsafeMacroFeedback):
                    PublicFeedback(step=bad_step, loss_bp=valid_loss)
                bypass = PublicFeedback.__new__(PublicFeedback)
                object.__setattr__(bypass, "step", bad_step)
                object.__setattr__(bypass, "loss_bp", valid_loss)
                with self.assertRaises(UnsafeMacroFeedback):
                    MacroMixer.uniform().observe(bypass)

    def test_mixer_last_step_rejects_unbounded_and_bool_values(self):
        with self.assertRaises(UnsafeMacroFeedback):
            MacroMixer(last_step=STEP_MAX + 1)
        with self.assertRaises(UnsafeMacroFeedback):
            MacroMixer(last_step=True)
        with self.assertRaises(UnsafeMacroFeedback):
            MacroMixer(last_step=-2)

    def test_update_penalizes_only_observed_losses(self):
        mixer = MacroMixer.uniform().observe({
            "step": 1,
            "loss_bp": loss(conservative_expansion=9_000, production_acceleration=1_000),
        })
        self.assertGreater(mixer.weights[1], mixer.weights[0])
        self.assertEqual(sum(mixer.weights), WEIGHT_TOTAL)
        self.assertEqual(mixer.observations, 1)

    def test_updates_are_byte_for_byte_repeatable(self):
        rows = [
            {"step": step, "loss_bp": loss(
                conservative_expansion=(step * 811) % 10_001,
                production_acceleration=(step * 613 + 17) % 10_001,
                market_pressure=(step * 421 + 29) % 10_001,
                survival=(step * 277 + 43) % 10_001,
            )}
            for step in range(1, 65)
        ]
        a = MacroMixer.uniform().observe_many(rows)
        b = MacroMixer.uniform().observe_many(rows)
        self.assertEqual(a, b)
        self.assertEqual(a.distribution_ppm(), b.distribution_ppm())

    def test_stale_and_replayed_feedback_fail_closed(self):
        mixer = MacroMixer.uniform().observe({"step": 4, "loss_bp": loss()})
        for step in (4, 3):
            with self.subTest(step=step):
                with self.assertRaises(UnsafeMacroFeedback):
                    mixer.observe({"step": step, "loss_bp": loss()})

    def test_bool_negative_and_out_of_range_values_fail_closed(self):
        bad_rows = [
            {"step": True, "loss_bp": loss()},
            {"step": 1, "loss_bp": loss(survival=-1)},
            {"step": 1, "loss_bp": loss(survival=10_001)},
            {"step": 1, "loss_bp": loss(survival=True)},
        ]
        for row in bad_rows:
            with self.subTest(row=row):
                with self.assertRaises(UnsafeMacroFeedback):
                    PublicFeedback.from_mapping(row)

    def test_mixed_selection_has_explicit_repeatable_boundaries(self):
        mixer = MacroMixer.uniform()
        self.assertEqual(mixer.mixed_macro(0), MACROS[0])
        self.assertEqual(mixer.mixed_macro(249_999), MACROS[0])
        self.assertEqual(mixer.mixed_macro(250_000), MACROS[1])
        self.assertEqual(mixer.mixed_macro(999_999), MACROS[3])
        with self.assertRaises(UnsafeMacroFeedback): mixer.mixed_macro(-1)
        with self.assertRaises(UnsafeMacroFeedback): mixer.mixed_macro(1_000_000)

    def test_expected_loss_uses_exact_normalized_distribution(self):
        uniform = {macro: 250_000 for macro in MACROS}
        self.assertEqual(expected_loss_bp(uniform, {
            "conservative_expansion": 0,
            "production_acceleration": 2_000,
            "market_pressure": 4_000,
            "survival": 6_000,
        }), 3_000)
        bad = dict(uniform); bad[MACROS[0]] -= 1
        with self.assertRaises(UnsafeMacroFeedback): expected_loss_bp(bad, loss())

    def test_worst_family_regret_is_identity_free_and_order_independent(self):
        distribution = {macro: 250_000 for macro in MACROS}
        rows = [
            loss(conservative_expansion=0, production_acceleration=4_000),
            loss(survival=0, market_pressure=4_000),
        ]
        self.assertEqual(worst_family_regret_bp(distribution, rows), worst_family_regret_bp(distribution, list(reversed(rows))))
        with self.assertRaises(UnsafeMacroFeedback): worst_family_regret_bp(distribution, [])

    def test_held_out_family_can_favor_robust_mix_over_deterministic(self):
        rows = [
            {"conservative_expansion": 0, "production_acceleration": 7_000, "market_pressure": 9_000, "survival": 9_000},
            {"conservative_expansion": 7_000, "production_acceleration": 0, "market_pressure": 9_000, "survival": 9_000},
        ]
        mixed = {"conservative_expansion": 500_000, "production_acceleration": 500_000, "market_pressure": 0, "survival": 0}
        deterministic = {"conservative_expansion": 1_000_000, "production_acceleration": 0, "market_pressure": 0, "survival": 0}
        self.assertLess(worst_family_regret_bp(mixed, rows), worst_family_regret_bp(deterministic, rows))

    def test_compare_policies_reports_same_evidence_family(self):
        mixer = MacroMixer.uniform().observe_many([
            {"step": 1, "loss_bp": loss(conservative_expansion=1_000, survival=9_000)},
            {"step": 2, "loss_bp": loss(conservative_expansion=1_000, market_pressure=8_000)},
        ])
        canonical = {macro: 250_000 for macro in MACROS}
        held_out = [
            loss(conservative_expansion=1_000, production_acceleration=6_000),
            loss(conservative_expansion=2_000, survival=8_000),
        ]
        report = compare_policies(mixer, canonical, held_out)
        self.assertEqual(report["observations"], 2)
        self.assertEqual(report["last_step"], 2)
        self.assertEqual(sum(report["distribution_ppm"].values()), WEIGHT_TOTAL)
        self.assertIn(report["deterministic_macro"], MACROS)
        self.assertIsInstance(report["mixed_beats_canonical_worst_family"], bool)

    def test_promotion_gate_rejects_worse_held_out_mix(self):
        rows = [
            {"step": step, "loss_bp": {
                "conservative_expansion": (step * 811) % 10_001,
                "production_acceleration": (step * 613 + 17) % 10_001,
                "market_pressure": (step * 421 + 29) % 10_001,
                "survival": (step * 277 + 43) % 10_001,
            }}
            for step in range(1, 65)
        ]
        mixer = MacroMixer.uniform().observe_many(rows)
        held_out = [
            {"conservative_expansion": 0, "production_acceleration": 7_000, "market_pressure": 9_000, "survival": 9_000},
            {"conservative_expansion": 7_000, "production_acceleration": 0, "market_pressure": 9_000, "survival": 9_000},
            {"conservative_expansion": 8_000, "production_acceleration": 8_000, "market_pressure": 0, "survival": 6_000},
            {"conservative_expansion": 8_000, "production_acceleration": 8_000, "market_pressure": 6_000, "survival": 0},
        ]
        report = compare_policies(mixer, {macro: 250_000 for macro in MACROS}, held_out)
        self.assertGreaterEqual(report["mixed_worst_regret_bp"], report["canonical_worst_regret_bp"])
        self.assertFalse(report["mixed_beats_canonical_worst_family"])
        self.assertEqual(report["canonical_worst_regret_bp"], 6_250)
        self.assertEqual(report["mixed_worst_regret_bp"], 6_955)
        self.assertEqual(report["deterministic_worst_regret_bp"], 9_000)

    def test_constructor_rejects_noncanonical_weight_state(self):
        with self.assertRaises(UnsafeMacroFeedback):
            MacroMixer(weights=(1, 1, 1, 1))
        with self.assertRaises(UnsafeMacroFeedback):
            MacroMixer(weights=(250_000, 250_000, 250_000, 250_000), learning_rate_bp=0)

    def test_learning_rate_bound_keeps_every_weight_positive(self):
        mixer = MacroMixer.uniform(learning_rate_bp=5_000)
        for step in range(1, 257):
            mixer = mixer.observe({
                "step": step,
                "loss_bp": loss(
                    conservative_expansion=10_000,
                    production_acceleration=0,
                    market_pressure=10_000,
                    survival=10_000,
                ),
            })
        self.assertTrue(all(weight > 0 for weight in mixer.weights))
        self.assertEqual(sum(mixer.weights), WEIGHT_TOTAL)

    def test_no_hidden_rng_surface(self):
        mixer = MacroMixer.uniform().observe({"step": 1, "loss_bp": loss()})
        tickets = (0, 1, 123_456, 500_000, 999_999)
        self.assertEqual([mixer.mixed_macro(t) for t in tickets], [mixer.mixed_macro(t) for t in tickets])


if __name__ == "__main__":
    unittest.main()
