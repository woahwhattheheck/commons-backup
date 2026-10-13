#!/usr/bin/env python3
"""UIOWA-042 -- tests for requirements-to-acceptance traceability.

Run:
    python3 -m unittest -v test_trace

The order's completion condition is the spec: the examples must include a
changed requirement and incomplete acceptance evidence, "with explicit
follow-up questions rather than invented conclusions".
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

import prompts
import trace as trace_mod
from trace import Example, TraceError, UNKNOWN

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "fixtures", "project_delivery.json")
MAINTENANCE = os.path.join(HERE, "fixtures", "maintenance_change.json")


def example(path):
    return Example(trace_mod.load(path))


def criterion(ex, cid):
    rows = [r for r in ex.results if r["criterion_id"] == cid]
    assert rows, cid
    return rows[0]


def minimal(style="project", **over):
    base = {
        "example_id": "TEST", "delivery_style": style,
        "requests": [{"request_id": "R1", "revision": 1}],
        "criteria": [{"criterion_id": "C1", "request_id": "R1", "revision": 1, "text": "t"}],
        "implementations": [{"impl_id": "I1", "criterion_id": "C1", "ref": "synthetic://x"}],
        "tests": [{"test_id": "T1", "criterion_id": "C1", "ref": "synthetic://y", "result": "PASS"}],
        "acceptances": [{"acceptance_id": "A1", "criterion_id": "C1", "criterion_revision": 1,
                         "accepted_by_role": "role", "accepted_at": "2026-01-01",
                         "evidence_ref": "synthetic://z"}],
    }
    base.update(over)
    return base


class TestTheChangedRequirement(unittest.TestCase):
    """The row still shows a tick. What it records is that somebody accepted
    an EARLIER version of the requirement."""

    def setUp(self):
        self.ex = example(PROJECT)

    def test_acceptance_against_an_earlier_revision_does_not_read_as_traced(self):
        row = criterion(self.ex, "AC-100-01")
        self.assertEqual(row["revision"], 2)
        self.assertEqual(row["state"], "ACCEPTED_AGAINST_SUPERSEDED_REVISION")
        self.assertFalse(row["closed"])

    def test_the_earlier_acceptance_is_not_carried_forward_silently(self):
        row = criterion(self.ex, "AC-100-01")
        self.assertIn("accepted against revision 1", " ".join(row["detail"]))
        self.assertIn("this criterion is at revision 2", " ".join(row["detail"]))

    def test_it_emits_a_question_not_a_conclusion(self):
        row = criterion(self.ex, "AC-100-01")
        self.assertIn("Ask who accepted revision 2", row["follow_up"])
        self.assertIn("do not carry the earlier acceptance forward", row["follow_up"])

    def test_the_same_criterion_traces_once_acceptance_matches_the_revision(self):
        payload = copy.deepcopy(trace_mod.load(PROJECT))
        for acc in payload["acceptances"]:
            if acc["acceptance_id"] == "ACC-100-01":
                acc["criterion_revision"] = 2
        self.assertEqual(criterion(Example(payload), "AC-100-01")["state"], "TRACED")

    def test_a_replaced_criterion_is_superseded_not_failed(self):
        row = criterion(self.ex, "AC-100-04")
        self.assertEqual(row["state"], "SUPERSEDED")
        self.assertTrue(row["closed"])
        self.assertEqual(criterion(self.ex, "AC-100-05")["state"], "TRACED")


class TestIncompleteAcceptanceEvidence(unittest.TestCase):
    """A passing test is evidence the code does what the test says. It is not
    evidence anybody agreed that was the need."""

    def setUp(self):
        self.ex = example(PROJECT)

    def test_passing_tests_with_no_acceptance_record_is_not_acceptance(self):
        row = criterion(self.ex, "AC-100-02")
        self.assertEqual(row["state"], "INCOMPLETE_ACCEPTANCE")
        self.assertIn("tests passing", " ".join(row["detail"]))
        self.assertIn("no user acceptance record", " ".join(row["detail"]))

    def test_an_acceptance_with_no_evidence_locator_is_incomplete(self):
        row = criterion(self.ex, "AC-100-09")
        self.assertEqual(row["state"], "INCOMPLETE_ACCEPTANCE")
        self.assertIn("no evidence locator", " ".join(row["detail"]))

    def test_the_follow_up_says_a_test_is_not_a_substitute(self):
        row = criterion(self.ex, "AC-100-02")
        self.assertIn("A passing test is not a substitute", row["follow_up"])


class TestTheRestOfTheChain(unittest.TestCase):
    def setUp(self):
        self.ex = example(PROJECT)

    def test_a_criterion_with_no_implementation_is_reported(self):
        self.assertEqual(criterion(self.ex, "AC-100-06")["state"], "NOT_IMPLEMENTED")

    def test_a_failing_test_blocks_the_chain(self):
        self.assertEqual(criterion(self.ex, "AC-100-07")["state"], "TEST_NOT_PASSING")

    def test_an_unrun_test_blocks_the_chain(self):
        payload = minimal()
        payload["tests"][0]["result"] = "NOT_RUN"
        self.assertEqual(criterion(Example(payload), "C1")["state"], "TEST_NOT_PASSING")

    def test_implemented_with_no_test_is_untested(self):
        self.assertEqual(criterion(self.ex, "AC-100-08")["state"], "UNTESTED")

    def test_a_clean_chain_traces(self):
        self.assertEqual(criterion(self.ex, "AC-100-03")["state"], "TRACED")

    def test_every_state_carries_a_follow_up(self):
        for r in self.ex.results:
            self.assertTrue(r["follow_up"].strip(), r["criterion_id"])
            self.assertIn(r["state"], trace_mod.FOLLOW_UP)


class TestDeliveryStyles(unittest.TestCase):
    def test_a_maintenance_change_may_declare_regression_coverage(self):
        row = criterion(example(MAINTENANCE), "AC-200-01")
        self.assertEqual(row["state"], "TRACED")
        self.assertIn("declared covered by", " ".join(row["detail"]))

    def test_coverage_must_be_declared_and_is_never_assumed(self):
        """A maintenance change with no test and no declared locator is
        UNTESTED. The tool does not assume an existing suite covers it."""
        payload = minimal(style="maintenance_change", tests=[])
        self.assertEqual(criterion(Example(payload), "C1")["state"], "UNTESTED")

    def test_a_project_cannot_use_the_regression_shortcut(self):
        payload = minimal(style="project", tests=[])
        payload["criteria"][0]["covered_by_regression_ref"] = "synthetic://suite"
        self.assertEqual(criterion(Example(payload), "C1")["state"], "UNTESTED")

    def test_an_unknown_delivery_style_is_refused(self):
        with self.assertRaises(TraceError):
            Example(minimal(style="agile-ish"))

    def test_both_examples_are_present_and_differ_in_verdict(self):
        self.assertEqual(example(MAINTENANCE).verdict(), "EVIDENCED")
        self.assertEqual(example(PROJECT).verdict(), "NOT_ESTABLISHED")


class TestVerdictAndCounts(unittest.TestCase):
    def test_one_open_criterion_keeps_the_verdict_unestablished(self):
        payload = minimal()
        payload["criteria"].append({"criterion_id": "C2", "request_id": "R1",
                                    "revision": 1, "text": "t2"})
        ex = Example(payload)
        self.assertEqual(ex.verdict(), "NOT_ESTABLISHED")
        self.assertEqual([r["criterion_id"] for r in ex.open_criteria()], ["C2"])

    def test_a_fully_traced_example_is_evidenced(self):
        self.assertEqual(Example(minimal()).verdict(), "EVIDENCED")

    def test_an_example_of_only_superseded_criteria_is_not_established(self):
        """Nothing current to check is not the same as everything checked."""
        payload = minimal(acceptances=[], tests=[], implementations=[])
        payload["criteria"] = [{"criterion_id": "C1", "request_id": "R1", "revision": 1,
                                "text": "t", "superseded_by": "C1"}]
        self.assertEqual(Example(payload).verdict(), "NOT_ESTABLISHED")

    def test_an_example_with_no_criteria_is_refused(self):
        with self.assertRaises(TraceError):
            Example(minimal(criteria=[]))

    def test_the_counts_account_for_every_criterion(self):
        ex = example(PROJECT)
        self.assertEqual(sum(ex.counts().values()), len(ex.results))

    def test_no_percentage_or_score_reaches_the_output(self):
        payload = json.dumps(example(PROJECT).as_dict()).lower()
        for banned in ("percent", "score", "maturity", "grade", "ranking", "rating"):
            self.assertNotIn(banned, payload, "found %r in the output" % banned)


class TestBrokenReferences(unittest.TestCase):
    def test_a_criterion_pointing_at_a_missing_request_is_a_broken_link(self):
        payload = minimal()
        payload["criteria"][0]["request_id"] = "R404"
        self.assertEqual(criterion(Example(payload), "C1")["state"], "BROKEN_LINK")

    def test_an_implementation_pointing_at_a_missing_criterion_is_reported(self):
        payload = minimal()
        payload["implementations"].append({"impl_id": "I9", "criterion_id": "C404",
                                           "ref": "synthetic://x"})
        ex = Example(payload)
        refs = [d["ref"] for d in ex.dangling_links()]
        self.assertIn("C404", refs)

    def test_a_broken_link_never_reads_as_traced(self):
        payload = minimal()
        payload["criteria"][0]["superseded_by"] = "C404"
        self.assertEqual(criterion(Example(payload), "C1")["state"], "BROKEN_LINK")

    def test_the_real_examples_have_no_broken_references(self):
        for path in (PROJECT, MAINTENANCE):
            self.assertEqual(example(path).dangling_links(), [], path)


class TestPrompts(unittest.TestCase):
    def test_no_prompt_asks_for_an_unverifiable_rating(self):
        for q in prompts.all_questions():
            self.assertIn(q["seeks"], prompts.ALLOWED_SEEKS, q["id"])
            self.assertNotIn(q["seeks"], prompts.BANNED_SEEKS, q["id"])

    def test_every_prompt_can_be_answered_unknown(self):
        for q in prompts.all_questions():
            self.assertTrue(q["accepts_unknown"], q["id"])
        self.assertIn("UNKNOWN", prompts.RECORDING_RULE)

    def test_every_stage_of_the_chain_has_a_question(self):
        stages = set(q["stage"] for q in prompts.CHAIN_QUESTIONS)
        for stage in ("request", "acceptance_criteria", "implementation",
                      "test", "user_acceptance"):
            self.assertIn(stage, stages, stage)

    def test_every_open_state_has_at_least_one_probe(self):
        for state in trace_mod.STATES:
            if state in trace_mod.CLOSED_STATES:
                continue
            self.assertIn(state, prompts.STATE_PROBES, state)
            self.assertTrue(prompts.STATE_PROBES[state], state)

    def test_probes_fire_for_the_two_required_cases(self):
        generated = prompts.probes_for(example(PROJECT).results)
        ids = [p["id"] for p in generated]
        self.assertIn("P-REV-01", ids)
        self.assertIn("P-ACC-01", ids)

    def test_a_clean_example_draws_no_probes(self):
        self.assertEqual(prompts.probes_for(example(MAINTENANCE).results), [])

    def test_probe_generation_is_deterministic(self):
        results = example(PROJECT).results
        self.assertEqual([p["id"] for p in prompts.probes_for(results)],
                         [p["id"] for p in prompts.probes_for(results)])


class TestOutputsAndCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, "trace.py")] + list(args),
                              cwd=HERE, capture_output=True, text=True)

    def test_the_cli_writes_three_files_and_exits_one_with_open_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("--input", MAINTENANCE, PROJECT, "--outdir", tmp)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            for name in ("traceability_sheet.csv", "traceability.json",
                         "traceability_report.md"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)
            self.assertIn("verdicts=EVIDENCED,NOT_ESTABLISHED", proc.stderr)

    def test_a_fully_traced_example_exits_zero(self):
        proc = self.run_cli("--input", MAINTENANCE)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_malformed_json_exits_two_without_a_traceback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{ nope")
            path = fh.name
        try:
            proc = self.run_cli("--input", path)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("Traceback", proc.stderr)
        finally:
            os.unlink(path)

    def test_the_report_labels_itself_fictional_and_lists_unknowns(self):
        text = trace_mod.render_markdown([example(MAINTENANCE), example(PROJECT)])
        self.assertIn("fictional", text.lower())
        self.assertIn("Still UNKNOWN", text)
        self.assertIn("questions, not conclusions", text)

    def test_the_payload_carries_the_prohibited_interpretations(self):
        meta = example(PROJECT).as_dict()["meta"]
        self.assertTrue(meta["synthetic"])
        self.assertIn("employee performance assessment", meta["prohibited_interpretation"])


class TestCommittedSampleIsNotStale(unittest.TestCase):
    def test_sample_markdown_matches_a_fresh_render(self):
        path = os.path.join(HERE, "sample_output", "traceability_report.md")
        with open(path, encoding="utf-8") as fh:
            committed = fh.read()
        fresh = trace_mod.render_markdown([example(MAINTENANCE), example(PROJECT)])
        self.assertEqual(committed, fresh,
                         "sample_output/ is stale -- regenerate with: python3 trace.py "
                         "--input fixtures/maintenance_change.json fixtures/project_delivery.json "
                         "--outdir sample_output")

    def test_sample_json_matches_a_fresh_run(self):
        path = os.path.join(HERE, "sample_output", "traceability.json")
        with open(path, encoding="utf-8") as fh:
            committed = json.load(fh)
        fresh = json.loads(json.dumps([example(MAINTENANCE).as_dict(),
                                       example(PROJECT).as_dict()], sort_keys=True))
        self.assertEqual(committed, fresh)


if __name__ == "__main__":
    unittest.main(verbosity=2)
