import base64
import hashlib
import hmac
import importlib.util
import io
import sys
import unittest
import urllib.error
from pathlib import Path


PATH = Path(__file__).with_name("commons_teams_bridge.py")
SPEC = importlib.util.spec_from_file_location("commons_teams_bridge", PATH)
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class Response:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return b""


class TeamsBridgeTest(unittest.TestCase):
    def test_adaptive_card_matches_teams_envelope(self):
        payload = bridge.adaptive_card(
            title="Commons shipped",
            text="Tests passed",
            url="https://example.test/commit/abc",
            event_id="event-1",
        )
        attachment = payload["attachments"][0]
        self.assertEqual(payload["type"], "message")
        self.assertEqual(attachment["contentType"], bridge.CONTENT_TYPE)
        self.assertIsNone(attachment["contentUrl"])
        self.assertEqual(attachment["content"]["type"], "AdaptiveCard")
        self.assertEqual(attachment["content"]["version"], "1.2")
        self.assertIn("commons:event-1", bridge.canonical(payload).decode())

    def test_large_unicode_body_is_shortened_under_28_kb(self):
        payload = bridge.adaptive_card(
            title="Large event",
            text="🛠 commons open road " * 4000,
            event_id="big",
        )
        raw = bridge.canonical(payload)
        self.assertLessEqual(len(raw), bridge.MAX_MESSAGE_BYTES)
        self.assertIn("commons:big", raw.decode())
        self.assertTrue(payload["attachments"][0]["content"]["body"][1]["text"].endswith("…"))

    def test_workflow_post_has_no_authorization_header(self):
        seen = []

        def opener(request, timeout):
            seen.append((request, timeout))
            return Response(202)

        receipt = bridge.post_workflow(
            "https://example.test/workflow/capability",
            bridge.adaptive_card(title="t", text="b"),
            opener=opener,
        )
        headers = {key.lower(): value for key, value in seen[0][0].header_items()}
        self.assertNotIn("authorization", headers)
        self.assertEqual(receipt["status"], 202)
        self.assertEqual(receipt["attempts"], 1)

    def test_workflow_retries_throttle_with_retry_after(self):
        calls, sleeps = [], []

        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "throttled", {"Retry-After": "0.25"}, io.BytesIO()
                )
            return Response(200)

        receipt = bridge.post_workflow(
            "https://example.test/workflow/capability",
            bridge.adaptive_card(title="t", text="b"),
            opener=opener,
            sleep=sleeps.append,
        )
        self.assertEqual(receipt["attempts"], 2)
        self.assertEqual(sleeps, [0.25])

    def test_outgoing_hmac_matches_provider_contract(self):
        key = b"teams-generated-signing-key"
        raw = b'{"type":"message","text":"hello"}'
        signature = base64.b64encode(hmac.new(key, raw, hashlib.sha256).digest()).decode()
        encoded_key = base64.b64encode(key).decode()
        self.assertTrue(bridge.verify_outgoing_hmac(raw, f"HMAC {signature}", encoded_key))
        self.assertFalse(bridge.verify_outgoing_hmac(raw + b"!", f"HMAC {signature}", encoded_key))
        self.assertFalse(bridge.verify_outgoing_hmac(raw, "HMAC wrong", encoded_key))

    def test_normalization_preserves_arbitrary_content_and_metadata(self):
        payload = {
            "type": "message",
            "id": "activity-1",
            "text": "自由な verb: deploy-now 🛠",
            "from": {"id": "member-1", "name": "Builder"},
            "conversation": {"id": "team-thread-1"},
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelData": {"tenant": {"id": "tenant-1"}, "caller": {"x": 1}},
            "scratchpad": {"anything": [1, 2, 3]},
        }
        normalized = bridge.normalize_outgoing_activity(payload)
        self.assertEqual(normalized["text"], payload["text"])
        self.assertIs(normalized["raw"], payload)
        self.assertEqual(normalized["raw"]["scratchpad"], {"anything": [1, 2, 3]})
        self.assertEqual(normalized["channel_data"], payload["channelData"])

    def test_outgoing_response_is_message(self):
        self.assertEqual(
            bridge.outgoing_response("Commons received it"),
            {"type": "message", "text": "Commons received it"},
        )


if __name__ == "__main__":
    unittest.main()
