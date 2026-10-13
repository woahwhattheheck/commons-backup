#!/usr/bin/env python3
from authority_tests_core import EvidenceAuthorityContractCoreTests  # noqa: F401
from authority_tests_verification import EvidenceAuthorityVerificationTests  # noqa: F401
from filesystem_tests_io import FilesystemCustodyTests  # noqa: F401
from filesystem_tests_cli import CliBoundaryTests  # noqa: F401

if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
