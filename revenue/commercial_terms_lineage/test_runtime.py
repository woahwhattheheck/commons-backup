from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import runtime
from lineage import TermsLineageError, canonical_bytes
from test_lineage import NOW, authority_one, authority_two, review_for


def current_review(auth=None, posture="NO_EXCEPTIONS_CERTIFICATION_REQUIRED"):
    """Production-current fixture with one immutable evidence digest per decision."""
    auth = auth or authority_one()
    review = review_for(auth, posture=posture)
    for index, row in enumerate(review["decisions"]):
        row["evidence_sha256"] = hashlib.sha256(
            f"{row['decision_id']}:{row['term_id']}:{index}".encode("utf-8")
        ).hexdigest()
    return review


class RuntimeBoundaryTests(unittest.TestCase):
    def test_public_current_apis_have_no_time_override(self):
        self.assertNotIn("as_of", inspect.signature(runtime.compile_current).parameters)
        self.assertNotIn("trusted_now", inspect.signature(runtime.verify_current).parameters)

    def test_compile_current_uses_private_process_clock(self):
        auth = authority_one()
        review = current_review(auth)
        fixed = datetime(2026, 9, 13, 13, 45, 0, tzinfo=timezone.utc)
        with mock.patch("runtime._utc_now", return_value=fixed):
            receipt = runtime.compile_current(auth, review)
        self.assertEqual(receipt["compiled_at"], "2026-09-13T13:45:00Z")
        self.assertEqual(receipt["state"], "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW")

    def test_verify_current_rejects_future_receipt_without_caller_clock_escape(self):
        auth = authority_one()
        review = current_review(auth)
        future = datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc)
        with mock.patch("runtime._utc_now", return_value=future):
            receipt = runtime.compile_current(auth, review)
        with mock.patch("runtime._utc_now", return_value=NOW):
            with self.assertRaisesRegex(TermsLineageError, "future"):
                runtime.verify_current(auth, review, receipt)

    def test_verify_current_recomputes_source_freshness_after_historical_clear(self):
        auth = authority_one()
        auth["max_source_age_days"] = 1
        review = current_review(auth)
        with mock.patch("runtime._utc_now", return_value=NOW):
            receipt = runtime.compile_current(auth, review)
        self.assertEqual(receipt["state"], "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW")
        later = NOW + timedelta(days=2)
        with mock.patch("runtime._utc_now", return_value=later):
            current = runtime.verify_current(auth, review, receipt)
        self.assertEqual(current["state"], "SOURCE_REFRESH_REQUIRED")
        self.assertNotEqual(current["compiled_at"], receipt["compiled_at"])
        self.assertTrue(any(reason.startswith("ACTIVE_TERM_SOURCE_STALE:") for reason in current["reasons"]))

    def test_verify_current_recomputes_decision_freshness_after_historical_clear(self):
        auth = authority_one()
        auth["max_decision_age_days"] = 1
        review = current_review(auth)
        with mock.patch("runtime._utc_now", return_value=NOW):
            receipt = runtime.compile_current(auth, review)
        self.assertEqual(receipt["state"], "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW")
        later = NOW + timedelta(days=2)
        with mock.patch("runtime._utc_now", return_value=later):
            current = runtime.verify_current(auth, review, receipt)
        self.assertEqual(current["state"], "OWNER_DECISION_REQUIRED")
        self.assertNotEqual(current["compiled_at"], receipt["compiled_at"])

    def test_current_review_rejects_replayed_evidence_digest_across_terms(self):
        auth = authority_one()
        review = current_review(auth)
        review["decisions"][1]["evidence_sha256"] = review["decisions"][0]["evidence_sha256"]
        with mock.patch("runtime._utc_now", return_value=NOW):
            with self.assertRaisesRegex(TermsLineageError, "evidence replay"):
                runtime.compile_current(auth, review)

    def test_current_authority_rejects_source_captured_after_issuance(self):
        auth = authority_one()
        auth["sources"][0]["captured_at"] = "2026-09-13T12:06:00Z"
        with mock.patch("runtime._utc_now", return_value=NOW):
            with self.assertRaisesRegex(TermsLineageError, "captured after authority issuance"):
                runtime.compile_current(auth, current_review(auth))

    def test_current_authority_rejects_nonmonotone_generation_issuance(self):
        previous = authority_one()
        auth = authority_two(previous)
        auth["issued_at"] = "2026-09-13T12:04:00Z"
        review = current_review(auth)
        for row in review["decisions"]:
            row["decided_at"] = "2026-09-13T13:05:00Z"
        with mock.patch("runtime._utc_now", return_value=NOW):
            with self.assertRaisesRegex(TermsLineageError, "issuance regressed"):
                runtime.compile_current(auth, review, previous_authority=previous)

    def test_current_decision_must_follow_authoritative_source_generation_custody(self):
        previous = authority_one()
        auth = authority_two(previous)
        review = current_review(auth)
        for row in review["decisions"]:
            row["decided_at"] = "2026-09-13T13:05:00Z"
        target = next(row for row in review["decisions"] if row["term_id"] == "mfn")
        target["decided_at"] = "2026-09-13T12:59:00Z"
        with mock.patch("runtime._utc_now", return_value=NOW):
            with self.assertRaisesRegex(TermsLineageError, "predates authoritative source-generation custody"):
                runtime.compile_current(auth, review, previous_authority=previous)

    def test_active_noncontrolling_unreviewed_source_cannot_green(self):
        auth = authority_one()
        base = next(row for row in auth["sources"] if row["source_id"] == "base")
        base["controlling"] = False
        base["reviewed"] = False
        with mock.patch("runtime._utc_now", return_value=NOW):
            receipt = runtime.compile_current(auth, current_review(auth))
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")
        self.assertIn("ACTIVE_TERM_SOURCE_UNREVIEWED:base", receipt["reasons"])

    def test_active_noncontrolling_stale_source_cannot_green(self):
        auth = authority_one()
        auth["max_source_age_days"] = 1
        base = next(row for row in auth["sources"] if row["source_id"] == "base")
        base["controlling"] = False
        base["captured_at"] = "2026-09-01T00:00:00Z"
        with mock.patch("runtime._utc_now", return_value=NOW):
            receipt = runtime.compile_current(auth, current_review(auth))
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")
        self.assertIn("ACTIVE_TERM_SOURCE_STALE:base", receipt["reasons"])

    def test_regular_file_swap_between_lstat_and_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "authority.json"
            replacement = root / "replacement.json"
            target.write_bytes(canonical_bytes(authority_one()))
            forged = deepcopy(authority_one())
            forged["authority_id"] = "forged-authority"
            replacement.write_bytes(canonical_bytes(forged))
            real_open = os.open
            swapped = False

            def racing_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if not swapped and Path(path) == target:
                    replacement.replace(target)
                    swapped = True
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch("runtime.os.open", side_effect=racing_open):
                with self.assertRaisesRegex(TermsLineageError, "path generation changed"):
                    runtime.read_json_file(target)

    def test_in_read_generation_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "authority.json"
            target.write_bytes(canonical_bytes(authority_one()))
            real_read = os.read
            mutated = False

            def racing_read(fd, count):
                nonlocal mutated
                chunk = real_read(fd, count)
                if chunk and not mutated:
                    mutated = True
                    with target.open("ab") as handle:
                        handle.write(b" ")
                return chunk

            with mock.patch("runtime.os.read", side_effect=racing_read):
                with self.assertRaisesRegex(TermsLineageError, "changed while being read"):
                    runtime.read_json_file(target)

    def test_write_exclusive_handles_short_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            real_write = os.write

            def short_write(fd, data):
                return real_write(fd, data[:3] if len(data) > 3 else data)

            with mock.patch("runtime.os.write", side_effect=short_write):
                runtime.write_exclusive(out, "abcdefghijk")
            self.assertEqual(out.read_text(encoding="utf-8"), "abcdefghijk")

    def test_write_exclusive_refuses_existing_and_symlink_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "existing.txt"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(TermsLineageError, "overwrite"):
                runtime.write_exclusive(existing, "new")
            link = root / "link.txt"
            try:
                link.symlink_to(existing)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(TermsLineageError):
                runtime.write_exclusive(link, "new")
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
