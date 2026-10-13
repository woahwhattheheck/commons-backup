"""Synthetic-only regression and CLI tests; no network or production access."""
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("basalt_environment_drift", HERE / "drift.py")
drift = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drift)


def packet():
    current = {"id": "E-current", "kind": "artifact", "captured_on": "2026-09-18",
               "locator": "synthetic/environment-export#current-table"}
    evidence = [current, dict(current, id="E-old", captured_on="2026-08-01"),
                dict(current, id="E-statement", kind="statement"),
                dict(current, id="E-rationale", captured_on="2026-07-01",
                     locator="synthetic/change-record#intentional-differences")]
    observation = lambda value: {"state": "observed", "value": value, "evidence_id": "E-current"}
    def check(ident, group, key, values):
        return {"id": ident, "group": group, "service": group + " fictional service",
                "dimension": "configuration", "key": key,
                "impact": "Hypothesis: this difference may limit the represented test behavior.",
                "owner_role": "Service maintainer", "effort_hours": [1, 4],
                "values": {k: observation(v) for k, v in values.items()}, "intentions": []}
    def rationale(ident, env, value, base, review="2026-10-01"):
        return {"id": ident, "environment": env, "value": value, "baseline_value": base,
                "reason": "Fictional compatibility exercise; isolated reduced environment.",
                "owner_role": "Test-environment maintainer", "evidence_id": "E-rationale",
                "valid_from": "2026-07-01", "review_on": review}
    a = check("ESS-runtime", "ESS", "runtime.major", {"development": 2, "test": 3, "production": 3})
    a["intentions"] = [rationale("R-runtime", "development", 2, 3)]
    b = check("ESS-database", "ESS", "database.major", dict(development=15, test=16, staging=15, production=16))
    b["dimension"] = "dependency"
    b["intentions"] = [rationale("R-db-expired", "staging", 15, 16, "2026-09-01")]
    c = check("RIS-queue", "RIS", "queue.enabled", dict(development=1, staging=True, production=True))
    c["values"]["test"] = {"state": "unknown", "reason": "Export not supplied"}
    d = check("IAM-runtime", "IAM", "provisioner.runtime", dict(development=2, test=3, production=3))
    d["values"]["test"]["evidence_id"] = "E-old"
    d["values"]["staging"] = {"state": "not_applicable", "reason": "Fictional topology has no staging provisioner",
                                "evidence_id": "E-current"}
    d["intentions"] = [rationale("R-iam", "development", 2, 3)]
    e = check("RIS-provisioning", "RIS", "image.revision", dict(development="r2", test="r2", staging="r2", production="r2"))
    e["dimension"] = "provisioning"
    e["values"]["development"]["evidence_id"] = "E-not-supplied"
    e["values"]["test"]["evidence_id"] = "E-statement"
    f = check("ESS-reference-gap", "ESS", "worker.count", dict(development=1, test=2, staging=2))
    g = check("IAM-reference-na", "IAM", "mock.endpoint", dict(development="mock"))
    g["values"]["production"] = {"state": "not_applicable", "reason": "Mock only used in development", "evidence_id": "E-current"}
    g["values"]["test"] = deepcopy(g["values"]["production"])
    return {"schema_version": 1, "label": "SYNTHETIC REHEARSAL — no University evidence or findings",
            "as_of": "2026-09-19", "max_age_days": 14,
            "environments": ["development", "test", "staging", "production"], "baseline": "production",
            "evidence": evidence, "checks": [a, b, c, d, e, f, g]}


def get_row(p, ident="ESS-runtime", env="development"):
    return next(r for r in drift.analyze(p)["comparisons"] if r["check_id"] == ident and r["environment"] == env)


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.p = packet()

    def test_full_fixture(self):
        report = drift.analyze(self.p)
        self.assertEqual(21, report["coverage"]["total_comparisons"])
        self.assertEqual(set(drift.STATUSES), {r["status"] for r in report["comparisons"]})
        self.assertEqual(21, sum(report["counts"].values()))
        self.assertEqual(21, sum(v for k, v in report["coverage"].items() if k != "total_comparisons"))

    def test_intentional(self):
        self.assertEqual("INTENTIONAL_DIFFERENCE", get_row(self.p)["status"])

    def test_aligned(self):
        self.assertEqual("ALIGNED", get_row(self.p, env="test")["status"])

    def test_unexplained(self):
        self.assertEqual("UNEXPLAINED_DIFFERENCE", get_row(self.p, "ESS-database")["status"])

    def test_expired(self):
        self.assertEqual("EXPLANATION_REVIEW_DUE", get_row(self.p, "ESS-database", "staging")["status"])

    def test_bool_is_not_int(self):
        self.assertEqual("UNEXPLAINED_DIFFERENCE", get_row(self.p, "RIS-queue")["status"])

    def test_stale_equal_is_unknown(self):
        row = get_row(self.p, "IAM-runtime", "test")
        self.assertEqual("UNKNOWN", row["status"])
        self.assertIn("target_stale_evidence", row["diagnostics"])

    def test_missing_observation(self):
        self.assertIn("target_missing_observation", get_row(self.p, env="staging")["diagnostics"])

    def test_missing_baseline(self):
        self.assertIn("baseline_missing_observation", get_row(self.p, "ESS-reference-gap")["diagnostics"])

    def test_missing_evidence(self):
        self.assertIn("target_missing_evidence", get_row(self.p, "RIS-provisioning")["diagnostics"])

    def test_statement_is_not_observation(self):
        self.assertIn("target_statement_only", get_row(self.p, "RIS-provisioning", "test")["diagnostics"])

    def test_not_applicable(self):
        self.assertEqual("NOT_APPLICABLE", get_row(self.p, "IAM-runtime", "staging")["status"])

    def test_not_comparable(self):
        self.assertEqual("NOT_COMPARABLE", get_row(self.p, "IAM-reference-na")["status"])

    def test_rationale_changed_baseline(self):
        self.p["checks"][0]["values"]["production"]["value"] = 4
        self.assertIn("rationale_values_mismatch", get_row(self.p)["diagnostics"])

    def test_rationale_missing_artifact(self):
        self.p["checks"][0]["intentions"][0]["evidence_id"] = "absent"
        self.assertEqual("UNEXPLAINED_DIFFERENCE", get_row(self.p)["status"])

    def test_rationale_future(self):
        self.p["checks"][0]["intentions"][0]["valid_from"] = "2026-09-20"
        self.assertEqual("UNEXPLAINED_DIFFERENCE", get_row(self.p)["status"])

    def test_rationale_end_inclusive(self):
        self.p["checks"][0]["intentions"][0]["review_on"] = self.p["as_of"]
        self.assertEqual("INTENTIONAL_DIFFERENCE", get_row(self.p)["status"])

    def test_conflicting_rationales(self):
        r = deepcopy(self.p["checks"][0]["intentions"][0]); r["id"] = "R-other"
        self.p["checks"][0]["intentions"].append(r)
        self.assertEqual("UNKNOWN", get_row(self.p)["status"])

    def test_objects_order_insensitive(self):
        c = self.p["checks"][0]
        c["values"]["development"]["value"] = {"a": 1, "b": 2}
        c["values"]["production"]["value"] = {"b": 2, "a": 1}
        self.assertEqual("ALIGNED", get_row(self.p)["status"])

    def test_null_is_observed(self):
        c = self.p["checks"][0]
        c["values"]["development"]["value"] = None
        c["values"]["production"]["value"] = None
        self.assertEqual("ALIGNED", get_row(self.p)["status"])

    def test_age_boundary_inclusive(self):
        self.p["evidence"][0]["captured_on"] = "2026-09-05"
        self.assertEqual("ALIGNED", get_row(self.p, env="test")["status"])

    def test_stale_nonapplicability_unknown(self):
        self.p["checks"][3]["values"]["staging"]["evidence_id"] = "E-old"
        self.assertEqual("UNKNOWN", get_row(self.p, "IAM-runtime", "staging")["status"])

    def test_no_mutation_and_determinism(self):
        original = deepcopy(self.p)
        first = drift.analyze(self.p)
        self.assertEqual(original, self.p)
        self.p["checks"].reverse(); self.p["evidence"].reverse()
        second = drift.analyze(self.p)
        self.assertEqual(first["comparisons"], second["comparisons"])
        self.assertEqual(drift.analyze(original), first)

    def test_duplicate_ids(self):
        for field in ("checks", "evidence"):
            with self.subTest(field=field):
                p = packet(); p[field].append(deepcopy(p[field][0]))
                with self.assertRaises(drift.InputError): drift.analyze(p)

    def test_bad_schema_types(self):
        for field, value in (("schema_version", True), ("max_age_days", True), ("max_age_days", -1),
                             ("baseline", "typo"), ("as_of", "2026-02-30"), ("checks", [])):
            with self.subTest(field=field, value=value):
                p = packet(); p[field] = value
                with self.assertRaises(drift.InputError): drift.analyze(p)

    def test_future_evidence(self):
        self.p["evidence"][0]["captured_on"] = "2026-09-20"
        with self.assertRaises(drift.InputError): drift.analyze(self.p)

    def test_nonfinite_rejected(self):
        for value in (float("nan"), float("inf")):
            self.p["checks"][0]["values"]["test"]["value"] = value
            with self.assertRaises(drift.InputError): drift.analyze(self.p)

    def test_bad_effort(self):
        for value in ([5, 1], [-1, 3], [True, 3]):
            self.p["checks"][0]["effort_hours"] = value
            with self.assertRaises(drift.InputError): drift.analyze(self.p)

    def test_missing_value_and_environment_typo(self):
        del self.p["checks"][0]["values"]["test"]["value"]
        with self.assertRaises(drift.InputError): drift.analyze(self.p)
        self.p = packet(); self.p["checks"][0]["values"]["tset"] = {"state": "unknown", "reason": "typo"}
        with self.assertRaises(drift.InputError): drift.analyze(self.p)

    def test_markdown_escape(self):
        self.p["checks"][0]["service"] = "<script>alert(1)</script>|`x`\nmore"
        output = drift.markdown(drift.analyze(self.p))
        self.assertNotIn("<script>", output)
        self.assertIn("&#124;", output)
        self.assertIn("&#96;", output)
        self.assertIn("E-not-supplied", output)
        self.assertIn("R-runtime", output)

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "packet.json"; target = Path(root) / "report.md"
            source.write_text(json.dumps(self.p), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, drift.main([str(source), "--format", "markdown", "--output", str(target)]))
                self.assertEqual(2, drift.main([str(source), "--output", str(target)]))
                self.assertEqual(2, drift.main([str(source), "--output", str(source)]))
            self.assertEqual(self.p, json.loads(source.read_text()))
            self.assertIn("Follow-up worksheet", target.read_text())

    def test_cli_duplicate_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "bad.json"
            for raw in ('{"schema_version":1,"schema_version":1}', '{"x":NaN}', '{"x":'):
                source.write_text(raw)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(2, drift.main([str(source)]))


if __name__ == "__main__":
    unittest.main()
