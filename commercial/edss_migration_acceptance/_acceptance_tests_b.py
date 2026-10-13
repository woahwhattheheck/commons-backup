from ._test_base import *

class AcceptanceTestsB(AcceptanceTestBase):
    def test_ack_before_receive_holds(self):
        p = ready_packet(); p["interface_events"][0]["acknowledgements"][0]["ack_at"] = "2026-09-13T16:01:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_receive_before_event_holds(self):
        p = ready_packet(); p["interface_events"][0]["received_at"] = "2026-09-13T16:01:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_unexpected_logical_record(self):
        p = ready_packet(); e = p["interface_events"][0]; e["logical_record_id"] = "rec.999"
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["UNEXPECTED_LOGICAL_RECORD"], 1)

    def test_cutover_start_inclusive(self):
        p = ready_packet(); p["expectation"]["expected_events"][0]["event_at"] = "2026-09-13T16:00:00Z"; refresh_expected_events(p); p["interface_events"][0]["event_at"] = "2026-09-13T16:00:00Z"
        self.assertEqual(self.compile(p)["state"], ACCEPTANCE_READY)

    def test_cutover_end_exclusive(self):
        p = ready_packet(); p["expectation"]["expected_events"][0]["event_at"] = "2026-09-13T16:30:00Z"; refresh_expected_events(p); p["interface_events"][0]["event_at"] = "2026-09-13T16:30:00Z"; p["interface_events"][0]["received_at"] = "2026-09-13T16:31:00Z"; p["interface_events"][0]["acknowledgements"][0]["ack_at"] = "2026-09-13T16:31:00Z"
        r = self.compile(p); self.assertEqual(r["state"], INTERFACE_MISMATCH); self.assertEqual(r["interface_counts"]["OUTSIDE_CUTOVER"], 1)

    def test_stale_event(self):
        p = ready_packet(); policy = deepcopy(DEFAULT_POLICY); policy["max_event_age_seconds"] = 60
        self.assertEqual(self.compile(p, policy=policy)["state"], EVIDENCE_STALE)

    def test_row_order_invariance(self):
        p = ready_packet(); a = self.compile(p); p["source_snapshot"]["rows"].reverse(); p["target_snapshot"]["rows"].reverse(); refresh_snapshot(p, "SOURCE"); refresh_snapshot(p, "TARGET")
        b = self.compile(p); self.assertEqual(a["packet_sha256"], b["packet_sha256"])

    def test_field_order_digest_invariance(self):
        p = ready_packet(); a = rows_digest(p["source_snapshot"]["rows"]); p["source_snapshot"]["rows"][0]["fields"].reverse(); b = rows_digest(p["source_snapshot"]["rows"]); self.assertEqual(a, b)

    def test_event_order_invariance(self):
        p = ready_packet(); a = self.compile(p); p["interface_events"].reverse(); p["expectation"]["expected_events"].reverse(); refresh_expected_events(p)
        b = self.compile(p); self.assertEqual(a["packet_sha256"], b["packet_sha256"])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(EdssAcceptanceError): load_json_strict('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(EdssAcceptanceError): load_json_strict('{"a":NaN}')

    def test_bool_sequence_rejected(self):
        p = ready_packet(); p["interface_events"][0]["source_sequence"] = True
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_bool_record_count_rejected(self):
        p = ready_packet(); p["source_snapshot"]["record_count"] = True
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_malformed_hash_rejected(self):
        p = ready_packet(); p["source_snapshot"]["rows"][0]["fields"][0]["value_sha256"] = "abc"; refresh_snapshot(p, "SOURCE")
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_noncanonical_timestamp_rejected(self):
        p = ready_packet(); p["target_snapshot"]["captured_at"] = "2026-09-13T12:30:00-04:00"
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_direct_email_in_id_rejected(self):
        p = ready_packet(); p["engagement_ref"] = "person@example.com"
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_phone_in_id_rejected(self):
        p = ready_packet(); p["engagement_ref"] = "555-123-4567"
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_raw_health_payload_key_rejected(self):
        p = ready_packet(); p["source_snapshot"]["rows"][0]["patient_name"] = "Synthetic Person"
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_unknown_top_level_rejected(self):
        p = ready_packet(); p["clinical_payload"] = {"x": "y"}
        with self.assertRaises(EdssAcceptanceError): self.compile(p)

    def test_changed_source_bytes_same_snapshot_breaks_receipt(self):
        p = ready_packet(); receipt = self.compile(p)
        q = deepcopy(p); q["source_snapshot"]["rows"][0]["fields"][0]["value_sha256"] = h("changed"); refresh_snapshot(q, "SOURCE")
        with self.assertRaises(EdssAcceptanceError): verify_receipt(q, receipt)

    def test_receipt_tamper_fails(self):
        p = ready_packet(); receipt = self.compile(p); receipt["state"] = HOLD
        with self.assertRaises(EdssAcceptanceError): verify_receipt(p, receipt)

    def test_policy_drift_fails(self):
        p = ready_packet(); receipt = self.compile(p); policy = deepcopy(DEFAULT_POLICY); policy["max_snapshot_age_seconds"] += 1
        with self.assertRaises(EdssAcceptanceError): verify_receipt(p, receipt, policy=policy)

    def test_cli_compile_verify_and_overwrite_refusal(self):
        p = ready_packet()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); inp = td / "packet.json"; jout = td / "receipt.json"; mout = td / "receipt.md"
            inp.write_bytes(canonical_json_bytes(p))
            env = dict(os.environ); env["PYTHONPATH"] = os.getcwd()
            cmd = [sys.executable, "-m", "commercial.edss_migration_acceptance.cli", "compile", "--input", str(inp), "--json-out", str(jout), "--md-out", str(mout)]
            run = subprocess.run(cmd, cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr); self.assertIn(run.stdout.strip(), {ACCEPTANCE_READY, EVIDENCE_STALE})
            second = subprocess.run(cmd, cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(second.returncode, 2)
            verify = subprocess.run([sys.executable, "-m", "commercial.edss_migration_acceptance.cli", "verify", "--input", str(inp), "--receipt", str(jout)], cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(verify.returncode, 0, verify.stderr); self.assertIn("VERIFIED", verify.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_cli_symlink_output_refusal(self):
        p = ready_packet()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); inp = td / "packet.json"; real = td / "real.json"; link = td / "receipt.json"; md = td / "receipt.md"
            inp.write_bytes(canonical_json_bytes(p)); real.write_text("sentinel"); os.symlink(real, link)
            env = dict(os.environ); env["PYTHONPATH"] = os.getcwd()
            run = subprocess.run([sys.executable, "-m", "commercial.edss_migration_acceptance.cli", "compile", "--input", str(inp), "--json-out", str(link), "--md-out", str(md)], cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 2); self.assertEqual(real.read_text(), "sentinel")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_cli_symlink_input_refusal(self):
        p = ready_packet()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); real = td / "real.json"; link = td / "packet.json"; jout = td / "receipt.json"; md = td / "receipt.md"
            real.write_bytes(canonical_json_bytes(p)); os.symlink(real, link)
            env = dict(os.environ); env["PYTHONPATH"] = os.getcwd()
            run = subprocess.run([sys.executable, "-m", "commercial.edss_migration_acceptance.cli", "compile", "--input", str(link), "--json-out", str(jout), "--md-out", str(md)], cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 2); self.assertFalse(jout.exists())
