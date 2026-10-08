"""One focused regression for concurrent TAKE IDs pointing to one GitHub issue."""
import unittest

from host.swarm_claim_scan import _issue_targets, scan


class GitHubIssueClaimCollisionTest(unittest.TestCase):
    def test_distinct_claim_ids_same_issue_are_advisory_overlap(self):
        def observation(ts, operation, reference):
            return {
                "channel_id": "C0BVANHNB26",
                "message_ts": ts,
                "permalink": "https://tokenjunkielabs.slack.com/archives/C0BVANHNB26/p"
                    + ts.replace(".", ""),
                "source": "offline-fixture",
                "text": "TAKE · " + operation + " · sponsor " + reference,
            }

        messages = [
            observation(
                "1791430595.283339",
                "GF-SANCTIFIER711-DANGER-PR-REPORT-20261008-R1",
                "Centurylong/sanctifier #711",
            ),
            observation(
                "1791430614.814209",
                "GF-SANCTIFIER711-DANGER-PR-FINDINGS-20261008-R1",
                "https://github.com/Centurylong/sanctifier/issues/711",
            ),
            observation(
                "1791430618.004001",
                "GF-SANCTIFIER710-BITBUCKET-20261008-R2",
                "Centurylong/sanctifier#710",
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
                "GF-SANCTIFIER711-DANGER-PR-REPORT-20261008-R1",
                "GF-SANCTIFIER711-DANGER-PR-FINDINGS-20261008-R1",
            },
        )
        self.assertEqual(len(overlaps[0]["declaration_observations"]), 2)
        self.assertEqual(overlaps[0]["status"], "possible_same_issue_overlap")

        # Mere pull-request URLs or an unqualified number must not imply
        # identity with an issue.
        self.assertEqual(_issue_targets("https://github.com/a/b/pull/711 #711"), [])
        self.assertEqual(
            _issue_targets("Centurylong/sanctifier#711"),
            ["centurylong/sanctifier#711"],
        )


if __name__ == "__main__":
    unittest.main()
