"""Attributed vendor copies must match SOURCE_MANIFEST git blobs.

leftover Live cash belongs on product README pages, not on unmodified
upstream Autopsy markdown. Leftover remints of vendor/*.md fail autopsy-agent
at verify_vendor.py; this unittest is the in-suite regression for that break.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
PINNED_MD = {
    "vendor/autopsy/report-template.md": "7fc28f9092affd72e2039b7cf59266fa6fe0d553",
    "vendor/autopsy/RUNBOOK.md": "66de6e3f2b5b65fe8bdb458ebd23200808aa0274",
}


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class VendorBlobTests(unittest.TestCase):
    def test_manifest_pins_unmodified_autopsy_markdown(self):
        by_path = {item["local_path"]: item["git_blob"] for item in MANIFEST["upstream_files"]}
        for path, pin in PINNED_MD.items():
            self.assertEqual(by_path[path], pin)

    def test_working_tree_matches_manifest_blobs(self):
        for item in MANIFEST["upstream_files"]:
            raw = (ROOT / item["local_path"]).read_bytes()
            self.assertEqual(blob_id(raw), item["git_blob"], item["local_path"])

    def test_pinned_autopsy_markdown_has_no_leftover_live_cash(self):
        for path in PINNED_MD:
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn("## Live cash", text, path)


if __name__ == "__main__":
    unittest.main()
