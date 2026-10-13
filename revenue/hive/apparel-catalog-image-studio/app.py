#!/usr/bin/env python3
"""Loopback web desk for Apparel Catalog Image Studio."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlparse

from studio import (
    BACKGROUNDS, MODELS, StudioError, StudioStore, audit_garment, build_catalog,
    canonical_json, decode_png, parse_hex, render_scene, resolve_under, sha256_bytes,
)

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
MAX_UPLOAD = 8_000_000


def safe_name(value: str) -> str:
    name = Path(value or "garment.png").name
    if not name.lower().endswith(".png"):
        name += ".png"
    stem = "".join(ch for ch in Path(name).stem if ch.isalnum() or ch in "._-")[:60] or "garment"
    return stem + ".png"


class CatalogServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, workspace: Path):
        self.workspace = workspace.resolve()
        self.imports = self.workspace / "imports"
        self.specs = self.workspace / "specs"
        self.exports = self.workspace / "exports"
        for path in (self.imports, self.specs, self.exports):
            path.mkdir(parents=True, exist_ok=True)
        self.store = StudioStore(self.workspace / "studio.sqlite3")
        super().__init__(address, Handler)

    def server_close(self) -> None:
        try:
            self.store.close()
        finally:
            super().server_close()


class Handler(BaseHTTPRequestHandler):
    server: CatalogServer
    server_version = "ApparelCatalogStudio/1"

    def log_message(self, *_args) -> None:
        pass

    def _json(self, status: int, value: dict) -> None:
        raw = canonical_json(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _read_json(self, limit: int = 1_000_000) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise StudioError("invalid Content-Length") from exc
        if length <= 0 or length > limit:
            raise StudioError(f"JSON body must be 1..{limit} bytes")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudioError(f"invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise StudioError("JSON body must be an object")
        return value

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                raw = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/api/health":
                self._json(200, {"ok": True, "network": "loopback-only", "external_generation": False,
                                 "backgrounds": list(BACKGROUNDS), "models": list(MODELS)})
                return
            if path.startswith("/api/projects/"):
                project_id = path.split("/")[-1]
                self._json(200, {"ok": True, "project": self.server.store.get_project(project_id)})
                return
            self._error(404, "not found")
        except (StudioError, OSError) as exc:
            self._error(400, str(exc))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/import":
                self._import()
                return
            if path == "/api/projects":
                self._create_project()
                return
            if path.startswith("/api/projects/") and path.endswith("/revisions"):
                self._revise(path.split("/")[-2])
                return
            if path.startswith("/api/projects/") and path.endswith("/render"):
                self._render(path.split("/")[-2])
                return
            if path.startswith("/api/projects/") and path.endswith("/catalog"):
                self._catalog(path.split("/")[-2])
                return
            self._error(404, "not found")
        except (StudioError, OSError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def _import(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise StudioError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_UPLOAD:
            raise StudioError(f"PNG upload must be 1..{MAX_UPLOAD} bytes")
        raw = self.rfile.read(length)
        width, height, _ = decode_png(raw)
        base = safe_name(self.headers.get("X-Filename", "garment.png"))
        digest = sha256_bytes(raw)
        name = f"{Path(base).stem}-{digest[:12]}.png"
        destination = self.server.imports / name
        if destination.exists():
            if destination.read_bytes() != raw:
                raise StudioError("existing import path has different bytes")
        else:
            fd, temp_name = tempfile.mkstemp(prefix=name + ".", dir=self.server.imports)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, destination)
            except Exception:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        self._json(201, {"ok": True, "file": name, "sha256": digest, "dimensions": [width, height], "bytes": len(raw)})

    def _create_project(self) -> None:
        value = self._read_json()
        project_id = value.get("id")
        source_name = value.get("source")
        sku, name, size = value.get("sku"), value.get("name"), value.get("size")
        for label, item in (("id", project_id), ("source", source_name), ("sku", sku), ("name", name), ("size", size)):
            if not isinstance(item, str) or not item.strip():
                raise StudioError(f"{label} must be nonempty text")
        source_path = resolve_under(self.server.imports, source_name)
        raw = source_path.read_bytes()
        width, height, _ = decode_png(raw)
        checks = value.get("detail_checks", [])
        colors = value.get("declared_colors", [])
        if not isinstance(checks, list) or not isinstance(colors, list):
            raise StudioError("detail_checks and declared_colors must be lists")
        spec = {
            "sku": sku, "name": name, "size": size,
            "source": source_name,
            "source_sha256": sha256_bytes(raw),
            "source_dimensions": [width, height],
            "declared_colors": colors,
            "detail_checks": checks,
            "rights": value.get("rights", "operator-attested-authorized"),
        }
        preset = value.get("preset")
        if not isinstance(preset, dict):
            raise StudioError("preset must be an object")
        # Validate values before persisting by rendering them through normal validators.
        parse_hex(preset.get("accent"), "preset accent")
        scenes = preset.get("scenes")
        if not isinstance(scenes, list) or len(scenes) != 10:
            raise StudioError("preset scenes must contain exactly 10 scenes")
        for scene in scenes:
            if not isinstance(scene, dict) or scene.get("background") not in BACKGROUNDS or scene.get("model") not in MODELS:
                raise StudioError("preset contains an unknown background/model scene")
        if not isinstance(preset.get("id"), str) or not isinstance(preset.get("brand"), str):
            raise StudioError("preset id and brand must be text")
        if "canvas" not in preset:
            preset["canvas"] = [720, 720]
        spec_path = self.server.specs / f"{project_id}.garment.json"
        preset_path = self.server.specs / f"{project_id}.preset.json"
        if spec_path.exists() or preset_path.exists():
            raise StudioError("project spec files already exist")
        # Spec source is relative to the spec directory. Copy exact bytes to a project-local source.
        project_source = self.server.specs / f"{project_id}.source.png"
        project_source.write_bytes(raw)
        spec["source"] = project_source.name
        spec_path.write_text(canonical_json(spec), encoding="utf-8")
        preset_path.write_text(canonical_json(preset), encoding="utf-8")
        try:
            audit_garment(spec_path)
            state = self.server.store.create_project(project_id, spec, preset, source_name)
        except Exception:
            for item in (spec_path, preset_path, project_source):
                item.unlink(missing_ok=True)
            raise
        self._json(201, {"ok": True, "project": state})

    def _revise(self, project_id: str) -> None:
        value = self._read_json()
        state = self.server.store.revise(
            project_id,
            expected_revision=value.get("expected_revision"),
            background=value.get("background"), model=value.get("model"),
            offset_x=value.get("offset_x", 0), offset_y=value.get("offset_y", 0),
            note=value.get("note", ""),
        )
        self._json(200, {"ok": True, "project": state})

    def _render(self, project_id: str) -> None:
        project = self.server.store.get_project(project_id)
        revision = project["revisions"][-1]
        spec_path = self.server.specs / f"{project_id}.garment.json"
        preset_path = self.server.specs / f"{project_id}.preset.json"
        output = self.server.exports / project_id / f"revision-{revision['revision']:03d}.png"
        entry = render_scene(spec_path, preset_path, {"background": revision["background"], "model": revision["model"]}, output,
                             offset_x=revision["offset_x"], offset_y=revision["offset_y"])
        self._json(200, {"ok": True, "render": entry, "path": output.relative_to(self.server.workspace).as_posix()})

    def _catalog(self, project_id: str) -> None:
        project = self.server.store.get_project(project_id)
        revision = project["revisions"][-1]
        spec_path = self.server.specs / f"{project_id}.garment.json"
        preset_path = self.server.specs / f"{project_id}.preset.json"
        output = self.server.exports / project_id / f"catalog-r{revision['revision']:03d}"
        manifest = build_catalog(spec_path, preset_path, output)
        self._json(200, {"ok": True, "manifest": manifest, "path": output.relative_to(self.server.workspace).as_posix()})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "workspace")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8878)
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("this local studio may bind only to loopback")
    server = CatalogServer((args.host, args.port), args.workspace)
    host, port = server.server_address[:2]
    print(f"Apparel Catalog Image Studio http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
