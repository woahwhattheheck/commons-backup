import unittest

import sara_partner_accession as sara


class NamedHumanReservedTokenRegressionTests(unittest.TestCase):
    def test_reserved_terms_cannot_hide_inside_multi_token_identity(self):
        for bad in (
            "System Reviewer",
            "auto reviewer",
            "AI Reviewer",
            "service account",
            "System.Reviewer Human",
            "agent_review human",
            "worker-human reviewer",
            "service-account reviewer",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(PermissionError):
                    sara._named_human(bad)

    def test_normal_two_token_and_hyphenated_human_names_still_pass(self):
        self.assertEqual("Jordan Reviewer", sara._named_human("Jordan Reviewer"))
        self.assertEqual("Mary-Jane Reviewer", sara._named_human("Mary-Jane Reviewer"))


if __name__ == "__main__":
    unittest.main()
