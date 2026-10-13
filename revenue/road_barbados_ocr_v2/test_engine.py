from .test_policy import PolicyTests
from .test_pipeline import PipelineTests

__all__ = ["PolicyTests", "PipelineTests"]

if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
