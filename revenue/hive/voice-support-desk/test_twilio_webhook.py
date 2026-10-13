#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

import merchant_auth
import twilio_webhook as webhook


class FakeGate:
    def __init__(self):
        self.turn_calls = []
        self.dial_calls = []

    def turn(self, call_id, turn, speech="", digits=""):
        self.turn_calls.append((call_id, turn, speech, digits))
        return {"twiml": "<Response><Say>ok</Say></Response>"}

    def dial_result(self, call_id, status):
        self.dial_calls.append((call_id, status))
        return {"twiml": "<Response><Say>dial ok</Say></Response>"}


class RecordingValidator:
    def __init__(self, expected_signature="valid", expected_url=None, explode=False):
        self.expected_signature = expected_signature
        self.expected_url = expected_url
        self.explode = explode
        self.calls = []

    def validate(self, url, params, signature):
        self.calls.append((url, dict(params), signature))
        if self.explode:
            raise RuntimeError("validator failure")
        return signature == self.expected_signature and (
            self.expected_url is None or url == self.expected_url
        )


class ServerCase(unittest.TestCase):
    origin = "https://support.example.test"

    def start_server(self, gate=None, validator=None):
        self.gate = gate or FakeGate()
        self.validator = validator or RecordingValidator()
        handler = webhook.make_handler(self.gate, self.validator, self.origin)
        self.server = webhook.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)

    def post(self, target, fields, signature=None, raw_body=None, content_type="application/x-www-form-urlencoded"):
        body = raw_body if raw_body is not None else urlencode(fields)
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body.encode("utf-8"))),
        }
        if signature is not None:
            headers[webhook.SIGNATURE_HEADER] = signature
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", target, body=body.encode("utf-8"), headers=headers)
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()
        return response.status, payload

    def get(self, target):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("GET", target)
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()
        return response.status, payload

    def test_missing_and_invalid_signature_stop_before_gate(self):
        self.start_server()
        fields = {"CallSid": "CA123", "SpeechResult": ""}
        status, body = self.post("/voice", fields)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "request authentication failed")
        status, _ = self.post("/voice", fields, signature="wrong")
        self.assertEqual(status, 403)
        self.assertEqual(self.gate.turn_calls, [])
        self.assertEqual(self.gate.dial_calls, [])

    def test_exact_public_url_query_and_every_form_field_reach_validator(self):
        expected_url = self.origin + "/voice?turn=7"
        validator = RecordingValidator(expected_url=expected_url)
        self.start_server(validator=validator)
        fields = {
            "CallSid": "CA123",
            "SpeechResult": "status",
            "Digits": "",
            "From": "+15005550006",
            "To": "+15005550007",
            "FutureProviderField": "preserve-me",
        }
        status, _ = self.post("/voice?turn=7", fields, signature="valid")
        self.assertEqual(status, 200)
        self.assertEqual(len(validator.calls), 1)
        url, seen, _ = validator.calls[0]
        self.assertEqual(url, expected_url)
        self.assertEqual(seen, fields)
        self.assertEqual(self.gate.turn_calls, [("CA123", 7, "status", "")])

    def test_validator_exception_fails_closed_before_gate(self):
        self.start_server(validator=RecordingValidator(explode=True))
        status, body = self.post(
            "/voice", {"CallSid": "CA123"}, signature="valid"
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "request authentication failed")
        self.assertEqual(self.gate.turn_calls, [])

    def test_query_tamper_fails_before_gate(self):
        validator = RecordingValidator(expected_url=self.origin + "/voice?turn=3")
        self.start_server(validator=validator)
        status, _ = self.post(
            "/voice?turn=4", {"CallSid": "CA123", "Digits": "1"}, signature="valid"
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.gate.turn_calls, [])

    def test_duplicate_form_key_fails_closed_before_validator_and_gate(self):
        self.start_server()
        status, _ = self.post(
            "/voice",
            {},
            signature="valid",
            raw_body="CallSid=CA1&CallSid=CA2",
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.validator.calls, [])
        self.assertEqual(self.gate.turn_calls, [])

    def test_authenticated_dial_result_dispatches_once(self):
        self.start_server()
        fields = {"CallSid": "CA123", "DialCallStatus": "completed"}
        status, body = self.post("/dial-result", fields, signature="valid")
        self.assertEqual(status, 200)
        self.assertIn("dial ok", body)
        self.assertEqual(self.gate.dial_calls, [("CA123", "completed")])

    def test_dial_result_query_is_bound_then_rejected(self):
        expected = self.origin + "/dial-result?unexpected=1"
        validator = RecordingValidator(expected_url=expected)
        self.start_server(validator=validator)
        status, _ = self.post(
            "/dial-result?unexpected=1",
            {"CallSid": "CA123", "DialCallStatus": "completed"},
            signature="valid",
        )
        self.assertEqual(status, 400)
        self.assertEqual(len(validator.calls), 1)
        self.assertEqual(self.gate.dial_calls, [])

    def test_health_states_both_auth_boundaries_and_no_live_claim(self):
        self.start_server()
        status, body = self.get("/health")
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(value["provider_authentication"], "twilio-request-validator-required")
        self.assertEqual(value["order_verification"], "required")
        self.assertIs(value["live_telephone_tested"], False)


class ConfigurationCase(unittest.TestCase):
    def test_public_origin_is_https_origin_only(self):
        self.assertEqual(
            webhook._public_origin("https://support.example.com/"),
            "https://support.example.com",
        )
        for bad in (
            "http://support.example.com",
            "https://support.example.com/twilio",
            "https://support.example.com?x=1",
            "https://user:pass@support.example.com",
            " https://support.example.com",
        ):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                webhook._public_origin(bad)

    def test_loopback_only_bind(self):
        self.assertEqual(webhook._loopback("127.0.0.1"), "127.0.0.1")
        self.assertEqual(webhook._loopback("::1"), "::1")
        with self.assertRaises(Exception):
            webhook._loopback("0.0.0.0")

    def test_official_twilio_form_signature_vector_when_sdk_available(self):
        try:
            validator = webhook._load_validator("12345")
        except RuntimeError:
            self.skipTest("Twilio SDK not installed in local smoke environment")
        url = "https://example.com/myapp.php?foo=1&bar=2"
        params = {
            "CallSid": "CA1234567890ABCDE",
            "Caller": "+14158675310",
            "Digits": "1234",
            "From": "+14158675310",
            "To": "+18005551212",
        }
        expected = "L/OH5YylLD5NRKLltdqwSvS0BnU="
        self.assertEqual(validator.compute_signature(url, params), expected)
        self.assertTrue(validator.validate(url, params, expected))
        self.assertFalse(validator.validate(url + "&tampered=1", params, expected))


@unittest.skipUnless(
    hasattr(merchant_auth, "MerchantGate") and hasattr(merchant_auth, "ACCESS_COLUMNS"),
    "real merchant_auth.py not present in local smoke environment",
)
class RealMerchantGateCase(unittest.TestCase):
    """Runs in the repository/hosted workflow against the landed MerchantGate."""

    def setUp(self):
        try:
            self.validator = webhook._load_validator("test-auth-token-12345")
        except RuntimeError:
            self.skipTest("Twilio SDK not installed")
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "voice.sqlite3")
        self.gate = merchant_auth.MerchantGate(self.db)
        self.gate.base.import_csv(
            "order_ref,status,eta,delivered_on,returnable\n"
            "ORD-100,shipped,Arrives tomorrow,,true\n"
        )
        self.gate.import_access_csv(
            "order_ref,support_code\nORD-100,12345678\n"
        )
        self.origin = "https://voice.example.test"
        handler = webhook.make_handler(self.gate, self.validator, self.origin)
        self.server = webhook.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def signed_post(self, target, fields):
        signature = self.validator.compute_signature(self.origin + target, fields)
        body = urlencode(fields)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body.encode("utf-8"))),
            webhook.SIGNATURE_HEADER: signature,
        }
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", target, body=body.encode("utf-8"), headers=headers)
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()
        return response.status, payload

    def test_signed_body_tamper_is_rejected_before_merchant_gate(self):
        fields = {"CallSid": "CA-HIVE006-TAMPER-1"}
        signature = self.validator.compute_signature(self.origin + "/voice", fields)
        body = urlencode({"CallSid": "CA-HIVE006-TAMPER-1", "SpeechResult": "changed"})
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body.encode("utf-8"))),
            webhook.SIGNATURE_HEADER: signature,
        }
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", "/voice", body=body.encode("utf-8"), headers=headers)
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()
        self.assertEqual(response.status, 403)
        self.assertEqual(json.loads(payload)["error"], "request authentication failed")
        with self.gate.base.connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM merchant_calls WHERE call_id=?",
                ("CA-HIVE006-TAMPER-1",),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_source_bundle_excludes_runtime_state_and_secret_material(self):
        destination = Path(self.temp.name) / "source.zip"
        webhook.bundle(destination)
        import zipfile
        with zipfile.ZipFile(destination) as archive:
            names = set(archive.namelist())
        expected = {"voice-support-desk/" + name for name in webhook.BUNDLE_NAMES}
        self.assertEqual(names, expected)
        self.assertFalse(any(name.endswith(".sqlite3") for name in names))
        self.assertFalse(any("token" in name.lower() for name in names))

    def test_signed_provider_flow_still_requires_order_support_code(self):
        call = "CA-HIVE006-SIGNED-1"
        status, body = self.signed_post("/voice", {"CallSid": call})
        self.assertEqual(status, 200)
        self.assertIn("secure order desk", body)

        status, body = self.signed_post(
            "/voice?turn=1", {"CallSid": call, "SpeechResult": "ORD-100"}
        )
        self.assertEqual(status, 200)
        self.assertIn("support code", body)
        self.assertNotIn("Arrives tomorrow", body)

        status, body = self.signed_post(
            "/voice?turn=2", {"CallSid": call, "Digits": "12345678#"}
        )
        self.assertEqual(status, 200)
        self.assertIn("Order ORD-100 found", body)

        status, body = self.signed_post(
            "/voice?turn=3", {"CallSid": call, "Digits": "1"}
        )
        self.assertEqual(status, 200)
        self.assertIn("shipped", body)
        self.assertIn("Arrives tomorrow", body)


if __name__ == "__main__":
    unittest.main()
