from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import re
import sqlite3
import threading
from contextlib import closing
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_TEXT = 4000
MAX_INGREDIENTS = 80
MAX_INGREDIENT_LEN = 120
MAX_RECIPES = 500
DELETE_CONFIRMATION = "DELETE ALL MEALFRAME DATA"
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_date TEXT NOT NULL,
    title TEXT NOT NULL,
    portion_note TEXT NOT NULL,
    notes TEXT NOT NULL,
    photo_mime TEXT,
    photo_bytes BLOB,
    photo_sha256 TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meal_ingredients (
    meal_id INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    ingredient TEXT NOT NULL,
    PRIMARY KEY (meal_id, position)
);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    notes TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    ingredient TEXT NOT NULL,
    PRIMARY KEY (recipe_id, position)
);
CREATE TABLE IF NOT EXISTS operation_receipts (
    operation_id TEXT PRIMARY KEY,
    payload_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

class JournalError(ValueError):
    pass

class ConflictError(JournalError):
    pass

class NotFoundError(JournalError):
    pass

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JournalError(f"value is not canonical JSON: {exc}") from exc

def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def _text(value: Any, name: str, *, max_len: int = MAX_TEXT, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise JournalError(f"{name} must be text")
    value = value.strip()
    if not allow_empty and not value:
        raise JournalError(f"{name} must not be empty")
    if len(value) > max_len:
        raise JournalError(f"{name} exceeds {max_len} characters")
    return value

def _token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not TOKEN_RE.fullmatch(value):
        raise JournalError(f"{name} must match {TOKEN_RE.pattern}")
    return value

def _date(value: Any, name: str = "date") -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise JournalError(f"{name} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise JournalError(f"{name} is not a valid calendar date") from exc
    return value

def _ingredients(value: Any, name: str = "ingredients") -> List[str]:
    if not isinstance(value, list) or len(value) > MAX_INGREDIENTS:
        raise JournalError(f"{name} must be a list with <= {MAX_INGREDIENTS} entries")
    out: List[str] = []
    seen = set()
    for item in value:
        ingredient = _text(item, name, max_len=MAX_INGREDIENT_LEN, allow_empty=False)
        key = ingredient.casefold()
        if key in seen:
            raise JournalError(f"{name} contains duplicate ingredient: {ingredient}")
        seen.add(key)
        out.append(ingredient)
    return out

def _photo(photo: Optional[bytes], mime: Optional[str]) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    if photo is None:
        if mime not in (None, ""):
            raise JournalError("photo mime supplied without photo bytes")
        return None, None, None
    if not isinstance(photo, (bytes, bytearray)):
        raise JournalError("photo must be bytes")
    photo = bytes(photo)
    if not photo:
        raise JournalError("photo must not be empty")
    if len(photo) > MAX_PHOTO_BYTES:
        raise JournalError(f"photo exceeds {MAX_PHOTO_BYTES} bytes")
    if not isinstance(mime, str) or mime not in ALLOWED_MIME:
        raise JournalError("unsupported photo mime type")
    return photo, mime, hashlib.sha256(photo).hexdigest()

class MealJournal:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _initialize(self) -> None:
        with self._init_lock:
            with closing(self._connect()) as conn:
                conn.executescript(SCHEMA)

    def _mutate(self, operation_id: str, payload: Mapping[str, Any], callback):
        operation_id = _token(operation_id, "operation_id")
        payload_hash = _hash_payload(payload)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            receipt = conn.execute(
                "SELECT payload_sha256, result_json FROM operation_receipts WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if receipt:
                if receipt["payload_sha256"] != payload_hash:
                    raise ConflictError("operation_id was already used with a different payload")
                result = json.loads(receipt["result_json"])
                conn.commit()
                return result
            result = callback(conn)
            result_json = _canonical(result).decode("utf-8")
            conn.execute(
                "INSERT INTO operation_receipts(operation_id,payload_sha256,result_json,created_at) VALUES(?,?,?,?)",
                (operation_id, payload_hash, result_json, _utc_now()),
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_meal(
        self,
        *,
        operation_id: str,
        meal_date: str,
        title: str,
        portion_note: str,
        notes: str,
        ingredients: Any,
        photo: Optional[bytes] = None,
        photo_mime: Optional[str] = None,
    ) -> Dict[str, Any]:
        meal_date = _date(meal_date, "meal_date")
        title = _text(title, "title", max_len=200, allow_empty=False)
        portion_note = _text(portion_note, "portion_note", max_len=500)
        notes = _text(notes, "notes")
        ingredients = _ingredients(ingredients)
        photo, photo_mime, photo_sha = _photo(photo, photo_mime)
        payload = {
            "action": "create_meal", "meal_date": meal_date, "title": title,
            "portion_note": portion_note, "notes": notes, "ingredients": ingredients,
            "photo_sha256": photo_sha, "photo_mime": photo_mime,
        }
        def work(conn):
            now = _utc_now()
            cur = conn.execute(
                """INSERT INTO meals(meal_date,title,portion_note,notes,photo_mime,photo_bytes,photo_sha256,version,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,1,?,?)""",
                (meal_date, title, portion_note, notes, photo_mime, photo, photo_sha, now, now),
            )
            meal_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO meal_ingredients(meal_id,position,ingredient) VALUES(?,?,?)",
                [(meal_id, i, ingredient) for i, ingredient in enumerate(ingredients)],
            )
            return {"meal_id": meal_id, "version": 1, "photo_sha256": photo_sha}
        return self._mutate(operation_id, payload, work)

    def update_meal(
        self,
        *,
        operation_id: str,
        meal_id: int,
        expected_version: int,
        meal_date: str,
        title: str,
        portion_note: str,
        notes: str,
        ingredients: Any,
    ) -> Dict[str, Any]:
        if type(meal_id) is not int or meal_id < 1:
            raise JournalError("meal_id must be a positive integer")
        if type(expected_version) is not int or expected_version < 1:
            raise JournalError("expected_version must be a positive integer")
        meal_date = _date(meal_date, "meal_date")
        title = _text(title, "title", max_len=200, allow_empty=False)
        portion_note = _text(portion_note, "portion_note", max_len=500)
        notes = _text(notes, "notes")
        ingredients = _ingredients(ingredients)
        payload = {
            "action": "update_meal", "meal_id": meal_id, "expected_version": expected_version,
            "meal_date": meal_date, "title": title, "portion_note": portion_note,
            "notes": notes, "ingredients": ingredients,
        }
        def work(conn):
            row = conn.execute("SELECT version FROM meals WHERE id=?", (meal_id,)).fetchone()
            if not row:
                raise NotFoundError("meal not found")
            if row["version"] != expected_version:
                raise ConflictError("stale meal version")
            next_version = expected_version + 1
            conn.execute(
                "UPDATE meals SET meal_date=?,title=?,portion_note=?,notes=?,version=?,updated_at=? WHERE id=?",
                (meal_date, title, portion_note, notes, next_version, _utc_now(), meal_id),
            )
            conn.execute("DELETE FROM meal_ingredients WHERE meal_id=?", (meal_id,))
            conn.executemany(
                "INSERT INTO meal_ingredients(meal_id,position,ingredient) VALUES(?,?,?)",
                [(meal_id, i, ingredient) for i, ingredient in enumerate(ingredients)],
            )
            return {"meal_id": meal_id, "version": next_version}
        return self._mutate(operation_id, payload, work)

    def save_recipe(
        self,
        *,
        operation_id: str,
        name: str,
        ingredients: Any,
        notes: str = "",
        recipe_id: Optional[int] = None,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        name = _text(name, "name", max_len=200, allow_empty=False)
        ingredients = _ingredients(ingredients)
        notes = _text(notes, "notes")
        if recipe_id is not None and (type(recipe_id) is not int or recipe_id < 1):
            raise JournalError("recipe_id must be a positive integer")
        if recipe_id is not None and (type(expected_version) is not int or expected_version < 1):
            raise JournalError("expected_version is required when updating a recipe")
        payload = {
            "action": "save_recipe", "name": name, "ingredients": ingredients, "notes": notes,
            "recipe_id": recipe_id, "expected_version": expected_version,
        }
        def work(conn):
            if recipe_id is None:
                count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
                if count >= MAX_RECIPES:
                    raise JournalError(f"recipe limit {MAX_RECIPES} reached")
                now = _utc_now()
                cur = conn.execute(
                    "INSERT INTO recipes(name,notes,version,created_at,updated_at) VALUES(?,?,1,?,?)",
                    (name, notes, now, now),
                )
                rid, version = cur.lastrowid, 1
            else:
                row = conn.execute("SELECT version FROM recipes WHERE id=?", (recipe_id,)).fetchone()
                if not row:
                    raise NotFoundError("recipe not found")
                if row["version"] != expected_version:
                    raise ConflictError("stale recipe version")
                rid, version = recipe_id, expected_version + 1
                conn.execute(
                    "UPDATE recipes SET name=?,notes=?,version=?,updated_at=? WHERE id=?",
                    (name, notes, version, _utc_now(), rid),
                )
                conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (rid,))
            conn.executemany(
                "INSERT INTO recipe_ingredients(recipe_id,position,ingredient) VALUES(?,?,?)",
                [(rid, i, ingredient) for i, ingredient in enumerate(ingredients)],
            )
            return {"recipe_id": rid, "version": version}
        return self._mutate(operation_id, payload, work)

    def delete_meal(self, *, operation_id: str, meal_id: int, expected_version: int) -> Dict[str, Any]:
        if type(meal_id) is not int or meal_id < 1:
            raise JournalError("meal_id must be a positive integer")
        if type(expected_version) is not int or expected_version < 1:
            raise JournalError("expected_version must be a positive integer")
        payload = {"action": "delete_meal", "meal_id": meal_id, "expected_version": expected_version}
        def work(conn):
            row = conn.execute("SELECT version,photo_sha256 FROM meals WHERE id=?", (meal_id,)).fetchone()
            if not row:
                raise NotFoundError("meal not found")
            if row["version"] != expected_version:
                raise ConflictError("stale meal version")
            conn.execute("DELETE FROM meals WHERE id=?", (meal_id,))
            return {"deleted_meal_id": meal_id, "deleted_photo_sha256": row["photo_sha256"]}
        return self._mutate(operation_id, payload, work)

    def delete_all(self, *, operation_id: str, confirmation: str) -> Dict[str, Any]:
        confirmation = _text(confirmation, "confirmation", max_len=100, allow_empty=False)
        if confirmation != DELETE_CONFIRMATION:
            raise JournalError("delete-all confirmation text does not match")
        payload = {"action": "delete_all", "confirmation": confirmation}
        def work(conn):
            meals = conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]
            recipes = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            photos = conn.execute("SELECT COUNT(*) FROM meals WHERE photo_bytes IS NOT NULL").fetchone()[0]
            conn.execute("DELETE FROM meals")
            conn.execute("DELETE FROM recipes")
            return {"deleted_meals": meals, "deleted_recipes": recipes, "deleted_photos": photos}
        return self._mutate(operation_id, payload, work)

    def _ingredients_for(self, conn: sqlite3.Connection, table: str, id_column: str, value: int) -> List[str]:
        return [
            row["ingredient"] for row in conn.execute(
                f"SELECT ingredient FROM {table} WHERE {id_column}=? ORDER BY position",
                (value,),
            )
        ]

    def state(self) -> Dict[str, Any]:
        with closing(self._connect()) as conn:
            meals = []
            for row in conn.execute(
                "SELECT id,meal_date,title,portion_note,notes,photo_mime,photo_sha256,version,created_at,updated_at FROM meals ORDER BY meal_date DESC,id DESC"
            ):
                item = dict(row)
                item["ingredients"] = self._ingredients_for(conn, "meal_ingredients", "meal_id", row["id"])
                item["photo_url"] = f"/photo/{row['id']}" if row["photo_sha256"] else None
                meals.append(item)
            recipes = []
            for row in conn.execute("SELECT id,name,notes,version,created_at,updated_at FROM recipes ORDER BY name COLLATE NOCASE,id"):
                item = dict(row)
                item["ingredients"] = self._ingredients_for(conn, "recipe_ingredients", "recipe_id", row["id"])
                recipes.append(item)
            return {
                "schema_version": 1,
                "product": "MealFrame",
                "privacy": "local_instance_only",
                "nutrition_inference": False,
                "photo_recognition": False,
                "meals": meals,
                "recipes": recipes,
            }

    def suggestions(self, title: str = "", *, limit: int = 12) -> List[Dict[str, str]]:
        title = _text(title, "title", max_len=200)
        if type(limit) is not int or not 1 <= limit <= 30:
            raise JournalError("limit must be an integer from 1 to 30")
        tokens = {t for t in re.findall(r"[a-z0-9]+", title.casefold()) if len(t) >= 2}
        counter: Counter[str] = Counter()
        display: Dict[str, str] = {}
        sources: Dict[str, set[str]] = {}
        with closing(self._connect()) as conn:
            recipes = conn.execute("SELECT id,name FROM recipes").fetchall()
            for recipe in recipes:
                name_tokens = set(re.findall(r"[a-z0-9]+", recipe["name"].casefold()))
                if tokens and not (tokens & name_tokens):
                    continue
                for ingredient in self._ingredients_for(conn, "recipe_ingredients", "recipe_id", recipe["id"]):
                    key = ingredient.casefold()
                    counter[key] += 3
                    display.setdefault(key, ingredient)
                    sources.setdefault(key, set()).add("recipe")
            for row in conn.execute(
                """SELECT mi.ingredient FROM meal_ingredients mi
                   JOIN meals m ON m.id=mi.meal_id
                   ORDER BY m.meal_date DESC,m.id DESC LIMIT 400"""
            ):
                ingredient = row["ingredient"]
                key = ingredient.casefold()
                counter[key] += 1
                display.setdefault(key, ingredient)
                sources.setdefault(key, set()).add("history")
        ranked = sorted(counter, key=lambda k: (-counter[k], display[k].casefold()))
        return [
            {
                "ingredient": display[key],
                "source": "+".join(sorted(sources[key])),
                "basis": "saved recipe/history only; not inferred from photo",
            }
            for key in ranked[:limit]
        ]

    def photo(self, meal_id: int) -> Tuple[bytes, str, str]:
        if type(meal_id) is not int or meal_id < 1:
            raise JournalError("meal_id must be a positive integer")
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT photo_bytes,photo_mime,photo_sha256 FROM meals WHERE id=?", (meal_id,)
            ).fetchone()
            if not row or row["photo_bytes"] is None:
                raise NotFoundError("photo not found")
            return bytes(row["photo_bytes"]), row["photo_mime"], row["photo_sha256"]

    def _week_bounds(self, week_start: str) -> Tuple[str, str]:
        start_text = _date(week_start, "week_start")
        start = date.fromisoformat(start_text)
        if start.weekday() != 0:
            raise JournalError("week_start must be a Monday")
        end = start + timedelta(days=7)
        return start.isoformat(), end.isoformat()

    def week_data(self, week_start: str) -> Dict[str, Any]:
        start, end = self._week_bounds(week_start)
        state = self.state()
        meals = [m for m in state["meals"] if start <= m["meal_date"] < end]
        for meal in meals:
            meal.pop("photo_url", None)
            meal["photo_included"] = bool(meal.get("photo_sha256"))
        return {
            "product": "MealFrame",
            "week_start": start,
            "week_end_exclusive": end,
            "nutrition_estimates_included": False,
            "photo_recognition_used": False,
            "meals": meals,
        }

    def export_week_json(self, week_start: str) -> bytes:
        return json.dumps(self.week_data(week_start), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"

    def export_week_html(self, week_start: str) -> bytes:
        data = self.week_data(week_start)
        parts = [
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>MealFrame weekly journal</title>",
            "<style>body{font-family:system-ui;max-width:760px;margin:2rem auto;padding:0 1rem}article{border-top:1px solid #aaa;padding:1rem 0}.muted{color:#555}</style>",
            "</head><body>",
            f"<h1>MealFrame weekly journal</h1><p>{html.escape(data['week_start'])} through the following Sunday</p>",
            "<p class=\"muted\">Ingredient entries and portions are user-edited journal notes. No nutrition, calorie, medical, or image-recognition inference is included.</p>",
        ]
        for meal in data["meals"]:
            parts.append(f"<article><h2>{html.escape(meal['meal_date'])} — {html.escape(meal['title'])}</h2>")
            if meal["ingredients"]:
                parts.append("<p><strong>Ingredients:</strong> " + ", ".join(html.escape(x) for x in meal["ingredients"]) + "</p>")
            if meal["portion_note"]:
                parts.append("<p><strong>Portion note:</strong> " + html.escape(meal["portion_note"]) + "</p>")
            if meal["notes"]:
                parts.append("<p>" + html.escape(meal["notes"]) + "</p>")
            if meal["photo_included"]:
                parts.append("<p class=\"muted\">A local photo is attached to the source journal entry; photo bytes are not embedded in this printable export.</p>")
            parts.append("</article>")
        if not data["meals"]:
            parts.append("<p>No meals recorded for this week.</p>")
        parts.append("</body></html>")
        return "".join(parts).encode("utf-8")
