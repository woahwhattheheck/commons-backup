from __future__ import annotations

import copy
import unittest
from support import *


class NormalizationTests(unittest.TestCase):
    def test_semantically_unordered_lists_normalize(self):
        a = load_fixture("scenario_good.json")
        b = copy.deepcopy(a)
        b["traders"].reverse()
        b["news"].reverse()
        b["panel"]["slots"].reverse()
        self.assertEqual(canonical_bytes(compile_result(a)), canonical_bytes(compile_result(b)))
