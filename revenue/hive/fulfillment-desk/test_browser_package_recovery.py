"""Browser-produced Parcel deployment packages retain receiver-recovery semantics.

This closes the explicit adapter-backed browser -> Deployment JSON -> bundle -> extracted
package boundary. It does not claim normal-origin navigation or native localStorage.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import zipfile

from playwright.sync_api import sync_playwright

from test_bundle_receiver_recovery import ReceiverRecoveryTests, bundle, RUNNER

ROOT = Path(__file__).resolve().parent
PRESETS = ("client-intake", "quote-request", "service-request")
SOURCE_REVISION = "e8e5f5b3aefbdad2947ec822fa07d0cc5589b9d5"
HTML = re.sub(r'<script src="(?:model|app)\.js"></script>', '', (ROOT / "index.html").read_text())


class BrowserPackageRecoveryTests(ReceiverRecoveryTests):
    """Run the landed recovery contract against exact browser-downloaded deployments."""

    def browser_deployment_bytes(self, preset: str) -> bytes:
        index = PRESETS.index(preset)
        errors: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.set_content(HTML)
                page.evaluate(
                    """() => {
                      window.parcelMap = new Map();
                      window.ParcelStorage = {
                        getItem: key => parcelMap.has(key) ? parcelMap.get(key) : null,
                        setItem: (key, value) => parcelMap.set(key, value)
                      };
                    }"""
                )
                page.add_script_tag(content=(ROOT / "model.js").read_text())
                page.add_script_tag(content=(ROOT / "app.js").read_text())
                self.assertEqual(page.locator(".template").count(), 3)
                page.locator(".template").nth(index).click()
                self.assertEqual(page.locator("[name=workflowId]").input_value(), preset)
                page.locator("#tab-delivery").click()
                with page.expect_download() as download:
                    page.locator("#download-deployment").click()
                raw = Path(download.value.path()).read_bytes()
                self.assertFalse(errors, errors)
                return raw
            finally:
                browser.close()

    def build_browser_package(self, preset: str) -> dict:
        work = self.root / preset
        work.mkdir(parents=True, exist_ok=True)
        self.package = work / "package"
        self.output = work / "package.zip"
        self.deployment = work / "browser-deployment.json"
        self.db_name = f"{preset}.sqlite3"
        raw = self.browser_deployment_bytes(preset)
        self.deployment.write_bytes(raw)
        value = json.loads(raw)
        self.assertEqual(value["preset"], preset)
        self.assertEqual(value["format"], "parcel.intake-handoff")
        self.assertEqual(value["version"], 1)
        self.assertEqual(len(value["tasks"]), 3)
        self.assertEqual(value["exampleIntake"]["id"], f"{value['orderId']}-smoke-v{value['specRevision']}")
        bundle.build(self.deployment, RUNNER, self.output, SOURCE_REVISION)
        self.package.mkdir()
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(self.package)
            packaged = json.loads(archive.read("parcel.json"))
        self.assertEqual(packaged, value)
        return value

    def test_ambiguous_receiver_retry_survives_restart_without_duplicate_application(self):
        observed = []
        original_builder = self.build_and_unpack
        try:
            for preset in PRESETS:
                with self.subTest(preset=preset):
                    value = self.build_browser_package(preset)
                    # The landed receiver-recovery contract owns the HTTP failure fixture and
                    # sender assertions. Skip only its synthetic deployment builder so it runs
                    # against the exact package extracted above.
                    self.build_and_unpack = lambda: None
                    super().test_ambiguous_receiver_retry_survives_restart_without_duplicate_application()
                    observed.append((preset, tuple(value["tasks"])))
                    self.stop_all_package_servers()
                    self.server_processes.clear()
        finally:
            self.build_and_unpack = original_builder
        self.assertEqual([preset for preset, _ in observed], list(PRESETS))
        self.assertEqual(len({tasks for _, tasks in observed}), 3)


if __name__ == "__main__":
    import unittest
    unittest.main()
