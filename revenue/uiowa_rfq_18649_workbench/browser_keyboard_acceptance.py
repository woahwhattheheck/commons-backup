#!/usr/bin/env python3
"""Keyboard task regression for the actual workbench HTML/CSS/JS in Chromium.

Run: python browser_keyboard_acceptance.py -v
Dependencies: Playwright + Chromium (CHROMIUM_EXECUTABLE overrides the executable).
UIOWA_WORKBENCH_ROOT selects another exact source tree for red/green comparison.
No server, compiler, network, screen reader, or WCAG certification is simulated.
The built-in SYNTHETIC_UI_DEMO fixture is used unless a test explicitly adds a field.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(os.environ.get("UIOWA_WORKBENCH_ROOT", Path(__file__).resolve().parent))


class KeyboardAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
        options = {"headless": True, "args": ["--no-sandbox"]}
        if executable:
            options["executable_path"] = executable
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(accept_downloads=True, viewport={"width": 1280, "height": 800})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script\b[^>]*src="([^"]+)"[^>]*></script>', html)
        styles = re.findall(r'<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>', html)
        html = re.sub(r'<script\b[^>]*src="[^"]+"[^>]*></script>', '', html)
        html = re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>', '', html)
        self.page.set_content(html)
        for asset in styles:
            self.page.add_style_tag(content=(ROOT / asset.lstrip('/')).read_text(encoding="utf-8"))
        for asset in scripts:
            self.page.add_script_tag(content=(ROOT / asset.lstrip('/')).read_text(encoding="utf-8"))

    def tearDown(self):
        errors = self.errors[:]
        self.page.close()
        self.assertEqual(errors, [], "Unexpected browser errors")

    def tab_to(self, selector: str, *, reverse=False):
        """Navigate by actual Tab presses, never locator.focus/click for the task."""
        for _ in range(100):
            if self.page.locator(selector).evaluate_all("nodes => nodes.includes(document.activeElement)"):
                return
            self.page.keyboard.press("Shift+Tab" if reverse else "Tab")
        self.fail(f"Keyboard could not reach {selector}")

    def open_import(self):
        if not self.page.locator("#importPanel").get_attribute("open") == "":
            self.tab_to("#importPanel > summary", reverse=True)
            self.page.keyboard.press("Enter")

    def load_demo(self):
        self.open_import()
        self.tab_to("#demoBtn")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.locator(".cell").count(), 12)

    def select_first(self, key="Enter"):
        self.tab_to(".cell:nth-of-type(1)")
        self.page.keyboard.press(key)
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "selectedCellHeading")

    def test_keyboard_review_and_download(self):
        self.load_demo()
        self.select_first()
        self.tab_to(".technical-details > summary")
        self.page.keyboard.press("Enter")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "detail")
        self.tab_to("#disposition")
        self.page.keyboard.press("ArrowDown")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "note")
        note = "SYNTHETIC: request the current release example; do not infer a maturity score."
        self.page.keyboard.type(note)
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "backToCellBtn")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.key"), "ESS|software_development")
        self.tab_to("#exportBtn")
        with self.page.expect_download() as event:
            self.page.keyboard.press("Enter")
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "handoff.json"
            event.value.save_as(dest)
            draft = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(len(draft["cell_notes"]), 12)
        self.assertEqual(draft["cell_notes"][0]["analyst_note"], note)
        self.assertEqual(draft["cell_notes"][0]["disposition"], "NEEDS_EVIDENCE")
        self.assertEqual(draft["report_receipt_sha256"], "d" * 64)
        self.assertTrue(draft["synthetic_demo"])
        self.assertTrue(all(value is False for value in draft["authority"].values()))

    def test_failed_import_restores_its_keyboard_invoker(self):
        self.load_demo()
        self.open_import()
        self.tab_to("#inspectBtn")
        self.page.keyboard.press("Enter")
        self.page.wait_for_function("!document.getElementById('inspectBtn').disabled")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "inspectBtn")
        self.assertTrue(self.page.locator("#exportBtn").is_disabled())
        self.assertTrue(self.page.locator("#error").inner_text().strip())

    def test_space_activates_cell_and_context(self):
        self.load_demo()
        self.select_first("Space")
        self.assertEqual(self.page.locator("#selectedCellHeading").inner_text(), "ESS / Software development")

    def test_complete_evidence_including_digests_is_visible(self):
        self.load_demo()
        self.select_first()
        detail = json.loads(self.page.locator("#detail").inner_text())
        self.assertEqual(detail, self.page.evaluate("state.cells[0]"))
        self.assertEqual(detail["source_record_sha256s"], ["0" * 64])
        self.assertIsNone(detail["maturity"])
        self.assertIsNone(detail["confidence_bp"])

    def test_unknown_zero_and_extensions_remain_literal(self):
        self.load_demo()
        self.page.evaluate('''() => {
          const report = syntheticReport();
          report.assessment_matrix[0].confidence_bp = 0;
          report.assessment_matrix[0].extension = {locator: "Appendix Ω / row 4", note: "<b>literal only</b>"};
          installReport(report);
        }''')
        self.select_first()
        detail = json.loads(self.page.locator("#detail").inner_text())
        self.assertEqual(detail["confidence_bp"], 0)
        self.assertIsNone(detail["maturity"])
        self.assertEqual(detail["extension"]["locator"], "Appendix Ω / row 4")
        self.assertEqual(self.page.locator("#detail b").count(), 0)

    def test_filter_has_count_without_stealing_focus(self):
        self.load_demo()
        self.tab_to("#search")
        self.page.keyboard.type("security")
        self.assertEqual(self.page.locator(".cell").count(), 3)
        self.assertIn("3 of 12", self.page.locator("#matrixStatus").inner_text())
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "search")

    def test_no_match_is_explicit(self):
        self.load_demo()
        self.tab_to("#search")
        self.page.keyboard.type("not-a-fixture-term")
        self.assertEqual(self.page.locator(".cell").count(), 0)
        self.assertIn("No cells match", self.page.locator("#matrixStatus").inner_text())
        self.assertEqual(self.page.locator("#matrixStatus").get_attribute("role"), "status")

    def test_hidden_selection_return_preserves_notes(self):
        self.load_demo()
        self.select_first()
        self.tab_to("#note")
        self.page.keyboard.type("Retain this synthetic note.")
        self.tab_to("#search", reverse=True)
        self.page.keyboard.type("IAM")
        self.assertIn("outside the current filters", self.page.locator("#matrixStatus").inner_text())
        self.tab_to("#backToCellBtn")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "search")
        self.assertEqual(self.page.locator("#note").input_value(), "Retain this synthetic note.")
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.tab_to("#backToCellBtn")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.key"), "ESS|software_development")

    def test_rerender_preserves_focused_matrix_button(self):
        self.load_demo()
        self.tab_to(".cell:nth-of-type(1)")
        self.page.evaluate("renderMatrix()")
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.key"), "ESS|software_development")

    def test_reset_clears_accessible_selection(self):
        self.load_demo()
        self.select_first()
        self.open_import()
        self.tab_to("#resetBtn")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.locator("#selectedCellHeading").inner_text(), "No cell selected")
        self.assertTrue(self.page.locator("#backToCellBtn").is_disabled())
        self.assertTrue(self.page.locator("#note").is_disabled())
        self.assertIn("No report loaded", self.page.locator("#matrixStatus").inner_text())
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "resetBtn")

    def test_new_generation_clears_previous_notes(self):
        self.load_demo()
        self.select_first()
        self.tab_to("#note")
        self.page.keyboard.type("Old generation note")
        self.load_demo()
        self.select_first()
        self.assertEqual(self.page.locator("#note").input_value(), "")

    def test_skip_link_is_first_and_targets_focusable_heading(self):
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.textContent"), "Skip to assessment matrix")
        self.assertEqual(self.page.locator("#summary-heading").get_attribute("tabindex"), "-1")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "summary-heading")

    def test_cell_and_form_controls_have_context(self):
        self.load_demo()
        for button in self.page.locator(".cell").all():
            self.assertIn("Open evidence", button.get_attribute("aria-label"))
            self.assertEqual(button.get_attribute("aria-controls"), "detailPanel")
        self.assertIn("selectedCellHeading", self.page.locator("#note").get_attribute("aria-describedby"))
        self.assertEqual(self.page.locator("#detail").get_attribute("aria-labelledby"), "selectedCellHeading")

    def test_focus_is_visible_in_light_dark_and_forced_colors(self):
        self.load_demo()
        for mode in ("light", "dark", "forced"):
            with self.subTest(mode=mode):
                self.page.emulate_media(color_scheme="dark" if mode == "dark" else "light", forced_colors="active" if mode == "forced" else "none")
                self.tab_to(".cell:nth-of-type(1)")
                outline = self.page.locator(".cell:nth-of-type(1)").evaluate("e => ({width:getComputedStyle(e).outlineWidth, style:getComputedStyle(e).outlineStyle})")
                self.assertEqual(outline, {"width": "3px", "style": "solid"})

    def test_repeated_keyboard_review_has_no_trap(self):
        self.load_demo()
        for _ in range(3):
            self.select_first()
            self.tab_to("#backToCellBtn")
            self.page.keyboard.press("Enter")
            self.assertEqual(self.page.evaluate("document.activeElement.dataset.key"), "ESS|software_development")
        self.tab_to("#exportBtn")
        self.assertTrue(self.page.locator("#exportBtn").is_enabled())

    def test_selected_heading_visible_at_narrow_and_wide_width(self):
        self.load_demo()
        for width in (1280, 480, 320):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 800})
                self.select_first()
                bounds = self.page.locator("#selectedCellHeading").bounding_box()
                self.assertIsNotNone(bounds)
                self.assertGreaterEqual(bounds["y"], 0)
                self.assertLess(bounds["y"] + bounds["height"], 800)


if __name__ == "__main__":
    unittest.main(verbosity=2)

