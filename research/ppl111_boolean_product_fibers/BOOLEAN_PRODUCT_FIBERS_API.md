# Finite Boolean products and inverse fibers

This package compiles a fixed Boolean matrix into small block-product tables and a complete finite image index. It counts input vectors by output and Hamming weight, returns products for sequentially supplied vectors, and navigates the vectors producing a requested output. Its bounded preprocessing may be exponential. It makes no improvement or refutation claim for the Online Matrix–Vector Multiplication conjecture.

## Primary source and scope

Henzinger, Krinninger, Nanongkai and Saranurak, [Unifying and Strengthening Hardness for Dynamic Problems via the Online Matrix-Vector Multiplication Conjecture](https://arxiv.org/abs/1511.06773), November 2015, define OMv using an n×n Boolean matrix and n column vectors received one at a time: each product must be returned before the next vector is received. Conjecture 1.1 concerns total O(n^(3−epsilon)) time, including the computation, with error probability at most 1/3. Their Section 2.1 separately treats rectangular dimensions and polynomial preprocessing. The directly read [author PDF](https://arxiv.org/pdf/1511.06773) supplies these definitions; the article identifies its preliminary STOC 2015 version.

Here Boolean multiplication means OR over coordinatewise AND:

    (Mv)_i = OR_j (M_ij AND v_j).

It is not multiplication over the field of two elements. Duplicate witnesses do not cancel. A zero input gives a zero output. Repeated rows and zero rows are permitted.

The actual input is a fixed 12×13 matrix. This finite rectangular instance, its exact fibers and its sequential interface do not settle the source’s square asymptotic problem. No timing benchmark, new complexity bound, current conjecture-status survey, sponsor contact or prize submission is asserted. Reading the source’s statements is not a proof audit of its reductions.

## Reused input and new operation

The matrix uses the complete local flags in the released [PPL087 certificate, #31614](https://github.com/woahwhattheheck/commons/pull/31614), blob 55964c45530dbcf06855c08fc6f0c4f2fad369e1. That source concerns n=10^1000+477965 and the divisors 2,3,5,7,11,13.

For each divisor in that order, the new matrix takes two rows: the saved linear-hit flag and the saved quadratic-hit flag. Columns are k=0,...,12. Entry (row,k) reads the relevant bit of snapshot.local[i].flags[k modulo modulus]. It does not evaluate n+k, n+k², n modulo a modulus, a CRT recurrence or any prime predicate.

The complete row strings, with column zero printed first, are:

    0101010101010
    0101010101010
    1001001001001
    1001001001001
    1000010000100
    1000010000100
    0000010000001
    0000000000000
    0000001000000
    0000000000000
    0001000000000
    0000100001000

The new product has a simple coverage meaning: selecting a set of these thirteen columns marks each divisibility-test row that is hit by at least one selected column. It does not say that one column hits every marked row. In particular, the OR aggregation must not be confused with a simultaneous-prime filter on a single k.

Only the matrix is an input premise. No earlier local test, polynomial value, CRT row, candidate count or primality calculation is replayed. The complete provenance labels remain in the new input envelope.

## Input contract and limits

buildIndex(input) accepts:

- matrix: 1 through 20 binary row strings, all of the same positive length from 1 through 20.
- block_size: an integer from 1 through 5.

Additional provenance fields are retained by the certificate envelope but are not mathematical parameters. Rows and columns are labelled. Input bit j denotes column j; output bit i denotes row i. Numeric masks fit within twenty bits, so bit operations and all counts are exact safe integers. Each total count is at most 2^20.

The compiler refuses a construction exceeding 100,000 accumulated layer states, 500,000 transition arcs or 1,500,000 coefficient cells. Each reader allows at most 200,000 distinct conditional memo cells; it refuses additional cells rather than silently truncating a fiber. Pages have at most 128 rows. These limits are finite implementation bounds, not mathematical upper bounds for the general source problem.

The exports are buildIndex, openIndex, SCHEMA and LIMITS. Construction is synchronous and returns a complete snapshot or throws. The reader copies the snapshot before indexing; returned matrices, block tables, profiles and counters are copies.

## Block products

Divide columns into successive blocks of at most b columns. For every block pattern c, store the Boolean OR of exactly its selected column masks. Store its Hamming weight as well. Pattern zero has output and weight zero. For nonzero c, remove its least significant set bit to obtain p and let j be that bit’s column:

    table[c] = table[p] OR column[j],
    weight[c] = weight[p] + 1.

Induction on the number of selected bits proves the block table. A complete vector’s product is the OR of its saved block outputs. Thus the online reader needs one lookup and one accumulating OR per block. The implementation counts the initial OR with zero as an OR operation.

This is ordinary tabulation of a bounded matrix. Fast lookup after this preprocessing is not an uncharged solution to OMv. The complete image compilation below can have exponentially many reachable states and is included in the package’s declared work.

## Complete output/cardinality layers

Layer i records all outputs attainable after the first i blocks. Each state stores a coefficient array: counts[w] is the number of block assignments of total input weight w producing that output. The initial layer contains only output zero with coefficient one at weight zero.

For each previous state s and each next block choice c, the target is

    output(s) OR table[c].

For every old coefficient of degree w, add it to degree w+weight[c] at that target. Different choices leading to the same output are added, not identified as the same input vector. Since every full vector has a unique sequence of block choices, this recurrence counts each input exactly once and covers every input. Sorting states by output supplies stable identifiers; saved transition rows identify the target state for every source-state/block-choice pair.

No flat census of all full input masks is required. The compiler does enumerate every block pattern and every retained state/choice transition; both quantities are reported. The counter input_vectors_enumerated=0 refers only to an exhaustive flat full-input census. It does not deny block-pattern enumeration or the explicit selected vectors returned by the reader.

The final layer partitions all 2^n inputs by output and weight. Its smallest positive coefficient degree is the minimum support size for that output. This is an optimum within the fixed supplied matrix, not a statement about arbitrary matrices.

## Conditional inverse navigation

An inverse query fixes a target output and optionally an exact input weight. A memo cell

    target : layer : state : remaining_weight

counts completions from the saved state. An asterisk means that any remaining weight is allowed. A state already containing an output bit outside the target contributes zero. At the terminal layer, the count is one precisely for the target output and, if specified, remaining weight zero. Otherwise the count is the sum over all next-block choices of the corresponding saved child count, subtracting the choice’s weight when constrained.

The memo reads saved transitions and block weights. It performs new conditional arithmetic; it does not rerun matrix products, block-table construction or the unconditioned layer recurrence. The complete memo produced by the actual queries is retained alongside their answers.

Input order within a fiber is lexicographic in numerical block-choice values, starting with block zero. This differs from numerical whole-mask order. Rank and select skip branches by their exact conditional counts. Each selection retains its chosen state/choice path and residual rank. A rank query returns null for an input outside the requested output/weight fiber.

## Public reader interface

| Method | Meaning |
| --- | --- |
| summary() | Dimensions, block sizes, input/output counts and construction work |
| matrix() | The complete saved binary matrix and block size |
| profiles() | Every reachable output, complete weight coefficients, total and minimum weight |
| block(index) | One complete saved block-output and weight table |
| product(mask) | Boolean product and the block choices used |
| fiberCount(output,weight=null) | Count from the saved final coefficients |
| fiberSelect(output,rank,weight=null) | Selected input and full branch trace |
| fiberRank(output,input,weight=null) | Its rank or null, with saved transition trace |
| fiberPage(output,start="0",limit=16,weight=null) | Up to limit selected inputs in the declared fiber order |
| stream() | A sequential submit/state interface |
| conditionalTable() | All memo cells created so far, with their semantics |
| work() | Explicit reader work counters |

Input and output masks, weights, indices and page sizes are bounded safe integers. Ranks and page starts are canonical nonnegative decimal strings of at most eight digits, with values no larger than 2^20. A rank must be below the requested fiber count. A page may start exactly at that count and be empty. Missing outputs have count zero; their selections are invalid and their empty pages are supported.

A stream is created with round zero. submit(mask) validates one vector, returns its product and round number, and then retains that response. The next call need not be supplied until the prior response is available. It consumes no list of future inputs. state() returns the current round and last reply. The matrix remains fixed. The interface is a finite sequential product service, not a proof of a time bound under the OMv conjecture.

openIndex checks dimensions, bounds, row and coefficient shapes, increasing state outputs, transition targets, block-table sizes and the initial state. It indexes saved arrays without verifying every matrix/table relation or replaying the coefficient recurrence. Its semantic answers rely on the identified construction’s provenance. Structural loading alone is not an independent mathematical certification of arbitrary submitted data.

## Actual construction and saved queries

One new compilation with block size four produced:

| Record | Exact size |
| --- | ---: |
| Matrix entries read | 156 |
| Block-table sizes | 16,16,16,2 |
| Total block entries | 50 |
| Block recurrence ORs | 46 |
| Layer state counts | 1,6,34,39,55 |
| Total states | 135 |
| Saved arcs / transition ORs | 734 |
| Coefficient cells | 1,614 |
| Coefficient additions | 2,604 |
| Distinct final outputs | 55 |
| Represented input vectors | 8,192 |

Zero output has four preimages: masks 0,256,4,260 in the declared order. Columns 2 and 8 are zero columns, explaining these four vectors. Rows 7 and 9 are zero rows, so the all-one twelve-row output 4095 is impossible.

Selecting every column gives the largest reachable output, mask 3455, with printed row-bit string 111111101011. Its complete weight coefficients for weights 0 through 13 are:

    [0,0,0,0,2,21,88,201,281,252,146,53,11,1].

Thus 1,056 inputs produce that output. Exactly two have the minimum support size four:

- Mask 616, selected columns {3,5,6,9}, first in block-choice order.
- Mask 120, selected columns {3,4,5,6}, last in that two-member fiber.

The ordering is why the first numeric mask is larger than the second. Rank 528 in the unrestricted 1,056-member fiber selects mask 5708. These finite coverage minima do not certify a simultaneous-prime value.

All 35 saved reader outputs are retained. They include the complete 55 output profiles, every block table, two direct products, constrained and unconstrained fiber counts and inverse ranks, both minimum-support vectors, every zero-output vector, and a thirteen-round sequential transcript.

The first stream input is mask 616. After receiving response i, with i starting at one, the consumer constructs the next input as (output*37+i*97)&8191 and only then submits it. The complete transcript is:

| Round | Input | Output |
| ---: | ---: | ---: |
| 1 | 616 | 3455 |
| 2 | 5052 | 3199 |
| 3 | 3869 | 3135 |
| 4 | 1598 | 3199 |
| 5 | 4063 | 3391 |
| 6 | 3072 | 51 |
| 7 | 2469 | 127 |
| 8 | 5378 | 127 |
| 9 | 5475 | 383 |
| 10 | 6852 | 2383 |
| 11 | 7221 | 2175 |
| 12 | 7814 | 2175 |
| 13 | 7911 | 2431 |

The transcript demonstrates the defined response-before-next-input use. It is not a measured asymptotic performance experiment.

The fresh reader indexed 135 states, 1,614 coefficients and 734 arcs. The two direct products plus thirteen stream responses performed 60 block lookups and 60 accumulating ORs. Inverse queries created 547 new memo cells with 1,748 cache hits, 2,110 conditional additions and 2,311 saved-arc lookups. Every one of those 547 cells is retained. Matrix entries read, block tables rebuilt, base layer coefficients rebuilt and exhaustive input-vector enumerations were zero in the reader.

## Files and provenance

- boolean_product_fibers.cjs: source blob 1d8b845cbbc4d26dbe312429b9a2986d88547972, 10,823 UTF-8 bytes.
- Complete original input: blob daaf79b42feb269c5c3ba76d62aba139ae749dfd, 897 bytes; embedded in the certificate.
- local_flag_matrix_certificate.json: blob 2ee2809423c1ace1aa0ba101b8a2f2dc73500cd1, 11,633 bytes.
- saved_reader_queries.json: blob a945b1d905b8e9ac8beb18aab2111385da02376c, 35,021 bytes.
- This guide and README explain the exact operation and its scope.

The source was syntax-parsed and banked with the input before the single production construction. Complete construction and reader records were each banked before publication. No prior mathematical calculation or published example was replayed, and no additional verification-only census was run. Publication uses guarded serial Contents writes plus complete immutable/main text and blob readbacks, with no file-mode or whole-tree assertion.

The result is exact finite product, output-fiber, minimum-support and sequential navigation for the stated matrix, together with a bounded reusable implementation. Its preprocessing and conditional query work are charged and reported. No new OMv algorithmic frontier, hardness theorem, conjecture resolution or mathematical priority is claimed.
