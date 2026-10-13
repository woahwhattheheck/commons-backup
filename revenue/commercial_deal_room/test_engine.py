from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone

from .acceptance import A, D, E, P, R, accepted_path, add, base_packet, offer_sent, acceptance_summary
from .engine import ContractError, canonical_json, compile_board, verify_board

NOW = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)


class DealRoomTests(unittest.TestCase):
    def test_offer_ready(self):
        self.assertEqual(compile_board(base_packet("x"), now=NOW)["next_action"], "OWNER_SEND_REVIEW")

    def test_send_is_not_acceptance(self):
        p = base_packet("x"); offer_sent(p)
        b = compile_board(p, now=NOW)
        self.assertEqual(b["stage"], "AWAITING_BUYER")
        self.assertFalse(b["evidence"]["buyer_acceptance_event_present"])

    def test_interest_moves_to_scope(self):
        p = base_packet("x"); offer_sent(p)
        add(p,"interest","BUYER_INTEREST","2026-09-13T12:20:00Z",{"provider":"gmail","provider_message_id":"m-int","reply_to_event_id":"send-1"})
        self.assertEqual(compile_board(p, now=NOW)["next_action"], "PREPARE_SCOPE")

    def test_payment_road_is_not_payment(self):
        p = accepted_path("x")
        add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R})
        b = compile_board(p, now=NOW)
        self.assertEqual(b["stage"], "PAYMENT_ROAD_READY")
        self.assertEqual(b["net_settled_minor"], 0)

    def test_full_happy_path_closes(self):
        p = accepted_path("x")
        add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R})
        add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"artifact","FULFILLMENT_ARTIFACT","2026-09-13T13:10:00Z",{"artifact_id":"a1","artifact_sha256":A})
        add(p,"delivery","FULFILLMENT_SENT","2026-09-13T13:20:00Z",{"provider":"gmail","provider_message_id":"m-del","artifact_event_id":"artifact"})
        add(p,"fa","BUYER_FULFILLMENT_ACCEPTED","2026-09-13T13:30:00Z",{"provider":"gmail","provider_message_id":"m-fa","reply_to_event_id":"delivery","artifact_event_id":"artifact"})
        b = compile_board(p, now=NOW)
        self.assertEqual(b["stage"], "CLOSED_SETTLED")
        self.assertFalse(b["authority_ceiling"]["recognized_revenue_authorized"])

    def test_exact_replay_collapses(self):
        p = base_packet("x"); offer_sent(p); p["events"].append(copy.deepcopy(p["events"][0]))
        b = compile_board(p, now=NOW)
        self.assertEqual(b["replay_collapses"], 1)
        self.assertEqual(b["stage"], "AWAITING_BUYER")

    def test_changed_same_id_holds(self):
        p = base_packet("x"); offer_sent(p); altered=copy.deepcopy(p["events"][0]); altered["source_sha256"]="9"*64; p["events"].append(altered)
        self.assertIn("EVENT_ID_CONFLICT", compile_board(p, now=NOW)["reasons"])

    def test_duplicate_offer_send_holds(self):
        p=base_packet("x"); offer_sent(p); add(p,"send-2","OFFER_SENT","2026-09-13T12:11:00Z",{"provider":"gmail","provider_message_id":"m2","scope_sha256":D,"terms_sha256":E})
        self.assertIn("DUPLICATE_OFFER_SEND", compile_board(p, now=NOW)["reasons"])

    def test_cross_deal_transplant_rejected(self):
        p=base_packet("x"); offer_sent(p); p["events"][0]["buyer_id"]="buyer-other"
        with self.assertRaises(ContractError): compile_board(p, now=NOW)

    def test_acceptance_must_bind_latest_proposal(self):
        p=accepted_path("x"); p["events"][-1]["payload"]["accepted_proposal_sha256"]="8"*64
        self.assertIn("BUYER_ACCEPTANCE_BINDING_MISMATCH", compile_board(p, now=NOW)["reasons"])


    def test_acceptance_must_reply_to_latest_proposal(self):
        p=accepted_path("x")
        p["events"][-1]["payload"]["reply_to_event_id"]="send-1"
        self.assertIn("BUYER_ACCEPTANCE_REFERENCE_NOT_LATEST_PROPOSAL", compile_board(p, now=NOW)["reasons"])

    def test_duplicate_business_reversal_id_not_double_counted(self):
        p=accepted_path("x")
        add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R})
        add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"reverse-a","SETTLEMENT_REVERSED","2026-09-13T13:05:00Z",{"settlement_id":"s1","reversal_id":"rev1","currency":"USD","amount_minor":50000})
        add(p,"reverse-b","SETTLEMENT_REVERSED","2026-09-13T13:05:00Z",{"settlement_id":"s1","reversal_id":"rev1","currency":"USD","amount_minor":50000})
        b=compile_board(p, now=NOW)
        self.assertEqual(b["reversed_minor"],50000)
        self.assertEqual(b["net_settled_minor"],200000)

    def test_changed_duplicate_business_reversal_id_holds(self):
        p=accepted_path("x")
        add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R})
        add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000})
        add(p,"reverse-a","SETTLEMENT_REVERSED","2026-09-13T13:05:00Z",{"settlement_id":"s1","reversal_id":"rev1","currency":"USD","amount_minor":50000})
        add(p,"reverse-b","SETTLEMENT_REVERSED","2026-09-13T13:06:00Z",{"settlement_id":"s1","reversal_id":"rev1","currency":"USD","amount_minor":60000})
        self.assertIn("REVERSAL_ID_CONFLICT", compile_board(p, now=NOW)["reasons"])

    def test_dnr_stays_closed_without_new_buyer_event(self):
        p=base_packet("x"); offer_sent(p); add(p,"dnr","DNR","2026-09-13T12:20:00Z",{"reason_code":"buyer-no"})
        self.assertEqual(compile_board(p, now=NOW)["stage"], "DNR")

    def test_dnr_can_reopen_only_with_later_buyer_event(self):
        p=base_packet("x"); offer_sent(p); add(p,"dnr","DNR","2026-09-13T12:20:00Z",{"reason_code":"buyer-no"})
        add(p,"interest","BUYER_INTEREST","2026-09-13T12:21:00Z",{"provider":"gmail","provider_message_id":"m-int","reply_to_event_id":"send-1"})
        self.assertEqual(compile_board(p, now=NOW)["stage"], "BUYER_INTEREST")

    def test_settlement_requires_payment_request(self):
        p=accepted_path("x"); add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R}); add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000})
        self.assertIn("SETTLEMENT_BEFORE_PAYMENT_REQUEST", compile_board(p, now=NOW)["reasons"])

    def test_reversal_demotes_funding(self):
        p=accepted_path("x"); add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R}); add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"reverse","SETTLEMENT_REVERSED","2026-09-13T13:05:00Z",{"settlement_id":"s1","reversal_id":"rev1","currency":"USD","amount_minor":250000})
        b=compile_board(p, now=NOW); self.assertEqual(b["net_settled_minor"],0); self.assertEqual(b["stage"],"AWAITING_SETTLEMENT")

    def test_over_settlement_holds(self):
        p=accepted_path("x"); add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R}); add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250001})
        self.assertIn("OVERSETTLEMENT_REQUIRES_RECONCILIATION",compile_board(p, now=NOW)["reasons"])

    def test_fulfillment_artifact_does_not_mean_delivered(self):
        p=accepted_path("x"); add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R}); add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"settle","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"artifact","FULFILLMENT_ARTIFACT","2026-09-13T13:10:00Z",{"artifact_id":"a1","artifact_sha256":A})
        self.assertEqual(compile_board(p, now=NOW)["stage"],"FULFILLMENT_READY")

    def test_fulfillment_send_before_required_settlement_holds(self):
        p=accepted_path("x"); add(p,"road","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"r1","route_sha256":R}); add(p,"request","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay","route_id":"r1","currency":"USD","amount_minor":250000}); add(p,"artifact","FULFILLMENT_ARTIFACT","2026-09-13T13:10:00Z",{"artifact_id":"a1","artifact_sha256":A}); add(p,"delivery","FULFILLMENT_SENT","2026-09-13T13:20:00Z",{"provider":"gmail","provider_message_id":"m-del","artifact_event_id":"artifact"})
        self.assertIn("FULFILLMENT_SENT_BEFORE_REQUIRED_SETTLEMENT",compile_board(p, now=NOW)["reasons"])

    def test_future_event_holds(self):
        p=base_packet("x"); add(p,"send-1","OFFER_SENT","2026-09-14T12:10:00Z",{"provider":"gmail","provider_message_id":"m1","scope_sha256":D,"terms_sha256":E})
        self.assertIn("FUTURE_EVENT",compile_board(p, now=NOW)["reasons"])

    def test_expiration_is_current_time_gate(self):
        p=base_packet("x"); offer_sent(p); p["offer"]["expires_at"]="2026-09-13T15:00:00Z"
        self.assertIn("OFFER_EXPIRED", compile_board(p, now=NOW)["reasons"])

    def test_acceptance_prevents_offer_expiry_hold(self):
        p=accepted_path("x"); p["offer"]["expires_at"]="2026-09-13T15:00:00Z"
        # acceptance was 12:40; current time 16:00. Accepted commercial state remains valid.
        self.assertNotIn("OFFER_EXPIRED", compile_board(p, now=NOW)["reasons"])

    def test_verify_detects_board_tamper(self):
        p=base_packet("x"); board=compile_board(p,now=NOW); self.assertTrue(verify_board(p,board,now=NOW)["historical_valid"]); board=copy.deepcopy(board); board["stage"]="CLOSED_SETTLED"; self.assertFalse(verify_board(p,board,now=NOW)["historical_valid"])

    def test_provider_message_reuse_conflict_holds(self):
        p=base_packet("x"); offer_sent(p); add(p,"interest","BUYER_INTEREST","2026-09-13T12:20:00Z",{"provider":"gmail","provider_message_id":"m-send-1","reply_to_event_id":"send-1"})
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT",compile_board(p,now=NOW)["reasons"])

    def test_order_invariant(self):
        p=accepted_path("x"); b1=compile_board(p,now=NOW); p["events"]=list(reversed(p["events"])); b2=compile_board(p,now=NOW); self.assertEqual(b1,b2)

    def test_authority_ceiling_always_false(self):
        p=accepted_path("x"); b=compile_board(p,now=NOW); self.assertTrue(all(v is False for v in b["authority_ceiling"].values()))

    def test_acceptance_fixture(self):
        s=acceptance_summary(); self.assertEqual(s["count"],12); self.assertEqual(s["stages"]["HOLD"],1); self.assertEqual(s["stages"]["DNR"],1)


if __name__ == "__main__":
    unittest.main()
