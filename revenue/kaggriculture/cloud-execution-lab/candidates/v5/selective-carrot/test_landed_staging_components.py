from pathlib import Path
import unittest

import staging_composer as sc


class LandedStagingComponentTests(unittest.TestCase):
    def test_future_own_supply_component_is_self_authenticating_and_isolated(self):
        root = Path(__file__).with_name("components") / "future-own-supply-v1"
        component = sc.load_component(root / "COMPONENT.json")

        self.assertEqual(component["component_id"], "future-own-supply-v1")
        self.assertEqual(component["depends_on"], [])
        self.assertEqual(component["conflicts_with"], [])
        self.assertEqual(component["overlap_after"], {})
        self.assertEqual(
            set(component["replacements"]),
            {"frozen_selected.py", "selected_sell_core.py"},
        )
        self.assertEqual(set(component["additions"]), {"future_own_supply.py"})

    def test_c02_component_is_self_authenticating_and_isolated(self):
        root = Path(__file__).with_name("components") / "c02-deferred-replacement-v1"
        component = sc.load_component(root / "COMPONENT.json")

        self.assertEqual(component["component_id"], "c02-deferred-replacement-v1")
        self.assertEqual(component["depends_on"], [])
        self.assertEqual(component["conflicts_with"], [])
        self.assertEqual(component["overlap_after"], {})
        self.assertEqual(set(component["replacements"]), {"delivery_choice.py"})
        self.assertEqual(component["additions"], {})

    def test_wf1_component_is_self_authenticating_and_isolated(self):
        root = Path(__file__).with_name("components") / "wf1-production20f-v1"
        component = sc.load_component(root / "COMPONENT.json")

        self.assertEqual(component["component_id"], "wf1-production20f-v1")
        self.assertEqual(component["depends_on"], [])
        self.assertEqual(component["conflicts_with"], [])
        self.assertEqual(component["overlap_after"], {})
        self.assertEqual(set(component["replacements"]), {"main.py"})
        self.assertEqual(
            set(component["additions"]),
            {"r04_wheat_fert.py", "wf1_current_adapter.py"},
        )


if __name__ == "__main__":
    unittest.main()
