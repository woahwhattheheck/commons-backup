from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from revenue.merged_work_payment_claim import compiler_v2 as compiler
from revenue.merged_work_payment_claim.schema_v2 import SCHEMA

NOW = "2026-09-18T07:00:00Z"

def subj():
    return {"claimant_id":"woahwhattheheck","counterparty_id":"sponsor-example","opportunity_id":"bounty-42","work_id":"example/project#42@"+"1"*40}

def ready_doc():
    s=subj()
    return {
        "schema":SCHEMA,"claim_id":"claim-example-42","claimant_id":s["claimant_id"],"counterparty_id":s["counterparty_id"],"opportunity_id":s["opportunity_id"],
        "work":{"work_id":s["work_id"],"repository":"example/project","pr_number":42,"merged_commit_sha":"1"*40,"deliverable_sha256":"2"*64,"merged_at":"2026-09-17T18:00:00Z","source_ref":"github:example/project/pull/42","source_sha256":"3"*64},
        "compensation":[{"offer_id":"offer-42","subject":s,"repository":"example/project","pr_number":42,"source_ref":"program:offer-42","source_sha256":"4"*64,"advertised_at":"2026-09-10T12:00:00Z","expires_at":None,"currency":"USD","amount_minor":9000,"terms_text":None,"eligibility_required":True,"supersedes_offer_id":None}],
        "acceptance":{"acceptance_id":"merge-42","subject":s,"source_class":"TARGET_MERGE_EVENT","source_ref":"github:example/project/pull/42#merged","source_sha256":"5"*64,"accepted_at":"2026-09-17T18:00:00Z","repository":"example/project","pr_number":42,"merged_commit_sha":"1"*40},
        "eligibility":{"subject":s,"status":"ELIGIBLE","source_ref":"program:eligibility","source_sha256":"6"*64,"observed_at":"2026-09-18T06:00:00Z"},
        "followups":[],
        "payment_status":{"subject":s,"repository":"example/project","pr_number":42,"status":"UNPAID","provenance_class":"PROVIDER_OBSERVED","source_ref":"provider:status","source_sha256":"7"*64,"observed_at":"2026-09-18T06:30:00Z","paid_amount_minor":None,"payment_ref":None},
        "policy":{"max_status_age_hours":168,"cooldown_hours":72},
    }

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        dt=datetime(2026,9,18,7,0,0,tzinfo=timezone.utc)
        return dt if tz is None else dt.astimezone(tz)

class Base(unittest.TestCase):
    def current(self, doc=None):
        with mock.patch.object(compiler,"datetime",FixedDateTime):
            return compiler.compile_current(ready_doc() if doc is None else doc)
    def state(self, doc=None): return self.current(doc)[0]["state"]
    def followup(self,kind="PAYMENT_REQUEST_SENT"):
        return {"id":"f1","subject":subj(),"repository":"example/project","pr_number":42,"kind":kind,"route":"email","provider_ref":"gmail:1","thread_ref":None,"message_ref":"m1","source_ref":"gmail:m1","source_sha256":"8"*64,"observed_at":"2026-09-18T06:00:00Z"}
