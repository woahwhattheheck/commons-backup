from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AcceptanceInputError(ValueError):
    """Raised when acceptance input cannot be safely interpreted."""


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    scenario: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "status": self.status,
            "detail": self.detail,
        }


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AcceptanceInputError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise AcceptanceInputError(f"{path} must be a list")
    return value


def require_text(value: Any, path: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise AcceptanceInputError(f"{path} must be a trimmed non-empty string")
    if any(not char.isprintable() for char in value):
        raise AcceptanceInputError(f"{path} must contain printable text")
    return value
