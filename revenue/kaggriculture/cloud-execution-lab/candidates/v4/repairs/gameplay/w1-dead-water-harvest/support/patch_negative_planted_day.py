from __future__ import annotations

BASE_HELPER_BLOB = "d6b3ad45d6099937e852f76e5be0d9acf11d18d1"

OLD = (
    "        if not _plain_int(planted_day) or not _plain_int(yield_units):\n"
    "            return False\n"
    "        if yield_units <= 0:\n"
)

NEW = (
    "        if (\n"
    "            not _plain_int(planted_day)\n"
    "            or planted_day < 0\n"
    "            or not _plain_int(yield_units)\n"
    "        ):\n"
    "            return False\n"
    "        if yield_units <= 0:\n"
)


def _req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def apply(source: str) -> str:
    _req(source.count(OLD) == 1, "W1 planted_day anchor drifted or is ambiguous")
    out = source.replace(OLD, NEW)
    _req(out.count(NEW) == 1, "W1 planted_day repair did not materialize exactly once")
    _req(OLD not in out, "W1 planted_day repair left predecessor anchor behind")
    return out


def self_test() -> None:
    source = "prefix\n" + OLD + "suffix\n"
    out = apply(source)
    _req("or planted_day < 0" in out, "negative planted-day guard missing")
    failed = False
    try:
        apply(out)
    except AssertionError:
        failed = True
    _req(failed, "double apply must fail closed")


if __name__ == "__main__":
    self_test()
    print("W1 NEGATIVE-PLANTED-DAY PATCH SELF-TEST OK")
