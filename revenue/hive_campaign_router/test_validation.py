# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

from app import make_server, qr_svg
from campaign_router import (
    Store,
    ValidationError,
    append_utm,
    event_id,
    short_url,
    validate_destination,
    validate_public_base_url,
    validate_slug,
)


class ValidationTests(unittest.TestCase):
    def test_slug_contract(self):
        self.assertEqual(validate_slug("launch-01"), "launch-01")
        for value in ("a", "ab", "-abc", "abc-", "ABC!", "a b", None, 4):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_slug(value)

    def test_public_https_destination_normalizes(self):
        self.assertEqual(validate_destination("https://EXAMPLE.com"), "https://example.com/")
        self.assertEqual(validate_destination("https://example.com:8443/a?q=1#x"), "https://example.com:8443/a?q=1#x")

    def test_unsafe_destination_classes_rejected(self):
        cases = (
            "http://example.com", "javascript:alert(1)", "//example.com/a",
            "https://localhost/x", "https://service.internal/x", "https://user@example.com/x",
            "https://127.0.0.1/x", "https://10.2.3.4/x", "https://[::1]/x",
            "https://bad host.example/x", "https://example.com/\\evil", "https://example.com/%5Cevil",
            " https://example.com/x", "https://example.com/%00x",
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_destination(value)

    def test_public_base_url_allows_loopback_http_only(self):
        self.assertEqual(validate_public_base_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080")
        self.assertEqual(validate_public_base_url("https://go.example.com/a/"), "https://go.example.com/a")
        with self.assertRaises(ValidationError):
            validate_public_base_url("http://go.example.com")
        with self.assertRaises(ValidationError):
            validate_public_base_url("https://go.example.com/?x=1")

    def test_utm_merge_preserves_non_utm_and_overwrites_old_utm(self):
        result = append_utm(
            "https://example.com/path?plan=agency&utm_source=old#buy",
            {"utm_source": "youtube", "utm_medium": "video", "utm_campaign": "launch",
             "utm_content": "description", "utm_term": ""},
        )
        parts = urlsplit(result)
        self.assertEqual(parts.fragment, "buy")
        self.assertEqual(parse_qs(parts.query), {
            "plan": ["agency"], "utm_source": ["youtube"], "utm_medium": ["video"],
            "utm_campaign": ["launch"], "utm_content": ["description"],
        })

    def test_event_id_contract(self):
        self.assertEqual(event_id("event_123456"), "event_123456")
        self.assertGreaterEqual(len(event_id()), 8)
        for value in ("short", "spaces are bad", "!invalid!", None):
            if value is None:
                continue
            with self.subTest(value=value), self.assertRaises(ValidationError):
                event_id(value)

    def test_qr_is_deterministic_svg(self):
        first = qr_svg("https://go.example.com/r/launch-01")
        second = qr_svg("https://go.example.com/r/launch-01")
        self.assertEqual(first, second)
        self.assertIn(b"<svg", first)
        self.assertIn(b"<path", first)




if __name__ == "__main__":
    unittest.main(verbosity=2)
