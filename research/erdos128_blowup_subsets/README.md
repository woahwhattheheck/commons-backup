# Labelled subsets of a C5 blow-up

Exact subset-size and induced-edge counts, with conditioned labelled rank/select, for a finite graph blow-up.

The retained classical C5 instance has five parts of size six: 30 vertices and 180 edges. Its 16,807 occupancy patterns represent all 1,073,741,824 labelled vertex subsets in 477 size/edge buckets. Exactly 200 of its size-15 subsets attain the minimum of 18 induced edges. The saved reader exports all 200 and includes 34 complete query responses.

Start with [the API guide](BLOWUP_SUBSETS_API.md), then open the [index envelope](cycle5_size6_index.json) and the five occupancy shards it identifies using [the CommonJS module](blowup_subsets.cjs). [Reader results](saved_reader_queries.json) retain conditional families, ranks, selections and query-work counters.

Norin and Yepremyan document the uniform C5 blow-up as the classical sharpness family for Erdős's sparse-half conjecture. This package adds finite labelled distribution and navigation; it does not solve the general conjecture or claim the construction as new.
