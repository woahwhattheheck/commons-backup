# SPDX-License-Identifier: Apache-2.0
"""S2 must not infer same-day cash ownership from a truncated native tape."""
import copy
import unittest

import r04_s2_sheep_swap as s2
from test_r04_s2_sheep_swap import CFG, action, obs


def day_tape(length):
    return [action() for _ in range(length)]


def run_buy(step, length, *, player=0, quantity=1):
    observation = obs(step=step)
    observation['player'] = player
    parent = action([['BUY_ANIMAL', 'COW', quantity]])
    state = s2.new_state()
    native = day_tape(length)
    before = copy.deepcopy((observation, parent, native))
    result = s2.apply_s2_swap(observation, parent, state, enabled=True,
                              configuration=CFG, native_tape=native)
    return result, state, (observation, parent, native), before


class S2DayCoverageTests(unittest.TestCase):
    def test_every_truncated_buy_window_declines_cash_ownership(self):
        # Cover every enabled step and every possible missing suffix of its day.
        for step in range(s2.START_STEP, s2.END_STEP + 1):
            end = ((step // 24) + 1) * 24
            complete = day_tape(end)
            for length in range(step + 1, end):
                with self.subTest(step=step, length=length, end=end):
                    self.assertTrue(s2._future_purchase_conflict(complete[:length], step))

    def test_complete_day_remains_admissible_at_every_buy_step(self):
        for step in range(s2.START_STEP, s2.END_STEP + 1):
            end = ((step // 24) + 1) * 24
            with self.subTest(step=step):
                self.assertFalse(s2._future_purchase_conflict(day_tape(end), step))

    def test_truncation_never_creates_pending_purchase_or_spends_swap_quota(self):
        for step in (72, 94, 96, 100, 118, 120, 287, 360):
            end = ((step // 24) + 1) * 24
            for length in {step + 1, end - 1}:
                if length <= step or length >= end:
                    continue
                for player in (0, 1):
                    for quantity in (1, 2):
                        with self.subTest(step=step, length=length, player=player, quantity=quantity):
                            result, state, inputs, before = run_buy(step, length, player=player, quantity=quantity)
                            self.assertEqual(result['market'], [['BUY_ANIMAL', 'COW', quantity]])
                            self.assertIsNone(state['pending_buy'])
                            self.assertEqual(state['requested'], 0)
                            self.assertEqual(state['reserved'], 0)
                            self.assertEqual(inputs, before)

    def test_complete_day_callback_preserves_both_seat_positive_controls(self):
        for step in (72, 95, 96, 100, 119, 120, 287, 360):
            for player in (0, 1):
                for quantity in (1, 2):
                    with self.subTest(step=step, player=player, quantity=quantity):
                        result, state, inputs, before = run_buy(
                            step, ((step // 24) + 1) * 24, player=player, quantity=quantity)
                        self.assertEqual(result['market'], [['BUY_ANIMAL', 'SHEEP', quantity]])
                        self.assertEqual(state['pending_buy'], {'before': 0, 'quantity': quantity})
                        self.assertEqual(state['requested'], quantity)
                        self.assertEqual(inputs, before)

    def test_last_same_day_row_still_owns_cash(self):
        for operation in s2.PURCHASE_OPS:
            with self.subTest(operation=operation):
                native = day_tape(120)
                native[119] = action([[operation, 'WHEAT', 1]])
                self.assertTrue(s2._future_purchase_conflict(native, 100))

    def test_next_day_purchase_is_outside_the_ownership_window(self):
        native = day_tape(121)
        native[120] = action([['HIRE']])
        self.assertFalse(s2._future_purchase_conflict(native, 100))
        self.assertFalse(s2._future_purchase_conflict(native, 119))

    def test_last_same_day_malformed_evidence_still_vetoes(self):
        for future in (None, 'bad', {'market': 'bad'}, {'market': [['MYSTERY', 1, 1]]}):
            with self.subTest(future=future):
                native = day_tape(120)
                native[119] = future
                self.assertTrue(s2._future_purchase_conflict(native, 100))

    def test_sell_only_complete_tail_remains_admissible(self):
        native = day_tape(120)
        native[119] = action([[], ['SELL', 'WOOL', 2]])
        self.assertFalse(s2._future_purchase_conflict(native, 100))

    def test_incomplete_day_is_rejected_before_scanning_rows(self):
        class NoSlice(list):
            def __getitem__(self, key):
                if isinstance(key, slice):
                    raise AssertionError('incomplete evidence reached row scanning')
                return super().__getitem__(key)
        self.assertTrue(s2._future_purchase_conflict(NoSlice(day_tape(104)), 100))

    def test_invalid_tape_and_step_shapes_keep_declining(self):
        for native, step in ((None, 100), ({}, 100), ((), 100), ([], 0),
                             (day_tape(120), -1), (day_tape(120), True),
                             (day_tape(120), 100.0), (day_tape(120), '100'),
                             (day_tape(120), 120)):
            with self.subTest(native_type=type(native).__name__, step=step):
                self.assertTrue(s2._future_purchase_conflict(native, step))

    def test_existing_confirmed_transaction_lifecycle_does_not_need_new_buy_proof(self):
        state = s2.new_state()
        state.update(last=100, requested=1, pending_buy={'before': 0, 'quantity': 1})
        observation = obs(step=101, shed={'SHEEP': 1})
        parent = action(farmer=['PICKUP', 'COW', 1])
        result = s2.apply_s2_swap(observation, parent, state, enabled=True,
                                  configuration=CFG, native_tape=day_tape(102))
        self.assertEqual(result['farmer'], ['PICKUP', 'SHEEP', 1])
        self.assertEqual(state['confirmed'], 1)
        self.assertEqual(state['picked'], 1)
        self.assertIsNone(state['pending_buy'])

    def test_disabled_path_still_returns_exact_parent_without_state_changes(self):
        observation = obs()
        parent = action([['BUY_ANIMAL', 'COW', 1]])
        state = s2.new_state()
        before = copy.deepcopy(state)
        result = s2.apply_s2_swap(observation, parent, state, enabled=False,
                                  configuration=CFG, native_tape=day_tape(101))
        self.assertIs(result, parent)
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
