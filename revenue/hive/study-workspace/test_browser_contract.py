"""Standard-library contract checks for the Hive Study browser composition.

These tests validate the static consumer surface against the documented backend
route vocabulary without adding a browser/runtime dependency to the core suite.
The executable Chromium workflow lives in test_browser_acceptance.py.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.scripts: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.styles.append(values["href"])


class BrowserContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "workspace.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "style.css").read_text(encoding="utf-8")
        cls.inventory = Inventory()
        cls.inventory.feed(cls.html)

    def test_html_ids_are_unique(self):
        self.assertEqual(len(self.inventory.ids), len(set(self.inventory.ids)))

    def test_app_static_asset_names_match_backend_contract(self):
        self.assertEqual(self.inventory.scripts, ["/workspace.js"])
        self.assertEqual(self.inventory.styles, ["/style.css"])
        for name in ("index.html", "workspace.js", "style.css"):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_customer_workflow_controls_exist(self):
        required = {
            "import-form", "document-list", "show-due", "show-all", "review-form",
            "edit-card-form", "source-link", "retry-pending", "export-link",
            "original-link", "delete-document", "feedback", "next-card",
        }
        self.assertFalse(required - set(self.inventory.ids))

    def test_consumer_uses_documented_api_routes(self):
        for token in (
            '"/api/capabilities"', '"/api/documents"', '"/api/import"',
            '"/api/review"', '/api/cards/${', '/api/documents/${',
        ):
            self.assertIn(token, self.js)
        self.assertIn("/cards${dueOnly ? \"?due=1\" : \"\"}", self.js)
        self.assertIn("/export`", self.js)
        self.assertIn("/original/${encodeURIComponent", self.js)

    def test_review_request_is_persisted_before_network_write(self):
        save_at = self.js.index("savePending(pending); // Persist before any network write.")
        send_at = self.js.index("api.review(pendingPayload(pending))")
        self.assertLess(save_at, send_at)
        self.assertIn("request_id: freshRequestId()", self.js)
        self.assertIn("pending.request_id", self.js)

    def test_transient_failure_keeps_pending_but_terminal_conflict_can_reload(self):
        self.assertIn("error.status === 0 || error.status >= 500", self.js)
        self.assertIn("if (!transient) savePending(null)", self.js)
        self.assertIn("error.status === 409", self.js)
        self.assertIn("await loadDocument(state.selectedId", self.js)

    def test_no_external_runtime_dependency_or_restore_control(self):
        external = re.findall(r"https?://[^\s\"']+", self.html + self.js + self.css)
        self.assertEqual(external, [])
        self.assertNotRegex(self.html, r'id=["\'](?:restore|restore-export|snapshot-restore)["\']')
        self.assertIn("does not restore exported snapshots", self.html)
        self.assertIn("No model API · no telemetry", self.html)

    def test_source_bound_feedback_is_visible_in_consumer(self):
        for token in ("result.answer", "result.quote", "result.source_url", "result.feedback"):
            self.assertIn(token, self.js)
        self.assertIn("Open cited source", self.html)

    def test_responsive_layout_and_source_anchor_highlight_exist(self):
        self.assertIn("@media (max-width: 900px)", self.css)
        self.assertIn("@media (max-width: 560px)", self.css)
        self.assertIn(".source-lines li:target", self.css)

    @unittest.skipUnless(shutil.which("node"), "Node is optional; syntax check skipped")
    def test_javascript_syntax(self):
        result = subprocess.run([shutil.which("node"), "--check", str(ROOT / "workspace.js")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
