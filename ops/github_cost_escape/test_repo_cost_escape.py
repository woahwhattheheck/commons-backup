import unittest

from repo_cost_escape import decide, normalize_inventory, plan, render_markdown


class CostEscapeTests(unittest.TestCase):
    def test_sensitive_repo_never_becomes_publish_candidate(self):
        repo = {"repository_full_name": "o/customer", "visibility": "private", "size": 10}
        overlay = {"repositories": {"o/customer": {"classification": "customer", "public_release_reviewed": True}}}
        d = decide(repo, overlay)
        self.assertEqual(d.action, "keep_private")
        self.assertEqual(d.risk, "high")

    def test_private_repo_defaults_to_review_required(self):
        d = decide({"full_name": "o/unknown", "private": True, "size": 50}, {})
        self.assertEqual(d.action, "review_required")

    def test_empty_private_repo_is_retirement_candidate(self):
        d = decide({"full_name": "o/empty", "private": True, "size": 0}, {})
        self.assertEqual(d.action, "empty_private_retirement_candidate")

    def test_retention_blocks_empty_retirement(self):
        repo = {"full_name": "o/evidence", "private": True, "size": 0}
        overlay = {"repositories": {"o/evidence": {"retention_required": True}}}
        self.assertEqual(decide(repo, overlay).action, "review_required")

    def test_public_review_is_explicit_gate(self):
        repo = {"full_name": "o/releasable", "private": True, "size": 7}
        overlay = {"repositories": {"o/releasable": {"public_release_reviewed": True}}}
        self.assertEqual(decide(repo, overlay).action, "publish_safe_candidate")

    def test_split_candidate_without_publish_permission(self):
        repo = {"full_name": "o/split", "private": True, "size": 70}
        overlay = {"repositories": {"o/split": {"separable_public_core": True}}}
        self.assertEqual(decide(repo, overlay).action, "split_public_core_private_data")

    def test_ci_migration_is_independent_of_visibility(self):
        repo = {"full_name": "o/private", "private": True, "size": 70}
        overlay = {"repositories": {"o/private": {"classification": "customer", "hosted_ci_minutes_estimate": 200, "free_external_ci_available": True}}}
        d = decide(repo, overlay)
        self.assertEqual(d.action, "keep_private")
        self.assertEqual(d.ci_action, "migrate_hosted_ci_to_free_external_capacity")

    def test_fanout_consolidation(self):
        repo = {"full_name": "o/private", "private": True, "size": 70}
        overlay = {"repositories": {"o/private": {"hosted_ci_minutes_estimate": 20, "hosted_ci_fanout": 5}}}
        self.assertEqual(decide(repo, overlay).ci_action, "consolidate_hosted_ci_fanout")

    def test_inventory_wrappers(self):
        repos = [{"name": "x"}]
        self.assertEqual(normalize_inventory(repos), repos)
        self.assertEqual(normalize_inventory({"repositories": repos}), repos)
        self.assertEqual(normalize_inventory({"result": {"repositories": repos}}), repos)
        with self.assertRaises(ValueError):
            normalize_inventory({"nope": []})

    def test_priority_puts_reversible_savings_first(self):
        repos = [
            {"full_name": "o/unknown", "private": True, "size": 10},
            {"full_name": "o/empty", "private": True, "size": 0},
            {"full_name": "o/public", "private": False, "size": 10},
        ]
        actions = [d.action for d in plan(repos, {})]
        self.assertEqual(actions[0], "empty_private_retirement_candidate")
        self.assertEqual(actions[-1], "already_public")

    def test_markdown_contains_advisory_guard(self):
        out = render_markdown([decide({"full_name": "o/x", "private": True, "size": 1}, {})])
        self.assertIn("advisory only", out)
        self.assertIn("human approval required", out)


if __name__ == "__main__":
    unittest.main()
