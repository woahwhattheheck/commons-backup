from __future__ import annotations

from typing import Any

from .codec_v2 import ClaimError, exact, sha256, text

SUBJECT_KEYS = frozenset({"claimant_id", "counterparty_id", "opportunity_id", "work_id"})


def _subject(raw: Any, where: str) -> dict[str, str]:
    row = exact(raw, SUBJECT_KEYS, where)
    return {key: text(row[key], f"{where}.{key}", 160) for key in sorted(SUBJECT_KEYS)}


def _same_subject(subject: dict[str, str], root: dict[str, str], where: str) -> None:
    if subject != root:
        raise ClaimError(f"{where}: cross-subject transplant")


def _source(raw: Any, where: str) -> tuple[str, str]:
    return text(raw["source_ref"], f"{where}.source_ref"), sha256(raw["source_sha256"], f"{where}.source_sha256")
