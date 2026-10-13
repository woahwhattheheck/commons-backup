from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE / "triclinic_controlled_sample_gate.py"
spec = importlib.util.spec_from_file_location("triclinic_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

FIXTURE = HERE / "fixtures" / "triclinic_180_intakes.json"

def bundle():
    return gate.expand_bundle(json.loads(FIXTURE.read_text(encoding="utf-8")))

def cal(data=None):
    data = data or bundle()
    return gate.BusinessCalendar.from_manifest(data["calendar"])

class ContractTests(unittest.TestCase):
    def test_exact_180_140_40_contract(self):
        data = bundle(); ledger = gate.Ledger()
        result = gate.process_batch(data["intakes"], cal(data), ledger)
        self.assertEqual(result["input_count"], 180)
        self.assertEqual(result["added_ready"], 140)
        self.assertEqual(result["new_holds"], 40)
        self.assertEqual(result["after_counts"], [140, 140, 140])

    def test_exact_hold_distribution(self):
        data = bundle(); result = gate.process_batch(data["intakes"], cal(data), gate.Ledger())
        counts = Counter(row["hold_code"] for row in result["outcomes"] if row["status"] == "HOLD")
        self.assertEqual(counts, Counter({
            "MISSING_QUOTE": 7,
            "MISSING_SDS": 7,
            "MISSING_LOT": 7,
            "MISSING_STORAGE": 7,
            "MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222": 6,
            "CONFLICTING_HANDLING_INSTRUCTIONS": 6,
        }))

    def test_holds_create_zero_job_report_state(self):
        data = bundle(); ledger = gate.Ledger(); result = gate.process_batch(data["intakes"], cal(data), ledger)
        held_ids = {row["intake_id"] for row in result["outcomes"] if row["status"] == "HOLD"}
        self.assertFalse(held_ids & set(ledger.accessions))
        self.assertFalse(held_ids & set(ledger.jobs))
        self.assertFalse(held_ids & set(ledger.reports))

    def test_ready_states_are_staged_not_run_and_unsent(self):
        data=bundle(); ledger=gate.Ledger(); gate.process_batch(data["intakes"], cal(data), ledger)
        self.assertTrue(all(x["state"] == "STAGED_NOT_RUN" and not x["production_execution_authorized"] for x in ledger.jobs.values()))
        self.assertTrue(all(x["state"] == "STAGED_HUMAN_DISPOSITION" and x["delivery_state"] == "UNSENT" and not x["automatic_release_authorized"] for x in ledger.reports.values()))

    def test_replay_zero_add_stable_digest(self):
        data=bundle(); ledger=gate.Ledger(); first=gate.process_batch(data["intakes"], cal(data), ledger)
        second=gate.process_batch(data["intakes"], cal(data), ledger)
        self.assertEqual(second["added_ready"], 0); self.assertEqual(second["new_holds"], 0)
        self.assertEqual(second["idempotent"], 180); self.assertEqual(second["after_counts"], [140,140,140])
        self.assertEqual(first["ledger_digest"], second["ledger_digest"])

    def test_changed_content_same_id_fails_before_mutation(self):
        data=bundle(); ledger=gate.Ledger(); gate.process_batch(data["intakes"], cal(data), ledger)
        snap=ledger.snapshot(); changed=copy.deepcopy(data["intakes"]); changed[0]["storage_condition"]="CHANGED"
        with self.assertRaisesRegex(gate.GateError, "changed-content"):
            gate.process_batch(changed, cal(data), ledger)
        self.assertEqual(ledger.snapshot(), snap)

    def test_batch_duplicate_id_rejected(self):
        data=bundle(); dup=[copy.deepcopy(data["intakes"][0]),copy.deepcopy(data["intakes"][0])]
        with self.assertRaisesRegex(gate.GateError, "duplicate intake_id"):
            gate.process_batch(dup, cal(data), gate.Ledger())

    def test_before_noon_same_business_day(self):
        c=cal(); from datetime import datetime
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-15T11:59:59-04:00")), date(2026,9,15))

    def test_exact_noon_next_business_day(self):
        c=cal(); from datetime import datetime
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-15T12:00:00-04:00")), date(2026,9,16))

    def test_after_noon_next_business_day(self):
        c=cal(); from datetime import datetime
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-15T12:00:01-04:00")), date(2026,9,16))

    def test_weekend_rolls_forward(self):
        c=cal(); from datetime import datetime
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-19T09:00:00-04:00")), date(2026,9,22))

    def test_pinned_holiday_rolls_forward(self):
        c=cal(); from datetime import datetime
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-21T09:00:00-04:00")), date(2026,9,22))

    def test_friday_after_noon_skips_weekend_and_holiday(self):
        c=cal(); from datetime import datetime
        # Fri Sep18 after noon -> weekend -> pinned Mon Sep21 holiday -> Tue Sep22.
        self.assertEqual(c.queue_date(datetime.fromisoformat("2026-09-18T12:00:00-04:00")), date(2026,9,22))

    def test_missing_controlled_classification_when_required_holds(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["intake_id"]="SPECIAL-CLASS"; x["controlled_classification_required"]=True; x["controlled_classification_present"]=False
        r=gate.process_batch([x],cal(data),gate.Ledger()); self.assertEqual(r["outcomes"][0]["hold_code"],"MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222")

    def test_missing_form_222_when_fixture_marks_required_holds(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["intake_id"]="SPECIAL-222"; x["form_222_required"]=True; x["form_222_present"]=False
        r=gate.process_batch([x],cal(data),gate.Ledger()); self.assertEqual(r["outcomes"][0]["hold_code"],"MISSING_CONTROLLED_CLASSIFICATION_OR_FORM_222")

    def test_no_requirement_never_infers_classification(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["intake_id"]="NO-INFER"; x["controlled_classification_required"]=False; x["controlled_classification_present"]=False; x["form_222_required"]=False; x["form_222_present"]=False
        r=gate.process_batch([x],cal(data),gate.Ledger()); self.assertEqual(r["outcomes"][0]["status"],"READY")

    def test_conflicting_handling_text_holds(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["intake_id"]="CONFLICT"; x["handling_instruction_primary"]="A"; x["handling_instruction_secondary"]="B"
        r=gate.process_batch([x],cal(data),gate.Ledger()); self.assertEqual(r["outcomes"][0]["hold_code"],"CONFLICTING_HANDLING_INSTRUCTIONS")

    def test_reserved_actor_label_rejected(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["human_disposition_owner"]="SYSTEM"
        with self.assertRaisesRegex(gate.GateError,"human review actor"): gate.process_batch([x],cal(data),gate.Ledger())

    def test_unknown_fields_rejected(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["extra"]=1
        with self.assertRaisesRegex(gate.GateError,"fields mismatch"): gate.process_batch([x],cal(data),gate.Ledger())

    def test_naive_timestamp_rejected(self):
        data=bundle(); x=copy.deepcopy(data["intakes"][0]); x["submitted_local"]="2026-09-15T10:00:00"
        with self.assertRaisesRegex(gate.GateError,"UTC offset"): gate.process_batch([x],cal(data),gate.Ledger())

    def test_authority_is_hard_negative(self):
        data=bundle(); r=gate.process_batch([data["intakes"][0]],cal(data),gate.Ledger()); a=r["authority"]
        self.assertTrue(a["synthetic_or_deidentified_only"]); self.assertTrue(a["human_disposition_required"])
        for key in ("classifies_controlled_substances","handles_or_transfers_controlled_substances","authorizes_testing","automatic_release","customer_or_regulator_transmission"):
            self.assertFalse(a[key])

    def test_cli_normal_and_optimized(self):
        for opt in (False, True):
            cmd=[sys.executable]+(["-O"] if opt else [])+[str(MODULE),str(FIXTURE)]
            proc=subprocess.run(cmd,cwd=HERE,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode,0,proc.stderr)
            out=json.loads(proc.stdout); self.assertEqual(out["first"]["added_ready"],140); self.assertEqual(out["replay"]["idempotent"],180)
            self.assertEqual(out["first"]["ledger_digest"],out["replay"]["ledger_digest"])

if __name__ == "__main__": unittest.main()
