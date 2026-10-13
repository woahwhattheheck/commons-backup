from __future__ import annotations

import unittest

from revenue.outbound_send_consumer.consume import consume_once
from revenue.outbound_send_consumer.test_consume import FakeGit, fixture


class RepositoryAliasTests(unittest.TestCase):
    def test_github_repo_case_aliases_share_one_reservation(self):
        git = FakeGit()
        host, first = fixture("Z-Case-A")
        second_host, second = fixture("Z-Case-B")
        second_host["repo"] = "WOAHWHATTHEHECK/COMMONS"
        second["repo"] = "WoahWhatTheHeck/Commons"
        calls: list[str] = []

        r1 = consume_once(
            first,
            host_raw=host,
            transport=git,
            authority_probe=lambda: host["authority_sha256"],
            provider_callback=lambda key: calls.append("a"),
        )
        r2 = consume_once(
            second,
            host_raw=second_host,
            transport=git,
            authority_probe=lambda: second_host["authority_sha256"],
            provider_callback=lambda key: calls.append("b"),
        )

        self.assertEqual(r1["decision"], "SENT")
        self.assertEqual(r2["decision"], "SUPPRESSED")
        self.assertEqual(r1["seam_sha256"], r2["seam_sha256"])
        self.assertEqual(calls, ["a"])


if __name__ == "__main__":
    unittest.main()
