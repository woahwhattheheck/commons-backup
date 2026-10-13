import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations" / "commons_publication_hooks"))
from slack_route_mapping import slack_route_mapping, slack_route_allowed

class SlackHookMappingTests(unittest.TestCase):
    def test_connector_send_uses_actual_text_and_owner_fixed_sender(self):
        route = slack_route_mapping("mcp__codex_apps__slack_slack_send_message", {
            "channel_id": "C0BRGMDQB6G", "message": "handoff", "thread_ts": "1788567066.179399"
        })
        self.assertEqual(route.kind, "connector_send")
        self.assertEqual(route.selected_fields, {"message": "handoff"})
        self.assertIn("fixed owner-connected", route.sender_contract)

    def test_gateway_send_maps_text_field(self):
        route = slack_route_mapping("mcp__commons_gateway__slack_post_message", {
            "channel_id": "C0BRGMDQB6G", "text": "handoff"
        })
        self.assertEqual(route.kind, "gateway_send")
        self.assertEqual(route.selected_fields, {"text": "handoff"})

    def test_cloud_native_alias_is_exactly_mapped_but_remains_held_without_channel_read(self):
        args = {"channel_id": "C0BU51F1PL3", "message": "handoff", "thread_ts": "1790851459.659859"}
        route = slack_route_mapping("mcp__Slack__slack_send_message", args)
        self.assertEqual(route.kind, "cloud_destination_unverified")
        self.assertEqual(route.selected_fields, {"message": "handoff"})
        self.assertFalse(slack_route_allowed("mcp__Slack__slack_send_message", args))

    def test_file_upload_is_staged_and_final_share_maps_comment(self):
        start = slack_route_mapping("mcp__codex_apps__slack_slack_get_file_upload_url", {
            "filename": "handoff-x.patch", "content_length": 3, "snippet_type": "diff"
        })
        finish = slack_route_mapping("mcp__codex_apps__slack_slack_complete_file_upload", {
            "file_id": "F0ABC12345", "channel_id": "C0BRGMDQB6G", "initial_comment": "handoff", "title": "patch"
        })
        self.assertEqual(start.kind, "private_upload_stage")
        self.assertEqual(finish.kind, "connector_complete_upload")
        self.assertEqual(finish.selected_fields, {"initial_comment": "handoff", "title": "patch"})

    def test_identity_override_and_unknown_field_are_denied(self):
        base = {"channel_id": "C0BRGMDQB6G", "message": "handoff"}
        self.assertFalse(slack_route_allowed("mcp__codex_apps__slack_slack_send_message", {**base, "username": "Claude"}))
        self.assertFalse(slack_route_allowed("mcp__codex_apps__slack_slack_send_message", {**base, "unknown": "x"}))
        self.assertFalse(slack_route_allowed("mcp__codex_apps__slack_slack_send_message", {"channel_id": "C0BRGMDQB6G", "message": 7}))
        self.assertFalse(slack_route_allowed("mcp__codex_apps__slack_slack_schedule_message", {**base, "post_at": "123"}))
        self.assertFalse(slack_route_allowed("other_mcp__codex_apps__slack_slack_send_message", base))

if __name__ == "__main__":
    unittest.main(verbosity=2)
