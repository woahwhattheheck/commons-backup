#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from host.product_lifecycle_guard import (
    LifecycleError,
    canonical_active_checkout_identity,
    canonical_checkout_identity,
    check_repo,
    enforce_retired_monotonicity,
    load_json_bytes,
    validate_registry,
)

URL = "https://buy.stripe.com/exampleABC123"
SOURCE = "revenue/example_offer/offer.json"


def registry(state: str = "RETIRED", *, url: str = URL, source: str = SOURCE):
    return {
        "schema": "commons.product-lifecycle.v1",
        "products": [
            {
                "id": "example-product",
                "state": state,
                "checkout_urls": [url],
                "catalog_sources": [source],
                "effective_at": "2026-09-17T20:00:00Z" if state == "RETIRED" else None,
                "provenance": "test",
                "note": "fixture",
            }
        ],
    }


def required_workflow_paths(sources=()):
    return [
        ".github/workflows/capability-entrypoints.yml",
        "*.html",
        "host/payment_capability.py",
        "host/product_lifecycle_guard.py",
        "revenue/product_lifecycle/**",
        "revenue/outcome_commerce/catalog.json",
        *sources,
    ]


def workflow_text(sources=(), *, pull_paths=None):
    push_paths = required_workflow_paths(sources)
    lines = [
        "name: fixture",
        "",
        "on:",
        "  push:",
        "    branches:",
        "      - main",
        "    paths: &entrypoint_paths",
        *(f"      - '{path}'" for path in push_paths),
        "  pull_request:",
    ]
    if pull_paths is None:
        lines.append("    paths: *entrypoint_paths")
    else:
        lines.append("    paths:")
        lines.extend(f"      - '{path}'" for path in pull_paths)
    lines.extend(["  workflow_dispatch:", "", "jobs:", "  noop:", "    runs-on: ubuntu-latest"])
    return "\n".join(lines) + "\n"


class ProductLifecycleGuardTests(unittest.TestCase):
    def make_repo(self, doc=None, *, source_present=False):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "revenue/product_lifecycle").mkdir(parents=True)
        (root / "revenue/outcome_commerce").mkdir(parents=True)
        (root / "host").mkdir(parents=True)
        (root / ".github/workflows").mkdir(parents=True)
        (root / "p").mkdir()
        (root / "by").mkdir()
        (root / "d").mkdir()
        actual = doc if doc is not None else registry()
        (root / "revenue/product_lifecycle/registry.json").write_text(
            json.dumps(actual, sort_keys=True), encoding="utf-8"
        )
        sources = []
        for product in actual["products"]:
            sources.extend(product["catalog_sources"])
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            workflow_text(sources),
            encoding="utf-8",
        )
        if source_present:
            path = root / SOURCE
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"retired": true}', encoding="utf-8")
        return td, root

    def test_retired_checkout_on_active_root_html_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(
            f'<a data-checkout href="{URL}">buy</a>', encoding="utf-8"
        )
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual(("example-product", "storefront.html", "checkout_url"),
                         (rows[0].product_id, rows[0].path, rows[0].kind))

    def test_historical_receipts_are_not_scanned(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        for base in ("p", "by", "d"):
            (root / base / "receipt.html").write_text(URL, encoding="utf-8")
        self.assertEqual((), check_repo(root))

    def test_board_html_historical_projection_is_not_scanned(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "board.html").write_text(
            f"<pre>SHIP historical receipt {URL}</pre>", encoding="utf-8"
        )
        (root / "storefront.html").write_text(
            f'<a data-checkout href="{URL}">buy</a>', encoding="utf-8"
        )
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual("storefront.html", rows[0].path)
        self.assertEqual("checkout_url", rows[0].kind)

    def test_split_scheme_host_constructor_is_not_ambiguous_prefix(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "host/payment_capability.py").write_text(
            'def ident(path):\n    return "https://" + "buy.stripe.com" + "/" + path\n',
            encoding="utf-8",
        )
        self.assertEqual((), check_repo(root))

        (root / "host/payment_capability.py").write_text(
            'PREFIX = "https://buy.stripe.com/"\n',
            encoding="utf-8",
        )
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual("ambiguous_checkout_url", rows[0].kind)

    def test_retiring_is_non_blocking_until_cleanup_composes(self):
        td, root = self.make_repo(registry("RETIRING"), source_present=True)
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(URL, encoding="utf-8")
        (root / "host/payment_capability.py").write_text(repr(URL), encoding="utf-8")
        self.assertEqual((), check_repo(root))

    def test_normalized_checkout_alias_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        alias = "HTTPS://BUY.STRIPE.COM/exampleABC123/"
        (root / "storefront.html").write_text(alias, encoding="utf-8")
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual(URL, rows[0].identity)

    def test_percent_encoded_path_alias_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(
            "https://buy.stripe.com/example%41BC123", encoding="utf-8"
        )
        self.assertEqual(1, len(check_repo(root)))

    def test_query_alias_is_rejected_on_active_surface(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(URL + "?utm=stale", encoding="utf-8")
        self.assertEqual("checkout_url", check_repo(root)[0].kind)

    def test_fragment_alias_is_rejected_on_active_surface(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(URL + "#buy", encoding="utf-8")
        self.assertEqual("checkout_url", check_repo(root)[0].kind)

    def test_protocol_relative_alias_is_rejected_on_active_surface(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(
            "//buy.stripe.com/exampleABC123", encoding="utf-8"
        )
        self.assertEqual("checkout_url", check_repo(root)[0].kind)

    def test_http_alias_is_rejected_on_active_surface(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(
            "http://buy.stripe.com/exampleABC123", encoding="utf-8"
        )
        self.assertEqual("checkout_url", check_repo(root)[0].kind)

    def test_dns_trailing_dot_alias_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "storefront.html").write_text(
            "https://buy.stripe.com./exampleABC123", encoding="utf-8"
        )
        self.assertEqual("checkout_url", check_repo(root)[0].kind)

    def test_retired_catalog_source_presence_is_rejected(self):
        td, root = self.make_repo(source_present=True)
        self.addCleanup(td.cleanup)
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual("catalog_source_present", rows[0].kind)

    def test_catalog_source_reference_in_active_generator_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "revenue/outcome_commerce/catalog.json").write_text(
            json.dumps({"integration_sources": [SOURCE]}), encoding="utf-8"
        )
        rows = check_repo(root)
        self.assertEqual(1, len(rows))
        self.assertEqual("catalog_source_reference", rows[0].kind)

    def test_catalog_source_in_historical_receipt_remains_legal(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "p/receipt.html").write_text(SOURCE, encoding="utf-8")
        self.assertEqual((), check_repo(root))

    def test_workflow_must_wake_for_every_recorded_catalog_source(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            workflow_text(()), encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "missing required trigger"):
            check_repo(root)

    def test_escaped_solidus_checkout_in_active_json_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "revenue/outcome_commerce/catalog.json").write_text(
            r'{"nested":{"checkout":"https:\/\/buy.stripe.com\/exampleABC123"}}',
            encoding="utf-8",
        )
        rows = check_repo(root)
        self.assertTrue(
            any(row.kind == "checkout_url" and row.identity == URL for row in rows),
            rows,
        )

    def test_escaped_catalog_source_in_active_json_is_rejected(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "revenue/outcome_commerce/catalog.json").write_text(
            r'{"nested":{"source":"revenue\/example_offer\/offer.json"}}',
            encoding="utf-8",
        )
        rows = check_repo(root)
        self.assertTrue(
            any(row.kind == "catalog_source_reference" for row in rows),
            rows,
        )

    def test_invalid_active_json_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "revenue/outcome_commerce/catalog.json").write_text(
            '{"broken":', encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "invalid active JSON"):
            check_repo(root)

    def test_duplicate_key_active_json_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "revenue/outcome_commerce/catalog.json").write_text(
            '{"checkout":"a","checkout":"b"}', encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "duplicate JSON key"):
            check_repo(root)

    def test_comment_cannot_fake_workflow_catalog_source_wake(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        fake = workflow_text(()) + f"# - '{SOURCE}'\n"
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            fake, encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "missing required trigger"):
            check_repo(root)

    def test_unrelated_list_cannot_fake_workflow_catalog_source_wake(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        fake = workflow_text(()) + f"x-fake:\n  - '{SOURCE}'\n"
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            fake, encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "missing required trigger"):
            check_repo(root)

    def test_heredoc_cannot_fake_workflow_catalog_source_wake(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        fake = workflow_text(()) + (
            "x-job:\n"
            "  run: |\n"
            f"    - '{SOURCE}'\n"
        )
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            fake, encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "missing required trigger"):
            check_repo(root)

    def test_push_coverage_cannot_substitute_for_pull_request_coverage(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        pull_paths = [
            path for path in required_workflow_paths(()) if path != SOURCE
        ]
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            workflow_text((SOURCE,), pull_paths=pull_paths), encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "on.pull_request.paths"):
            check_repo(root)

    def test_workflow_must_wake_on_its_own_guard_surface(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        text = workflow_text((SOURCE,)).replace(
            "      - 'host/product_lifecycle_guard.py'\n", ""
        )
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            text, encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "host/product_lifecycle_guard.py"):
            check_repo(root)

    def test_alias_backed_exact_negative_path_filter_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        text = workflow_text((SOURCE,)).replace(
            "      - 'host/product_lifecycle_guard.py'\n",
            "      - 'host/product_lifecycle_guard.py'\n"
            "      - '!host/product_lifecycle_guard.py'\n",
        )
        (root / ".github/workflows/capability-entrypoints.yml").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(LifecycleError, "negative lifecycle workflow path filter"):
            check_repo(root)

    def test_alias_backed_wildcard_negative_path_filter_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        text = workflow_text((SOURCE,)).replace(
            "      - 'host/product_lifecycle_guard.py'\n",
            "      - 'host/product_lifecycle_guard.py'\n"
            "      - '!host/**'\n",
        )
        (root / ".github/workflows/capability-entrypoints.yml").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(LifecycleError, "negative lifecycle workflow path filter"):
            check_repo(root)

    def test_direct_pull_exact_negative_path_filter_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        pull_paths = [*required_workflow_paths((SOURCE,)), "!host/product_lifecycle_guard.py"]
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            workflow_text((SOURCE,), pull_paths=pull_paths), encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "negative lifecycle workflow path filter"):
            check_repo(root)

    def test_direct_pull_wildcard_negative_path_filter_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        pull_paths = [*required_workflow_paths((SOURCE,)), "!revenue/**"]
        (root / ".github/workflows/capability-entrypoints.yml").write_text(
            workflow_text((SOURCE,), pull_paths=pull_paths), encoding="utf-8"
        )
        with self.assertRaisesRegex(LifecycleError, "negative lifecycle workflow path filter"):
            check_repo(root)

    def test_paths_ignore_fails_closed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        text = workflow_text((SOURCE,)).replace(
            "  pull_request:\n",
            "    paths-ignore:\n      - 'host/**'\n  pull_request:\n",
        )
        (root / ".github/workflows/capability-entrypoints.yml").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(LifecycleError, "paths-ignore is forbidden"):
            check_repo(root)

    def test_retired_product_cannot_be_downgraded(self):
        old = validate_registry(registry("RETIRED"))
        new = validate_registry(registry("RETIRING"))
        with self.assertRaisesRegex(LifecycleError, "downgraded"):
            enforce_retired_monotonicity(old, new)

    def test_retired_product_cannot_be_deleted(self):
        old = validate_registry(registry("RETIRED"))
        new = validate_registry({"schema": "commons.product-lifecycle.v1", "products": []})
        with self.assertRaisesRegex(LifecycleError, "removed from lifecycle"):
            enforce_retired_monotonicity(old, new)

    def test_retired_checkout_identity_cannot_be_removed(self):
        old = validate_registry(registry("RETIRED"))
        doc = registry("RETIRED")
        doc["products"][0]["checkout_urls"] = []
        new = validate_registry(doc)
        with self.assertRaisesRegex(LifecycleError, "checkout identities removed"):
            enforce_retired_monotonicity(old, new)

    def test_retired_catalog_source_cannot_be_removed(self):
        old = validate_registry(registry("RETIRED"))
        doc = registry("RETIRED")
        doc["products"][0]["catalog_sources"] = []
        new = validate_registry(doc)
        with self.assertRaisesRegex(LifecycleError, "catalog sources removed"):
            enforce_retired_monotonicity(old, new)

    def test_check_repo_compares_base_registry(self):
        td, root = self.make_repo(registry("RETIRING"))
        self.addCleanup(td.cleanup)
        base = root / "base.json"
        base.write_text(json.dumps(registry("RETIRED")), encoding="utf-8")
        with self.assertRaisesRegex(LifecycleError, "downgraded"):
            check_repo(root, base_registry_path=base)

    def test_duplicate_product_id_rejected(self):
        doc = registry()
        doc["products"].append(dict(doc["products"][0]))
        with self.assertRaisesRegex(LifecycleError, "duplicate product id"):
            validate_registry(doc)

    def test_duplicate_normalized_checkout_identity_rejected_across_products(self):
        doc = registry()
        other = dict(doc["products"][0])
        other["id"] = "second-product"
        other["checkout_urls"] = ["HTTPS://BUY.STRIPE.COM/exampleABC123/"]
        other["catalog_sources"] = ["revenue/second/offer.json"]
        doc["products"].append(other)
        with self.assertRaisesRegex(LifecycleError, "checkout identity shared"):
            validate_registry(doc)

    def test_duplicate_checkout_identity_rejected_within_product(self):
        doc = registry()
        doc["products"][0]["checkout_urls"] = [
            URL,
            "HTTPS://BUY.STRIPE.COM/exampleABC123/",
        ]
        with self.assertRaisesRegex(LifecycleError, "within example-product"):
            validate_registry(doc)

    def test_duplicate_catalog_source_rejected_across_products(self):
        doc = registry()
        other = dict(doc["products"][0])
        other["id"] = "second-product"
        other["checkout_urls"] = ["https://buy.stripe.com/other"]
        doc["products"].append(other)
        with self.assertRaisesRegex(LifecycleError, "catalog source shared"):
            validate_registry(doc)

    def test_invalid_state_rejected(self):
        doc = registry()
        doc["products"][0]["state"] = "DELETED"
        with self.assertRaisesRegex(LifecycleError, "invalid lifecycle state"):
            validate_registry(doc)

    def test_retired_requires_effective_at(self):
        doc = registry()
        doc["products"][0]["effective_at"] = None
        with self.assertRaisesRegex(LifecycleError, "requires effective_at"):
            validate_registry(doc)

    def test_registry_duplicate_json_key_rejected(self):
        raw = b'{"schema":"commons.product-lifecycle.v1","schema":"x","products":[]}'
        with self.assertRaisesRegex(LifecycleError, "duplicate JSON key"):
            load_json_bytes(raw)

    def test_registry_float_rejected(self):
        raw = b'{"schema":"commons.product-lifecycle.v1","products":[],"x":1.5}'
        with self.assertRaisesRegex(LifecycleError, "floating-point"):
            load_json_bytes(raw)

    def test_unknown_keys_rejected(self):
        doc = registry()
        doc["products"][0]["authority"] = "send-money"
        with self.assertRaisesRegex(LifecycleError, "unknown keys"):
            validate_registry(doc)

    def test_catalog_source_path_traversal_rejected(self):
        doc = registry(source="../p/receipt.json")
        with self.assertRaisesRegex(LifecycleError, "normalized repository-relative"):
            validate_registry(doc)

    def test_checkout_query_fragment_rejected_in_registry(self):
        doc = registry(url=URL + "?utm=stale")
        with self.assertRaisesRegex(LifecycleError, "query/fragment"):
            validate_registry(doc)

    def test_active_identity_discards_query_and_fragment(self):
        self.assertEqual(URL, canonical_active_checkout_identity(URL + "?x=1#frag"))

    def test_checkout_identity_has_no_assert_dependency(self):
        self.assertEqual(URL, canonical_checkout_identity(URL))


if __name__ == "__main__":
    unittest.main()
