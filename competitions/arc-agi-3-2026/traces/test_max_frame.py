from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core import EpisodeRecorder, decode_frame_record, verify_manifest


class MaximumFrameTests(unittest.TestCase):
    def test_maximum_64x64_frame_compiles_and_verifies(self):
        frame = tuple(tuple((x + y) % 16 for x in range(64)) for y in range(64))
        rec = EpisodeRecorder("max-frame", max_actions=1)
        rec.append_observation((frame,), ("ACTION1",), source_ref="synthetic:max-frame")
        manifest = rec.compile()
        self.assertEqual(decode_frame_record(manifest["events"][0]["payload"]["frames"][0]), frame)
        self.assertEqual(verify_manifest(manifest)["event_count"], 1)


if __name__ == "__main__":
    unittest.main()
