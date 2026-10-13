import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from socketserver import TCPServer

from civic_ledger.core import ContractError, DocumentSnapshot, Ledger, compile_ledger, read_workspace, verify_bundle, write_bundle, write_workspace
from civic_ledger.server import Handler

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
AS_OF = "2026-09-13T16:30:00Z"


def snap(doc_id, kind, text, observed="2026-09-12T16:00:00Z", meeting="riverton-2026-09-12"):
    return DocumentSnapshot.create(meeting_id=meeting, doc_id=doc_id, kind=kind, source_url=f"https://civic.example/{doc_id}.html", observed_at=observed, text=text)


class LedgerTests(unittest.TestCase):
    def sample(self):
        l = Ledger("riverton-2026-09-12")
        l.add(snap("agenda-v1", "agenda", (FIX / "sample_agenda.txt").read_text(), "2026-09-09T14:00:00Z"))
        l.add(snap("addendum-v1", "addendum", (FIX / "sample_addendum.txt").read_text(), "2026-09-10T14:00:00Z"))
        l.add(snap("minutes-v1", "minutes", (FIX / "sample_minutes.txt").read_text(), "2026-09-12T20:00:00Z"))
        return l

    def test_compile_decisions_and_latest_source_backed_fields(self):
        c = compile_ledger(self.sample(), as_of=AS_OF)
        by = {x["item_id"]: x for x in c["items"]}
        self.assertEqual(by["4.2"]["state"], "DECIDED_APPROVED")
        self.assertEqual(by["4.2"]["owner"], "Public Works & Accessibility Office")
        self.assertEqual(by["4.2"]["deadline"], "2026-10-22")
        self.assertEqual(by["7.1"]["state"], "DECIDED_CONTINUED")
        self.assertEqual(by["9.3"]["state"], "DECIDED_DENIED")
        self.assertFalse(c["authority"]["external_actions_authorized"])

    def test_change_history_retains_old_and_new_values(self):
        c = compile_ledger(self.sample(), as_of=AS_OF)
        item = next(x for x in c["items"] if x["item_id"] == "4.2")
        owners = [x["value"] for x in item["changes"] if x["field"] == "owner"]
        self.assertEqual(owners, ["Public Works", "Public Works & Accessibility Office"])
        deadlines = [x["value"] for x in item["changes"] if x["field"] == "deadline"]
        self.assertEqual(deadlines, ["2026-10-15", "2026-10-22"])

    def test_agenda_only_remains_proposed(self):
        l = Ledger("m")
        l.add(snap("a", "agenda", "[ITEM X] Thing\nOwner: Team\n", meeting="m"))
        self.assertEqual(compile_ledger(l, as_of=AS_OF)["items"][0]["state"], "PROPOSED")

    def test_minutes_without_decision_is_unknown_not_inferred(self):
        l = Ledger("m")
        l.add(snap("a", "agenda", "[ITEM X] Thing\n", meeting="m"))
        l.add(snap("m", "minutes", "[ITEM X] Thing\nAction: Discussed at length.\n", meeting="m"))
        item = compile_ledger(l, as_of=AS_OF)["items"][0]
        self.assertEqual(item["state"], "UNKNOWN_DECISION")
        self.assertIsNone(item["decision"])

    def test_conflicting_minute_decisions_hold(self):
        l = Ledger("m")
        l.add(snap("m1", "minutes", "[ITEM X] Thing\nDecision: APPROVED\n", "2026-09-11T00:00:00Z", "m"))
        l.add(snap("m2", "minutes", "[ITEM X] Thing\nDecision: DENIED\n", "2026-09-12T00:00:00Z", "m"))
        item = compile_ledger(l, as_of=AS_OF)["items"][0]
        self.assertEqual(item["state"], "HOLD_CONFLICT")
        self.assertTrue(item["conflict"])
        self.assertIsNone(item["decision"])

    def test_exact_replay_idempotent_changed_replay_rejected(self):
        l = Ledger("m")
        a = snap("a", "agenda", "[ITEM X] Thing\n", meeting="m")
        self.assertTrue(l.add(a))
        self.assertFalse(l.add(a))
        with self.assertRaisesRegex(ContractError, "replay changed"):
            l.add(snap("a", "agenda", "[ITEM X] Different\n", meeting="m"))

    def test_snapshot_digest_tamper_rejected(self):
        d = snap("a", "agenda", "[ITEM X] Thing\n", meeting="m").to_dict()
        d["text"] += "tamper"
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            DocumentSnapshot.from_dict(d)

    def test_rejects_non_http_credentialed_or_future_source(self):
        with self.assertRaises(ContractError):
            DocumentSnapshot.create(meeting_id="m", doc_id="a", kind="agenda", source_url="file:///x", observed_at="2026-09-12T00:00:00Z", text="x")
        with self.assertRaises(ContractError):
            DocumentSnapshot.create(meeting_id="m", doc_id="a", kind="agenda", source_url="https://user:pass@example.com/x", observed_at="2026-09-12T00:00:00Z", text="x")
        l = Ledger("m")
        l.add(snap("a", "agenda", "[ITEM X] Thing\n", "2026-09-14T00:00:00Z", "m"))
        with self.assertRaisesRegex(ContractError, "future snapshot"):
            compile_ledger(l, as_of=AS_OF)

    def test_stale_source_visible(self):
        l = Ledger("m")
        l.add(snap("a", "agenda", "[ITEM X] Thing\n", "2025-01-01T00:00:00Z", "m"))
        self.assertEqual(compile_ledger(l, as_of=AS_OF, max_source_age_days=30)["freshness"], "STALE_SOURCE")

    def test_unsupported_decision_and_bad_deadline_fail(self):
        l = Ledger("m")
        l.add(snap("m", "minutes", "[ITEM X] Thing\nDecision: MAYBE\n", meeting="m"))
        with self.assertRaisesRegex(ContractError, "unsupported decision"):
            compile_ledger(l, as_of=AS_OF)
        l2 = Ledger("m")
        l2.add(snap("a", "agenda", "[ITEM X] Thing\nDeadline: 2026-02-31\n", meeting="m"))
        with self.assertRaisesRegex(ContractError, "invalid deadline"):
            compile_ledger(l2, as_of=AS_OF)

    def test_duplicate_field_or_item_fails(self):
        l = Ledger("m")
        l.add(snap("a", "agenda", "[ITEM X] Thing\nOwner: A\nOwner: B\n", meeting="m"))
        with self.assertRaisesRegex(ContractError, "duplicate field"):
            compile_ledger(l, as_of=AS_OF)
        l2 = Ledger("m")
        l2.add(snap("a", "agenda", "[ITEM X] Thing\n[ITEM X] Again\n", meeting="m"))
        with self.assertRaisesRegex(ContractError, "duplicate item id"):
            compile_ledger(l2, as_of=AS_OF)

    def test_line_anchor_hash_is_exact(self):
        c = compile_ledger(self.sample(), as_of=AS_OF)
        ev = c["items"][0]["title_evidence"]
        source = next(s for s in self.sample().snapshots if s.doc_id == ev["doc_id"])
        line = source.text.splitlines()[ev["line"] - 1]
        import hashlib
        self.assertEqual(ev["line_sha256"], hashlib.sha256(line.encode()).hexdigest())

    def test_workspace_roundtrip_and_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "work.json"
            write_workspace(self.sample(), p)
            loaded = read_workspace(p)
            self.assertEqual(loaded.to_dict(), self.sample().to_dict())
            p.write_text('{"schema":"civic-action-ledger/v1","meeting_id":"m","meeting_id":"x","snapshots":[]}')
            with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
                read_workspace(p)

    def test_bundle_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            compiled = compile_ledger(self.sample(), as_of=AS_OF)
            manifest = write_bundle(compiled, td)
            self.assertEqual(set(manifest["files"]), {"ledger.json", "ledger.csv", "ledger.md"})
            self.assertTrue(verify_bundle(td)["ok"])
            with open(Path(td) / "ledger.csv", "ab") as fh:
                fh.write(b"tamper")
            with self.assertRaisesRegex(ContractError, "digest mismatch"):
                verify_bundle(td)

    def test_compiled_digest_tamper_blocks_bundle(self):
        c = compile_ledger(self.sample(), as_of=AS_OF)
        c["freshness"] = "CURRENT_BUT_TAMPERED"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ContractError, "compiled digest mismatch"):
                write_bundle(c, td)

    def test_server_search_and_html_escape(self):
        with tempfile.TemporaryDirectory() as td:
            c = compile_ledger(self.sample(), as_of=AS_OF)
            c["items"][0]["title"] = "<script>alert(1)</script>"
            p = Path(td) / "ledger.json"
            p.write_text(json.dumps(c))
            handler = type("TestHandler", (Handler,), {"ledger_path": p})
            srv = TCPServer(("127.0.0.1", 0), handler)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=3)
                conn.request("GET", "/?q=4.2")
                r = conn.getresponse(); body = r.read().decode(); self.assertEqual(r.status, 200)
                self.assertNotIn("<script>alert(1)</script>", body)
                self.assertIn("&lt;script&gt;", body)
                conn.request("GET", "/api/search?q=Library&state=DECIDED_CONTINUED")
                r = conn.getresponse(); obj = json.loads(r.read()); self.assertEqual(obj["count"], 1)
            finally:
                srv.shutdown(); srv.server_close(); t.join(2)

    def test_server_api_does_not_authorize_actions(self):
        with tempfile.TemporaryDirectory() as td:
            c = compile_ledger(self.sample(), as_of=AS_OF)
            p = Path(td) / "ledger.json"; p.write_text(json.dumps(c))
            handler = type("TestHandler", (Handler,), {"ledger_path": p})
            srv = TCPServer(("127.0.0.1", 0), handler); t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=3)
                conn.request("GET", "/api/ledger"); r = conn.getresponse(); obj = json.loads(r.read())
                self.assertFalse(obj["authority"]["external_actions_authorized"])
            finally:
                srv.shutdown(); srv.server_close(); t.join(2)

    def test_bundle_symlink_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        with tempfile.TemporaryDirectory() as td:
            write_bundle(compile_ledger(self.sample(), as_of=AS_OF), td)
            p = Path(td) / "ledger.md"; copy = Path(td) / "copy.md"; copy.write_bytes(p.read_bytes()); p.unlink(); os.symlink(copy, p)
            with self.assertRaisesRegex(ContractError, "unavailable"):
                verify_bundle(td)


if __name__ == "__main__":
    unittest.main()
