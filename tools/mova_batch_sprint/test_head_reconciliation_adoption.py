import unittest

from plan import apply_head_reconciliation

OLD = "a" * 40
NEW = "b" * 40


def record(observed=NEW, touched=None):
    return {
        "issue_url": "https://github.com/example/project/issues/12",
        "repo": "example/project",
        "number": 12,
        "operation_id": "MOVA-example-project-12-OWNER_CONTINUES",
        "take_operation_id": "SOURCE-OP-AAA1",
        "take_paths": ["src/validation"],
        "take_head": OLD,
        "active_owner": "peer-a",
        "source_pr_url": None,
        "pr_url": None,
        "action": "OWNER_CONTINUES",
        "reason": "existing owner",
        "lease_recovery": {
            "branch": "work/issue-12",
            "expected_head": OLD,
            "observed_head": observed,
            "touched_paths": ["src/validation/parser.ts"] if touched is None else touched,
            "comparison_complete": True,
            "stale": True,
            "provider_readback": "compare-receipt-123",
            "origin": "coordination-receipt-123",
            "source": "branch:work/issue-12",
            "completion_proof": None,
        },
    }


class AdoptionTests(unittest.TestCase):
    def test_overlap_stops_duplicate_dispatch(self):
        current = record()
        apply_head_reconciliation(current)
        self.assertEqual(current["action"], "COLLISION_RECONCILIATION")
        self.assertEqual(current["take_head"], OLD)

    def test_disjoint_advance_rebases_next_head(self):
        current = record(touched=["docs/notes.md"])
        apply_head_reconciliation(current)
        self.assertEqual(current["action"], "OWNER_CONTINUES")
        self.assertEqual(current["take_head"], NEW)

    def test_unchanged_stale_head_routes_to_recovery(self):
        current = record(observed=OLD, touched=[])
        apply_head_reconciliation(current)
        self.assertEqual(current["action"], "STALE_RECOVERY")
        self.assertEqual(current["take_head"], OLD)


if __name__ == "__main__":
    unittest.main()
