"""Real Chromium acceptance for the complete Paceboard customer workflow.

The execution environment blocks native browser navigation before loopback
requests reach the application. Real loopback HTTP is covered independently by
test_app.py. This test executes the exact HTML, CSS, JavaScript, Store and API
contract in Chromium through a narrow in-process fetch bridge.
"""
from __future__ import annotations

import base64
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from paceboard import PaceboardError, Store, canonical_json, sha256_bytes

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - optional local acceptance dependency
    expect = None
    sync_playwright = None

ROOT = Path(__file__).resolve().parent
CSRF = "browser-acceptance-csrf"


@unittest.skipUnless(sync_playwright is not None and shutil.which("chromium"), "Chromium + Playwright required")
class BrowserAcceptanceTest(unittest.TestCase):
    def test_complete_private_customer_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            store = Store(workspace / "paceboard.sqlite3")
            console_errors: list[str] = []

            def response(status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
                return {
                    "status": status,
                    "body_base64": base64.b64encode(body).decode("ascii"),
                    "headers": {
                        "Content-Type": content_type,
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                        **(headers or {}),
                    },
                }

            def api_call(request: dict[str, Any]) -> dict[str, Any]:
                method = request.get("method", "GET").upper()
                path = request.get("path")
                headers = {str(key).lower(): str(value) for key, value in (request.get("headers") or {}).items()}
                try:
                    if method == "GET" and path == "/api/state":
                        state = store.snapshot()
                        state["csrf_token"] = CSRF
                        return response(200, canonical_json(state), "application/json; charset=utf-8")
                    if method == "GET" and path == "/api/export.json":
                        body = store.backup_bytes()
                        return response(200, body, "application/json; charset=utf-8", {
                            "Content-Disposition": 'attachment; filename="paceboard-backup.json"',
                            "X-Content-SHA256": sha256_bytes(body),
                        })
                    if method == "GET" and path == "/api/export.csv":
                        body = store.timeline_csv_bytes()
                        return response(200, body, "text/csv; charset=utf-8", {
                            "Content-Disposition": 'attachment; filename="paceboard-history.csv"',
                            "X-Content-SHA256": sha256_bytes(body),
                        })
                    if method == "POST" and path == "/api/change":
                        if headers.get("x-paceboard-csrf") != CSRF:
                            raise PaceboardError("Valid Paceboard CSRF token required", 403, "CSRF_REQUIRED")
                        value = json.loads(request.get("body") or "null")
                        if not isinstance(value, dict):
                            raise PaceboardError("Request JSON must be an object")
                        result = store.mutate(value.get("action"), value.get("operation_id"), value.get("payload"))
                        return response(200, canonical_json(result), "application/json; charset=utf-8")
                    raise PaceboardError("Not found", 404, "NOT_FOUND")
                except PaceboardError as exc:
                    return response(
                        exc.status,
                        canonical_json({"error": str(exc), "code": exc.code}),
                        "application/json; charset=utf-8",
                    )

            index = (ROOT / "index.html").read_text(encoding="utf-8")
            index = index.replace('<link rel="stylesheet" href="/style.css">', f"<style>{(ROOT / 'style.css').read_text(encoding='utf-8')}</style>")
            index = index.replace('<script src="/app.js" defer></script>', "")
            fetch_bridge = r"""
                (() => {
                  const decode = value => {
                    const binary = atob(value);
                    const bytes = new Uint8Array(binary.length);
                    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
                    return bytes;
                  };
                  window.fetch = async (input, init = {}) => {
                    const url = new URL(typeof input === 'string' ? input : input.url, 'https://paceboard.local/');
                    const headers = Object.fromEntries(new Headers(init.headers || {}).entries());
                    const result = await window.__paceboardApi({
                      method: String(init.method || 'GET'),
                      path: url.pathname,
                      headers,
                      body: init.body == null ? null : String(init.body),
                    });
                    return new Response(decode(result.body_base64), {
                      status: result.status,
                      headers: result.headers,
                    });
                  };
                })();
            """

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=shutil.which("chromium"),
                    args=["--no-sandbox"],
                )
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.expose_function("__paceboardApi", api_call)
                page.set_content(index, wait_until="domcontentloaded")
                page.add_script_tag(content=fetch_bridge)
                page.add_script_tag(content=(ROOT / "app.js").read_text(encoding="utf-8"))
                expect(page.locator("#connection-status")).to_have_text("Local workspace ready")
                expect(page.locator("#summary-active")).to_have_text("0")

                page.get_by_role("button", name="Add a goal").click()
                page.locator("#goal-title").fill("Read for ten minutes")
                page.locator("#goal-intention").fill("Leave work mode gently")
                page.locator("#goal-reminder").select_option("0")
                page.locator("#goal-focus").fill("1")
                page.get_by_role("button", name="Save goal").click()
                expect(page.locator("#summary-active")).to_have_text("1")
                goal = page.locator(".goal-card", has_text="Read for ten minutes")
                expect(goal).to_be_visible()

                page.once("dialog", lambda dialog: dialog.accept("Today needs a pause."))
                goal.get_by_role("button", name="Pause day").click()
                expect(goal.locator(".latest-checkin")).to_contain_text("Paused without penalty")

                page.once("dialog", lambda dialog: dialog.accept("Tomorrow feels workable."))
                goal.get_by_role("button", name="Resume").click()
                expect(goal.locator(".latest-checkin")).to_contain_text("Resumed when ready")

                page.once("dialog", lambda dialog: dialog.accept("1"))
                goal.get_by_role("button", name="Start focus").click()
                focus = page.locator(".focus-card", has_text="Read for ten minutes")
                expect(focus).to_be_visible()
                focus.get_by_role("button", name="Pause").click()
                expect(focus).to_contain_text("PAUSED")
                focus.get_by_role("button", name="Resume").click()
                expect(focus).to_contain_text("RUNNING")
                focus.get_by_role("button", name="Finish").click()
                expect(focus).to_contain_text("FINISHED")

                page.locator("#note-goal").select_option(index=1)
                page.locator("#note-body").fill("Putting the book in reach reduced friction.")
                page.get_by_role("button", name="Save private note").click()
                expect(page.locator("#history")).to_contain_text("TRIGGER_NOTE")
                expect(page.locator("#history")).to_contain_text("RESUMED")

                with page.expect_download() as download_info:
                    page.locator("#export-json").click()
                backup_path = workspace / "paceboard-backup.json"
                download_info.value.save_as(backup_path)
                backup = json.loads(backup_path.read_text(encoding="utf-8"))
                self.assertEqual(backup["format"], "paceboard-backup/v1")
                self.assertEqual(len(backup["data"]["goals"]), 1)
                self.assertEqual(len(backup["data"]["trigger_notes"]), 1)
                self.assertEqual(len(backup["content_sha256"]), 64)

                with page.expect_download() as csv_info:
                    page.locator("#export-csv").click()
                csv_path = workspace / "paceboard-history.csv"
                csv_info.value.save_as(csv_path)
                csv_text = csv_path.read_text(encoding="utf-8")
                self.assertIn("TRIGGER_NOTE", csv_text)
                self.assertIn("FOCUS_FINISHED", csv_text)

                page.locator(".danger-zone > summary").click()
                page.locator("#erase-confirm").fill("ERASE PACEBOARD")
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("#erase-button").click()
                expect(page.locator("#summary-active")).to_have_text("0")
                expect(page.locator("#empty-goals")).to_be_visible()

                page.locator("#restore-file").set_input_files(str(backup_path))
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator("#restore-button").click()
                expect(page.locator("#summary-active")).to_have_text("1")
                expect(page.locator(".goal-card", has_text="Read for ten minutes")).to_be_visible()
                expect(page.locator("#history")).to_contain_text("TRIGGER_NOTE")

                state = page.evaluate("() => fetch('/api/state', {cache: 'no-store'}).then(r => r.json())")
                self.assertTrue(state["authority"]["local_only"])
                self.assertFalse(state["authority"]["external_notification_authorized"])
                self.assertFalse(state["authority"]["treatment_or_diagnosis"])
                context.close()
                browser.close()

            self.assertEqual(console_errors, [])


if __name__ == "__main__":
    unittest.main()
