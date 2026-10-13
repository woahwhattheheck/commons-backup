from __future__ import annotations

import unittest

from .common import EvidenceError
from .model import _base_ref


class BaseRefTests(unittest.TestCase):
    def test_rejects_git_invalid_branch_refs(self) -> None:
        invalid = (
            "refs/heads/main~1",
            "refs/heads/main^2",
            "refs/heads/main:evil",
            "refs/heads/main?x",
            "refs/heads/main*x",
            "refs/heads/main[x",
            "refs/heads/main@{1}",
            "refs/heads/.hidden",
            "refs/heads/release.lock",
            "refs/heads/trailing.",
            "refs/heads/release/.hidden",
            "refs/heads/release/feature.lock",
            "refs/heads/main//topic",
            "refs/heads/main..topic",
            "refs/heads/main\\topic",
            "refs/heads/main topic",
            " refs/heads/main",
            "refs/heads/main ",
            "refs/heads/main\x7ftopic",
        )
        for ref in invalid:
            with self.subTest(ref=ref), self.assertRaises(EvidenceError):
                _base_ref(ref, "policy.base_ref")

    def test_accepts_valid_nested_branch_refs(self) -> None:
        valid = (
            "refs/heads/main",
            "refs/heads/release/2026.09",
            "refs/heads/feature/@",
            "refs/heads/foo./bar",
            "refs/heads/feature/a-b_c",
        )
        for ref in valid:
            with self.subTest(ref=ref):
                self.assertEqual(_base_ref(ref, "policy.base_ref"), ref)


if __name__ == "__main__":
    unittest.main()
