# Finite alternating-game certificates and policy navigation

This package consumes an explicit signed transition graph and compiles finite winning and losing certificates. It never computes a Collatz successor. Its actual input is the already retained graph on the 70 odd states from 1 through 139 from [Commons #31513](https://github.com/woahwhattheheck/commons/pull/31513). This is a new game interpretation and closure of that graph, with the original stochastic computation kept as an identified input premise.

For that input the complete closure contains terminal state 1, **33 winning positions, 14 losing positions and 22 unresolved positions**. The finite proof depths run through 13. The saved index represents **8,388,608 stationary policies**, including choices at every nonterminal retained state, and exposes exact count, rank, select, certificate and playout queries.

## Source and mathematical scope

Althöfer's [Prize 3](https://althofer.de/collatz-prizes.html) describes an alternating game on positive odd integers. A move chooses 3n+1 or 3n−1 and removes all powers of two. The player whose move produces 1 wins. The retained author page, updated September 21, 2026, reports Michael Hartisch's prior finite computer analysis below one million and a manuscript by Grisha Pochuev whose checking was still underway in the stated September update. Those are author-reported historical context; this package neither certifies that manuscript nor presents this much smaller graph as a new range record. The author's request not to send proof attempts is respected. No proof submission or sponsor contact occurred.

The source's game differs from the fair-sign stochastic process used to produce the earlier graph artifact. There are no probabilities in this index. Both signed moves remain choices, even if their targets coincide.

Entry into 1 ends play immediately: the preceding mover has won. The two self-loops supplied at 1 by the stochastic artifact remain in the retained source graph as provenance; they are **not playable game moves**. The game record for 1 has status T, depth 0 and an empty move list. A query whose initial state is already 1 reports already_terminal with no inferred preceding winner. This avoids adding an initial-position convention not established by the source.

The finite domain is explicit. A target outside it is unknown in the original infinite game. The implementation's censored model stops on such an exit and assigns neither player a win; infinite play is likewise nonwinning in that model. This convention supplies a precise finite analysis, not a statement about what happens after the same exit in the original game.

Finite W and L certificates do lift to the original game, conditional on the retained graph's being its actual complete move list at each supplied nonterminal state. A W certificate needs one genuine move to a certified L position or to 1. An L certificate covers every genuine move, all of which lead to W. Unknown exits therefore prevent an L certificate. Induction on the recorded proof depth proves finite termination under the certified winning player's choices, regardless of any unexamined behavior outside the domain.

The reported remoteness and the policy family's duration conventions are exact for the **finite censored game and its finite proof closure**. An outside continuation might give a faster winning strategy in the original game. Thus a finite depth is not asserted to be the globally minimum original-game duration. U denotes unresolved by this closure; it does not certify an original-game draw, loss or nontermination.

## Input custody

The actual input is copied literally from:

- Repository: woahwhattheheck/commons.
- Accepted carrier: #31513.
- Commit: df9f924e832ad3306791c5320d7b10ce19e0a2b6.
- Path: research/ppl116_stochastic_collatz/odd139_absorption.json.
- Git blob: 49292324248673869e9f47a06158e1dab0174647.
- Field: constructor.snapshot.nodes.

The input preserves 70 sorted node records and all 140 signed source edges, including their saved raw and halving fields. Only state, sign and target drive this new computation. The raw expressions and halving counts are provenance, not recalculated transition evidence.

The standalone input packet was banked before computation as Git blob 4b723008358b1ed2d0b2daf5dd5bc273c8995a7a, 20,266 bytes. The new source was parsed, inspected and banked before computation as Git blob 554a4b7037d02847b7e73f4a680b53424422f707, 14,051 bytes. The complete initial result was banked in the same connected V8 invocation as the new construction: blob 7f4d620df838fc39f4430a8a9f119ba07b05dc31, 95,150 bytes.

No original successor calculation, SCC computation, probability solve, linear elimination or residual calculation was rerun. The new finite closure is the production calculation for this artifact.

## Closure and remoteness derivation

Let T consist of terminal state 1 and initially set r(1)=0. Every other retained state starts unresolved. A nonterminal node has exactly two signed moves.

In a synchronous round, inspect only classifications completed in earlier rounds:

1. Mark v as W if at least one successor is already L or T. Set
   r(v)=1+min r(u), over its L or T successors.
2. Otherwise mark v as L if every legal successor is already W. Set
   r(v)=1+max r(u), over both successors.
3. Leave all other nodes unresolved. An outside successor remains unknown.

Apply all newly obtained labels together, then begin the next round. Stop when a round adds nothing. Each productive round labels at least one previously unresolved node, so there are at most N−1 productive rounds for an N-node graph containing the terminal.

This is the least finite inductive W/L solution. At depth 1, W positions move directly to the terminal. A W position first acquired at round h has a minimum-depth losing successor of depth h−1: any lower-depth witness would have made it available earlier. An L position first acquired at round h has all successors W, with largest depth h−1: otherwise all of them would already have been available at an earlier round. Therefore the synchronous round number equals the stored remoteness, and later classifications cannot supply a smaller-depth witness that should have been used earlier.

For the censored finite game, choose a fastest winning move at W and a longest delaying move at L. Each selected move decreases remoteness by exactly one; hence the selected playout lasts exactly r(v) steps. More generally, arbitrary moves by a losing opponent only shorten the bound, because every L successor has smaller depth. This is the finite inductive winning certificate used for the original-game implication.

When the closure stops, an unresolved node has no successor in L or T; otherwise it would be W. It also has at least one unknown successor, either another U node or an exit; otherwise all successors would be W and it would be L. Thus its safe options are precisely its U or exit targets. A safe policy can stay unresolved or leave the finite domain. This establishes the stated censored-model behavior only.

The algorithm does not infer game draws from the old stochastic SCCs, from an arbitrary directed cycle, or from the presence of an unknown exit.

## Retained policy family

A policy is one signed choice at each of the 69 nonterminal retained states. States are ordered increasingly, and −1 precedes +1. It includes choices at states not reached from a particular queried start.

The allowed choices are:

- At W: all moves to L or T with target depth exactly r(v)−1.
- At L: all moves to W with target depth exactly r(v)−1.
- At U: all moves to U or outside the retained domain.
- At T: no policy coordinate.

This is the family of fastest-win, longest-delay and unresolved-safe stationary choices for the specified censored game. It is not the family of every strategy that might eventually win, every strategy in the original infinite game, or equivalence classes under reachability or relabelling.

The restriction to minimum-depth W choices matters. Merely allowing any W-to-L edge can permit a selected policy to revisit positions rather than monotonically reduce the certificate depth. The retained family makes the duration claim directly checkable.

For coordinate i let its option count be b_i, either 1 or 2. Save suffix products s_i=product_{j>=i} b_j, with s_m=1. A digit vector d_i has zero-based lexicographic rank sum_i d_i s_{i+1}. Selection divides by these saved suffix products; no policy enumeration is needed. Duplicate target states do not merge the two signed options.

There are 23 binary coordinates in the actual input, so the family contains 2^23=8,388,608 policies. Restricting the state-7 sign to +1 and the state-17 sign to −1 leaves 2,097,152 policies. Requiring sign −1 at state 27 leaves zero policies in this family; this is a conditional policy-family statement, not a universal prohibition on that legal game move.

## Actual full classification

The complete snapshot retains every node, move, classification, proof edge, policy option, layer and suffix count. Its productive layers are:

| Depth | Newly certified states |
| --- | --- |
| 0 | 1 (terminal) |
| 1 | 3, 5, 11, 21, 43, 85 |
| 2 | 7, 29, 57 |
| 3 | 9, 19, 37, 39, 75, 77 |
| 4 | 13, 25, 51 |
| 5 | 17, 33, 35, 67, 69, 133, 139 |
| 6 | 23, 45, 89, 93 |
| 7 | 15, 31, 59, 61, 119, 123 |
| 8 | 41, 79 |
| 9 | 27, 53, 55, 105, 109 |
| 10 | 73 |
| 11 | 49, 97 |
| 12 | 65 |
| 13 | 87 |

Odd positive layers are W, and positive even layers are L for this terminal-move game. The 22 remaining U states are:
47, 63, 71, 81, 83, 91, 95, 99, 101, 103, 107, 111, 113, 115, 117, 121, 125, 127, 129, 131, 135, 137.

There are 138 playable signed edges after the terminal override and 23 distinct outside targets. The closure visited unresolved nodes 569 times and their edges 1,138 times. Thirteen productive synchronous rounds were followed by a no-change stopping pass. The observed construction time was 1 ms in this invocation; this is an observation, not a benchmark guarantee.

## Public API

The module is plain CommonJS JavaScript with no imports, I/O, native dependency or environment access. It runs directly in connected V8.

| Export or method | Contract |
| --- | --- |
| compileFiniteGame(input) | Consume an explicit sorted signed graph and produce a complete snapshot. |
| openFiniteGame(snapshotOrJSON) | Reopen a saved snapshot without retrograde classification. |
| summary() | Return the saved counts, exit targets, unresolved list and policy count. |
| record(state) | Return a copied full classification, move and certificate record. |
| recordsPage(start=0, limit=32) | Page records by zero-based sorted position; limit at most 64. |
| layer(depth) | Return a saved depth layer, or an empty layer if that permitted depth is absent. |
| policyCount(restrictions=[]) | Return a decimal exact count under distinct state/sign restrictions. |
| selectPolicy(rank) | Select the full labelled policy at a zero-based rank. |
| rankPolicy(policyOrMoves) | Rank a complete policy containing one admissible sign per sorted nonterminal state. |
| play(start, rank) | Follow a selected saved policy, retaining the complete finite trace. |
| statistics() | Return reader work counters; this accessor is not itself counted as a query. |

The reader returns copies of data. Query results cannot mutate its retained records.

Example for the existing artifact:

~~~js
const { openFiniteGame } = require("./finite_game_index.cjs");
const record = JSON.parse(savedArtifactText);
const api = openFiniteGame(record.constructor.snapshot);
const classification = api.record(27);         // W, depth 9
const policy = api.selectPolicy("4194304");
const back = api.rankPolicy(policy);          // "4194304"
const play = api.play(27, "0");                // player 0 reaches 1 in 9 moves
const count = api.policyCount([
  { state: 7, sign: 1 },
  { state: 17, sign: -1 }
]);                                          // "2097152"
~~~

Use compileFiniteGame only for a new explicit graph input. The saved reader is the intended way to query this published instance.

### Generic input bounds and semantics

The constructor accepts 1 through 1,024 nodes. States and targets are positive odd safe integers at most 10^12, supplied as Numbers. Nodes must be strictly increasing and include state 1. Each source node must carry exactly two edges, ordered by sign −1 then +1, with a positive odd target. Targets may lie outside the supplied node set. Extra JSON provenance fields, including raw and halvings, are copied but are not arithmetic certificates checked by this API.

The generic contract is an explicit labelled two-choice game graph with a terminal at 1. It does not establish that arbitrary supplied edges follow the accelerated 3n±1 rule. That meaning must come from an identified input premise, as it does here. Missing move options are refused rather than treated as a vacuous loss.

The saved reader accepts an object or JSON text, with a serialized limit of 8,000,000 characters. Snapshot records must match the supplied graph identities and the supported schema/version. Policy ranks accept canonical nonnegative decimal strings, BigInts, or nonnegative safe-integer Numbers; strings are capped at 400 digits. A rank must be less than the saved policy count. With at most 1,023 binary coordinates the count fits this digit envelope.

A record query requires a state in the retained domain. A restriction must refer to a nonterminal policy coordinate, use sign −1 or +1, and not repeat a state. An otherwise valid but unavailable sign produces count zero. Complete policy ranking rejects missing, out-of-order or inadmissible choices. Record pages use a start from 0 through the record count and a limit from 1 through 64. A page at the end is empty.

An initial query at 1 checks the policy rank but does not decode a policy or take a move. Other playouts alternate player identifiers 0 and 1. A move to 1 returns reached_one and the mover's identifier. An outside target returns censored_exit with no winner. A repeated (state, player) pair returns censored_repetition, cycle position and full trace, explicitly without an original-game draw conclusion. At most twice the retained state count of state/turn pairs can occur before termination, exit or repetition. The repetition branch and larger generic caps were source-inspected; the actual query set below exited or reached 1 and did not exercise a cycle case.

### Loader checks and their limits

Opening checks JSON and schema bounds, sorted graph identities, status and remoteness shape, terminal override, saved move identities, policy-coordinate binding and the saved mixed-radix product identities. It indexes the 70 records and their policy positions. It does not rerun retrograde closure, recompute the source graph, reconstruct SCCs, or solve a stochastic system.

Those checks are structural and arithmetic consistency checks on the saved navigation data. They do not authenticate an arbitrary edited snapshot's mathematical W/L labels, depth claims, layer completeness or provenance. The published constructor and banked data identify the actual calculation supporting this artifact. No independent proof-checking claim is made for openFiniteGame.

## Fresh saved-reader consumption

A separate module instance opened the saved snapshot once and completed 27 queries:

- The summary, six individual records, the deepest layer, and two pages exporting all 70 records.
- The unrestricted policy count and the two conditional counts above.
- Complete policy selection and ranking at 0, 4,194,304 and 8,388,607.
- Eight playouts including the initial-terminal case, finite wins/losses and unknown exits.

Every query output, including the full selected policies and all move traces, is saved in odd139_game_certificates.json. Reader counters are 897 policy-digit steps and 49 playout steps. It reports zero classification, source-transition, source-SCC or stochastic-system recomputations. Opening took 1 ms in this observation. Policy count validation and the new rank/playout arithmetic are fresh reader work, not claimed to be zero work.

Selected complete traces are:

- Start 27, policy 0:
  27 → 41 → 61 → 23 → 17 → 25 → 37 → 7 → 5 → 1.
  Player 0 wins after nine moves.
- Start 27, policy 8,388,607:
  27 → 41 → 31 → 23 → 35 → 13 → 19 → 29 → 11 → 1.
  Player 0 again wins after nine moves.
- Start 87, policy 0:
  87 → 65 → 97 → 73 → 109 → 41 → 61 → 23 → 17 → 25 → 37 → 7 → 5 → 1.
  Player 0 wins after thirteen moves.
- Start 73, policy 4,194,304:
  73 → 109 → 41 → 61 → 23 → 17 → 25 → 37 → 7 → 11 → 1.
  Player 1 wins after ten moves.
- Start 47, both the first and last policies:
  47 → 71 → 107 → 161.
  The final target is outside the retained domain; no original-game outcome is assigned.
- Start 137, policy 8,388,607:
  137 → 103 → 155.
  This is another unknown exit.

The recorded legal signs and moving players are in the machine-readable traces; these abbreviated state lists do not replace them.

## Files and retained boundaries

- finite_game_index.cjs: new compiler and separate saved reader.
- odd139_game_certificates.json: exact input graph, complete constructor snapshot and all 27 reader outputs.
- FINITE_GAME_API.md: conventions, derivation, bounds, usage and source scope.
- README.md: entry point and concise outcome.

The source was frozen before the single actual closure. The fresh reader used that same source without reconstruction of accepted predecessor work. There was no synthetic test suite, new larger-range game search, accepted computation replay, external submission or claim of novelty. This package delivers an explicit finite certificate and a usable navigation interface; it does not prove the author's general game assertion.
