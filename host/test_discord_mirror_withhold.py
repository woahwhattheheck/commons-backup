"""Regression: a rejected Discord chunk withholds the whole send.

The joined mirror of a software report can be allowed while a later chunk,
read alone, is rejected. The job must send nothing and must not raise.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from commons_publication_policy import check_publication
from host.discord_mirror import send_parts


def _response(body: bytes):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    return _Resp()


class DiscordChunkWithholdTest(unittest.TestCase):
    def _parts(self):
        artifact = "https://github.com/woahwhattheheck/commons/actions/runs/35937027364"
        head = (
            "workflow repair for the ci pipeline. "
            + artifact
            + " "
            + ("context " * 80)
        )
        tail = "The workflow failed and the error remains broken."
        return [head, tail]

    def test_joined_report_is_allowed_and_tail_chunk_is_not(self):
        head, tail = self._parts()
        self.assertTrue(check_publication("\n".join((head, tail)))["allowed"])
        self.assertFalse(check_publication(tail)["allowed"])

    def test_rejected_chunk_sends_nothing(self):
        with patch("host.discord_mirror.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(b'{"id":"should-not-send"}')
            receipts = send_parts(self._parts(), token="token", channel="1")
        self.assertEqual(receipts, [])
        urlopen.assert_not_called()

    def test_allowed_message_still_posts(self):
        with patch("host.discord_mirror.urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(b'{"id":"99"}')
            receipts = send_parts(
                ["Board note. The catalog page is updated."],
                token="token",
                channel="1",
            )
        self.assertEqual(receipts, ["99"])
        urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
