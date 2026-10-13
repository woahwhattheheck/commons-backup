# SPDX-License-Identifier: Apache-2.0
"""Keep release-owned mirrors byte-identical to their live lab counterparts."""
from pathlib import Path
import unittest

import build_integrated


ROOT = Path(__file__).resolve().parent
MIRRORED = (
    "integrated_selected.py",
    "ordered_selected_sell.py",
    "selected_action_sell.py",
    "selected_sell_core.py",
)


class ReleaseMirrorParityTests(unittest.TestCase):
    def test_builder_sources_all_shadowed_modules_from_latest(self):
        mapping = build_integrated.source_files()
        for name in MIRRORED:
            with self.subTest(name=name):
                self.assertEqual(
                    mapping[name],
                    f"reference/titan-current/latest/{name}",
                )

    def test_shadowed_modules_match_live_bytes(self):
        for name in MIRRORED:
            with self.subTest(name=name):
                live = (ROOT / name).read_bytes()
                packaged = (ROOT / "reference/titan-current/latest" / name).read_bytes()
                self.assertEqual(
                    packaged,
                    live,
                    f"packaged {name} drifted from live lab source",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
