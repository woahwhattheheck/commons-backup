# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import build_route_matrix as builder


ROUTER = b'''ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
SHOP_PLANS = {("A", "B"): 3}

class State:
    plan = 0

def choose(state, observation, step):
    if step == ROUTE_STEP:
        shops = observation["town"]["unlocked_shops"]
        state.plan = SHOP_PLANS.get(tuple(shops[:2]), 0)
    if step == FINAL_PLAN_STEP:
        state.plan = 2
    return state.plan
'''


class BuildRouteMatrixTests(unittest.TestCase):
    def _build(
        self,
        plan_index=7,
        *,
        selection_step=builder.ROUTE_STEP,
        candidate_sha=None,
        router_sha=None,
    ):
        baseline = {
            "main.py": b"entry\n",
            "r04_full_router.py": ROUTER,
            "TITAN-CONFIG.json": b"{}\n",
        }
        expected_candidate = builder.digest(builder.archive_bytes(baseline))
        expected_router = builder.digest(ROUTER)
        if candidate_sha is None:
            candidate_sha = expected_candidate
        if router_sha is None:
            router_sha = expected_router
        with (
            mock.patch.object(builder, "members", side_effect=({"v31": b"x"}, {"delivery": b"y"})),
            mock.patch.object(builder, "compose", return_value=dict(baseline)),
            mock.patch.object(builder.Path, "read_bytes", return_value=b"overlay\n"),
            mock.patch.object(builder, "CANDIDATE_SHA", candidate_sha),
            mock.patch.object(builder, "ROUTER_SHA256", router_sha),
        ):
            result = builder.build(
                Path("v31.tar.gz"),
                Path("delivery.tar.gz"),
                plan_index,
                selection_step,
            )
        return baseline, result

    def _publication_args(self, root):
        files = {
            "main.py": b"entry\n",
            "r04_full_router.py": ROUTER,
            "TITAN-CONFIG.json": b"{}\n",
        }
        before = ROUTER
        after = ROUTER.replace(
            b"SHOP_PLANS.get(tuple(shops[:2]), 0)",
            b"7",
            1,
        )
        files["r04_full_router.py"] = after
        packed = builder.archive_bytes(files)
        out = root / "candidate"
        tar_path = root / "candidate.tar.gz"
        receipt_path = root / "candidate-manifest.json"
        return files, before, after, packed, out, tar_path, receipt_path

    def test_exact_baseline_changes_only_router(self):
        baseline, (files, before, after) = self._build(9)
        self.assertEqual(before, ROUTER)
        self.assertNotEqual(after, before)
        self.assertEqual(set(files), set(baseline))
        self.assertEqual(files["main.py"], baseline["main.py"])
        self.assertEqual(files["TITAN-CONFIG.json"], baseline["TITAN-CONFIG.json"])
        self.assertEqual(files["r04_full_router.py"], after)
        self.assertIn(b"state.plan = 9\n", after)
        self.assertIn(b"if step == FINAL_PLAN_STEP:\n        state.plan = 2", after)

    def test_terminal_matrix_changes_only_terminal_rhs(self):
        baseline, (files, before, after) = self._build(
            9, selection_step=builder.FINAL_PLAN_STEP
        )
        self.assertEqual(before, ROUTER)
        self.assertNotEqual(after, before)
        self.assertEqual(set(files), set(baseline))
        self.assertEqual(files["main.py"], baseline["main.py"])
        self.assertIn(
            b'state.plan = SHOP_PLANS.get(tuple(shops[:2]), 0)',
            after,
        )
        self.assertIn(
            b"if step == FINAL_PLAN_STEP:\n        state.plan = 9",
            after,
        )

    def test_terminal_plan2_is_exact_production_control(self):
        baseline, (files, before, after) = self._build(
            builder.TERMINAL_PLAN,
            selection_step=builder.FINAL_PLAN_STEP,
        )
        self.assertEqual(before, ROUTER)
        self.assertEqual(after, ROUTER)
        self.assertEqual(files, baseline)

    def test_rejects_invalid_selection_step(self):
        with self.assertRaisesRegex(ValueError, "selection_step"):
            self._build(9, selection_step=647)

    def test_rejects_production_v3_archive_drift(self):
        with self.assertRaisesRegex(ValueError, "baseline identity drift"):
            self._build(candidate_sha="0" * 64)

    def test_rejects_router_identity_drift(self):
        with self.assertRaisesRegex(ValueError, "router identity drift"):
            self._build(router_sha="0" * 64)

    def test_preexisting_receipt_preserved_and_archive_rolled_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._publication_args(root)
            files, before, after, packed, out, tar_path, receipt_path = args
            receipt_path.write_bytes(b"sentinel\n")
            with self.assertRaises(FileExistsError):
                builder._publish(
                    files,
                    before,
                    after,
                    packed,
                    7,
                    builder.ROUTE_STEP,
                    out,
                    tar_path,
                    receipt_path,
                )
            self.assertFalse(tar_path.exists())
            self.assertFalse(out.exists())
            self.assertEqual(receipt_path.read_bytes(), b"sentinel\n")

    def test_receipt_write_failure_rolls_back_archive_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._publication_args(root)
            files, before, after, packed, out, tar_path, receipt_path = args
            real_write = builder._write_reserved
            calls = []

            def fail_receipt(fd, payload):
                calls.append(fd)
                if len(calls) == 2:
                    raise OSError("receipt write failed")
                return real_write(fd, payload)

            with mock.patch.object(builder, "_write_reserved", side_effect=fail_receipt):
                with self.assertRaisesRegex(OSError, "receipt write failed"):
                    builder._publish(
                        files,
                        before,
                        after,
                        packed,
                        7,
                        builder.ROUTE_STEP,
                        out,
                        tar_path,
                        receipt_path,
                    )
            self.assertEqual(len(calls), 2)
            self.assertFalse(tar_path.exists())
            self.assertFalse(receipt_path.exists())
            self.assertFalse(out.exists())

    def test_archive_receipt_alias_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = self._publication_args(root)
            files, before, after, packed, out, _tar_path, receipt_path = args
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                builder._publish(
                    files,
                    before,
                    after,
                    packed,
                    7,
                    builder.ROUTE_STEP,
                    out,
                    receipt_path,
                    receipt_path,
                )
            self.assertFalse(out.exists())
            self.assertFalse(receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
