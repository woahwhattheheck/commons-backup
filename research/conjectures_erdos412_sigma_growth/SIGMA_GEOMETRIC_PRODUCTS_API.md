# Sigma through cached geometric products

[sigma_geometric_products.cjs](sigma_geometric_products.cjs) computes the divisor sum of a product from exact factorizations of its components. It caches each distinct component factorization and exports/imports that catalog as ordinary JSON records. The existing [sigma_orbit_merge.cjs](sigma_orbit_merge.cjs) supplies its deterministic factorization dependency.

The actual consumer continues the two retained index-nine heads from [#31197](https://github.com/woahwhattheheck/commons/pull/31197). It adds **61 sigma transitions**, reaches absolute indices **39 and 40**, and retains all new transitions plus a shared catalog of **128 distinct component factorizations**. The complete data is [sigma_geometric_continuation_59548377_59548401.json](sigma_geometric_continuation_59548377_59548401.json).

Together with the preserved 18-transition prefix, the records exclude a common orbit value through

\[
771258603484062010708460568575999.
\]

The larger remaining head, 771258603484062010708460568576000, remains a possible future meeting. The run stopped at its chosen 128-factorization allowance, with the next uncached component 72 explicitly retained.

## Product composition and its exact boundary

Suppose the supplied components have complete prime factorizations

\[
c_j=\prod_p p^{e_{p,j}}.
\]

For their product N, collect the exponents

\[
E_p=\sum_j e_{p,j}.
\]

Then

\[
N=\prod_p p^{E_p},
\qquad
\sigma(N)=\prod_p(1+p+\cdots+p^{E_p}).
\]

This identity follows by choosing each divisor's prime exponents independently. Components can share prime factors, and repeated component entries contribute repeatedly to E_p. The implementation therefore combines the exponents before forming the geometric sums.

The output geometric sums are a product representation of the next orbit value. They can be passed directly as the next step's components. This lets a large full product advance while every fresh trial-factor input remains at most 10^12.

The first actual left input is

\[
2839668249600=65535\cdot13\cdot6\cdot14\cdot20\cdot32\cdot62.
\]

Shared factors across these seven components give

\[
2839668249600=2^{10}3^2 5^2\cdot7\cdot13\cdot17\cdot31\cdot257.
\]

The new step records the corresponding geometric factors and the exact result

\[
\sigma(2839668249600)=13730397198336.
\]

All component factorizations, combined exponents and geometric sums used in that calculation are retained.

The factorizer dependency remains unchanged at blob 4e5641b7f0cb715e3e8de38362c29500989c544f. It uses deterministic trial division under its 10^12 cap. Each newly produced component record preserves its complete dependency output, including prime powers, terminal trial bounds and work counters. The dependency also returns sigma of the component; that field is retained as part of the record but is not used to compute sigma of a product with shared prime factors.

## Public interface

The module is plain CommonJS and runs in connected V8. It contains no imports, native execution, network calls or I/O. Its exports are createSigmaGeometricProducts and limits.

### Constructing the index

~~~javascript
const index = productApi.createSigmaGeometricProducts(
  directApi.sigmaFactorization,
  {
    component_limit: "1000000000000",
    max_factorizations: 128
  }
);
~~~

The first argument must be the exact sigmaFactorization function from the linked public dependency. The module validates returned prime-power/input bindings. Primality is supplied by that exact dependency; this is an explicit dependency contract, not a way to certify arbitrary callbacks.

| Option | Contract |
| --- | --- |
| component_limit | Positive integer through 10^12; default 10^12 |
| max_factorizations | Integer Number from zero through 1024; default 128; fresh dependency calls allowed in this index |
| retained_catalog | Optional array of up to 1024 complete catalog entries from a retained exact run, with consecutive indices starting at zero |

Mathematical integer inputs accept BigInt, safe integer Number or canonical nonnegative decimal strings, with at most 2048 decimal digits. Component values must be positive.

A retained catalog is a trusted output of the stated exact dependency. Import checks its component identities, distinctness, index order and reconstruction by the recorded prime powers. It does not repeat trial factorization or independently prove the recorded primes. Preserve the catalog's source and the factorizer's source identity when transferring it.

Imported entries keep their indices. New entries are appended, so earlier transition references remain valid. The caller's array is copied. An imported entry must satisfy the configured component limit.

### step(request, newFactorizationBudget)

The request contains components, an array of at most 64 positive factors, and optionally expected_input. The API checks the complete product against expected_input when the component values are within the factor bound.

The per-call fresh-factorization budget is an integer from one through 16, default 16. Already-cached components do not consume that budget. Repeated components reuse the same catalog entry while contributing their exponents with their full multiplicity.

The empty product is supported as the positive-integer identity: its value and divisor sum are one. Unit components do not create factorization records. These point-operation conventions do not add seed one to the original orbit problem.

The step schema is erdos412.sigma_geometric_product_step/v1:

| Status | Meaning |
| --- | --- |
| COMPLETE | All component factors were available; the returned prime powers reconstruct the input and determine its exact sigma value |
| NEEDS_MORE_FACTORIZATIONS | The per-call fresh-factorization budget ended before all components were ready; repeat the unfinished request on the same index |
| FACTORIZATION_LIMIT | The index's total fresh-factorization allowance is exhausted at the next uncached component |
| COMPONENT_LIMIT | At least one input component exceeds component_limit; no factorizer call is made for this request |

A complete step returns input_components, component_catalog_refs, the combined prime_powers, factor_product, sigma and output_components. Each nonunit component reference is an index into the shared catalog; unit references are null. The two next-component flags say whether the output fits the next request's component-count and component-value bounds.

For a component limit, input_binding explicitly says that the product was not checked. This early refusal makes no sigma assertion. In the actual orbit consumer, the refused components came from an already completed transition, whose product binding was retained.

An unfinished factorization request returns the completed component references, the next component index/value and a continuation request. Cached factorizations survive a bounded call ending. Invalid shapes, integer formats, product bindings or unsupported component counts throw an Error with a code field; already-retained catalog entries remain available.

### describe() and records(page)

describe() reports the catalog size, fresh-factorization capacity, completed product steps and exact work counters. When the index imports a nonempty catalog, it also reports imported_catalog_entries and fresh_factorizations. Its factorizations field counts the complete catalog, including imported entries; max_factorizations and remaining_factorization_capacity concern fresh calls in the current index.

records({start_index, limit}) returns copied catalog entries. The page limit is from one through 128, default 128. Indices are zero based, and a start equal to the current catalog count produces an empty page. A null next_start_index means the end of the currently retained catalog. Pagination does not assert that an orbit computation has ended.

The catalog can have at most 2048 entries: up to 1024 imported and 1024 fresh. Its schema is erdos412.sigma_component_catalog_page/v1.

## Bounded arithmetic and accounting

Every fresh component factorization retains the direct dependency's conservative bound of 500,040 remainder tests and 39 exact quotient divisions. A step call with 16 fresh calls therefore has an upper bound of 8,000,640 remainder tests.

With at most 64 components, the sum of their prime multiplicities is at most 64 times 39, or 2496. Combining exponents and forming all output geometric sums uses at most that many successive prime-power multiplications per complete step. Full products and geometric sums use BigInt. The bounded Number arithmetic remains inside the unchanged direct factorizer.

This consumer reserved at most 64 new sigma transitions and 128 distinct fresh component factorizations. When the first index stopped after 94 fresh factorizations, its 34 unused calls were transferred to a new index that imported the 94 existing entries. The two live-index allowances were used sequentially under the same 128-call total.

The completed execution used:

| Quantity | Actual value |
| --- | ---: |
| New sigma transitions | 61 |
| New left/right transitions | 30 / 31 |
| Distinct fresh component factorizations | 128 |
| Prime-power factors in the shared catalog | 328 |
| Remainder tests | 32,155 |
| Exact quotient divisions | 389 |
| Trial candidates | 31,783 |
| Product-step calls | 63 |
| Component lookups | 550 |
| Cached component lookups | 421 |
| Geometric prime-power multiplications | 1,953 |
| Fresh index instances | 2 |

The 63 step calls comprise 61 completed sigma steps and two finite boundary results. Of the 550 component lookups, 421 found cached entries, 128 produced a fresh factorization, and one reached the final uncached component after the budget ended.

Prime-power reconstruction checks total 568: 328 for fresh component records and 240 when importing the existing catalog. Those input-binding checks used the retained prime powers; the import made **zero factorizer calls**. Work counters name these operations explicitly and do not purport to count every JavaScript operation.

The largest fresh component was 549,755,813,887, within the 10^12 limit. At most seven fresh factorizations occurred in any one actual step call. The actual maximum number of input or output components was 13, and the largest combined prime multiplicity was 55.

## Actual saved-catalog continuation

The first segment added 41 transitions, with 94 distinct component factorizations. It reached the right orbit's index-30 head with a geometric component

\[
17592186044415=2^{44}-1,
\]

arising from the prime power 2^43 in the preceding input. The component exceeds the direct factor limit. A single exact difference-of-squares refinement gives

\[
2^{44}-1=(2^{22}-1)(2^{22}+1)
        =4194303\cdot4194305.
\]

Both replacement components are within the cap. Their product was bound exactly to the saved old component. The refinement changes the product representation of the current head; it does not recompute an orbit transition.

The current heads, refined components, catalog and remaining budget were serialized as JSON. A fresh connected V8 isolate loaded the two public modules, imported all 94 catalog entries, and continued from absolute indices 29 and 30. It added 20 transitions using 34 new component factorizations. All imported catalog entries remained identical, and no fresh factorizer call used a previously catalogued value.

A connected loader can evaluate the two committed modules as follows:

~~~javascript
function loadCommonJS(sourceText) {
  const box = { exports: {} };
  new Function("module", "exports", sourceText)(box, box.exports);
  return box.exports;
}

const directApi = loadCommonJS(directSourceText);
const productApi = loadCommonJS(productSourceText);
const saved = JSON.parse(serializedCheckpoint);

const index = productApi.createSigmaGeometricProducts(
  directApi.sigmaFactorization,
  {
    ...saved.index_options,
    retained_catalog: saved.retained_catalog
  }
);

const rightStep = index.step({
  components: saved.heads.right.components,
  expected_input: saved.heads.right.value
}, 16);
~~~

In the actual second segment, index_options allowed exactly 34 fresh factorizations. The consumer then repeatedly selected the smaller head, called step, and committed only complete increasing transitions. Its absolute indices and opposite-head decisions are retained in every new transition record. No original or first-segment sigma transition was replayed.

The first checkpoint's 94 entries are the unchanged prefix of the final component_catalog array. The data includes all other consumed checkpoint fields and the exact component refinement. The final 128-entry catalog is directly accepted by retained_catalog for a later bounded continuation.

## Final finite result and next input

The final heads are:

| Original seed | Last absolute index | Last known value |
| --- | ---: | ---: |
| 59,548,377 | 39 | 771258603484062010708460568576000 |
| 59,548,401 | 40 | 256715658654037094255935758336000 |

The accepted [smaller-head merge invariant](SIGMA_ORBIT_MERGE_API.md) rules out every value below the larger head. Applying it to these final heads gives the stated closed exclusion endpoint. The larger head itself could be reached later by the other orbit.

The final status is FACTORIZATION_LIMIT. The next right-head request has components

~~~text
16383, 29524, 31, 57, 16105, 14, 18, 20, 62, 72, 242, 632, 5420
~~~

Its next uncached component is 72 at component index nine. It is within the numerical factor cap. A later operation can assign a fresh bounded allowance and consume this request with the complete saved catalog; the current operation has zero fresh-factorization capacity and three unused transition slots.

The JSON contains every one of the 61 new sigma transitions, all 128 component factorizations and both complete known paths. Left indices zero through nine and right indices zero through nine are copied from #31197; subsequent values are new here. The original 18 transition certificates remain in that unchanged predecessor dataset. Together the two datasets carry all 79 known transitions and the 40-term/41-term paths.

## Attribution and scope

This continues the original #16060 carrier and the #31197 direct merge, preserving their authorship and submission ownership. The original source attributes the orbit question to van Wijngaarden via [Erdős's 1979 paper, §1, page 71](https://www.renyi.hu/~p_erdos/1979-23.pdf). [Cohen and te Riele's 1996 paper](https://ir.cwi.nl/pub/10355/10355D.pdf) supplies the historical finite orbit-tree computations. The [July 28 working report](https://www.erdosproblemaday.com/report/412), credited to Patrick White with model assistance disclosed there, is expressly not independently verified. The predecessor guide records the detailed source boundaries.

The current [Formal Conjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/412.lean) uses seeds at least two, the sum of all positive divisors, and independent natural iterate indices including zero. This consumer preserves those conventions. It makes no infinite-separation, conjecture-resolution, priority or external-frontier claim and supplies no new Lean elaboration or sponsor submission.
