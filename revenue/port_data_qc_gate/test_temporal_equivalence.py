from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

import revenue.port_data_qc_gate.gate as gate
from revenue.port_data_qc_gate.test_gate import policy, snapshot


def _relabel_as_current(result):
    result["receipt"]["temporal_authority"] = gate.CURRENT_TEMPORAL_AUTHORITY
    core = dict(result["receipt"])
    core.pop("receipt_sha256", None)
    raw = json.dumps(
        core,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    result["receipt"]["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    return result


class CurrentEquivalenceNotMintProvenanceTests(unittest.TestCase):
    def test_fresh_relabel_is_accepted_only_as_current_equivalent_state(self):
        now = datetime.now(timezone.utc)
        captured = (now - timedelta(seconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        replayed_at = (now - timedelta(milliseconds=100)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        s = snapshot(captured)
        p = policy(120)
        historical = gate._evaluate_historical_at(p, s, evaluated_at=replayed_at)
        self.assertEqual(gate.HISTORICAL_TEMPORAL_AUTHORITY, historical["receipt"]["temporal_authority"])
        relabelled = _relabel_as_current(historical)
        # verify() proves the bound evidence still has the same current decision at
        # verifier-owned UTC. It is deliberately not a cryptographic attestation of
        # which Python helper originally serialized otherwise-equivalent bytes.
        self.assertTrue(gate.verify(relabelled, policy=p, snapshot=s))

    def test_stale_relabel_cannot_backdate_currentness(self):
        s = snapshot("2026-09-14T12:00:00Z")
        p = policy(60)
        historical = gate._evaluate_historical_at(
            p,
            s,
            evaluated_at="2026-09-14T12:00:01Z",
        )
        self.assertEqual("PASS", historical["receipt"]["decision"])
        relabelled = _relabel_as_current(historical)
        self.assertFalse(gate.verify(relabelled, policy=p, snapshot=s))


if __name__ == "__main__":
    unittest.main()
