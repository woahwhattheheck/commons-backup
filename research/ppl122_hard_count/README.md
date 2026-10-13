# Kimberling's A Hard Count: complete finite history

**128 complete tables · 65,227 written cells · 623 distinct values · exact saved navigation**

This contribution implements the cumulative counting process in
[Clark Kimberling's problem 4](https://faculty.evansville.edu/ck6/integer/unsolved.html).
It starts with one written 1, then appends a table listing every value already
written and its cumulative count. Each count cell and each label cell is one
new written occurrence.

The complete delivered prefix contains every integer from 1 through **518**.
Its first missing value is **519**, and its largest written value is **714**.
These are finite-prefix findings; they do not settle eventual occurrence of
every positive integer.

| File | Contents |
|---|---|
| [hard_count.cjs](hard_count.cjs) | Bounded constructor, resumable continuation and saved-data API |
| [one_seed_history.json](one_seed_history.json) | All 128 tables, all 65,227 occurrence positions and all retained method receipts |
| [HARD_COUNT_API.md](HARD_COUNT_API.md) | Recurrence proof, conventions, API, exact work, bounds and source custody |

## Findings from the saved record

Value **156** is absent after table 54. Its first occurrence is at position
**13,567** in table **68**, where it is the count for label **23**.
The completed record contains 89 occurrences of 156.

Value **518** first appears in table **107**, at position **41,152**, as the
count for label 2. The complete initial interval reaches 518 later, at
table 125, when earlier gaps have been filled.

The zero-based occurrence rank **100** for value 1 selects position **1,861**,
a count cell in table **30** for label **95**. A rank query at that position
returns 100. At the final frontier, value 1 has 720 occurrences.

Every position includes the seed and starts at zero. Generated columns are
ordered numerically; the serialized stream writes each whole count row and
then its whole label row.

## Use the delivered index

```js
const { openHardCount } = require("./hard_count.cjs");
const evidence = require("./one_seed_history.json");

const reader = openHardCount(evidence.record);
const origin = reader.firstAppearance({ value: "156" });
const count = reader.countAt({ value: "1", through_table: 54 });
const occurrences = reader.pageOccurrences({
  value: "156", offset: 0, limit: 8
});
```

The exports also include `createHardCount`, `SCHEMA` and `LIMITS`.
A facade's `snapshot()` returns a complete plain JSON record. Opening a record
checks structure and every stream/index binding; it does not regenerate its
counting history. A new session preserves old sessions and receipts.

## Actual execution and endpoint

The first advance requested 64 tables with 8,192 new-token slots. It completed
54 tables and stopped before the next whole table. A fresh session reused
that saved prefix and added 74 tables. It then reached the global
65,536-token ceiling: 309 slots remain, while another table requires 1,246.
The intended 256-table target was not reached.

All 54 earlier tables, all 8,039 earlier occurrence positions and the earlier
session remained literally unchanged. A fresh reader made 19 navigation
calls with zero table reconstructions, recurrence steps or occurrence-index
rebuilds. Its complete core remained unchanged.

The source is frozen at
`8b58d5a5a674172ad9cf1eae2e8c89bea30dea1f`.
The complete 928,401-byte data has blob
`76fe7df3a3c4f1c5f01d0edeb5f562e150d2e3bf`.
The guide provides all actual counters, single-run timing limits and
unexecuted branches. No tests, fixtures, native executor or workflow calls
were used.

For an indefinitely continued process, a short argument proves unbounded
support: each existing label is written again every round, so its frequency
eventually exceeds any proposed bound on all written values. The stronger
all-positive coverage question remains separate. The author's post-2025
reward form is an OEIS donation in the solver's name; no submission, contact
or award claim was made.
