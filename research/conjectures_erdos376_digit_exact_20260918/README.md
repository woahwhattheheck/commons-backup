# Erdős #376 — exact digit-characterization extension

Lane: `CONJECTURES-ERDOS376-EXTEND-11LEMMAS-ZSOL376A-20260918`.

## Scope

The published Conjectures.io Erdős #376 contribution proves that simultaneous
base-3/base-5/base-7 digit smallness (`2*d < p`) is **sufficient** for
`Nat.Coprime n.centralBinom 105`.  This carrier develops the complementary
reverse direction: Kummer no-carry nondivisibility forces those same local digit
bounds.  If the Lean candidate elaborates in the sponsor-pinned environment,
that upgrades the published predicate from a sufficient construction device to
an exact characterization.

This does **not** prove infinitude and is not a bounty-closure claim.

## Independent arithmetic evidence

`verify_digit_exact.py` is stdlib-only and checks two separate formulations:

* for each `p ∈ {3,5,7}` and every `0 ≤ n ≤ 200000`, digitwise `2*d < p`
  is equivalent to all relevant doubled-prefix inequalities
  `2*(n mod p^i) < p^i` (600,003 generic cases);
* for every `0 ≤ n ≤ 4096`, the simultaneous digit predicate agrees with the
  independent exact integer calculation `gcd(binomial(2*n,n),105)=1` (4,097
  arithmetic cases).

It also enumerates the predicate through `10^6`: 13 values,
`0,1,10,756,757,3160,3186,3187,3250,7560,7561,7651,20007`, whose canonical
newline-list SHA-256 is
`bcf682f1acff4a7ef6804d09f470075824a5149ae61804b8476bc0597166f6c3`.

Run:

```bash
python3 verify_digit_exact.py
python3 -m unittest -v tests.test_verify_digit_exact
python3 -O -m unittest -v tests.test_verify_digit_exact
```

## Lean status / evidence ceiling

`Contribution.lean` is a **candidate**, not an executed proof receipt.  The
current cloud runtime has Python 3.13.5 but no `lean` or `lake`, and its shell
cannot resolve GitHub for dependency bootstrap.  The file therefore must be
elaborated against the sponsor-pinned Conjectures.io source before submission.
No sponsor PR, accepted contribution, solved conjecture, prize, payment, or
revenue is claimed here.

Pinned sponsor/task identities and file hashes are in `receipt.json`.

## Connected digit navigation and restartable interval search

[The exact navigation API](DIGIT_NAVIGATION_API.md) computes the least
integer satisfying a digit rule and searches intersections by skipping
excluded intervals. Bounded advances return JSON restart options for the
first unprocessed integer.

[The completed new input](interval_1000001_1000000000000.json) covers
`1,000,001 <= n <= 10^12` in 832 ceiling calls across a real restart,
retaining all four values and their base-3/base-5/base-7 representations.
Coverage is complete; the saved jump trace has an explicit 64-record
per-segment limit.

The guide credits the already-published OEIS table through `10^70` and
the later working report. This adds a connected capability and retained
input, with no new external-frontier or infinitude claim. Earlier
arithmetic, witness enumeration and Lean artifacts are unchanged.
