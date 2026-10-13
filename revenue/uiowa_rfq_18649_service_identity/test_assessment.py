"""Behavior and misuse regression tests; all examples are fictional metadata."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location("uiowa054_" + name, HERE / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a = module("assessment")
sample_inventory = module("example").sample_inventory


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.data = sample_inventory()

    def identity(self, name="svc-shared"):
        return next(row for row in self.data["identities"] if row["id"] == name)

    def evidence(self, aspect, name="svc-shared"):
        return next(row for row in self.data["evidence"] if row["identity_id"] == name and row["aspect"] == aspect)

    def result(self, name="svc-shared"):
        return next(row for row in a.assess(self.data)["identities"] if row["identity_id"] == name)

    def state(self, aspect, name="svc-shared"):
        return self.result(name)["controls"][aspect]["state"]

    def test_complete_shared_case(self):
        result = self.result()
        self.assertEqual({r["state"] for r in result["controls"].values()}, {"observed", "not_applicable"})
        self.assertEqual(result["affected_groups"], ["ESS", "IAM", "RIS"])
        self.assertTrue(result["shared_direct_dependency"])
        self.assertEqual(len(result["potentially_affected_services"]), 4)

    def test_report_never_authorizes_changes(self):
        report = a.assess(self.data)
        self.assertIs(report["access_changes_authorized"], False)
        self.assertIsNone(report["compliance_verdict"])
        self.assertEqual(report["summary"]["identities"], 6)
        self.assertEqual(sum(report["summary"]["control_states"].values()), 48)

    def test_departed_owner(self):
        self.assertEqual(self.state("ownership", "svc-departed"), "follow_up")
        action = next(x for x in a.assess(self.data)["actions"] if x["id"] == "svc-departed:ownership")
        self.assertEqual(action["accountable_role"], "Service portfolio owner")

    def test_owner_name_is_not_acceptance(self):
        self.evidence("ownership")["kind"] = "procedure"
        self.assertEqual(self.state("ownership"), "documented")

    def test_interview_is_reported(self):
        self.evidence("ownership")["kind"] = "interview"
        self.assertEqual(self.state("ownership"), "reported")

    def test_wrong_owner_record_not_observed(self):
        self.evidence("ownership")["owner_id"] = "role-ess"
        self.assertEqual(self.state("ownership"), "unknown")

    def test_transition_requires_new_owner_acceptance(self):
        self.assertEqual(self.state("transition", "svc-transition"), "documented")
        self.evidence("transition", "svc-transition")["kind"] = "record"
        self.assertEqual(self.state("transition", "svc-transition"), "observed")

    def test_transition_destination_mismatch(self):
        self.identity("svc-transition")["owner_id"] = "role-ess"
        self.assertEqual(self.state("transition", "svc-transition"), "contradictory")

    def test_pre_transition_demo_is_stale(self):
        self.assertEqual(self.state("continuity", "svc-transition"), "stale")
        self.evidence("continuity", "svc-transition")["observed_on"] = "2026-09-01"
        self.assertEqual(self.state("continuity", "svc-transition"), "observed")

    def test_demo_must_bind_continuity_role(self):
        self.evidence("continuity")["owner_id"] = "role-ess"
        self.assertEqual(self.state("continuity"), "unknown")

    def test_record_is_not_continuity_demonstration(self):
        self.evidence("continuity")["kind"] = "record"
        self.assertEqual(self.state("continuity"), "reported")

    def test_same_person_not_distinct_continuity_role(self):
        self.identity()["continuity_owner_id"] = "role-iam"
        self.assertEqual(self.state("continuity"), "follow_up")

    def test_departed_backup(self):
        self.identity()["continuity_owner_id"] = "role-former"
        self.assertEqual(self.state("continuity"), "follow_up")

    def test_retired_with_consumers_conflicts(self):
        self.assertEqual(self.state("retirement", "svc-retired-conflict"), "contradictory")

    def test_empty_consumers_not_clearance(self):
        self.assertEqual(self.state("dependency", "svc-retiring-empty"), "unknown")
        self.assertEqual(self.state("retirement", "svc-retiring-empty"), "unknown")

    def test_retirement_supported_only_after_dependencies(self):
        row = self.identity("svc-retired-conflict")
        row["consumer_ids"] = []
        self.assertEqual(self.state("retirement", row["id"]), "observed")
        self.evidence("dependency", row["id"])["kind"] = "procedure"
        self.assertEqual(self.state("retirement", row["id"]), "unknown")

    def test_retiring_with_consumers_follow_up(self):
        self.identity()["status"] = "retiring"
        self.assertEqual(self.state("retirement"), "follow_up")

    def test_unknown_metadata_not_inferred(self):
        result = self.result("svc-unknown")
        for aspect in ("ownership", "purpose", "privilege", "renewal", "dependency", "continuity"):
            self.assertEqual(result["controls"][aspect]["state"], "unknown")

    def test_contradiction_does_not_expire_or_hide(self):
        row = deepcopy(self.evidence("purpose"))
        row.update(id="ev-old-conflict", observed_on="2020-01-01", result="contradicts")
        self.data["evidence"].append(row)
        self.identity()["purpose"] = None
        self.assertEqual(self.state("purpose"), "contradictory")

    def test_unknown_observation_not_positive(self):
        self.evidence("purpose")["result"] = "unknown"
        self.assertEqual(self.state("purpose"), "unknown")

    def test_stale_boundary_is_inclusive(self):
        cutoff = date.fromisoformat(self.data["as_of"]) - timedelta(days=90)
        self.evidence("purpose")["observed_on"] = cutoff.isoformat()
        self.assertEqual(self.state("purpose"), "observed")
        self.evidence("purpose")["observed_on"] = (cutoff - timedelta(days=1)).isoformat()
        self.assertEqual(self.state("purpose"), "stale")

    def test_review_today_not_overdue(self):
        self.identity()["review_due_on"] = self.data["as_of"]
        self.assertEqual(self.state("renewal"), "observed")
        self.identity()["review_due_on"] = "2026-09-18"
        self.assertEqual(self.state("renewal"), "follow_up")

    def test_expiry_elapsed_is_conflict_not_access_action(self):
        self.identity()["expires_on"] = "2026-09-18"
        self.assertEqual(self.state("renewal"), "contradictory")
        self.assertEqual(self.result()["expiry_days_remaining"], -1)

    def test_cycle_terminates(self):
        self.data["services"][0]["depends_on"] = ["ris-export"]
        self.assertEqual(len(self.result()["potentially_affected_services"]), 4)

    def test_dependency_direction(self):
        self.identity()["consumer_ids"] = ["ris-export"]
        self.assertEqual(self.result()["potentially_affected_services"], ["ris-export"])

    def test_order_independence(self):
        expected = a.assess(self.data)
        rng = random.Random(54019)
        for _ in range(20):
            for key in ("owners", "services", "identities", "evidence"):
                rng.shuffle(self.data[key])
            for row in self.data["identities"]:
                rng.shuffle(row["consumer_ids"])
            self.assertEqual(a.assess(self.data), expected)

    def test_input_not_mutated(self):
        original = deepcopy(self.data)
        a.assess(self.data)
        self.assertEqual(self.data, original)

    def test_empty_inventory_no_false_percentages(self):
        for key in ("owners", "services", "identities", "evidence"):
            self.data[key] = []
        report = a.assess(self.data)
        self.assertEqual(report["identities"], [])
        self.assertEqual(report["actions"], [])
        self.assertEqual(report["summary"]["identities"], 0)

    def test_unknown_fields_rejected_without_echoing_secret(self):
        self.identity()["password"] = "DO-NOT-ECHO-THIS"
        with self.assertRaises(a.InputError) as caught:
            a.assess(self.data)
        self.assertNotIn("DO-NOT-ECHO-THIS", str(caught.exception))

    def test_padded_metadata_length_rejected(self):
        self.identity()["purpose"] = "x" + " " * 501
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_duplicate_ids_and_references(self):
        self.data["owners"].append(deepcopy(self.data["owners"][0]))
        with self.assertRaises(a.InputError):
            a.assess(self.data)
        self.data = sample_inventory()
        self.identity()["consumer_ids"] *= 2
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_unresolved_references(self):
        mutations = [lambda d: d["identities"][0].update(owner_id="missing"),
                     lambda d: d["services"][0].update(depends_on=["missing"]),
                     lambda d: d["evidence"][0].update(identity_id="missing")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = sample_inventory()
                mutate(data)
                with self.assertRaises(a.InputError):
                    a.assess(data)

    def test_boolean_age_not_integer(self):
        self.data["evidence_max_age_days"] = True
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_future_observation_rejected(self):
        self.evidence("purpose")["observed_on"] = "2026-09-20"
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_future_transition_rejected(self):
        self.identity("svc-transition")["owner_transition"]["effective_on"] = "2026-09-20"
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_strict_dates(self):
        for invalid in ("20260919", "2026-02-30", "2026-09-19T00:00:00Z", True, 17, None):
            with self.subTest(value=invalid):
                self.data["as_of"] = invalid
                with self.assertRaises(a.InputError):
                    a.assess(self.data)

    def test_enum_container_types_fail_cleanly(self):
        for key in ("kind", "aspect", "result"):
            data = sample_inventory()
            data["evidence"][0][key] = []
            with self.subTest(key=key), self.assertRaises(a.InputError):
                a.assess(data)

    def test_active_departure_metadata_rejected(self):
        self.data["owners"][0]["departure_on"] = "2026-09-01"
        with self.assertRaises(a.InputError):
            a.assess(self.data)

    def test_markdown_escapes_role_markup(self):
        self.data["owners"][2]["role"] = "<script>alert(1)</script>|`role`"
        self.identity()["purpose"] = None
        result = a.markdown(a.assess(self.data))
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("&#124;", result)

    def test_every_action_has_role_effort_and_dependencies(self):
        for action in a.assess(self.data)["actions"]:
            self.assertTrue(action["accountable_role"])
            self.assertIn(action["effort"], ("small", "medium"))
            self.assertIsInstance(action["depends_on"], list)
            self.assertTrue(action["next_step"])

    def test_cli_roundtrip_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "input.json", Path(directory) / "report.json"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            self.assertEqual(a.main([str(source), "--output", str(target)]), 0)
            self.assertEqual(json.loads(target.read_text()), a.assess(self.data))
            before = target.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(a.main([str(source), "--output", str(target)]), 2)
            self.assertEqual(before, target.read_bytes())

    def test_invalid_input_creates_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "input.json", Path(directory) / "report.json"
            source.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(a.main([str(source), "--output", str(target)]), 2)
            self.assertFalse(target.exists())

    def test_bad_json_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            for raw in (b"\xff", b"{", b"NaN", b"Infinity", b"[" * 2000):
                source.write_bytes(raw)
                with self.subTest(raw=raw[:10]), self.assertRaises(a.InputError):
                    a.load(source)

    def test_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_bytes(b" " * (a.MAX_BYTES + 1))
            with self.assertRaises(a.InputError):
                a.load(source)

    def test_cli_markdown_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(a.main([str(source), "--format", "markdown"]), 0)
            self.assertEqual(out.getvalue(), a.markdown(a.assess(self.data)))

    def test_actual_subprocess_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(HERE / "assessment.py"), str(source)], capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), a.assess(self.data))


if __name__ == "__main__":
    unittest.main()
