# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ablation


FROZEN = b"""def fund_same_turn_acquisition(
    pass

def funded_minimum_now(obs, config, base, farm, private, route, end,
                       current, targets, item, stress_units=32):
    pass

def transform(self, obs, config, base):
    item_budget=self.cash_reserve(obs,config,base,item_end)
            minimum,funding=funded_minimum_now(obs,config,base,farm,private,route,item_end,
                                                current,targets,item)
            funding['nominal_future_spend']=item_budget
            self.diagnostics.setdefault('funding_certificates',{})[item]=funding
    out['market']=materialize_sales(out['market'],current,shed,targets,
                                    int(config.get('maxMarketOrdersPerTurn',10)))
        out['market'],funding=fund_same_turn_acquisition(
            out['market'],farm,private,obs['market'],shops,config,now,targets,
            lambda product:self.rival_supply(obs,product))
        if funding is not None:self.diagnostics['same_turn_funding']=funding
    return out
"""


def members():
    return {
        "main.py": b"def agent(*a): return None\n",
        "frozen_selected.py": FROZEN,
        "other.py": b"unchanged\n",
    }


class FundingPolicyAblationTest(unittest.TestCase):
    def test_builds_complete_orthogonal_2x2(self):
        base = members()
        arms, receipts = ablation.build_arms(base)
        self.assertEqual(tuple(arms), ablation.ARMS)
        self.assertEqual(set(receipts), set(ablation.ARMS))
        self.assertEqual(arms["control"], base)
        self.assertEqual(receipts["control"]["changed_members"], [])
        for arm in ("min_v31", "no_reorder", "funding_pair_v31"):
            self.assertEqual(receipts[arm]["changed_members"], ["frozen_selected.py"])
            self.assertEqual(arms[arm]["main.py"], base["main.py"])
            self.assertEqual(arms[arm]["other.py"], base["other.py"])

    def test_minimum_arm_changes_only_minimum_semantics(self):
        arms, _ = ablation.build_arms(members())
        src = arms["min_v31"]["frozen_selected.py"]
        self.assertIn(b"minimum=current[item] if farm['money']<item_budget else 0", src)
        self.assertNotIn(ablation._MINIMUM_TARGET, src)
        self.assertIn(ablation._REORDER_TARGET, src)

    def test_reorder_arm_preserves_minimum_and_sale_emitter(self):
        arms, _ = ablation.build_arms(members())
        src = arms["no_reorder"]["frozen_selected.py"]
        self.assertIn(ablation._MINIMUM_TARGET, src)
        self.assertNotIn(ablation._REORDER_TARGET, src)
        self.assertIn(b"funding=None  # evidence-only", src)
        self.assertIn(
            b"out['market']=materialize_sales(out['market'],current,shed,targets,", src
        )

    def test_both_arm_combines_exactly_the_two_axes(self):
        arms, receipts = ablation.build_arms(members())
        both = arms["funding_pair_v31"]["frozen_selected.py"]
        self.assertNotIn(ablation._MINIMUM_TARGET, both)
        self.assertNotIn(ablation._REORDER_TARGET, both)
        self.assertIn(ablation._MINIMUM_REPLACEMENT, both)
        self.assertIn(ablation._REORDER_REPLACEMENT, both)
        self.assertEqual(
            receipts["funding_pair_v31"]["axes"],
            {"legacy_minimum": True, "disable_reorder": True},
        )

    def test_source_callsite_drift_fails_closed(self):
        base = members()
        base["frozen_selected.py"] = base["frozen_selected.py"].replace(
            b"current,targets,item)\n", b"current,targets,item,0)\n", 1
        )
        with self.assertRaisesRegex(ValueError, "funded-minimum callsite drifted"):
            ablation.build_arms(base)

    def test_duplicate_reorder_callsite_fails_closed(self):
        base = members()
        base["frozen_selected.py"] += ablation._REORDER_TARGET
        with self.assertRaisesRegex(ValueError, "same-turn funding callsite drifted"):
            ablation.build_arms(base)

    def test_provider_drift_fails_closed(self):
        base = members()
        base["frozen_selected.py"] = base["frozen_selected.py"].replace(
            b"def fund_same_turn_acquisition(", b"def moved_funder(", 1
        )
        with self.assertRaisesRegex(ValueError, "same-turn funding provider drifted"):
            ablation.build_arms(base)

    def test_capture_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real.tar.gz"
            real.write_bytes(b"x")
            link = root / "link.tar.gz"
            link.symlink_to(real)
            with self.assertRaisesRegex(ValueError, "ordinary file"):
                ablation.capture_exact_archive(link)

    def test_capture_authenticates_single_read_bytes(self):
        payload = b"submitted-v4-fixture"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v4.tar.gz"
            path.write_bytes(payload)
            with mock.patch.object(ablation, "BASELINE_SHA256", expected):
                captured = ablation.capture_exact_archive(path)
                path.write_bytes(b"poison-after-auth")
                self.assertEqual(captured, payload)
                self.assertNotEqual(captured, path.read_bytes())

    def test_capture_rejects_wrong_sha(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v4.tar.gz"
            path.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "not exact submitted V4"):
                ablation.capture_exact_archive(path)


if __name__ == "__main__":
    unittest.main()
