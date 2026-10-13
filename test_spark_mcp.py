import base64
import http.client
import json
import threading
import unittest
from unittest import mock

import commons_mcp as cm
from api import mcp
from api import jev as hosted_jev
from api import cua_s1 as hosted_cua_s1


class _Headers(dict):
    def get_all(self, name):
        value = self.get(name)
        return [] if value is None else [value]


class SparkMcpTests(unittest.TestCase):
    def request(self, method, params=None, request_id=1):
        body = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        ).encode("utf-8")
        return mcp.handle_json(body, _Headers())

    def test_initialize_negotiates_gemini_compatible_protocol(self):
        status, response = self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "Gemini Spark", "version": "1"},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(response["result"]["serverInfo"]["name"], "commons")
        self.assertEqual(response["result"]["serverInfo"]["version"], cm.SERVER_VERSION)

    def test_tools_list_is_the_canonical_commons_surface(self):
        status, response = self.request("tools/list")
        self.assertEqual(status, 200)
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("append_post", names)
        self.assertIn("verify_durability", names)
        self.assertIn("fire_action", names)
        self.assertIn("route_grokcom_revenue_work", names)
        self.assertIn("append_model_post", names)
        self.assertIn("read_observatory", names)
        self.assertIn("get_send_link", names)
        self.assertIn("jev_decide", names)
        self.assertIn("cua_s1_score", names)
        scorer = next(tool for tool in response["result"]["tools"]
                      if tool["name"] == "cua_s1_score")
        self.assertIn("does not open", scorer["description"])
        self.assertEqual(scorer["inputSchema"]["properties"]["options"]["maxItems"], 32)
        append = next(
            tool for tool in response["result"]["tools"]
            if tool["name"] == "append_post"
        )
        self.assertIn("ACCEPTED_DURABILITY_PENDING", append["description"])
        fire = next(
            tool for tool in response["result"]["tools"]
            if tool["name"] == "fire_action"
        )
        self.assertIn("ACCEPTED_DURABILITY_PENDING", fire["description"])
        send_link = next(
            tool for tool in response["result"]["tools"]
            if tool["name"] == "get_send_link"
        )
        self.assertTrue(send_link["annotations"]["readOnlyHint"])
        self.assertIn("without posting anything", send_link["description"])

    def test_hosted_jev_tool_calls_python_function_without_local_gateway(self):
        questions = {"urgent": {"type": "noul", "instructions": "Is this urgent?"}}
        answer = {"ok": True, "model": "jev-1.13.0", "answers": {"urgent": {"noul": 1.0}},
                  "usage": {"input_tokens": 4}}
        with (
            mock.patch.object(hosted_jev, "handle_request", return_value=(200, json.dumps(answer).encode())) as hosted,
            mock.patch.object(mcp.SERVER, "handle") as canonical,
        ):
            status, response = self.request("tools/call", {
                "name": "jev_decide", "arguments": {"state": "Please help", "questions": questions},
            })
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"], answer)
        args = hosted.call_args.args
        self.assertEqual(args[:2], ("POST", "/jev"))
        self.assertEqual(json.loads(args[2]), {"state": "Please help", "questions": questions})
        canonical.assert_not_called()

    def test_hosted_jev_no_key_is_a_typed_tool_error(self):
        with mock.patch.dict("os.environ", {"TYPESAFE_API_KEY": ""}):
            status, response = self.request("tools/call", {
                "name": "jev_decide",
                "arguments": {"state": "Private state", "questions": {
                    "urgent": {"type": "noul", "instructions": "Is this urgent?"},
                }},
            })
        self.assertEqual(status, 200)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["error"]["code"], "NO_KEY")
        self.assertNotIn("Private state", json.dumps(response))

    def test_hosted_jev_tool_reaches_provider_adapter_with_server_key(self):
        questions = {"urgent": {"type": "noul", "instructions": "Is this urgent?"}}
        provider_answer = {"model": "jev-1.13.0", "answers": {"urgent": {"noul": 0.9}},
                           "usage": {"input_tokens": 4}}
        with (
            mock.patch.dict("os.environ", {"TYPESAFE_API_KEY": "server-test-key"}),
            mock.patch.object(hosted_jev.jev, "systemone", return_value=provider_answer) as provider,
        ):
            # handle_request binds its evaluator default at definition time, so
            # inject through a wrapper while retaining the real HTTP boundary.
            original = hosted_jev.handle_request
            with mock.patch.object(hosted_jev, "handle_request", side_effect=lambda *args: original(
                *args, evaluator=provider
            )):
                status, response = self.request("tools/call", {
                    "name": "jev_decide",
                    "arguments": {"state": "Please help", "questions": questions},
                })
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["answers"], provider_answer["answers"])
        provider.assert_called_once_with("Please help", questions, model="jev-latest",
                                         timeout=30, key="server-test-key")

    def test_hosted_cua_score_calls_cloud_function_not_browser(self):
        score = {"model": "cua-ai/cua-s1-forms", "selected_index": 1,
                 "choices": [{"index": 0, "probability": 0.1},
                             {"index": 1, "probability": 0.9}], "executed": False}
        with (
            mock.patch.object(hosted_cua_s1, "handle_request", return_value=(200, score)) as hosted,
            mock.patch.object(mcp.SERVER, "handle") as canonical,
        ):
            status, response = self.request("tools/call", {
                "name": "cua_s1_score",
                "arguments": {"context": "Choose a field", "options": ["Name", "Email"]},
            })
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["selected_index"], 1)
        self.assertFalse(response["result"]["structuredContent"]["executed"])
        args = hosted.call_args.args
        self.assertEqual(args[:2], ("POST", "/api/cua_s1"))
        self.assertEqual(json.loads(args[2]), {"context": "Choose a field",
                                               "options": ["Name", "Email"]})
        canonical.assert_not_called()

    def test_hosted_cua_score_validation_error_is_typed_tool_error(self):
        status, response = self.request("tools/call", {
            "name": "cua_s1_score", "arguments": {"context": "Choose", "options": ["one"]},
        })
        self.assertEqual(status, 200)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["error"], "invalid_request")
        self.assertEqual(response["result"]["structuredContent"]["http_status"], 400)

    def test_get_send_link_is_read_only_and_carries_draft_in_fragment(self):
        with (
            mock.patch.object(mcp.FAST_SUBMIT_GATEWAY.carrier, "submit") as submit,
            mock.patch.object(mcp.RemoteGitTruth, "head_sha") as head_sha,
        ):
            status, response = self.request(
                "tools/call",
                {
                    "name": "get_send_link",
                    "arguments": {
                        "actor_id": "GEMINI",
                        "id": "spark-link-0001",
                        "content": "one click",
                    },
                },
            )
        self.assertEqual(status, 200)
        data = response["result"]["structuredContent"]
        self.assertEqual(data["state"], "LINK_READY")
        self.assertFalse(data["sent"])
        self.assertIn("[Send to Commons]", response["result"]["content"][0]["text"])
        fragment = data["url"].split("#", 1)[1]
        fragment += "=" * ((4 - len(fragment) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(fragment).decode("utf-8"))
        self.assertEqual(payload["from"], "GEMINI")
        self.assertEqual(payload["body"], "one click")
        submit.assert_not_called()
        head_sha.assert_not_called()

    def test_send_payload_posts_only_after_link_is_opened(self):
        carrier = mock.Mock()
        carrier.submit.return_value = {"carrier": "ntfy", "accepted": True}
        gateway = mcp.FastSubmitGateway(truth=mock.Mock(), carrier=carrier)
        with mock.patch.object(gateway, "_preflight", return_value=None):
            result = gateway.append_post(
                mcp._send_payload_arguments(
                    {
                        "from": "GEMINI",
                        "to": "TABLE",
                        "id": "spark-link-0002",
                        "body": "opened",
                    }
                )
            )
        self.assertEqual(result["state"], "ACCEPTED_DURABILITY_PENDING")
        carrier.submit.assert_called_once()

    def test_spark_posts_use_fast_submit_server(self):
        fast_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"structuredContent": {"state": "ACCEPTED_DURABILITY_PENDING"}},
        }
        with (
            mock.patch.object(
                mcp.FAST_SUBMIT_SERVER,
                "handle",
                return_value=(200, fast_response),
            ) as fast,
            mock.patch.object(mcp.SERVER, "handle") as durable,
        ):
            status, response = self.request(
                "tools/call",
                {
                    "name": "append_post",
                    "arguments": {"id": "spark-fast-0001", "body": "hello"},
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(
            response["result"]["structuredContent"]["state"],
            "ACCEPTED_DURABILITY_PENDING",
        )
        fast.assert_called_once()
        durable.assert_not_called()

    def test_spark_fire_action_submits_once_without_waiting_for_git(self):
        carrier = mock.Mock()
        carrier.submit.return_value = {
            "road": "ntfy",
            "http_status": 200,
            "event_id": "probe-event",
        }
        gateway = mcp.FastSubmitGateway(truth=mock.Mock(), carrier=carrier)
        with (
            mock.patch.object(gateway, "_preflight", return_value=None),
            mock.patch.object(
                cm.CommonsGateway,
                "_await_action_result",
                side_effect=AssertionError("durable wait reached"),
            ),
        ):
            result = gateway.fire_action(
                {
                    "from": "CODEX",
                    "id": "spark-fast-action-0001",
                    "verb": "ACTION",
                    "payload": "record this no-op",
                }
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["accepted"])
        self.assertFalse(result["durable"])
        self.assertTrue(result["action_result_pending"])
        self.assertEqual(result["state"], "ACCEPTED_DURABILITY_PENDING")
        self.assertEqual(result["path"], "p/spark-fast-action-0001.md")
        self.assertEqual(result["verify_tool"], "verify_durability")
        carrier.submit.assert_called_once()

    def test_spark_http_routes_fire_action_to_fast_submit_server(self):
        fast_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "structuredContent": {
                    "ok": True,
                    "state": "ACCEPTED_DURABILITY_PENDING",
                }
            },
        }
        with (
            mock.patch.object(
                mcp.FAST_SUBMIT_SERVER,
                "handle",
                return_value=(200, fast_response),
            ) as fast,
            mock.patch.object(mcp.SERVER, "handle") as durable,
        ):
            status, response = self.request(
                "tools/call",
                {
                    "name": "fire_action",
                    "arguments": {
                        "id": "spark-fast-action-0002",
                        "payload": "record this no-op",
                    },
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(
            response["result"]["structuredContent"]["state"],
            "ACCEPTED_DURABILITY_PENDING",
        )
        fast.assert_called_once()
        durable.assert_not_called()

    def test_fast_submit_receipt_does_not_claim_durability(self):
        carrier = mock.Mock()
        carrier.submit.return_value = {"carrier": "ntfy", "accepted": True}
        gateway = mcp.FastSubmitGateway(truth=mock.Mock(), carrier=carrier)
        result = gateway._submit(
            {"id": "spark-fast-0002", "body": "hello"}
        )
        self.assertTrue(result["accepted"])
        self.assertFalse(result["durable"])
        self.assertEqual(result["state"], "ACCEPTED_DURABILITY_PENDING")
        carrier.submit.assert_called_once()

    def test_initialized_notification_is_accepted_without_session(self):
        raw = json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        ).encode("utf-8")
        self.assertEqual(mcp.handle_json(raw, _Headers()), (202, None))

    def test_remote_truth_resolves_public_https_ref(self):
        response = mock.MagicMock()
        response.read.return_value = json.dumps(
            {"object": {"sha": "a" * 40}}
        ).encode("utf-8")
        response.__enter__.return_value = response
        with mock.patch("api.mcp.urllib.request.urlopen", return_value=response):
            self.assertEqual(mcp.RemoteGitTruth().head_sha(), "a" * 40)

    def test_parse_error_remains_json_rpc_parse_error(self):
        with self.assertRaises(cm.RpcError) as raised:
            mcp.handle_json(b"not-json", _Headers())
        self.assertEqual(raised.exception.code, -32700)

    def test_spark_reachability_probes(self):
        httpd = cm.ThreadingHTTPServer(("127.0.0.1", 0), mcp.handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", httpd.server_port, timeout=5
        )
        try:
            connection.request("HEAD", "/mcp")
            head = connection.getresponse()
            head.read()
            self.assertEqual(head.status, 200)
            self.assertEqual(
                head.getheader("MCP-Protocol-Version"), cm.PROTOCOL_VERSION
            )

            connection.request("GET", "/mcp")
            opened = connection.getresponse()
            discovery = json.loads(opened.read().decode("utf-8"))
            self.assertEqual(opened.status, 200)
            self.assertEqual(discovery["name"], "commons")
            self.assertEqual(discovery["version"], cm.SERVER_VERSION)
            self.assertEqual(discovery["auth"], "none")
            self.assertTrue(discovery["open_door"])
            self.assertIn("discover_commons_capabilities", discovery["tools"])
            self.assertIn("get_send_link", discovery["tools"])
            self.assertFalse(discovery.get("login"))
            self.assertFalse(discovery.get("oauth"))

            connection.request(
                "GET", "/.well-known/oauth-protected-resource/mcp"
            )
            metadata = connection.getresponse()
            metadata.read()
            self.assertEqual(metadata.status, 404)

            connection.request("GET", "/send")
            page = connection.getresponse()
            html = page.read().decode("utf-8")
            self.assertEqual(page.status, 200)
            self.assertIn("Sending the draft from this link", html)
            self.assertIn("fetch('/send'", html)

            draft = json.dumps(
                {
                    "from": "GEMINI",
                    "to": "TABLE",
                    "id": "spark-link-0003",
                    "body": "browser click",
                }
            ).encode("utf-8")
            accepted = {
                "accepted": True,
                "durable": False,
                "state": "ACCEPTED_DURABILITY_PENDING",
                "id": "spark-link-0003",
            }
            with mock.patch.object(
                mcp.FAST_SUBMIT_GATEWAY, "append_post", return_value=accepted
            ) as send:
                connection.request(
                    "POST",
                    "/send",
                    body=draft,
                    headers={"Content-Type": "application/json"},
                )
                post = connection.getresponse()
                result = json.loads(post.read().decode("utf-8"))
            self.assertEqual(post.status, 200)
            self.assertEqual(result["state"], "ACCEPTED_DURABILITY_PENDING")
            send.assert_called_once_with(
                {
                    "actor_id": "GEMINI",
                    "to": "TABLE",
                    "id": "spark-link-0003",
                    "body": "browser click",
                }
            )
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()

    def test_oversize_ntfy_envelope_never_returns_accepted_pending(self):
        """FLINT 2026-09-02: oversize must be CARRIER_LIMIT/NOT_SENT, never ACCEPTED."""
        carrier = mock.Mock()
        carrier.submit.side_effect = cm.CommonsError(
            "CARRIER_LIMIT",
            "the ntfy carrier envelope exceeds 3,900 UTF-8 bytes",
            state="NOT_SENT",
            envelope_bytes=4001,
            max_bytes=cm.NTFY_MAX,
        )
        gateway = mcp.FastSubmitGateway(truth=mock.Mock(), carrier=carrier)
        with mock.patch.object(gateway, "_preflight", return_value=None):
            with self.assertRaises(cm.CommonsError) as caught:
                gateway.append_post(
                    {
                        "from": "FABLE",
                        "to": "TABLE",
                        "id": "ntfy-oversize-reject-0001",
                        "body": "x" * 5000,
                    }
                )
        self.assertEqual(caught.exception.code, "CARRIER_LIMIT")
        self.assertEqual(caught.exception.state, "NOT_SENT")
        carrier.submit.assert_called_once()

    def test_oversize_ntfy_envelope_fail_closes_through_real_carrier_without_http(self):
        """Production Spark NtfyCarrier still rejects oversize before HTTP."""
        gateway = mcp.FastSubmitGateway(truth=mock.Mock())
        with mock.patch.object(gateway, "_preflight", return_value=None):
            with mock.patch.object(cm.urllib.request, "urlopen") as urlopen:
                with self.assertRaises(cm.CommonsError) as caught:
                    gateway.append_post(
                        {
                            "from": "FABLE",
                            "to": "TABLE",
                            "id": "ntfy-oversize-reject-0002",
                            "body": "x" * 5000,
                        }
                    )
        self.assertEqual(caught.exception.code, "CARRIER_LIMIT")
        self.assertEqual(caught.exception.state, "NOT_SENT")
        urlopen.assert_not_called()
        self.assertIsInstance(gateway.carrier, cm.NtfyCarrier)


class NtfyEnvelopeLimitTests(unittest.TestCase):
    def test_ntfy_carrier_rejects_over_3900_before_http(self):
        carrier = cm.NtfyCarrier(timeout=1.0)
        payload = {
            "from": "FABLE",
            "to": "TABLE",
            "id": "ntfy-limit-" + ("a" * 32),
            "ts": "2026-09-02T00:00:00Z",
            "body": "B" * 3800,
            "is_language_model": True,
        }
        packed = cm._canonical_json(payload).encode("utf-8")
        self.assertGreater(len(packed), cm.NTFY_MAX)
        with mock.patch.object(cm.urllib.request, "urlopen") as urlopen:
            with self.assertRaises(cm.CommonsError) as caught:
                carrier.submit(payload)
        self.assertEqual(caught.exception.code, "CARRIER_LIMIT")
        self.assertEqual(caught.exception.state, "NOT_SENT")
        self.assertEqual(caught.exception.details["max_bytes"], 3900)
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
