"""Focused issue-identity overlap regression from the Sanctifier #330 TAKE race."""

import unittest

from integrations.command_center.claim_overlap import build_claim_overlap


CHANNEL = "C0BVANHNB26"
WORKSPACE = "https://tokenjunkielabs.slack.com"


def message(text, second):
    ts = f"17914312{second}.000001"
    return {
        "text": text,
        "ts": ts,
        "channel_id": CHANNEL,
        "permalink": f"{WORKSPACE}/archives/{CHANNEL}/p{ts.replace('.', '')}",
    }


def project(*messages):
    return build_claim_overlap([{"messages": list(messages)}])


class ExplicitSponsorIssueOverlap(unittest.TestCase):
    def test_same_issue_different_operations_without_file_paths(self):
        result = project(
            message(
                "TAKE BUILD / PUBLISH · GF-SANCTIFIER330-ADMIN-POWERS-20261008-H6R7 "
                "· Sponsor Centurylong/sanctifier#330. I will handle the report.",
                "93",
            ),
            message(
                "TAKE BUILD · GF-SANCTIFIER330-ADMIN-POWERS-20261008-GPT6-R1 "
                "· Issue https://github.com/centurylong/SANCTIFIER/issues/330. "
                "I will handle the detector.",
                "94",
            ),
        )
        self.assertEqual(result["summary"]["potential_overlap_pairs"], 1)
        pair = result["overlaps"][0]
        self.assertEqual(pair["matches"], [])
        self.assertEqual(
            pair["issue_matches"][0]["issue_url"],
            "https://github.com/centurylong/sanctifier/issues/330",
        )
        self.assertIn("/archives/", pair["issue_matches"][0]["left_source"]["permalink"])
        self.assertIn("/archives/", pair["issue_matches"][0]["right_source"]["permalink"])

    def test_unrelated_issue_or_pull_reference_does_not_claim_issue(self):
        result = project(
            message("TAKE · GF-ALPHA-20261008 · Repo/A#330; see also #331.", "93"),
            message(
                "TAKE · GF-BETA-20261008 · Repo/A#331; "
                "see https://github.com/Repo/A/pull/330.",
                "94",
            ),
        )
        self.assertEqual(result["overlaps"], [])

    def test_exact_terminal_release_removes_active_overlap(self):
        result = project(
            message("TAKE · GF-ALPHA-20261008 · Repo/A#330.", "93"),
            message("TAKE · GF-BETA-20261008 · repo/a#330.", "94"),
            message("RELEASE · GF-ALPHA-20261008", "95"),
        )
        self.assertEqual(result["summary"]["potential_overlap_pairs"], 0)
        self.assertEqual(result["summary"]["terminal_observed"], 1)

    def test_existing_file_scope_overlap_remains_supported(self):
        result = project(
            message("TAKE · GF-ONE-20261008 · scope: host/audit.py", "93"),
            message("TAKE · GF-TWO-20261008 · scope: host/audit.py", "94"),
        )
        self.assertEqual(result["summary"]["potential_overlap_pairs"], 1)
        self.assertEqual(result["overlaps"][0]["issue_matches"], [])
        self.assertEqual(result["overlaps"][0]["matches"][0]["path_relation"], "same_explicit_path")


if __name__ == "__main__":
    unittest.main()
