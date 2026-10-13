# Homogeneous graph partitions

Exact partition polynomials and saved navigation for a supplied finite labelled graph.

The actual input is the retained eleven-vertex Mycielski graph from [#31448](https://github.com/woahwhattheheck/commons/pull/31448). The new computation covers all **2,048 induced vertex subsets**, retaining **39,936 coefficients** for independent, clique and homogeneous block modes.

For the full graph, χ=4, ζ=4 and χ(complement)=6. The optimum unlabelled partition counts are respectively **520, 840 and 87**. The known chromatic value four remains credited to the established construction. Singleton blocks count once even though they are both cliques and independent sets.

[PARTITION_API.md](PARTITION_API.md) gives the exact recurrence, source scope, API, bounds and retained query results.

| File | Contents |
| --- | --- |
| [partition_index.cjs](partition_index.cjs) | Compiler and separate saved-table reader. |
| [mycielski_partition_polynomials.json](mycielski_partition_polynomials.json) | Complete graph, all coefficients, profile and 30 actual reader queries. |
| [PARTITION_API.md](PARTITION_API.md) | Mathematical derivation, interface and conventions. |

Count, prefix, rank, select and page operations navigate unlabelled partitions. A separate falling-factorial evaluation counts assignments of genuine colour labels. No graph generation, old cut/component computation or saved-reader polynomial recurrence is repeated.

The source question concerns a diverging chromatic–cochromatic gap in G(n,1/2). [Heckel's February 2025 revision](https://arxiv.org/html/2409.17614v2) reports partial progress on specified graph sizes. This deterministic finite host does not establish an asymptotic random-graph statement, a current full resolution or a new extremal record. Formal625's unavailable route remains held; no sponsor submission occurred.
