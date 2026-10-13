#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

import app
from studio import (
    BACKGROUNDS, MODELS, StudioError, StudioStore, audit_garment, build_catalog,
    canonical_json, create_sample, decode_png, encode_png, load_json, render_scene,
    sha256_bytes,
)

ROOT = Path(__file__).resolve().parent


class SampleMixin:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parts = create_sample(self.root / "sample")


class PngAndAuditTests(SampleMixin, unittest.TestCase):
    def test_sample_png_roundtrip_and_expected_source(self):
        raw = self.parts["source"].read_bytes()
        width, height, rgba = decode_png(raw)
        self.assertEqual((width, height), (240, 280))
        self.assertEqual(decode_png(encode_png(width, height, rgba)), (width, height, rgba))
        audit = audit_garment(self.parts["garment"])
        self.assertEqual(audit["sku"], "SYN-TEE-001")
        self.assertEqual(audit["size"], "M")
        self.assertEqual(len(audit["detail_checks"]), 4)
        self.assertEqual(audit["source_sha256"], sha256_bytes(raw))
        self.assertGreater(audit["visible_pixels"], 20_000)

    def test_source_hash_tamper_is_rejected_without_mutating_files(self):
        spec = load_json(self.parts["garment"])
        spec["source_sha256"] = "0" * 64
        bad = self.parts["garment"].parent / "bad.json"
        bad.write_text(canonical_json(spec), encoding="utf-8")
        before = self.parts["source"].read_bytes()
        with self.assertRaisesRegex(StudioError, "SHA-256"):
            audit_garment(bad)
        self.assertEqual(self.parts["source"].read_bytes(), before)

    def test_wrong_color_and_detail_coordinates_are_rejected(self):
        spec = load_json(self.parts["garment"])
        spec["declared_colors"] = ["#010203"]
        bad = self.parts["garment"].parent / "color.json"
        bad.write_text(canonical_json(spec), encoding="utf-8")
        with self.assertRaisesRegex(StudioError, "not present"):
            audit_garment(bad)
        spec = load_json(self.parts["garment"])
        spec["detail_checks"][0]["color"] = "#FFFFFF"
        bad.write_text(canonical_json(spec), encoding="utf-8")
        with self.assertRaisesRegex(StudioError, "body navy"):
            audit_garment(bad)

    def test_png_crc_and_path_escape_are_rejected(self):
        raw = bytearray(self.parts["source"].read_bytes())
        raw[30] ^= 1
        with self.assertRaisesRegex(StudioError, "CRC"):
            decode_png(bytes(raw))
        spec = load_json(self.parts["garment"])
        outside = self.root / "outside.png"
        outside.write_bytes(self.parts["source"].read_bytes())
        spec["source"] = "../outside.png"
        escaped = self.parts["garment"].parent / "escaped.json"
        escaped.write_text(canonical_json(spec), encoding="utf-8")
        with self.assertRaisesRegex(StudioError, "escapes"):
            audit_garment(escaped)


class RenderAndCatalogTests(SampleMixin, unittest.TestCase):
    def test_all_ten_images_are_real_distinct_pngs_with_exact_opaque_pixels(self):
        output = self.root / "catalog"
        manifest = build_catalog(self.parts["garment"], self.parts["preset"], output)
        self.assertEqual(manifest["image_count"], 10)
        hashes = set()
        source_w, source_h, source_rgba = decode_png(self.parts["source"].read_bytes())
        for row in manifest["images"]:
            raw = (output / "images" / row["file"]).read_bytes()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            width, height, rendered = decode_png(raw)
            self.assertEqual((width, height), (720, 720))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row["sha256"])
            self.assertEqual(row["opaque_pixel_fidelity"], "BYTE_EXACT_RGBA")
            x0, y0 = row["placement"]
            checked = 0
            for y in range(source_h):
                for x in range(source_w):
                    si = (y * source_w + x) * 4
                    pixel = source_rgba[si:si + 4]
                    if pixel[3] == 255:
                        di = ((y0 + y) * width + x0 + x) * 4
                        self.assertEqual(rendered[di:di + 4], pixel)
                        checked += 1
            self.assertEqual(checked, row["opaque_pixels_copied_exact"])
            hashes.add(row["sha256"])
        self.assertEqual(len(hashes), 10)
        self.assertTrue(manifest["truth"]["opaque_garment_pixels_modified"] is False)

    def test_catalog_preserves_exact_source_and_has_complete_zip(self):
        output = self.root / "catalog"
        manifest = build_catalog(self.parts["garment"], self.parts["preset"], output)
        self.assertEqual((output / "source" / "garment.png").read_bytes(), self.parts["source"].read_bytes())
        with zipfile.ZipFile(output / "catalog.zip") as archive:
            names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("catalog.csv", names)
            self.assertIn("source/garment.png", names)
            image_names = [name for name in names if name.startswith("images/") and name.endswith(".png")]
            self.assertEqual(len(image_names), 10)
            self.assertEqual(archive.read("source/garment.png"), self.parts["source"].read_bytes())
            parsed = json.loads(archive.read("manifest.json"))
            self.assertEqual(parsed["garment"]["source_sha256"], manifest["garment"]["source_sha256"])

    def test_rebuild_is_byte_deterministic(self):
        one, two = self.root / "one", self.root / "two"
        first = build_catalog(self.parts["garment"], self.parts["preset"], one)
        second = build_catalog(self.parts["garment"], self.parts["preset"], two)
        self.assertEqual(canonical_json(first), canonical_json(second))
        paths1 = sorted(p.relative_to(one) for p in one.rglob("*") if p.is_file())
        paths2 = sorted(p.relative_to(two) for p in two.rglob("*") if p.is_file())
        self.assertEqual(paths1, paths2)
        for rel in paths1:
            self.assertEqual((one / rel).read_bytes(), (two / rel).read_bytes(), rel)

    def test_oversized_source_refuses_resampling_and_preserves_no_output(self):
        spec = load_json(self.parts["garment"])
        preset = load_json(self.parts["preset"])
        preset["canvas"] = [320, 320]
        p = self.root / "small-preset.json"
        p.write_text(canonical_json(preset), encoding="utf-8")
        # Existing source still fits 320x320, so make the source logically wider using a real PNG.
        rgba = bytes((20, 30, 40, 255)) * (330 * 280)
        wide = self.parts["garment"].parent / "wide.png"
        wide.write_bytes(encode_png(330, 280, rgba))
        spec["source"] = "wide.png"
        spec["source_sha256"] = sha256_bytes(wide.read_bytes())
        spec["source_dimensions"] = [330, 280]
        spec["declared_colors"] = ["#141E28"]
        spec["detail_checks"] = []
        s = self.parts["garment"].parent / "wide.json"
        s.write_text(canonical_json(spec), encoding="utf-8")
        output = self.root / "too-small.png"
        with self.assertRaisesRegex(StudioError, "refuses resampling"):
            render_scene(s, p, preset["scenes"][0], output)
        self.assertFalse(output.exists())


class StoreTests(SampleMixin, unittest.TestCase):
    def test_revisions_persist_and_stale_revision_does_not_overwrite(self):
        db = self.root / "studio.sqlite3"
        spec, preset = load_json(self.parts["garment"]), load_json(self.parts["preset"])
        store = StudioStore(db)
        try:
            first = store.create_project("project-1", spec, preset, "garment.png", created_at="2026-09-08T12:00:00Z")
            self.assertEqual(first["revisions"][-1]["revision"], 1)
            second = store.revise("project-1", expected_revision=1, background="sand", model="warm", note="buyer wants sand", created_at="2026-09-08T12:01:00Z")
            self.assertEqual(second["revisions"][-1]["revision"], 2)
            with self.assertRaisesRegex(StudioError, "revision conflict"):
                store.revise("project-1", expected_revision=1, background="mist", model="cool")
        finally:
            store.close()
        reopened = StudioStore(db)
        try:
            state = reopened.get_project("project-1")
            self.assertEqual(len(state["revisions"]), 2)
            self.assertEqual(state["revisions"][-1]["note"], "buyer wants sand")
        finally:
            reopened.close()


class HttpWorkflowTests(SampleMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.workspace = self.root / "workspace"
        self.server = app.CatalogServer(("127.0.0.1", 0), self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, method, path, body=b"", headers=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, json.loads(raw) if raw else None

    def post_json(self, path, value):
        raw = json.dumps(value).encode()
        return self.request("POST", path, raw, {"Content-Type": "application/json", "Content-Length": str(len(raw))})

    def test_real_import_project_revision_render_catalog_restart_state(self):
        source = self.parts["source"].read_bytes()
        status, imported = self.request("POST", "/api/import", source, {"Content-Type": "application/octet-stream", "Content-Length": str(len(source)), "X-Filename": "tee.png"})
        self.assertEqual(status, 201)
        spec = load_json(self.parts["garment"])
        preset = load_json(self.parts["preset"])
        status, created = self.post_json("/api/projects", {"id": "http-project", "source": imported["file"], "sku": spec["sku"], "name": spec["name"], "size": spec["size"], "declared_colors": spec["declared_colors"], "detail_checks": spec["detail_checks"], "rights": "synthetic-original", "preset": preset})
        self.assertEqual(status, 201, created)
        self.assertEqual(created["project"]["revisions"][-1]["revision"], 1)
        status, revised = self.post_json("/api/projects/http-project/revisions", {"expected_revision": 1, "background": "sage", "model": "deep", "note": "alternate scene"})
        self.assertEqual((status, revised["project"]["revisions"][-1]["revision"]), (200, 2))
        status, rendered = self.post_json("/api/projects/http-project/render", {})
        self.assertEqual(status, 200, rendered)
        render_path = self.workspace / rendered["path"]
        self.assertTrue(render_path.exists())
        self.assertEqual(rendered["render"]["scene"], {"background": "sage", "model": "deep"})
        status, catalog = self.post_json("/api/projects/http-project/catalog", {})
        self.assertEqual(status, 200, catalog)
        catalog_path = self.workspace / catalog["path"]
        self.assertEqual(len(list((catalog_path / "images").glob("*.png"))), 10)
        self.assertTrue((catalog_path / "catalog.zip").exists())
        status, state = self.request("GET", "/api/projects/http-project")
        self.assertEqual(status, 200)
        self.assertEqual(len(state["project"]["revisions"]), 2)
        # The exact imported bytes were never altered.
        imported_path = self.workspace / "imports" / imported["file"]
        self.assertEqual(imported_path.read_bytes(), source)

    def test_invalid_upload_and_stale_revision_are_structured_errors(self):
        status, body = self.request("POST", "/api/import", b"not-png", {"Content-Length": "7", "X-Filename": "bad.png"})
        self.assertEqual(status, 400)
        self.assertIn("PNG", body["error"])
        source = self.parts["source"].read_bytes()
        _, imported = self.request("POST", "/api/import", source, {"Content-Length": str(len(source)), "X-Filename": "tee.png"})
        spec, preset = load_json(self.parts["garment"]), load_json(self.parts["preset"])
        self.post_json("/api/projects", {"id": "p2", "source": imported["file"], "sku": spec["sku"], "name": spec["name"], "size": spec["size"], "declared_colors": spec["declared_colors"], "detail_checks": spec["detail_checks"], "preset": preset})
        self.post_json("/api/projects/p2/revisions", {"expected_revision": 1, "background": "sand", "model": "warm"})
        status, body = self.post_json("/api/projects/p2/revisions", {"expected_revision": 1, "background": "mist", "model": "cool"})
        self.assertEqual(status, 400)
        self.assertIn("revision conflict", body["error"])


class BrowserAssetTests(unittest.TestCase):
    def test_index_has_no_external_assets_and_javascript_parses(self):
        text = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("http://", text.lower().replace("http://127.0.0.1:8878", ""))
        self.assertNotIn("https://", text.lower())
        self.assertIn("type=\"file\"", text)
        self.assertIn("/api/import", text)
        start, end = text.index("<script>") + len("<script>"), text.index("</script>")
        script = text[start:end]
        node = shutil.which("node")
        if not node:
            self.skipTest("Node not installed")
        temp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
        try:
            temp.write(script)
            temp.close()
            result = subprocess.run([node, "--check", temp.name], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            os.unlink(temp.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
