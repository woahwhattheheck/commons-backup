# Erdős 1052: retained unitary-divisor index

A public, dependency-free JavaScript API for exact counts, interval sums, numerical rank/select and consecutive pages of unitary divisors. It builds and saves two half-subset product tables, then restores them without regenerating the products.

**Completed finite input:** the 24 prime-power blocks of **89!**, composed through 34 factorial-valuation divisions from the identified #31426 prime source. Two 4,096-row halves implicitly represent **16,777,216** unitary divisors; **16,777,215** are proper. The inclusive interval **[10^30,10^60]** contains **5,472,372** proper unitary divisors, with exact sum

```text
125096473838759904348068399635264963909595967607889450685508347008
```

The complete saved record includes all half products and prefix sums, three full cutoff vectors, 226 selection bisection records, two pages containing 32 divisor records, complement witnesses, membership rejections and work counters. The complete cross-product family was not enumerated.

## Files

| File | Contents |
| --- | --- |
| [unitary_divisor_index.cjs](unitary_divisor_index.cjs) | Factorial-input composer, constructor and retained reader. |
| [UNITARY_DIVISOR_API.md](UNITARY_DIVISOR_API.md) | Mathematical derivation, full API contract, source custody and actual results. |
| [factorial89_unitary_divisor_index.json](factorial89_unitary_divisor_index.json) | Complete 953,407-byte data artifact; open its `snapshot` field. |

## Open the retained data

In connected JavaScript, provide the complete fetched module and JSON as `sourceText` and `dataText`:

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);

const saved = JSON.parse(dataText);
const index = loaded.exports.openRetainedUnitaryDivisorIndex(saved.snapshot);
const summary = index.summary();
const total = index.count({ kind: "proper" });
```

The index also exposes `prefix`, `interval`, `rank`, `select`, `page`, `snapshot` and `work`. Ranks are zero-based in increasing numerical divisor order. The default family is proper; use `kind:"all"` to include N. Bounds are inclusive. Whole prime powers are indivisible blocks: the actual rank query rejects divisor 2 because gcd(2,89!/2)=2, while it admits the entire block \(2^{85}\) at rank 232,241.

A fresh reader made 12 public calls with no new prime-power, half-subset-product, factor/sigma construction, sort, sieve or primality work. Opening still checked all 8,192 prefix-sum equalities, mask coverage, row order, two square-root products and two aggregate products. Prime-source completeness/primality and saved individual product identities remain identified premises; opening is not an independent provenance proof.

## Mathematical scope

[Subbarao and Warren, *Unitary Perfect Numbers* (1966)](https://doi.org/10.4153/CMB-1966-018-4), give the standard convention \(\sigma^*(N)=\prod(1+p^a)\). Unitary perfection means \(\sigma^*(N)=2N\); the proper family removes N once. For N=1 there is one all-family divisor and no proper divisor. This finite input is unitary deficient.

The [FormalConjectures statement of Erdős 1052](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/1052.lean) concerns global finiteness. The inspected source tags that declaration open, while separate solved declarations do not settle it. The 1966 paper's fixed-parameter finiteness results are also distinct from global finiteness. No known perfect-number example, earlier source computation or linked Lean proof was replayed.

Executed source blob: `64494e6fb71b877d50ef63d2c14abc8412e20f57`. Complete data blob: `3cad8b2aaa202bf868dc490692410092989871ec`. The guide identifies the exact accepted prime-source path, merge, blob and selected field. No novelty, global finiteness or external-frontier claim.
