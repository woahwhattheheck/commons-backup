#!/usr/bin/env python3
from __future__ import annotations

import base64
import copy
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deskmod = load_module("catalog_desk_tested", HERE / "catalog_desk.py")


class DeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the real checked-in bundle extractor and exact canonical core.
        cls.desk = deskmod.CatalogDesk(HERE)
        cls.core_root = Path(cls.desk.core.__file__).resolve().parent
        cls.catalog = (cls.core_root / "examples/catalog.csv").read_bytes()
        cls.complete = json.loads((cls.core_root / "examples/translations.es-ES.json").read_text(encoding="utf-8"))
        cls.glossary = json.loads((cls.core_root / "examples/glossary.es-ES.json").read_text(encoding="utf-8"))
        cls.profile = json.loads((cls.core_root / "examples/locale.es-ES.json").read_text(encoding="utf-8"))

    def new(self, *, defaults: bool = False):
        kwargs = {} if defaults else {"glossary": self.glossary, "locale_profile": self.profile}
        return self.desk.new_workspace(
            catalog_name="catalog.csv",
            catalog_bytes=self.catalog,
            source_locale="en-US",
            target_locale="es-ES",
            **kwargs,
        )

    def filled(self):
        ws = self.new()
        edits = []
        for sku, entry in self.complete["products"].items():
            for field, value in entry["target"].items():
                edits.append({"sku": sku, "field": field, "value": value})
        return self.desk.apply_edits(ws, edits)

    def test_blank_workspace_publishes_draft_only(self):
        result = self.desk.publish(self.new())
        self.assertFalse(result["ready"])
        self.assertTrue(result["manifest"]["draft_files"])
        self.assertEqual([], result["manifest"]["store_ready_files"])
        self.assertIn("DRAFT-REVIEW-REQUIRED", result["download_name"])
        self.assertGreater(len(result["review"]), 0)

    def test_default_settings_are_valid_and_still_draft(self):
        ws = self.new(defaults=True)
        reopened = self.desk.validate_workspace(ws)
        self.assertEqual(ws, reopened)
        result = self.desk.publish(reopened)
        self.assertFalse(result["ready"])
        self.assertEqual([], result["manifest"]["store_ready_files"])

    def test_complete_workspace_publishes_store_ready(self):
        result = self.desk.publish(self.filled())
        self.assertTrue(result["ready"])
        self.assertEqual(2, len(result["manifest"]["store_ready_files"]))
        self.assertEqual([], result["manifest"]["draft_files"])
        self.assertIn("STORE-READY", result["download_name"])
        payload = base64.b64decode(result["download_b64"], validate=True)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
        self.assertIn("manifest.json", names)
        self.assertTrue(any(name.startswith("catalog.es-ES.") for name in names))

    def test_protected_field_edit_is_rejected(self):
        with self.assertRaisesRegex(deskmod.DeskError, "protected or unknown"):
            self.desk.apply_edits(
                self.new(),
                [{"sku": "TEA-001", "field": "price", "value": "0.01"}],
            )

    def test_duplicate_edit_target_is_rejected(self):
        edit = {"sku": "TEA-001", "field": "name", "value": "uno"}
        with self.assertRaisesRegex(deskmod.DeskError, "duplicate edit"):
            self.desk.apply_edits(self.new(), [edit, dict(edit, value="dos")])

    def test_tampered_source_snapshot_is_rejected(self):
        ws = self.new()
        ws["translations"]["products"]["TEA-001"]["source"]["name"] = "tampered"
        with self.assertRaisesRegex(deskmod.DeskError, "source snapshot"):
            self.desk.validate_workspace(ws)

    def test_catalog_byte_tamper_is_rejected(self):
        ws = self.new()
        raw = base64.b64decode(ws["catalog_b64"])
        ws["catalog_b64"] = base64.b64encode(raw + b"\n").decode("ascii")
        with self.assertRaisesRegex(deskmod.DeskError, "catalog_sha256"):
            self.desk.validate_workspace(ws)

    def test_path_like_catalog_name_is_rejected(self):
        with self.assertRaisesRegex(deskmod.DeskError, "plain filename"):
            self.desk.new_workspace(
                catalog_name="../catalog.csv",
                catalog_bytes=self.catalog,
                source_locale="en-US",
                target_locale="es-ES",
            )

    def test_workspace_export_reopen_is_deterministic(self):
        ws = self.filled()
        first = self.desk.export_workspace(ws)
        reopened = self.desk.validate_workspace(json.loads(first))
        second = self.desk.export_workspace(reopened)
        self.assertEqual(first, second)

    def test_revision_changes_only_target_and_preserves_previous(self):
        ws = self.filled()
        old = ws["translations"]["products"]["TEA-001"]["target"]["description"]
        new = old + " Edición revisada."
        revised = self.desk.revise(
            ws,
            revision_id="desk-r1",
            changes=[{
                "sku": "TEA-001",
                "field": "description",
                "expected": old,
                "value": new,
                "reason": "editor correction",
            }],
        )
        self.assertEqual(
            old,
            revised["previous_translations"]["products"]["TEA-001"]["target"]["description"],
        )
        self.assertEqual(
            new,
            revised["translations"]["products"]["TEA-001"]["target"]["description"],
        )
        self.assertEqual(1, len(revised["revision_receipts"]))
        self.assertEqual(
            ws["translations"]["products"]["TEA-001"]["source"],
            revised["translations"]["products"]["TEA-001"]["source"],
        )

    def test_wrong_locale_settings_fail_closed(self):
        ws = self.new()
        bad = copy.deepcopy(self.profile)
        bad["locale"] = "fr-FR"
        with self.assertRaisesRegex(deskmod.DeskError, "target locale"):
            self.desk.replace_settings(ws, glossary=self.glossary, locale_profile=bad)

    def test_http_status_and_template_boundary(self):
        handler = type("TestDeskHandler", (deskmod.DeskHandler,), {"desk": self.desk})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/api/status")
            response = conn.getresponse()
            status_payload = json.loads(response.read())
            self.assertEqual(200, response.status)
            self.assertEqual("loopback-only", status_payload["network"])
            self.assertEqual(list(self.desk.fields), status_payload["translation_fields"])

            request = {
                "catalog_name": "catalog.csv",
                "catalog_b64": base64.b64encode(self.catalog).decode("ascii"),
                "source_locale": "en-US",
                "target_locale": "es-ES",
            }
            body = json.dumps(request).encode("utf-8")
            conn.request(
                "POST",
                "/api/template",
                body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(200, response.status)
            self.assertEqual("workspace_created", payload["status"])
            self.assertEqual(
                deskmod.WORKSPACE_SCHEMA,
                payload["workspace"]["schema"],
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_http_rejects_wrong_content_type(self):
        handler = type("TestDeskHandlerBadType", (deskmod.DeskHandler,), {"desk": self.desk})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            conn.request(
                "POST",
                "/api/open",
                body=b"{}",
                headers={"Content-Type": "text/plain", "Content-Length": "2"},
            )
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(400, response.status)
            self.assertIn("Content-Type", payload["error"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_server_refuses_non_loopback_binding(self):
        with self.assertRaisesRegex(SystemExit, "loopback-only"):
            deskmod.serve(host="0.0.0.0", port=0, bundle_dir=HERE)


if __name__ == "__main__":
    unittest.main()
