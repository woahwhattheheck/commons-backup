from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core import EpisodeRecorder, verify_manifest


class SageContractCompatibilityTests(unittest.TestCase):
    def test_symbolic_action_suffix_matches_landed_sage_action_star_contract(self):
        rec = EpisodeRecorder("symbolic-action", max_actions=1)
        rec.append_observation((((0,),),), ("ACTION_MOVE",), source_ref="synthetic:sage-contract")
        rec.append_action("ACTION_MOVE")
        rec.append_observation((((1,),),), ("ACTION_MOVE",), state="WIN", source_ref="synthetic:sage-contract")
        self.assertEqual(verify_manifest(rec.compile())["action_count"], 1)


if __name__ == "__main__":
    unittest.main()
