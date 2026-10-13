import copy
import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("pinellas_check", ROOT / "validate_readiness.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

OPP = json.loads((ROOT / "opportunity.json").read_text())
STATE = json.loads((ROOT / "state.json").read_text())
WORK = json.loads((ROOT / "workshare.json").read_text())
NOW = dt.datetime(2026, 9, 14, 3, 0, tzinfo=dt.timezone.utc)


def prove(entry, ref="synthetic:test"):
    entry["status"] = "PROVEN"
    entry["evidence"] = [ref]


def ready_fixture():
    opp = copy.deepcopy(OPP)
    state = copy.deepcopy(STATE)
    work = copy.deepcopy(WORK)
    state["thread_state"]["latest_human_event_kind"] = "PROCUREMENT_TEAMING_CONFIRMATION"
    state["thread_state"]["awaiting_new_human_reply"] = False
    for gate in state["gates"].values():
        prove(gate)
    return opp, state, work


class Tests(unittest.TestCase):
    def test_default_holds_and_preserves_dnr(self):
        result, reasons = v.check(copy.deepcopy(OPP), copy.deepcopy(STATE), copy.deepcopy(WORK), NOW)
        self.assertEqual(result, v.HOLD)
        self.assertTrue(STATE["thread_state"]["dnr_until_new_human_procurement_teaming_event"])
        self.assertFalse(STATE["external_authority"]["email_send_authorized"])
        self.assertTrue(any("new_human_procurement_teaming_confirmation" in r for r in reasons))

    def test_ready_requires_new_human_procurement_teaming_event(self):
        opp, state, work = ready_fixture()
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.READY)
        self.assertEqual(reasons, [])
        self.assertTrue(state["thread_state"]["dnr_until_new_human_procurement_teaming_event"])
        self.assertFalse(state["external_authority"]["email_send_authorized"])

    def test_staffing_event_cannot_masquerade_as_teaming(self):
        opp, state, work = ready_fixture()
        state["thread_state"]["latest_human_event_kind"] = "C2C_STAFFING_MISCLASSIFICATION"
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("latest human event is not procurement teaming confirmation", reasons)

    def test_confidential_profile_use_is_stop(self):
        opp, state, work = ready_fixture()
        state["confidential_material"]["consultant_profile_use_allowed"] = True
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("consultant_profile_use_allowed must remain false", reasons)

    def test_profile_content_leak_is_stop(self):
        opp, state, work = ready_fixture()
        state["confidential_material"]["profile_content_present_in_carrier"] = True
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("profile_content_present_in_carrier must remain false", reasons)

    def test_fabricated_recruiter_or_county_authority_is_stop(self):
        for section, key in [
            ("thread_state", "recruiter_authority"),
            ("thread_state", "county_contact_authority"),
            ("external_authority", "county_submission_authorized"),
            ("external_authority", "email_send_authorized"),
        ]:
            with self.subTest(section=section, key=key):
                opp, state, work = ready_fixture()
                state[section][key] = True
                result, reasons = v.check(opp, state, work, NOW)
                self.assertEqual(result, v.HOLD)
                self.assertTrue(any(key in r for r in reasons))

    def test_fee_is_exact_integer_not_bool(self):
        for bad in [True, 14999, 15000.0, "15000"]:
            with self.subTest(bad=bad):
                opp, state, work = ready_fixture()
                work["proposed_fixed_fee_usd"] = bad
                result, reasons = v.check(opp, state, work, NOW)
                self.assertEqual(result, v.HOLD)
                self.assertIn("proposed fee must be exact integer USD 15000", reasons)

    def test_milestone_amount_bool_alias_is_rejected(self):
        opp, state, work = ready_fixture()
        work["payment_milestones"][0]["amount_usd"] = True
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("payment milestone 0: amount mismatch", reasons)

    def test_missing_confirmation_evidence_is_stop(self):
        opp, state, work = ready_fixture()
        state["gates"]["new_human_procurement_teaming_confirmation"]["evidence"] = []
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("new_human_procurement_teaming_confirmation: proven without evidence", reasons)

    def test_expired_deadline_is_stop(self):
        opp, state, work = ready_fixture()
        later = dt.datetime(2026, 9, 16, tzinfo=dt.timezone.utc)
        result, reasons = v.check(opp, state, work, later)
        self.assertEqual(result, v.HOLD)
        self.assertIn("deadline expired", reasons)

    def test_closed_no_fit_requires_evidence(self):
        state = copy.deepcopy(STATE)
        state["disposition"] = v.CLOSED
        state["closeout"]["reason"] = "Provider confirmed channel is staffing-only."
        state["closeout"]["evidence"] = ["synthetic:human-closeout"]
        result, reasons = v.check(copy.deepcopy(OPP), state, copy.deepcopy(WORK), NOW)
        self.assertEqual(result, v.CLOSED)
        self.assertEqual(reasons, [])

    def test_closed_no_fit_cannot_bypass_profile_or_parallel_contact_safety(self):
        for section, key in [
            ("confidential_material", "profile_content_present_in_carrier"),
            ("thread_state", "parallel_contact_forbidden"),
        ]:
            with self.subTest(section=section, key=key):
                state = copy.deepcopy(STATE)
                state["disposition"] = v.CLOSED
                state["closeout"]["reason"] = "Provider confirmed channel is staffing-only."
                state["closeout"]["evidence"] = ["synthetic:human-closeout"]
                state[section][key] = True if key == "profile_content_present_in_carrier" else False
                result, reasons = v.check(copy.deepcopy(OPP), state, copy.deepcopy(WORK), NOW)
                self.assertEqual(result, v.HOLD)
                self.assertTrue(reasons)

    def test_ready_spoof_by_disposition_is_rejected(self):
        opp, state, work = ready_fixture()
        state["disposition"] = v.READY
        result, reasons = v.check(opp, state, work, NOW)
        self.assertEqual(result, v.HOLD)
        self.assertIn("invalid disposition", reasons)


if __name__ == "__main__":
    unittest.main()
