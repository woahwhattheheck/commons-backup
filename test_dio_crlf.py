#!/usr/bin/env python3
"""DIO CRLF leftover pins receipt-bound paths and fail-closes unknown Titan size."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "host"))

from dio_crlf import (
    ALREADY_LANDED,
    CALIBRATION,
    PINNED_PATHS,
    REQUIRED_PHRASES,
    SEARCH_SPACE,
    SLACK_TS,
    classify,
    hash_pair,
    load_catalog,
    measure_from_rows,
    measure_root,
    pinned_attr_lines,
)
from titan_append_guard import refuse_further_append


class TestDioCrlf(unittest.TestCase):
    def test_unmeasured_is_not_stillness(self):
        row = classify({})
        self.assertEqual(row["state"], "UNMEASURED")
        self.assertIn("not stillness", row["note"])

    def test_failed_calibration_is_instrument_failure(self):
        verdict = classify(
            {
                "measured": True,
                "calibration_ok": False,
                "calibration_hits": [],
                "card_present": True,
                "catalog_present": True,
            }
        )
        self.assertEqual(verdict["state"], "UNMEASURED")
        self.assertIn("instrument failure", verdict["note"])
        self.assertIn("never 0", verdict["note"].lower())

    def test_missing_paths_are_not_landed(self):
        measured = measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": ["ground/DIO_CRLF.md"],
                "calibration_ok": True,
            }
        )
        self.assertEqual(classify(measured)["state"], "NOT_LANDED")

    def test_unpinned_paths_are_not_landed(self):
        measured = measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "pinned_paths": [],
                "hash_ok": True,
                "crlf_named": True,
                "unknown_size_fail_closed": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
        verdict = classify(measured)
        self.assertEqual(verdict["state"], "NOT_LANDED")
        self.assertIn("-text", verdict["note"])

    def test_complete_leftover_is_integrated(self):
        measured = measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "pinned_paths": list(PINNED_PATHS),
                "hash_ok": True,
                "crlf_named": True,
                "unknown_size_fail_closed": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
        verdict = classify(measured)
        self.assertEqual(verdict["state"], "INTEGRATED")
        self.assertIn("still not the file", verdict["note"])

    def test_receipt_hashes_and_crlf_expansion_match_jojo(self):
        with open(os.path.join(ROOT, "ground", "DIO_CRLF.json"), encoding="utf-8") as handle:
            catalog = load_catalog(handle.read())
        by_path = {row["path"]: row for row in catalog["artifacts"]}
        self.assertEqual(set(by_path), set(PINNED_PATHS))
        lineage = by_path["bazaar/results/cursor-bazaar-lineage-seed0-20260822-01.json"]
        circuits = by_path["excerpts/20260823/grbn_circuits.json"]
        self.assertEqual(lineage["bytes"], 773)
        self.assertEqual(lineage["crlf_bytes"], 798)
        self.assertTrue(circuits["sha256"].startswith("15c2a25"))
        self.assertTrue(circuits["crlf_sha256"].startswith("e4cc1524"))
        for path in PINNED_PATHS:
            with open(os.path.join(ROOT, path), "rb") as handle:
                raw = handle.read()
            got = hash_pair(raw)
            want = by_path[path]
            self.assertEqual(got["bytes"], want["bytes"], path)
            self.assertEqual(got["sha256"], want["sha256"], path)
            self.assertEqual(got["crlf_bytes"], want["crlf_bytes"], path)
            self.assertEqual(got["crlf_sha256"], want["crlf_sha256"], path)
            self.assertEqual(got["crlf_count"], 0, path)

    def test_gitattributes_pins_exact_minus_text(self):
        with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as handle:
            attr = handle.read()
        self.assertEqual(sorted(pinned_attr_lines(attr)), sorted(PINNED_PATHS))

    def test_autocrlf_checkout_stays_lf_when_pinned(self):
        sample = PINNED_PATHS[0]
        with open(os.path.join(ROOT, sample), "rb") as handle:
            raw = handle.read()
        self.assertNotIn(b"\r\n", raw)
        with tempfile.TemporaryDirectory(prefix="dio-crlf-") as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(repo)
            dest = os.path.join(repo, os.path.basename(sample))
            with open(dest, "wb") as handle:
                handle.write(raw)
            def git(*args, check=True):
                return subprocess.run(
                    ["git", "-C", repo, *args],
                    check=check,
                    capture_output=True,
                    text=True,
                )
            git("init")
            git("config", "user.email", "rivet@example.invalid")
            git("config", "user.name", "RIVET")
            git("config", "core.autocrlf", "true")
            git("add", os.path.basename(sample))
            git("commit", "-m", "sample")
            os.remove(dest)
            git("checkout", "--", os.path.basename(sample))
            with open(dest, "rb") as handle:
                expanded = handle.read()
            self.assertGreater(len(expanded), len(raw))
            self.assertIn(b"\r\n", expanded)
            with open(dest, "wb") as handle:
                handle.write(raw)
            with open(os.path.join(repo, ".gitattributes"), "w", encoding="utf-8") as handle:
                handle.write("%s -text\n" % os.path.basename(sample))
            git("add", ".gitattributes")
            git("add", "--renormalize", os.path.basename(sample))
            git("commit", "-m", "pin -text")
            os.remove(dest)
            git("checkout", "--", os.path.basename(sample))
            with open(dest, "rb") as handle:
                pinned = handle.read()
            self.assertEqual(pinned, raw)
            self.assertEqual(hashlib.sha256(pinned).hexdigest(), hashlib.sha256(raw).hexdigest())

    def test_unknown_live_size_fail_closes(self):
        packet = {"claimed_append_base": 100, "claimed_append_end": 108, "written_bytes": 8}
        refused, reason = refuse_further_append(packet, None)
        self.assertTrue(refused)
        self.assertEqual(reason, "no live size")
        refused, reason = refuse_further_append(packet, "not-a-size")
        self.assertTrue(refused)
        self.assertEqual(reason, "live size unreadable")

    def test_live_tree_has_the_leftover(self):
        row = measure_root(ROOT)
        self.assertTrue(row["measured"])
        self.assertTrue(row["calibration_ok"])
        self.assertEqual(row["landed_missing"], [])
        self.assertEqual(sorted(row["pinned_paths"]), sorted(PINNED_PATHS))
        self.assertTrue(row["hash_ok"])
        self.assertTrue(row["crlf_named"])
        self.assertTrue(row["unknown_size_fail_closed"])
        self.assertEqual(row["titan"], "NOT_WRITTEN")
        self.assertEqual(SLACK_TS, "1787650704.417459")
        self.assertEqual(len(CALIBRATION), 3)
        self.assertGreaterEqual(len(SEARCH_SPACE), 7)
        self.assertEqual(classify(row)["state"], "INTEGRATED")

    def test_subzero_receipt_rejects_live_cash_and_contest_append(self):
        path = os.path.join(ROOT, "ground", "SUBZERO_GRBN.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        raw = text.encode("utf-8")
        self.assertNotIn("## Live cash", text)
        self.assertNotIn("## Contest product", text)
        self.assertEqual(len(raw), 1854)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "73926a0e1fc00051ec0b10fc873122b012fc6fb02981d6117d66c38ed8c8119b",
        )


if __name__ == "__main__":
    unittest.main()
