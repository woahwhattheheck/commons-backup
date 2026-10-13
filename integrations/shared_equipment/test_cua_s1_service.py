"""Shared CUA-S1 equipment catalog and dispatch behavior."""

import unittest
from unittest.mock import patch

from integrations.shared_equipment.services import ServiceEquipment


class FakeDriver:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class CuaS1ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ServiceEquipment()
        self.request = {
            "url": "https://example.invalid/form",
            "form_title": "Example form",
            "entities": [{"label": "Phone", "value": "555-0142"}],
            "checkpoint": "C:/model/cua-s1-forms.safetensors",
        }

    def test_catalog_exposes_typed_peer_tool(self):
        tool = next(item for item in self.service.tools() if item["name"] == "cua_s1_form")
        self.assertEqual(tool["inputSchema"]["properties"]["entities"]["type"], "array")
        self.assertEqual(set(tool["inputSchema"]["required"]), {"url", "form_title", "entities"})
        self.assertEqual(tool["inputSchema"]["properties"]["execute"]["type"], "boolean")

    def test_dispatch_defaults_to_dry_run_and_closes_driver(self):
        driver = FakeDriver()
        with patch("host.cua_s1_browser.connect_cdp", return_value=(driver, object())) as connect, \
             patch("host.cua_s1_forms.run_with_driver", return_value={"ok": True, "execution_order": []}) as run:
            outcome = self.service.call("cua_s1_form", self.request)
        self.assertFalse(outcome["isError"])
        self.assertTrue(driver.closed)
        connect.assert_called_once_with(self.request["url"], endpoint="http://127.0.0.1:9222", allow_submit=False)
        arguments = run.call_args.kwargs
        self.assertFalse(arguments["execute"])
        self.assertFalse(arguments["submit"])
        self.assertEqual(arguments["entities"][0].value, "555-0142")

    def test_execution_flags_are_explicit_and_cleanup_runs_after_error(self):
        driver = FakeDriver()
        request = {**self.request, "execute": True, "submit": True}
        with patch("host.cua_s1_browser.connect_cdp", return_value=(driver, object())) as connect, \
             patch("host.cua_s1_forms.run_with_driver", side_effect=RuntimeError("test failure")):
            outcome = self.service.call("cua_s1_form", request)
        self.assertTrue(outcome["isError"])
        self.assertTrue(driver.closed)
        connect.assert_called_once_with(request["url"], endpoint="http://127.0.0.1:9222", allow_submit=True)

    def test_invalid_boolean_fails_before_connect(self):
        with patch("host.cua_s1_browser.connect_cdp") as connect:
            outcome = self.service.call("cua_s1_form", {**self.request, "execute": "yes"})
        self.assertTrue(outcome["isError"])
        connect.assert_not_called()

    def test_cache_discovery_uses_official_files_without_network(self):
        driver = FakeDriver()
        calls = []
        def cached(repo, filename, **kwargs):
            calls.append((repo, filename, kwargs))
            return "C:/cache/" + filename
        request = {key: value for key, value in self.request.items() if key != "checkpoint"}
        with patch("huggingface_hub.hf_hub_download", side_effect=cached), \
             patch("host.cua_s1_browser.connect_cdp", return_value=(driver, object())), \
             patch("host.cua_s1_forms.run_with_driver", return_value={"ok": True}) as run:
            self.service.call("cua_s1_form", request)
        self.assertEqual([item[1] for item in calls], ["cua-s1-forms.safetensors", "cua-s1-forms.json"])
        self.assertTrue(all(item[2] == {"local_files_only": True} for item in calls))
        self.assertEqual(run.call_args.kwargs["checkpoint"].name, "cua-s1-forms.safetensors")


if __name__ == "__main__":
    unittest.main()
