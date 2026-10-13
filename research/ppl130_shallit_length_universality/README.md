# PPL130 / Shallit: universal lengths of finite automata

This package retains an exact eventual-period index for the lengths at which a supplied epsilon-free NFA accepts every word. It includes bounded public count/rank/select and rejected-word operations that consume saved data without reconstructing automaton families.

| File | Purpose |
|---|---|
| [universal_length_index.cjs](universal_length_index.cjs) | Pure CommonJS/connected-V8 compiler and retained index |
| [UNIVERSAL_LENGTH_API.md](UNIVERSAL_LENGTH_API.md) | Quantifier semantics, family-period proof, public contract, hard bounds and source scope |
| [prime_cycles_2_3_5_7.json](prime_cycles_2_3_5_7.json) | Complete 18-state prime-cycle input, 211 layers, 844 predecessor rows and all consumer outputs |

The actual input is the prime-cycle DFA from Gawrychowski, Lange, Rampersad, Shallit and Szykuła, [*Existential Length Universality*, STACS 2020](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.STACS.2020.16), specialized to primes 2,3,5,7. Its known least universal length 210 is credited. The saved full-family sequence has preperiod 1 and period 210; the universal positive lengths are exactly the multiples of 210.

The retained-data consumer answers through $10^{100}$, selects and recovers rank $10^{90}$, pages twelve universal lengths, and reconstructs a complete rejected word of length 211 across the closing edge. It performs no subset-transition or family recomputation.

The paper already classifies existential length universality as NEXPTIME-complete for NFAs and NP-complete for DFAs; the NFA supplied-binary-length question is PSPACE-complete. The old open framing is outdated. No strict complexity-class separation, new minimum, external frontier or classification of navigation complexity is asserted.

The public input alphabet is nonempty, epsilon transitions are rejected, and empty reachable subsets remain rejecting family members. A cap-stopped computation is explicitly incomplete. Loading is structural only and assumes the provenance and mathematical completeness of the saved compiler record. The guide makes every boundary explicit.
