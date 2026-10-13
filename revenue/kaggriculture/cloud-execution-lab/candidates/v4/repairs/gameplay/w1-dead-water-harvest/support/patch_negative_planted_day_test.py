from __future__ import annotations

BASE_TEST_BLOB = "fae2f54b0d8e810a188974bb6d585f72f0ff7b4f"

ANCHOR = (
    "    def test_annual_yield_units_before_maturity_fails_closed(self):\n"
)

TEST = (
    "    def test_negative_planted_day_fails_closed(self):\n"
    "        tile = _tile(crop=\"TOMATO\", planted_day=-1, yield_units=2,\n"
    "                     watered_today=True, max_lifespan_step=-1)\n"
    "        action = _action()\n"
    "        out = _apply(_obs(tile), action)\n"
    "        self.assertIs(out, action)\n"
    "        self.assertEqual(lane.get_report()[\"not_harvestable\"], 1)\n"
    "        self.assertEqual(lane.get_report()[\"recovered\"], 0)\n"
    "\n"
)


def _req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def apply(source: str) -> str:
    _req(source.count(ANCHOR) == 1, "W1 focused-test anchor drifted or is ambiguous")
    _req("def test_negative_planted_day_fails_closed" not in source, "regression already present")
    out = source.replace(ANCHOR, TEST + ANCHOR)
    _req(out.count("def test_negative_planted_day_fails_closed") == 1, "regression insertion failed")
    return out


def self_test() -> None:
    source = "class T:\n" + ANCHOR + "        pass\n"
    out = apply(source)
    _req("planted_day=-1" in out, "poison fixture missing")
    failed = False
    try:
        apply(out)
    except AssertionError:
        failed = True
    _req(failed, "double apply must fail closed")


if __name__ == "__main__":
    self_test()
    print("W1 NEGATIVE-PLANTED-DAY TEST PATCH SELF-TEST OK")
