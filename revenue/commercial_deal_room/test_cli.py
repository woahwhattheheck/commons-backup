from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from .acceptance import base_packet
from .cli import _read_json
from .engine import ContractError


class CliIngressTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write('{"a":1,"a":2}')
            path=f.name
        try:
            with self.assertRaises(ContractError): _read_json(path)
        finally: os.unlink(path)

    def test_symlink_final_rejected_when_supported(self):
        if not hasattr(os,"O_NOFOLLOW"): self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as d:
            target=os.path.join(d,"p.json"); link=os.path.join(d,"link.json")
            with open(target,"w",encoding="utf-8") as out:
                out.write(json.dumps(base_packet("x")))
            os.symlink(target,link)
            with self.assertRaises(OSError): _read_json(link)

    def test_regular_packet_reads(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            json.dump(base_packet("x"),f); path=f.name
        try: self.assertEqual(_read_json(path)["buyer_id"],"buyer-x")
        finally: os.unlink(path)


if __name__ == "__main__": unittest.main()
