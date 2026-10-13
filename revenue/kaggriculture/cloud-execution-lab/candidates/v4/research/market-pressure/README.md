# ASTRA-SQUEEZE — adversarial market-control probe

Research/stress component for the **single** TITAN V4 line. This package started from the live swarm hypothesis that unlimited carried inventory plus the scarcity curves might permit a direct hinge squeeze or WHEAT starvation attack. The official interpreter narrows that idea sharply.

## Engine facts that survive source review

Pinned official engine blob: `3c202c7ee921da239356789e266b694635103fc4`; pinned spec blob: `b354d06b742fe48402513792253f1a5c29366b20`.

* Direct `BUY_PRODUCT` is legal only for **WHEAT** and **FERTILIZER**. CARROT/TOMATO/EGG hinge-price goods cannot be purchased from the market, so the proposed direct hinge buyout is not executable.
* Farmer/hand inventory is unbounded, and `PICKUP` can move shed goods into it, but market purchases land in the shed and obey the shared default capacity of 100. Unit actions happen before market actions, so `PICKUP WHEAT` can free room for that turn's buy.
* There is no market-stock availability check on WHEAT buys. Inventory can cross zero. “Starvation” therefore cannot make WHEAT unavailable; it can only raise the rival's acquisition cost.
* A self-created WHEAT squeeze is exactly reversible: BUY quotes post-buy inventory, SELL quotes current inventory, so buy N and later sell the same N with no intervening market flow returns exactly the cash spent.
* **External net demand is the surviving adversarial mechanism.** If we buy before the rival and unwind after the rival makes net WHEAT purchases, the rival's demand moves our unwind onto higher quotes. At the same time, our earlier buy makes those rival purchases more expensive.

## Executed local model checks

`python -B -m unittest -v test_market_pressure.py`

The model is an independent specialization of the pinned official WHEAT formula and per-unit BUY/SELL semantics. Exact receipts from the executed 9-test suite:

* Starting `$3000`, empty 100-slot shed: 95 WHEAT bought for `$2995`, market `10000 -> 9905`.
* Pure 95-unit self round-trip: `$0` profit and inventory returns to `10000`.
* Buy 64, rival net-buys 64, unwind 64: own profit `+$280`, rival surcharge `+$280`, score-margin swing `+$560`.
* Starting-cash symmetric pressure (95 / 95): own profit `+$510`, rival surcharge `+$510`, score-margin swing `+$1020`; final market inventory `9905` reflects the rival's net 95-unit demand.

`pressure_agent(obs)` is included as a **gauntlet stress opponent**, not as the canonical TITAN policy. It uses public market state and own private inventory only, never attempts illegal hinge-product buys, acquires WHEAT in the early window, and unwinds late enough to avoid relying on EOD overflow disposal. Its purpose is to expose whether a candidate with predictable external WHEAT demand is exploitable by a reversible price-pressure position.

## Gate / disposition

Do **not** wire a hinge-hoarding or “market stockout” production feature from the original hypothesis. Those mechanisms are falsified by the interpreter contract. Feed this stress opponent to the existing gauntlet / replay economics owners and measure both seats. A production response is justified only if current V4 loses margin against this pressure opponent while controls without external WHEAT demand remain neutral.

No production/default/archive/Kaggle change is part of this package.
