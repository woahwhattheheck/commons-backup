# Lean handoff — UNEXECUTED

This is a theorem plan, not a kernel receipt.  Do not represent it as sponsor-accepted or elaborated.

Existing immutable contribution `9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b` already defines/proves local objects including `primeSquareObstructionResidues`, `primeSquareGoodResidues`, `primeSquareObstructionResidues_card_le_four`, and the Hensel correspondence.  Sponsor contributions must be self-contained; if sibling scripts cannot be imported directly, copy/reprove only the minimum local interface with attribution or target a supported extension mechanism.

Suggested new namespace: `Contribution.Erdos978PartIIIFiniteCRT`.

New mathematical interface to formalize:

1. For a finite set/list `P` of pairwise-distinct primes, define
   `finiteSieveModulus P = ∏ p ∈ P, p^2`.
2. Define global good residues modulo that product as residues whose projection mod `p²` lies in `primeSquareGoodResidues p` for every `p ∈ P`.
3. Use pairwise coprimality of `p²` and `q²` for distinct primes plus finite CRT to establish a bijection between the global good residues and the dependent product of the local good residue sets.
4. Deduce the exact cardinality identity
   `card globalGood = ∏ p ∈ P, card (primeSquareGoodResidues p)`.
5. Combine with the existing local lower bound to get
   `∏ p ∈ P, (p² - 4) ≤ card globalGood`
   for odd primes; handle `p=2` separately using the existing `4 ∤ n⁴+2` lemma.
6. Deduce nonemptiness of `globalGood`, hence existence of an integer avoiding every `p²` obstruction from the fixed finite family.  A periodicity corollary can state that adding any multiple of the global modulus preserves membership.

Evidence ceiling: this finite CRT result leaves the infinite prime tail untouched.  It is not the Hooley-style squarefree-value theorem needed to close Erdős 978(iii).
