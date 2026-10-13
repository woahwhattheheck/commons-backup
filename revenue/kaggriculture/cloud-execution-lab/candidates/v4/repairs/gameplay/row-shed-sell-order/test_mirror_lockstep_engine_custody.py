# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from types import ModuleType

import check_mirror_lockstep_engine as C


class MirrorLockstepEngineCustodyTests(unittest.TestCase):
    def test_engine_config_is_pinned_to_official_blob(self):
        self.assertEqual(
            C.ENGINE_CONFIG_BLOB,
            "b354d06b742fe48402513792253f1a5c29366b20",
        )

    def test_captured_dependency_survives_backing_path_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module_path = root / "synthetic_engine.py"
            config_path = root / "kaggriculture.json"
            source = (
                "from pathlib import Path\n"
                "CONFIG = open(Path(__file__).with_name('kaggriculture.json')).read()\n"
            ).encode("utf-8")
            config_path.write_text("captured", encoding="utf-8")
            captured = config_path.read_bytes()
            config_path.write_text("attacker", encoding="utf-8")

            module = C.load_captured(
                "_rowshed_config_swap_control",
                module_path,
                source,
                text_captures={config_path: captured},
            )
            self.assertEqual(module.CONFIG, "captured")
            self.assertEqual(config_path.read_text(encoding="utf-8"), "attacker")

    def test_engine_exec_fences_ambient_kaggle_seed_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module_path = root / "kaggriculture.py"
            config_path = root / "kaggriculture.json"
            source = (
                "from kaggle_environments.utils import resolve_episode_seed\n"
                "RESOLVER = resolve_episode_seed\n"
                "with open(__file__.replace('.py', '.json')) as f:\n"
                "    SPEC = f.read()\n"
            ).encode("utf-8")
            config_path.write_text("captured", encoding="utf-8")

            previous_package = sys.modules.get("kaggle_environments")
            previous_utils = sys.modules.get("kaggle_environments.utils")
            had_package = "kaggle_environments" in sys.modules
            had_utils = "kaggle_environments.utils" in sys.modules
            attacker_package = ModuleType("kaggle_environments")
            attacker_package.__path__ = []
            attacker_utils = ModuleType("kaggle_environments.utils")
            attacker_utils.resolve_episode_seed = lambda *_a, **_k: "attacker"
            attacker_package.utils = attacker_utils
            sys.modules["kaggle_environments"] = attacker_package
            sys.modules["kaggle_environments.utils"] = attacker_utils
            old_config = C.ENGINE_CONFIG
            try:
                C.ENGINE_CONFIG = config_path
                module = C.load_engine_captured(
                    module_path,
                    source,
                    config_path.read_bytes(),
                )
                with self.assertRaises(C.CheckError):
                    module.RESOLVER(None)
                self.assertEqual(module.SPEC, "captured")
                self.assertIs(sys.modules["kaggle_environments"], attacker_package)
                self.assertIs(sys.modules["kaggle_environments.utils"], attacker_utils)
            finally:
                C.ENGINE_CONFIG = old_config
                if had_utils:
                    sys.modules["kaggle_environments.utils"] = previous_utils
                else:
                    sys.modules.pop("kaggle_environments.utils", None)
                if had_package:
                    sys.modules["kaggle_environments"] = previous_package
                else:
                    sys.modules.pop("kaggle_environments", None)

    def test_undeclared_engine_file_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            module_path = root / "synthetic_engine.py"
            config_path = root / "kaggriculture.json"
            other_path = root / "other.json"
            source = (
                "from pathlib import Path\n"
                "VALUE = open(Path(__file__).with_name('other.json')).read()\n"
            ).encode("utf-8")
            config_path.write_text("captured", encoding="utf-8")
            other_path.write_text("ambient", encoding="utf-8")

            with self.assertRaises(C.CheckError):
                C.load_captured(
                    "_rowshed_undeclared_open_control",
                    module_path,
                    source,
                    text_captures={config_path: config_path.read_bytes()},
                )


if __name__ == "__main__":
    unittest.main()
