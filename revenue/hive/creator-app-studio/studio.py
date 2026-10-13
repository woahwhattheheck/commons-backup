#!/usr/bin/env python3
"""Local creator brief studio and dependency-free, standalone planner publisher."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
MAX_BODY = 256 * 1024


class InputError(ValueError):
    pass


class Conflict(InputError):
    pass


def text(value, name, *, limit=2000, required=True):
    if not isinstance(value, str) or len(value) > limit:
        raise InputError(f"{name} must be text of at most {limit} characters")
    value = value.strip()
    if required and not value:
        raise InputError(f"{name} is required")
    return value


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InputError(f"{name} must be a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputError(f"{name} must be a number") from exc
    if not result.is_finite() or not Decimal(str(low)) <= result <= Decimal(str(high)):
        raise InputError(f"{name} must be between {low} and {high}")
    # Six fractional digits are plenty for ordinary supply planning and keep
    # the standalone app's exact integer arithmetic bounded and predictable.
    if result != result.quantize(Decimal("0.000001")):
        raise InputError(f"{name} supports at most six decimal places")
    return format(result.normalize(), "f")


def validate_brief(data):
    if not isinstance(data, dict):
        raise InputError("brief must be an object")
    result = {}
    for key, limit in (("name", 100), ("creator", 100), ("audience", 500),
                       ("problem", 2000), ("onboarding", 3000),
                       ("pricing", 500), ("support", 1000)):
        result[key] = text(data.get(key), key, limit=limit)
    result["demand_evidence"] = text(data.get("demand_evidence", ""),
                                     "demand_evidence", required=False, limit=3000)
    usage = data.get("usage_target", 20)
    if type(usage) is not int or not 1 <= usage <= 10000:
        raise InputError("usage_target must be an integer from 1 to 10000")
    result["usage_target"] = usage
    materials = data.get("materials")
    if not isinstance(materials, list) or not 1 <= len(materials) <= 50:
        raise InputError("materials must contain 1 to 50 rows")
    result["materials"] = []
    for i, row in enumerate(materials, 1):
        if not isinstance(row, dict):
            raise InputError(f"material {i} must be an object")
        basis = row.get("quantity_basis", "per_kit")
        if basis not in ("per_kit", "per_workshop"):
            raise InputError(f"material {i} quantity_basis must be per_kit or per_workshop")
        material = {
            "name": text(row.get("name"), f"material {i} name", limit=100),
            "unit": text(row.get("unit"), f"material {i} unit", limit=40),
            "per_attendee": number(row.get("per_attendee"), "per_attendee", 0, 1000000),
            "pack_size": number(row.get("pack_size"), "pack_size", 0.000001, 1000000),
            "buffer_percent": number(row.get("buffer_percent", "0"), "buffer_percent", 0, 100),
        }
        # Leave older brief bytes normalized as before so create retries keep
        # their saved request identity. Missing basis means per-kit quantities.
        if "quantity_basis" in row:
            material["quantity_basis"] = basis
        result["materials"].append(material)
    return result


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_json(raw):
    def unique_pairs(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise InputError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(InputError("non-finite JSON number")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError("invalid UTF-8 JSON") from exc


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    initial_json TEXT NOT NULL, brief_json TEXT NOT NULL,
                    revision INTEGER NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    brief_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, revision));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def view(row):
        if row is None:
            raise KeyError("project not found")
        return {"id": row["id"], "revision": row["revision"],
                "updated_at": row["updated_at"], "brief": json.loads(row["brief_json"])}

    def list(self):
        with self.connect() as db:
            return [self.view(row) for row in db.execute("SELECT * FROM projects ORDER BY updated_at DESC, id")]

    def get(self, project_id):
        with self.connect() as db:
            return self.view(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def history(self, project_id):
        with self.connect() as db:
            self.view(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
            return [{"revision": r["revision"], "brief": json.loads(r["brief_json"]),
                     "created_at": r["created_at"]} for r in db.execute(
                         "SELECT * FROM revisions WHERE project_id=? ORDER BY revision", (project_id,))]

    def save(self, brief, *, request_id=None, project_id=None, expected_revision=None):
        encoded = canonical(validate_brief(brief))
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if project_id is None:
                key = text(request_id, "request_id", limit=100)
                previous = db.execute("SELECT * FROM projects WHERE request_id=?", (key,)).fetchone()
                if previous:
                    if previous["initial_json"] != encoded:
                        raise Conflict("request_id already belongs to a different brief")
                    return self.view(previous)
                project_id, revision = uuid.uuid4().hex, 1
                db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)",
                           (project_id, key, encoded, encoded, revision, now))
            else:
                previous = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
                self.view(previous)
                if type(expected_revision) is not int or expected_revision != previous["revision"]:
                    raise Conflict("brief changed; reload the current revision before saving")
                revision = previous["revision"] + 1
                db.execute("UPDATE projects SET brief_json=?,revision=?,updated_at=? WHERE id=?",
                           (encoded, revision, now, project_id))
            db.execute("INSERT INTO revisions VALUES(?,?,?,?)", (project_id, revision, encoded, now))
            return self.view(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())


def render_planner(project):
    payload = canonical({"id": project["id"], "revision": project["revision"], **project["brief"]})
    # Script data must never terminate the element. Names/briefs render only
    # through textContent; JSON data stays data even when it contains markup.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return (HERE / "planner.html").read_text(encoding="utf-8").replace("__BRIEF_JSON__", payload)


def build_package(project, history=None):
    brief = project["brief"]
    files = {
        "index.html": render_planner(project).encode("utf-8"),
        "brief.json": (json.dumps(project, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "revisions.json": (json.dumps(history or [], ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "START-HERE.md": ("# " + brief["name"] + "\n\nOpen index.html in a modern browser. No server, account, dependency, "
            "external model or payment connection is required.\n\n" + brief["onboarding"] +
            "\n\n## Pricing copy (operator-proposed, not a checkout)\n" + brief["pricing"] +
            "\n\n## Support route (operator-provided)\n" + brief["support"] +
            "\n\n## Local data\nPlans save in this browser for this project ID. Moving the file or clearing browser "
            "storage may remove access to saved plans. Export JSON backups before moving; import restores them. "
            "Storage unavailability is shown explicitly and never reported as a successful save.\n\n"
            "Usage targets are advisory, not paid-plan enforcement. No billing or identity system is present. "
            "Choose Per kit to multiply a material by attendee, demonstration and spare kits. "
            "Choose Once per workshop for a fixed shared-supply quantity. Reserve applies in both modes. "
            "Material quantities do not convert between different units. Pack counts round upward.\n\n"
            "## Audience discovery\nThe studio does not independently verify demand evidence, partnership, sales, "
            "or customer fulfillment. The supplied example is synthetic. Replace the brief with an actual "
            "creator's agreed workflow and confirm their audience need before making commercial claims.\n").encode("utf-8"),
        "launch-copy.txt": (brief["name"] + "\nFor: " + brief["audience"] + "\nWorkflow: " + brief["problem"] +
            "\nOffer: " + brief["pricing"] + "\nSupport: " + brief["support"] +
            "\n\nDraft launch copy; no publication, partnership or sale is implied.\n").encode("utf-8"),
    }
    files["SHA256SUMS"] = "".join(f"{hashlib.sha256(content).hexdigest()}  {name}\n"
                                   for name, content in sorted(files.items())).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def make_server(store, host="127.0.0.1", port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def reply(self, status, body, kind="application/json; charset=utf-8", filename=None):
            if kind.startswith("application/json"):
                body = canonical(body).encode("utf-8")
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self):
            path = urlsplit(self.path).path
            try:
                if self.command == "GET":
                    if path == "/":
                        return self.reply(200, (HERE / "studio.html").read_bytes(), "text/html; charset=utf-8")
                    if path == "/api/example":
                        return self.reply(200, json.loads((HERE / "example.json").read_text(encoding="utf-8")))
                    if path == "/api/projects":
                        return self.reply(200, {"projects": store.list()})
                    match = re.fullmatch(r"/api/projects/([0-9a-f]{32})(/history|/export.zip|/preview)?", path)
                    if not match:
                        return self.reply(404, {"error": "not found"})
                    project_id, suffix = match.groups()
                    project = store.get(project_id)
                    if suffix == "/history":
                        return self.reply(200, {"revisions": store.history(project_id)})
                    if suffix == "/export.zip":
                        return self.reply(200, build_package(project, store.history(project_id)),
                                          "application/zip", "creator-app.zip")
                    if suffix == "/preview":
                        return self.reply(200, render_planner(project), "text/html; charset=utf-8")
                    return self.reply(200, project)
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    return self.reply(415, {"error": "use application/json"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise InputError("invalid Content-Length")
                if not 0 < size <= MAX_BODY:
                    return self.reply(413, {"error": "request must be between 1 and 262144 bytes"})
                data = decode_json(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise InputError("request must be an object")
                if self.command == "POST" and path == "/api/projects":
                    return self.reply(201, store.save(data.get("brief"), request_id=data.get("request_id")))
                match = re.fullmatch(r"/api/projects/([0-9a-f]{32})", path)
                if self.command == "PUT" and match:
                    return self.reply(200, store.save(data.get("brief"), project_id=match[1],
                                                      expected_revision=data.get("expected_revision")))
                return self.reply(404, {"error": "not found"})
            except Conflict as exc:
                self.reply(409, {"error": str(exc)})
            except InputError as exc:
                self.reply(400, {"error": str(exc)})
            except KeyError:
                self.reply(404, {"error": "project not found"})
            except sqlite3.Error:
                self.reply(503, {"error": "database unavailable; retry without changing request_id"})

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("creator-studio.sqlite3"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(Store(args.db), port=args.port)
    print(f"Creator App Studio: http://127.0.0.1:{server.server_port} (local, no accounts)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
