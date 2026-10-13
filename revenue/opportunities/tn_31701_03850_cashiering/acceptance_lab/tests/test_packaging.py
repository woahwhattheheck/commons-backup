"""Package metadata follows the actual reporting engine generation."""
import unittest
import cashiering_lab
from cashiering_lab.core import VERSION

class PackagingTests(unittest.TestCase):
    def test_package_version_matches_engine(self):
        self.assertEqual(cashiering_lab.__version__, VERSION)
        self.assertEqual(VERSION, "0.1.1")
