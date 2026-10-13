import concurrent.futures
import datetime as dt
import json
import pathlib
import tempfile
import unittest

import lease

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 13, 23, 35, tzinfo=UTC)


class LeaseProtocolTests(unittest.TestCase):
    def test_same_target_same_key_under_case_and_space_variation(self):
        a = lease.lead_key(opportunity=" ACME / diagnostic ", channel="Email", destination="CEO@Example.com")
        b = lease.lead_key(opportunity="acme / diagnostic", channel=" email ", destination="ceo@example.COM")
        self.assertEqual(a, b)
        self.assertEqual(lease.lease_path(a), f"coordination/outbound/leases/{a}.json")

    def test_public_document_does_not_contain_raw_destination(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="Z-Forge",
            provider_snapshot="thread:123/history:9",
            now=T0,
        )
        encoded = obj.to_json()
        self.assertNotIn("buyer@example.com", encoded)
        self.assertIn(lease.fingerprint("buyer@example.com"), encoded)

    def test_provider_change_blocks_send(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="Z-Forge",
            provider_snapshot="thread:123/history:9",
            now=T0,
        )
        with self.assertRaisesRegex(lease.PreflightFailed, "provider state changed"):
            lease.assert_preflight(
                obj,
                holder="Z-Forge",
                provider_snapshot="thread:123/history:10",
                now=T0 + dt.timedelta(seconds=1),
            )

    def test_wrong_holder_and_expiry_block_send(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="Z-Forge",
            provider_snapshot="v1",
            now=T0,
            ttl_seconds=5,
        )
        with self.assertRaises(lease.PreflightFailed):
            lease.assert_preflight(obj, holder="Other", provider_snapshot="v1", now=T0)
        with self.assertRaisesRegex(lease.PreflightFailed, "expired"):
            lease.assert_preflight(obj, holder="Z-Forge", provider_snapshot="v1", now=T0 + dt.timedelta(seconds=5))

    def test_sent_is_terminal(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="Z-Forge",
            provider_snapshot="v1",
            now=T0,
        )
        sent = lease.mark_sent(
            obj,
            holder="Z-Forge",
            provider_snapshot="v1",
            send_receipt="gmail-message-id:abc",
            now=T0 + dt.timedelta(seconds=3),
        )
        self.assertEqual(sent.state, lease.SENT)
        self.assertNotIn("gmail-message-id:abc", sent.to_json())
        with self.assertRaises(lease.LeaseHeld):
            lease.takeover(sent, holder="Other", provider_snapshot="v2", now=T0 + dt.timedelta(days=30))
        with self.assertRaises(lease.LeaseHeld):
            lease.release(sent, holder="Z-Forge", reason="oops", now=T0 + dt.timedelta(seconds=4))

    def test_expired_takeover_increments_generation_when_provider_unchanged(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="A",
            provider_snapshot="v1",
            now=T0,
            ttl_seconds=5,
        )
        with self.assertRaises(lease.LeaseHeld):
            lease.takeover(obj, holder="B", provider_snapshot="v1", now=T0 + dt.timedelta(seconds=4))
        nxt = lease.takeover(obj, holder="B", provider_snapshot="v1", now=T0 + dt.timedelta(seconds=5), ttl_seconds=9)
        self.assertEqual(nxt.holder, "B")
        self.assertEqual(nxt.generation, 2)
        self.assertEqual(nxt.provider_snapshot, lease.fingerprint("v1"))

    def test_expired_takeover_rejects_changed_provider_after_possible_send(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="A",
            provider_snapshot="thread:123/history:9",
            now=T0,
            ttl_seconds=5,
        )
        with self.assertRaisesRegex(lease.PreflightFailed, "reconcile before takeover"):
            lease.takeover(
                obj,
                holder="B",
                provider_snapshot="thread:123/history:10",
                now=T0 + dt.timedelta(seconds=5),
            )

    def test_release_allows_same_provider_takeover_but_not_send(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="A",
            provider_snapshot="v1",
            now=T0,
        )
        released = lease.release(obj, holder="A", reason="not pursuing", now=T0 + dt.timedelta(seconds=1))
        self.assertEqual(released.state, lease.RELEASED)
        with self.assertRaises(lease.PreflightFailed):
            lease.assert_preflight(released, holder="A", provider_snapshot="v1", now=T0 + dt.timedelta(seconds=2))
        nxt = lease.takeover(released, holder="B", provider_snapshot="v1", now=T0 + dt.timedelta(seconds=2))
        self.assertEqual(nxt.state, lease.ACTIVE)
        self.assertEqual(nxt.holder, "B")

    def test_released_takeover_rejects_changed_provider(self):
        obj = lease.acquire(
            opportunity="ACME diagnostic",
            channel="email",
            destination="buyer@example.com",
            holder="A",
            provider_snapshot="v1",
            now=T0,
        )
        released = lease.release(obj, holder="A", reason="handoff", now=T0 + dt.timedelta(seconds=1))
        with self.assertRaisesRegex(lease.PreflightFailed, "reconcile before takeover"):
            lease.takeover(released, holder="B", provider_snapshot="v2", now=T0 + dt.timedelta(seconds=2))


class StoreRaceTests(unittest.TestCase):
    def _new_lease(self, holder: str):
        return lease.acquire(
            opportunity="hot lead 42",
            channel="email",
            destination="hot@example.com",
            holder=holder,
            provider_snapshot="provider-v1",
            now=T0,
        )

    def test_simultaneous_initial_claim_has_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = lease.LocalCASStore(tmp)
            contenders = [self._new_lease(f"seat-{i}") for i in range(32)]

            def attempt(obj):
                try:
                    store.create(obj)
                    return obj.holder
                except lease.LeaseHeld:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                winners = [w for w in pool.map(attempt, contenders) if w]
            self.assertEqual(len(winners), 1)
            current, _ = store.read(contenders[0].key)
            self.assertEqual(current.holder, winners[0])

    def test_competing_cas_updates_have_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = lease.LocalCASStore(tmp)
            original = self._new_lease("A")
            rev = store.create(original)
            released = lease.release(original, holder="A", reason="handoff", now=T0 + dt.timedelta(seconds=1))
            rev2 = store.compare_and_swap(released, expected_revision=rev)
            current, seen = store.read(original.key)
            self.assertEqual(rev2, seen)

            variants = [
                lease.takeover(current, holder=f"seat-{i}", provider_snapshot="provider-v1", now=T0 + dt.timedelta(seconds=2))
                for i in range(24)
            ]

            def attempt(obj):
                try:
                    store.compare_and_swap(obj, expected_revision=rev2)
                    return obj.holder
                except lease.LeaseHeld:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
                winners = [w for w in pool.map(attempt, variants) if w]
            self.assertEqual(len(winners), 1)
            final, _ = store.read(original.key)
            self.assertEqual(final.holder, winners[0])

    def test_state_file_remains_valid_json_after_many_cas_races(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = lease.LocalCASStore(tmp)
            obj = self._new_lease("A")
            rev = store.create(obj)
            for n in range(50):
                current, rev = store.read(obj.key)
                if current.state == lease.ACTIVE:
                    candidate = lease.release(current, holder=current.holder, reason=f"cycle-{n}", now=T0 + dt.timedelta(seconds=n + 1))
                else:
                    candidate = lease.takeover(current, holder=f"seat-{n}", provider_snapshot="provider-v1", now=T0 + dt.timedelta(seconds=n + 1))
                rev = store.compare_and_swap(candidate, expected_revision=rev)
                json.loads(pathlib.Path(tmp, f"{obj.key}.json").read_text())


if __name__ == "__main__":
    unittest.main()
