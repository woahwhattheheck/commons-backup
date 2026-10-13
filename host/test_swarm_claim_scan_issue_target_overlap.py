"""One focused regression for concurrent TAKE IDs pointing to one GitHub issue."""
import unittest

from host.swarm_claim_scan import _issue_targets, scan


class GitHubIssueClaimCollisionTest(unittest.TestCase):
    def test_distinct_claim_ids_same_issue_are_advisory_overlap(self):
        def observation(ts, operation, reference):
            return {
                "channel_id": "C0EXAMPLE00",
                "message_ts": ts,
                "permalink": "https://workspace.slack.com/archives/C0EXAMPLE00/p"
                    + ts.replace(".", ""),
                "source": "offline-fixture",
                "text": "TAKE · " + operation + " · sponsor " + reference,
            }

        messages = [
            observation(
                "1700000001.000001",
                "GF-EXAMPLE711-DANGER-PR-REPORT-20261008-R1",
                "example/project #711",
            ),
            observation(
                "1700000002.000002",
                "GF-EXAMPLE711-DANGER-PR-FINDINGS-20261008-R1",
                "https://github.com/example/project/issues/711",
            ),
            observation(
                "1700000003.000003",
                "GF-EXAMPLE710-BITBUCKET-20261008-R2",
                "example/project#710",
            ),
        ]
        report = scan(messages, [])
        overlaps = report["possible_issue_target_overlaps"]
        self.assertEqual(report["counts"]["possible_issue_target_overlaps"], 1)
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]["issue_target"], "centurylong/sanctifier#711")
        self.assertEqual(
            set(overlaps[0]["operation_ids"]),
            {
                "GF-EXAMPLE711-DANGER-PR-REPORT-20261008-R1",
                "GF-EXAMPLE711-DANGER-PR-FINDINGS-20261008-R1",
            },
        )
        self.assertEqual(len(overlaps[0]["declaration_observations"]), 2)
        self.assertEqual(overlaps[0]["status"], "possible_same_issue_overlap")

        # Mere pull-request URLs or an unqualified number must not imply
        # identity with an issue.
        self.assertEqual(_issue_targets("https://github.com/a/b/pull/711 #711"), [])
        self.assertEqual(
            _issue_targets("example/project#711"),
            ["centurylong/sanctifier#711"],
        )


if __name__ == "__main__":
    unittest.main()
