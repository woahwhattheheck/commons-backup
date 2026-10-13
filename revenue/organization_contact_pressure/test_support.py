from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from revenue.organization_contact_pressure import gate
from .test_fixture import GateFixture, digest, ts


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fx = GateFixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def assert_decision(self, expected, receipt):
        self.assertEqual(expected, receipt["decision"], receipt)
        self.assertFalse(receipt["external_send_authorized"])
