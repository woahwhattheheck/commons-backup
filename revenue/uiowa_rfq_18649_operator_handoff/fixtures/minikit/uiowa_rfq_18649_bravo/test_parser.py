import unittest
from parser import parse_pair


class TestParser(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_pair("a=1"), ("a", "1"))

    def test_value_with_equals_is_preserved(self):
        self.assertEqual(parse_pair("locator=s3://b/k?v=2"), ("locator", "s3://b/k?v=2"))


if __name__ == "__main__":
    unittest.main()
