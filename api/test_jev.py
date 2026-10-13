"""Focused hosted Jev boundary tests without provider spending."""

import json
import unittest

from api import jev as hosted


QUESTIONS = {
    "urgent": {"type": "noul", "instructions": "Does this message express urgency?"},
    "team": {"type": "choice", "instructions": "Which team handles this?",
             "criteria": {"billing": "Payment", "technical": "Software"}},
}


def request(payload, *, key="test-key", evaluator=None):
    return hosted.handle_request("POST", "/jev", json.dumps(payload).encode(), key=key,
                                 evaluator=evaluator or hosted.jev.systemone)


class HostedJevTests(unittest.TestCase):
    def test_official_request_and_answer_contract(self):
        calls = []
        def evaluate(state, questions, **kwargs):
            calls.append((state, questions, kwargs))
            return {"model": "jev-1.13.0", "answers": {"urgent": {"type": "noul", "noul": 1.0}},
                    "usage": {"input_tokens": 12, "output_tokens": 3}}
        status, blob = request({"state": "Please help ASAP", "questions": QUESTIONS}, evaluator=evaluate)
        data = json.loads(blob)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["answers"]["urgent"]["noul"], 1.0)
        self.assertEqual(calls[0][2], {"model": "jev-latest", "timeout": 30, "key": "test-key"})

    def test_key_absent_returns_typed_result_without_provider_call(self):
        def forbidden(*_args, **_kwargs):
            self.fail("provider must not be called")
        status, blob = request({"state": "Hello", "questions": QUESTIONS}, key="", evaluator=forbidden)
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(blob)["error"]["code"], "NO_KEY")
        self.assertNotIn(b"test-key", blob)

    def test_invalid_question_stays_local(self):
        status, blob = request({"state": "Hello", "questions": {"x": {"type": "choice"}}})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(blob)["error"]["code"], "BAD_QUESTIONS")

    def test_provider_error_is_typed_without_secret_or_state(self):
        def fail(*_args, **_kwargs):
            raise hosted.jev.JevError("HTTP_402")
        status, blob = request({"state": "PRIVATE STATE", "questions": QUESTIONS}, evaluator=fail)
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(blob)["error"]["code"], "HTTP_402")
        self.assertNotIn(b"PRIVATE STATE", blob)
        self.assertNotIn(b"test-key", blob)

    def test_health_exposes_configuration_state_only(self):
        status, blob = hosted.handle_request("GET", "/jev", b"", key="test-key")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(blob)["configured"])
        self.assertNotIn(b"test-key", blob)

    def test_body_and_route_bounds(self):
        status, blob = hosted.handle_request("POST", "/jev", b"x" * (hosted.MAX_BODY_BYTES + 1), key="test-key")
        self.assertEqual((status, json.loads(blob)["error"]["code"]), (413, "BODY_TOO_LARGE"))
        status, blob = hosted.handle_request("POST", "/other", b"", key="test-key")
        self.assertEqual((status, json.loads(blob)["error"]["code"]), (404, "NOT_FOUND"))


if __name__ == "__main__":
    unittest.main()
