from ._test_base import *

class AcceptanceTestsA(AcceptanceTestBase):
    def test_ready(self):
        packet = ready_packet()
        receipt = self.compile(packet)
        self.assertEqual(receipt["state"], ACCEPTANCE_READY)
        self.assertEqual(receipt["record_counts"], {"PARITY_OK": 3})
        self.assertEqual(receipt["interface_counts"], {"INTERFACE_OK": 3})
        self.assertFalse(receipt["authority"]["production_access"])
        self.assertFalse(receipt["authority"]["protocol_certification"])
        self.assertTrue(verify_receipt(packet, receipt))

    def test_fixture_ready(self):
        path = Path("commercial/edss_migration_acceptance/fixtures/synthetic_ready.json")
        packet = load_json_strict(path.read_bytes())
        self.assertEqual(self.compile(packet)["state"], ACCEPTANCE_READY)

    def test_fixed_fixture_receipt_verifies(self):
        packet = load_json_strict(Path("commercial/edss_migration_acceptance/fixtures/synthetic_ready.json").read_bytes())
        receipt = load_json_strict(Path("commercial/edss_migration_acceptance/fixtures/synthetic_ready_receipt.json").read_bytes())
        self.assertTrue(verify_receipt(packet, receipt))

    def test_deterministic_json_markdown(self):
        a = self.compile()
        b = self.compile(deepcopy(ready_packet()))
        self.assertEqual(canonical_json_bytes(a), canonical_json_bytes(b))
        self.assertEqual(render_markdown(a), render_markdown(b))

    def test_missing_target(self):
        p = ready_packet(); p["target_snapshot"]["rows"] = p["target_snapshot"]["rows"][:-1]; refresh_snapshot(p, "TARGET")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["MISSING_TARGET"], 1)

    def test_unexpected_target(self):
        p = ready_packet(); p["target_snapshot"]["rows"].append(row("rec.999", status="open")); refresh_snapshot(p, "TARGET")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["UNEXPECTED_RECORD"], 1)

    def test_field_mismatch(self):
        p = ready_packet(); p["target_snapshot"]["rows"][0]["fields"][0]["value_sha256"] = h("different"); refresh_snapshot(p, "TARGET")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["FIELD_MISMATCH"], 1)

    def test_duplicate_source_same_bytes(self):
        p = ready_packet(); p["source_snapshot"]["rows"].append(deepcopy(p["source_snapshot"]["rows"][0])); refresh_snapshot(p, "SOURCE")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["DUPLICATE_SOURCE"], 1)

    def test_conflicting_source_duplicate(self):
        p = ready_packet(); dup = deepcopy(p["source_snapshot"]["rows"][0]); dup["fields"][0]["value_sha256"] = h("conflict"); p["source_snapshot"]["rows"].append(dup); refresh_snapshot(p, "SOURCE")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["CONFLICT_SOURCE"], 1)

    def test_duplicate_target_same_bytes(self):
        p = ready_packet(); p["target_snapshot"]["rows"].append(deepcopy(p["target_snapshot"]["rows"][0])); refresh_snapshot(p, "TARGET")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["DUPLICATE_TARGET"], 1)

    def test_conflicting_target_duplicate(self):
        p = ready_packet(); dup = deepcopy(p["target_snapshot"]["rows"][0]); dup["fields"][0]["value_sha256"] = h("conflict"); p["target_snapshot"]["rows"].append(dup); refresh_snapshot(p, "TARGET")
        r = self.compile(p); self.assertEqual(r["state"], MIGRATION_MISMATCH); self.assertEqual(r["record_counts"]["CONFLICT_TARGET"], 1)

    def test_incomplete_source(self):
        p = ready_packet(); p["source_snapshot"]["complete_export"] = False
        self.assertEqual(self.compile(p)["state"], EVIDENCE_INCOMPLETE)

    def test_incomplete_target(self):
        p = ready_packet(); p["target_snapshot"]["complete_export"] = False
        self.assertEqual(self.compile(p)["state"], EVIDENCE_INCOMPLETE)

    def test_stale_source(self):
        p = ready_packet(); p["source_snapshot"]["captured_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(self.compile(p)["state"], EVIDENCE_STALE)

    def test_stale_source_and_target(self):
        p = ready_packet(); p["source_snapshot"]["captured_at"] = "2026-09-01T00:00:00Z"; p["target_snapshot"]["captured_at"] = "2026-09-01T00:01:00Z"
        self.assertEqual(self.compile(p)["state"], EVIDENCE_STALE)

    def test_stale_expectation(self):
        p = ready_packet(); p["expectation"]["captured_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(self.compile(p)["state"], EVIDENCE_STALE)

    def test_future_snapshot_holds(self):
        p = ready_packet(); p["target_snapshot"]["captured_at"] = "2026-09-13T16:41:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_target_snapshot_cannot_predate_source(self):
        p = ready_packet(); p["target_snapshot"]["captured_at"] = "2026-09-13T16:19:59Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_expectation_snapshot_id_binding(self):
        p = ready_packet(); p["expectation"]["source_snapshot_id"] = "snap.other"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_expectation_source_digest_binding(self):
        p = ready_packet(); p["expectation"]["source_rows_sha256"] = "f" * 64
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_expected_record_set_must_equal_unique_source(self):
        p = ready_packet(); p["expectation"]["expected_record_ids"] = p["expectation"]["expected_record_ids"][:-1]; p["expectation"]["expected_record_ids_sha256"] = expected_record_ids_digest(p["expectation"]["expected_record_ids"])
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_missing_event(self):
        p = ready_packet(); p["interface_events"] = p["interface_events"][:-1]
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["MISSING_EVENT"], 1)

    def test_unexpected_event(self):
        p = ready_packet(); e = deepcopy(p["interface_events"][0]); e["message_id"] = "msg.unexpected"; e["acknowledgements"][0]["ack_id"] = "ack.unexpected"; p["interface_events"].append(e)
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["UNEXPECTED_EVENT"], 1)

    def test_replay_duplicate(self):
        p = ready_packet(); p["interface_events"].append(deepcopy(p["interface_events"][0]))
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["REPLAY_DUPLICATE"], 2)

    def test_message_id_conflict(self):
        p = ready_packet(); e = deepcopy(p["interface_events"][0]); e["payload_sha256"] = h("conflicting-payload"); p["interface_events"].append(e)
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["MESSAGE_ID_CONFLICT"], 2)

    def test_out_of_order(self):
        p = ready_packet(); a, b = p["interface_events"][0], p["interface_events"][1]; a["received_at"], b["received_at"] = "2026-09-13T16:12:00Z", "2026-09-13T16:11:00Z"
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertGreaterEqual(r["interface_counts"].get("OUT_OF_ORDER", 0), 1)

    def test_missing_ack(self):
        p = ready_packet(); p["interface_events"][0]["acknowledgements"] = []
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["MISSING_ACK"], 1)

    def test_rejected_ack(self):
        p = ready_packet(); p["interface_events"][0]["acknowledgements"][0]["outcome"] = "REJECTED"
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["REJECTED"], 1)

    def test_duplicate_ack_id(self):
        p = ready_packet(); ack = deepcopy(p["interface_events"][0]["acknowledgements"][0]); p["interface_events"][0]["acknowledgements"].append(ack)
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["DUPLICATE_ACK_ID"], 1)

    def test_multiple_acks(self):
        p = ready_packet(); ack = deepcopy(p["interface_events"][0]["acknowledgements"][0]); ack["ack_id"] = "ack.second"; p["interface_events"][0]["acknowledgements"].append(ack)
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["MULTIPLE_ACKS"], 1)

    def test_equal_receive_time_same_interface_fails_closed(self):
        p = ready_packet()
        a, b = p["interface_events"][0], p["interface_events"][1]
        tied = "2026-09-13T16:11:00Z"
        a["received_at"] = tied; b["received_at"] = tied
        a["acknowledgements"][0]["ack_at"] = tied; b["acknowledgements"][0]["ack_at"] = tied
        p["interface_events"] = [b, a] + p["interface_events"][2:]
        r = self.compile(p)
        self.assertEqual(r["state"], INTERFACE_MISMATCH)
        self.assertGreaterEqual(r["interface_counts"].get("RECEIVE_TIME_AMBIGUOUS", 0), 2)

    def test_ack_id_reuse_across_messages_fails(self):
        p = ready_packet()
        p["interface_events"][1]["acknowledgements"][0]["ack_id"] = p["interface_events"][0]["acknowledgements"][0]["ack_id"]
        r = self.compile(p)
        self.assertEqual(r["state"], INTERFACE_MISMATCH)
        self.assertGreaterEqual(r["interface_counts"].get("DUPLICATE_ACK_ID", 0), 2)
