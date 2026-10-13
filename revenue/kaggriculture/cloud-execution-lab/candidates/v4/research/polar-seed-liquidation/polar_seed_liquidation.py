"""POLAR-20260911-SEED-SHADOW: prospective seed-value calculator.

Research-only. Sequential per-unit liquidation versus naive
current_quote * extra_yield. Bind official interpreter
465f4263da1c98acf78889d67cdd21b61dbba145 and engine blob
3c202c7ee921da239356789e266b694635103fc4 as source pins.

Does not mutate runtime, keys, config, gameplay spine, canonical
ref, Actions, or Kaggle. A result here is not permission to skip
authored PLANT or BUY_SEED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

INTERPRETER_SHA = "465f4263da1c98acf78889d67cdd21b61dbba145"
ENGINE_BLOB_SHA = "3c202c7ee921da239356789e266b694635103fc4"
CLAIM = "POLAR-20260911-SEED-SHADOW"


@dataclass(frozen=True)
class MarketBook:
    """Isolated same-item book: price after `sold` units already offered."""

    quote0: float
    impact: float
    floor: float = 0.0

    def price_after(self, sold: int) -> float:
        if sold < 0:
            raise ValueError("sold must be >= 0")
        return max(self.floor, self.quote0 - self.impact * sold)


@dataclass(frozen=True)
class SeedCase:
    """One isolated liquidation scenario.

    owned_seed: already held; purchase cost is sunk (not charged).
    buy_seed: fresh purchases; charged at seed_price each.
    committed_output: yield already promised / in inventory; sold first.
    extra_yield: incremental units from planting more seed.
    """

    book: MarketBook
    committed_output: int
    extra_yield: int
    owned_seed: int = 0
    buy_seed: int = 0
    seed_price: float = 0.0
    realized_yield_per_seed: float = 1.0


@dataclass(frozen=True)
class Valuation:
    naive_incremental: float
    sequential_incremental: float
    committed_revenue: float
    extra_revenue: float
    purchase_cost: float
    net_sequential: float
    sign_flip: bool
    interpreter_sha: str = INTERPRETER_SHA
    engine_blob_sha: str = ENGINE_BLOB_SHA
    claim: str = CLAIM


def liquidate(book: MarketBook, units: int, start_sold: int = 0) -> List[float]:
    if units < 0:
        raise ValueError("units must be >= 0")
    return [book.price_after(start_sold + i) for i in range(units)]


def revenue(book: MarketBook, units: int, start_sold: int = 0) -> float:
    return float(sum(liquidate(book, units, start_sold)))


def naive_incremental(quote: float, extra_yield: int) -> float:
    return float(quote) * int(extra_yield)


def evaluate(case: SeedCase) -> Valuation:
    committed = int(case.committed_output)
    extra = int(case.extra_yield)
    committed_rev = revenue(case.book, committed, 0)
    extra_rev = revenue(case.book, extra, committed)
    naive = naive_incremental(case.book.quote0, extra)
    purchase = float(case.seed_price) * int(case.buy_seed)
    net = extra_rev - purchase
    return Valuation(
        naive_incremental=naive,
        sequential_incremental=extra_rev,
        committed_revenue=committed_rev,
        extra_revenue=extra_rev,
        purchase_cost=purchase,
        net_sequential=net,
        sign_flip=(naive > 0 and net < 0) or (naive < 0 and net > 0),
    )


def break_even_extra_yield(case: SeedCase, max_extra: int = 10_000):
    """Smallest extra_yield where sequential net is >= 0 given buy_seed cost."""
    for extra in range(0, max_extra + 1):
        probe = SeedCase(
            book=case.book,
            committed_output=case.committed_output,
            extra_yield=extra,
            owned_seed=case.owned_seed,
            buy_seed=case.buy_seed,
            seed_price=case.seed_price,
            realized_yield_per_seed=case.realized_yield_per_seed,
        )
        if evaluate(probe).net_sequential >= 0:
            return extra
    return None


def scenario_pack() -> dict:
    """Reproducible sign-flip and break-even fixtures for the V4 queue."""
    book = MarketBook(quote0=10.0, impact=1.0, floor=0.0)
    flip = SeedCase(
        book=book,
        committed_output=8,
        extra_yield=3,
        owned_seed=0,
        buy_seed=1,
        seed_price=6.0,
    )
    flip_v = evaluate(flip)
    sunk = SeedCase(
        book=book,
        committed_output=8,
        extra_yield=3,
        owned_seed=1,
        buy_seed=0,
        seed_price=6.0,
    )
    sunk_v = evaluate(sunk)
    be_case = SeedCase(
        book=book,
        committed_output=8,
        extra_yield=0,
        owned_seed=0,
        buy_seed=1,
        seed_price=3.0,
    )
    be = break_even_extra_yield(be_case)
    return {
        "claim": CLAIM,
        "interpreter_sha": INTERPRETER_SHA,
        "engine_blob_sha": ENGINE_BLOB_SHA,
        "assumptions": [
            "fixed realized yield",
            "isolated same-item liquidation at a specified inventory",
            "public market changes, opponent trades, and future shop unlocks are scenarios",
            "owned seed is sunk and is not charged as a fresh purchase",
            "research result is not permission to skip authored PLANT/BUY_SEED",
        ],
        "sign_flip": {
            "committed_output": 8,
            "extra_yield": 3,
            "buy_seed": 1,
            "seed_price": 6.0,
            "quote0": 10.0,
            "impact": 1.0,
            "naive_incremental": flip_v.naive_incremental,
            "net_sequential": flip_v.net_sequential,
            "sign_flip": flip_v.sign_flip,
        },
        "sunk_owned_seed": {
            "owned_seed": 1,
            "buy_seed": 0,
            "purchase_cost": sunk_v.purchase_cost,
            "net_sequential": sunk_v.net_sequential,
        },
        "break_even_extra_yield": be,
    }


def main(argv: Iterable[str] | None = None) -> int:
    pack = scenario_pack()
    print(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
