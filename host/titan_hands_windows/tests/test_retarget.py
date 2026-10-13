from __future__ import annotations

import json
import unittest

from host.titan_hands.mcp_one import TOOL as MCP_ONE_TOOL
from host.titan_hands.mcp_server import ACTION_PROPERTY, TOOLS as UNIFIED_TOOLS
from host.titan_hands_windows.mcp_server import TOOLS as WINDOWS_TOOLS, dispatch
from host.titan_hands_windows.retarget import prepare_action
from host.titan_hands_windows.server import TitanHandsServer


BACKEND_ACTIONS = [
    "invoke",
    "set_value",
    "toggle",
    "expand",
    "collapse",
    "select",
    "focus",
    "click",
    "type_text",
    "key",
    "scroll",
    "launch",
    "wait",
    "done",
]


class ScriptedBackend:
    def __init__(self, nodes, focus_id="", collapse_on_clear=False, sticky_values=None):
        self.nodes = {node["id"]: dict(node) for node in nodes}
        self.focus_id = focus_id
        self.calls = []
        self.closed = False
        self.collapse_on_clear = collapse_on_clear
        self.sticky_values = dict(sticky_values or {})

    def request(self, message):
        self.calls.append(message)
        op = message.get("op")
        if op == "capabilities":
            return {"ok": True, "actions": list(BACKEND_ACTIONS)}
        if op == "snapshot":
            return {
                "ok": True,
                "nodes": [dict(node) for node in self.nodes.values()],
                "focus_id": self.focus_id,
            }
        if op == "action":
            action = dict(message.get("action") or {})
            action_type = str(action.get("type") or "")
            node_id = str(action.get("id") or "")
            if node_id and node_id not in self.nodes and action_type in {
                "invoke",
                "click",
                "set_value",
                "type_text",
                "toggle",
                "focus",
                "select",
            }:
                return {
                    "ok": False,
                    "kind": "failure",
                    "failure_reason": "ELEMENT_STALE",
                    "message": f"element is absent or stale: {node_id}",
                }
            if action_type == "set_value" and node_id in self.nodes:
                if str(action.get("value") or "") == "" and self.collapse_on_clear:
                    self.nodes.pop(node_id, None)
                else:
                    self.nodes[node_id]["value"] = str(action.get("value") or "")
                    if node_id in self.sticky_values:
                        self.nodes[node_id]["value"] = self.sticky_values[node_id]
            if action_type == "invoke" and self.nodes.get(node_id, {}).get("name") == "Idle":
                self.nodes[node_id]["name"] = "Done"
            return {"ok": True, "kind": "action_outcome", "action": action_type, "id": node_id}
        raise AssertionError(message)

    def close(self):
        self.closed = True


def _edit(node_id="field", value="", focused=True, name="Search"):
    states = ["enabled", "focusable"]
    if focused:
        states.append("focused")
    return {
        "id": node_id,
        "role": "Edit",
        "name": name,
        "value": value,
        "actions": ["set_value", "click"],
        "states": states,
    }


class RetargetVerifyTests(unittest.TestCase):
    def _server(self, nodes, focus_id="", collapse_on_clear=False, sticky_values=None):
        backend = ScriptedBackend(
            nodes,
            focus_id=focus_id,
            collapse_on_clear=collapse_on_clear,
            sticky_values=sticky_values,
        )
        return TitanHandsServer(backend), backend

    def test_stale_id_retargets_by_name(self):
        server, backend = self._server(
            [{"id": "w_aaaabbbbccccddddeeee", "role": "Button", "name": "Save", "actions": ["invoke", "click"]}]
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "action": {
                    "type": "invoke",
                    "id": "w_deadbeefdeadbeefdead",
                    "name": "Save",
                },
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["retarget"]["to_id"], "w_aaaabbbbccccddddeeee")
        self.assertEqual(backend.calls[-2]["action"]["id"], "w_aaaabbbbccccddddeeee")
        server.close()

    def test_set_text_alias_uses_focused_editable(self):
        field = _edit()
        server, backend = self._server(
            [
                {"id": "w_buttonbuttonbuttonbtn", "role": "Button", "name": "Go", "actions": ["invoke", "click"]},
                field,
            ],
            focus_id="field",
        )
        server.handle({"op": "observe"})
        result = server.handle({"op": "act", "action": {"action": "set_text", "text": "hello"}})
        self.assertTrue(result["ok"])
        sent = backend.calls[-2]["action"]
        self.assertEqual(sent["type"], "set_value")
        self.assertEqual(sent["id"], "field")
        self.assertEqual(result["verification"]["status"], "confirmed")
        self.assertIn("text IS in the field", result["verification"]["message"])
        server.close()

    def test_non_field_set_value_retargets_to_lone_edit(self):
        server, backend = self._server(
            [
                {"id": "w_buttonbuttonbuttonbtn", "role": "Button", "name": "Go", "actions": ["invoke", "click"]},
                _edit("field", focused=False),
            ]
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "action": {"type": "set_value", "id": "w_buttonbuttonbuttonbtn", "value": "cats"},
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["retarget"]["to_id"], "field")
        self.assertEqual(backend.calls[-2]["action"]["id"], "field")
        self.assertEqual(result["verification"]["status"], "confirmed")
        server.close()

    def test_explicit_label_beats_focused_editable(self):
        server, backend = self._server(
            [
                _edit("email", focused=True, name="Email"),
                _edit("search", focused=False, name="Search"),
            ],
            focus_id="email",
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "action": {
                    "type": "set_value",
                    "id": "w_deadbeefdeadbeef",
                    "name": "Search",
                    "value": "secret",
                },
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["retarget"]["to_id"], "search")
        self.assertEqual(result["retarget"]["reason"], "label_match")
        self.assertEqual(backend.calls[-2]["action"]["id"], "search")
        self.assertEqual(backend.nodes["search"]["value"], "secret")
        self.assertEqual(backend.nodes["email"].get("value", ""), "")
        server.close()

    def test_ambiguous_set_value_label_fails_closed(self):
        server, backend = self._server(
            [
                _edit("one", focused=False, name="Search"),
                _edit("two", focused=False, name="Search"),
            ]
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {"op": "act", "action": {"type": "set_value", "name": "Search", "value": "secret"}}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_reason"], "TARGET_AMBIGUOUS")
        self.assertFalse(any(call.get("op") == "action" for call in backend.calls))
        server.close()

    def test_set_value_verifies_landed_text(self):
        server, _backend = self._server([_edit()], focus_id="field")
        server.handle({"op": "observe"})
        result = server.handle(
            {"op": "act", "action": {"type": "set_value", "id": "field", "value": "typed-in"}}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["status"], "confirmed")
        self.assertIn("typed-in", _backend.nodes["field"]["value"])
        server.close()

    def test_invoke_unchanged_screen_is_contradicted(self):
        server, _backend = self._server(
            [{"id": "noop", "role": "Button", "name": "Still", "actions": ["invoke", "click"]}]
        )
        server.handle({"op": "observe"})
        result = server.handle({"op": "act", "action": {"type": "invoke", "id": "noop"}})
        self.assertTrue(result["ok"], "backend success is not proof")
        self.assertEqual(result["verification"]["status"], "contradicted")
        self.assertIn("UNCHANGED", result["verification"]["message"])
        server.close()

    def test_assert_reports_state_without_backend_action(self):
        server, backend = self._server(
            [{"id": "go", "role": "Button", "name": "Go", "actions": ["invoke"], "states": ["enabled"]}]
        )
        server.handle({"op": "observe"})
        before = len(backend.calls)
        result = server.handle({"op": "act", "action": {"type": "verify", "id": "go", "state": "enabled"}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "assert")
        self.assertEqual(result["verification"]["status"], "confirmed")
        self.assertFalse(any(call.get("op") == "action" for call in backend.calls[before:]))
        missing = server.handle(
            {"op": "act", "action": {"type": "assert", "id": "go", "state": "selected"}}
        )
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["failure_reason"], "ASSERT_CONTRADICTED")
        self.assertEqual(missing["verification"]["status"], "contradicted")
        server.close()

    def test_contradicted_assert_is_mcp_error(self):
        server, backend = self._server(
            [{"id": "go", "role": "Button", "name": "Go", "actions": ["invoke"], "states": ["enabled"]}]
        )
        server.handle({"op": "observe"})
        message = dispatch(
            server,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "hands_act",
                    "arguments": {
                        "action": {"type": "assert", "id": "go", "state": "selected"},
                    },
                },
            },
        )
        self.assertTrue(message["result"]["isError"])
        body = json.loads(message["result"]["content"][0]["text"])
        self.assertFalse(body["ok"])
        self.assertEqual(body["failure_reason"], "ASSERT_CONTRADICTED")
        self.assertFalse(any(call.get("op") == "action" for call in backend.calls))
        server.close()

    def test_clear_removed_target_is_unchecked(self):
        server, _backend = self._server(
            [_edit("field", value="old")],
            focus_id="field",
            collapse_on_clear=True,
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {"op": "act", "action": {"type": "set_value", "id": "field", "value": ""}}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["status"], "unchecked")
        self.assertFalse(result["verification"]["ok"])
        self.assertIn("left the tree", result["verification"]["message"])
        server.close()

    def test_value_mismatch_not_overwritten_by_expect(self):
        server, _backend = self._server(
            [_edit("field", value="old")],
            focus_id="field",
            sticky_values={"field": "old"},
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "action": {
                    "type": "set_value",
                    "id": "field",
                    "value": "new",
                    "expect": "text entered in field",
                },
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["status"], "contradicted")
        self.assertIn("does not contain 'new'", result["verification"]["message"])
        self.assertNotIn("✓", result["verification"]["message"])
        server.close()

    def test_mystery_type_is_forwarded(self):
        server, backend = self._server(
            [{"id": "go", "role": "Button", "name": "Go", "actions": ["invoke", "click"]}]
        )
        result = server.handle({"op": "act", "action": {"type": "mystery_verb", "payload": "keep-me"}})
        self.assertTrue(result["ok"])
        sent = backend.calls[-2]["action"] if backend.calls[-1]["op"] == "snapshot" else backend.calls[-1]["action"]
        self.assertEqual(sent["type"], "mystery_verb")
        self.assertEqual(sent["payload"], "keep-me")
        server.close()

    def test_ambiguous_label_does_not_guess(self):
        server, backend = self._server(
            [
                {"id": "one", "role": "Button", "name": "Save", "actions": ["invoke"]},
                {"id": "two", "role": "Button", "name": "Save", "actions": ["invoke"]},
            ]
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {"op": "act", "action": {"type": "invoke", "id": "missing", "name": "Save"}}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_reason"], "TARGET_AMBIGUOUS")
        self.assertFalse(any(call.get("op") == "action" for call in backend.calls))
        server.close()

    def test_capabilities_keep_backend_actions(self):
        server, _backend = self._server([])
        result = server.handle({"op": "capabilities"})
        for action in BACKEND_ACTIONS:
            self.assertIn(action, result["actions"])
        self.assertIn("assert", result["actions"])
        self.assertTrue(result["retarget"])
        self.assertTrue(result["verify_after"])
        self.assertEqual(result["implementation"], "windows-uia-adapter")
        server.close()

    def test_id_sentence_salvaged_as_text(self):
        prepared = prepare_action(
            {"type": "set_text", "id": "I argue the case"},
            nodes={"field": _edit()},
            meta={"focus_id": "field"},
        )
        self.assertIsNone(prepared.failure)
        self.assertEqual(prepared.action["type"], "set_value")
        self.assertEqual(prepared.action["id"], "field")
        self.assertEqual(prepared.action["value"], "I argue the case")

    def test_observe_after_false_does_not_claim_success(self):
        server, _backend = self._server([_edit()], focus_id="field")
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "observe_after": False,
                "action": {"type": "set_value", "id": "field", "value": "x"},
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["status"], "unchecked")
        self.assertFalse(result["verification"]["ok"])
        server.close()

    def test_expect_checks_visible_text(self):
        server, _backend = self._server(
            [{"id": "title", "role": "Text", "name": "Search results for cats", "actions": []}]
        )
        server.handle({"op": "observe"})
        result = server.handle(
            {
                "op": "act",
                "action": {"type": "wait", "milliseconds": 0},
                "expect": "search results for cats",
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["status"], "confirmed")
        server.close()

    def test_mcp_act_still_listed(self):
        server, _backend = self._server([])
        listed = dispatch(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        self.assertEqual(names, ["hands_observe", "hands_act", "hands_capture", "hands_capabilities"])
        server.close()

    def test_tools_list_advertises_assert_and_expect(self):
        self.assertIn("state", ACTION_PROPERTY["properties"])
        self.assertIn("that", ACTION_PROPERTY["properties"])
        self.assertIn("expect", ACTION_PROPERTY["properties"])
        self.assertIn("assert", ACTION_PROPERTY["properties"]["type"]["description"])
        unified_act = next(tool for tool in UNIFIED_TOOLS if tool["name"] == "hands_act")
        self.assertIn("expect", unified_act["inputSchema"]["properties"])
        self.assertIs(MCP_ONE_TOOL["inputSchema"]["properties"]["action"], ACTION_PROPERTY)
        self.assertIn("expect", MCP_ONE_TOOL["inputSchema"]["properties"])
        windows_act = next(tool for tool in WINDOWS_TOOLS if tool["name"] == "hands_act")
        win_action = windows_act["inputSchema"]["properties"]["action"]
        self.assertIn("state", win_action["properties"])
        self.assertIn("that", win_action["properties"])
        self.assertIn("expect", win_action["properties"])
        self.assertIn("expect", windows_act["inputSchema"]["properties"])
        self.assertNotIn("required", win_action)


if __name__ == "__main__":
    unittest.main()
