# Finite dictionary factor universality

This directory contains a dependency-free connected-V8/CommonJS index for contiguous factors of a finite dictionary's Kleene star. It returns a complete finite universality certificate or the exact shortest missing length and a countable, rankable, selectable shortest-word family when the bounded search finishes.

## Published mathematical context

The old Shallit problem-17 complexity question is settled: [Mika and Szykuła, JACM 2021, Theorem 5.12](https://arxiv.org/pdf/1902.06702) prove PSPACE-completeness even for binary alphabets. This package implements finite instances and does not claim a new complexity classification or general missing-word length bound.

The actual dictionary is $S_6$ from [Gusev and Pribavkina, DLT 2011](https://arxiv.org/pdf/1104.0388). Their published formula already gives shortest length 91. The new retained finite index accounts for **all 128 shortest words** and exposes their complete data through a public API.

## Files

| File | Contents |
|---|---|
| [finite_factor_index.cjs](finite_factor_index.cjs) | Bounded trie/subset compiler, explicit resource stops, retained-index loader, exact count/rank/select and paging. |
| [FINITE_FACTOR_INDEX_API.md](FINITE_FACTOR_INDEX_API.md) | Definitions, self-contained automaton and shortest-DAG reasoning, contracts, limits, source attribution, and actual consumer. |
| [gusev_pribavkina_s6_factor_index.json](gusev_pribavkina_s6_factor_index.json) | Complete 92-word input, 125 trie states, 1,383 subset states, 2,708 transitions, suffix counts, and all 128 shortest words with paths. |

The search completed every layer needed to establish shortest length 91. The entire shortest family has seven freely chosen binary positions and 84 fixed positions. The complete finite output proves exhaustion for this dictionary; it makes no all-parameter exhaustiveness claim.

One actual compiler call produced the data. A fresh connected V8 invocation opened the retained index and exported every shortest word without replaying the search or count recurrence. The loader treats the retained certificate as a source premise and performs structural checks, not independent mathematical authentication. No native or provider runtime is required by the module.
