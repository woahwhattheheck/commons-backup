from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from tools.outbound_send_guard import muse_election_v2 as gate

MUSE = gate.MUSE_USER_ID
DM = gate.MUSE_DM_CONVERSATION_ID
SENDER = "U0BSAL3CZ4Y"
OTHER = "U0OTHER12345"
BASE = datetime(2026, 9, 15, 0, 30, 0, tzinfo=timezone.utc)
OBSERVED = "2026-09-15T00:31:10Z"
H = "a" * 64
J = "b" * 64
K = "c" * 64
L = "d" * 64
M = "e" * 64
N = "f" * 64


def z(seconds: int) -> str:
    return datetime.fromtimestamp(BASE.timestamp() + seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sts(seconds: int, frac: int = 1) -> str:
    whole = int(BASE.timestamp()) + seconds
    return f"{whole}.{frac:06d}"


def candidate(worker="ZIQ-K4R9", body=J, operation="OP-A", claim_id="claim-a"):
    return {
        "buyer_scope_sha256": H,
        "recipient_fingerprint": K,
        "offer_scope_sha256": L,
        "route_kind": "EMAIL",
        "intent_sha256": M,
        "body_sha256": body,
        "claimant": worker,
        "operation_id": operation,
        "lease_binding": {
            "schema_version": gate.LEASE_BINDING_SCHEMA,
            "receipt_schema": gate.LEASE_RECEIPT_SCHEMA,
            "claimant": worker,
            "claim_id": claim_id,
            "seam_sha256": ("1" if worker == "ZIQ-K4R9" else "2") * 64,
            "lease_ref": "refs/heads/outbound-lease-v3/" + ("1" if worker == "ZIQ-K4R9" else "2") * 64,
            "lease_commit_sha": ("5" if worker == "ZIQ-K4R9" else "6") * 40,
            "claim_capability_sha256": N if worker == "ZIQ-K4R9" else "0" * 64,
            "receipt_sha256": "3" * 64 if worker == "ZIQ-K4R9" else "4" * 64,
        },
    }


def request(c=None, rid="req-00000001", requested_at=None):
    return gate.prepare_request(c or candidate(), request_id=rid, requested_at=requested_at or z(0))


def msg(ts, author, text):
    return {"message_ts": ts, "author_user_id": author, "text": text}


def selected_text(req, kind="SELECTED"):
    p = req["payload"]
    return gate._decision_message(kind, p["request_id"], p["publication_key"], p["candidate_sha256"])


def snap(messages, **changes):
    out = {
        "schema_version": gate.SNAPSHOT_SCHEMA,
        "complete": True,
        "channel_id": DM,
        "coverage_started_at": z(-600),
        "captured_at": z(60),
        "messages": messages,
    }
    out.update(changes)
    return out


def happy(req=None):
    req = req or request()
    return snap([
        msg(sts(5, 1), SENDER, req["message"]),
        msg(sts(15, 2), MUSE, selected_text(req)),
    ])


class MuseElectionV2Tests(unittest.TestCase):
    def compile(self, req=None, snapshot=None, observed=OBSERVED, prior=(), complete=True):
        req = req or request()
        snapshot = snapshot or happy(req)
        return gate.compile_receipt(
            req,
            snapshot,
            observed_at=observed,
            prior_receipts=prior,
            ledger_complete=complete,
        )

    def test_happy_selected_and_bound(self):
        req = request()
        receipt = self.compile(req)
        self.assertEqual(receipt["payload"]["decision"], "SELECTED")
        self.assertTrue(gate.verify_receipt(receipt))
        self.assertTrue(gate.verify_selected_binding(req, receipt))
        self.assertFalse(receipt["payload"]["external_send_authorized"])
        self.assertFalse(receipt["payload"]["side_effects_authorized"])
        self.assertTrue(receipt["payload"]["requires_current_worker_lease_possession"])

    def test_publication_key_collides_across_worker_and_body(self):
        a = candidate()
        b = candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b")
        self.assertEqual(gate.publication_key(a), gate.publication_key(b))
        self.assertNotEqual(
            gate.candidate_digest(a, request_id="req-00000001", requested_at=z(0)),
            gate.candidate_digest(b, request_id="req-00000001", requested_at=z(0)),
        )

    def test_candidate_sha_binds_request_generation_without_changing_publication_key(self):
        c = candidate()
        by_id_a = request(c, rid="req-00000001", requested_at=z(0))
        by_id_b = request(c, rid="req-00000002", requested_at=z(0))
        by_time = request(c, rid="req-00000001", requested_at=z(1))
        self.assertEqual(by_id_a["payload"]["publication_key"], by_id_b["payload"]["publication_key"])
        self.assertEqual(by_id_a["payload"]["publication_key"], by_time["payload"]["publication_key"])
        self.assertNotEqual(by_id_a["payload"]["candidate_sha256"], by_id_b["payload"]["candidate_sha256"])
        self.assertNotEqual(by_id_a["payload"]["candidate_sha256"], by_time["payload"]["candidate_sha256"])

    def test_request_pins_real_muse_route(self):
        req = request()
        self.assertEqual(req["payload"]["muse_user_id"], MUSE)
        self.assertEqual(req["payload"]["muse_dm_conversation_id"], DM)
        self.assertIn(req["payload"]["publication_key"], req["message"])

    def test_wrong_channel_holds(self):
        s = happy()
        s["channel_id"] = "D0OTHER12345"
        r = self.compile(snapshot=s)
        self.assertEqual(r["payload"]["decision"], "HOLD")
        self.assertIn("WRONG_MUSE_DM_CONVERSATION", r["payload"]["reasons"])

    def test_incomplete_snapshot_holds(self):
        s = happy(); s["complete"] = False
        r = self.compile(snapshot=s)
        self.assertIn("SNAPSHOT_INCOMPLETE", r["payload"]["reasons"])

    def test_incomplete_collision_lookback_holds(self):
        s = happy(); s["coverage_started_at"] = z(-599)
        r = self.compile(snapshot=s)
        self.assertIn("COLLISION_LOOKBACK_INCOMPLETE", r["payload"]["reasons"])

    def test_stale_snapshot_holds(self):
        s = happy(); s["captured_at"] = z(20)
        r = self.compile(snapshot=s, observed=z(200))
        self.assertIn("SNAPSHOT_STALE", r["payload"]["reasons"])

    def test_future_snapshot_holds(self):
        s = happy(); s["captured_at"] = z(200)
        r = self.compile(snapshot=s, observed=z(100))
        self.assertIn("SNAPSHOT_IN_FUTURE", r["payload"]["reasons"])

    def test_non_muse_decision_holds(self):
        req = request()
        s = snap([msg(sts(5), SENDER, req["message"]), msg(sts(15), OTHER, selected_text(req))])
        r = self.compile(req, s)
        self.assertTrue(any(x.startswith("DECISION_NOT_FROM_MUSE") for x in r["payload"]["reasons"]))

    def test_muse_cannot_author_request(self):
        req = request()
        s = snap([msg(sts(5), MUSE, req["message"]), msg(sts(15), MUSE, selected_text(req))])
        r = self.compile(req, s)
        self.assertIn("REQUEST_SELF_AUTHORED_BY_MUSE", r["payload"]["reasons"])

    def test_missing_request_holds(self):
        req = request()
        s = snap([msg(sts(15), MUSE, selected_text(req))])
        r = self.compile(req, s)
        self.assertIn("EXACT_REQUEST_MESSAGE_COUNT_NOT_ONE", r["payload"]["reasons"])

    def test_duplicate_request_generation_holds(self):
        req = request()
        s = snap([
            msg(sts(5, 1), SENDER, req["message"]),
            msg(sts(6, 2), SENDER, req["message"]),
            msg(sts(15, 3), MUSE, selected_text(req)),
        ])
        r = self.compile(req, s)
        self.assertIn("EXACT_REQUEST_MESSAGE_COUNT_NOT_ONE", r["payload"]["reasons"])

    def test_decision_before_request_holds(self):
        req = request()
        s = snap([msg(sts(5), MUSE, selected_text(req)), msg(sts(10), SENDER, req["message"])])
        r = self.compile(req, s)
        self.assertTrue(any(x.startswith("DECISION_NOT_AFTER_REQUEST") for x in r["payload"]["reasons"]))

    def test_decision_after_deadline_holds(self):
        req = request()
        s = snap([
            msg(sts(5), SENDER, req["message"]),
            msg(sts(601), MUSE, selected_text(req)),
        ], captured_at=z(610))
        r = self.compile(req, s, observed=z(620))
        self.assertTrue(any(x.startswith("DECISION_AFTER_DEADLINE") for x in r["payload"]["reasons"]))

    def test_selection_freshness_holds(self):
        req = request()
        s = snap([
            msg(sts(5), SENDER, req["message"]),
            msg(sts(15), MUSE, selected_text(req)),
        ], captured_at=z(700))
        r = self.compile(req, s, observed=z(710))
        self.assertIn("MUSE_SELECTION_STALE", r["payload"]["reasons"])

    def test_explicit_not_selected(self):
        req = request()
        s = snap([msg(sts(5), SENDER, req["message"]), msg(sts(15), MUSE, selected_text(req, "NOT_SELECTED"))])
        r = self.compile(req, s)
        self.assertEqual(r["payload"]["decision"], "NOT_SELECTED")
        self.assertTrue(gate.verify_receipt(r))

    def test_other_candidate_selected_means_not_selected(self):
        mine = request()
        other = request(candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b"), rid="req-00000002")
        s = snap([
            msg(sts(5), SENDER, mine["message"]),
            msg(sts(6), OTHER, other["message"]),
            msg(sts(15), MUSE, selected_text(other)),
        ])
        r = self.compile(mine, s)
        self.assertEqual(r["payload"]["decision"], "NOT_SELECTED")
        self.assertEqual(r["payload"]["winner_candidate_sha256"], other["payload"]["candidate_sha256"])

    def test_selected_then_cancelled_not_selected(self):
        req = request()
        s = snap([
            msg(sts(5), SENDER, req["message"]),
            msg(sts(15), MUSE, selected_text(req)),
            msg(sts(16), MUSE, selected_text(req, "CANCELLED")),
        ])
        r = self.compile(req, s)
        self.assertEqual(r["payload"]["decision"], "NOT_SELECTED")
        self.assertIsNone(r["payload"]["selection_binding_sha256"])

    def test_predecessor_killer_two_workers_selected_same_publication_holds(self):
        mine = request()
        other = request(candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b"), rid="req-00000002")
        self.assertEqual(mine["payload"]["publication_key"], other["payload"]["publication_key"])
        self.assertNotEqual(mine["payload"]["candidate_sha256"], other["payload"]["candidate_sha256"])
        s = snap([
            msg(sts(5, 1), SENDER, mine["message"]),
            msg(sts(6, 2), OTHER, other["message"]),
            msg(sts(15, 3), MUSE, selected_text(mine)),
            msg(sts(16, 4), MUSE, selected_text(other)),
        ])
        r = self.compile(mine, s)
        self.assertEqual(r["payload"]["decision"], "HOLD")
        self.assertIn("MULTIPLE_DISTINCT_WINNERS", r["payload"]["reasons"])

    def test_same_candidate_selected_for_different_request_cannot_bind_generation(self):
        mine = request(rid="req-00000001")
        second = request(rid="req-00000002")
        self.assertEqual(mine["payload"]["publication_key"], second["payload"]["publication_key"])
        self.assertNotEqual(mine["payload"]["candidate_sha256"], second["payload"]["candidate_sha256"])
        s = snap([
            msg(sts(5), SENDER, mine["message"]),
            msg(sts(6), SENDER, second["message"]),
            msg(sts(15), MUSE, selected_text(second)),
        ])
        r = self.compile(mine, s)
        self.assertNotEqual(r["payload"]["decision"], "SELECTED")
        self.assertFalse(gate.verify_selected_binding(mine, r))

    def test_request_id_rebound_to_other_candidate_holds(self):
        mine = request()
        other = request(candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b"), rid=mine["payload"]["request_id"])
        p = other["payload"]
        text = gate._decision_message("SELECTED", mine["payload"]["request_id"], mine["payload"]["publication_key"], p["candidate_sha256"])
        s = snap([msg(sts(5), SENDER, mine["message"]), msg(sts(15), MUSE, text)])
        r = self.compile(mine, s)
        self.assertIn("REQUEST_ID_REBOUND_TO_DIFFERENT_CANDIDATE", r["payload"]["reasons"])

    def test_no_decision_holds(self):
        req = request()
        r = self.compile(req, snap([msg(sts(5), SENDER, req["message"])]))
        self.assertIn("NO_MUSE_DECISION", r["payload"]["reasons"])

    def test_prior_ledger_must_be_complete(self):
        r = self.compile(complete=False)
        self.assertIn("PRIOR_RECEIPT_LEDGER_INCOMPLETE", r["payload"]["reasons"])

    def test_prior_invalid_receipt_holds(self):
        bad = {"payload": {}, "receipt_sha256": "0" * 64}
        r = self.compile(prior=[bad])
        self.assertIn("PRIOR_RECEIPT_LEDGER_INVALID", r["payload"]["reasons"])

    def test_request_replay_holds(self):
        req = request()
        prior = self.compile(req)
        r = self.compile(req, prior=[prior])
        self.assertIn("REQUEST_EVIDENCE_REPLAY", r["payload"]["reasons"])

    def test_receipt_tamper_fails(self):
        r = self.compile()
        r["payload"]["claimant"] = "Z-TAMPER"
        self.assertFalse(gate.verify_receipt(r))

    def test_recomputed_outer_digest_does_not_hide_inner_binding_tamper(self):
        r = self.compile()
        r["payload"]["selection_binding_sha256"] = "1" * 64
        r["receipt_sha256"] = gate._digest(r["payload"])
        self.assertFalse(gate.verify_receipt(r))

    def test_recomputed_outer_digest_does_not_hide_winner_request_tamper(self):
        r = self.compile()
        r["payload"]["winner_request_id"] = "req-99999999"
        r["receipt_sha256"] = gate._digest(r["payload"])
        self.assertFalse(gate.verify_receipt(r))

    def test_selected_receipt_cannot_bind_other_request(self):
        r = self.compile()
        other = request(candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b"), rid="req-00000002")
        self.assertFalse(gate.verify_selected_binding(other, r))

    def test_lease_claimant_must_equal_worker(self):
        c = candidate(); c["lease_binding"]["claimant"] = "Z-OTHER"
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_candidate(c)


    def test_lease_binding_ref_must_match_seam(self):
        c = candidate(); c["lease_binding"]["lease_ref"] = "refs/heads/outbound-lease-v3/" + "9" * 64
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_candidate(c)

    def test_extract_binding_from_actual_v3_receipt_shape(self):
        c = candidate()
        b = c["lease_binding"]
        receipt = {
            "schema": gate.LEASE_RECEIPT_SCHEMA,
            "claimant": b["claimant"],
            "claim_id": b["claim_id"],
            "seam_sha256": b["seam_sha256"],
            "lease_ref": b["lease_ref"],
            "lease_commit_sha": b["lease_commit_sha"],
            "claim_capability_sha256": b["claim_capability_sha256"],
            "receipt_sha256": b["receipt_sha256"],
            "other_authenticated_v3_fields": "preserved-in-full-receipt-but-not-copied",
        }
        self.assertEqual(gate.lease_binding_from_v3_receipt(receipt), b)

    def test_unknown_candidate_field_rejected(self):
        c = candidate(); c["mystery"] = True
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_candidate(c)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.parse_json_bytes(b'{"a":1,"a":2}', "x")

    def test_conflicting_same_slack_timestamp_rejected(self):
        req = request()
        s = snap([
            msg(sts(5), SENDER, req["message"]),
            msg(sts(5), MUSE, selected_text(req)),
        ])
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_snapshot(s)

    def test_noncanonical_slack_timestamp_rejected(self):
        req = request()
        s = snap([msg("short.1", SENDER, req["message"])])
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_snapshot(s)

    def test_request_artifact_route_tamper_rejected(self):
        req = request()
        req["payload"]["muse_user_id"] = OTHER
        req["request_sha256"] = gate._digest(req["payload"])
        with self.assertRaises(gate.MuseElectionV2Error):
            gate._validate_request(req)

    def test_request_text_tamper_rejected(self):
        req = request(); req["message"] += "\nextra"
        with self.assertRaises(gate.MuseElectionV2Error):
            gate._validate_request(req)

    def test_unrelated_publication_decision_is_ignored(self):
        mine = request()
        other_c = candidate(); other_c["recipient_fingerprint"] = "8" * 64
        other = request(other_c, rid="req-00000002")
        s = snap([msg(sts(5), SENDER, mine["message"]), msg(sts(15), MUSE, selected_text(other))])
        r = self.compile(mine, s)
        self.assertIn("NO_MUSE_DECISION", r["payload"]["reasons"])

    def test_cli_selected_exit_zero(self):
        req = request()
        s = happy(req)
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "request.json")
            sp = os.path.join(td, "snapshot.json")
            with open(rp, "w", encoding="utf-8") as f: json.dump(req, f)
            with open(sp, "w", encoding="utf-8") as f: json.dump(s, f)
            proc = subprocess.run([
                sys.executable, "-m", "tools.outbound_send_guard.muse_election_v2", "compile",
                "--request", rp, "--snapshot", sp, "--observed-at", OBSERVED, "--ledger-complete",
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            out = json.loads(proc.stdout)
            self.assertEqual(out["payload"]["decision"], "SELECTED")


if __name__ == "__main__":
    unittest.main()
