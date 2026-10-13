import hashlib
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from civic_ledger.core import _canonical_bytes

ROOT = Path(__file__).resolve().parents[1]


class AuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.forms = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "script":
            self.scripts.append(attrs)
        if tag == "form":
            self.forms.append(attrs)


class StaticDemoTests(unittest.TestCase):
    def test_sample_ledger_digest_and_authority(self):
        data = json.loads((ROOT / "sample-ledger.json").read_text("utf-8"))
        digest = data["compile_sha256"]
        clone = dict(data)
        clone.pop("compile_sha256")
        self.assertEqual(hashlib.sha256(_canonical_bytes(clone)).hexdigest(), digest)
        self.assertEqual(digest, "29735202669dc34f86d2ee066691bacb748fc0de383fd593e037108f42a1c200")
        self.assertFalse(data["authority"]["external_actions_authorized"])
        self.assertEqual(
            {x["state"] for x in data["items"]},
            {"DECIDED_APPROVED", "DECIDED_CONTINUED", "DECIDED_DENIED"},
        )

    def test_page_is_dependency_free_and_accessible_surface_exists(self):
        text = (ROOT / "index.html").read_text("utf-8")
        parser = AuditParser()
        parser.feed(text)
        self.assertTrue({"ledger", "search", "state", "items", "load-status", "compile-hash"} <= parser.ids)
        self.assertTrue(all("src" not in script for script in parser.scripts), "external scripts are forbidden")
        self.assertFalse(parser.forms, "static demo performs no form submission")
        self.assertIn("Synthetic Riverton demo", text)
        self.assertIn("Zero autonomous authority", text)
        self.assertIn("fetch('sample-ledger.json'", text)
        self.assertNotRegex(text, r"https?://(?:cdn|unpkg|jsdelivr)\\.")

    def test_page_has_no_mutation_endpoints_or_tracking(self):
        text = (ROOT / "index.html").read_text("utf-8").lower()
        forbidden = [
            "google-analytics",
            "gtag(",
            "segment.io",
            "mixpanel",
            "postmessage(",
            "webhook",
            "mailto:",
            "method=\"post\"",
        ]
        for needle in forbidden:
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
