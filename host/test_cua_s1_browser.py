"""Contract checks for the direct-CDP CUA-S1 adapter without a live browser."""

import unittest

from cua_s1.driver import DriverError

from host.cua_s1_browser import BrowserFormDriver


class FakeLocator:
    def __init__(self, page, token):
        self.page, self.token = page, token

    def count(self):
        return int(self.token in self.page.controls)

    def evaluate(self, _script):
        item = self.page.controls[self.token]
        return {**{key: item[key] for key in ("tag", "type", "disabled", "value", "checked", "label")},
                "liveToken": item["element_token"]}

    def fill(self, value):
        self.page.controls[self.token]["value"] = value

    def input_value(self):
        return self.page.controls[self.token]["value"]

    def is_checked(self):
        return self.page.controls[self.token]["checked"]

    def click(self):
        self.page.controls[self.token]["checked"] = not self.is_checked()


class FakePage:
    url = "https://example.test/form"

    def __init__(self):
        self.closed = False
        self.controls = {
            "field": {"element_index": 0, "element_token": "field", "role": "Edit", "label": "Name",
                      "value": "", "checked": None, "actions": ["set_value"], "tag": "input", "type": "text", "disabled": False},
            "check": {"element_index": 1, "element_token": "check", "role": "CheckBox", "label": "Agree",
                      "value": "on", "checked": False, "actions": ["click"], "tag": "input", "type": "checkbox", "disabled": False},
            "send": {"element_index": 2, "element_token": "send", "role": "Button", "label": "Submit",
                     "value": "", "checked": None, "actions": ["click"], "tag": "button", "type": "submit", "disabled": False},
            "radio": {"element_index": 3, "element_token": "radio", "role": "RadioButton", "label": "Option",
                      "value": "a", "checked": False, "actions": ["click"], "tag": "input", "type": "radio", "disabled": False},
        }

    def is_closed(self):
        return self.closed

    def title(self):
        return "Example form"

    def evaluate(self, _script):
        return [dict(control) for control in self.controls.values()]

    def locator(self, selector):
        return FakeLocator(self, selector.split('"')[1])


class BrowserFormDriverTests(unittest.TestCase):
    def setUp(self):
        self.page = FakePage()
        self.driver = BrowserFormDriver(self.page)
        self.target = self.driver.target

    def test_fill_and_check_read_back_through_upstream_contract(self):
        initial = self.driver.window_state(self.target)
        self.assertTrue(initial.elements_complete)
        self.assertEqual(len(initial.elements), 4)
        self.assertTrue(self.driver.supports_value_mutation())
        filled = self.driver.set_value(self.target, "field", "Ada")
        self.assertEqual(filled.action["effect"], "confirmed")
        self.assertEqual(filled.observation.elements[0].value, "Ada")
        checked = self.driver.click(self.target, "check", delivery_mode="background")
        self.assertTrue(checked.observation.elements[1].checked)

    def test_missing_stale_and_submit_fail_closed(self):
        self.driver.window_state(self.target)
        with self.assertRaises(DriverError):
            self.driver.set_value(self.target, "missing", "x")
        with self.assertRaises(DriverError) as caught:
            self.driver.click(self.target, "send", delivery_mode="background")
        self.assertEqual(caught.exception.code, "submit_not_enabled")
        self.page.controls.pop("field")
        with self.assertRaises(DriverError):
            self.driver.set_value(self.target, "field", "x")

    def test_url_change_fails(self):
        self.page.url = "https://example.test/other"
        with self.assertRaises(DriverError) as caught:
            self.driver.window_state(self.target)
        self.assertEqual(caught.exception.code, "stale_browser_target")

    def test_value_change_after_snapshot_rejects_stale_plan(self):
        self.driver.window_state(self.target)
        self.page.controls["field"]["value"] = "Someone else's edit"
        with self.assertRaises(DriverError) as caught:
            self.driver.set_value(self.target, "field", "Ada")
        self.assertEqual(caught.exception.code, "element_stale")

    def test_tokens_stable_and_radio_not_fillable(self):
        first = self.driver.window_state(self.target)
        second = self.driver.window_state(self.target)
        self.assertEqual([e.element_token for e in first.elements],
                         [e.element_token for e in second.elements])
        with self.assertRaises(DriverError) as caught:
            self.driver.set_value(self.target, "radio", "changed")
        self.assertEqual(caught.exception.code, "unsupported_element_action")

    def test_close_disconnects_without_browser_close(self):
        class Browser:
            def close(self):
                raise AssertionError("attached browser must not be closed")

        class Runtime:
            stopped = False

            def stop(self):
                self.stopped = True

        runtime = Runtime()
        driver = BrowserFormDriver(self.page, browser=Browser(), playwright=runtime)
        driver.close()
        self.assertTrue(runtime.stopped)


if __name__ == "__main__":
    unittest.main()
