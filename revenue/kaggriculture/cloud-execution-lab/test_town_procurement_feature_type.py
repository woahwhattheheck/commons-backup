# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_town_feature_main", HERE / "main.py")
main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(main)


class TownProcurementFeatureTypeTests(unittest.TestCase):
    def setUp(self):
        self.old_file = main.__file__
        self.old_instance = main._INSTANCE
        self.old_recovery = main._SPATIAL_RECOVERY
        self.old_titan_runtime = sys.modules.get("titan_runtime")
        self.old_town_procurement = sys.modules.get("town_procurement")
        main._INSTANCE = None
        main._SPATIAL_RECOVERY = None

    def tearDown(self):
        main.__file__ = self.old_file
        main._INSTANCE = self.old_instance
        main._SPATIAL_RECOVERY = self.old_recovery
        if self.old_titan_runtime is None:
            sys.modules.pop("titan_runtime", None)
        else:
            sys.modules["titan_runtime"] = self.old_titan_runtime
        if self.old_town_procurement is None:
            sys.modules.pop("town_procurement", None)
        else:
            sys.modules["town_procurement"] = self.old_town_procurement

    def test_reader_accepts_only_literal_bools(self):
        self.assertIs(main._town_procurement_enabled({}), False)
        self.assertIs(main._town_procurement_enabled({"town_procurement": False}), False)
        self.assertIs(main._town_procurement_enabled({"town_procurement": True}), True)
        for alias in (0, 1, "false", "true", None, [], {}):
            with self.subTest(alias=alias):
                with self.assertRaises(TypeError):
                    main._town_procurement_enabled({"town_procurement": alias})

    def _run_entrypoint(self, value):
        observed = []
        town = types.ModuleType("town_procurement")
        town.observe = lambda obs: observed.append(dict(obs))
        sys.modules["town_procurement"] = town

        deadline = types.SimpleNamespace(
            terminal_liquidation_fallback=lambda obs, cfg: {"kind": "terminal"},
            legal_pass=lambda obs: {"kind": "pass"},
        )
        titan_runtime = types.ModuleType("titan_runtime")
        titan_runtime.deadline = deadline
        sys.modules["titan_runtime"] = titan_runtime

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TITAN-CONFIG.json").write_text(json.dumps({
                "town_procurement": value,
                "budget_seconds": 1e-12,
                "reserve_seconds": 0.0,
            }))
            main.__file__ = str(root / "main.py")
            result = main.agent({"step": 0, "player": 0}, {})
        return observed, result

    def test_false_is_identity_and_true_reaches_receipt_observer(self):
        observed, result = self._run_entrypoint(False)
        self.assertEqual(observed, [])
        self.assertEqual(result, {"kind": "pass"})

        main._INSTANCE = None
        main._SPATIAL_RECOVERY = None
        observed, result = self._run_entrypoint(True)
        self.assertEqual(observed, [{"step": 0, "player": 0}])
        self.assertEqual(result, {"kind": "pass"})

    def test_aliases_fail_before_receipt_observer(self):
        for alias in (0, 1, "false", "true", None, [], {}):
            with self.subTest(alias=alias):
                main._INSTANCE = None
                main._SPATIAL_RECOVERY = None
                observed = []
                town = types.ModuleType("town_procurement")
                town.observe = lambda obs: observed.append(dict(obs))
                sys.modules["town_procurement"] = town
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "TITAN-CONFIG.json").write_text(json.dumps({
                        "town_procurement": alias,
                        "budget_seconds": 1e-12,
                        "reserve_seconds": 0.0,
                    }))
                    main.__file__ = str(root / "main.py")
                    with self.assertRaises(TypeError):
                        main.agent({"step": 0, "player": 0}, {})
                self.assertEqual(observed, [])


if __name__ == "__main__":
    unittest.main()
