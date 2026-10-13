# Lean handoff — Erdős 1142 p=29/p=37 primitive-root tail

Status: **UNEXECUTED in this runtime.** The mathematical premises below are exact, but no Lean
kernel receipt is claimed here.

Pinned sponsor target:

* task `fc-8432eac9-erdos1142-erdos-1142-a29719d6af-formalized-v1`
* commitment `sha256:60a1381809a9c064c907712012dcc037343ee3d39486f392c00e34a42dda7b4d`
* source type `sha256:140c4194bf440ed9095b2b1a1f8cb6b534b1f4738ee1c9d78a89ec890ed38632`

The already-published contribution
`contributions/erdos-1142/8b08710200d75e84c26054cc34ad7f155d26ca3c649f5e06290878af8770409b/script.lean`
contains the general theorem `Contribution.Erdos1142Sieve.dvd_of_covering` plus
`dvd_40755`. A new sponsor contribution may need to be self-contained rather than importing
that sibling script, so do not assume those declarations are importable. Reproduce the small
general argument locally if the contribution rules require it.

## Exact new statements

Using the same covering theorem shape as the published piece:

```lean
theorem twenty_nine_dvd {n : ℕ}
    (hn : Erdos1142.Erdos1142Prop n)
    (h : 268435485 < n) : 29 ∣ n := by
  -- `2` has order 28 mod 29; the finite covering premise is decidable.
  exact dvd_of_covering (p := 29) (K := 28) (by norm_num) (by decide) hn (by norm_num; omega)

theorem thirty_seven_dvd {n : ℕ}
    (hn : Erdos1142.Erdos1142Prop n)
    (h : 68719476773 < n) : 37 ∣ n := by
  -- `2` has order 36 mod 37.
  exact dvd_of_covering (p := 37) (K := 36) (by norm_num) (by decide) hn (by norm_num; omega)
```

Then combine coprime divisors:

```lean
theorem dvd_1181895 {n : ℕ}
    (hn : Erdos1142.Erdos1142Prop n)
    (h : 268435485 < n) : 1181895 ∣ n := by
  have h40755 : 40755 ∣ n := dvd_40755 hn (by omega)
  have h29 : 29 ∣ n := twenty_nine_dvd hn h
  simpa using Nat.Coprime.mul_dvd_of_dvd_of_dvd
    (show Nat.Coprime 40755 29 by norm_num) h40755 h29

theorem dvd_43730115 {n : ℕ}
    (hn : Erdos1142.Erdos1142Prop n)
    (h : 68719476773 < n) : 43730115 ∣ n := by
  have h1181895 : 1181895 ∣ n := dvd_1181895 hn (by omega)
  have h37 : 37 ∣ n := thirty_seven_dvd hn h
  simpa using Nat.Coprime.mul_dvd_of_dvd_of_dvd
    (show Nat.Coprime 1181895 37 by norm_num) h1181895 h37
```

## Exhaustion statement for the direct primitive-root method

For the Mientka–Weitzenkamp upper bound `n ≤ 2^44`, any direct instance with
`K=p-1` and threshold `2^(p-1)+p` must have `p<47`. The exact finite classification of
primes below 47 for which `2` has order `p-1` is

`{3,5,11,13,19,29,37}`.

A Lean contribution can expose this as a finite `by decide` lemma if useful; the Python receipt
independently records the order and coverage witnesses for every prime through 45.

## Residual-search bridge

The useful downstream theorem is not a new infinitude claim. It is a sharper finite reduction
for the existing `mientka_weitzenkamp` variant: split `(4109,2^44]` at `262163`,
`268435485`, and `68719476773`, and use divisors `2145`, `40755`, `1181895`,
`43730115` respectively. The exact surviving arithmetic candidate count is `465335`.

A Lean-enabled executor should:

1. create a self-contained contribution in the sponsor repository;
2. kernel-elaborate these lemmas against the pinned source/toolchain;
3. run the sponsor's current contribution checks;
4. submit only if all checks are green.

Do not claim the main Erdős 1142 conjecture or the full finite classification from this handoff.
