# Erdős 143: finite rational-grid extensions

An exact BigInt index for individually admissible larger additions to a supplied finite rational prefix. The fixed denominator defines the candidate grid. Inclusive residue bands and generalized CRT retain every accepted residue and complete descriptions of the incompatible gcd classes.

| File | Role |
| --- | --- |
| [rational_grid_extension_index.cjs](rational_grid_extension_index.cjs) | Public compiler, saved-state loader, incremental append, numeric count/rank/select and paging |
| [RATIONAL_GRID_EXTENSION_API.md](RATIONAL_GRID_EXTENSION_API.md) | Original questions, full reduction/CRT proof, contracts, bounds, provenance and actual results |
| [rational_prefix_extensions.json](rational_prefix_extensions.json) | Three directly loadable complete snapshots and all actual query/work records |

The actual construction starts with numerators `[5,7,12]` at denominator `2`, then appends the current least candidates `17` and `32`. The completed prefix is `[5,7,12,17,32]/2`. Its index has 7,392 admissible residues modulo 57,120, ten pair witnesses and 8,482 cumulative CRT join rows. The final noncoprime step retains four gcd classes describing all 21,840 incompatible input-residue/band pairs.

A fresh saved-data reader counted candidates through the real bound `10^100`, selected and recovered rank `10^90`, and exported sixteen candidates with no prefix-pair, gcd or CRT recomputation. The next candidate `38/2` was not appended. All earlier accepted computations stayed unreplayed.

These are **individual additions to the finite prefix**. Both `87/2` and `88/2` occur in the saved page, but their distance is only `1/2`, so they cannot both be appended. The positive candidate frequency is not an infinite well-separated set.

The [actual formal statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/143.lean) asks whether every countably infinite real set in `(1,infinity)` satisfying `|kx-y| >= 1` for distinct elements and all positive integer multipliers has lower counting density zero, and whether its reciprocal-log sum converges. This finite grid API does not settle those general conclusions. The guide records the observed statement blob and preserves the original problem attribution.

Koukoulopoulos–Lamzouri–Lichtman's [2025 primary paper](https://arxiv.org/abs/2502.09539) already proves the logarithmic-density alternative, which implies zero lower natural density; the formal file's open tags are not a current status summary. The stronger reciprocal-log convergence question is separate. For an entire set on a single fixed rational grid, that convergence already follows from Erdős's classical primitive-integer theorem, as explained and attributed in the guide.

Saved-index loading establishes bounded structural consistency only; it does not authenticate provenance or reprove the accepted mathematical derivation. Resource stops preserve the last complete prefix and are distinct from explicit separation obstructions.
