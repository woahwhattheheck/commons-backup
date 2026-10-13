"""Contracts for E03 identity-free public behavior scenario weighting."""
import unittest

from e03_public_behavior_mixture import (
    PPM,
    PublicFlowSample,
    StressScenario,
    fixed_diverse_mixture,
    rolling_public_mixture,
    scenarios_from_public_stress,
)


def exact(step, quantity, *, product="MILK", alignment=None):
    return PublicFlowSample(step, product, quantity, quantity, "identified", alignment)


class PublicBehaviorMixtureTests(unittest.TestCase):
    def test_fixed_diverse_is_exact_normalized_and_stable(self):
        scenarios = [StressScenario("zero", 0), StressScenario("small", 10), StressScenario("large", 40)]
        first = fixed_diverse_mixture(scenarios)
        second = fixed_diverse_mixture(scenarios)
        self.assertEqual(first, second)
        self.assertEqual(sum(first["weights_ppm"].values()), PPM)
        self.assertEqual(first["top"], "zero")

    def test_insufficient_or_ambiguous_evidence_is_exact_noop(self):
        scenarios = [StressScenario("zero", 0), StressScenario("flow", 20)]
        samples = [
            exact(1, 20),
            PublicFlowSample(2, "MILK", 0, 100, "floor_censored"),
            PublicFlowSample(3, "MILK", 20, 20, "identified", ambiguous=True),
        ]
        result = rolling_public_mixture("MILK", scenarios, samples, now=4, minimum_support=2)
        self.assertFalse(result["ready"])
        self.assertEqual(result["support"], 1)
        self.assertEqual(result["ambiguous"], 2)
        self.assertEqual(result["weights_ppm"], {})
        self.assertIsNone(result["top"])

    def test_rolling_quantity_evidence_favors_matching_public_stress(self):
        scenarios = [StressScenario("zero", 0), StressScenario("small", 10), StressScenario("large", 40)]
        samples = [exact(1, 9), exact(2, 10), exact(3, 11), exact(4, 10)]
        result = rolling_public_mixture("MILK", scenarios, samples, now=5, minimum_support=3)
        self.assertTrue(result["ready"])
        self.assertEqual(result["top"], "small")
        self.assertGreater(result["weights_ppm"]["small"], result["weights_ppm"]["zero"])
        self.assertGreater(result["weights_ppm"]["small"], result["weights_ppm"]["large"])
        self.assertEqual(sum(result["weights_ppm"].values()), PPM)

    def test_public_absorption_timing_breaks_equal_quantity_tie(self):
        scenarios = [
            StressScenario("prompt", 20, "before_absorption"),
            StressScenario("reactive", 20, "after_absorption"),
        ]
        samples = [
            exact(1, 20, alignment="after_absorption"),
            exact(2, 20, alignment="after_absorption"),
            exact(3, 20, alignment="after_absorption"),
        ]
        result = rolling_public_mixture("MILK", scenarios, samples, now=4, minimum_support=3)
        self.assertEqual(result["top"], "reactive")
        self.assertEqual(result["loss"]["reactive"], 0)
        self.assertGreater(result["loss"]["prompt"], 0)

    def test_midgame_switch_recovers_when_old_public_evidence_expires(self):
        scenarios = [StressScenario("quiet", 0), StressScenario("heavy", 40)]
        samples = [
            exact(1, 0), exact(2, 0), exact(3, 0),
            exact(10, 40), exact(11, 40), exact(12, 40),
        ]
        early = rolling_public_mixture("MILK", scenarios, samples, now=4, window=4, minimum_support=3)
        late = rolling_public_mixture("MILK", scenarios, samples, now=13, window=4, minimum_support=3)
        self.assertEqual(early["top"], "quiet")
        self.assertEqual(late["top"], "heavy")
        self.assertEqual(late["latest_training_step"], 12)

    def test_product_and_future_evidence_do_not_leak(self):
        scenarios = [StressScenario("zero", 0), StressScenario("flow", 20)]
        samples = [
            exact(1, 20, product="WOOL"),
            exact(1, 0), exact(2, 0), exact(9, 20),
        ]
        result = rolling_public_mixture("MILK", scenarios, samples, now=3, minimum_support=2)
        self.assertEqual(result["support"], 2)
        self.assertEqual(result["latest_training_step"], 2)
        self.assertEqual(result["top"], "zero")

    def test_public_stress_adapter_deduplicates_equal_quantities(self):
        scenarios = scenarios_from_public_stress(
            {"visible": 0, "short": 20, "long_rate": 20},
            capacity=100,
        )
        self.assertEqual([(s.name, s.quantity) for s in scenarios], [
            ("no_flow", 0), ("short", 20), ("capacity", 100),
        ])

    def test_invalid_inputs_fail_closed_instead_of_becoming_hidden_state(self):
        with self.assertRaises(ValueError):
            scenarios_from_public_stress({"visible": "20", "short": 0, "long_rate": 0})
        with self.assertRaises(ValueError):
            rolling_public_mixture("MILK", [StressScenario("bad", -1)], [], now=1)
        with self.assertRaises(ValueError):
            rolling_public_mixture(
                "MILK",
                [StressScenario("ok", 1)],
                [PublicFlowSample(0, "MILK", 5, 4, "identified")],
                now=1,
                minimum_support=1,
            )

    def test_parsed_sample_scalars_are_strictly_validated_before_filtering(self):
        scenarios = [StressScenario("zero", 0), StressScenario("flow", 20)]
        bad_samples = [
            PublicFlowSample(True, "MILK", 1, 1, "identified"),
            PublicFlowSample(1.5, "MILK", 1, 1, "identified"),
            PublicFlowSample(1, "", 1, 1, "identified"),
            PublicFlowSample(1, 7, 1, 1, "identified"),
            PublicFlowSample(1, "MILK", True, 1, "identified"),
            PublicFlowSample(1, "MILK", 1.5, 2, "identified"),
            PublicFlowSample(1, "MILK", 1, True, "identified"),
            PublicFlowSample(1, "MILK", 1, 2.5, "identified"),
            PublicFlowSample(1, "MILK", 1, 1, ""),
            PublicFlowSample(1, "MILK", 1, 1, 9),
            PublicFlowSample(1, "MILK", 1, 1, "identified", "any"),
            PublicFlowSample(1, "MILK", 1, 1, "identified", "bogus"),
            PublicFlowSample(1, "MILK", 1, 1, "identified", None, 1),
        ]
        for sample in bad_samples:
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    rolling_public_mixture(
                        "MILK", scenarios, [sample], now=4, minimum_support=1
                    )
        # Validation happens before product/time filtering, so malformed unrelated
        # evidence cannot be silently retained in a parsed history stream.
        with self.assertRaises(ValueError):
            rolling_public_mixture(
                "MILK",
                scenarios,
                [PublicFlowSample(99, "WOOL", True, True, "identified")],
                now=4,
                minimum_support=1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
