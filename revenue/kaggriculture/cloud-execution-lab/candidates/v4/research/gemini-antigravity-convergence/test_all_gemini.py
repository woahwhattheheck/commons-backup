#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_all_gemini as A
import check_full_coverage as D
import check_labeled_history as L
import check_ledger as C


class AllGeminiCoverageTests(unittest.TestCase):
    def test_required_id_sets_are_disjoint_and_total_37(self):
        master = set(C.REQUIRED_IDS)
        direct = set(D.HISTORICAL_IDS)
        labeled = set(L.REQUIRED_IDS)
        self.assertFalse(master & direct)
        self.assertFalse(master & labeled)
        self.assertFalse(direct & labeled)
        self.assertEqual(len(master | direct | labeled), 37)

    def test_overlap_is_fail_closed(self):
        with patch.object(L, "REQUIRED_IDS", frozenset(set(L.REQUIRED_IDS) | {next(iter(C.REQUIRED_IDS))})):
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                for name in ("GEMINI-ANTIGRAVITY.json", "HISTORICAL-DIRECT.json", "HISTORICAL-LABELED.json"):
                    (base / name).write_text("{}", encoding="utf-8")
                with patch.object(C, "load_strict_json", return_value={}), \
                     patch.object(C, "validate_document", return_value={"entry_count": 21}), \
                     patch.object(D, "validate_history", return_value={"direct_author_messages": 44, "historical_propositions": 4}), \
                     patch.object(L, "validate_document", return_value={"entry_count": 13}), \
                     patch.object(C, "find_repo_root", return_value=base):
                    with self.assertRaisesRegex(C.ConvergenceError, "ID overlap"):
                        A.validate_all(base)

    def test_runtime_authority_is_never_implied(self):
        self.assertEqual(A.TOTAL_DISTINCT, 37)


if __name__ == "__main__":
    unittest.main()
