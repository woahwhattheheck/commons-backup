#!/usr/bin/env python3
"""Actual Chromium operator-flow smoke for the local workbench UI.

The browser flow injects the exact checked-in HTML/CSS/JS bytes with Playwright's
``set_content``/asset injection so it remains runnable in sandboxes whose enterprise
Chromium policy blocks navigation. HTTP/host/origin/compiler-adapter behavior is
covered separately by ``test_workbench.py`` against the actual loopback server.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        # Enterprise browser policy in some ChatGPT sandboxes blocks navigation entirely.
        # set_content + explicit checked-in assets still executes the exact UI bytes in Chromium.
        html = html.replace('<link rel="stylesheet" href="/style.css">', '').replace('<script src="/app.js" defer></script>', '')

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                args=["--no-sandbox", "--allow-file-access-from-files"],
            )
            page = browser.new_page(accept_downloads=True)
            page.set_content(html, wait_until="load")
            page.add_style_tag(content=(ROOT / "style.css").read_text(encoding="utf-8"))
            page.add_script_tag(content=(ROOT / "app.js").read_text(encoding="utf-8"))
            page.get_by_role("button", name="Load synthetic UI demo").click()
            assert page.locator("#matrix").get_attribute("data-rendered-cells") == "12"
            assert page.locator("#summary").get_by_text("Evidence consistent").count() == 1
            assert page.locator("#sampleBadge").text_content() == "Synthetic sample · UI demonstration"
            assert page.locator(".report-details").get_attribute("open") is None
            assert "HOLD_" not in " ".join(page.locator(".cell .status").all_text_contents())

            first = page.locator(".cell").first
            first.focus(); page.keyboard.press("Enter")
            page.locator("#note").fill("Need primary source confirmation before prime review.")
            page.locator("#disposition").select_option("NEEDS_EVIDENCE")
            page.locator(".cell").nth(1).click(); first.click()
            assert page.locator("#note").input_value().startswith("Need primary source")
            assert page.locator("#disposition").input_value() == "NEEDS_EVIDENCE"

            # A successful new import must never silently inherit notes from the previous generation.
            page.locator("#importPanel > summary").click()
            page.get_by_role("button", name="Load synthetic UI demo").click()
            page.locator(".cell").first.click()
            assert page.locator("#note").input_value() == ""
            assert page.locator("#disposition").input_value() == "UNREVIEWED"

            # A FAILED replacement import is also a generation boundary: stale report,
            # notes and export controls must be killed before parsing or transport.
            page.locator("#note").fill("THIS MUST NOT SURVIVE A FAILED REPLACEMENT")
            malformed = td_path / "malformed-candidate.json"
            malformed.write_text("{not-json")
            page.locator("#importPanel > summary").click()
            page.locator("#candidateFile").set_input_files(str(malformed))
            # Deliberately leave authorityFile empty; either local validation failure is
            # sufficient, but the prior generation must already be gone.
            page.get_by_role("button", name="Inspect evidence").click()
            assert page.locator("#matrix").get_attribute("data-rendered-cells") == "0"
            assert page.locator("#exportBtn").is_disabled()
            assert page.locator("#note").is_disabled()
            assert page.locator("#note").input_value() == ""
            assert page.locator("#error").text_content().strip()

            # Continue from a fresh synthetic generation after the negative regression.
            page.get_by_role("button", name="Load synthetic UI demo").click()
            page.locator("#search").fill("security")
            assert page.locator("#matrix").get_attribute("data-rendered-cells") == "3"
            page.locator("#search").fill("")

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Export review handoff").click()
            download = download_info.value
            path = td_path / download.suggested_filename
            download.save_as(path)
            handoff = json.loads(path.read_text())
            assert handoff["status"] == "DRAFT_NON_AUTHORITATIVE"
            assert handoff["authority"] == {
                "buyer_approved": False,
                "prime_approved": False,
                "current_evidence_review_authority": False,
                "submission_authorized": False,
                "signature_authorized": False,
                "invoice_or_payment_authorized": False,
                "recognized_revenue": False,
            }
            assert len(handoff["cell_notes"]) == 12
            browser.close()

    print("CHROMIUM_OPERATOR_FLOW PASS: 12 cells, keyboard selection, note reset, filter, authority-safe export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
