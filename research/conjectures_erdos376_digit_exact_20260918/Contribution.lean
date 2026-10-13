import Mathlib.Data.Nat.Choose.Central
import Mathlib.Data.Nat.Multiplicity
import Mathlib.Data.Set.Finite.Lattice

open Finset

namespace Contribution.Erdos376DigitExact

/-- Same digit predicate used by the published Erdős-376 contribution. -/
def DigitGood357 (n : ℕ) : Prop :=
  (∀ j : ℕ, 2 * (n / 3 ^ j % 3) < 3) ∧
  (∀ j : ℕ, 2 * (n / 5 ^ j % 5) < 5) ∧
  (∀ j : ℕ, 2 * (n / 7 ^ j % 7) < 7)

/-- The local reverse direction missing from the published prefix lemma:
carry-free doubling of the `(j+1)`-digit prefix forces the `j`th digit to be
small enough not to carry. -/
theorem prefix_no_carry_implies_digit_bound {p n j : ℕ} (hp : 0 < p)
    (hprefix : n % p ^ (j + 1) + n % p ^ (j + 1) < p ^ (j + 1)) :
    2 * (n / p ^ j % p) < p := by
  rw [show j + 1 = j.succ by omega, Nat.mod_pow_succ, pow_succ] at hprefix
  let r := n % p ^ j
  let d := n / p ^ j % p
  have hpj : 0 < p ^ j := pow_pos hp _
  have hmul : p ^ j * (d + d) < p ^ j * p := by
    calc
      p ^ j * (d + d) ≤ (r + r) + p ^ j * (d + d) := Nat.le_add_left _ _
      _ = (r + p ^ j * d) + (r + p ^ j * d) := by ring
      _ < p ^ j * p := by simpa only [r, d] using hprefix
  have hd : d + d < p := (Nat.mul_lt_mul_left hpj).mp hmul
  simpa only [d, two_mul] using hd

/-- Kummer carry count specialized to the central binomial coefficient. -/
theorem centralBinom_emultiplicity_eq_carries {p n b : ℕ} (hp : p.Prime)
    (hbound : Nat.log p (2 * n) < b) :
    emultiplicity p n.centralBinom =
      #{i ∈ Ico 1 b | p ^ i ≤ n % p ^ i + n % p ^ i} := by
  simpa [Nat.centralBinom, Nat.two_mul, Nat.add_sub_cancel_left] using
    (Nat.Prime.emultiplicity_choose hp (Nat.le_mul_of_pos_left n Nat.zero_lt_two) hbound)

theorem centralBinom_not_dvd_iff_no_carry {p n b : ℕ} (hp : p.Prime)
    (hbound : Nat.log p (2 * n) < b) :
    ¬ p ∣ n.centralBinom ↔
      ∀ i ∈ Ico 1 b, ¬ p ^ i ≤ n % p ^ i + n % p ^ i := by
  rw [← emultiplicity_eq_zero, centralBinom_emultiplicity_eq_carries hp hbound]
  simp

/-- Nondivisibility of the central binomial coefficient by `p` forces every
base-`p` digit of `n` to be small enough that doubling it produces no carry. -/
theorem centralBinom_not_dvd_implies_digit_bound {p n : ℕ} (hp : p.Prime)
    (hnot : ¬ p ∣ n.centralBinom) :
    ∀ j : ℕ, 2 * (n / p ^ j % p) < p := by
  intro j
  let b := max (Nat.log p (2 * n) + 1) (j + 2)
  have hbound : Nat.log p (2 * n) < b := by
    exact lt_of_lt_of_le (Nat.lt_succ_self _) (Nat.le_max_left _ _)
  have hnocar := (centralBinom_not_dvd_iff_no_carry hp hbound).mp hnot
  have hjmem : j + 1 ∈ Ico 1 b := by
    constructor
    · omega
    · exact lt_of_lt_of_le (by omega : j + 1 < j + 2) (Nat.le_max_right _ _)
  have hprefix : n % p ^ (j + 1) + n % p ^ (j + 1) < p ^ (j + 1) :=
    lt_of_not_ge (hnocar (j + 1) hjmem)
  exact prefix_no_carry_implies_digit_bound hp.pos hprefix

/-- The reverse implication missing from the existing published contribution. -/
theorem coprime_105_implies_digitGood357 (n : ℕ)
    (h : n.centralBinom.Coprime 105) : DigitGood357 n := by
  have hsplit : ¬ 3 ∣ n.centralBinom ∧ ¬ 5 ∣ n.centralBinom ∧ ¬ 7 ∣ n.centralBinom := by
    rw [show 105 = 3 * 5 * 7 by norm_num, Nat.coprime_mul_iff_right,
      Nat.coprime_mul_iff_right] at h
    rcases h with ⟨⟨h3, h5⟩, h7⟩
    exact ⟨Nat.prime_three.coprime_iff_not_dvd.mp h3.symm,
      Nat.prime_five.coprime_iff_not_dvd.mp h5.symm,
      Nat.prime_seven.coprime_iff_not_dvd.mp h7.symm⟩
  exact ⟨centralBinom_not_dvd_implies_digit_bound Nat.prime_three hsplit.1,
    centralBinom_not_dvd_implies_digit_bound Nat.prime_five hsplit.2.1,
    centralBinom_not_dvd_implies_digit_bound Nat.prime_seven hsplit.2.2⟩

end Contribution.Erdos376DigitExact
