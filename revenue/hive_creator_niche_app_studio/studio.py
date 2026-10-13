from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "creator-niche-app-studio/v1"
WORKFLOW_KIND = "attendance_supply_planner/v1"
MAX_CLASSES = 64
MAX_ITEMS = 256
MAX_TEXT = 240
MAX_QTY = 1_000_000
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ITEM_MODES = {
    "per_attendee_consumable",
    "per_class_shared",
    "program_shared",
}


class StudioError(ValueError):
    pass


def _require_builtin_int(value: Any, field: str, *, low: int = 0, high: int = MAX_QTY) -> int:
    if type(value) is not int or not low <= value <= high:
        raise StudioError(f"{field} must be an integer in [{low}, {high}]")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise StudioError(f"{field} must be a string")
    if "\x00" in value or any(ord(c) < 32 and c not in "\t\n\r" for c in value):
        raise StudioError(f"{field} contains control characters")
    value = value.strip()
    if not allow_empty and not value:
        raise StudioError(f"{field} must not be empty")
    if len(value) > max_len:
        raise StudioError(f"{field} exceeds {max_len} characters")
    return value


def _id(value: Any, field: str) -> str:
    value = _text(value, field, max_len=64).lower()
    if not SAFE_ID.fullmatch(value):
        raise StudioError(f"{field} is not a safe id")
    return value


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise StudioError(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def strict_json_loads(raw: bytes) -> Any:
    if len(raw) > 512_000:
        raise StudioError("JSON input too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StudioError("input must be UTF-8") from exc

    def bad_constant(token: str) -> None:
        raise StudioError(f"non-finite JSON number: {token}")

    try:
        return json.loads(text, object_pairs_hook=_strict_object_pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise StudioError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CreatorConfig:
    creator_id: str
    app_id: str
    app_name: str
    creator_label: str
    audience_label: str
    promise: str
    support_route: str
    mvp_sprint_price_cents: int
    limits: Mapping[str, int]

    @classmethod
    def from_obj(cls, obj: Any) -> "CreatorConfig":
        if type(obj) is not dict:
            raise StudioError("creator config must be an object")
        required = {
            "schema_version",
            "creator_id",
            "app_id",
            "app_name",
            "creator_label",
            "audience_label",
            "promise",
            "support_route",
            "mvp_sprint_price_cents",
            "workflow",
            "limits",
        }
        unknown = set(obj) - required
        missing = required - set(obj)
        if unknown or missing:
            raise StudioError(f"creator config keys mismatch missing={sorted(missing)} unknown={sorted(unknown)}")
        if obj["schema_version"] != SCHEMA_VERSION:
            raise StudioError("unsupported schema_version")
        if obj["workflow"] != WORKFLOW_KIND:
            raise StudioError("unsupported workflow")
        limits = obj["limits"]
        if type(limits) is not dict or set(limits) != {"max_classes", "max_items", "max_saved_plans"}:
            raise StudioError("limits must define max_classes, max_items, max_saved_plans")
        norm_limits = {
            "max_classes": _require_builtin_int(limits["max_classes"], "max_classes", low=1, high=MAX_CLASSES),
            "max_items": _require_builtin_int(limits["max_items"], "max_items", low=1, high=MAX_ITEMS),
            "max_saved_plans": _require_builtin_int(limits["max_saved_plans"], "max_saved_plans", low=1, high=512),
        }
        return cls(
            creator_id=_id(obj["creator_id"], "creator_id"),
            app_id=_id(obj["app_id"], "app_id"),
            app_name=_text(obj["app_name"], "app_name", max_len=80),
            creator_label=_text(obj["creator_label"], "creator_label", max_len=80),
            audience_label=_text(obj["audience_label"], "audience_label", max_len=120),
            promise=_text(obj["promise"], "promise", max_len=220),
            support_route=_text(obj["support_route"], "support_route", max_len=160),
            mvp_sprint_price_cents=_require_builtin_int(obj["mvp_sprint_price_cents"], "mvp_sprint_price_cents", low=1, high=50_000_000),
            limits=norm_limits,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "creator_id": self.creator_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "creator_label": self.creator_label,
            "audience_label": self.audience_label,
            "promise": self.promise,
            "support_route": self.support_route,
            "mvp_sprint_price_cents": self.mvp_sprint_price_cents,
            "workflow": WORKFLOW_KIND,
            "limits": dict(self.limits),
        }


def load_config(path: str | os.PathLike[str]) -> tuple[CreatorConfig, str]:
    p = Path(path)
    st = p.stat(follow_symlinks=False)
    if not p.is_file() or p.is_symlink():
        raise StudioError("config must be a regular non-symlink file")
    if st.st_size > 512_000:
        raise StudioError("config too large")
    raw = p.read_bytes()
    obj = strict_json_loads(raw)
    cfg = CreatorConfig.from_obj(obj)
    canonical = canonical_json_bytes(cfg.public_dict())
    return cfg, sha256_bytes(canonical)


class StudioStore:
    def __init__(self, db_path: str | os.PathLike[str], config: CreatorConfig, config_sha256: str):
        self.path = str(db_path)
        self.config = config
        self.config_sha256 = config_sha256
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=10.0, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._bind_config()

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS classes(
              class_id TEXT PRIMARY KEY,
              label TEXT NOT NULL,
              rostered INTEGER NOT NULL,
              expected INTEGER NOT NULL,
              notes TEXT NOT NULL DEFAULT '',
              revision INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS items(
              item_id TEXT PRIMARY KEY,
              label TEXT NOT NULL,
              mode TEXT NOT NULL,
              units_per_attendee INTEGER NOT NULL DEFAULT 0,
              units_per_class INTEGER NOT NULL DEFAULT 0,
              program_units INTEGER NOT NULL DEFAULT 0,
              package_size INTEGER NOT NULL DEFAULT 1,
              notes TEXT NOT NULL DEFAULT '',
              revision INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS saved_plans(
              plan_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              input_sha256 TEXT NOT NULL,
              output_sha256 TEXT NOT NULL,
              json_bytes BLOB NOT NULL
            );
            """
        )

    def _bind_config(self) -> None:
        row = self.db.execute("SELECT value FROM meta WHERE key='config_sha256'").fetchone()
        if row is None:
            self.db.execute("INSERT INTO meta(key,value) VALUES('config_sha256',?)", (self.config_sha256,))
            self.db.execute("INSERT INTO meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))
        elif row["value"] != self.config_sha256:
            raise StudioError("workspace is bound to a different creator configuration")

    def _count(self, table: str) -> int:
        with self._lock:
            return int(self.db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

    def upsert_class(self, class_id: str, label: str, rostered: int, expected: int, notes: str = "") -> None:
        class_id = _id(class_id, "class_id")
        label = _text(label, "class label", max_len=100)
        rostered = _require_builtin_int(rostered, "rostered", low=0, high=10_000)
        expected = _require_builtin_int(expected, "expected", low=0, high=10_000)
        notes = _text(notes, "class notes", allow_empty=True, max_len=500)
        if expected > rostered:
            raise StudioError("expected attendance cannot exceed rostered attendance")
        with self._lock:
            exists = self.db.execute("SELECT 1 FROM classes WHERE class_id=?", (class_id,)).fetchone()
            if exists is None and self._count("classes") >= self.config.limits["max_classes"]:
                raise StudioError("class limit reached")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    """INSERT INTO classes(class_id,label,rostered,expected,notes)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(class_id) DO UPDATE SET
                         label=excluded.label, rostered=excluded.rostered,
                         expected=excluded.expected, notes=excluded.notes,
                         revision=classes.revision+1""",
                    (class_id, label, rostered, expected, notes),
                )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def delete_class(self, class_id: str) -> None:
        class_id = _id(class_id, "class_id")
        with self._lock:
            self.db.execute("DELETE FROM classes WHERE class_id=?", (class_id,))

    def upsert_item(
        self,
        item_id: str,
        label: str,
        mode: str,
        *,
        units_per_attendee: int = 0,
        units_per_class: int = 0,
        program_units: int = 0,
        package_size: int = 1,
        notes: str = "",
    ) -> None:
        item_id = _id(item_id, "item_id")
        label = _text(label, "item label", max_len=100)
        mode = _text(mode, "mode", max_len=40)
        if mode not in ITEM_MODES:
            raise StudioError("unsupported item mode")
        units_per_attendee = _require_builtin_int(units_per_attendee, "units_per_attendee")
        units_per_class = _require_builtin_int(units_per_class, "units_per_class")
        program_units = _require_builtin_int(program_units, "program_units")
        package_size = _require_builtin_int(package_size, "package_size", low=1, high=MAX_QTY)
        notes = _text(notes, "item notes", allow_empty=True, max_len=500)
        if mode == "per_attendee_consumable" and units_per_attendee <= 0:
            raise StudioError("per-attendee items require units_per_attendee > 0")
        if mode == "per_class_shared" and units_per_class <= 0:
            raise StudioError("per-class items require units_per_class > 0")
        if mode == "program_shared" and program_units <= 0:
            raise StudioError("program-shared items require program_units > 0")
        with self._lock:
            exists = self.db.execute("SELECT 1 FROM items WHERE item_id=?", (item_id,)).fetchone()
            if exists is None and self._count("items") >= self.config.limits["max_items"]:
                raise StudioError("item limit reached")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    """INSERT INTO items(item_id,label,mode,units_per_attendee,units_per_class,program_units,package_size,notes)
                       VALUES(?,?,?,?,?,?,?,?)
                       ON CONFLICT(item_id) DO UPDATE SET label=excluded.label, mode=excluded.mode,
                         units_per_attendee=excluded.units_per_attendee, units_per_class=excluded.units_per_class,
                         program_units=excluded.program_units, package_size=excluded.package_size, notes=excluded.notes,
                         revision=items.revision+1""",
                    (item_id, label, mode, units_per_attendee, units_per_class, program_units, package_size, notes),
                )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def delete_item(self, item_id: str) -> None:
        item_id = _id(item_id, "item_id")
        with self._lock:
            self.db.execute("DELETE FROM items WHERE item_id=?", (item_id,))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            classes = [dict(r) for r in self.db.execute("SELECT * FROM classes ORDER BY class_id")]
            items = [dict(r) for r in self.db.execute("SELECT * FROM items ORDER BY item_id")]
        return {
            "schema_version": SCHEMA_VERSION,
            "workflow": WORKFLOW_KIND,
            "config_sha256": self.config_sha256,
            "classes": classes,
            "items": items,
        }

    @staticmethod
    def _ceil_div(n: int, d: int) -> int:
        return (n + d - 1) // d

    def compute_plan(self) -> dict[str, Any]:
        snap = self.snapshot()
        classes = snap["classes"]
        items = snap["items"]
        if not classes:
            raise StudioError("add at least one class before computing a plan")
        if not items:
            raise StudioError("add at least one supply item before computing a plan")
        expected_total = sum(int(c["expected"]) for c in classes)
        rostered_total = sum(int(c["rostered"]) for c in classes)
        rows: list[dict[str, Any]] = []
        for item in items:
            mode = item["mode"]
            if mode == "per_attendee_consumable":
                units = expected_total * int(item["units_per_attendee"])
                basis = f"expected_attendance:{expected_total}"
            elif mode == "per_class_shared":
                units = len(classes) * int(item["units_per_class"])
                basis = f"classes:{len(classes)}"
            else:
                units = int(item["program_units"])
                basis = "program_fixed"
            package_size = int(item["package_size"])
            packages = self._ceil_div(units, package_size)
            rows.append(
                {
                    "item_id": item["item_id"],
                    "label": item["label"],
                    "mode": mode,
                    "needed_units": units,
                    "package_size": package_size,
                    "packages_to_prepare": packages,
                    "basis": basis,
                    "notes": item["notes"],
                }
            )
        input_sha = sha256_bytes(canonical_json_bytes(snap))
        result = {
            "schema_version": SCHEMA_VERSION,
            "workflow": WORKFLOW_KIND,
            "config_sha256": self.config_sha256,
            "input_sha256": input_sha,
            "summary": {
                "class_count": len(classes),
                "rostered_total": rostered_total,
                "expected_total": expected_total,
                "attendance_gap": rostered_total - expected_total,
                "item_count": len(items),
            },
            "classes": [
                {
                    "class_id": c["class_id"],
                    "label": c["label"],
                    "rostered": c["rostered"],
                    "expected": c["expected"],
                    "notes": c["notes"],
                }
                for c in classes
            ],
            "supply_plan": rows,
            "authority_note": "Planning aid only. Quantities come from creator/user inputs; shared tools are never multiplied by attendees.",
        }
        result["output_sha256"] = sha256_bytes(canonical_json_bytes(result))
        return result

    def save_plan(self, plan_id: str, now: str | None = None) -> dict[str, Any]:
        plan_id = _id(plan_id, "plan_id")
        with self._lock:
            plan = self.compute_plan()
            exists = self.db.execute("SELECT 1 FROM saved_plans WHERE plan_id=?", (plan_id,)).fetchone()
            if exists is not None:
                prior = self.db.execute("SELECT json_bytes FROM saved_plans WHERE plan_id=?", (plan_id,)).fetchone()["json_bytes"]
                if bytes(prior) != canonical_json_bytes(plan):
                    raise StudioError("plan_id already exists with different content")
                return plan
            if self._count("saved_plans") >= self.config.limits["max_saved_plans"]:
                raise StudioError("saved plan limit reached")
            created_at = now or utc_now()
            raw = canonical_json_bytes(plan)
            self.db.execute(
                "INSERT INTO saved_plans(plan_id,created_at,input_sha256,output_sha256,json_bytes) VALUES(?,?,?,?,?)",
                (plan_id, created_at, plan["input_sha256"], plan["output_sha256"], raw),
            )
            return plan

    def export_csv(self, plan: Mapping[str, Any]) -> bytes:
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["item_id", "label", "mode", "needed_units", "package_size", "packages_to_prepare", "basis", "notes"])
        for row in plan["supply_plan"]:
            safe = []
            for value in [row["item_id"], row["label"], row["mode"], row["needed_units"], row["package_size"], row["packages_to_prepare"], row["basis"], row["notes"]]:
                text = str(value)
                if text[:1] in {"=", "+", "-", "@"}:
                    text = "'" + text
                safe.append(text)
            writer.writerow(safe)
        return out.getvalue().encode("utf-8")

    def create_support_packet(self, topic: str, details: str) -> bytes:
        topic = _text(topic, "support topic", max_len=120)
        details = _text(details, "support details", max_len=1200)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "app_id": self.config.app_id,
            "config_sha256": self.config_sha256,
            "support_route": self.config.support_route,
            "topic": topic,
            "details": details,
            "snapshot_sha256": sha256_bytes(canonical_json_bytes(self.snapshot())),
            "send_authority": False,
            "note": "This packet is for the user to review and send through the configured support route; the app sends nothing automatically.",
        }
        return canonical_json_bytes(payload)


def write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    if p.exists() or p.is_symlink():
        raise StudioError(f"refusing to overwrite {p}")
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".creator-app-", dir=str(parent))
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp_path, p)
    except FileExistsError as exc:
        raise StudioError(f"refusing to overwrite {p}") from exc
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
