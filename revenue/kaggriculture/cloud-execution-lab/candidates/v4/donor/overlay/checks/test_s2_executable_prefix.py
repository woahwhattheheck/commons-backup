"""S2 admission regressions. Normal unittest checks remain active under python -O."""
import copy
import unittest

import r04_s2_sheep_swap as s2

CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24,
           shedCapacity=100, maxMarketOrdersPerTurn=10)


def action(market=None):
    return {"farmer": ["PASS"], "hands": [["PASS"]],
            "market": [] if market is None else market}


def observation(step=100, shed=None):
    farm = {"money": 1000, "tiles": [[None] * 10 for _ in range(10)],
            "farmer": [4, 4], "hands": [[4, 4]], "hires_today": 0}
    return {"step": step, "player": 0, "farms": [farm, copy.deepcopy(farm)],
            "private": {"shed": {} if shed is None else shed, "inventories": [{}, {}]},
            "town": {"unlocked_shops": ["YARN_STORE"]},
            "market": {"prices": {"WOOL": 200, "MILK": 100}}}


def tape():
    return [action() for _ in range(719)]


def apply(obs, parent, state, native=None):
    return s2.apply_s2_swap(obs, parent, state, enabled=True,
                            configuration=CFG, native_tape=tape() if native is None else native)


class PrefixTests(unittest.TestCase):
    def test_buy_in_raw_slot_11_never_reserves_transaction(self):
        st = s2.new_state()
        p = action([[] for _ in range(10)] + [["BUY_ANIMAL", "COW", 1]])
        before = copy.deepcopy(p)
        out = apply(observation(), p, st)
        self.assertEqual(out["market"], [[] for _ in range(10)])
        self.assertIsNone(st["pending_buy"])
        self.assertEqual(st["requested"], 0)
        self.assertEqual(p, before)

    def test_buy_in_raw_slot_10_is_executable(self):
        st = s2.new_state()
        out = apply(observation(), action([[] for _ in range(9)] + [["BUY_ANIMAL", "COW", 1]]), st)
        self.assertEqual(out["market"][-1], ["BUY_ANIMAL", "SHEEP", 1])
        self.assertEqual(st["pending_buy"]["quantity"], 1)

    def test_empty_raw_rows_count_against_cap(self):
        for index in range(25):
            with self.subTest(index=index):
                st = s2.new_state()
                out = apply(observation(), action([[] for _ in range(index)] + [["BUY_ANIMAL", "COW", 1]]), st)
                self.assertEqual(st["requested"], int(index < 10))
                self.assertEqual(len(out["market"]), min(index + 1, 10))

    def test_irrelevant_current_tail_does_not_veto_owned_buy(self):
        for tail in (["HIRE"], ["BUY_ANIMAL", "COW", 1], "malformed", ["MYSTERY", 1, 1]):
            with self.subTest(tail=tail):
                st = s2.new_state()
                p = action([["BUY_ANIMAL", "COW", 1]] + [[] for _ in range(9)] + [tail])
                out = apply(observation(), p, st)
                self.assertEqual(out["market"][0], ["BUY_ANIMAL", "SHEEP", 1])
                self.assertEqual(st["requested"], 1)

    def test_irrelevant_future_tail_does_not_veto_owned_buy(self):
        for tail in (["HIRE"], "bad", ["BUY_LAND"], ["MYSTERY", 1, 1]):
            with self.subTest(tail=tail):
                st = s2.new_state(); nt = tape()
                nt[101] = action([[] for _ in range(10)] + [tail])
                out = apply(observation(), action([["BUY_ANIMAL", "COW", 1]]), st, nt)
                self.assertEqual(out["market"][0][1], "SHEEP")

    def test_future_cash_spend_in_slot_10_still_vetoes(self):
        nt = tape(); nt[101] = action([[] for _ in range(9)] + [["HIRE"]])
        st = s2.new_state()
        out = apply(observation(), action([["BUY_ANIMAL", "COW", 1]]), st, nt)
        self.assertEqual(out["market"][0][1], "COW")
        self.assertIsNone(st["pending_buy"])

    def test_unexecuted_wool_sale_does_not_spend_credit(self):
        st = s2.new_state(); st["wool_credit"] = 2
        out = apply(observation(shed={"WOOL": 5}),
                    action([[] for _ in range(10)] + [["SELL", "WOOL", 1]]), st)
        self.assertEqual(out["market"], [[] for _ in range(10)])
        self.assertEqual(st["wool_credit"], 2)
        self.assertEqual(st["extra_wool_sale_requests"], 0)

    def test_unexecuted_wool_sale_does_not_suppress_live_topup(self):
        st = s2.new_state(); st["wool_credit"] = 2
        out = apply(observation(shed={"WOOL": 5}),
                    action([["SELL", "WOOL", 1]] + [[] for _ in range(9)] + [["SELL", "WOOL", 100]]), st)
        self.assertEqual(out["market"][0], ["SELL", "WOOL", 3])
        self.assertEqual(st["wool_credit"], 0)
        self.assertEqual(st["extra_wool_sale_requests"], 2)

    def test_incomplete_future_day_is_not_proof(self):
        # The buy window ends at step 360, so all eligible days have 24 callbacks.
        for step in (72, 95, 100, 119, 120, 287, 288, 359, 360):
            end = (step // 24 + 1) * 24
            for length in range(step + 1, end):
                with self.subTest(step=step, length=length):
                    st = s2.new_state()
                    out = apply(observation(step), action([["BUY_ANIMAL", "COW", 1]]), st, tape()[:length])
                    self.assertEqual(out["market"][0][1], "COW")
                    self.assertIsNone(st["pending_buy"])

    def test_complete_future_day_is_sufficient(self):
        for step in (72, 95, 100, 119, 120, 287, 288, 359, 360):
            with self.subTest(step=step):
                end = (step // 24 + 1) * 24
                st = s2.new_state()
                out = apply(observation(step), action([["BUY_ANIMAL", "COW", 1]]), st, tape()[:end])
                self.assertEqual(out["market"][0][1], "SHEEP")

    def test_bad_market_returns_parent_before_any_state_changes(self):
        for bad in (None, {}, "bad", ()):
            with self.subTest(market=bad):
                st = s2.new_state(); st["last"] = 99
                st["pending_buy"] = {"before": 0, "quantity": 1}; st["requested"] = 1
                st["sites"] = {(4, 4): 4}
                before = copy.deepcopy(st)
                p = action(); p["market"] = bad
                out = apply(observation(shed={"SHEEP": 1}), p, st)
                self.assertIs(out, p)
                self.assertEqual(st, before)

    def test_non_dict_action_is_inert(self):
        for p in (None, [], (), "bad"):
            with self.subTest(action=p):
                st = s2.new_state(); before = copy.deepcopy(st)
                self.assertIs(apply(observation(), p, st), p)
                self.assertEqual(st, before)

    def test_exact_two_seat_domain(self):
        for count in (1, 3, 4):
            for player in (0, 1):
                with self.subTest(count=count, player=player):
                    o = observation(); o["farms"] = [copy.deepcopy(o["farms"][0]) for _ in range(count)]
                    o["player"] = player
                    st = s2.new_state(); before = copy.deepcopy(st)
                    p = action([["BUY_ANIMAL", "COW", 1]])
                    self.assertIs(apply(o, p, st), p)
                    self.assertEqual(st, before)

    def test_invalid_step_does_not_consume_state(self):
        for step in (-1, 719, 720, True, "100", 100.0):
            with self.subTest(step=step):
                st = s2.new_state(); st["last"] = 99
                st["pending_buy"] = {"before": 0, "quantity": 1}
                before = copy.deepcopy(st); p = action()
                self.assertIs(apply(observation(step, {"SHEEP": 1}), p, st), p)
                self.assertEqual(st, before)

    def test_final_callback_718_can_confirm_pending_transaction(self):
        # The DAY helper is a new-buy-window proof (72..360), not a terminal callback gate.
        st = s2.new_state(); st["last"] = 717
        st["pending_buy"] = {"before": 0, "quantity": 1}; st["requested"] = 1
        out = apply(observation(718, {"SHEEP": 1}), action(), st)
        self.assertEqual(st["last"], 718)
        self.assertEqual(st["confirmed"], 1)
        self.assertEqual(st["reserved"], 1)
        self.assertIsNone(st["pending_buy"])
        self.assertEqual(out["market"], [])

    def test_disabled_preserves_even_out_of_prefix_parent(self):
        st = s2.new_state(); before = copy.deepcopy(st)
        p = action([[] for _ in range(10)] + [["BUY_ANIMAL", "COW", 1]])
        original = copy.deepcopy(p)
        self.assertIs(s2.apply_s2_swap(observation(), p, st, enabled=False,
                                      configuration=CFG, native_tape=tape()), p)
        self.assertEqual(st, before)
        self.assertEqual(p, original)

    def test_direct_ownership_helper_ignores_tail(self):
        buy = ["BUY_ANIMAL", "COW", 1]
        self.assertIsNone(s2._owned_current_cow_buy([[] for _ in range(10)] + [buy]))
        self.assertIs(s2._owned_current_cow_buy([buy] + [[] for _ in range(9)] + [["HIRE"]]), buy)


if __name__ == "__main__":
    unittest.main()
