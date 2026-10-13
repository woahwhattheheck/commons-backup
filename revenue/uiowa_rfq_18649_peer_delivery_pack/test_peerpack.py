#!/usr/bin/env python3
"""UIOWA-015 -- tests for the peer delivery pack.

Run:
    python3 -m unittest -v test_peerpack

These enforce the citation discipline. A benchmark pack fails in one
direction: it overstates what peers require, by labelling advisory wording as
mandatory, by citing a source nobody read, or by presenting a policy as proof
of practice. Each of those has a test.
"""

import copy
import json
import os
import subprocess
import sys
import unittest

import peerpack

HERE = os.path.dirname(os.path.abspath(__file__))


def built():
    return peerpack.build(peerpack.load("sources.json"), peerpack.load("cards.json"))


def card(cards, card_id):
    rows = [c for c in cards if c["card_id"] == card_id]
    assert rows, card_id
    return rows[0]


class TestThePackValidatesClean(unittest.TestCase):
    def test_no_validation_problems(self):
        _cards, _sources, problems = built()
        self.assertEqual(problems, [], problems)

    def test_every_card_resolves_to_a_verified_source(self):
        cards, sources, _p = built()
        self.assertTrue(cards)
        for c in cards:
            self.assertEqual(sources[c["source_id"]]["verification"], "VERIFIED", c["card_id"])

    def test_every_card_carries_a_url_and_a_retrieval_date(self):
        cards, _s, _p = built()
        for c in cards:
            self.assertTrue(c["source"]["url"].startswith("https://"), c["card_id"])
            self.assertEqual(c["source"]["retrieved_at"], "2026-09-19", c["card_id"])

    def test_every_card_carries_the_sources_own_words(self):
        cards, _s, _p = built()
        for c in cards:
            self.assertTrue(c["quote"].strip(), c["card_id"])
            self.assertIn(c["obligation_basis"], c["quote"], c["card_id"])


class TestItCannotOverstateWhatPeersRequire(unittest.TestCase):
    def test_advisory_wording_cannot_be_labelled_mandatory(self):
        """A should is not a must. This is the single easiest way a benchmark
        pack misrepresents a peer."""
        sources = peerpack.load("sources.json")
        cards = copy.deepcopy(peerpack.load("cards.json"))
        target = [c for c in cards["cards"] if c["card_id"] == "PC-001"][0]
        self.assertEqual(target["obligation_strength"], "ADVISORY")
        target["obligation_strength"] = "MANDATORY"
        _c, _s, problems = peerpack.build(sources, cards)
        self.assertTrue(any("not a must" in p["problem"] for p in problems), problems)

    def test_a_strength_asserted_on_wording_not_in_the_quote_is_refused(self):
        sources = peerpack.load("sources.json")
        cards = copy.deepcopy(peerpack.load("cards.json"))
        cards["cards"][0]["obligation_basis"] = "must be enforced at all times"
        _c, _s, problems = peerpack.build(sources, cards)
        self.assertTrue(any("does not appear in the quote" in p["problem"] for p in problems))

    def test_the_advisory_cards_are_actually_advisory_in_the_source(self):
        cards, _s, _p = built()
        for c in cards:
            if c["obligation_strength"] == "ADVISORY":
                self.assertTrue(
                    any(m in c["obligation_basis"].lower() for m in peerpack.ADVISORY_MARKERS),
                    "%s claims ADVISORY on wording %r" % (c["card_id"], c["obligation_basis"]))

    def test_both_obligation_strengths_are_represented(self):
        cards, _s, _p = built()
        strengths = set(c["obligation_strength"] for c in cards)
        self.assertIn("MANDATORY", strengths)
        self.assertIn("ADVISORY", strengths)


class TestPolicyIsNotProofOfPractice(unittest.TestCase):
    def test_a_policy_card_is_labelled_as_what_is_published_not_what_is_done(self):
        cards, _s, _p = built()
        for c in cards:
            if c["source"]["source_kind"] == "PUBLISHED_POLICY":
                self.assertIn("publishes as required", c["evidence_of"], c["card_id"])
                self.assertNotIn("actually did", c["evidence_of"], c["card_id"])

    def test_no_card_in_this_pack_claims_reported_implementation(self):
        """Stated as a fact about this pack, and asserted so it cannot change
        without a test failing."""
        cards, _s, _p = built()
        kinds = set(c["source"]["source_kind"] for c in cards)
        self.assertEqual(kinds, {"PUBLISHED_POLICY"})

    def test_the_source_read_with_nothing_relevant_is_recorded_not_dropped(self):
        _c, sources, _p = built()
        rutgers = sources["SRC-RUTGERS-AR"]
        self.assertEqual(rutgers["verification"], "VERIFIED_NO_RELEVANT_CONTENT")
        self.assertIn("not as an absence of practice", rutgers["verification_note"])

    def test_a_source_that_could_not_be_read_carries_no_card_and_no_quote(self):
        sources_doc = copy.deepcopy(peerpack.load("sources.json"))
        for source in sources_doc["sources"]:
            if source["source_id"] == "SRC-UCOP-SSDS":
                source["verification"] = "NOT_VERIFIED"
        cards, sources, problems = peerpack.build(sources_doc, peerpack.load("cards.json"))
        self.assertNotIn("SRC-UCOP-SSDS", [c["source_id"] for c in cards])
        self.assertTrue(any("only a VERIFIED source" in p["problem"] for p in problems))

    def test_a_card_on_an_unverified_source_is_refused(self):
        sources = copy.deepcopy(peerpack.load("sources.json"))
        cards = copy.deepcopy(peerpack.load("cards.json"))
        for s in sources["sources"]:
            if s["source_id"] == "SRC-DSU-1410":
                s["verification"] = "NOT_VERIFIED"
        _c, _s, problems = peerpack.build(sources, cards)
        self.assertTrue(any("only a VERIFIED source" in p["problem"] for p in problems))

    def test_a_draft_document_is_marked_as_a_draft(self):
        cards, sources, _p = built()
        self.assertEqual(sources["SRC-NEU-SDLC"]["document_status"], "DRAFT")
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), [])
        self.assertIn("identifies itself as a draft", text)


class TestQuestionsAskForEvidence(unittest.TestCase):
    def test_every_card_has_at_least_two_transferable_questions(self):
        cards, _s, _p = built()
        for c in cards:
            self.assertGreaterEqual(len(c["transferable_questions"]), 2, c["card_id"])

    def test_every_card_asks_for_a_concrete_artifact_or_instance(self):
        cards, _s, _p = built()
        for c in cards:
            self.assertTrue(
                any(any(m in q.lower() for m in peerpack.CONCRETE_MARKERS)
                    for q in c["transferable_questions"]),
                "%s restates the policy instead of testing it" % c["card_id"])

    def test_the_concreteness_check_proves_it_can_fail(self):
        """It caught a real weakness in PC-004 on the first run. A checker
        that has never gone red is worth nothing."""
        sources = peerpack.load("sources.json")
        cards = copy.deepcopy(peerpack.load("cards.json"))
        cards["cards"][0]["transferable_questions"] = [
            "Do you have a change control policy?",
            "Is it followed?",
        ]
        _c, _s, problems = peerpack.build(sources, cards)
        self.assertTrue(any("restates the policy" in p["problem"] for p in problems))

    def test_a_card_with_one_question_is_refused(self):
        sources = peerpack.load("sources.json")
        cards = copy.deepcopy(peerpack.load("cards.json"))
        cards["cards"][0]["transferable_questions"] = ["Can you show me the last one?"]
        _c, _s, problems = peerpack.build(sources, cards)
        self.assertTrue(any("fewer than two" in p["problem"] for p in problems))


class TestNoPeerIsRanked(unittest.TestCase):
    def test_no_card_ranks_or_praises_a_peer(self):
        """Checked against the card content, not the rendered prose -- the
        pack's own disclaimer says no peer is described as a leader, and
        grepping the whole document would match that sentence."""
        cards, _s, _p = built()
        payload = json.dumps([{k: v for k, v in c.items() if k != "source"}
                              for c in cards]).lower()
        for banned in ("percentile", "leader", "best practice", "best-in-class",
                       "ranking", "benchmark score", "outperform", "ahead of",
                       "world-class", "exemplary"):
            self.assertNotIn(banned, payload, "found %r in the card content" % banned)

    def test_the_pack_carries_no_ordinal_ranking(self):
        cards, sources, _p = built()
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), []).lower()
        for banned in ("#1", "top three", "top 3", "ranked ", "scored ", "out of 5"):
            self.assertNotIn(banned, text, "found %r in the pack" % banned)

    def test_the_pack_states_plainly_that_it_ranks_nobody(self):
        cards, sources, _p = built()
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), [])
        self.assertIn("No peer", text)
        self.assertIn("is ranked, scored, or described as a leader", text)

    def test_the_pack_says_it_is_not_about_the_client(self):
        cards, sources, _p = built()
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), [])
        self.assertIn("Nothing in this pack is a statement about the University of Iowa", text)

    def test_the_pack_states_what_remains_unknown(self):
        cards, sources, _p = built()
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), [])
        self.assertIn("Still UNKNOWN", text)
        self.assertIn("no source checked reports that", text)

    def test_an_uncovered_practice_area_is_not_a_claim_about_peers(self):
        cards, sources, _p = built()
        selected = [c for c in cards if c["practice_area"] != "security_testing"]
        cov = peerpack.coverage(selected, sources)
        self.assertIn("security_testing", cov["uncovered_practice_areas"])
        text = peerpack.render(cards, sources, peerpack.load("sources.json"), [])
        self.assertIn("It does not mean peers have no such practice", text)


class TestDeliverableAndCli(unittest.TestCase):
    def test_the_named_deliverable_is_generated_and_current(self):
        path = os.path.join(HERE, "15-development-peer-pack.md")
        self.assertTrue(os.path.exists(path), "the order names this file")
        with open(path, encoding="utf-8") as fh:
            committed = fh.read()
        cards, sources, problems = built()
        fresh = peerpack.render(cards, sources, peerpack.load("sources.json"), problems)
        self.assertEqual(committed, fresh,
                         "the pack is stale -- regenerate with: python3 peerpack.py --render")

    def test_check_exits_zero_on_the_real_data(self):
        proc = subprocess.run([sys.executable, os.path.join(HERE, "peerpack.py"), "--check"],
                              cwd=HERE, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("problems=0", proc.stderr)

    def test_the_cli_reports_that_no_card_rests_on_implementation(self):
        proc = subprocess.run([sys.executable, os.path.join(HERE, "peerpack.py"), "--render"],
                              cwd=HERE, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("reported_implementation_cards=0", proc.stderr)

    def test_no_network_call_is_made_at_runtime(self):
        """A static tripwire on the source text; the pack is built from local
        JSON only. Retrieval was a separate, dated, human-initiated act."""
        with open(os.path.join(HERE, "peerpack.py"), encoding="utf-8") as fh:
            source = fh.read()
        for banned in ("urllib.request", "import requests", "http.client", "socket."):
            self.assertNotIn(banned, source, "peerpack.py references %s" % banned)

    def test_all_five_organizations_appear_with_distinct_sources(self):
        cards, sources, _p = built()
        cov = peerpack.coverage(cards, sources)
        self.assertEqual(len(cov["organizations"]), 5)
        self.assertEqual(cov["sources_carrying_cards"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
