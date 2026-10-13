"""Current-state and chronological projections for Paceboard."""
from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from paceboard_common import SCHEMA_VERSION, _iso, _parse_iso


class ViewMixin:
    def snapshot(self) -> dict[str, Any]:
        now = self.clock.utc()
        connection = self._connect()
        try:
            meta = connection.execute("SELECT created_at,revision FROM workspace_meta WHERE singleton=1").fetchone()
            goals = self._rows(connection, "goals", "state ASC, created_at ASC, goal_id ASC")
            checkins = self._rows(connection, "checkins", "sequence DESC")
            notes = self._rows(connection, "trigger_notes", "sequence DESC")
            sessions = self._rows(connection, "focus_sessions", "sequence DESC")
        finally:
            connection.close()

        latest_by_goal: dict[str, dict[str, Any]] = {}
        for row in checkins:
            latest_by_goal.setdefault(row["goal_id"], row)
        goal_by_id = {row["goal_id"]: row for row in goals}
        reminders: list[dict[str, Any]] = []
        for goal in goals:
            latest = latest_by_goal.get(goal["goal_id"])
            goal["latest_checkin"] = latest
            minutes = int(goal["reminder_minutes"])
            if goal["state"] == "ACTIVE" and minutes:
                base = _parse_iso(latest["created_at"] if latest else goal["created_at"], "reminder_base")
                due = base + timedelta(minutes=minutes)
                if now >= due:
                    reminders.append({
                        "goal_id": goal["goal_id"],
                        "title": goal["title"],
                        "due_at": _iso(due),
                        "minutes_overdue": int((now - due).total_seconds() // 60),
                    })

        history: list[dict[str, Any]] = []
        for row in checkins:
            history.append({
                "type": "checkin",
                "id": row["checkin_id"],
                "goal_id": row["goal_id"],
                "goal_title": goal_by_id.get(row["goal_id"], {}).get("title", "Deleted goal"),
                "label": row["kind"],
                "detail": row["note"],
                "sequence": int(row["sequence"]),
                "created_at": row["created_at"],
            })
        for row in notes:
            history.append({
                "type": "note",
                "id": row["note_id"],
                "goal_id": row["goal_id"],
                "goal_title": goal_by_id.get(row["goal_id"], {}).get("title", "General note") if row["goal_id"] else "General note",
                "label": "TRIGGER_NOTE",
                "detail": row["body"],
                "sequence": int(row["sequence"]),
                "created_at": row["created_at"],
            })
        for row in sessions:
            effective = self._elapsed_at(row, now)
            row["elapsed_seconds"] = effective
            history.append({
                "type": "focus",
                "id": row["session_id"],
                "goal_id": row["goal_id"],
                "goal_title": goal_by_id.get(row["goal_id"], {}).get("title", "Deleted goal"),
                "label": f"FOCUS_{row['state']}",
                "detail": f"{effective // 60} minute(s) focused",
                "sequence": int(row["sequence"]),
                "created_at": row["started_at"],
            })
        history.sort(key=lambda item: (item["sequence"], item["type"], item["id"]), reverse=True)
        summary = {
            "active_goals": sum(1 for goal in goals if goal["state"] == "ACTIVE"),
            "archived_goals": sum(1 for goal in goals if goal["state"] == "ARCHIVED"),
            "done_checkins": sum(1 for row in checkins if row["kind"] == "DONE"),
            "paused_checkins": sum(1 for row in checkins if row["kind"] == "PAUSED"),
            "finished_focus_minutes": sum(
                int(row["accumulated_seconds"]) for row in sessions if row["state"] == "FINISHED"
            ) // 60,
        }
        return {
            "product": "Paceboard",
            "schema_version": SCHEMA_VERSION,
            "workspace_created_at": meta["created_at"],
            "revision": int(meta["revision"]),
            "now": _iso(now),
            "goals": goals,
            "checkins": checkins,
            "trigger_notes": notes,
            "focus_sessions": sessions,
            "reminders": reminders,
            "history": history,
            "summary": summary,
            "authority": {
                "local_only": True,
                "external_notification_authorized": False,
                "treatment_or_diagnosis": False,
                "tracking_or_analytics": False,
            },
        }

    def timeline_csv_bytes(self) -> bytes:
        snapshot = self.snapshot()
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer,
            fieldnames=("created_at", "type", "id", "goal_id", "goal_title", "label", "detail"),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in reversed(snapshot["history"]):
            writer.writerow({key: row.get(key, "") or "" for key in writer.fieldnames})
        return buffer.getvalue().encode("utf-8")
