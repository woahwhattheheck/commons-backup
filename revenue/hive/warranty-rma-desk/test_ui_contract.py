#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("warranty_rma_app", HERE / "app.py")
app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(app)
HTML = (HERE / "index.html").read_text()


class UIContractTest(unittest.TestCase):
    def test_operator_decisions_match_backend_contract(self):
        for value in sorted(app.DECISIONS):
            self.assertIn(f'"{value}"', HTML)

    def test_inspection_choices_match_backend_contract(self):
        for value in sorted(app.INSPECTIONS):
            self.assertIn(f'"INSPECT_{value}"', HTML)
        self.assertNotIn('"INSPECT_OK"', HTML)
        self.assertNotIn('"INSPECT_DEFECT_CONFIRMED"', HTML)

    def test_resolution_choices_match_backend_contract(self):
        for value in sorted(app.RESOLUTIONS):
            self.assertIn(f'"RESOLVE_{value}"', HTML)

    def test_dom_rendering_avoids_dynamic_inner_html(self):
        self.assertNotIn(".innerHTML", HTML)
        self.assertNotIn(".innerhtml", HTML.lower())


if __name__ == "__main__":
    unittest.main()
