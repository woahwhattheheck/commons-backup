from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from unittest import mock

from .acceptance import base_packet
from .cli import _read_json, main
from .engine import ContractError


class _StdoutCapture:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, value):
        return len(value)

    def flush(self):
        return None


class CliIngressTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write('{"a":1,"a":2}')
            path = handle.name
        try:
            with self.assertRaises(ContractError):
                _read_json(path)
        finally:
            os.unlink(path)

    def test_regular_packet_reads(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            json.dump(base_packet("read"), handle)
            path = handle.name
        try:
            self.assertEqual(_read_json(path)["portfolio_id"], "portfolio-read")
        finally:
            os.unlink(path)

    def test_final_component_symlink_rejected_when_supported(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "packet.json")
            link = os.path.join(directory, "link.json")
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(base_packet("symlink"), handle)
            os.symlink(target, link)
            with self.assertRaises(OSError):
                _read_json(link)

    def test_verify_exit_code_requires_current_gate_clear(self):
        capture = _StdoutCapture()
        with mock.patch("revenue.commercial_portfolio_allocator.cli._read_json", side_effect=[{}, {}]), mock.patch(
            "revenue.commercial_portfolio_allocator.cli.verify_plan",
            return_value={"historical_valid": True, "current_gate_clear": False},
        ), mock.patch("revenue.commercial_portfolio_allocator.cli.sys.stdout", capture):
            self.assertEqual(main(["verify", "packet.json", "plan.json"]), 2)

        capture = _StdoutCapture()
        with mock.patch("revenue.commercial_portfolio_allocator.cli._read_json", side_effect=[{}, {}]), mock.patch(
            "revenue.commercial_portfolio_allocator.cli.verify_plan",
            return_value={"historical_valid": True, "current_gate_clear": True},
        ), mock.patch("revenue.commercial_portfolio_allocator.cli.sys.stdout", capture):
            self.assertEqual(main(["verify", "packet.json", "plan.json"]), 0)


if __name__ == "__main__":
    unittest.main()
