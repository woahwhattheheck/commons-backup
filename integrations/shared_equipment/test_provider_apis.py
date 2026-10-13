import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from integrations.shared_equipment.provider_apis import GroqExaEquipment
from integrations.shared_equipment.credential_transfer import CredentialSources
from integrations.shared_equipment.services import CombinedCatalog


class Credentials(CredentialSources):
    def __init__(self):
        self.reads = []
        super().__init__(readers={
            "groq/api-key": lambda: "synthetic-groq-test-key",
            "exa/api-key": lambda: "synthetic-exa-test-key",
        })

    def read(self, reference):
        self.reads.append(reference)
        return super().read(reference)


class Response:
    def __init__(self, value, status=200, headers=None):
        self.body = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
        self.status = status
        self.headers = headers or Message()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self, count=-1):
        if count < 0:
            return self.body
        return self.body[:count]


class ProviderApiTests(unittest.TestCase):
    def test_catalog_advertises_shared_provider_extension(self):
        class Public:
            def tools(self, **_kwargs):
                return []

            def call(self, _name, _arguments):
                self.fail("public catalog must not receive provider tools")

        names = {tool["name"] for tool in CombinedCatalog(Public()).tools()}
        self.assertTrue({"groq_list_models", "groq_chat_completion", "exa_search", "exa_contents"}.issubset(names))

    def test_groq_chat_loads_secure_reference_and_sends_one_bounded_completion(self):
        creds = Credentials()
        captured = []

        def opener(request, timeout):
            captured.append((request, timeout, request.data))
            return Response({"id": "chatcmpl-test", "choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 3}})

        equipment = GroqExaEquipment(credential_sources=creds, opener=opener)
        result = equipment.call("groq_chat_completion", {
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "Reply exactly OK"}],
            "max_completion_tokens": 8,
        })

        request, timeout, body = captured[0]
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(result["result"]["choices"][0]["message"]["content"], "OK")
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-groq-test-key")
        self.assertEqual(request.get_header("User-agent"), "CommonsSharedEquipment/1.0")
        self.assertEqual(payload["max_completion_tokens"], 8)
        self.assertFalse(payload["stream"])
        self.assertEqual(creds.reads, ["groq/api-key"])
        self.assertLessEqual(timeout, 60)

    def test_exa_search_defaults_to_metadata_and_caps_results(self):
        creds = Credentials()
        captured = []

        def opener(request, timeout):
            captured.append(request)
            return Response({"requestId": "exa-test", "results": [{"title": "Example", "url": "https://example.com"}]})

        equipment = GroqExaEquipment(credential_sources=creds, opener=opener)
        result = equipment.call("exa_search", {"query": "example research"})
        request = captured[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertFalse(result["isError"])
        self.assertEqual(request.full_url, "https://api.exa.ai/search")
        self.assertEqual(request.get_header("X-api-key"), "synthetic-exa-test-key")
        self.assertEqual(payload, {"query": "example research", "type": "auto", "numResults": 5})
        self.assertEqual(creds.reads, ["exa/api-key"])

    def test_exa_contents_uses_documented_endpoint_and_rejects_embedded_credentials(self):
        creds = Credentials()
        captured = []

        def opener(request, timeout):
            captured.append(request)
            return Response({"requestId": "exa-test", "results": [{"url": "https://example.com", "text": "text"}]})

        equipment = GroqExaEquipment(credential_sources=creds, opener=opener)
        result = equipment.call("exa_contents", {"urls": ["https://example.com"]})
        payload = json.loads(captured[0].data.decode("utf-8"))
        self.assertFalse(result["isError"])
        self.assertEqual(captured[0].full_url, "https://api.exa.ai/contents")
        self.assertEqual(payload, {"urls": ["https://example.com"], "text": True})
        rejected = equipment.call("exa_contents", {"urls": ["https://user:pass@example.com"]})
        self.assertTrue(rejected["isError"])
        self.assertEqual(rejected["code"], "invalid_url")
        self.assertEqual(len(captured), 1)

    def test_rate_limit_error_preserves_retry_after_and_scrubs_key(self):
        creds = Credentials()
        headers = Message()
        headers["Retry-After"] = "17"
        headers["X-RateLimit-Remaining-Requests"] = "0"

        def opener(_request, timeout):
            raise HTTPError(
                "https://api.groq.com/openai/v1/chat/completions",
                429,
                "rate limited",
                headers,
                io.BytesIO(b'{"error":{"code":"rate_limit_exceeded","message":"synthetic-groq-test-key rejected"}}'),
            )

        equipment = GroqExaEquipment(credential_sources=creds, opener=opener)
        result = equipment.call("groq_chat_completion", {
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "Hello"}],
        })

        self.assertTrue(result["isError"])
        self.assertEqual(
            result.get("http_status"), 429,
            f"unexpected error shape: keys={sorted(result)} code={result.get('code')}",
        )
        self.assertEqual(result["retry_after"], "17")
        self.assertEqual(result["rate_limit_headers"]["x-ratelimit-remaining-requests"], "0")
        self.assertEqual(result["provider_error"]["code"], "rate_limit_exceeded")
        self.assertNotIn("synthetic-groq-test-key", json.dumps(result))
        self.assertFalse(result["uncertain"])

    def test_network_error_on_post_is_marked_uncertain_without_retry(self):
        creds = Credentials()
        calls = []

        def opener(_request, timeout):
            calls.append(True)
            raise OSError("synthetic network failure")

        equipment = GroqExaEquipment(credential_sources=creds, opener=opener)
        result = equipment.call("exa_search", {"query": "bounded query"})
        self.assertTrue(result["isError"])
        self.assertTrue(
            result["uncertain"],
            f"POST network failure should be uncertain: code={result.get('code')} error={result.get('error')}",
        )
        self.assertEqual(calls, [True])
        self.assertNotIn("synthetic network failure", json.dumps(result))

    def test_oversized_success_response_for_post_is_uncertain(self):
        equipment = GroqExaEquipment(credential_sources=Credentials(), opener=lambda _request, timeout: Response(b"012345"))
        with patch("integrations.shared_equipment.provider_apis.MAX_RESPONSE_BYTES", 4):
            result = equipment.call("exa_search", {"query": "bounded query"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["code"], "provider_response_too_large")
        self.assertTrue(result["uncertain"])

    def test_malformed_success_response_for_post_is_uncertain(self):
        equipment = GroqExaEquipment(credential_sources=Credentials(), opener=lambda _request, timeout: Response(b"not-json"))
        result = equipment.call("exa_contents", {"urls": ["https://example.com"]})
        self.assertTrue(result["isError"])
        self.assertEqual(result["code"], "provider_response_invalid")
        self.assertTrue(result["uncertain"])

    def test_unreadable_server_error_body_preserves_uncertainty_and_status(self):
        headers = Message()
        headers["Retry-After"] = "5"

        class BrokenBodyHTTPError(HTTPError):
            def read(self, _amount=-1):
                raise OSError("synthetic response read failure")

        def opener(_request, timeout):
            raise BrokenBodyHTTPError("https://api.exa.ai/search", 503, "unavailable", headers, None)

        equipment = GroqExaEquipment(credential_sources=Credentials(), opener=opener)
        result = equipment.call("exa_search", {"query": "bounded query"})
        self.assertTrue(result["isError"])
        self.assertEqual(result["http_status"], 503)
        self.assertEqual(result["retry_after"], "5")
        self.assertTrue(result["error_body_read_failed"])
        self.assertTrue(result["uncertain"])


if __name__ == "__main__":
    unittest.main()
