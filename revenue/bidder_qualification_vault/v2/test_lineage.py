from __future__ import annotations

import copy
import unittest

from revenue.bidder_qualification_vault.v2.engine import compile_registry, verify_receipt
from revenue.bidder_qualification_vault.v2.test_support import H, H2, evidence, payload, req

class LineageTests(unittest.TestCase):
    def state(self, p):
        return compile_registry(p)["requirements"][0]["state"]

    def test_future_evidence_conflicts(self):
        ev = evidence("w9-future", "W9", issued="2026-09-15T00:00:00Z", captured="2026-09-15T01:00:00Z")
        self.assertEqual(self.state(payload([ev], [req("r", "W9")])), "CONFLICT")

    def test_future_successor_cannot_make_prior_generation_green(self):
        old = evidence("w9-old", "W9", sha=H)
        future = evidence("w9-future", "W9", sha=H2, supersedes="w9-old",
                          issued="2026-09-15T00:00:00Z", captured="2026-09-15T01:00:00Z")
        self.assertEqual(self.state(payload([old, future], [req("r", "W9")])), "CONFLICT")

    def test_revoked_successor_does_not_resurrect_prior_generation(self):
        old = evidence("w9-old", "W9", sha=H)
        revoked = evidence("w9-new", "W9", sha=H2, supersedes="w9-old", revoked_at="2026-09-10T00:00:00Z")
        self.assertEqual(self.state(payload([old, revoked], [req("r", "W9")])), "SUPERSEDED")

    def test_changed_same_id_conflicts(self):
        a = evidence("same", "W9", sha=H)
        b = evidence("same", "W9", sha=H2)
        self.assertEqual(self.state(payload([a, b], [req("r", "W9")])), "CONFLICT")

    def test_identical_duplicate_id_also_conflicts(self):
        a = evidence("same", "W9", sha=H)
        self.assertEqual(self.state(payload([a, copy.deepcopy(a)], [req("r", "W9")])), "CONFLICT")

    def test_forged_unknown_supersession_conflicts(self):
        ev = evidence("w9-new", "W9", supersedes="does-not-exist")
        self.assertEqual(self.state(payload([ev], [req("r", "W9")])), "CONFLICT")

    def test_backward_dated_successor_cannot_supersede_later_generation(self):
        old = evidence("w9-old", "W9", sha=H, issued="2026-09-10T00:00:00Z", captured="2026-09-10T01:00:00Z")
        forged = evidence("w9-forged-successor", "W9", sha=H2, supersedes="w9-old",
                          issued="2026-09-09T00:00:00Z", captured="2026-09-09T01:00:00Z")
        self.assertEqual(self.state(payload([old, forged], [req("r", "W9")])), "CONFLICT")

    def test_cross_entity_supersession_conflicts(self):
        old = evidence("old", "W9", entity_id="other-company")
        new = evidence("new", "W9", supersedes="old")
        self.assertEqual(self.state(payload([old, new], [req("r", "W9")])), "CONFLICT")

    def test_supersession_fork_conflicts(self):
        old = evidence("old", "W9")
        one = evidence("one", "W9", sha=H2, supersedes="old")
        two = evidence("two", "W9", sha="c" * 64, supersedes="old")
        self.assertEqual(self.state(payload([old, one, two], [req("r", "W9")])), "CONFLICT")

    def test_multiple_current_generations_conflict(self):
        one = evidence("one", "W9", sha=H)
        two = evidence("two", "W9", sha=H2)
        self.assertEqual(self.state(payload([one, two], [req("r", "W9")])), "CONFLICT")

    def test_order_invariance(self):
        evs = [evidence("w9", "W9"), evidence("reg", "REGISTRATION", sha=H2)]
        reqs = [req("r1", "W9"), req("r2", "REGISTRATION")]
        a = compile_registry(payload(evs, reqs))
        b = compile_registry(payload(list(reversed(evs)), list(reversed(reqs))))
        self.assertEqual(a, b)

    def test_receipt_tamper_rejected(self):
        p = payload()
        receipt = compile_registry(p)
        self.assertTrue(verify_receipt(p, receipt))
        receipt["requirements"][0]["state"] = "MISSING"
        self.assertFalse(verify_receipt(p, receipt))
