from __future__ import annotations

import unittest
from unittest.mock import patch

from revenue.wri_open_timber_portal import cli, engine
from revenue.wri_open_timber_portal.test_engine import _packet, TEST_NOW


class CliTests(unittest.TestCase):
    def test_compile_parser_is_current_only_and_submission_held(self):
        with patch.object(cli, "_load", return_value=_packet()), \
             patch.object(engine, "_PROCESS_UTC_NOW", lambda: TEST_NOW), \
             patch.object(cli, "compile_proposal", side_effect=lambda packet: engine.compile_proposal(packet)):
            code = cli.main(["compile", "ignored.json"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
