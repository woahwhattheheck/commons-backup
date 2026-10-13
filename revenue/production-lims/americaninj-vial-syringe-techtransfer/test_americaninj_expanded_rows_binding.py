#!/usr/bin/env python3
"""Independent fixture/expanded-row custody for American Injectables."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import americaninj_lims as lims  # noqa: E402

FIXTURE = HERE / "fixtures" / "americaninj_120_records.json"
MANIFEST = HERE / "fixtures" / "manifest.json"
EXPECTED_FIXTURE_SHA256 = "f87034d97c3e96477d3a2e03e90a8e006317acc124d3af07717d18b82b0132ae"
EXPECTED_EXPANDED_RECORDS_SHA256 = "53f4951064ae6b5e4a866ad48fc123a4021df28236645fd046eac640231910e0"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class AmericanInjectablesExpandedRowsBindingTests(unittest.TestCase):
    def test_compact_fixture_and_expanded_rows_are_independently_frozen(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(120, manifest["records"])
        self.assertEqual(FIXTURE.name, manifest["fixture"])
        self.assertEqual(EXPECTED_FIXTURE_SHA256, manifest["fixture_sha256"])
        self.assertEqual(
            EXPECTED_EXPANDED_RECORDS_SHA256,
            manifest["expanded_records_sha256"],
        )

        self.assertEqual(
            EXPECTED_FIXTURE_SHA256,
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        )

        expanded = lims.load_fixture(FIXTURE)
        self.assertEqual(120, len(expanded))
        self.assertEqual(
            EXPECTED_EXPANDED_RECORDS_SHA256,
            hashlib.sha256(_canonical_bytes(expanded)).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
