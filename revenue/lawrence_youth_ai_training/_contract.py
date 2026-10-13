from __future__ import annotations

from pathlib import Path
from typing import Any

from ._constants import EXPECTED_SOURCE_CONTRACT_SHA256, SOURCE_SCHEMA, QualificationInputError
from ._json import _object, digest, strict_json_loads


def _load_source_contract() -> dict[str, Any]:
    path = Path(__file__).with_name("source_contract.json")
    if path.is_symlink():
        raise QualificationInputError("source_contract.json must not be a symlink")
    contract = _object(
        strict_json_loads(path.read_bytes(), "source_contract.json"),
        "source contract",
    )
    if digest(contract) != EXPECTED_SOURCE_CONTRACT_SHA256:
        raise QualificationInputError("source contract digest mismatch")
    if contract.get("schema") != SOURCE_SCHEMA:
        raise QualificationInputError("source contract schema mismatch")
    return contract
