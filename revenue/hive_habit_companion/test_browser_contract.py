from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class BrowserContractTest(unittest.TestCase):
    def test_customer_workflow_controls_are_present(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        required = {
            'id="goal-form"',
            'id="note-form"',
            'id="focus-sessions"',
            'id="history"',
            'id="export-json"',
            'id="export-csv"',
            'id="restore-file"',
            'id="erase-button"',
            'id="enable-notifications"',
        }
        for marker in required:
            self.assertIn(marker, html)
        self.assertIn("A habit utility, not treatment", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("<script>", html.lower())
        self.assertNotIn("style=", html.lower())

    def test_browser_code_has_no_remote_transport_or_tracking_surface(self) -> None:
        script = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/state'", script)
        self.assertIn("fetch('/api/change'", script)
        self.assertNotIn("XMLHttpRequest", script)
        self.assertNotIn("WebSocket", script)
        self.assertNotIn("sendBeacon", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        self.assertNotIn("https://", script)
        self.assertNotIn("http://", script)
        self.assertIn("Notification.requestPermission", script)
        self.assertIn("PAUSED", script)
        self.assertIn("RESUMED", script)

    def test_javascript_syntax_when_node_is_available(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed")
        subprocess.run([node, "--check", str(ROOT / "app.js")], check=True, capture_output=True, text=True)

    def test_static_assets_are_self_contained(self) -> None:
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        self.assertNotIn("@import", css)
        self.assertNotIn("url(http", css)
        self.assertIn("prefers-color-scheme", css)
        self.assertIn("@media (max-width", css)


if __name__ == "__main__":
    unittest.main()
