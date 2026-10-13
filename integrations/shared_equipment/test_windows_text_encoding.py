"""Explicit Windows text decoding and exact binary retrieval contracts."""
import base64
import ctypes
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from integrations.shared_equipment import credential_transfer as ct
from integrations.shared_equipment.credential_client import CredentialRequest


class WindowsTextEncodingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sources = ct.CredentialSources(config_path=self.root / "sources.json", box_paths=())

    def test_decoder_install_is_idempotent(self):
        from integrations.shared_equipment.windows_text import install_windows_text_decoder

        reader = ct.CredentialSources._descriptor_read
        install_windows_text_decoder()
        self.assertIs(ct.CredentialSources._descriptor_read, reader)

    def test_windows_explicit_text_encodings_and_binary_precedence(self):
        class Credential(ctypes.Structure):
            _fields_ = [("CredentialBlobSize", ctypes.c_uint32),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte))]

        payloads = {
            "utf8-json": b'{"token":"synthetic-text"}\x00\x00',
            "utf16-text": "synthetic-key".encode("utf-16-le"),
            "utf16-json": json.dumps({"nested": {"field/with/slash": "p\u00e4ss-\u6d4b\u8bd5"}},
                                      ensure_ascii=False).encode("utf-16-le"),
            "odd-utf16": b"A",
            "binary": b"\x00\xff\x80A\x00B\x00",
            "utf8-nuls": b"A\x00B\x00",
        }
        retained, freed = [], []

        def read(target, kind, flags, out):
            raw = payloads[target]
            buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
            record = Credential(len(raw), buffer)
            retained.append((buffer, record))
            ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(
                ctypes.pointer(record), ctypes.c_void_p)
            return True

        module = SimpleNamespace(CREDENTIAL=Credential, advapi32=SimpleNamespace(
            CredReadW=read, CredFree=lambda pointer: freed.append(pointer.value)))
        descriptors = {
            "windows/legacy": {"target": "utf8-json", "format": "json", "pointer": "/token"},
            "windows/utf16": {"target": "utf16-text", "text_encoding": "utf-16-le"},
            "windows/unicode": {"target": "utf16-json", "text_encoding": "utf-16-le",
                                "format": "json", "pointer": "/nested/field~1with~1slash"},
            "windows/malformed": {"target": "odd-utf16", "text_encoding": "utf-16-le"},
            "windows/unsupported": {"target": "utf16-text", "text_encoding": "utf-32"},
            "windows/binary": {"target": "binary", "encoding": "base64",
                               "text_encoding": "utf-16-le"},
            "windows/embedded": {"target": "utf8-nuls"},
        }
        self.sources.config_path.write_text(json.dumps({"sources": {
            ref: {"type": "windows_credential", **descriptor}
            for ref, descriptor in descriptors.items()}}), encoding="utf-8")
        with patch.object(ct.CredentialSources, "_gemini_module", return_value=module):
            expected = {"windows/legacy": "synthetic-text", "windows/utf16": "synthetic-key",
                        "windows/unicode": "p\u00e4ss-\u6d4b\u8bd5", "windows/embedded": "A\x00B"}
            for ref, value in expected.items():
                with self.subTest(reference=ref):
                    self.assertEqual(self.sources.read(ref), value)
                    pending = CredentialRequest(ref)
                    self.assertEqual(pending.open(self.sources.retrieve_sealed(pending.arguments())), value)
            with self.assertRaisesRegex(ct.CredentialTransferError,
                                        "^existing_credential_source_unavailable_or_empty$"):
                self.sources.read("windows/malformed")
            with self.assertRaisesRegex(ct.CredentialTransferError,
                                        "^existing_credential_source_unavailable_or_empty$"):
                self.sources.read("windows/unsupported")
            encoded = self.sources.read("windows/binary")
            self.assertEqual(base64.b64decode(encoded, validate=True), payloads["binary"])
            pending = CredentialRequest("windows/binary")
            sealed = self.sources.retrieve_sealed(pending.arguments())
            self.assertEqual(base64.b64decode(pending.open(sealed), validate=True), payloads["binary"])
        self.assertEqual(len(freed), 11)


if __name__ == "__main__":
    unittest.main()
