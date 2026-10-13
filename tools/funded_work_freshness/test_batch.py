from datetime import datetime, timedelta, timezone
import unittest

from batch import (
    CACHE_SCHEMA,
    MemoizingTransport,
    ReceiptCache,
    cache_entry_hash,
    candidate_fingerprint,
    process_batch,
)
from models import Candidate, Response
from receipt import receipt_hash

NOW = datetime(2026, 9, 13, 7, 40, tzinfo=timezone.utc)


class UnderlyingTransport:
    def __init__(self):
        self.calls = []

    def fetch(self, url, *, accept):
        self.calls.append((url, accept))
        return Response(url=url, status=200, headers={}, body=b"{}")


def candidate(
    url="https://board.example/bounty/1",
    canonical="https://github.com/acme/repo/issues/7",
    amount="500",
    max_age_days=30,
    max_visible_claims=0,
):
    return Candidate.validated(
        candidate_url=url,
        platform="fixture",
        advertised_amount=amount,
        currency="USD",
        canonical_url=canonical,
        max_age_days=max_age_days,
        max_visible_claims=max_visible_claims,
    )


def receipt_for(
    item,
    status="actionable",
    *,
    generated_at=NOW,
    evidence_complete=True,
):
    value = {
        "schema": "funded-work-freshness/v1",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "candidate": {
            "url": item.candidate_url,
            "platform": item.platform,
            "advertised_amount": item.advertised_amount,
            "currency": item.currency,
            "canonical_url_hint": item.canonical_url,
        },
        "canonical": {"url": item.canonical_url, "state": "open"},
        "checks": {"evidence_complete": evidence_complete},
        "freshness_status": status,
        "route": "qualified_for_human_claim_decision" if status == "actionable" else "reject",
        "reasons": ["fixture"],
    }
    value["receipt_sha256"] = receipt_hash(value)
    return value


class BatchTests(unittest.TestCase):
    def test_exact_duplicate_evaluated_once(self):
        item = candidate()
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate)

        report, _ = process_batch([item, item], UnderlyingTransport(), observed_at=NOW, evaluator=evaluator)
        self.assertEqual(1, len(calls))
        self.assertEqual(1, report["stats"]["batch_duplicate_hits"])
        self.assertEqual("batch_duplicate", report["items"][1]["source"])
        self.assertEqual(0, report["items"][1]["duplicate_of"])

    def test_same_canonical_shares_http_response_without_sharing_policy(self):
        first = candidate(url="https://a.example/1", amount="500")
        second = candidate(url="https://b.example/2", amount="750")
        underlying = UnderlyingTransport()

        def evaluator(item, transport, *, observed_at):
            transport.fetch("https://api.github.com/repos/acme/repo/issues/7", accept="application/json")
            return receipt_for(item)

        report, _ = process_batch([first, second], underlying, observed_at=NOW, evaluator=evaluator)
        self.assertEqual(1, len(underlying.calls))
        self.assertEqual(1, report["stats"]["http_network_fetches"])
        self.assertEqual(1, report["stats"]["http_memo_hits"])
        self.assertEqual([0, 1], report["canonical_groups"][first.canonical_url])
        self.assertEqual("500", report["items"][0]["receipt"]["candidate"]["advertised_amount"])
        self.assertEqual("750", report["items"][1]["receipt"]["candidate"]["advertised_amount"])

    def test_fresh_persistent_cache_skips_evaluator(self):
        item = candidate()
        cache = ReceiptCache()
        cached_at = NOW - timedelta(seconds=10)
        cache.put(
            item,
            receipt_for(item, status="occupied", generated_at=cached_at),
            cached_at=cached_at,
        )

        def fail(*args, **kwargs):
            raise AssertionError("evaluator should not run")

        report, _ = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW, cache=cache, cache_ttl_seconds=60, evaluator=fail
        )
        self.assertEqual("persistent_cache", report["items"][0]["source"])
        self.assertEqual(1, report["stats"]["persistent_cache_hits"])
        self.assertEqual(0, report["stats"]["fresh_evaluations"])

    def test_actionable_persistent_cache_is_never_reused(self):
        item = candidate()
        cache = ReceiptCache()
        cached_at = NOW - timedelta(seconds=1)
        cache.put(item, receipt_for(item, generated_at=cached_at), cached_at=cached_at)
        self.assertEqual({}, cache.entries)
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate, status="occupied", generated_at=observed_at)

        report, _ = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW, cache=cache,
            cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual("fresh", report["items"][0]["source"])
        self.assertEqual(1, len(calls))

    def test_expired_or_corrupt_cache_forces_fresh_evaluation(self):
        item = candidate()
        cache = ReceiptCache()
        cached_at = NOW - timedelta(seconds=61)
        old = receipt_for(item, status="occupied", generated_at=cached_at)
        cache.put(item, old, cached_at=cached_at)
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate, status="occupied", generated_at=observed_at)

        report, cache = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW, cache=cache, cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual(1, len(calls))
        self.assertEqual("fresh", report["items"][0]["source"])
        key = candidate_fingerprint(item)
        cache.entries[key]["receipt"]["freshness_status"] = "actionable"
        report, _ = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW + timedelta(seconds=1), cache=cache,
            cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual("fresh", report["items"][0]["source"])
        self.assertEqual(2, len(calls))

    def test_cache_entry_rejects_policy_key_relabel(self):
        strict = candidate(max_age_days=1, max_visible_claims=0)
        permissive = candidate(max_age_days=90, max_visible_claims=1)
        cache = ReceiptCache()
        cache.put(strict, receipt_for(strict, status="occupied"), cached_at=NOW)
        payload = cache.to_payload(max_entries=10)
        strict_key = candidate_fingerprint(strict)
        permissive_key = candidate_fingerprint(permissive)
        payload["entries"][permissive_key] = payload["entries"].pop(strict_key)
        replay = ReceiptCache.from_payload(payload)
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate, status="actionable")

        report, _ = process_batch(
            [permissive], UnderlyingTransport(), observed_at=NOW,
            cache=replay, cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual("fresh", report["items"][0]["source"])
        self.assertEqual(1, len(calls))

    def test_cache_entry_rejects_unhashed_timestamp_refresh(self):
        item = candidate()
        cache = ReceiptCache()
        cached_at = NOW - timedelta(seconds=61)
        cache.put(
            item,
            receipt_for(item, status="occupied", generated_at=cached_at),
            cached_at=cached_at,
        )
        payload = cache.to_payload(max_entries=10)
        key = candidate_fingerprint(item)
        payload["entries"][key]["cached_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat().replace("+00:00", "Z")
        replay = ReceiptCache.from_payload(payload)
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate, status="occupied", generated_at=observed_at)

        report, _ = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW,
            cache=replay, cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual("fresh", report["items"][0]["source"])
        self.assertEqual(1, len(calls))

    def test_incomplete_evidence_is_never_persisted_or_reused(self):
        item = candidate()
        incomplete = receipt_for(
            item, status="ambiguous", evidence_complete=False
        )
        cache = ReceiptCache()
        cache.put(item, incomplete, cached_at=NOW)
        self.assertEqual({}, cache.entries)

        fingerprint = candidate_fingerprint(item)
        entry = {
            "candidate_fingerprint": fingerprint,
            "cached_at": NOW.isoformat().replace("+00:00", "Z"),
            "receipt": incomplete,
        }
        entry["entry_sha256"] = cache_entry_hash(entry)
        replay = ReceiptCache.from_payload(
            {"schema": CACHE_SCHEMA, "entries": {fingerprint: entry}}
        )
        self.assertEqual({}, replay.entries)
        calls = []

        def evaluator(candidate, transport, *, observed_at):
            calls.append(candidate)
            return receipt_for(candidate, generated_at=observed_at)

        report, _ = process_batch(
            [item], UnderlyingTransport(), observed_at=NOW, cache=replay,
            cache_ttl_seconds=60, evaluator=evaluator
        )
        self.assertEqual("fresh", report["items"][0]["source"])
        self.assertEqual(1, len(calls))

    def test_legacy_unbound_cache_entry_is_dropped(self):
        item = candidate()
        fingerprint = candidate_fingerprint(item)
        payload = {
            "schema": CACHE_SCHEMA,
            "entries": {
                fingerprint: {
                    "cached_at": NOW.isoformat().replace("+00:00", "Z"),
                    "receipt": receipt_for(item, status="occupied"),
                }
            },
        }
        self.assertEqual({}, ReceiptCache.from_payload(payload).entries)

    def test_cache_bound_keeps_newest_entries(self):
        cache = ReceiptCache()
        items = [candidate(url=f"https://board.example/{i}") for i in range(3)]
        for index, item in enumerate(items):
            cached_at = NOW + timedelta(seconds=index)
            cache.put(
                item,
                receipt_for(item, status="occupied", generated_at=cached_at),
                cached_at=cached_at,
            )
        payload = cache.to_payload(max_entries=2)
        self.assertEqual(2, len(payload["entries"]))
        self.assertNotIn(candidate_fingerprint(items[0]), payload["entries"])


if __name__ == "__main__":
    unittest.main()
