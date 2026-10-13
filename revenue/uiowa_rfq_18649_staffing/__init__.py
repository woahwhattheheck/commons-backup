"""UIOWA-002 isolated six/eight-week staffing plan."""

from __future__ import annotations

try:
    from .canonical import INTERVIEW_SESSIONS, SCHEMA, SPECIALIST_HOURS_IN_BASE
    from .engine import schedule
    from .workbook import StaffingError
except ImportError:
    from canonical import INTERVIEW_SESSIONS, SCHEMA, SPECIALIST_HOURS_IN_BASE
    from engine import schedule
    from workbook import StaffingError

__all__ = ["INTERVIEW_SESSIONS", "SCHEMA", "SPECIALIST_HOURS_IN_BASE", "StaffingError", "schedule"]
