from __future__ import annotations

import unittest
from pathlib import Path

import postimage_trust as trust


class PostimageControlGenerationTests(unittest.TestCase):
    def test_pinned_control_generation_matches_checkout(self):
        root = Path(__file__).resolve().parent
        manifest, manifest_bytes, paths = trust.verify_control_sources(root)
        self.assertEqual(manifest.get("schema"), "titan-v4-composition/v1")
        self.assertEqual(paths[trust.MANIFEST_NAME], root / trust.MANIFEST_NAME)
        self.assertEqual(trust.git_blob(manifest_bytes), trust.PINNED_CONTROL_BLOBS[trust.MANIFEST_NAME])
        for name, expected in trust.PINNED_CONTROL_BLOBS.items():
            self.assertEqual(
                trust.git_blob((root / name).read_bytes()),
                expected,
                f"{name} changed without rebinding the authenticated postimage generation",
            )


if __name__ == "__main__":
    unittest.main()
