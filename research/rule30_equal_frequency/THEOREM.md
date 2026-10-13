# Conditional center-trace bijection for Rule 30

## Definitions

Use bits in `{0,1}` and coordinates

`X_i(t+1) = F(X_{i-1}(t), X_i(t), X_{i+1}(t))`, with
`F(l,c,r) = l XOR (c OR r)`.

Fix a horizon `T >= 1` and the initial nonnegative prefix
`R=(X_0(0),...,X_T(0))`. Only initial sites in `[-T,T]` can influence
the center through time `T`. For the negative prefix
`L=(X_-1(0),...,X_-T(0))`, define
`Phi_{T,R}(L)=(X_0(1),...,X_0(T))`.

## Theorem

For every `T` and every fixed `R`, `Phi_{T,R}` is a bijection of
`{0,1}^T`.

More strongly, for each `1 <= t <= T`, with all sites
`X_{-(t-1)}(0),...,X_T(0)` fixed, flipping the newly exposed extreme
bit `X_-t(0)` leaves `X_0(1),...,X_0(t-1)` unchanged and flips
`X_0(t)`.

### Proof

Rule 30 is **left-permutive**: for each fixed pair `(c,r)`,
`F(1,c,r)=1-F(0,c,r)`.

Causality gives the first triangular fact immediately. A site
`X_-t(0)` is distance `t` from `(0,t)`, and the radius-one rule moves
influence at speed at most one cell per time step. Therefore it cannot
influence the center at any earlier time `s<t`.

For time `t`, any causal path from `(-t,0)` to `(0,t)` must gain exactly
one spatial unit at every one of the `t` steps. There is therefore only
one such extremal path:

`(-t,0) -> (-t+1,1) -> ... -> (-1,t-1) -> (0,t)`.

At every update on that path, the predecessor on the path is the
**left** argument of `F`. The original extreme bit cannot at the same
time reach either the center or right argument of that path cell:
doing so would require more than the maximum rightward speed in the
remaining time. Thus toggling `X_-t(0)` toggles the path value at the
first step; left permutivity toggles it again at each subsequent step
while the other two arguments are unaffected by that extreme bit.
Hence the final center value `X_0(t)` toggles exactly once.

So, after `X_-1(0),...,X_{-(t-1)}(0)` have been chosen, exactly one of
the two possible values of `X_-t(0)` realizes any prescribed target
value for `X_0(t)`, and that choice cannot alter the already prescribed
earlier center values. Induction on `t=1,...,T` gives a unique negative
prefix for every target future center trace. This is precisely
bijectivity. QED.

## Exact consequences

1. **Conditional finite-horizon uniformity.** If the `T` negative
   prefix bits are uniform, while `R` is held fixed arbitrarily, then
   the `T` future center bits are jointly uniform: every length-`T`
   future trace occurs exactly once among the `2^T` left prefixes.
   This is stronger in conditioning than merely sampling all initial
   cells at random, but it is a standard type of consequence of
   left-permutivity; no novelty claim is made here.
2. **No local forbidden trace word at fixed right half.** For every
   finite target center word there is a unique compatible left prefix.
   Therefore a proof that some finite center word is impossible cannot
   follow from the Rule-30 local transition law plus a fixed
   nonnegative initial half alone. A proof about the sponsor's lone
   seed must use its extra global condition—most notably the all-zero
   negative completion / finite support—or another genuinely global
   invariant.
3. **Exact reduction of the lone seed.** For `R=(1,0,...,0)`, the
   actual lone-seed future trace is exactly the image of
   `L=(0,...,0)` under this triangular Boolean permutation. The prize's
   frequency problem is therefore about the Hamming-weight asymptotics
   of one distinguished image, not about the uniform ensemble.

## What this does *not* prove

Stephen Wolfram's 2019 prize announcement already notes that equal
probability over all initial conditions gives equal block frequencies
for Rule 30, while explicitly warning that this does not settle the
single-cell initial condition. The theorem above makes a sharper
finite, one-sided conditional version executable and proof-transparent;
it does **not** transfer ensemble uniformity to the distinguished
all-zero left completion.

In particular, it does not prove that the lone-seed center-column
frequency tends to one half, nor the equivalent sponsor ratio
statement. `prize_theorem` remains false.
