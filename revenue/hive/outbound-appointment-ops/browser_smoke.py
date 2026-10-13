"""Optional Chromium workflow for the composed Hive028 operator UI.

Derived from ASTRA-MAPLE's preserved browser smoke at
8f593cda6719d64f09aa021356dee62f2de2fdf7, adapted to TEMPEST's landed
OutboundDesk via app.py. Requires Playwright + a Chromium executable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import threading

import app


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is optional; install it only in an authorized browser-test environment.") from exc

    with tempfile.TemporaryDirectory() as tmp:
        operator = app.OperatorApp(Path(tmp) / "browser.sqlite3")
        server = app.Server(("127.0.0.1", 0), operator)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as p:
                executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
                launch = {"headless": True, "args": ["--no-sandbox"]}
                if executable:
                    launch["executable_path"] = executable
                browser = p.chromium.launch(**launch)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Ready.')")

                page.fill("#campaignId", "browser-campaign")
                page.fill("#customerName", "Fictional Seller")
                page.fill("#offer", "a bounded local appointment workflow")
                page.fill("#sourcePolicy", "fictional customer-provided lawful source only")
                page.click("#campaignForm button")
                page.wait_for_function("document.querySelector('#status').textContent==='Campaign created locally.'")

                page.fill("#prospectId", "browser-p1")
                page.fill("#organization", "Fictional Buyer")
                page.fill("#contactName", "Sample Contact")
                page.fill("#routeRef", "route-browser-1")
                page.fill("#sourceRef", "example://authorized/browser-1")
                page.fill("#lawfulNote", "fictional source fixture supplied for browser validation")
                page.fill("#relevance", "the fictional organization manually coordinates appointments")
                page.click("#prospectForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Prospect added')")

                page.click("#draft")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Unsent draft')")
                assert "UNSENT:" in page.locator("#draftView").inner_text()

                page.fill("#replyNote", "Fictional interested reply fixture.")
                page.click("#replyForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Inbound reply')")

                page.fill("#slotId", "browser-slot-1")
                page.fill("#start", "2035-09-10T14:00:00Z")
                page.fill("#end", "2035-09-10T14:30:00Z")
                page.click("#slotForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Local slot added')")

                page.click("#bookForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Local booking')")
                with page.expect_download() as downloaded:
                    page.click("#bookings a")
                calendar = Path(downloaded.value.path()).read_bytes()
                assert b"DTSTART:20350910T140000Z" in calendar
                assert b"ATTENDEE" not in calendar

                page.fill("#prospectId", "browser-p2")
                page.fill("#organization", "Fictional Buyer Two")
                page.fill("#contactName", "Second Contact")
                page.fill("#routeRef", "route-browser-2")
                page.fill("#sourceRef", "example://authorized/browser-2")
                page.fill("#lawfulNote", "fictional source fixture supplied for browser validation")
                page.fill("#relevance", "the second fictional organization coordinates appointments")
                page.click("#prospectForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Prospect added')")
                page.select_option("#replyKind", "opt_out")
                page.fill("#replyNote", "Fictional opt-out fixture.")
                page.click("#replyForm button")
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Inbound reply')")
                assert "SUPPRESSED" in page.locator("#prospects").inner_text()

                page.reload()
                page.wait_for_function("document.querySelector('#status').textContent.startsWith('Ready.')")
                assert "SUPPRESSED" in page.locator("#prospects").inner_text()

                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(100)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors

                if os.environ.get("SCREENSHOT_DIR"):
                    out = Path(os.environ["SCREENSHOT_DIR"])
                    out.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(out / "mobile.png"), full_page=True)

                state = operator.state()
                assert len(state["bookings"]) == 1
                assert len(state["suppressions"]) == 1
                print(json.dumps({
                    "browser": browser.version,
                    "desktop_workflow": "PASS",
                    "mobile_390px": "PASS",
                    "reload_persistence": "PASS",
                    "page_errors": errors,
                    "bookings": 1,
                    "suppressions": 1,
                    "provider_updates": 0,
                }, sort_keys=True))
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            operator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
