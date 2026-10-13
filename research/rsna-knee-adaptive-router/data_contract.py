from __future__ import annotations

import csv
import hashlib
import io
from typing import Any, Mapping, Sequence

from controller import Series, receipt


def _integer(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be integer in [{lo}, {hi}]")
    return value


def series_manifest_from_csv(data: bytes, slice_counts: Mapping[str, Any]) -> dict[str, tuple[Series, ...]]:
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("series manifest too large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("series manifest must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected = ("StudyInstanceUID", "SeriesInstanceUID", "Fluid_Sensitive", "Fat_Suppression", "Anatomical_Plane")
    if tuple(reader.fieldnames or ()) != expected:
        raise ValueError("series manifest header mismatch")
    rows: list[Series] = []
    seen: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        if None in row or set(row) != set(expected):
            raise ValueError(f"series manifest row {row_number} shape mismatch")
        study = (row["StudyInstanceUID"] or "").strip()
        sid = (row["SeriesInstanceUID"] or "").strip()
        if not study or not sid:
            raise ValueError(f"series manifest row {row_number} has empty id")
        if sid in seen:
            raise ValueError("duplicate SeriesInstanceUID in manifest")
        seen.add(sid)
        def bit(name: str) -> int:
            value = (row[name] or "").strip()
            if value not in {"0", "1"}:
                raise ValueError(f"{name} must be 0 or 1")
            return int(value)
        if sid not in slice_counts:
            raise ValueError(f"missing slice count for {sid}")
        count = _integer(slice_counts[sid], f"slice_count[{sid}]", 1, 10000)
        rows.append(Series(study, sid, (row["Anatomical_Plane"] or "").strip(), bit("Fluid_Sensitive"), bit("Fat_Suppression"), count).validate())
    if not rows:
        raise ValueError("series manifest has no rows")
    if set(slice_counts) != seen:
        raise ValueError("slice count keys must exactly match manifest series")
    grouped: dict[str, list[Series]] = {}
    for row in rows:
        grouped.setdefault(row.study_id, []).append(row)
    return {study: tuple(sorted(items, key=lambda x: x.series_id)) for study, items in sorted(grouped.items())}


def assign_group_folds(study_groups: Sequence[tuple[str, str]], n_folds: int, *, salt: str) -> dict[str, int]:
    folds = _integer(n_folds, "n_folds", 2, 1000)
    if type(salt) is not str or not salt or len(salt) > 256:
        raise ValueError("salt must be a non-empty bounded string")
    if not study_groups:
        raise ValueError("study_groups must not be empty")
    studies: set[str] = set()
    group_fold: dict[str, int] = {}
    out: dict[str, int] = {}
    for study_id, group_id in study_groups:
        if type(study_id) is not str or not study_id or type(group_id) is not str or not group_id:
            raise ValueError("study/group ids must be non-empty strings")
        if study_id in studies:
            raise ValueError("duplicate study_id in fold manifest")
        studies.add(study_id)
        if group_id not in group_fold:
            digest = hashlib.sha256((salt + "\0" + group_id).encode("utf-8")).digest()
            group_fold[group_id] = int.from_bytes(digest[:8], "big") % folds
        out[study_id] = group_fold[group_id]
    return out


_ABSTENTION_REASONS = {"MISSING_SERIES", "PREDICTOR_ERROR", "RESOURCE_BUDGET", "INVARIANT_REJECTED"}

def abstention_receipt(study_id: str, reason_code: str, *, selected_series: Sequence[str] = ()) -> dict[str, Any]:
    if type(study_id) is not str or not study_id:
        raise ValueError("study_id required")
    if reason_code not in _ABSTENTION_REASONS:
        raise ValueError("unknown abstention reason")
    if len(set(selected_series)) != len(selected_series) or any(type(x) is not str or not x for x in selected_series):
        raise ValueError("selected_series must be unique non-empty strings")
    return receipt("abstention", {"study_id": study_id, "reason_code": reason_code, "selected_series": list(selected_series)})
