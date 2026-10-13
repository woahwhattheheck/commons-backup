#!/usr/bin/env python3
"""Regression tests for the human-access lifecycle evidence review.

Organized around the order's completion bar:

* `PolicyIsNotProofTests`   -- a written policy establishes nothing about a case.
  The hard requirement.
* `ReachedTheSystemTests`   -- a closed ticket is not a system state, and a stale
  observation is not an observation of the change.
* `PerSystemTests`          -- status is per system and never rolled up.
* `ScenarioTests`           -- the contractor departure and changed
  responsibilities the order names.
* `HostileInputTests`       -- malformed input is refused by name.

Run:  python3 -m unittest -v test_access_lifecycle.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

import access_lifecycle
from access_lifecycle import (
    ACTION_RECORDED,
    APPROVED_ONLY,
    CONFIRMED_IN_SYSTEM,
    CONTRADICTED_IN_SYSTEM,
    LEAVER,
    LIFECYCLE_EVENTS,
    MOVER,
    NO_EVIDENCE,
    POLICY_ONLY,
    REQUESTED_ONLY,
    STATUS_RANK,
    AccessReviewError,
    Case,
    load_cases,
    read_json,
    render_matrix,
    render_scenarios,
    review_all,
    review_case,
    to_csv_rows,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "lifecycle_cases.json")

POLICY = {
    "kind": "written_policy",
    "statement": "a standard requires removal on the last working day",
}


def make_case(**overrides):
    payload = {
        "case_id": "CASE-T-01",
        "lifecycle_event": "leaver",
        "worker_type": "staff",
        "event_on": "2026-01-10",
        "summary": "test case",
        "access_changes": [
            {
                "system": "sysA",
                "environment": "development",
                "intent": "revoke",
                "entitlement": "an entitlement",
                "effective_on": "2026-01-10",
            }
        ],
        "evidence": [],
    }
    payload.update(overrides)
    return Case(payload)


def status_of(case, system="sysA"):
    record = review_case(case)
    return next(r for r in record["per_system"] if r["system"] == system)


def fixture_result():
    return review_all(load_cases(read_json(FIXTURE)))


def case_named(result, case_id):
    return next(r for r in result["cases"] if r["case_id"] == case_id)


def system_row(record, system, intent=None):
    rows = [r for r in record["per_system"] if r["system"] == system]
    if intent is not None:
        rows = [r for r in rows if r["intent"] == intent]
    return rows[0]


# ---------------------------------------------------------------------------
# The hard requirement
# ---------------------------------------------------------------------------


class PolicyIsNotProofTests(unittest.TestCase):
    """A written policy is evidence about an intent, not about a case."""

    def test_a_policy_alone_yields_policy_only_and_no_conclusion(self):
        """The single most important assertion in this suite."""
        case = make_case(evidence=[POLICY])
        row = status_of(case)
        self.assertEqual(row["status"], POLICY_ONLY)
        self.assertTrue(row["conclusion_rests_on_policy_alone"])
        self.assertIn("not a record of what happened here", row["what_would_settle_it"])
        self.assertIn("not evidence about this case", row["status_meaning"])

    def test_more_policies_do_not_improve_the_conclusion(self):
        """Volume of policy is still zero evidence about the case."""
        many = [dict(POLICY, statement=f"standard {i}") for i in range(10)]
        self.assertEqual(status_of(make_case(evidence=many))["status"], POLICY_ONLY)

    def test_policy_only_is_distinct_from_no_evidence(self):
        """Both yield no conclusion, but they are different situations.

        Collapsing them would lose the fact that a standard exists and was not
        followed up, which is a different conversation from no standard at all.
        """
        self.assertNotEqual(POLICY_ONLY, NO_EVIDENCE)
        self.assertEqual(status_of(make_case(evidence=[]))["status"], NO_EVIDENCE)
        self.assertEqual(status_of(make_case(evidence=[POLICY]))["status"], POLICY_ONLY)

    def test_a_policy_never_lifts_a_case_specific_conclusion(self):
        """Adding a policy to a request does not make it an approval."""
        request = {
            "kind": "ticket_request",
            "system": "sysA",
            "statement": "request raised",
            "observed_on": "2026-01-09",
        }
        without = status_of(make_case(evidence=[request]))["status"]
        with_policy = status_of(make_case(evidence=[request, POLICY]))["status"]
        self.assertEqual(without, REQUESTED_ONLY)
        self.assertEqual(with_policy, REQUESTED_ONLY)

    def test_the_fixture_contains_a_policy_only_case(self):
        result = fixture_result()
        self.assertGreaterEqual(result["counts"]["cases_resting_on_policy_alone"], 1)
        leaver2 = case_named(result, "CASE-SYN-LEAVER-02")
        for row in leaver2["per_system"]:
            self.assertEqual(row["status"], POLICY_ONLY)

    def test_the_rendered_matrix_states_what_a_policy_establishes(self):
        text = render_matrix(fixture_result())
        self.assertIn("**Nothing about any individual case.**", text)


# ---------------------------------------------------------------------------
# Did the change reach the system?
# ---------------------------------------------------------------------------


class ReachedTheSystemTests(unittest.TestCase):
    def test_a_closed_ticket_is_not_a_system_state(self):
        case = make_case(
            evidence=[
                {
                    "kind": "execution_record",
                    "system": "sysA",
                    "statement": "ticket closed, marked done",
                    "observed_on": "2026-01-10",
                }
            ]
        )
        row = status_of(case)
        self.assertEqual(row["status"], ACTION_RECORDED)
        self.assertNotEqual(row["status"], CONFIRMED_IN_SYSTEM)
        self.assertIn("state has not been observed", row["status_meaning"])

    def test_an_observation_after_the_change_confirms(self):
        case = make_case(
            evidence=[
                {
                    "kind": "system_state_observation",
                    "system": "sysA",
                    "statement": "account listing shows the account gone",
                    "observed_on": "2026-01-15",
                    "matches_intent": True,
                }
            ]
        )
        self.assertEqual(status_of(case)["status"], CONFIRMED_IN_SYSTEM)

    def test_an_observation_before_the_change_is_excluded_and_listed(self):
        """A stale export is how a change gets 'confirmed' before it happened."""
        case = make_case(
            evidence=[
                {
                    "kind": "execution_record",
                    "system": "sysA",
                    "statement": "ticket closed",
                    "observed_on": "2026-01-10",
                },
                {
                    "kind": "system_state_observation",
                    "system": "sysA",
                    "statement": "export offered as proof of removal",
                    "observed_on": "2026-01-05",
                    "matches_intent": True,
                },
            ]
        )
        row = status_of(case)
        self.assertEqual(row["status"], ACTION_RECORDED)
        self.assertEqual(len(row["evidence_excluded_as_stale"]), 1)
        self.assertIn(
            "cannot show the change reached the system",
            row["evidence_excluded_as_stale"][0]["why_excluded"],
        )

    def test_a_contradicting_observation_outranks_every_paper_record(self):
        case = make_case(
            evidence=[
                {
                    "kind": "approval_record",
                    "system": "sysA",
                    "statement": "approved",
                    "observed_on": "2026-01-09",
                },
                {
                    "kind": "execution_record",
                    "system": "sysA",
                    "statement": "ticket closed, marked done",
                    "observed_on": "2026-01-10",
                },
                {
                    "kind": "system_state_observation",
                    "system": "sysA",
                    "statement": "role still assigned",
                    "observed_on": "2026-01-20",
                    "matches_intent": False,
                },
            ]
        )
        row = status_of(case)
        self.assertEqual(row["status"], CONTRADICTED_IN_SYSTEM)
        self.assertEqual(STATUS_RANK[CONTRADICTED_IN_SYSTEM], 0)

    def test_an_observation_with_no_recorded_result_cannot_confirm(self):
        """Somebody looked and did not write down what they saw."""
        case = make_case(
            evidence=[
                {
                    "kind": "execution_record",
                    "system": "sysA",
                    "statement": "ticket closed",
                    "observed_on": "2026-01-10",
                },
                {
                    "kind": "system_state_observation",
                    "system": "sysA",
                    "statement": "an export was taken",
                    "observed_on": "2026-01-20",
                },
            ]
        )
        row = status_of(case)
        self.assertEqual(row["status"], ACTION_RECORDED)
        self.assertEqual(len(row["observation_result_not_recorded"]), 1)

    def test_an_entitlement_review_does_not_establish_a_change(self):
        """A review says somebody looked at standing access, nothing more."""
        case = make_case(
            evidence=[
                {
                    "kind": "entitlement_review_record",
                    "system": "sysA",
                    "statement": "quarterly review recorded",
                    "observed_on": "2026-01-20",
                }
            ]
        )
        row = status_of(case)
        self.assertEqual(row["status"], NO_EVIDENCE)
        self.assertEqual(len(row["entitlement_reviews"]), 1)

    def test_stage_order_is_strictly_increasing(self):
        """Each stage must rank above the one before, or the ladder is broken."""
        statuses = [
            (POLICY_ONLY, [POLICY]),
            (
                REQUESTED_ONLY,
                [POLICY, {"kind": "ticket_request", "system": "sysA",
                          "statement": "r", "observed_on": "2026-01-09"}],
            ),
            (
                APPROVED_ONLY,
                [POLICY, {"kind": "approval_record", "system": "sysA",
                          "statement": "a", "observed_on": "2026-01-09"}],
            ),
            (
                ACTION_RECORDED,
                [POLICY, {"kind": "execution_record", "system": "sysA",
                          "statement": "e", "observed_on": "2026-01-10"}],
            ),
            (
                CONFIRMED_IN_SYSTEM,
                [POLICY, {"kind": "system_state_observation", "system": "sysA",
                          "statement": "o", "observed_on": "2026-01-20",
                          "matches_intent": True}],
            ),
        ]
        ranks = []
        for expected, evidence in statuses:
            row = status_of(make_case(evidence=evidence))
            self.assertEqual(row["status"], expected)
            ranks.append(STATUS_RANK[row["status"]])
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(len(set(ranks)), len(ranks))


# ---------------------------------------------------------------------------
# Per-system
# ---------------------------------------------------------------------------


class PerSystemTests(unittest.TestCase):
    def test_a_case_status_is_its_weakest_system_not_an_average(self):
        case = make_case(
            access_changes=[
                {"system": "sysA", "intent": "revoke", "effective_on": "2026-01-10"},
                {"system": "sysB", "intent": "revoke", "effective_on": "2026-01-10"},
                {"system": "sysC", "intent": "revoke", "effective_on": "2026-01-10"},
            ],
            evidence=[
                POLICY,
                {"kind": "system_state_observation", "system": "sysA",
                 "statement": "gone", "observed_on": "2026-01-20",
                 "matches_intent": True},
                {"kind": "system_state_observation", "system": "sysB",
                 "statement": "gone", "observed_on": "2026-01-20",
                 "matches_intent": True},
            ],
        )
        record = review_case(case)
        self.assertEqual(record["case_status"], POLICY_ONLY)
        self.assertEqual(record["systems_not_confirmed"], ["sysC"])
        self.assertIn("weakest system, not an average", record["case_status_basis"])

    def test_evidence_for_one_system_does_not_cover_another(self):
        case = make_case(
            access_changes=[
                {"system": "sysA", "intent": "revoke", "effective_on": "2026-01-10"},
                {"system": "sysB", "intent": "revoke", "effective_on": "2026-01-10"},
            ],
            evidence=[
                {"kind": "system_state_observation", "system": "sysA",
                 "statement": "gone", "observed_on": "2026-01-20",
                 "matches_intent": True}
            ],
        )
        record = review_case(case)
        self.assertEqual(system_row(record, "sysA")["status"], CONFIRMED_IN_SYSTEM)
        self.assertEqual(system_row(record, "sysB")["status"], NO_EVIDENCE)

    def test_two_changes_on_one_system_do_not_share_evidence(self):
        """An elevation's record says nothing about its later removal.

        When a system carries both a grant and a revoke, evidence that does not
        name which it concerns is excluded as ambiguous rather than credited to
        whichever change happens to be nearby.
        """
        case = make_case(
            lifecycle_event="emergency_access",
            access_changes=[
                {"system": "sysA", "intent": "grant", "effective_on": "2026-01-10"},
                {"system": "sysA", "intent": "revoke", "effective_on": "2026-01-11"},
            ],
            evidence=[
                {"kind": "execution_record", "system": "sysA",
                 "statement": "elevation recorded", "observed_on": "2026-01-10"}
            ],
        )
        record = review_case(case)
        grant = system_row(record, "sysA", "grant")
        revoke = system_row(record, "sysA", "revoke")
        self.assertEqual(grant["status"], NO_EVIDENCE)
        self.assertEqual(revoke["status"], NO_EVIDENCE)
        self.assertTrue(grant["evidence_excluded_as_ambiguous"])
        self.assertIn("would be a guess",
                      grant["evidence_excluded_as_ambiguous"][0]["why_excluded"])

    def test_naming_the_intent_attributes_the_evidence(self):
        case = make_case(
            lifecycle_event="emergency_access",
            access_changes=[
                {"system": "sysA", "intent": "grant", "effective_on": "2026-01-10"},
                {"system": "sysA", "intent": "revoke", "effective_on": "2026-01-11"},
            ],
            evidence=[
                {"kind": "execution_record", "system": "sysA", "intent": "grant",
                 "statement": "elevation recorded", "observed_on": "2026-01-10"}
            ],
        )
        record = review_case(case)
        self.assertEqual(
            system_row(record, "sysA", "grant")["status"], ACTION_RECORDED
        )
        self.assertEqual(
            system_row(record, "sysA", "revoke")["status"], NO_EVIDENCE
        )

    def test_csv_has_one_row_per_system_not_per_case(self):
        result = fixture_result()
        rows = to_csv_rows(result)
        self.assertEqual(len(rows) - 1, result["counts"]["systems_reviewed"])
        self.assertGreater(
            result["counts"]["systems_reviewed"], result["counts"]["cases"]
        )

    def test_csv_never_blanks_a_missing_date(self):
        result = fixture_result()
        rows = to_csv_rows(result)
        column = rows[0].index("effective_on")
        for row in rows[1:]:
            self.assertNotEqual(row[column], "")


# ---------------------------------------------------------------------------
# The named scenarios
# ---------------------------------------------------------------------------


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.result = fixture_result()

    def test_a_contractor_departure_is_present(self):
        """Named by the order."""
        self.assertTrue(self.result["coverage"]["contractor_departure_present"])
        case = case_named(self.result, "CASE-SYN-LEAVER-01")
        self.assertEqual(case["lifecycle_event"], LEAVER)
        self.assertEqual(case["worker_type"], "contractor")

    def test_the_contractor_case_shows_one_system_missed(self):
        """The identity account is confirmed gone; the pipeline was never looked at."""
        case = case_named(self.result, "CASE-SYN-LEAVER-01")
        self.assertEqual(
            system_row(case, "central identity provider")["status"],
            CONFIRMED_IN_SYSTEM,
        )
        self.assertEqual(
            system_row(case, "deployment pipeline")["status"], POLICY_ONLY
        )
        self.assertEqual(case["case_status"], POLICY_ONLY)
        self.assertIn("deployment pipeline", case["systems_not_confirmed"])

    def test_changed_responsibilities_is_present(self):
        """Named by the order."""
        self.assertTrue(self.result["coverage"]["changed_responsibilities_present"])
        case = case_named(self.result, "CASE-SYN-MOVER-01")
        self.assertEqual(case["lifecycle_event"], MOVER)

    def test_the_mover_case_shows_grant_confirmed_and_revoke_not(self):
        """Where entitlement accumulates: the grant lands, the revoke drifts."""
        case = case_named(self.result, "CASE-SYN-MOVER-01")
        self.assertEqual(
            system_row(case, "deployment pipeline")["status"], CONFIRMED_IN_SYSTEM
        )
        self.assertEqual(
            system_row(case, "support console")["status"], REQUESTED_ONLY
        )

    def test_all_four_lifecycle_events_are_covered(self):
        self.assertEqual(
            self.result["coverage"]["lifecycle_events_covered"],
            sorted(LIFECYCLE_EVENTS),
        )
        self.assertEqual(self.result["coverage"]["lifecycle_events_missing"], [])

    def test_every_status_is_exercised_by_the_fixture(self):
        seen = set(self.result["counts"]["system_status"])
        self.assertEqual(
            seen,
            {
                POLICY_ONLY,
                REQUESTED_ONLY,
                APPROVED_ONLY,
                ACTION_RECORDED,
                CONFIRMED_IN_SYSTEM,
                CONTRADICTED_IN_SYSTEM,
            },
        )

    def test_scenarios_document_asks_for_records_not_descriptions(self):
        text = render_scenarios(self.result)
        self.assertIn("a description of the process is not evidence", text)
        for case in self.result["cases"]:
            self.assertIn(case["case_id"], text)

    def test_no_scenario_assesses_a_person(self):
        """No case record may characterise an individual.

        `limits` is excluded from the scan because that is where the disclaimer
        lives -- it contains the word "performance" precisely in order to say the
        output does not assess it.
        """
        text = render_scenarios(self.result)
        self.assertIn("No person is assessed", text)
        payload = {k: v for k, v in self.result.items() if k != "limits"}
        blob = json.dumps(payload).lower()
        for banned in ("performance", "negligent", "at fault", "blame",
                       "careless", "failed to follow"):
            self.assertNotIn(banned, blob)
        # And the disclaimer really is present rather than merely absent-by-luck.
        self.assertIn("never an individual's performance",
                      " ".join(self.result["limits"]))


# ---------------------------------------------------------------------------
# Hostile input
# ---------------------------------------------------------------------------


class HostileInputTests(unittest.TestCase):
    def test_an_unrecognized_evidence_kind_is_refused(self):
        with self.assertRaises(AccessReviewError) as ctx:
            make_case(evidence=[{"kind": "someone_said_so", "system": "sysA",
                                 "statement": "s"}])
        self.assertIn("someone_said_so", str(ctx.exception))

    def test_evidence_without_a_system_is_refused_unless_it_is_policy(self):
        with self.assertRaises(AccessReviewError) as ctx:
            make_case(evidence=[{"kind": "execution_record", "statement": "s"}])
        self.assertIn("cannot show a change reached any particular one",
                      str(ctx.exception))
        # A policy legitimately applies to every system.
        make_case(evidence=[POLICY])

    def test_an_undated_system_observation_is_refused(self):
        """An undated export is how a stale one gets read as confirmation."""
        with self.assertRaises(AccessReviewError) as ctx:
            make_case(evidence=[{"kind": "system_state_observation",
                                 "system": "sysA", "statement": "s",
                                 "matches_intent": True}])
        self.assertIn("cannot be shown to post-date the change", str(ctx.exception))

    def test_an_unparseable_date_is_refused(self):
        with self.assertRaises(AccessReviewError) as ctx:
            make_case(event_on="last Tuesday")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_an_invalid_matches_intent_is_refused(self):
        with self.assertRaises(AccessReviewError):
            make_case(evidence=[{"kind": "system_state_observation",
                                 "system": "sysA", "statement": "s",
                                 "observed_on": "2026-01-20",
                                 "matches_intent": "maybe"}])

    def test_an_invalid_evidence_intent_is_refused(self):
        with self.assertRaises(AccessReviewError):
            make_case(evidence=[{"kind": "execution_record", "system": "sysA",
                                 "statement": "s", "observed_on": "2026-01-10",
                                 "intent": "sideways"}])

    def test_an_unknown_lifecycle_event_is_refused(self):
        with self.assertRaises(AccessReviewError):
            make_case(lifecycle_event="promotion")

    def test_a_case_with_no_access_changes_is_refused(self):
        with self.assertRaises(AccessReviewError) as ctx:
            make_case(access_changes=[])
        self.assertIn("nothing to review", str(ctx.exception))

    def test_an_invalid_change_intent_is_refused(self):
        with self.assertRaises(AccessReviewError):
            make_case(access_changes=[{"system": "sysA", "intent": "adjust"}])

    def test_duplicate_case_ids_are_refused(self):
        with self.assertRaises(AccessReviewError) as ctx:
            load_cases({"cases": [
                {"case_id": "C1", "lifecycle_event": "leaver",
                 "access_changes": [{"system": "s", "intent": "revoke"}]},
                {"case_id": "C1", "lifecycle_event": "leaver",
                 "access_changes": [{"system": "s", "intent": "revoke"}]},
            ]})
        self.assertIn("C1", str(ctx.exception))

    def test_malformed_json_names_the_file(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            handle.write("{nope")
            path = handle.name
        try:
            with self.assertRaises(AccessReviewError) as ctx:
                read_json(path)
            self.assertIn(path, str(ctx.exception))
        finally:
            os.unlink(path)

    def test_an_empty_case_list_does_not_crash(self):
        result = review_all([])
        self.assertEqual(result["cases"], [])
        self.assertEqual(
            result["coverage"]["lifecycle_events_missing"], list(LIFECYCLE_EVENTS)
        )
        self.assertFalse(result["coverage"]["contractor_departure_present"])


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
                "--matrix-out": os.path.join(tmp, "m.md"),
                "--scenarios-out": os.path.join(tmp, "s.md"),
            }
            argv = ["--cases", FIXTURE]
            for flag, path in paths.items():
                argv += [flag, path]
            self.assertEqual(access_lifecycle.main(argv), 0)
            bundle = read_json(paths["--json-out"])
            self.assertEqual(
                bundle["content_class"], "SYNTHETIC_NOT_A_UNIVERSITY_FINDING"
            )
            self.assertTrue(bundle["coverage"]["contractor_departure_present"])
            with open(paths["--matrix-out"], encoding="utf-8") as handle:
                self.assertIn("Access-lifecycle evidence matrix", handle.read())
            with open(paths["--scenarios-out"], encoding="utf-8") as handle:
                self.assertIn("role-change scenarios", handle.read())

    def test_cli_reports_a_bad_path_without_a_traceback(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "access_lifecycle.py"),
             "--cases", "/nonexistent/c.json"],
            capture_output=True, text=True, cwd=HERE,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_module_runs_under_python_O(self):
        proc = subprocess.run(
            [sys.executable, "-O", "-m", "unittest",
             "test_access_lifecycle.PolicyIsNotProofTests"],
            capture_output=True, text=True, cwd=HERE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
