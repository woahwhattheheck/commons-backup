# Finite sum–product subsets

A complete fixed-host sum–product census and saved-query API for Erdős 52 context.

For every nine-element subset of {1,…,17}, the saved record contains the distinct sum and product image sizes, with diagonal pairs included. The unique minimizer of the larger image is

    A = {1,2,3,4,6,8,9,12,16},
    |A+A| = |AA| = 25.

The complete Pareto signatures are (17,36), (18,35), (19,32), (20,30), (25,25), each realized by one subset. This is an optimum only inside the stated finite host.

## Files

- [sum_product_subsets.cjs](sum_product_subsets.cjs): bounded BigInt pair compilation, incremental subset census and saved navigation.
- [SUM_PRODUCT_API.md](SUM_PRODUCT_API.md): conventions, proof, source attribution, complete API and trust boundary.
- [nine_subsets_interval17.json](nine_subsets_interval17.json): all 153 host pairs, 24,310 subset rows, 210 histogram cells, five Pareto sets and all 28 reader outputs.

## Use saved data

    const { open } = require("./sum_product_subsets.cjs");
    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const best = reader.openSlice(reader.minimizers()).select(0);
    const productFibers = reader.fibers(best.rank, "product");

No full census is rebuilt by these operations. A fiber request does scan and group the saved host-pair ledger; the guide reports that work explicitly. The loader checks structure, not mathematical provenance.

The generic host may contain negative integers or zero, must be strictly increasing, and is capped at 20 members. Pages are capped at 64. Counts are for labelled subsets and distinct-value images, not isomorphism classes or pair multiplicities. Ordered pair fibers separately assign diagonal weight one and off-diagonal weight two.

Chang's 2003 definitions and Xu–Zhou's 2023 arithmetic-progression results retain their attribution. The global asymptotic conjecture quantifies over arbitrary finite integer sets; this finite host classification does not resolve it. No current literature frontier or novelty is claimed.
