from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import deploy_transport_preflight.preflight as preflight_module  # noqa: E402
from deploy_transport_preflight.preflight import (  # noqa: E402
    DomainError,
    HOLD_AMBIGUOUS,
    HOLD_UNBOUND,
    READY,
    canonical_bytes,
    compile_bytes,
    compile_values,
    strict_loads,
    verify_bytes,
)

REPO = "https://github.com/woahwhattheheck/public-commons-sprint-2026"
COMMIT = "1" * 40
DIGEST = "2" * 64
ALT_COMMIT = "3" * 40


def request(provider="netlify", *, project_id=None, source=None):
    if source is None:
        source = {
            "repo": "https://github.com/woahwhattheheck/public-commons-sprint-2026",
            "commit_sha": COMMIT,
            "subdir": "cookie-crumbs",
        }
    return {
        "schema": "deploy-transport-request.v1",
        "provider": provider,
        "source": source,
        "target": {"project_id": project_id},
    }


def manifest(provider, *actions):
    return {
        "schema": "deploy-transport-capability-manifest.v1",
        "provider": provider,
        "actions": list(actions),
    }


def action(name, kind, source_binding):
    return {"name": name, "kind": kind, "source_binding": source_binding}


def binding(provider="netlify", project_id="site-123", source=None):
    if source is None:
        source = request(provider)["source"]
    return {
        "schema": "deploy-project-binding.v1",
        "provider": provider,
        "project_id": project_id,
        "source": source,
    }


def raw(value):
    return canonical_bytes(value)


class PreflightTests(unittest.TestCase):
    def test_current_netlify_surface_holds_without_project_binding(self):
        m = json.loads((HERE / "fixtures/netlify_current.json").read_text())
        report = compile_values(request("netlify"), m)
        self.assertEqual(report["status"], HOLD_UNBOUND)
        self.assertEqual(report["viable_paths"], [])
        self.assertIn("create-new-project:ACTION_HAS_NO_SOURCE_BINDING", report["blockers"])
        self.assertIn("deploy-site:PROJECT_BINDING_MISSING", report["blockers"])
        self.assertTrue(all(value is False for value in report["external_authority"].values()))

    def test_current_vercel_surface_holds_without_project_binding(self):
        m = json.loads((HERE / "fixtures/vercel_current.json").read_text())
        report = compile_values(request("vercel"), m)
        self.assertEqual(report["status"], HOLD_UNBOUND)
        self.assertIn("deploy-current-project:PROJECT_BINDING_MISSING", report["blockers"])

    def test_repo_plus_immutable_commit_is_ready(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        report = compile_values(req, m)
        self.assertEqual(report["status"], READY)
        self.assertEqual(report["viable_paths"], ["deploy-repo"])
        self.assertEqual(report["source_identity"]["commit_sha"], COMMIT)

    def test_repo_subdir_requires_explicit_subdir_binding(self):
        req = request("netlify")
        plain = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        held = compile_values(req, plain)
        self.assertEqual(held["status"], HOLD_UNBOUND)
        self.assertIn("deploy-repo:REQUEST_SUBDIR_UNBOUND", held["blockers"])
        exact = manifest("netlify", action("deploy-subdir", "DEPLOY_REPO_SUBDIR", "repo_commit_subdir"))
        ready = compile_values(req, exact)
        self.assertEqual(ready["status"], READY)
        self.assertEqual(ready["viable_paths"], ["deploy-subdir"])

    def test_artifact_and_file_bundle_paths_are_machine_bound_separately(self):
        art = compile_values(
            request("host", source={"artifact_sha256": DIGEST}),
            manifest("host", action("deploy-artifact", "DEPLOY_ARTIFACT", "artifact_sha256")),
        )
        self.assertEqual(art["status"], READY)
        bundle = compile_values(
            request("host", source={"file_bundle_sha256": "4" * 64}),
            manifest("host", action("deploy-bundle", "DEPLOY_FILE_BUNDLE", "file_bundle_sha256")),
        )
        self.assertEqual(bundle["status"], READY)

    def test_multiple_independent_source_identities_rejected(self):
        req = request("host", source={"artifact_sha256": DIGEST, "file_bundle_sha256": "4" * 64})
        m = manifest("host", action("deploy-artifact", "DEPLOY_ARTIFACT", "artifact_sha256"))
        with self.assertRaises(DomainError):
            compile_values(req, m)

    def test_exact_existing_project_binding_is_ready(self):
        req = request("netlify", project_id="site-123")
        m = manifest("netlify", action("deploy-site", "DEPLOY_EXISTING_PROJECT", "existing_project_binding"))
        report = compile_values(req, m, binding())
        self.assertEqual(report["status"], READY)
        self.assertEqual(report["viable_paths"], ["deploy-site"])
        self.assertIsNotNone(report["binding_sha256"])

    def test_same_project_different_commit_holds(self):
        req = request("netlify", project_id="site-123")
        different = binding(source={
            "repo": req["source"]["repo"],
            "commit_sha": ALT_COMMIT,
            "subdir": req["source"]["subdir"],
        })
        m = manifest("netlify", action("deploy-site", "DEPLOY_EXISTING_PROJECT", "existing_project_binding"))
        report = compile_values(req, m, different)
        self.assertEqual(report["status"], HOLD_UNBOUND)
        self.assertIn("deploy-site:PROJECT_BINDING_SOURCE_MISMATCH", report["blockers"])

    def test_cross_provider_binding_holds(self):
        req = request("netlify", project_id="site-123")
        m = manifest("netlify", action("deploy-site", "DEPLOY_EXISTING_PROJECT", "existing_project_binding"))
        report = compile_values(req, m, binding(provider="vercel"))
        self.assertEqual(report["status"], HOLD_UNBOUND)
        self.assertIn("deploy-site:PROJECT_BINDING_PROVIDER_MISMATCH", report["blockers"])

    def test_branch_only_is_not_immutable(self):
        req = request(
            "netlify",
            source={
                "repo": "https://github.com/woahwhattheheck/public-commons-sprint-2026",
                "branch": "main",
            },
        )
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        report = compile_values(req, m)
        self.assertEqual(report["status"], HOLD_UNBOUND)
        self.assertIn("REQUEST_SOURCE_NOT_IMMUTABLE", report["blockers"])
        self.assertIn("deploy-repo:REQUEST_REPO_COMMIT_MISSING", report["blockers"])

    def test_unknown_binding_is_ambiguous_not_ready(self):
        m = manifest("netlify", action("deploy-magic", "DEPLOY_REPO", "free_form_source"))
        report = compile_values(request("netlify"), m)
        self.assertEqual(report["status"], HOLD_AMBIGUOUS)
        self.assertIn("deploy-magic:UNKNOWN_SOURCE_BINDING", report["blockers"])

    def test_contradictory_kind_and_binding_is_ambiguous(self):
        m = manifest("netlify", action("deploy-site", "DEPLOY_EXISTING_PROJECT", "repo_commit"))
        report = compile_values(request("netlify"), m)
        self.assertEqual(report["status"], HOLD_AMBIGUOUS)
        self.assertIn("deploy-site:CONTRADICTORY_ACTION_BINDING", report["blockers"])

    def test_manifest_provider_mismatch_is_ambiguous(self):
        m = manifest("vercel", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        report = compile_values(request("netlify"), m)
        self.assertEqual(report["status"], HOLD_AMBIGUOUS)
        self.assertIn("MANIFEST_PROVIDER_MISMATCH", report["blockers"])

    def test_manifest_freshness_policy_fails_closed(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        req["manifest_policy"] = {"evaluation_epoch": 1000, "max_age_seconds": 100}
        fresh = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        fresh["captured_at_epoch"] = 950
        self.assertEqual(compile_values(req, fresh)["status"], READY)

        stale = dict(fresh)
        stale["captured_at_epoch"] = 899
        stale_report = compile_values(req, stale)
        self.assertEqual(stale_report["status"], HOLD_AMBIGUOUS)
        self.assertIn("MANIFEST_STALE", stale_report["blockers"])

        missing = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        missing_report = compile_values(req, missing)
        self.assertEqual(missing_report["status"], HOLD_AMBIGUOUS)
        self.assertIn("MANIFEST_FRESHNESS_UNKNOWN", missing_report["blockers"])

        future = dict(fresh)
        future["captured_at_epoch"] = 1001
        future_report = compile_values(req, future)
        self.assertEqual(future_report["status"], HOLD_AMBIGUOUS)
        self.assertIn("MANIFEST_CAPTURED_IN_FUTURE", future_report["blockers"])

    def test_report_tamper_rejected_by_exact_recompile(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        report = compile_values(req, m)
        verify_bytes(raw(req), raw(m), raw(report))
        report["status"] = HOLD_UNBOUND
        with self.assertRaises(DomainError):
            verify_bytes(raw(req), raw(m), raw(report))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(DomainError):
            strict_loads(b'{"schema":"a","schema":"b"}')

    def test_nonfinite_and_float_rejected(self):
        for payload in (b'{"x":NaN}', b'{"x":1.25}'):
            with self.assertRaises(DomainError):
                strict_loads(payload)

    def test_huge_integer_rejected(self):
        with self.assertRaises(DomainError):
            strict_loads(b'{"x":9007199254740992}')

    def test_lone_surrogate_rejected(self):
        with self.assertRaises(DomainError):
            strict_loads(b'{"x":"\\ud800"}')

    def test_raw_nested_json_depth_fails_closed_before_decoder_recursion(self):
        nested_array = ("[" * 80 + "0" + "]" * 80).encode("ascii")
        nested_object = ('{"x":' * 80 + "0" + "}" * 80).encode("ascii")
        for payload in (nested_array, nested_object):
            self.assertLess(len(payload), preflight_module.MAX_INPUT_BYTES)
            with self.assertRaisesRegex(DomainError, "JSON depth limit exceeded"):
                strict_loads(payload)

    def test_direct_canonicalization_depth_fails_closed(self):
        value = 0
        for _ in range(preflight_module.MAX_JSON_DEPTH + 1):
            value = [value]
        with self.assertRaisesRegex(DomainError, "JSON depth limit exceeded"):
            canonical_bytes(value)

    def test_wide_direct_values_hit_node_budget(self):
        wide_list = [0] * preflight_module.MAX_JSON_NODES
        with self.assertRaisesRegex(DomainError, "JSON node limit exceeded"):
            canonical_bytes(wide_list)
        wide_dict = {"k%05d" % i: 0 for i in range(preflight_module.MAX_JSON_NODES // 2)}
        with self.assertRaisesRegex(DomainError, "JSON node limit exceeded"):
            canonical_bytes(wide_dict)

    def test_compile_values_bounds_direct_input_before_schema_work(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        for i in range(preflight_module.MAX_JSON_NODES // 2):
            req["extra_%05d" % i] = 0
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        with self.assertRaisesRegex(DomainError, "JSON node limit exceeded"):
            compile_values(req, m)

    def test_external_authority_is_source_literal_and_verify_is_type_sensitive(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        original = preflight_module.EXTERNAL_AUTHORITY_FALSE
        original_snapshot = dict(original)
        try:
            original["deploy_authorized"] = True
            original["provider_authenticated"] = True
            compiled = compile_values(req, m)
            self.assertTrue(
                all(type(value) is bool and value is False for value in compiled["external_authority"].values())
            )

            preflight_module.EXTERNAL_AUTHORITY_FALSE = {
                key: True for key in original_snapshot
            }
            rebound = compile_values(req, m)
            self.assertTrue(
                all(type(value) is bool and value is False for value in rebound["external_authority"].values())
            )
            verify_bytes(raw(req), raw(m), raw(rebound))

            tampered = json.loads(raw(rebound))
            tampered["external_authority"]["deploy_authorized"] = 0
            with self.assertRaisesRegex(DomainError, "report does not exactly recompile"):
                verify_bytes(raw(req), raw(m), raw(tampered))
        finally:
            original.clear()
            original.update(original_snapshot)
            preflight_module.EXTERNAL_AUTHORITY_FALSE = original

    def test_bool_cannot_alias_project_id(self):
        req = request("netlify")
        req["target"]["project_id"] = True
        m = manifest("netlify", action("deploy-site", "DEPLOY_EXISTING_PROJECT", "existing_project_binding"))
        with self.assertRaises(DomainError):
            compile_values(req, m)

    def test_canonical_repo_url_rejects_query_and_userinfo(self):
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        for repo in (
            "https://github.com/a/b?ref=x",
            "https://user@github.com/a/b",
            "https://github.com/a/b/",
        ):
            req = request("netlify", source={"repo": repo, "commit_sha": COMMIT})
            with self.assertRaises(DomainError):
                compile_values(req, m)

    def test_cli_nested_json_returns_typed_domain_failure_without_traceback(self):
        script = HERE / "preflight.py"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            reqp = td / "request.json"
            manp = td / "manifest.json"
            outp = td / "report.json"
            reqp.write_bytes(("[" * 80 + "0" + "]" * 80).encode("ascii"))
            manp.write_bytes(raw(manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))))
            run = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "compile",
                    "--request",
                    str(reqp),
                    "--manifest",
                    str(manp),
                    "--out",
                    str(outp),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 2)
            self.assertIn("JSON depth limit exceeded", run.stderr)
            self.assertNotIn("Traceback", run.stderr)
            self.assertFalse(outp.exists())

    def test_cli_compile_verify_and_overwrite_refusal(self):
        req = request("netlify", source={"repo": REPO, "commit_sha": COMMIT})
        m = manifest("netlify", action("deploy-repo", "DEPLOY_REPO", "repo_commit"))
        script = HERE / "preflight.py"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            reqp, manp, outp = td / "request.json", td / "manifest.json", td / "report.json"
            reqp.write_bytes(raw(req))
            manp.write_bytes(raw(m))
            run = subprocess.run(
                [sys.executable, str(script), "compile", "--request", str(reqp), "--manifest", str(manp), "--out", str(outp)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn(READY, run.stdout)
            verify = subprocess.run(
                [sys.executable, str(script), "verify", "--request", str(reqp), "--manifest", str(manp), "--report", str(outp)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            second = subprocess.run(
                [sys.executable, str(script), "compile", "--request", str(reqp), "--manifest", str(manp), "--out", str(outp)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 2)
            self.assertIn("refusing to overwrite output", second.stderr)


if __name__ == "__main__":
    unittest.main()
