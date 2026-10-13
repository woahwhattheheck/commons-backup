# Bounded pure-S rewrite histories

This package retains every stopped rewrite history from every closed binary pure-S term with exactly eight S leaves, subject to a six-step horizon and a twelve-leaf retained-state limit. It supplies exact outcome/length counts, prefix conditions and lexicographic history navigation from saved coefficients.

The [official Wolfram S Combinator Challenge](https://www.combinatorprize.org/) asks for a full proof or disproof of computation universality. These finite histories do not answer that question. No source example, published termination classification, universality proof or earlier evaluator was replayed.

## Exact finite model

A term is S or an ordered binary application (left right). There are no variables, K atoms or other primitives in the input grammar. The only rule is

    (((S x) y) z) -> ((x z) (y z)).

Here x,y,z stand for subterms in a matching occurrence. The rule and arbitrary-occurrence interpretation are supported by the inspected passages of [Stephen Wolfram, Combinators: A Centennial View](https://writings.stephenwolfram.com/2020/12/combinators-a-centennial-view/), December 6, 2020. SOURCE_QUALIFICATION.md distinguishes the directly read official challenge from the source scout's definition passages. Finite limits and history conventions below are this API's choices.

An address is a word over 0,1: the empty word is the root, 0 goes to the left/function child and 1 to the right/argument child. A move contracts exactly one matching occurrence. The occurrence addresses are listed in preorder, which is their lexicographic order with a word preceding its extensions.

A history is its sequence of move addresses. Different choices remain distinct even if their resulting term IDs agree. The input root index is also part of the identity; this is not an isomorphism or normal-form quotient.

The stopping rules have the following precedence:

1. A retained term with no redex is a normal stop, including at remaining horizon zero.
2. A retained term with at least one redex and no remaining steps is a horizon stop.
3. Otherwise each redex is an available edge. If its actual successor has more than twelve leaves, that edge produces a leaf_limit stop immediately.
4. Every other successor is retained with one fewer step.

A leaf-limit successor is saved as syntax but is not searched for further redexes. Consequently leaf_limit is not a claim that the successor lacks a normal form, has a redex, or diverges. Horizon is equally unresolved beyond the stated budget. A normal stop is a genuine redex-free term.

The source accepts a bounded general input shape, but the only constructor invocation reported here uses rootLeaves=8, horizon=6, leafCap=12.

## Construction and counting argument

The source generates terms of size n by every split n=a+(n-a), combining every previously generated left and right term. Every ordered full binary term has a unique root split and two unique subterms, so this recurrence gives the complete root family without duplicates.

Syntax is stored by immutable hash-consed application nodes. Equal subterms share an ID, but the semantics remain trees: redex traversal visits each occurrence address, and contracting an address reconstructs only the ancestors on that path. Shared children are never mutated. Thus two references to one subtree ID remain separate rewrite occurrences.

For each term actually examined, all redex addresses are cached. Its contractions are built once and retained. A counted state is (term ID, remaining steps), not just the syntax node. Remaining steps strictly decrease along every retained transition, making the coefficient recurrence finite even if an unbounded rewrite relation could revisit a term.

For outcome o and exact additional step count k, write F(term,h,o,k) for the saved coefficient. A normal state contributes one at (normal,0); a horizon state contributes one at (horizon,0). Each leaf-limit edge contributes one at (leaf_limit,1). Each retained edge contributes its child's coefficient shifted by one step. Summing over addresses counts distinct histories, including multiple addresses with the same child state.

Induction on remaining steps proves that these coefficients count exactly the stopped histories under the declared rules. This is a finite counting argument; it does not rely on confluence, universal normalization, a cycle criterion or the universality conjecture.

## Complete saved construction

There are 429 roots, 985 immutable syntax nodes, 1,321 states with step budgets, and 1,167 state edges. The certificate retains 670 redex lists and 490 term-contraction lists. Some syntax nodes are subterms or recorded boundary successors rather than independent counted states.

Counts below are histories across all roots, not counts of distinct roots or distinct terminal terms:

| Exact steps | Normal | Horizon | Leaf limit |
|---:|---:|---:|---:|
| 0 | 127 | 0 | 0 |
| 1 | 75 | 0 | 0 |
| 2 | 48 | 0 | 18 |
| 3 | 38 | 0 | 37 |
| 4 | 35 | 0 | 50 |
| 5 | 33 | 0 | 54 |
| 6 | 22 | 52 | 50 |

The actual constructor recorded 3,037 application-node requests, 985 created syntax nodes, 11,212 redex-occurrence visits, 564 detected redex occurrences and 563 built contractions. One redex occurrence belongs to a term only examined at remaining horizon zero, so it was not contracted. There were 723 ancestor reconstructions, 1,321 new counted states, 113 memo hits and 13,725 coefficient additions. No complete history family was enumerated.

The last statement refers to constructing counts, not to the later bounded sample of selected histories. All constructor records are retained; no work counter is presented as a timing benchmark.

## Saved reader and rank semantics

The reader imports the certificate and performs no contraction, redex search or coefficient recurrence. A prefix is an array of valid addresses starting at the chosen root. Each address must be an available saved edge, and a prefix cannot continue past a stop.

condition returns coefficients indexed by total steps from the original root, with zeros before the prefix length. A prefix ending at a leaf-limit edge has one completion of zero additional steps in that outcome. Prefixes do not authorize further exploration outside either budget.

For fixed root, outcome, total length and optional prefix, the eligible histories are ordered lexicographically by their address sequences. Ranks are zero-based exact integers. Selection walks addresses in saved order and skips entire branches using their saved coefficient. Ranking adds the corresponding earlier-branch counts. At each step this partitions the filtered family into consecutive blocks, proving the inverse relationship. A numeric order on term IDs or root IDs is not substituted for this address order.

Integer ranks may be BigInts, nonnegative decimal strings or safe integer Numbers. Roots, step counts and term IDs are bounded integer Numbers. There is no ranking across different root indices, and no unbounded-length history claim.

| Method | Result |
|---|---|
| summary() | Saved construction summary and work |
| rootProfiles() | Every root ID and all saved outcome/length coefficients |
| rootProfile(i) | One root profile |
| condition(i,prefix=[]) | Current retained/boundary term, stop and shifted coefficients |
| count(i,outcome,steps,prefix=[]) | Exact selected history count |
| select(i,outcome,steps,rank,prefix=[]) | Complete address path and term-ID path |
| rank(i,outcome,steps,path,prefix=[]) | Conditional zero-based rank |
| term(id) | Fully parenthesized display from saved syntax |
| work() | Actual reader work |
| caches() | Every retained prefix context |

Invalid IDs, lengths, outcomes, malformed address arrays, impossible ranks or paths continuing beyond stops are rejected according to the source. Successful normal, horizon and leaf-limit queries were exercised; the rejection branches are not claimed as exhaustively tested.

createReader checks the schema tag and trusts the supplied saved data. It does not authenticate an arbitrary certificate or independently prove its mathematical claims. Consumers should bind the complete published identities rather than treat this lightweight loader as a verifier.

## Actual reader use

reader_plan.json and reader_consumer.cjs specify the once-only consumer. It read all 429 saved root profiles and scanned 9,009 saved outcome/length cells. For each outcome and length with a positive coefficient, it chose the least-index root attaining that group's maximum coefficient. This yields thirteen selected groups.

Within each group, it selected distinct ranks from 0, floor(count/2), and count-1, then ranked the returned paths. It also conditioned nonempty histories on a deterministic first-half prefix and selected them back from their conditional ranks. Term rendering used the retained immutable syntax.

All 202 request/response pairs are retained. The 32 ordinary inverse checks and 31 prefix-conditioned inverse checks all agree. Thirty-six prefix contexts are cached. The largest selected group count is 8; this is a condition-specific history count, not a global extremal or termination assertion.

Fresh reader work was 429 root-profile reads, 1,122 coefficient reads, 36 condition builds, 139 condition-cache hits, 60 prefix-edge reads, 245 selection-edge reads, 245 rank-edge reads and 485 term-node reads. New contractions, new redex searches and new coefficients are all zero. The driver's 9,009 saved-cell comparisons are separately recorded and are not hidden inside zero-construction claims.

Each request was stored before invocation. Each full response and current caches/work were stored immediately afterward. No query failed, no unbanked response was reconstructed, and the constructor was not rerun. The inverse checks exercise the navigator; they are not an independent proof audit or a test of the infinite rewrite system.

## Complete serialization and recovery

The complete construction JSON is 1,233,569 ASCII UTF-8 bytes, with Git blob identity b55ace4cb5d22be3cbfcb436835500677dce57ba. It was acknowledged as one native public Git blob before reader work.

For publication, that exact string is split into five raw .jsonpart files, in chunks of at most 300,000 bytes. certificate_manifest.json gives the order, lengths, identities and full identity. Concatenate without separators, then parse JSON. The joined text was compared exactly with the banked original and independently hashed; this was byte serialization, not reconstruction of the mathematics.

assemble_certificate.cjs offers a pure assembly function taking the manifest and full part strings in order. It checks ASCII/lengths and parses JSON. It does not calculate SHA identities or audit the mathematics. The saved reader consumed the already banked full object; this assembly wrapper is provided for loading the published parts.

Example use, for a consumer supplying the complete part texts:

    const { assembleCertificate } = require("./assemble_certificate.cjs");
    const { createReader } = require("./pure_s_histories.cjs");
    const certificate = assembleCertificate(manifest, partTexts);
    const reader = createReader(certificate);
    const counts = reader.condition(0, []);

Only the requests in saved_reader.json are claimed as executed in this production.

The complete reader file is 414,032 bytes, blob e1f5d5794c119c6a05da0f4af06f5f3ab32dcba3. public_checkpoints.json lists actual acknowledged source/input/plan, construction, reader-plan and reader manifests. A later publication-spec checkpoint is reported separately to avoid self-reference. No private provider data or journal keys are published.

All conclusions remain restricted to the declared eight-leaf roots and stopping budgets. They are a reusable finite research tool, with no universality, nonuniversality, novelty, source-record, prize-eligibility or sponsor-submission claim.
