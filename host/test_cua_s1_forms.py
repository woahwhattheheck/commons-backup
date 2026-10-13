"""Behavioral checks for the CUA-S1 model adapter and execution boundary."""

import importlib.util
import os
import unittest
from pathlib import Path

from cua_s1.driver import MutationResult, WindowSnapshot, WindowTarget
from cua_s1.schema import Decision, Element, Entity


SPEC = importlib.util.spec_from_file_location("cua_s1_forms_commons", Path(__file__).with_name("cua_s1_forms.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FixedBackend:
    def __init__(self, actions):
        self.actions = actions

    def plan(self, title, elements, entities):
        return [Decision(element, action, index, 0.99, [0.99])
                for element, (action, index) in zip(elements, self.actions)]


class FakeDriver:
    def __init__(self, elements, *, can_fill=True, confirm=True, reflect_value=True):
        self.target = WindowTarget(123, 456)
        self.elements = elements
        self.can_fill = can_fill
        self.confirm = confirm
        self.reflect_value = reflect_value
        self.calls = []
        self.timings = []
        self.revision = 0

    def window_state(self, target):
        assert target == self.target
        return WindowSnapshot(target, self.elements, f"snapshot-{self.revision}", "", True, {})

    def supports_value_mutation(self):
        return self.can_fill

    def set_value(self, target, token, value):
        self.calls.append(("set_value", token, value))
        if self.reflect_value:
            self.elements[0].value = value
        self.revision += 1
        return MutationResult({"effect": "confirmed" if self.confirm else "refused"}, self.window_state(target))

    def click(self, target, token, *, delivery_mode):
        self.calls.append(("click", token, delivery_mode))
        if self.elements[0].role == "CheckBox":
            self.elements[0].checked = True
        self.revision += 1
        return MutationResult({"effect": "confirmed" if self.confirm else "refused"}, self.window_state(target))


def run(fake, actions, *, execute=True, submit=False):
    return MODULE.run_with_driver(
        checkpoint=Path("unused.safetensors"), driver=fake, target=fake.target,
        form_title="Demo Form", entities=[Entity("Phone", "555-0142")],
        execute=execute, submit=submit, backend=FixedBackend(actions),
    )


class RunWithDriverTests(unittest.TestCase):
    def test_fill_confirms_observed_value(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1, element_token="tok")])
        report = run(fake, [("fill", 0)])
        self.assertTrue(report["ok"])
        self.assertEqual(fake.calls, [("set_value", "tok", "555-0142")])
        self.assertEqual(report["execution_order"][0]["status"], "delivered")

    def test_missing_value_capability_fails_before_mutation(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1, element_token="tok")], can_fill=False)
        report = run(fake, [("fill", 0)])
        self.assertEqual(report["error"]["code"], "unsupported_driver_capability")
        self.assertEqual(fake.calls, [])

    def test_missing_token_fails_before_mutation(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1)])
        report = run(fake, [("fill", 0)])
        self.assertEqual(report["error"]["code"], "element_token_missing")
        self.assertEqual(fake.calls, [])

    def test_fill_must_match_reobserved_value(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1, element_token="tok")], reflect_value=False)
        report = run(fake, [("fill", 0)])
        self.assertFalse(report["ok"])
        self.assertEqual(report["execution_order"][0]["error"]["code"], "fill_postcondition_failed")

    def test_driver_refusal_keeps_typed_effect_failure(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1, element_token="tok")],
                          confirm=False, reflect_value=False)
        report = run(fake, [("fill", 0)])
        self.assertFalse(report["ok"])
        self.assertEqual(report["execution_order"][0]["error"]["code"], "action_effect_unconfirmed")

    def test_unknown_checkbox_state_refuses_click(self):
        fake = FakeDriver([Element("CheckBox", "Agree", index=1, element_token="tok", checked=None)])
        report = run(fake, [("check", None)])
        self.assertEqual(report["execution_order"][0]["error"]["code"], "checkbox_state_unknown")
        self.assertEqual(fake.calls, [])

    def test_submit_requires_opt_in_and_exact_label(self):
        for label, opt_in, expected in [("Submit", False, 0), ("Submit", True, 1), ("Continue", True, 0)]:
            with self.subTest(label=label, opt_in=opt_in):
                fake = FakeDriver([Element("Button", label, index=1, element_token="tok")])
                report = run(fake, [("click", None)], submit=opt_in)
                self.assertTrue(report["ok"])
                self.assertEqual(len(fake.calls), expected)

    def test_dry_run_never_mutates(self):
        fake = FakeDriver([Element("Edit", "Phone", index=1, element_token="tok")])
        report = run(fake, [("fill", 0)], execute=False)
        self.assertTrue(report["ok"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(report["execution_order"][0]["status"], "planned")


class PublishedCheckpointTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CUA_S1_FORMS_CHECKPOINT"), "set CUA_S1_FORMS_CHECKPOINT")
    def test_real_checkpoint_uses_official_options(self):
        backend = MODULE.ModelBackend(Path(os.environ["CUA_S1_FORMS_CHECKPOINT"]))
        decisions = backend.plan("Demo Form", [Element("Edit", "Phone number", index=1)],
                                 [Entity("Tel", "(503) 555-0142"), Entity("DOB", "03/14/1987")])
        self.assertEqual(decisions[0].action, "fill")
        self.assertEqual(decisions[0].entity_index, 0)
        self.assertEqual(len(decisions[0].distribution), 5)


if __name__ == "__main__":
    unittest.main()
