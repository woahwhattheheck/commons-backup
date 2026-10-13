# SPDX-License-Identifier: Apache-2.0
"""Fail closed when a live current-runtime source outruns its release mirror."""
from pathlib import Path
import unittest

import build_integrated


ROOT = Path(__file__).resolve().parent
MIRRORED = (
    'integrated_selected.py',
    'selected_action_sell.py',
    'selected_sell_core.py',
    'ordered_selected_sell.py',
)


class CurrentReleaseMirrorParityTests(unittest.TestCase):
    def test_every_current_release_mirror_is_exact_live_bytes(self):
        mapping = build_integrated.source_files()
        for name in MIRRORED:
            mirror = f'reference/titan-current/latest/{name}'
            with self.subTest(name=name):
                self.assertEqual(mapping.get(name), mirror)
                self.assertEqual((ROOT / name).read_bytes(),
                                 (ROOT / mirror).read_bytes())

    def test_mirror_set_matches_builder_current_remaps(self):
        prefix = 'reference/titan-current/latest/'
        remapped = {
            archive_name: source.removeprefix(prefix)
            for archive_name, source in build_integrated.source_files().items()
            if source.startswith(prefix)
        }
        self.assertEqual(remapped, {name: name for name in MIRRORED})


if __name__ == '__main__':
    unittest.main(verbosity=2)
