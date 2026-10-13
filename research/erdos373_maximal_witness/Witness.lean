import FormalConjectures.ErdosProblems.«373»

namespace Contribution.Erdos373Witness

/-- Concrete first conjunct of the sponsor's maximal-solution target. -/
theorem witness_16_14_5_2 : (16, [14, 5, 2]) ∈ Erdos373.S := by
  norm_num [Erdos373.S, Nat.factorial]

end Contribution.Erdos373Witness
