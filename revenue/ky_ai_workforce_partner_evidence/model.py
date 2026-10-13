from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvidenceError(ValueError):
    """Raised when partner-evidence input cannot be safely interpreted."""


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"gate": self.gate, "status": self.status, "detail": self.detail}


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{path} must be a list")
    return value


def require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{path} must be a non-empty string")
    return value.strip()
