import io
import unittest
import urllib.error
from unittest import mock

from broker import Upstream
from gateway import API_ROOT, GitHubProvider, NoRedirect, build_url


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
    def read1(self, n=-1):
        return self.read(n)


class URLTests(unittest.TestCase):
    def test_fixed_routes_encode_dynamic_segments(self):
        self.assertEqual(API_ROOT + "/repos/o/r", build_url("repo.get", {"owner": "o", "repo": "r"}))
        url = build_url("contents.get", {"owner": "o", "repo": "r", "path": "dir/a b.txt", "ref": "main"})
        self.assertEqual(API_ROOT + "/repos/o/r/contents/dir/a%20b.txt?ref=main", url)
        url = build_url("search.issues", {"q": "repo:o/r is:issue bug", "page": 2, "per_page": 50})
        self.assertTrue(url.startswith(API_ROOT + "/search/issues?"))
        self.assertIn("q=repo%3Ao%2Fr+is%3Aissue+bug", url)
    def test_pull_list_url_and_strict_filters(self):
        url = build_url("pulls.list", {
            "owner": "WoahWhatTheHeck", "repo": "Commons",
            "head": "woahwhattheheck:sol56/branch", "base": "main",
            "state": "all", "page": 2, "per_page": 25,
        })
        self.assertEqual(
            API_ROOT + "/repos/woahwhattheheck/commons/pulls?"
            "head=woahwhattheheck%3Asol56%2Fbranch&base=main&state=all&page=2&per_page=25", url,
        )
        self.assertEqual(
            API_ROOT + "/repos/o/r/pulls?page=1&per_page=30",
            build_url("pulls.list", {"owner": "o", "repo": "r"}),
        )
        for bad in (
            {"head": "woahwhattheheck:foo\r\nX-Test: yes"},
            {"base": "main\r\nX-Test: yes"},
            {"head": "woahwhattheheck:../bad"},
            {"base": "feature//bad"},
            {"state": "merged"}, {"page": 0}, {"per_page": 101},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_url("pulls.list", {"owner": "o", "repo": "r", **bad})

    def test_pr_review_and_commit_routes_are_bounded_gets(self):
        # Each route is a fixed GET URL with the existing core read quota.
        for route, suffix in (
            ("pull.reviews", "reviews"),
            ("pull.comments", "comments"),
            ("pull.commits", "commits"),
        ):
            with self.subTest(route=route):
                self.assertEqual(
                    API_ROOT + f"/repos/o/r/pulls/42/{suffix}?page=1&per_page=30",
                    build_url(route, {"owner": "O", "repo": "R", "number": 42}),
                )
                self.assertEqual(
                    API_ROOT + f"/repos/o/r/pulls/42/{suffix}?page=2&per_page=25",
                    build_url(route, {"owner": "o", "repo": "r", "number": 42, "page": 2, "per_page": 25}),
                )
                for bad in (
                    {"number": True}, {"number": 0}, {"page": 0},
                    {"page": "2"}, {"per_page": 101},
                    {"url": "https://elsewhere.invalid"}, {"method": "POST"},
                ):
                    with self.subTest(route=route, bad=bad), self.assertRaises(ValueError):
                        build_url(route, {"owner": "o", "repo": "r", "number": 42, **bad})

    def test_traversal_and_header_injection_rejected(self):
        for route, params in [
            ("contents.get", {"owner": "o", "repo": "r", "path": "../x"}),
            ("commit.get", {"owner": "o", "repo": "r", "ref": "x\nInjected: y"}),
        ]:
            with self.assertRaises(ValueError):
                build_url(route, params)


class ProviderTests(unittest.TestCase):
    def test_get_only_fixed_origin_and_token_never_in_url(self):
        provider = GitHubProvider("synthetic-token-never-real")
        opener = mock.Mock()
        opener.open.return_value = Response(b'{"name":"demo"}', headers={})
        provider._opener = opener
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        request = opener.open.call_args.args[0]
        self.assertEqual(200, result.status)
        self.assertEqual("GET", request.method)
        self.assertEqual(API_ROOT + "/repos/o/r", request.full_url)
        self.assertNotIn("synthetic-token", request.full_url)
        self.assertEqual("Bearer synthetic-token-never-real", request.get_header("Authorization"))

    def test_redirects_are_never_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.invalid"))

    def test_secondary_limit_is_detected_but_body_is_not_returned(self):
        provider = GitHubProvider("synthetic-token-never-real")
        body = io.BytesIO(b'{"message":"You have exceeded a secondary rate limit. Please wait."}')
        err = urllib.error.HTTPError(API_ROOT + "/repos/o/r", 403, "Forbidden", {"Retry-After": "60", "X-RateLimit-Remaining": "4999"}, body)
        provider._opener = mock.Mock(); provider._opener.open.side_effect = err
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        self.assertTrue(result.secondary_limited)
        self.assertEqual("60", result.retry_after)
        self.assertIsNone(result.payload)

        # Retry-After itself is enough to preserve backoff if the error body
        # cannot be parsed, instead of allowing an immediate cross-route retry.
        malformed = urllib.error.HTTPError(
            API_ROOT + "/repos/o/r", 403, "Forbidden", {"Retry-After": "45"}, io.BytesIO(b"not-json")
        )
        provider._opener.open.side_effect = malformed
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        self.assertTrue(result.secondary_limited)
        self.assertEqual("45", result.retry_after)
        self.assertIsNone(result.payload)

    def test_primary_limit_headers_preserved(self):
        provider = GitHubProvider("synthetic-token-never-real")
        err = urllib.error.HTTPError(API_ROOT + "/repos/o/r", 403, "Forbidden", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "2000"}, io.BytesIO(b'{"message":"rate limit exceeded"}'))
        provider._opener = mock.Mock(); provider._opener.open.side_effect = err
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        self.assertEqual(("0", "2000", False), (result.rate_remaining, result.rate_reset, result.secondary_limited))

    def test_headerless_primary_quota_is_distinct_from_secondary_and_permissions(self):
        provider = GitHubProvider("synthetic-token-never-real")
        opener = mock.Mock()
        provider._opener = opener

        # No quota headers: retain GitHub primary body evidence while hiding
        # provider text from the public response and not inventing reset data.
        primary = urllib.error.HTTPError(
            API_ROOT + "/repos/o/r", 403, "Forbidden", {},
            io.BytesIO(b'{"message":"API rate limit exceeded for user ID 293286387."}')
        )
        opener.open.side_effect = primary
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        self.assertEqual(403, result.status)
        self.assertTrue(result.primary_limited)
        self.assertFalse(result.secondary_limited)
        self.assertIsNone(result.rate_remaining)
        self.assertIsNone(result.rate_reset)
        self.assertIsNone(result.payload)

        # Integration-scoped 403 is an access error, not a quota observation.
        denied = urllib.error.HTTPError(
            API_ROOT + "/repos/o/r", 403, "Forbidden", {},
            io.BytesIO(b'{"message":"Resource not accessible by integration"}')
        )
        opener.open.side_effect = denied
        result = provider("repo.get", {"owner": "o", "repo": "r"})
        self.assertFalse(result.primary_limited)
        self.assertFalse(result.secondary_limited)

    def test_authentication_checks_expected_login(self):
        provider = GitHubProvider("synthetic-token-never-real")
        with mock.patch.object(provider, "_request", return_value=Upstream(200, {"login": "woahwhattheheck"})):
            provider.authenticate("woahwhattheheck")
            with self.assertRaises(ValueError):
                provider.authenticate("someone-else")
        with self.assertRaises(ValueError):
            provider.authenticate("bad/login")

    def test_invalid_or_oversize_json_is_upstream_error(self):
        for raw in (b"not-json", b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * 1048577, b"\xff"):
            provider = GitHubProvider("synthetic-token-never-real")
            provider._opener = mock.Mock(); provider._opener.open.return_value = Response(raw)
            self.assertEqual(502, provider("repo.get", {"owner": "o", "repo": "r"}).status)


if __name__ == "__main__":
    unittest.main()
