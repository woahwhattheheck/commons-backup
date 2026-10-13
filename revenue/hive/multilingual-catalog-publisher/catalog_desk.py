#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local browser desk for the exact HIVE047 multilingual catalog publisher.

The desk is deliberately stateless: a portable workspace JSON carries the exact
catalog bytes plus target-locale work. Publishing always delegates to the
hash-bound canonical catalog_publisher.py from the shipped source bundle.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePath
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Sequence
import zipfile

WORKSPACE_SCHEMA = "hive.multilingual-catalog-desk.v1"
MAX_CATALOG_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
PRODUCT_ROOT = Path(__file__).resolve().parent
HTML_PATH = PRODUCT_ROOT / "desk.html"


class DeskError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _safe_catalog_name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise DeskError("catalog_name must be a nonempty string")
    if value != PurePath(value).name or value in {".", ".."}:
        raise DeskError("catalog_name must be a plain filename")
    if Path(value).suffix.lower() not in {".csv", ".json"}:
        raise DeskError("catalog_name must end in .csv or .json")
    return value


def _decode_catalog(workspace: Mapping[str, Any]) -> bytes:
    encoded = workspace.get("catalog_b64")
    if not isinstance(encoded, str):
        raise DeskError("catalog_b64 must be a base64 string")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise DeskError(f"catalog_b64 is invalid base64: {exc}") from exc
    if not payload or len(payload) > MAX_CATALOG_BYTES:
        raise DeskError(f"catalog must contain 1..{MAX_CATALOG_BYTES} bytes")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeskError("catalog must be UTF-8 CSV or JSON") from exc
    return payload


def _strict_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeskError(f"{label} must be an object")
    return value


class CoreLoader:
    """Extract and import the exact core without modifying the repository."""

    def __init__(self, bundle_dir: Path):
        self.bundle_dir = bundle_dir.resolve()
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self.module = self._load()

    def _load(self):
        extractor = self.bundle_dir / "extract_source_bundle.py"
        if not extractor.is_file():
            raise DeskError(f"missing exact-source extractor: {extractor}")
        self._tmp = tempfile.TemporaryDirectory(prefix="catalog-desk-core-")
        proc = subprocess.run(
            [sys.executable, "-B", str(extractor), "--bundle-dir", str(self.bundle_dir),
             "--destination", self._tmp.name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            timeout=30,
        )
        if proc.returncode:
            raise DeskError(f"exact-source extraction failed: {proc.stderr.strip() or proc.stdout.strip()}")
        path = Path(self._tmp.name) / "revenue/hive/multilingual-catalog-publisher/catalog_publisher.py"
        spec = importlib.util.spec_from_file_location("_hive047_catalog_publisher", path)
        if spec is None or spec.loader is None:
            raise DeskError("cannot load exact catalog publisher")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


class CatalogDesk:
    def __init__(self, bundle_dir: Path = PRODUCT_ROOT, *, core: Any | None = None):
        self.bundle_dir = Path(bundle_dir).resolve()
        self._loader = None if core is not None else CoreLoader(self.bundle_dir)
        self.core = core if core is not None else self._loader.module
        self.fields = tuple(self.core.TRANSLATABLE_FIELDS)

    def _write_catalog(self, directory: Path, workspace: Mapping[str, Any]) -> Path:
        name = _safe_catalog_name(workspace.get("catalog_name"))
        payload = _decode_catalog(workspace)
        # User filenames may also name generated translations/settings files.
        # Keep their exact bytes separate throughout validation and publishing.
        source_directory = directory / "source-catalog"
        source_directory.mkdir(exist_ok=True)
        path = source_directory / name
        path.write_bytes(payload)
        return path

    @staticmethod
    def default_glossary(source_locale: str, target_locale: str) -> dict[str, Any]:
        return {
            "schema": "hive.multilingual-catalog-glossary.v1",
            "source_locale": source_locale,
            "target_locale": target_locale,
            "terms": [],
        }

    @staticmethod
    def default_profile(target_locale: str) -> dict[str, Any]:
        return {
            "schema": "hive.multilingual-catalog-locale-profile.v1",
            "locale": target_locale,
            "decimal_separator": ".",
            "group_separator": ",",
            "currency_pattern": "{symbol}{amount}",
            "minor_digits": 2,
            "unit_labels": {},
            "currency_symbols": {},
        }

    def new_workspace(
        self,
        *,
        catalog_name: str,
        catalog_bytes: bytes,
        source_locale: str,
        target_locale: str,
        glossary: Mapping[str, Any] | None = None,
        locale_profile: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        _safe_catalog_name(catalog_name)
        if not isinstance(catalog_bytes, (bytes, bytearray)) or not catalog_bytes:
            raise DeskError("catalog_bytes must be nonempty bytes")
        if len(catalog_bytes) > MAX_CATALOG_BYTES:
            raise DeskError("catalog is too large")
        try:
            bytes(catalog_bytes).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeskError("catalog must be UTF-8 CSV or JSON") from exc
        with tempfile.TemporaryDirectory(prefix="catalog-desk-new-") as tmp:
            catalog_path = Path(tmp) / catalog_name
            catalog_path.write_bytes(bytes(catalog_bytes))
            try:
                catalog = self.core.load_catalog(catalog_path)
                translations = self.core.translation_template(catalog, source_locale, target_locale)
            except Exception as exc:
                if isinstance(exc, getattr(self.core, "CatalogError", ())):
                    raise DeskError(str(exc)) from exc
                raise
        workspace = {
            "schema": WORKSPACE_SCHEMA,
            "catalog_name": catalog_name,
            "catalog_b64": base64.b64encode(bytes(catalog_bytes)).decode("ascii"),
            "catalog_sha256": sha256_bytes(bytes(catalog_bytes)),
            "translations": translations,
            "glossary": _json_clone(glossary or self.default_glossary(source_locale, target_locale)),
            "locale_profile": _json_clone(locale_profile or self.default_profile(target_locale)),
            "previous_translations": None,
            "revision_receipts": [],
        }
        return self.validate_workspace(workspace)

    def validate_workspace(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        ws = _strict_object(_json_clone(raw), "workspace")
        expected = {
            "schema", "catalog_name", "catalog_b64", "catalog_sha256", "translations",
            "glossary", "locale_profile", "previous_translations", "revision_receipts",
        }
        if set(ws) != expected:
            extra = sorted(set(ws) - expected)
            missing = sorted(expected - set(ws))
            raise DeskError(f"workspace keys differ; missing={missing} extra={extra}")
        if ws["schema"] != WORKSPACE_SCHEMA:
            raise DeskError(f"workspace schema must be {WORKSPACE_SCHEMA!r}")
        payload = _decode_catalog(ws)
        _safe_catalog_name(ws["catalog_name"])
        if ws["catalog_sha256"] != sha256_bytes(payload):
            raise DeskError("catalog_sha256 does not match embedded catalog bytes")
        if not isinstance(ws["revision_receipts"], list):
            raise DeskError("revision_receipts must be an array")

        with tempfile.TemporaryDirectory(prefix="catalog-desk-validate-") as tmp:
            root = Path(tmp)
            catalog_path = self._write_catalog(root, ws)
            trans_path = root / "translations.json"
            glossary_path = root / "glossary.json"
            profile_path = root / "profile.json"
            trans_path.write_bytes(json.dumps(ws["translations"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
            glossary_path.write_bytes(json.dumps(ws["glossary"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
            profile_path.write_bytes(json.dumps(ws["locale_profile"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
            previous_path = None
            if ws["previous_translations"] is not None:
                previous_path = root / "previous.json"
                previous_path.write_bytes(json.dumps(ws["previous_translations"], ensure_ascii=False, sort_keys=True).encode("utf-8"))
            try:
                catalog = self.core.load_catalog(catalog_path)
                translations = self.core.load_translations(trans_path)
                glossary = self.core.load_glossary(glossary_path)
                profile = self.core.load_profile(profile_path)
                previous = self.core.load_translations(previous_path) if previous_path else None
                self.core.validate_translation_catalog_shape(catalog, translations)
                if previous is not None:
                    self.core.validate_translation_catalog_shape(catalog, previous)
            except Exception as exc:
                if isinstance(exc, getattr(self.core, "CatalogError", ())):
                    raise DeskError(str(exc)) from exc
                raise

        if translations["source_catalog_sha256"] != catalog.canonical_sha256:
            raise DeskError("workspace translations are bound to a different catalog")
        if (translations["source_locale"], translations["target_locale"]) != (glossary[0], glossary[1]):
            raise DeskError("glossary locales do not match workspace locales")
        if profile.locale != translations["target_locale"]:
            raise DeskError("locale profile does not match workspace target locale")

        products = {record["sku"]: record for record in catalog.products}
        if set(translations["products"]) != set(products):
            raise DeskError("workspace translation SKU set differs from catalog")
        for sku, record in products.items():
            entry = translations["products"][sku]
            if entry["source_fingerprint"] != self.core.source_fingerprint(record):
                raise DeskError(f"workspace source fingerprint was changed for {sku}")
            expected_source = {field: record[field] for field in self.fields}
            if entry["source"] != expected_source:
                raise DeskError(f"workspace source snapshot was changed for {sku}")
        return ws

    def apply_edits(self, raw: Mapping[str, Any], edits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        ws = self.validate_workspace(raw)
        if not isinstance(edits, list):
            raise DeskError("edits must be an array")
        products = ws["translations"]["products"]
        seen: set[tuple[str, str]] = set()
        for index, raw_edit in enumerate(edits):
            edit = _strict_object(raw_edit, f"edit {index}")
            if set(edit) != {"sku", "field", "value"}:
                raise DeskError(f"edit {index} must contain exactly sku, field, value")
            sku, field, value = edit["sku"], edit["field"], edit["value"]
            if not isinstance(sku, str) or sku not in products:
                raise DeskError(f"edit {index} has unknown sku")
            if field not in self.fields:
                raise DeskError(f"edit {index}.field is protected or unknown")
            if not isinstance(value, str):
                raise DeskError(f"edit {index}.value must be a string")
            key = (sku, field)
            if key in seen:
                raise DeskError(f"duplicate edit target {sku}.{field}")
            seen.add(key)
            products[sku]["target"][field] = value
        return self.validate_workspace(ws)

    def replace_settings(
        self, raw: Mapping[str, Any], *, glossary: Mapping[str, Any], locale_profile: Mapping[str, Any]
    ) -> dict[str, Any]:
        ws = self.validate_workspace(raw)
        ws["glossary"] = _json_clone(glossary)
        ws["locale_profile"] = _json_clone(locale_profile)
        return self.validate_workspace(ws)

    def revise(
        self, raw: Mapping[str, Any], *, revision_id: str, changes: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        ws = self.validate_workspace(raw)
        patch = {
            "schema": "hive.multilingual-catalog-revision.v1",
            "revision_id": revision_id,
            "target_locale": ws["translations"]["target_locale"],
            "changes": _json_clone(changes),
        }
        with tempfile.TemporaryDirectory(prefix="catalog-desk-revise-") as tmp:
            root = Path(tmp)
            trans_path, patch_path = root / "translations.json", root / "patch.json"
            output_path, receipt_path = root / "revised.json", root / "receipt.json"
            trans_path.write_text(json.dumps(ws["translations"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
            patch_path.write_text(json.dumps(patch, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            try:
                self.core.revise_translations(
                    translations_path=trans_path, patch_path=patch_path,
                    output_path=output_path, receipt_path=receipt_path,
                )
            except Exception as exc:
                if isinstance(exc, getattr(self.core, "CatalogError", ())):
                    raise DeskError(str(exc)) from exc
                raise
            revised = json.loads(output_path.read_text(encoding="utf-8"))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        ws["previous_translations"] = _json_clone(ws["translations"])
        ws["translations"] = revised
        ws["revision_receipts"].append(receipt)
        if len(ws["revision_receipts"]) > 100:
            ws["revision_receipts"] = ws["revision_receipts"][-100:]
        return self.validate_workspace(ws)

    def publish(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        ws = self.validate_workspace(raw)
        with tempfile.TemporaryDirectory(prefix="catalog-desk-publish-") as tmp:
            root = Path(tmp)
            catalog_path = self._write_catalog(root, ws)
            translations_path = root / "translations.json"
            glossary_path = root / "glossary.json"
            profile_path = root / "profile.json"
            output_dir = root / "pack"
            translations_path.write_text(json.dumps(ws["translations"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
            glossary_path.write_text(json.dumps(ws["glossary"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
            profile_path.write_text(json.dumps(ws["locale_profile"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
            previous_path = None
            if ws["previous_translations"] is not None:
                previous_path = root / "previous.json"
                previous_path.write_text(json.dumps(ws["previous_translations"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
            try:
                result = self.core.publish_pack(
                    catalog_path=catalog_path, translations_path=translations_path,
                    glossary_path=glossary_path, profile_path=profile_path,
                    previous_path=previous_path, output_dir=output_dir,
                )
            except Exception as exc:
                if isinstance(exc, getattr(self.core, "CatalogError", ())):
                    raise DeskError(str(exc)) from exc
                raise
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            review_files = sorted(output_dir.glob("review.*.csv"))
            review: list[dict[str, str]] = []
            if review_files:
                with review_files[0].open("r", encoding="utf-8", newline="") as handle:
                    review = list(csv.DictReader(handle))
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
                for path in sorted(p for p in output_dir.iterdir() if p.is_file()):
                    package.writestr(path.name, path.read_bytes())
            payload = archive.getvalue()
        locale = ws["translations"]["target_locale"].replace("/", "_").replace("\\", "_")
        disposition = "STORE-READY" if result["ready"] else "DRAFT-REVIEW-REQUIRED"
        return {
            "status": result["status"],
            "ready": bool(result["ready"]),
            "manifest": manifest,
            "review": review,
            "download_name": f"catalog-pack-{locale}-{disposition}.zip",
            "download_b64": base64.b64encode(payload).decode("ascii"),
            "download_sha256": sha256_bytes(payload),
        }

    def export_workspace(self, raw: Mapping[str, Any]) -> bytes:
        ws = self.validate_workspace(raw)
        return json.dumps(ws, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


class DeskHandler(BaseHTTPRequestHandler):
    desk: CatalogDesk
    server_version = "CatalogDesk/1"

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'")
        self.end_headers()

    def _send(self, status: int, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise DeskError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise DeskError(f"request body must contain 1..{MAX_REQUEST_BYTES} bytes")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise DeskError("Content-Type must be application/json")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeskError(f"invalid JSON: {exc}") from exc
        return _strict_object(value, "request")

    def do_GET(self) -> None:
        if self.path in {"/", "/desk.html"}:
            data = HTML_PATH.read_bytes()
            self._headers(200, "text/html; charset=utf-8", len(data))
            self.wfile.write(data)
            return
        if self.path == "/api/status":
            self._send(200, {"status": "ok", "workspace_schema": WORKSPACE_SCHEMA,
                             "translation_fields": list(self.desk.fields), "network": "loopback-only"})
            return
        self._send(404, {"status": "error", "error": "not found"})

    def do_POST(self) -> None:
        try:
            request = self._body()
            if self.path == "/api/template":
                if "catalog_b64" in request:
                    try:
                        catalog = base64.b64decode(request["catalog_b64"], validate=True)
                    except (ValueError, TypeError) as exc:
                        raise DeskError("catalog_b64 is invalid") from exc
                elif "catalog_text" in request and isinstance(request["catalog_text"], str):
                    catalog = request["catalog_text"].encode("utf-8")
                else:
                    raise DeskError("template request requires catalog_b64 or catalog_text")
                ws = self.desk.new_workspace(
                    catalog_name=request.get("catalog_name"),
                    catalog_bytes=catalog,
                    source_locale=request.get("source_locale"),
                    target_locale=request.get("target_locale"),
                    glossary=request.get("glossary"),
                    locale_profile=request.get("locale_profile"),
                )
                self._send(200, {"status": "workspace_created", "workspace": ws})
            elif self.path == "/api/open":
                ws = self.desk.validate_workspace(request.get("workspace"))
                self._send(200, {"status": "workspace_opened", "workspace": ws})
            elif self.path == "/api/edit":
                ws = self.desk.apply_edits(request.get("workspace"), request.get("edits"))
                self._send(200, {"status": "workspace_updated", "workspace": ws})
            elif self.path == "/api/settings":
                ws = self.desk.replace_settings(
                    request.get("workspace"), glossary=request.get("glossary"),
                    locale_profile=request.get("locale_profile"),
                )
                self._send(200, {"status": "workspace_updated", "workspace": ws})
            elif self.path == "/api/revise":
                ws = self.desk.revise(
                    request.get("workspace"), revision_id=request.get("revision_id"),
                    changes=request.get("changes"),
                )
                self._send(200, {"status": "workspace_revised", "workspace": ws})
            elif self.path == "/api/publish":
                self._send(200, self.desk.publish(request.get("workspace")))
            elif self.path == "/api/export":
                data = self.desk.export_workspace(request.get("workspace"))
                self._send(200, {"status": "workspace_exported",
                                 "workspace_b64": base64.b64encode(data).decode("ascii"),
                                 "sha256": sha256_bytes(data)})
            else:
                self._send(404, {"status": "error", "error": "not found"})
        except DeskError as exc:
            self._send(400, {"status": "error", "error": str(exc)})
        except Exception as exc:  # fail closed without exposing a traceback to the browser.
            self._send(500, {"status": "error", "error": f"internal error: {type(exc).__name__}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[catalog-desk] {self.address_string()} {fmt % args}", file=sys.stderr)


def serve(*, host: str, port: int, bundle_dir: Path) -> None:
    if host not in LOOPBACK_HOSTS:
        raise SystemExit("catalog desk is intentionally loopback-only; use 127.0.0.1, ::1, or localhost")
    desk = CatalogDesk(bundle_dir)
    handler = type("BoundDeskHandler", (DeskHandler,), {"desk": desk})
    server = ThreadingHTTPServer((host, port), handler)
    print(json.dumps({"status": "serving", "host": host, "port": server.server_address[1],
                      "url": f"http://{host}:{server.server_address[1]}/"}, sort_keys=True))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bundle-dir", type=Path, default=PRODUCT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (0 <= args.port <= 65535):
        raise SystemExit("--port must be between 0 and 65535")
    serve(host=args.host, port=args.port, bundle_dir=args.bundle_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
