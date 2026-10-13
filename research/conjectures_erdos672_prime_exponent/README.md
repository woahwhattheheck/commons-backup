# Erdős 672 — prime-exponent reduction and bounded exact search

This carrier is a first-piece research artifact for the current Conjectures.io Erdős 672 task. It is deliberately narrower than a solution.

## Exact sponsor target

Pinned task: `fc-8432eac9-erdos672-erdos-672-713e8186eb-formalized-v1`  
Task commitment: `sha256:9319c919b34ffc4e079f87512387799fde189e458faa517513b0d7ae0d13bc04`  
Pinned source type: `True ↔ ∀ (k l : ℕ), l > 1 → k ≥ 4 → Erdos672.Erdos672With k l`  
Source type SHA-256: `sha256:c445617cb40577954b07647947103591146b81f79e29b214a02745fc58e09a1a`.

The sponsor task metadata classifies this as a `DIRECT_PROP`, production-eligible target. The current public Formal Conjectures `main` file is not the task source: it still shows the older `answer(sorry) ↔ ∃ᵉ ... ¬ Erdos672With` form. The task instead pins sponsor-derived repository commit `8432eac998110a563e03df65a28c117e97c8c142`, and its source metadata fixes the target to the universal positive formulation above. Do not silently substitute upstream `main` when checking this task.

## General reduction

For any natural `q` and exponent `l > 1`, choose a prime divisor `p | l` and write `l = p m`. Then

`q^l = q^(p m) = (q^m)^p`.

Therefore any counterexample whose arithmetic-progression product is a perfect `l`th power is automatically a counterexample with a **prime exponent**. Equivalently, to establish `Erdos672With k l` for every `l > 1`, it is enough to rule out prime exponents. This removes composite exponents from the substantive search/proof surface without losing any counterexample.

`prime_exponent_reduction.py` implements that certificate exactly over integers and independently characterizes positive perfect powers via the gcd of prime-factor exponents.

## Exact finite evidence

The committed deterministic receipt checks two bounded rails:

* every exponent `2 ≤ l ≤ 10,000` reduces to its least prime divisor, 9,999 exact triples, stream SHA-256 `a71037ca58b44b3f87b0d984acd4ca4cbd2a6c835118e1d6e16cd705942817fe`;
* every coprime positive arithmetic progression with `4 ≤ k ≤ 8`, `1 ≤ n,d ≤ 256` is scanned exactly, 199,475 candidates, **0 perfect-power hits**, stream SHA-256 `1cae8794c66733beb4716bcb155c9d645dd33744375b9cd71187142159c4f7db`.

Canonical receipt SHA-256: `8e1bc6fcbe3383a095fd0868516cc88a6d9e5c8745091b70639b63670241d18a`.

The finite scan is not evidence of global nonexistence beyond its explicit box. The prime-exponent reduction itself is the reusable general mathematical step.

## Validation

Executed on Python 3.13.5:

```text
python -m py_compile prime_exponent_reduction.py test_prime_exponent_reduction.py   PASS
python -m unittest -v test_prime_exponent_reduction.py                            7/7 PASS
python -O -m unittest -v test_prime_exponent_reduction.py                         7/7 PASS
```

This runtime exposes neither `lean` nor `lake`, so `LEAN_HANDOFF.md` is **not kernel-elaborated** here. No sponsor submission, solve, bounty, payment, or revenue is claimed.
