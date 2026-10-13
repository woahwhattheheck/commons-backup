# SPDX-License-Identifier: Apache-2.0
# The method body below is the unchanged excerpt of PlanOverlay._commit,
# arlene_plan.py lines 448-474, git blob d3f93624a7c4ba4f2c5243c2edcb127cdd035f42.
# Only the enclosing class is a test harness; this is not a full PlanOverlay.
class CommitExcerpt:
    def _commit(self, plan, target, obs, unit, step, seat):
        """Record a COMMITTED errand. Bookkeeping only; play is unaffected."""
        inc = 0
        if hasattr(self.chooser, "at_risk"):
            try:
                inc = int(self.chooser.at_risk(target, obs))
            except Exception:
                inc = 0
        tpd = 24
        self.errands[plan["errand_id"]] = {
            "errand_id": plan["errand_id"],
            "worker_index": int(unit),
            "target": [int(target["at"][0]), int(target["at"][1])],
            "product": target["product"],
            # the WHOLE lot the harvest will lift, which is what competes for
            # capacity; the incremental part is what the output cap would destroy
            "units_total": int(target.get("units", 0)),
            "units_incremental": int(inc),
            "arrival_step": (step // tpd + 1) * tpd - 1,
            "arrival_kind": "eod_auto" if self.one_way else "worker_deposit",
            "no_forced_sale_date": True,
            "status": "pending",
            "observed_carried_units": 0,
            "started": int(step),
            "day": int(obs["day"]),
            "realized_at_step": None,
        }
