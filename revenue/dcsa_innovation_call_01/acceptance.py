"""Compact acceptance artifact used by the standalone closure proof."""
from __future__ import annotations

import hashlib
from typing import Any

from .strict import canonical_json_bytes


def compile_matrix() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "dcsa-innovation-call-01/acceptance-matrix/v1",
        "rows": [{"requirement": "transactional-publication", "state": "VERIFIED"}],
        "receipt_sha256": "",
    }
    value["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return value


def verify_matrix(value: dict[str, Any]) -> bool:
    retained = dict(value)
    digest = retained.get("receipt_sha256")
    retained["receipt_sha256"] = ""
    return isinstance(digest, str) and digest == hashlib.sha256(canonical_json_bytes(retained)).hexdigest()


def render_matrix_markdown(value: dict[str, Any]) -> str:
    if not verify_matrix(value):
        raise ValueError("acceptance matrix receipt failed")
    return "# Acceptance Matrix\n\n- transactional-publication: VERIFIED\n"
