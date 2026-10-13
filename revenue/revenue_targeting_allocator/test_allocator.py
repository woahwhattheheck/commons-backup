import unittest

from .test_core import CoreTests
from .test_security import SecurityTests

__all__ = ["CoreTests", "SecurityTests"]

if __name__ == "__main__":
    unittest.main()
