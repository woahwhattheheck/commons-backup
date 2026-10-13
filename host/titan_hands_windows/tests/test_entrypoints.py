from __future__ import annotations

import io
import json
import unittest

from host.titan_hands_windows.server import TitanHandsServer, serve_jsonl


class UnicodeBackend:
    def request(self, message):
        if message.get("op") == "snapshot":
            return {"ok": True, "nodes": [{"id": "x", "role": "Text", "name": "zero\u200bwidth"}]}
        return {"ok": True}

    def close(self):
        pass


class EntrypointTests(unittest.TestCase):
    def test_jsonl_preserves_unicode_observation(self):
        import sys

        old_in, old_out = sys.stdin, sys.stdout
        try:
            sys.stdin = io.StringIO('{"op":"observe"}\n')
            sys.stdout = io.StringIO()
            serve_jsonl(TitanHandsServer(UnicodeBackend()))
            response = json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        self.assertEqual(response["added"][0]["name"], "zero\u200bwidth")


if __name__ == "__main__":
    unittest.main()
