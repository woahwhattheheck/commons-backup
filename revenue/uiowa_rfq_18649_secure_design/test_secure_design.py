#!/usr/bin/env python3
"""Regression tests for the secure-design requirements evidence instrument.

Organized around the order's completion bar:

* `ThreeStatesTests`     -- documented intent, observed practice and unknown stay
  three different things. The hard requirement.
* `StaleTraceTests`      -- traceability survives a requirement change, or is
  reported as stale. The second half of the order.
* `ReferenceFrameTests`  -- SSDF is cited as a reference and never as a
  conformance or certification claim.
* `GapTests`             -- gaps that are not link states.
* `HostileInputTests`    -- malformed input is refused by name.

Run:  python3 -m unittest -v test_secure_design.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

import secure_design
from secure_design import (
    DOCUMENTED_INTENT,
    OBSERVED_PRACTICE,
    SSDF_REFERENCES,
    SSDF_URL,
    STATE_RANK,
    TRACED_STALE,
    UNKNOWN,
    DataFlow,
    DesignDecision,
    Evidence,
    Requirement,
    SecureDesignError,
    assess,
    assess_link,
    load_records,
    read_json,
    render_evidence_chain,
    render_worksheet,
    to_csv_rows,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "secure_design_records.json")


def make_requirement(**overrides):
    payload = {
        "requirement_id": "REQ-T-01",
        "current_version": 1,
        "statement": "a security requirement",
        "ssdf_references": ["PW.1.2"],
    }
    payload.update(overrides)
    return Requirement(payload)


def make_decision(**overrides):
    payload = {
        "decision_id": "DD-T-01",
        "summary": "a design decision",
        "flow_id": "FLOW-T-01",
        "governing_requirements": ["REQ-T-01"],
    }
    payload.update(overrides)
    return DesignDecision(payload)


def make_evidence(index=0, **overrides):
    payload = {
        "evidence_id": f"EV-T-{index:02d}",
        "kind": "design_decision_record",
        "requirement_id": "REQ-T-01",
        "decision_id": "DD-T-01",
        "statement": "an artifact",
        "cites_requirement_version": 1,
    }
    payload.update(overrides)
    return Evidence(payload, index=index)


def link_state(evidence, requirement=None, decision=None):
    return assess_link(
        decision or make_decision(),
        requirement or make_requirement(),
        evidence,
    )


def fixture_result():
    requirements, decisions, flows, evidence = load_records(read_json(FIXTURE))
    return assess(requirements, decisions, flows, evidence)


def link_for(result, decision_id, requirement_id):
    return next(
        l
        for l in result["links"]
        if l["decision_id"] == decision_id
        and l["requirement_id"] == requirement_id
    )


# ---------------------------------------------------------------------------
# The hard requirement
# ---------------------------------------------------------------------------


class ThreeStatesTests(unittest.TestCase):
    """Documented intent, observed practice and unknown are three states."""

    def test_the_three_states_are_distinct(self):
        """The single most important assertion in this suite."""
        self.assertEqual(len({UNKNOWN, DOCUMENTED_INTENT, OBSERVED_PRACTICE}), 3)
        self.assertNotEqual(STATE_RANK[UNKNOWN], STATE_RANK[DOCUMENTED_INTENT])
        self.assertNotEqual(
            STATE_RANK[DOCUMENTED_INTENT], STATE_RANK[OBSERVED_PRACTICE]
        )

    def test_a_standard_alone_is_documented_intent_not_practice(self):
        link = link_state(
            [make_evidence(kind="written_standard", cites_requirement_version=None,
                           decision_id="", requirement_id="REQ-T-01")]
        )
        self.assertEqual(link["state"], DOCUMENTED_INTENT)
        self.assertEqual(link["evidence_observed_practice"], [])
        self.assertIn("says nothing about whether this design decision did it",
                      link["state_meaning"])

    def test_volume_of_intent_does_not_become_practice(self):
        many = [
            make_evidence(
                index=i,
                kind="written_standard",
                cites_requirement_version=None,
                decision_id="",
            )
            for i in range(10)
        ]
        self.assertEqual(link_state(many)["state"], DOCUMENTED_INTENT)

    def test_nothing_at_all_is_unknown_not_a_gap(self):
        link = link_state([])
        self.assertEqual(link["state"], UNKNOWN)
        self.assertIn("not a gap, and not a pass", link["state_meaning"])
        self.assertIn("do not infer one from the standard", link["next_step"])

    def test_a_design_record_at_the_current_version_is_observed_practice(self):
        link = link_state([make_evidence()])
        self.assertEqual(link["state"], OBSERVED_PRACTICE)
        self.assertEqual(len(link["evidence_observed_practice"]), 1)
        self.assertIsNone(link["next_step"])

    def test_practice_evidence_must_name_both_ends_to_count_as_a_trace(self):
        """An artifact naming a requirement but no decision is not a trace.

        It does not tell you this decision considered the requirement, so it is
        reported in its own list rather than credited to every decision.
        """
        link = link_state([make_evidence(decision_id="")])
        self.assertEqual(link["state"], UNKNOWN)
        self.assertEqual(
            len(link["evidence_naming_requirement_but_no_decision"]), 1
        )

    def test_all_four_states_appear_in_the_fixture(self):
        result = fixture_result()
        self.assertEqual(
            set(result["counts"]["by_state"]),
            {UNKNOWN, DOCUMENTED_INTENT, TRACED_STALE, OBSERVED_PRACTICE},
        )

    def test_the_worksheet_states_what_intent_establishes(self):
        text = render_worksheet(fixture_result())
        self.assertIn("It says nothing about whether this design decision did it",
                      text)
        self.assertIn("Ten standards are still zero design records",
                      " ".join(fixture_result()["limits"]))


# ---------------------------------------------------------------------------
# Stale traces
# ---------------------------------------------------------------------------


class StaleTraceTests(unittest.TestCase):
    """Traceability has to survive a requirement change, or say it did not."""

    def test_a_trace_to_a_superseded_version_is_stale_not_traced(self):
        requirement = make_requirement(current_version=3)
        link = link_state([make_evidence(cites_requirement_version=2)],
                          requirement=requirement)
        self.assertEqual(link["state"], TRACED_STALE)
        self.assertEqual(len(link["evidence_stale_trace"]), 1)
        self.assertEqual(link["evidence_observed_practice"], [])

    def test_a_stale_trace_is_not_collapsed_into_untraced(self):
        """It is genuinely neither, so it must rank between the two."""
        self.assertLess(STATE_RANK[UNKNOWN], STATE_RANK[TRACED_STALE])
        self.assertLess(STATE_RANK[TRACED_STALE], STATE_RANK[OBSERVED_PRACTICE])
        self.assertGreater(STATE_RANK[TRACED_STALE], STATE_RANK[DOCUMENTED_INTENT])

    def test_the_stale_next_step_names_the_versions(self):
        requirement = make_requirement(current_version=3)
        link = link_state([make_evidence(cites_requirement_version=2)],
                          requirement=requirement)
        self.assertIn("v2", link["next_step"])
        self.assertIn("v3", link["next_step"])
        self.assertIn("looks fine in a traceability matrix", link["next_step"])

    def test_a_current_trace_beats_a_stale_one_on_the_same_link(self):
        """Somebody revisited the decision; the old citation does not demote it."""
        requirement = make_requirement(current_version=3)
        link = link_state(
            [
                make_evidence(index=0, cites_requirement_version=2),
                make_evidence(index=1, cites_requirement_version=3),
            ],
            requirement=requirement,
        )
        self.assertEqual(link["state"], OBSERVED_PRACTICE)
        self.assertEqual(len(link["evidence_stale_trace"]), 1)

    def test_a_citation_ahead_of_the_register_is_reported_separately(self):
        """Citing v4 when the register says v3 is a bookkeeping problem."""
        requirement = make_requirement(current_version=3)
        link = link_state([make_evidence(cites_requirement_version=4)],
                          requirement=requirement)
        self.assertEqual(link["state"], UNKNOWN)
        self.assertEqual(len(link["evidence_citing_a_future_version"]), 1)

    def test_the_fixture_stale_case_is_the_one_documented(self):
        result = fixture_result()
        link = link_for(result, "DD-SYN-01", "SEC-REQ-SYN-01")
        self.assertEqual(link["state"], TRACED_STALE)
        self.assertEqual(link["requirement_current_version"], 3)
        self.assertEqual(
            link["evidence_stale_trace"][0]["cites_requirement_version"], 2
        )

    def test_an_unversioned_practice_citation_is_refused(self):
        """An uncheckable trace would be reported as current."""
        with self.assertRaises(SecureDesignError) as ctx:
            make_evidence(cites_requirement_version=None)
        self.assertIn("cannot be checked for staleness", str(ctx.exception))

    def test_an_unversioned_requirement_is_refused(self):
        with self.assertRaises(SecureDesignError) as ctx:
            make_requirement(current_version=None)
        self.assertIn("Versions are what make a stale trace detectable",
                      str(ctx.exception))


# ---------------------------------------------------------------------------
# Reference frame
# ---------------------------------------------------------------------------


class ReferenceFrameTests(unittest.TestCase):
    def test_the_ssdf_url_is_cited(self):
        """The order requires the citation."""
        result = fixture_result()
        self.assertEqual(result["reference_frame"]["url"], SSDF_URL)
        self.assertIn("csrc.nist.gov/Projects/ssdf", SSDF_URL)
        self.assertIn(SSDF_URL, render_worksheet(result))
        self.assertIn(SSDF_URL, render_evidence_chain(result))

    def test_no_output_claims_conformance_or_certification(self):
        """SSDF organizes the instrument; it does not grade anything.

        `reference_frame` is excluded from the scan because that is where the
        disclaimer lives -- it contains these words in order to deny them.
        """
        result = fixture_result()
        payload = {k: v for k, v in result.items()
                   if k not in ("reference_frame", "limits")}
        blob = json.dumps(payload).lower()
        for banned in ("compliant", "conformance", "certified", "certification",
                       "attestation", "audit opinion"):
            self.assertNotIn(banned, blob)
        disclaimer = result["reference_frame"]["disclaimer"].lower()
        self.assertIn("no output is a conformance, certification or compliance claim",
                      " ".join(result["limits"]).lower())
        self.assertIn("certification", disclaimer)

    def test_practice_descriptions_are_labelled_as_paraphrase(self):
        """They are written for this worksheet, not quoted from the source."""
        for ref, text in SSDF_REFERENCES.items():
            self.assertTrue(
                text.startswith("PARAPHRASE:"),
                f"{ref} must be labelled a paraphrase",
            )
        disclaimer = fixture_result()["reference_frame"]["disclaimer"]
        self.assertIn("paraphrases", disclaimer)
        self.assertIn("not quotations", disclaimer)

    def test_an_unrecognized_practice_identifier_is_refused(self):
        with self.assertRaises(SecureDesignError) as ctx:
            make_requirement(ssdf_references=["ZZ.9.9"])
        self.assertIn("ZZ.9.9", str(ctx.exception))
        self.assertIn("nobody can look up", str(ctx.exception))

    def test_practice_references_reach_the_output(self):
        result = fixture_result()
        link = link_for(result, "DD-SYN-01", "SEC-REQ-SYN-03")
        self.assertEqual(sorted(link["ssdf_references"]), ["PW.1.1", "PW.2.1"])


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


class GapTests(unittest.TestCase):
    def setUp(self):
        self.result = fixture_result()

    def test_a_requirement_no_decision_cites_is_reported(self):
        """A requirement nothing points at is not satisfied by default."""
        requirements = [make_requirement(), make_requirement(
            requirement_id="REQ-T-02", statement="uncited")]
        result = assess(requirements, [make_decision()], [], [])
        self.assertEqual(
            result["gaps"]["requirements_no_decision_cites"], ["REQ-T-02"]
        )

    def test_a_dangling_requirement_reference_is_not_counted_either_way(self):
        """It cannot be assessed, so it is neither traced nor untraced."""
        dangling = self.result["gaps"]["dangling_requirement_references"]
        self.assertEqual(len(dangling), 1)
        self.assertEqual(dangling[0]["requirement_id"], "SEC-REQ-SYN-99")
        ids = {(l["decision_id"], l["requirement_id"]) for l in self.result["links"]}
        self.assertNotIn(("DD-SYN-04", "SEC-REQ-SYN-99"), ids)

    def test_a_flow_no_requirement_claims_is_reported(self):
        flows = [
            DataFlow({"flow_id": "FLOW-T-09", "description": "unclaimed",
                      "crosses_trust_boundary": True})
        ]
        result = assess([make_requirement()], [make_decision()], flows, [])
        unclaimed = result["gaps"]["flows_no_requirement_claims"]
        self.assertEqual(len(unclaimed), 1)
        self.assertTrue(unclaimed[0]["crosses_trust_boundary"])

    def test_the_fixture_carries_an_unclaimed_trust_boundary_flow(self):
        """A flow crossing a trust boundary with no requirement attached is the
        question worth asking, so the fixture demonstrates one."""
        unclaimed = self.result["gaps"]["flows_no_requirement_claims"]
        self.assertTrue(unclaimed)
        self.assertTrue(any(f["crosses_trust_boundary"] for f in unclaimed))
        self.assertIn("Data flows no requirement claims",
                      render_worksheet(self.result))

    def test_csv_writes_a_word_for_a_missing_flow(self):
        rows = to_csv_rows(self.result)
        column = rows[0].index("flow_id")
        for row in rows[1:]:
            self.assertNotEqual(row[column], "")

    def test_csv_has_one_row_per_link(self):
        rows = to_csv_rows(self.result)
        self.assertEqual(len(rows) - 1, self.result["counts"]["links_assessed"])

    def test_no_individual_is_assessed(self):
        payload = {k: v for k, v in self.result.items() if k != "limits"}
        blob = json.dumps(payload).lower()
        for banned in ("negligent", "at fault", "blame", "incompetent"):
            self.assertNotIn(banned, blob)
        self.assertIn("No individual is assessed", " ".join(self.result["limits"]))


# ---------------------------------------------------------------------------
# Hostile input
# ---------------------------------------------------------------------------


class HostileInputTests(unittest.TestCase):
    def test_an_unrecognized_evidence_kind_is_refused(self):
        with self.assertRaises(SecureDesignError) as ctx:
            make_evidence(kind="somebody_mentioned_it")
        self.assertIn("somebody_mentioned_it", str(ctx.exception))

    def test_a_decision_with_no_governing_requirement_is_refused(self):
        with self.assertRaises(SecureDesignError) as ctx:
            make_decision(governing_requirements=[])
        self.assertIn("nothing to be traced to", str(ctx.exception))

    def test_a_requirement_without_a_statement_is_refused(self):
        with self.assertRaises(SecureDesignError):
            make_requirement(statement="")

    def test_a_zero_or_negative_version_is_refused(self):
        for version in (0, -1, "3", 2.5, True):
            with self.subTest(version=version):
                with self.assertRaises(SecureDesignError):
                    make_requirement(current_version=version)

    def test_duplicate_ids_are_refused(self):
        payload = {
            "requirements": [
                {"requirement_id": "R1", "current_version": 1, "statement": "s"},
                {"requirement_id": "R1", "current_version": 1, "statement": "s"},
            ]
        }
        with self.assertRaises(SecureDesignError) as ctx:
            load_records(payload)
        self.assertIn("R1", str(ctx.exception))

    def test_evidence_without_a_statement_is_refused(self):
        with self.assertRaises(SecureDesignError):
            make_evidence(statement="")

    def test_malformed_json_names_the_file(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            handle.write("{nope")
            path = handle.name
        try:
            with self.assertRaises(SecureDesignError) as ctx:
                read_json(path)
            self.assertIn(path, str(ctx.exception))
        finally:
            os.unlink(path)

    def test_empty_records_do_not_crash(self):
        result = assess([], [], [], [])
        self.assertEqual(result["links"], [])
        self.assertEqual(result["counts"]["links_assessed"], 0)
        self.assertIn("Limits", render_worksheet(result))


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


class EndToEndTests(unittest.TestCase):
    def test_output_is_deterministic(self):
        self.assertEqual(
            json.dumps(fixture_result(), sort_keys=True),
            json.dumps(fixture_result(), sort_keys=True),
        )

    def test_cli_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                "--json-out": os.path.join(tmp, "o.json"),
                "--csv-out": os.path.join(tmp, "o.csv"),
                "--worksheet-out": os.path.join(tmp, "w.md"),
                "--chain-out": os.path.join(tmp, "c.md"),
            }
            argv = ["--records", FIXTURE]
            for flag, path in paths.items():
                argv += [flag, path]
            self.assertEqual(secure_design.main(argv), 0)
            bundle = read_json(paths["--json-out"])
            self.assertEqual(
                bundle["content_class"], "SYNTHETIC_NOT_A_UNIVERSITY_FINDING"
            )
            self.assertEqual(bundle["counts"]["by_state"][TRACED_STALE], 1)
            with open(paths["--worksheet-out"], encoding="utf-8") as handle:
                self.assertIn("Secure-design requirements worksheet", handle.read())
            with open(paths["--chain-out"], encoding="utf-8") as handle:
                self.assertIn("Sample evidence chain", handle.read())

    def test_cli_reports_a_bad_path_without_a_traceback(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "secure_design.py"),
             "--records", "/nonexistent/r.json"],
            capture_output=True, text=True, cwd=HERE,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_module_runs_under_python_O(self):
        proc = subprocess.run(
            [sys.executable, "-O", "-m", "unittest",
             "test_secure_design.ThreeStatesTests"],
            capture_output=True, text=True, cwd=HERE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
