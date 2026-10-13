from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from revenue.outbound_connector_lease.ref_immutability import admin_cutover as cut


HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "ruleset-candidate.json"


def candidate_pair():
    return cut.load_reviewed_candidate(CANDIDATE)


def candidate_doc():
    return candidate_pair()[1]


def detail(ruleset_id=99):
    doc = copy.deepcopy(candidate_doc())
    doc["id"] = ruleset_id
    return doc


class FakeClient:
    def __init__(self, routes):
        self.routes = {key: list(value) for key, value in routes.items()}
        self.calls = []

    def request(self, method, path, payload=None):
        key = (method, path)
        self.calls.append((method, path, copy.deepcopy(payload)))
        if key not in self.routes or not self.routes[key]:
            raise AssertionError(f"unexpected fake API request: {key}")
        item = self.routes[key].pop(0)
        if isinstance(item, Exception):
            raise item
        status, data = item
        return cut.ApiResponse(status, copy.deepcopy(data))


def success_routes(*, existing=False, effective_rules=None, update_status=403,
                   delete_status=403, recreate_status=422, final_sha=None,
                   default_branch="main", parents=True):
    probe_id = "TEST-01"
    branch = cut.PROBE_PREFIX + probe_id
    ref_segment = cut._ref_api_segment(branch)
    branch_segment = cut._branch_api_segment(branch)
    main_sha = "b" * 40
    parent_sha = "a" * 40
    routes = {
        ("GET", f"/repos/{cut.REPOSITORY}/rulesets"): [
            (200, [{"id": 99, "name": cut.RULESET_NAME}] if existing else [])
        ],
        ("GET", f"/repos/{cut.REPOSITORY}/rulesets/99"): [(200, detail())],
        ("GET", f"/repos/{cut.REPOSITORY}"): [
            (200, {"default_branch": default_branch})
        ],
        ("GET", f"/repos/{cut.REPOSITORY}/commits/main"): [
            (
                200,
                {
                    "sha": main_sha,
                    "parents": [{"sha": parent_sha}] if parents else [],
                },
            )
        ],
        ("POST", f"/repos/{cut.REPOSITORY}/git/refs"): [
            (201, {"ref": "refs/heads/" + branch, "object": {"sha": parent_sha}}),
            (recreate_status, {"message": "Reference already exists"}),
        ],
        (
            "GET",
            f"/repos/{cut.REPOSITORY}/rules/branches/{branch_segment}",
        ): [
            (
                200,
                copy.deepcopy(
                    effective_rules
                    if effective_rules is not None
                    else candidate_doc()["rules"]
                ),
            )
        ],
        (
            "PATCH",
            f"/repos/{cut.REPOSITORY}/git/refs/{ref_segment}",
        ): [(update_status, {"message": "blocked"})],
        (
            "DELETE",
            f"/repos/{cut.REPOSITORY}/git/refs/{ref_segment}",
        ): [(delete_status, {"message": "blocked"})],
        (
            "GET",
            f"/repos/{cut.REPOSITORY}/git/ref/{ref_segment}",
        ): [
            (
                200,
                {
                    "ref": "refs/heads/" + branch,
                    "object": {"sha": final_sha or parent_sha},
                },
            )
        ],
    }
    if not existing:
        routes[("POST", f"/repos/{cut.REPOSITORY}/rulesets")] = [
            (201, {"id": 99, "name": cut.RULESET_NAME})
        ]
    return routes


class CandidateTests(unittest.TestCase):
    def test_reviewed_candidate_raw_digest_is_pinned(self):
        raw, doc = candidate_pair()
        self.assertEqual(cut.sha256_hex(raw), cut.EXPECTED_CANDIDATE_RAW_SHA256)
        self.assertEqual(doc["name"], cut.RULESET_NAME)

    def test_candidate_raw_byte_drift_fails_even_when_json_semantics_match(self):
        raw = CANDIDATE.read_bytes() + b" "
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "candidate.json"
            path.write_bytes(raw)
            with self.assertRaisesRegex(cut.CutoverError, "reviewed digest"):
                cut.load_reviewed_candidate(path)

    def test_candidate_bypass_actor_fails(self):
        doc = candidate_doc()
        doc["bypass_actors"] = [{"actor_id": 1}]
        with self.assertRaisesRegex(cut.CutoverError, "bypass"):
            cut.validate_candidate_document(doc)

    def test_candidate_ref_scope_drift_fails(self):
        doc = candidate_doc()
        doc["conditions"]["ref_name"]["include"] = ["refs/heads/*"]
        with self.assertRaisesRegex(cut.CutoverError, "scope drift"):
            cut.validate_candidate_document(doc)

    def test_candidate_missing_mutation_rule_fails(self):
        doc = candidate_doc()
        doc["rules"] = doc["rules"][:2]
        with self.assertRaisesRegex(cut.CutoverError, "exactly three"):
            cut.validate_candidate_document(doc)

    def test_duplicate_json_key_fails(self):
        with self.assertRaisesRegex(cut.CutoverError, "duplicate JSON key"):
            cut.strict_json_loads('{"a":1,"a":2}')

    def test_nonfinite_json_fails(self):
        with self.assertRaisesRegex(cut.CutoverError, "non-finite"):
            cut.strict_json_loads('{"x":NaN}')


class PlanTests(unittest.TestCase):
    def test_plan_is_deterministic_and_fail_closed(self):
        raw, doc = candidate_pair()
        one = cut.build_plan(raw, doc)
        two = cut.build_plan(raw, doc)
        self.assertEqual(cut.canonical_json(one), cut.canonical_json(two))
        self.assertEqual(one["state"], "HOLD_ADMIN_APPLY_REQUIRED")
        self.assertFalse(one["ref_rollback_protection_verified"])
        self.assertFalse(one["branch_create_authority"])
        self.assertFalse(one["production_mutex_complete"])
        self.assertFalse(one["external_send_authorized"])
        self.assertTrue(cut.verify_self_hash(one))

    def test_plan_receipt_tamper_fails(self):
        raw, doc = candidate_pair()
        plan = cut.build_plan(raw, doc)
        plan["state"] = "READY"
        self.assertFalse(cut.verify_self_hash(plan))

    def test_cli_plan_does_not_need_token(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = cut.main(["--candidate", str(CANDIDATE), "plan"])
        self.assertEqual(rc, 0)
        receipt = json.loads(stdout.getvalue())
        self.assertTrue(cut.verify_self_hash(receipt))
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_apply_without_token_holds_before_network(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = cut.main(
                    [
                        "--candidate",
                        str(CANDIDATE),
                        "apply",
                        "--probe-id",
                        "NO-TOKEN",
                    ]
                )
        self.assertEqual(rc, 2)
        self.assertIn("refusing any network/admin mutation", stderr.getvalue())


class ApplyTests(unittest.TestCase):
    def test_apply_create_only_success_proves_only_ref_rollback(self):
        raw, doc = candidate_pair()
        client = FakeClient(success_routes())
        receipt = cut.apply_cutover(client, raw, doc, "TEST-01")
        self.assertEqual(receipt["state"], "REF_ROLLBACK_PROTECTION_VERIFIED")
        self.assertTrue(receipt["ruleset_installed_during_run"])
        self.assertTrue(receipt["ref_rollback_protection_verified"])
        self.assertEqual(receipt["fast_forward_update_status"], 403)
        self.assertEqual(receipt["delete_status"], 403)
        self.assertEqual(receipt["recreate_status"], 422)
        self.assertFalse(receipt["branch_create_authority"])
        self.assertFalse(receipt["production_mutex_complete"])
        self.assertFalse(receipt["external_send_authorized"])
        self.assertTrue(cut.verify_self_hash(receipt))
        methods = [call[0] for call in client.calls]
        self.assertNotIn("PUT", methods)
        self.assertEqual(methods.count("POST"), 3)

    def test_apply_reuses_exact_existing_ruleset_without_mutating_it(self):
        raw, doc = candidate_pair()
        client = FakeClient(success_routes(existing=True))
        receipt = cut.apply_cutover(client, raw, doc, "TEST-01")
        self.assertFalse(receipt["ruleset_installed_during_run"])
        ruleset_posts = [
            call for call in client.calls
            if call[0] == "POST" and call[1].endswith("/rulesets")
        ]
        self.assertEqual(ruleset_posts, [])

    def test_multiple_same_name_rulesets_hold(self):
        raw, doc = candidate_pair()
        routes = success_routes(existing=True)
        routes[("GET", f"/repos/{cut.REPOSITORY}/rulesets")] = [
            (
                200,
                [
                    {"id": 99, "name": cut.RULESET_NAME},
                    {"id": 100, "name": cut.RULESET_NAME},
                ],
            )
        ]
        with self.assertRaisesRegex(cut.CutoverError, "multiple same-name"):
            cut.apply_cutover(FakeClient(routes), raw, doc, "TEST-01")

    def test_existing_ruleset_policy_drift_holds(self):
        raw, doc = candidate_pair()
        routes = success_routes(existing=True)
        bad = detail()
        bad["bypass_actors"] = [{"actor_id": 42}]
        routes[("GET", f"/repos/{cut.REPOSITORY}/rulesets/99")] = [(200, bad)]
        with self.assertRaisesRegex(cut.CutoverError, "bypass"):
            cut.apply_cutover(FakeClient(routes), raw, doc, "TEST-01")

    def test_missing_effective_rule_holds(self):
        raw, doc = candidate_pair()
        effective = [
            {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
            {"type": "non_fast_forward"},
        ]
        with self.assertRaisesRegex(cut.CutoverError, "missing required"):
            cut.apply_cutover(
                FakeClient(success_routes(effective_rules=effective)),
                raw,
                doc,
                "TEST-01",
            )

    def test_fast_forward_update_must_be_blocked(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "update was not host-blocked"):
            cut.apply_cutover(
                FakeClient(success_routes(update_status=200)),
                raw,
                doc,
                "TEST-01",
            )

    def test_delete_must_be_blocked(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "deletion was not host-blocked"):
            cut.apply_cutover(
                FakeClient(success_routes(delete_status=204)),
                raw,
                doc,
                "TEST-01",
            )

    def test_recreate_must_fail_as_existing_ref(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "recreate"):
            cut.apply_cutover(
                FakeClient(success_routes(recreate_status=201)),
                raw,
                doc,
                "TEST-01",
            )

    def test_final_probe_sha_must_remain_original_parent(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "final SHA drifted"):
            cut.apply_cutover(
                FakeClient(success_routes(final_sha="c" * 40)),
                raw,
                doc,
                "TEST-01",
            )

    def test_default_branch_drift_holds(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "default branch drift"):
            cut.apply_cutover(
                FakeClient(success_routes(default_branch="trunk")),
                raw,
                doc,
                "TEST-01",
            )

    def test_missing_parent_holds_before_probe(self):
        raw, doc = candidate_pair()
        with self.assertRaisesRegex(cut.CutoverError, "retained parent"):
            cut.apply_cutover(
                FakeClient(success_routes(parents=False)),
                raw,
                doc,
                "TEST-01",
            )

    def test_create_ruleset_permission_failure_holds(self):
        raw, doc = candidate_pair()
        routes = success_routes()
        routes[("POST", f"/repos/{cut.REPOSITORY}/rulesets")] = [
            (403, {"message": "Resource not accessible"})
        ]
        with self.assertRaisesRegex(cut.CutoverError, "HTTP 403"):
            cut.apply_cutover(FakeClient(routes), raw, doc, "TEST-01")

    def test_invalid_probe_id_holds_before_any_api_call(self):
        raw, doc = candidate_pair()
        client = FakeClient({})
        with self.assertRaisesRegex(cut.CutoverError, "probe_id"):
            cut.apply_cutover(client, raw, doc, "../escape")
        self.assertEqual(client.calls, [])

    def test_effective_update_rule_with_allow_true_holds(self):
        raw, doc = candidate_pair()
        effective = copy.deepcopy(candidate_doc()["rules"])
        effective[0]["parameters"]["update_allows_fetch_and_merge"] = True
        with self.assertRaisesRegex(cut.CutoverError, "permits mutation"):
            cut.apply_cutover(
                FakeClient(success_routes(effective_rules=effective)),
                raw,
                doc,
                "TEST-01",
            )


if __name__ == "__main__":
    unittest.main()
