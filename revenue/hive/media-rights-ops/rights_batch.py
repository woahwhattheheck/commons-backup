"""Read-only CSV review of placement intents against one grant snapshot."""
from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

from rights_model import MAX_INPUT_BYTES, RightsError, normalize_intent, require
from rights_store import _evaluate

COLUMNS = ("asset_id", "channel", "territory", "starts_at", "ends_at")
MAX_BATCH_ROWS = 500


def _readonly(path):
    target = Path(path)
    require(target.is_file() and not target.is_symlink(), "desk database must be a regular file")
    con = sqlite3.connect(f"file:{target.resolve()}?mode=ro", uri=True, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def review_csv(path, csv_text):
    """Evaluate every data row. Malformed rows stay in the result as invalid.

    All supplied-authority decisions share one read-only SQLite snapshot, so a
    concurrent place/revoke cannot mix grant generations inside the batch.
    This does not record placements or invent request ids.
    """
    require(isinstance(csv_text, str), "csv must be text")
    raw = csv_text.encode("utf-8")
    require(len(raw) <= MAX_INPUT_BYTES, "csv exceeds 8 MiB")
    require("\x00" not in csv_text, "csv contains NUL")
    rows = []
    reader = csv.reader(io.StringIO(csv_text, newline=""))
    try:
        while True:
            # line_num advances to the record end; retain its start first.
            source_line = reader.line_num + 1
            try:
                columns = next(reader)
            except StopIteration:
                break
            rows.append((source_line, columns))
    except csv.Error as exc:
        raise RightsError(f"csv could not be parsed at row {source_line}: {exc}") from exc
    require(rows, "csv needs a header and at least one data row")
    header = [cell.strip() for cell in rows[0][1]]
    require(
        tuple(header) == COLUMNS,
        "csv header must be exactly asset_id,channel,territory,starts_at,ends_at",
    )
    data = rows[1:]
    require(data, "csv needs at least one data row")
    require(len(data) <= MAX_BATCH_ROWS, f"csv exceeds {MAX_BATCH_ROWS} data rows")

    prepared = []
    for offset, cols in data:
        if len(cols) == 0 or (len(cols) == 1 and cols[0].strip() == ""):
            prepared.append({"row": offset, "normalized": None, "errors": ["blank row"]})
            continue
        if len(cols) != len(COLUMNS):
            prepared.append({
                "row": offset,
                "normalized": None,
                "errors": [f"row {offset}: expected {len(COLUMNS)} columns, found {len(cols)}"],
            })
            continue
        intent = {key: value.strip() for key, value in zip(COLUMNS, cols)}
        blank = [key for key, value in intent.items() if value == ""]
        if blank:
            prepared.append({
                "row": offset,
                "normalized": None,
                "errors": [f"row {offset}: blank {', '.join(blank)}; refusing to invent a value"],
            })
            continue
        try:
            prepared.append({"row": offset, "normalized": normalize_intent(intent), "errors": []})
        except RightsError as exc:
            prepared.append({"row": offset, "normalized": None, "errors": [f"row {offset}: {exc}"]})

    generation = None
    con = _readonly(path)
    try:
        con.execute("BEGIN")
        try:
            found = con.execute("SELECT value FROM meta WHERE key='manifest_sha256'").fetchone()
        except sqlite3.Error as exc:
            raise RightsError(f"desk database is not a media-rights snapshot: {exc}") from exc
        generation = None if found is None else found[0]
        reviewed = []
        for item in prepared:
            if item["normalized"] is None:
                reviewed.append({
                    "row": item["row"],
                    "status": "invalid",
                    "errors": item["errors"],
                    "intent": None,
                    "selected_grant_id": None,
                    "reasons": [],
                    "intent_sha256": None,
                })
                continue
            try:
                decision = _evaluate(con, item["normalized"])
            except RightsError as exc:
                reviewed.append({
                    "row": item["row"],
                    "status": "invalid",
                    "errors": [f"row {item['row']}: {exc}"],
                    "intent": item["normalized"],
                    "selected_grant_id": None,
                    "reasons": [],
                    "intent_sha256": None,
                })
                continue
            reviewed.append({
                "row": item["row"],
                "status": decision["status"],
                "errors": [],
                "intent": item["normalized"],
                "selected_grant_id": decision["selected_grant_id"],
                "reasons": decision["reasons"],
                "intent_sha256": decision["intent_sha256"],
            })
    finally:
        if con.in_transaction:
            con.execute("ROLLBACK")
        con.close()

    def count(status):
        return sum(1 for row in reviewed if row["status"] == status)

    return {
        "status": "REVIEWED",
        "manifest_sha256": generation,
        "row_count": len(reviewed),
        "ready_count": count("READY_ON_SUPPLIED_AUTHORITY"),
        "hold_count": count("HOLD"),
        "invalid_count": count("invalid"),
        "rows": reviewed,
    }
