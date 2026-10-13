"""Run legacy state-machine hostiles through explicitly private transport seams."""
from __future__ import annotations

from . import hardened, lock as core
from . import test_hardened as legacy_hardened
from . import test_lock as legacy_core


class PrivateCoreTransportTests(legacy_core.ProspectContactLockTests):
    def setUp(self):
        self.transport = legacy_core.FakeTransport()
        self.lock = core._TestProspectContactLock("ghp_TESTTOKEN123", self.transport)
        self.email = "Lead.Person+Pilot@Example.com"
        self.owner = dict(agent_id="ZXR-B7Q2", operation_id="OP-PAID-1")

    def test_receipt_tamper_detected(self):
        receipt = self.acquire()
        self.assertIs(receipt["test_only_transport"], True)
        with self.assertRaises(core.ValidationError):
            core.verify_receipt(receipt)
        bad = dict(receipt)
        bad["state"] = "CONTACTED"
        with self.assertRaises(core.ValidationError):
            core.verify_receipt(bad)


class PrivateHardenedTransportTests(legacy_hardened.CanonicalHardeningTests):
    def setUp(self):
        self.transport = legacy_hardened.HardenedTransport()
        self.lock = hardened._TestProspectContactLock(
            "ghp_TESTTOKEN123", self.transport
        )
        self.email = "Lead.Person+Pilot@Example.com"
        self.owner = dict(agent_id="ZXR-B7Q2", operation_id="OP-PAID-1")
