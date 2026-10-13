"""Focused regression checks for explicit owner/repo#issue declarations."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

SCANNER = Path(os.environ.get("SWARM_CLAIM_SCANNER", Path(__file__).with_name("swarm_claim_scan.py")))
spec = importlib.util.spec_from_file_location("claim_scan", SCANNER)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class GitHubShorthandTests(unittest.TestCase):
    def test_direct_and_labeled_claims(self):
        for operation in ("seveibar/pgstrap#2", "owner/repo#123", "a/b#1"):
            for text in (f"CLAIM {operation}", f"TAKE `{operation}` — source only",
                         f"CONTINUING current work. Operation ID: {operation}"):
                with self.subTest(text=text):
                    self.assertEqual(scanner._statements(text), [("declaration", operation)])

    def test_terminal_forms_share_operation_identity(self):
        operation = "owner/repo#123"
        for text, kind in ((f"DONE {operation}", "done"),
                           (f"RELEASE / {operation}", "release"),
                           (f"{operation} is RELEASED", "released"),
                           (f"DONE SOURCE / RELEASED {operation}", "done"),
                           (f"SHIP / RELEASED {operation}", "ship")):
            with self.subTest(text=text):
                self.assertEqual(scanner._statements(text), [(kind, operation)])

    def test_prose_paths_and_malformed_shorthands_stay_unparsed(self):
        for operation in ("something", "owner/repo", "owner/repo#0", "owner/repo#01",
                          "owner/repo#one", "owner/repo#1/extra", "owner/repo#1.5",
                          "owner/other/repo#1", "owner/..#1"):
            with self.subTest(operation=operation):
                self.assertEqual(scanner._statements(f"CLAIM {operation}"), [])

    def test_quoted_and_conditional_releases_stay_nonterminal(self):
        for text in ("> CLAIM owner/repo#123", "```\nCLAIM owner/repo#123\n```",
                     'Example: "CLAIM owner/repo#123"',
                     "DONE SOURCE / RELEASED owner/repo#123 pending integration"):
            with self.subTest(text=text):
                self.assertEqual(scanner._statements(text), [])

    def test_legacy_ids_are_unchanged(self):
        for operation in ("SWARM-CLAIM-20261004", "publication:123", "repo-name/scope"):
            self.assertEqual(scanner._statements(f"TAKE {operation}"), [("declaration", operation)])
            self.assertEqual(scanner._statements(f"DONE {operation}"), [("done", operation)])

    def test_cli_repeated_claim_and_release(self):
        payload = {"channel": "C0BU51F1PL3", "has_more": False, "messages": [
            {"ts": "1791154000.000001", "text": "CLAIM owner/repo#123 — first"},
            {"ts": "1791154001.000001", "text": "CLAIM owner/repo#123 — second"},
            {"ts": "1791154002.000001", "text": "RELEASED owner/repo#123"},
        ]}
        run = subprocess.run([sys.executable, str(SCANNER), "-", "--operation", "owner/repo#123"],
                             input=json.dumps(payload), text=True, capture_output=True, check=True)
        report = json.loads(run.stdout)
        self.assertEqual(len(report["operations"]), 1)
        self.assertEqual(report["operations"][0]["state"], "explicit_terminal_observed")
        self.assertEqual(report["repeated_operation_declarations"][0]["declaration_count"], 2)
        self.assertFalse(report["coverage"]["provider_history_complete"])
        self.assertTrue(report["advisory_only"])


if __name__ == "__main__":
    unittest.main()
