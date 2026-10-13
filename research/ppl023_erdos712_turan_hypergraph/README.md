# Cyclic Turán hypergraph index — Erdős712 / PPL023

Exact finite navigation in Turán’s classical cyclic three-part \(K_4^{(3)}\)-free construction.

The public CommonJS module represents ten triple-composition blocks and supports edge/nonedge counts, classification, zero-based rank/select, bounded pages, vertex degrees, and a direct missing-edge certificate for any four-set. It uses BigInt throughout mathematical arithmetic and needs no I/O or dependencies.

## Delivered files

| File | Purpose |
|---|---|
| [cyclic_turan_index.cjs](cyclic_turan_index.cjs) | Constructor, saved-descriptor loader and public query methods |
| [CYCLIC_TURAN_API.md](CYCLIC_TURAN_API.md) | Construction/coverage argument, exact ordering, formulas, source attribution, API limits and execution scope |
| [n2197_cyclic_turan_index.json](n2197_cyclic_turan_index.json) | Complete ten-block descriptor, arithmetic, scalar provenance and all fourteen actual public-query receipts |

## Actual finite result

The vertex count 2,197 and queried labels 651, 986, 1,532 and 2,197 are identified retained integers from [Commons #31431](https://github.com/woahwhattheheck/commons/pull/31431). Their prior sequence calculation was not rerun.

Balanced parts have sizes **733, 732, 732**. The index counts:

| Family | Exact count |
|---|---:|
| Edges \(ABC,AAB,BBC,CCA\) | 981,093,378 |
| Nonedges \(AAA,BBB,CCC,AAC,ABB,BCC\) | 783,910,512 |
| All triples | 1,765,003,890 |

The source quartet has a missing \(BCC\) triple \(\{986,1532,2197\}\), at nonedge rank **783,423,984**. A fresh saved reader also returned a block-boundary page, the final complement page, all queried degrees and exact rank/select results.

One constructor computed eight binomial quantities and ten blocks. The fresh reader made fourteen public calls with zero count-construction work. No full vertex, triple or four-set family was enumerated. The JSON stores the complete implicit descriptor and selected query outputs, not individual records for every triple.

## Use the saved index

```js
const { openRetainedCyclicTuranIndex } = require("./cyclic_turan_index.cjs");
const receipt = require("./n2197_cyclic_turan_index.json");
const index = openRetainedCyclicTuranIndex(receipt.snapshot);

index.count("edge");
index.nonedgeInFour(["651", "986", "1532", "2197"]);
index.page("edge", { start: "392758988", limit: 8 });
```

The guide also gives a filesystem-free connected V8 loading example. A saved open checks structure and additive consistency; it does not independently prove the supplied counts or authenticate their source. The checked-in receipt identifies the actual constructor source.

Limits are 256 decimal digits for the total vertex count, 768 for ranks, and 128 returned triples per page. Other sizes, unbalanced/empty parts and rejection branches received source inspection only; they were not separate runtime consumers.

## Mathematical scope and credit

The edge construction is credited to Turán in [Frohmader, EJC 15 (2008), R137](https://www.combinatorics.org/ojs/index.php/eljc/article/download/v15i1r137/pdf/). Its balanced family gives the classical limiting edge-density lower bound \(5/9\). The complement is a cover of every four-set, with limiting density \(4/9\); [Pikhurko, Advances in Mathematics 464 (2025), 110148](https://pikhurko.github.io/E/Pikhurko25am.pdf) states the exact maximum-edge/minimum-cover relationship.

This finite instance establishes
\[
\operatorname{ex}(2197,K_4^{(3)})\ge981093378,
\qquad T(2197,4,3)\le783910512.
\]
No extremal equality, new limiting density, novelty or external frontier is claimed. Original attribution and submission ownership remain intact.
