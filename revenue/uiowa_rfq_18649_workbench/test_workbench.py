from __future__ import annotations

import http.client
import json
import threading
import unittest
from pathlib import Path

import server


class StubAdapter:
    def inspect(self, candidate, authority):
        if candidate.get("reject"):
            raise server.WorkbenchError("stub compiler rejection")
        cells = []
        for group in ("ESS", "RIS", "IAM"):
            for dimension in ("software_development", "security", "deployment", "ai_readiness"):
                cells.append({
                    "group": group,
                    "dimension": dimension,
                    "status": "UNTRUSTED_EVIDENCE_CONSISTENT",
                    "maturity": None,
                    "confidence_bp": None,
                    "source_ids": [f"{group}-{dimension}"],
                    "source_record_sha256s": ["0" * 64],
                    "reason_codes": ["TRUSTED_AUTHORITY_ROOT_REQUIRED"],
                })
        return {
            "schema": "stub",
            "mode": "UNTRUSTED_INSPECTION",
            "receipt_sha256": "a" * 64,
            "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
            "trust": {
                "authority_root_supplied_out_of_band": False,
                "current_evidence_review_authority": False,
            },
            "commercial_terms": {"status": "PROPOSED_NOT_ACCEPTED"},
            "assessment_matrix": cells,
        }


class WorkbenchHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.create_server(port=0, adapter=StubAdapter(), static_root=Path(__file__).parent)
        cls.host, cls.port = cls.httpd.server_address[:2]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.thread.join(timeout=2)

    def request(self, method, path, *, body=None, headers=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=3)
        base = {"Host": f"127.0.0.1:{self.port}"}
        if headers:
            base.update(headers)
        conn.request(method, path, body=body, headers=base)
        res = conn.getresponse(); data = res.read(); conn.close()
        return res.status, dict(res.headers.items()), data

    def post_raw(self, raw: bytes, **extra_headers):
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Length": str(len(raw)),
            **extra_headers,
        }
        return self.request("POST", "/api/inspect", body=raw, headers=headers)

    def test_static_surface_and_no_path_serving(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"RFQ 18649", body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/../server.py")[0], 404)
        self.assertEqual(self.request("GET", "/api/inspect")[0], 404)

    def test_demo_query_loads_the_same_document_and_assets(self):
        for path in ("/?demo=1", "/index.html?demo=1"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn("text/html", headers["Content-Type"])
            self.assertIn(b"Assessment workspace", body)
        status, headers, body = self.request("GET", "/app.js?presentation=1")
        self.assertEqual(status, 200)
        self.assertIn(b"URLSearchParams", body)
        self.assertEqual(self.request("HEAD", "/?demo=1")[0], 200)

    def test_host_must_be_loopback(self):
        status, _, _ = self.request("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)

    def test_origin_content_type_and_size_are_fail_closed(self):
        raw = b'{"candidate":{},"authority":{}}'
        status, _, _ = self.request("POST", "/api/inspect", body=raw, headers={
            "Origin": "http://attacker.example",
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
        })
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/inspect", body=raw, headers={
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Type": "text/plain",
            "Content-Length": str(len(raw)),
        })
        self.assertEqual(status, 415)
        status, _, _ = self.request("POST", "/api/inspect", body=b"", headers={
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Type": "application/json",
            "Content-Length": str(server.MAX_BODY_BYTES + 1),
        })
        self.assertEqual(status, 413)

    def test_request_schema_forbids_trusted_root_escape(self):
        raw = json.dumps({"candidate": {}, "authority": {}, "trusted_authority_sha256": "0" * 64}).encode()
        status, _, body = self.post_raw(raw)
        self.assertEqual(status, 400)
        self.assertIn(b"keys must be exactly", body)

    def test_duplicate_json_key_rejected(self):
        status, _, body = self.post_raw(b'{"candidate":{},"candidate":{},"authority":{}}')
        self.assertEqual(status, 400)
        self.assertIn(b"duplicate JSON key", body)

    def test_inspection_returns_only_untrusted_mode(self):
        raw = json.dumps({"candidate": {"x": 1}, "authority": {"sources": []}}).encode()
        status, _, body = self.post_raw(raw)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        report = payload["report"]
        self.assertEqual(report["mode"], "UNTRUSTED_INSPECTION")
        self.assertFalse(report["trust"]["current_evidence_review_authority"])
        self.assertEqual(len(report["assessment_matrix"]), 12)

    def test_compiler_errors_are_bounded(self):
        raw = json.dumps({"candidate": {"reject": True}, "authority": {}}).encode()
        status, _, body = self.post_raw(raw)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "stub compiler rejection")

    def test_mutating_methods_not_exposed(self):
        self.assertEqual(self.request("PUT", "/api/inspect", body=b"{}")[0], 405)
        self.assertEqual(self.request("DELETE", "/api/inspect")[0], 405)
        self.assertEqual(self.request("OPTIONS", "/api/inspect")[0], 405)


class RealCompilerIntegration(unittest.TestCase):
    def test_existing_parent_compiler_is_the_only_runtime_compiler(self):
        parent = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"
        if not parent.is_dir():
            self.skipTest("parent compiler not present in isolated local test directory")
        candidate = json.loads((parent / "fixtures" / "synthetic_packet.json").read_text())
        authority = json.loads((parent / "fixtures" / "synthetic_authority.json").read_text())
        report = server.CompilerAdapter().inspect(candidate, authority)
        self.assertEqual(report["mode"], "UNTRUSTED_INSPECTION")
        self.assertEqual(report["aggregate_state"], "HOLD_TRUSTED_AUTHORITY_REQUIRED")
        self.assertFalse(report["trust"]["authority_root_supplied_out_of_band"])
        self.assertFalse(report["trust"]["current_evidence_review_authority"])
        self.assertEqual(len(report["assessment_matrix"]), 12)


if __name__ == "__main__":
    unittest.main()
