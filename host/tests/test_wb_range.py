import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request

HOST_DIR = Path(__file__).resolve().parents[1]
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import wb_range


class FakeResponse:
    def __init__(self, *, status=206, headers=None, body=b"abc",
                 url="https://example.test/model.bin"):
        self.status = status
        self.headers = dict(headers or {})
        self._body = body
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def read(self):
        return self._body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class RangeReaderContractTests(unittest.TestCase):
    URL = "https://example.test/model.bin"

    def reader(self, response, *, url=None, use_cache=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        reader = wb_range.RangeReader(
            url or self.URL, Path(temp.name), use_cache=use_cache
        )
        opener = FakeOpener(response)
        reader._opener = opener
        return reader, opener

    def response(self, *, start=5, end=7, total=100, body=b"abc",
                 status=206, encoding=None, content_range=None, url=None):
        headers = {}
        if content_range is None:
            content_range = "bytes %d-%d/%s" % (start, end, total)
        if content_range is not False:
            headers["Content-Range"] = content_range
        if encoding is not None:
            headers["Content-Encoding"] = encoding
        return FakeResponse(
            status=status,
            headers=headers,
            body=body,
            url=url or self.URL,
        )

    def test_exact_206_range_is_accepted_and_requests_identity(self):
        reader, opener = self.reader(self.response())
        self.assertEqual(reader.read(5, 3), b"abc")
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_header("Range"), "bytes=5-7")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertEqual(timeout, 120)

    def test_200_full_body_fallback_is_rejected(self):
        reader, _ = self.reader(self.response(status=200))
        with self.assertRaisesRegex(wb_range.WbRangeError, "expected 206"):
            reader.read(5, 3)

    def test_missing_content_range_is_rejected(self):
        reader, _ = self.reader(self.response(content_range=False))
        with self.assertRaisesRegex(wb_range.WbRangeError, "Content-Range"):
            reader.read(5, 3)

    def test_malformed_content_range_is_rejected(self):
        reader, _ = self.reader(
            self.response(content_range="bytes=5-7/100")
        )
        with self.assertRaisesRegex(wb_range.WbRangeError, "Content-Range"):
            reader.read(5, 3)

    def test_wrong_content_range_interval_is_rejected(self):
        reader, _ = self.reader(self.response(start=4, end=6))
        with self.assertRaisesRegex(wb_range.WbRangeError, "expected 5-7"):
            reader.read(5, 3)

    def test_impossible_content_range_total_is_rejected(self):
        reader, _ = self.reader(self.response(total=7))
        with self.assertRaisesRegex(wb_range.WbRangeError, "total"):
            reader.read(5, 3)

    def test_short_and_long_bodies_are_rejected(self):
        for body in (b"ab", b"abcd"):
            with self.subTest(body=body):
                reader, _ = self.reader(self.response(body=body))
                with self.assertRaisesRegex(wb_range.WbRangeError, "body length mismatch"):
                    reader.read(5, 3)

    def test_non_identity_content_encoding_is_rejected(self):
        for encoding in ("gzip", "deflate", "br"):
            with self.subTest(encoding=encoding):
                reader, _ = self.reader(self.response(encoding=encoding))
                with self.assertRaisesRegex(wb_range.WbRangeError, "expected identity"):
                    reader.read(5, 3)

    def test_redirected_final_url_is_rejected(self):
        reader, _ = self.reader(
            self.response(url="http://example.test/model.bin")
        )
        with self.assertRaisesRegex(wb_range.WbRangeError, "redirects are not allowed"):
            reader.read(5, 3)

    def test_non_loopback_http_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(wb_range.WbRangeError, "must be https"):
                wb_range.RangeReader(
                    "http://example.test/model.bin", Path(temp), use_cache=False
                )

    def test_loopback_http_rehearsal_is_preserved(self):
        url = "http://127.0.0.1:8765/model.bin"
        response = self.response(url=url)
        reader, opener = self.reader(response, url=url)
        self.assertEqual(reader.read(5, 3), b"abc")
        self.assertEqual(opener.requests[0][0].full_url, url)

    def test_remote_size_uses_same_strict_range_contract(self):
        response = FakeResponse(
            status=206,
            headers={"Content-Range": "bytes 0-0/1234"},
            body=b"x",
            url=self.URL,
        )
        reader, opener = self.reader(response)
        self.assertEqual(reader.remote_size(), 1234)
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_header("Range"), "bytes=0-0")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertEqual(timeout, 60)

    def test_remote_size_rejects_unknown_total(self):
        response = FakeResponse(
            status=206,
            headers={"Content-Range": "bytes 0-0/*"},
            body=b"x",
            url=self.URL,
        )
        reader, _ = self.reader(response)
        with self.assertRaisesRegex(wb_range.WbRangeError, "total size"):
            reader.remote_size()

    def test_remote_size_rejects_content_length_fallback(self):
        response = FakeResponse(
            status=206,
            headers={"Content-Length": "1234"},
            body=b"x",
            url=self.URL,
        )
        reader, _ = self.reader(response)
        with self.assertRaisesRegex(wb_range.WbRangeError, "Content-Range"):
            reader.remote_size()

    def test_legacy_cache_entry_is_not_trusted(self):
        response = self.response(body=b"abc")
        reader, opener = self.reader(response, use_cache=True)
        key = reader._cache_key(5, 3)
        legacy = b"old"
        legacy_name = "legacy.bin"
        (reader.chunks_dir / legacy_name).write_bytes(legacy)
        reader.manifest["entries"][key] = {
            "url": self.URL,
            "offset": 5,
            "length": 3,
            "sha256": hashlib.sha256(legacy).hexdigest(),
            "file": legacy_name,
        }
        reader._save_manifest()

        self.assertEqual(reader.read(5, 3), b"abc")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(
            reader.manifest["entries"][key]["transport_contract"],
            wb_range.RANGE_CONTRACT_VERSION,
        )

    def test_no_redirect_handler_refuses_redirect_requests(self):
        handler = wb_range._NoRedirectHandler()
        request = urllib.request.Request(self.URL)
        self.assertIsNone(
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://other.test/model.bin"
            )
        )


if __name__ == "__main__":
    unittest.main()
