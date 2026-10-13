"""Fixture job test. Starts red until the thin health patch lands."""

from __future__ import annotations

import unittest

from health import status


class HealthTests(unittest.TestCase):
    def test_status_ok(self) -> None:
        self.assertEqual(status(), 200)


if __name__ == "__main__":
    unittest.main()
