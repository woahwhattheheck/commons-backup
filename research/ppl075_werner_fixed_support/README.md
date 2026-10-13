# PPL075: exact Werner fixed-support certificates

This package gives a reusable exact certificate for the two-copy Werner partial-trace form when the left support is supplied explicitly. It keeps the complex right factors unrestricted in the mathematical result.

The actual input uses the row-major vectors of `diag(1,2,3,5)` and the 4-by-4 cyclic shift. Its 32-by-32 integer form has an exact rational LDL factorization with **32 positive pivots and no kernel**. Therefore every nonzero coefficient matrix in this fixed left-support family has strictly positive expectation.

The complete determinant is:

```text
111619095298594930035071103900982976640371707084800
```

A fresh saved-reader consumer made ten queries with zero form construction or elimination. Its explicit non-Hermitian rank-two matrix has norm squared 4720, partial-trace norm squares 1668 and 1404, trace `10+10i`, and normalized state expectation **33/9440**. All query inputs, traces, transformed coordinates, sum-of-squares terms and the complete coefficient matrix are retained.

## Files

- [werner_fixed_support.cjs](werner_fixed_support.cjs): dependency-free BigInt/rational constructor and saved-reader API.
- [WERNER_FIXED_SUPPORT_API.md](WERNER_FIXED_SUPPORT_API.md): full state/tensor conventions, exact reduction and certificate argument, API, limits and complete result.
- [diagonal_shift_support_certificate.json](diagonal_shift_support_certificate.json): complete input, integer form, maps, factorization and ten request/response records.

## Use

```js
const api = require("./werner_fixed_support.cjs");
const packet = require("./diagonal_shift_support_certificate.json");
const index = api.openRetainedWernerFixedSupport(packet.snapshot);

index.summary();             // rank 32, nullity 0, positive definite
index.factorDirection(31);    // exact rational right factor and evaluation
index.formPage(0, 16);        // retained rows; no matrix construction
index.work();                // no elimination
```

The module is also usable as plain CommonJS text in the connected V8 runtime; the guide gives that loading pattern. Source authentication belongs to the caller. The reader performs structural checks and exact identities for selected queries, not a reconstruction or independent authentication of the whole certificate.

## Source and scope

[KCIK Problem 5](https://kcik.ug.edu.pl/wp-content/uploads/2021/12/2002.03233.pdf) supplies the original state. [Costa Rico's published partial-trace criterion](https://doi.org/10.1007/s11005-025-01935-y) supplies the mathematical convention. A [July 2026 author preprint](https://arxiv.org/abs/2607.24309) claims the full two-copy result; this package records that dated claim without certifying the proof.

The deliverable is an exact computational certificate for one restricted continuous family and a bounded reusable API. It does not claim a new global result or a still-open status for the full two-copy target. The rational query bounds do not restrict the certificate's implication for all complex right factors in the fixed support.

Executed source: `7b12525be10d3532e5dfec80bd36d1caa7c91d48`. Complete data: `4271b18c70007c485c641112747b23c47a8bd1cf`. Both computations used the same unchanged source.
