import io
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from integrations.gemini_slack.peer_tool_gateway import EventStore, ToolCallStore, ToolGateway, ToolLoop
from integrations.shared_equipment.provider_io import EquipmentError
from integrations.shared_equipment.services import CombinedCatalog, ServiceEquipment, redacted
from integrations.shared_equipment.slack_carrier import SlackEquipmentCarrier, parse_request, slack_timestamp


class EquipmentTests(unittest.TestCase):
    def test_unavailable_external_route_holds_before_provider(self):
        tool = ServiceEquipment(slack_token_loader=lambda: "unused",
                                opener=lambda *_a, **_k: self.fail("provider must not run"))
        tool._work_handoff.validate_destination = lambda _channel: False
        result = tool.call("slack_post_message", {
            "channel_id": "C123",
            "text": "Neutral status.",
        })
        self.assertTrue(result["isError"])
        self.assertEqual(result["result"]["state"], "PUBLISHER_ROUTE_REQUIRED")


    def test_every_unverified_slack_write_holds_before_token_or_provider(self):
        tool = ServiceEquipment(
            slack_token_loader=lambda: self.fail("write must not load token"),
            opener=lambda *_a, **_k: self.fail("provider must not run"),
        )
        for method in ("reactions.add", "conversations.invite", "files.upload"):
            with self.subTest(method=method), self.assertRaises(EquipmentError) as raised:
                tool.slack(method, {"channel": "C123"})
            self.assertEqual(raised.exception.code, "outbound_field_mapping_missing")

    def test_verified_unmapped_slack_write_still_holds_before_provider(self):
        tool = ServiceEquipment(
            slack_token_loader=lambda: self.fail("unmapped write must not load token"),
            opener=lambda *_a, **_k: self.fail("provider must not run"),
        )
        tool._slack_write_route_verified = lambda: True
        with self.assertRaises(EquipmentError) as raised:
            tool.slack("reactions.add", {"channel": "C123"})
        self.assertEqual(raised.exception.code, "outbound_field_mapping_missing")

    def test_internal_slack_text_does_not_enter_publication_classifier(self):
        requests = []
        def opener(request, **_kwargs):
            requests.append(request)
            return io.BytesIO(b'{"ok":true,"channel":"C0BU51F1PL3","ts":"1.2","message":{"text":"Astra status."}}')
        tool = ServiceEquipment(
            slack_token_loader=lambda: "existing-token",
            opener=opener,
        )
        tool._slack_write_route_verified = lambda _channel=None: True
        result = tool.slack("chat.postMessage", {
            "channel": "C0BU51F1PL3", "text": "Astra status.", "parse": "none",
        })
        self.assertTrue(result["ok"])
        self.assertIn(b"Astra status.", requests[0].data)

    def test_slack_invisible_action_values_are_not_identity_matches(self):
        tool = ServiceEquipment(
            slack_token_loader=lambda: self.fail("blocked write must not load token"),
            opener=lambda *_a, **_k: self.fail("provider must not run"),
        )
        payload = {
            "text": "Neutral visible text.",
            "blocks": [{
                "type": "actions",
                "block_id": "Codex",
                "elements": [{
                    "type": "button",
                    "action_id": "Claude",
                    "value": "Opus Fable Astra Sol Grok",
                    "text": {"type": "plain_text", "text": "Continue"},
                }],
            }],
        }
        with self.assertRaises(EquipmentError) as raised:
            tool.slack("chat.postMessage", payload)
        self.assertEqual(raised.exception.code, "outbound_field_mapping_missing")

    def test_slack_reads_use_query_and_secret_stays_in_header(self):
        requests = []
        def opener(request, **kwargs):
            requests.append(request)
            return io.BytesIO(b'{"ok":true,"messages":[]}')
        tool = ServiceEquipment(slack_token_loader=lambda: "[REDACTED]", opener=opener)
        result = tool.call("slack_read_thread", {"channel_id": "C123", "thread_ts": "1.2"})
        self.assertFalse(result["isError"])
        request = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("channel=C123", request.full_url)
        self.assertIn("ts=1.2", request.full_url)
        self.assertNotIn("synthetic", request.full_url)
        self.assertIsNone(request.data)
        self.assertNotIn("synthetic", json.dumps(result))

    def test_provider_secret_fields_and_token_strings_are_scrubbed(self):
        result = redacted({"nested": [{"bot_token": "example", "text": "[REDACTED] [REDACTED]"}], "normal": "read_count"})
        self.assertNotIn("SYNTHETIC", json.dumps(result))
        self.assertEqual(result["normal"], "read_count")

    def test_provider_redaction_scrubs_nested_urls_and_metadata(self):
        source = {
            "callback": "https://login.example/cb?state=keep&code=VALUE1#id_token=VALUE2&view=ok",
            "download": "https://files.example/object.txt?x-sig=VALUE3&part=7",
            "headers": {"Authorization": "VALUE4", "x_api_key": "VALUE5"},
            "cookie": "VALUE6",
            "ordinary": "https://example.test/path?mode=read#section",
        }
        result = redacted(source)
        encoded = json.dumps(result)
        for value in ("VALUE1", "VALUE2", "VALUE3", "VALUE4", "VALUE5", "VALUE6"):
            self.assertNotIn(value, encoded)
        self.assertIn("state=keep", result["callback"])
        self.assertIn("view=ok", result["callback"])
        self.assertIn("part=7", result["download"])
        self.assertEqual(result["ordinary"], source["ordinary"])
        self.assertEqual(result["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(result["headers"]["x_api_key"], "[REDACTED]")
        self.assertEqual(result["cookie"], "[REDACTED]")

    def test_service_exception_metadata_is_recursively_redacted(self):
        tool = ServiceEquipment(slack_token_loader=lambda: "unused")

        def fail(_name, _arguments):
            exc = EquipmentError(
                "failed https://login.example/cb?code=VALUE7&state=keep",
                private_instruction="retry https://files.example/a?sig=VALUE8&part=2",
                matched_terms=("https://x.example/#refresh_token=VALUE9",),
            )
            raise exc

        tool._call = fail
        result = tool.call("synthetic", {})
        encoded = json.dumps(result)
        for value in ("VALUE7", "VALUE8", "VALUE9"):
            self.assertNotIn(value, encoded)
        self.assertIn("state=keep", result["message"])
        self.assertIn("part=2", result["private_instruction"])

    def test_gh_uses_fixed_host_stdin_and_no_shell(self):
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, '{"sha":"abc"}', '')
        equipment = ServiceEquipment(gh_runner=runner)
        equipment.github("repos/owner/repo/git/trees", method="POST", payload={"tree": []})
        command, kwargs = calls[0]
        self.assertEqual(command[1:5], ["api", "--include", "--hostname", "github.com"])
        self.assertEqual(json.loads(kwargs["input"]), {"tree": []})
        self.assertNotIn("shell", kwargs)

    def test_external_url_cannot_replace_repository_shape(self):
        equipment = ServiceEquipment(gh_runner=lambda *a, **k: self.fail("provider must not run"))
        result = equipment.call("github_read_file", {"repository": "https://elsewhere.invalid/x", "path": "a"})
        self.assertTrue(result["isError"])

    def test_same_logical_call_is_not_executed_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            effects = []
            runner = lambda n, a: effects.append(a) or {"ok": True}
            first = calls.execute_journaled("equipment:r", "c", "slack_post_message", {"text": "same"}, runner)
            second = calls.execute_journaled("equipment:r", "c", "slack_post_message", {"text": "same"}, runner)
            conflict = calls.execute_journaled("equipment:r", "c", "slack_post_message", {"text": "different"}, runner)
            self.assertEqual(first, second)
            self.assertEqual(len(effects), 1)
            self.assertEqual(conflict["error"], "call_id_reused_with_different_arguments")
            calls.close()

    def test_interrupted_effect_is_reported_unknown_and_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            import hashlib
            digest = hashlib.sha256(b'{}').hexdigest()
            calls._db.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)", ("r", "c", "write", digest, "started", None, 1))
            calls._db.commit()
            result = calls.execute_journaled("r", "c", "write", {}, lambda n,a: self.fail("must reconcile first"))
            self.assertEqual(result["error"], "tool_effect_unknown_after_interruption")
            calls.close()

    def test_catalog_is_injected_into_actual_model_loop(self):
        class Public:
            def tools(self, **kwargs): return [{"name": "read_observatory", "inputSchema": {}}]
            def call(self, name, args): return {"public": True}
        class Model:
            def turn(self, peer, prompt, *, cancelled=None, on_submitted=None):
                self.prompt = prompt
                return "done"
        model = Model()
        catalog = CombinedCatalog(Public())
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            self.assertEqual(ToolLoop(model, catalog, calls).run("r", "any-role", "work"), "done")
            self.assertIn('"name":"slack_post_message"', model.prompt)
            self.assertIn('"name":"github_commit_files"', model.prompt)
            self.assertEqual(len(Public().tools()), 1)
            calls.close()

    def test_cancel_after_model_return_prevents_external_tool_effect(self):
        cancel_event = threading.Event()
        class Model:
            def turn(self, peer, prompt, *, cancelled=None, on_submitted=None):
                cancel_event.set()
                return '<commons_tool_call>{"call_id":"write","name":"slack_post_message","arguments":{}}</commons_tool_call>'
        class Catalog:
            def tools(self): return [{"name": "slack_post_message"}]
            def call(self, name, args): raise AssertionError("cancelled request must not post")
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            with self.assertRaises(InterruptedError):
                ToolLoop(Model(), Catalog(), calls).run("r", "role", "work", cancel_event)
            self.assertEqual(calls._db.execute("select count(*) from tool_calls").fetchone()[0], 0)
            calls.close()

    def test_restart_marks_running_request_interrupted_without_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            events = EventStore(Path(directory)/"events.jsonl")
            events.append(request_id="unfinished", peer="TESSERA", status="running")
            gateway = ToolGateway(("127.0.0.1", 0), None, events, None, None)
            self.assertEqual(events.request("unfinished", 0)["status"], "interrupted")
            self.assertEqual(gateway.cancel("unfinished")["event"]["status"], "interrupted")
            self.assertEqual(gateway._peer_queues, {})
            gateway.server_close()

    def test_slack_envelope_accepts_connector_footer_not_quoted_prose(self):
        envelope = '<commons_equipment_request>{"request_id":"r","call_id":"c","name":"equipment_catalog"}</commons_equipment_request>'
        self.assertEqual(parse_request(envelope + '\nSent using connector')["name"], "equipment_catalog")
        self.assertIsNone(parse_request("Example: " + envelope))
        with self.assertRaises(ValueError):
            parse_request('<commons_equipment_request>null</commons_equipment_request>')


    def test_unverified_carrier_holds_before_parsing_or_replying(self):
        class Services:
            def __init__(self):
                self.calls = 0
            def _slack_write_route_verified(self, _channel_id=None):
                return False
            def call(self, _name, _args):
                self.calls += 1
                raise AssertionError("unverified route must not reply")
        class Catalog:
            def __init__(self):
                self.services = Services()

        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog()
            carrier = SlackEquipmentCarrier(
                catalog,
                None,
                {"channel_id": "C123"},
                Path(directory) / "cursor.json",
            )
            result = carrier.process({
                "ts": "1.1",
                "text": "<commons_equipment_request>null</commons_equipment_request>",
            })
            self.assertEqual(result["code"], "outbound_sender_identity_unverified")
            self.assertFalse(result["delivered"])
            self.assertEqual(catalog.services.calls, 0)

    def test_idle_carrier_cursor_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"cursor.json"
            first = SlackEquipmentCarrier(None, None, {"channel_id": "C123"}, path)
            second = SlackEquipmentCarrier(None, None, {"channel_id": "C123"}, path)
            self.assertEqual(first.cursor, second.cursor)

    def test_slack_escaped_envelope_replays_actual_claude_connector_message(self):
        # TENON's actual request 1788573393.644269 was escaped in Slack text,
        # although connector reads rendered the literal envelope brackets.
        text = '&lt;commons_equipment_request&gt;{"request_id":"tenon-m3-equipment-read-20260905-01","call_id":"source","name":"github_read_file","arguments":{"repository":"woahwhattheheck/commons","path":"integrations/shared_equipment/peers.py","ref":"38e729aef8f0bd548db3e442ec6de57e706f1f6f"}}&lt;/commons_equipment_request&gt;\nTENON, local harness: Claude Code desktop app. *Sent using* <@U0BRJUMRG8K>'
        self.assertEqual(parse_request(text)["arguments"]["path"], "integrations/shared_equipment/peers.py")
        escaped_value = '&lt;commons_equipment_request&gt;{"request_id":"r","call_id":"c","name":"read","arguments":{"literal":"&amp;lt;tag&amp;gt; &amp; value"}}&lt;/commons_equipment_request&gt;'
        self.assertEqual(parse_request(escaped_value)["arguments"]["literal"], "&lt;tag&gt; & value")
        self.assertIsNone(parse_request("Example: " + text))

    def test_slack_cursor_precision_replays_observed_missing_reply_case(self):
        # Actual provider observation: oldest .4635916 silently omitted reply
        # 1788571985.555399; .463591 returned it. Do not reintroduce clock precision.
        self.assertEqual(slack_timestamp("1788571951.4635916"), "1788571951.463591")
        class Services:
            def _slack_write_route_verified(self, _channel_id=None): return True
            def slack(self, method, args):
                return {"ok": True, "messages": [] if args["oldest"].endswith("5916") else [{"ts":"1788571985.555399", "text":"ordinary coordination"}]}
        class Catalog:
            services = Services()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"cursor.json"
            path.write_text(json.dumps({"cursor":"1788571951.4635916"}), encoding="utf-8")
            carrier = SlackEquipmentCarrier(Catalog(), None, {"channel_id":"C0BU51F1PL3", "thread_ts":"1788567066.179399"}, path)
            carrier.once()
            self.assertEqual(carrier.cursor, "1788571985.555399")

    def test_carrier_replay_shares_http_call_key_and_returns_exact_result(self):
        class Services:
            def __init__(self): self.sent = []
            def _slack_write_route_verified(self, _channel_id=None): return True
            def call(self, n, a): self.sent.append(a); return {"result": {"ok": True, "ts": "4.1"}}
        class Catalog:
            def __init__(self): self.services = Services(); self.effects = 0
            def call(self, n, a): self.effects += 1; return {"answer": "useful"}
        with tempfile.TemporaryDirectory() as directory:
            calls = ToolCallStore(Path(directory) / "calls.db")
            catalog = Catalog()
            carrier = SlackEquipmentCarrier(catalog, calls, {"channel_id": "C123"}, Path(directory)/"cursor.json")
            message = {"ts": "1.1", "text": '<commons_equipment_request>{"request_id":"r","call_id":"c","name":"read"}</commons_equipment_request>'}
            carrier.process(message)
            carrier.process(message)
            self.assertEqual(catalog.effects, 1)
            self.assertEqual(len(catalog.services.sent), 1)
            self.assertIn('"answer": "useful"', catalog.services.sent[0]["text"])
            calls.close()


if __name__ == "__main__":
    unittest.main()
