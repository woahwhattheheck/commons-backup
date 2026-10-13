from __future__ import annotations

from typing import Any

from ._common import (
    HOST_AUTHORITY_ENVELOPE_PATH,
    HOST_AUTHORITY_KEY_PATH,
    QualificationInputError,
    SemanticAuthorityUnavailable,
    strict_json_loads,
)
from ._authority_io import _read_fixed_regular
from ._authority_model import _authenticate_envelope, _parse_key_document

def _load_host_authority() -> dict[str, Any]:
    try:
        key_raw = _read_fixed_regular(HOST_AUTHORITY_KEY_PATH, secret=True)
        envelope_raw = _read_fixed_regular(HOST_AUTHORITY_ENVELOPE_PATH, secret=False)
        key_doc = strict_json_loads(key_raw, "authority-key.json")
        envelope = strict_json_loads(envelope_raw, "semantic-authority.json")
        context = _authenticate_envelope(envelope, key_doc)
        context["mode"] = "HOST_HMAC"
        return context
    except (QualificationInputError, SemanticAuthorityUnavailable) as exc:
        raise SemanticAuthorityUnavailable("trusted semantic authority is unavailable") from exc

__all__ = [
    "_authenticate_envelope",
    "_load_host_authority",
    "_parse_key_document",
]
