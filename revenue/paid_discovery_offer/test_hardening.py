from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from revenue.paid_discovery_offer import engine
from revenue.paid_discovery_offer import test_offer as base


class HardeningTests(unittest.TestCase):
    """Additional cross-record and rendering hostiles added during PR self-review."""

    def setUp(self):
        self.now = base.datetime.now(base.timezone.utc).replace(microsecond=0)
        self.c = base.candidate_at(self.now)
        self.r = base.roots_for(self.c, self.now - timedelta(minutes=5))

    def reroot(self, candidate):
        return base.roots_for(candidate, self.now - timedelta(minutes=5))

    def compile(self, candidate=None, roots=None):
        return engine._base_packet(
            engine._validate_candidate(candidate or self.c),
            engine._validate_roots(roots or self.r),
            self.now,
            "CURRENT",
        )

    def assertHold(self, reason, candidate=None, roots=None):
        packet = self.compile(candidate, roots)
        self.assertEqual(engine.HOLD, packet["decision"])
        self.assertIn(reason, packet["reasons"])
        return packet

    def test_upfront_cannot_exceed_total_price(self):
        c = copy.deepcopy(self.c)
        c["proposed_offer"]["upfront_minor"] = c["proposed_offer"]["price_minor"] + 1
        self.assertHold("UPFRONT_EXCEEDS_TOTAL_PRICE", c, self.reroot(c))

    def test_custody_invalid_chronology_holds(self):
        c = copy.deepcopy(self.c)
        c["custody"]["expires_at"] = c["custody"]["acquired_at"]
        self.assertHold("CUSTODY_CHRONOLOGY_INVALID", c, self.reroot(c))

    def test_opportunity_invalid_chronology_holds(self):
        c = copy.deepcopy(self.c)
        c["opportunity"]["valid_until"] = c["opportunity"]["captured_at"]
        self.assertHold("OPPORTUNITY_CHRONOLOGY_INVALID", c, self.reroot(c))

    def test_roots_cannot_predate_rooted_evidence(self):
        r = base.roots_for(self.c, self.now - timedelta(hours=4))
        self.assertHold("AUTHORITY_ROOT_CHRONOLOGY_INVALID", self.c, r)

    def test_policy_invalid_chronology_holds(self):
        c = copy.deepcopy(self.c)
        c["commercial_policy"]["expires_at"] = c["commercial_policy"]["effective_at"]
        self.assertHold("COMMERCIAL_POLICY_CHRONOLOGY_INVALID", c, self.reroot(c))

    def test_mailto_route_in_scope_rejected(self):
        c = copy.deepcopy(self.c)
        c["proposed_offer"]["exclusions"][0] = "Use mailto:ops for details."
        with self.assertRaises(engine.OfferError):
            engine.compile_current(c, self.reroot(c))

    def test_markdown_escapes_public_text_as_literal_content(self):
        c = copy.deepcopy(self.c)
        c["proposed_offer"]["scope_items"][0]["deliverable"] = "Render **not bold** [label](relative) literally."
        p = self.compile(c, self.reroot(c))
        md = engine.markdown(p)
        self.assertIn(r"Render \*\*not bold\*\* \[label\]\(relative\) literally\.", md)

    def test_manifest_receipt_hashes_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "bundle"
            result = engine.write_bundle(str(target), self.compile())
            manifest_bytes = (target / "manifest.json").read_bytes()
            self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), result["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
