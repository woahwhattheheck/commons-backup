# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("name", "source", "license", "commercial_use_confirmed", "redistributable_in_submission", "organizer_disclosure_recorded")

def validate_asset_manifest(path: str | Path) -> tuple[dict[str, object], ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("asset manifest must be a JSON list")
    checked = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(f"asset row {index} must be an object")
        missing = [key for key in REQUIRED if key not in row]
        if missing:
            raise ValueError(f"asset row {index} missing fields: {missing}")
        if not row["commercial_use_confirmed"]:
            raise ValueError(f"asset row {index} lacks commercial-use confirmation")
        if not row["redistributable_in_submission"]:
            raise ValueError(f"asset row {index} cannot be redistributed in the submission")
        if not row["organizer_disclosure_recorded"]:
            raise ValueError(f"asset row {index} lacks organizer-disclosure record")
        checked.append(row)
    return tuple(checked)
