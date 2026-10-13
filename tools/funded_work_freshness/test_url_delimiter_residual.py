from __future__ import annotations

import unittest

from constants import GITHUB_ITEM_RE


def github_urls(text: str) -> list[str]:
    """Mirror the production consumer's canonical URL projection for regex matches."""

    return sorted(
        {
            (
                f"https://github.com/{match.group(1)}/{match.group(2)}/"
                f"{match.group(3).lower()}/{int(match.group(4))}"
            )
            for match in GITHUB_ITEM_RE.finditer(text)
        }
    )


class GithubUrlDelimiterResidualTests(unittest.TestCase):
    def test_non_delimiter_suffixes_never_bind_issue_prefix(self):
        base = "https://github.com/acme/widget/issues/42"
        for suffix in (
            "-deadbeef",
            "~name",
            "%2Fcomments",
            ".css",
        ):
            bad = base + suffix
            with self.subTest(bad=bad):
                self.assertIsNone(GITHUB_ITEM_RE.fullmatch(bad))
                self.assertEqual([], github_urls(f"see {bad} now"))

    def test_path_confusable_slash_tails_never_bind_issue_prefix(self):
        base = "https://github.com/acme/widget/issues/42"
        for suffix in (
            "/../pull/99",
            "/./comments",
            "/%2e%2e/pull/99",
            "/x.css",
            "/~name",
            "//comments",
            "/comments/../pull/99",
            "/comments%2Fmore",
        ):
            bad = base + suffix
            with self.subTest(bad=bad):
                self.assertIsNone(GITHUB_ITEM_RE.fullmatch(bad))
                self.assertEqual([], github_urls(f"see {bad} now"))

    def test_safe_slash_path_segments_remain_supported(self):
        base = "https://github.com/acme/widget/issues/42"
        for continuation in (
            "/",
            "/comments/",
            "/comments/page_2",
            "/commits/abcdef123",
            "/files?diff=split",
            "/#frag",
            "/?tab=foo",
        ):
            url = base + continuation
            with self.subTest(url=url):
                self.assertIsNotNone(GITHUB_ITEM_RE.fullmatch(url))
                self.assertEqual([base], github_urls(url))

    def test_legitimate_continuations_and_terminal_punctuation_still_bind(self):
        base = "https://github.com/acme/widget/issues/42"
        for continuation in (
            "#issuecomment-123",
            "?notification_referrer_id=1",
            "/comments",
        ):
            url = base + continuation
            with self.subTest(url=url):
                self.assertIsNotNone(GITHUB_ITEM_RE.fullmatch(url))
                self.assertEqual([base], github_urls(url))

        for rendered in (
            f"See {base}.",
            f"See ({base}).",
            f"See {base}, next",
        ):
            with self.subTest(rendered=rendered):
                self.assertEqual([base], github_urls(rendered))


if __name__ == "__main__":
    unittest.main()
