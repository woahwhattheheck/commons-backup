# Exact finite graph-isomorphism transcripts

This package indexes one round of the classical graph-isomorphism proof and its rejection simulator for a declared six-vertex example. It retains all 720 labelled permutations, 60 commitment graphs, 240 verifier challenge cells and a bijection between 2,880 real choices and 2,880 accepted simulator trials. The complete simulator trial space has 5,760 elements.

A separate public simulator file contains neither the isomorphism witness nor the real-view correspondence. A fresh reader can navigate its accepted/rejected trials and fixed-coin rejection runs from those public tables. This is an exact finite distribution and navigation artifact, not an implementation intended for cryptographic deployment or a new zero-knowledge theorem.

## Sources and scope

The official Simons Institute Summer 2015 problem list asks whether SZK equals PZK:
https://simons.berkeley.edu/open-problems-cryptography-summer-2015 .
That is a dated source statement. This package does not transform arbitrary statistical zero-knowledge proofs, compare the two complexity classes, or assert a current resolution.

The graph-isomorphism protocol is classical Goldreich–Micali–Wigderson. Goldreich's directly readable author page, https://www.wisdom.weizmann.ac.il/~oded/gmw.html , identifies the final paper in Journal of the ACM 38(3), July 1991. Its linked final paper is https://www.wisdom.weizmann.ac.il/~oded/X/gmw1j.pdf . The protocol passage available in the bounded source lookup was an indexed primary excerpt of Protocol 2, printed page 702: a uniformly relabelled input graph is the commitment, the challenge is a bit, and the response is an isomorphism from the challenged graph to that commitment. The excerpt uses G1 as the real commitment source; this package declares the equivalent normalization using G0.

Goldreich's 1987 *Randomness, Interactive Proofs and Zero-Knowledge* indexed primary excerpt describes guessing an input graph, relabelling it uniformly, retaining the trial when the verifier asks for that graph, and otherwise independently retrying. It states expected two trials and equality of the successful conversation distribution. The exact source locator https://web.cs.miami.edu/home/burt/learning/Csc598.0/goldreich87randomness.pdf was inaccessible when opened and remains held; the quoted scope is indexed text, not a full-paper read.

The final GMW PDF returned no parsed text. Its screenshot response contained only an ImageDisplayed text marker, not an image payload. No full-paper, visual diagram or proof review is claimed. A tutorial PostScript route was unsupported and a linked Cambridge discussion timed out; neither was retried. The finite conventions and argument below are explicitly stated, rather than inferred from an unavailable image.

## Declared input

The common graph G0 is the labelled cycle on vertices 0,...,5 with unordered edges
~~~
{0,1}, {0,5}, {1,2}, {2,3}, {3,4}, {4,5}.
~~~
It is a simple graph: no loops or repeated edges. The witness permutation is
~~~
sigma = [2,5,1,4,0,3].
~~~
A permutation array p means that old vertex i receives label p[i]. The common graph G1 is sigma(G0). Permutations are ordered lexicographically as arrays. Composition p o q means i maps to p[q[i]].

All unordered pairs i<j are ordered lexicographically. Bit i of a graph mask records the edge at position i in that pair list. For the actual input there are 15 pair positions. This representation describes labelled graphs; isomorphic commitment graphs with different labels remain different masks.

The verifier first chooses one of four coin values c=0,1,2,3 uniformly. For a commitment H its challenge is
\[
v(c,H)=\operatorname{parity}(H\mathbin{\&}((1<<0)|(1<<4)|(1<<8)))
 \mathbin{\mathrm{xor}}\operatorname{parity}(c\mathbin{\&}3).
\]
Thus the challenge depends on both the commitment and the verifier coins. It is always a bit. This model has no aborting challenge, auxiliary input, evolving verifier state or multiple protocol rounds. Fixing one coin value gives a deterministic commitment-dependent verifier.

The declared input is new and is not an imported prior graph calculation. Its complete text has Git blob 3d296f1683844d144f60eec70999d34435dcb00c (644 bytes). The six-cycle and the protocol are established examples; their use here makes no priority claim.

## Real and simulated choices

Let m=n!, C be the number of verifier coin values and N=Cm. The actual values are m=720, C=4 and N=2,880.

The real one-round view uses independent uniform c and rho:
\[
H=\rho(G_0),\qquad b=v(c,H),\qquad
\tau=\begin{cases}\rho&b=0,\\ \rho\circ\sigma^{-1}&b=1.\end{cases}
\]
The response satisfies H=tau(G_b). Its full verifier view is (c,H,b,tau). The package also keeps the real random-choice rank rho for certificate navigation; that extra coordinate is not a message sent to the verifier.

A simulator attempt uses a uniform guessed bit b and a uniform permutation tau, with the verifier coins c fixed:
\[
H=\tau(G_b).
\]
It is accepted exactly when v(c,H)=b. On acceptance it outputs (c,H,b,tau). The public simulator's graph images for both G0 and G1 are computed directly from those public graphs during compilation. Its reader does not consult sigma, inverse-witness compositions or the real-to-trial table.

The certificate identifies an accepted simulator attempt with the real choice
\[
\rho=\begin{cases}\tau&b=0,\\ \tau\circ\sigma&b=1.\end{cases}
\]
Conversely a real choice gives the accepted attempt from its response formula. These maps are inverse and preserve the full view. They supply a direct finite proof of equal distributions, since real choices and accepted attempts are uniform. The saved certificate retains both maps and checks the public commitment images along the correspondence. It does not rely on sampling or approximate histogram equality.

For each fixed c, exactly m of the 2m simulator choices are accepted. In particular the acceptance probability is 1/2 even when v(c,H) is biased toward one challenge bit. Every real view conditional on c has mass 1/m; after choosing c uniformly, it has mass 1/(Cm). The recorded total-variation distance is exactly 0.

The index's witness and coupling are certificate material. Merely deleting the witness field from a file would not prove a simulator witness-free; here the separate public reader uses only public image tables, challenge cells, permutations and accepted/rejected trial lists. Those fields suffice for its actual trial and run outputs.

## Labelled orbit and storage

The compiler enumerates permutations exactly once. Each permutation's image of G0 determines an orbit row. The complete fiber of that row is the list of permutations producing the same labelled commitment. The actual orbit has 60 graphs, each with 12 permutation preimages. The identity-labelled graph has 12 automorphisms.

No quotient of transcripts by automorphism is taken. The response permutation is part of the transcript, so the 12 elements of a commitment fiber remain distinct choices. Likewise the four verifier coin values are retained in the view. The 2,880 view records are represented by complete permutation/fiber and correspondence arrays; repeated graph edge lists are materialized only when requested.

The generic constructor accepts simple labelled graphs with 2<=n<=7, a supplied witness permutation, up to four coin bits and the declared edge/coin parity challenge form. It constructs G1 from that witness, so it does not solve graph isomorphism or handle an alleged nonisomorphic pair. The total simulator trial cap is 200,000. The work is factorial in n; this finite enumeration is not a polynomial-time implementation of the classical general simulator theorem.

## Trial and transcript order

A real choice has integer id
\[
\mathrm{realID}=c\,m+\operatorname{rank}(\rho).
\]
A simulator choice has id
\[
\mathrm{trialID}=(2c+b)m+\operatorname{rank}(\tau).
\]
Real and trial ids therefore have different meanings. Accepted trial ids are not their ranks in the accepted subfamily.

The conditional view interface orders results by coin value, then commitment-orbit row, then lexicographic real permutation. It supports any combination of fixed coin, fixed orbit and fixed challenge. This conditional order is intentionally different from the global real-id order. Counts and branch choices come from the saved orbit fibers and challenge rows.

The real reader can expose the accepted simulator id for a view and the corresponding real id for a simulator trial. A rejected trial has no corresponding real view. The public-only reader emits the public simulated transcript without those real-choice fields.

## Rejection runs with coins fixed

The verifier coin value is chosen once and kept unchanged when retrying. For that fixed coin, each fresh simulator attempt independently chooses a uniform bit and permutation from 2m possibilities.

A run with f rejected attempts followed by one accepted attempt has m^(f+1) possible ordered choice sequences. The run order is mixed radix with base m: the first f digits select from the saved rejected-trial list, and the last digit selects from the accepted list. Both lists are sorted by trial id. Rank/select can therefore reach a huge finite run family without enumerating earlier runs.

For a particular run sequence, its probability given the fixed verifier coin is (2m)^-(f+1). This is not its probability conditional on having f failures; under that conditioning its mass is m^-(f+1). The output field trial_sequence_mass_given_coin records the former. Summing the m^(f+1) sequences gives first success on attempt f+1 with probability 2^-(f+1). The probability of no success after j attempts is 2^-j, and the expected attempt count is two. These conclusions use independent uniform fresh attempts and the proved fixed-coin acceptance count; they are not observations from random sampling.

The run interface permits at most 128 failures and canonical nonnegative decimal ranks of at most 1,024 digits. The stopping-law interface permits attempt numbers 1,...,4096. It returns exact rational powers of two without generating any attempt sequence. No finite time cutoff is presented as an exact always-successful simulator.

## Saved-reader interfaces

~~~javascript
const { openIndex, openSimulator } = require('./gi_transcripts.cjs');
const full = require('./six_cycle_transcript_certificate.json');
const pub = require('./public_simulator.json');

const reader = openIndex(full.record);
reader.condition({coin:0, challenge:1});
reader.conditionalSelect({coin:0, challenge:1}, '100');
reader.runSelect(2, 100, '1' + '0'.repeat(200));

const simulator = openSimulator(pub);
simulator.trial(0);
~~~

| Full reader method | Meaning |
|---|---|
| summary() | Saved sizes, equality certificate and original construction work. |
| permutation(rank), permutationRank(p) | Lexicographic permutation navigation. |
| orbit(o), orbitForMask(mask), pageOrbits(offset,limit) | Commitment graph and saved permutation fiber navigation. |
| view(realID) | Full real transcript, real choice and corresponding accepted trial. |
| trial(trialID) | Simulator choice, outcome and any corresponding real id. |
| condition(filter) | Exact conditional count and all contributing coin/orbit cells. |
| conditionalSelect(filter,rank), conditionalRank(filter,realID) | Navigation in the stated conditional order. |
| pageTrials(coin,accepted,offset,limit) | A saved accepted/rejected trial page, at most 256 rows. |
| runSelect(coin,failures,rank), runRank(ids) | A fixed-coin rejection run and inverse rank. |
| stoppingLaw(attempt) | Exact geometric first-success/tail probabilities. |
| publicSnapshot() | Copy of public simulator fields only. |
| work(), snapshot() | Copies of counters or the full saved record. |

The public reader exposes summary(), trial(), runSelect(), runRank(), work() and snapshot(). It rejects additional fields outside the declared public schema. Its summary explicitly records witness_present:false and real_coupling_present:false. It does not offer real transcript ranks.

Both loaders perform bounded structural checks and build lookup maps from saved arrays. They do not authenticate foreign inputs, recheck the group action, reconstruct graph images, recompute challenges or recertify the bijection. Their mathematical provenance is the matching trusted construction. Returned arrays are copies. Invalid run outcome order or a change in verifier coins is rejected. A conditional rank is null for a view outside the condition. The size caps and larger unexercised branches were source-inspected only.

## Actual construction and queries

Frozen executed source: 1612bce0f1f3f4f9bb21d3f3bcd9290fd5e92bb0, 18,520 bytes.
Complete construction: 074012d6e28cc69ad919d2799a111f84a9c5526d, 293,303 bytes.
Public-only simulator: 22987780e8f4b6bf58d26c38bd78a603ad43cabc, 133,437 bytes.
Complete 31-query reader output: ac0e3fd1e2bad71100b8b3a0e5bfdd79102fca1a, 45,372 bytes.

| Verifier coin | Real challenge 0 | Real challenge 1 | Accepted attempts | Rejected attempts |
|---:|---:|---:|---:|---:|
| 0 | 288 | 432 | 720 | 720 |
| 1 | 432 | 288 | 720 | 720 |
| 2 | 432 | 288 | 720 | 720 |
| 3 | 288 | 432 | 720 | 720 |

Construction work was 720 permutations, 8,646 edge-image operations, 1,440 permutation compositions, 240 challenge cells, 2,880 correspondence rows and 5,760 trial classifications. The edge-image count includes the six operations constructing the declared public G1.

All 31 fresh query outputs are retained. They include every orbit size, both public-input commitment fibers, selected real views and corresponding simulator attempts, conditional counts/ranks, a page of rejected trials, three rejection-run selections and inverse ranks, and the exact stopping tail at 1,000 attempts. Coin 0/challenge 1 has 432 views; conditional rank 100 selects real id 277. Fixing the original commitment gives 48 views across all four coins. The rank 10^200 query among runs with 100 failures ends at real id 1545.

The public-only reader separately returns its schema summary, an accepted and rejected trial, and the last run with four failures for coin 3, together with the inverse rank. That run ends at trial 5759. It uses no coupling rows.

Full-reader work: 720 permutation rows indexed, 5,760 trial-rank rows indexed, 301 saved lookups, 248 condition-cell scans, nine transcript materializations and 211 run digits. Public-reader work: 5,760 trial-rank rows indexed, 17 saved lookups and ten run digits. Graph-image, challenge and coupling reconstruction counts are zero in both readers; the public reader also reads zero coupling rows.

These outputs concern only the declared finite common input and verifier. They do not establish a new soundness bound, audit the source paper, compare arbitrary-verifier complexity classes, or claim a new perfect zero-knowledge construction. No old computation, native executor, sponsor contact or submission occurred.

Publication uses guarded serial Contents operations with exact text, preimage, lineage and expected-head checks. That route makes no independent file-mode or whole-tree verification assertion.
