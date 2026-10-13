#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from test_release_transaction import ReleaseTransactionTests, rt


class ReleaseOriginInterlockTests(unittest.TestCase):
    def test_valid_replayed_pass_cannot_mutate_pointer_without_external_origin_authority(self):
        fixture = ReleaseTransactionTests(
            methodName="test_pass_is_deterministic_and_binds_all_authorities"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        receipt = fixture.build()
        self.assertEqual(receipt["classification"], "PASS")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pointer = root / "CURRENT-ARCHIVE.json"
            output = root / "TRANSACTION.json"
            pointer.write_bytes(fixture.old_raw)

            with self.assertRaisesRegex(rt.TransactionError, "origin authority"):
                rt.commit_pointer(
                    current_pointer=pointer,
                    expected_old_pointer_raw=fixture.old_raw,
                    approved_new_pointer_raw=fixture.new_raw,
                    receipt_path=output,
                    receipt=receipt,
                )

            self.assertEqual(pointer.read_bytes(), fixture.old_raw)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
