"""Focused, offline regression scenarios for the paid-PR TAKE preflight."""
import unittest

from preflight import assess_take, canonical_pr


def entry(ts, op, action="TAKE", pr="org/repo/pull/12", detail=""):
    return {"ts": str(ts), "user": "peer", "channel": "bug-bounty",
            "text": f"{action} · {op} · sponsor PR https://github.com/{pr} {detail}"}


class PreflightTests(unittest.TestCase):
    def test_live_overlap_and_same_head(self):
        rows = [entry(1000, "SOURCE-OP-AAA1", detail="HEAD deadbeef src/main.py")]
        result = assess_take(rows, pr="https://github.com/org/repo/pull/12",
                             paths=["src/main.py"], head="deadbeef", as_of_ts=1004)
        self.assertEqual(result["status"], "COORDINATE_SOURCE")
        self.assertEqual(result["peers"][0]["relation"], "overlapping-source-paths")
        self.assertTrue(result["peers"][0]["same_head"])

    def test_release_retires_only_exact_operation(self):
        rows = [entry(1000, "SOURCE-OP-AAA1", detail="src/main.py"),
                entry(1001, "SOURCE-OP-BBB2", detail="src/main.py"),
                entry(1002, "SOURCE-OP-AAA1", "RELEASE")]
        result = assess_take(rows, pr="org/repo#12", paths=["src/main.py"], as_of_ts=1005)
        self.assertEqual([p["operation"] for p in result["peers"]], ["SOURCE-OP-BBB2"])
        self.assertEqual(result["status"], "COORDINATE_SOURCE")

    def test_disjoint_and_metadata_distinction(self):
        rows = [entry(1000, "SOURCE-OP-AAA1", detail="src/a.py"),
                entry(1001, "META-OP-BBB22", detail="metadata-only PR body")]
        result = assess_take(rows, pr="org/repo#12", paths=["src/b.py"], as_of_ts=1002)
        self.assertEqual(result["status"], "PARALLEL_SCOPE_ADVISORY")
        self.assertEqual({p["relation"] for p in result["peers"]},
                         {"disjoint-source-paths", "separate-source-and-metadata"})
        result = assess_take(rows, pr="org/repo#12", kind="metadata", as_of_ts=1002)
        self.assertEqual(result["status"], "COORDINATE_SOURCE")

    def test_unknown_scope_missing_or_stale_snapshot(self):
        rows = [entry(1000, "SOURCE-OP-AAA1")]
        self.assertEqual(assess_take(rows, pr="org/repo#12", paths=["src/a.py"],
                                     as_of_ts=1002)["status"], "COORDINATE_SOURCE")
        self.assertEqual(assess_take(rows, pr="org/repo#12", as_of_ts=2000)["status"],
                         "REFRESH_FEED")
        self.assertEqual(assess_take([], pr="org/repo#12", as_of_ts=1000)["status"],
                         "REFRESH_FEED")

    def test_distinct_pr_self_and_bad_issue_url(self):
        rows = [entry(1000, "SOURCE-OP-AAA1", detail="src/a.py"),
                entry(1001, "SOURCE-OP-BBB2", pr="org/repo/pull/99", detail="src/a.py")]
        report = assess_take(rows, pr="org/repo#12", operation_id="SOURCE-OP-AAA1",
                             paths=["src/a.py"], as_of_ts=1002)
        self.assertEqual(report["status"], "NO_ACTIVE_OVERLAP_OBSERVED")
        self.assertEqual(report["peers"], [])
        self.assertEqual(canonical_pr("https://github.com/ORG/Repo/pull/00012"),
                         "org/repo#12")
        with self.assertRaises(ValueError):
            canonical_pr("https://github.com/org/repo/issues/12")


if __name__ == "__main__":
    unittest.main()
