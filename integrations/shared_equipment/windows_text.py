"""Explicit Windows credential text decoding with existing custody readers."""
from __future__ import annotations

import base64
import json
from functools import wraps


def install_windows_text_decoder() -> None:
    """Compose text decoding once for every ordinary package import."""
    from .credential_transfer import CredentialSources

    if getattr(CredentialSources, "_windows_text_decoder_installed", False):
        return
    original = CredentialSources._descriptor_read

    @wraps(original)
    def descriptor_read(self, descriptor):
        if (descriptor.get("type") != "windows_credential"
                or descriptor.get("encoding") == "base64"):
            return original(self, descriptor)
        text_encoding = descriptor.get("text_encoding", "utf-8")
        if text_encoding not in ("utf-8", "utf-16-le"):
            raise ValueError()
        if text_encoding == "utf-8":
            return original(self, descriptor)
        binary = {**descriptor, "encoding": "base64"}
        binary.pop("format", None)
        binary.pop("pointer", None)
        raw = base64.b64decode(original(self, binary), validate=True)
        value = raw.decode("utf-16-le").rstrip("\x00")
        if descriptor.get("format") == "json":
            value = json.loads(value)
        return self._select(value, descriptor)

    CredentialSources._descriptor_read = descriptor_read
    CredentialSources._windows_text_decoder_installed = True
