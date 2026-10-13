# A303656: four fixed offsets are necessary for local coverage

**Result.** Every set of at most three fixed integer offsets misses a residue class modulo a power of two. Consequently, the four legal offsets $2,4,6,8$ in the [prime-power coverage theorem](PRIME_POWER_LOCAL_COVER.md) have the smallest possible cardinality among fixed palettes that cover every integer target at every individual prime power.

This is a local statement about fixed offsets. The exponents may still depend on the target in the original [A303656 conjecture](https://oeis.org/A303656). No claim about a global proof or about novelty is made.

Operation: **A303656-MINIMUM-PALETTE-20261004-7CA6**. Original research scope: [#14608](https://github.com/woahwhattheheck/commons/issues/14608), ZOL-C4N9. The accepted [#14639](https://github.com/woahwhattheheck/commons/pull/14639) source and finite evidence remain unchanged.

## 1. A forbidden dyadic form

For every integer $v\ge0$, a number congruent to

$$
3\cdot2^v\pmod{2^{v+2}}
\tag{1}
$$

is not a sum of two squares modulo $2^{v+2}$.

For $v=0$, the residue is $3$ modulo $4$. For $v=1$, it is $6$ modulo $8$. Both are excluded by the possible square residues.

If $v\ge2$ and $x^2+y^2$ satisfied (1), reduction modulo $4$ would force both $x$ and $y$ to be even. Dividing the congruence by $4$ gives the same assertion with $v-2$ and modulus $2^v$. Repetition reaches one of the two excluded base cases.

Equivalently, a nonzero integer whose odd part is $3$ modulo $4$ has a finite dyadic obstruction. Multiplication by any power of two preserves that obstruction after increasing the modulus accordingly.

## 2. Any three translates have a common missing class

**Theorem.** Let $S$ be a nonempty set of at most three integers. There are integers $r$ and $K\ge2$ such that, for every $n\equiv r\pmod{2^K}$ and every $s\in S$, the congruence

$$
n-s\equiv x^2+y^2\pmod{2^K}
\tag{2}
$$

has no integer solution.

### Normalize the offsets

If $S$ has one distinct element $s$, take $n\equiv s+3\pmod4$.

Otherwise select $s_0\in S$ and let

$$
e=\min_{s\in S,\ s\ne s_0}v_2(s-s_0),\qquad
t_s=\frac{s-s_0}{2^e}.
$$

The normalized offsets are integers and do not all have the same parity. If necessary, repeat an offset to obtain a list of three entries. Name the two entries of the same parity $A,B$, and the other entry $C$.

We will choose a normalized target $m$ for which every $m-A,m-B,m-C$ has the forbidden form (1). There are two cases.

### Case I: $A\equiv B\pmod4$

Because $C$ has the opposite parity, exactly one of these rows applies:

| Condition | Choose the target class | Forbidden differences |
| --- | --- | --- |
| $C-A\equiv1\pmod4$ | $m\equiv C+6\pmod8$ | $m-C\equiv6\pmod8$; $m-A,m-B\equiv3\pmod4$ |
| $C-A\equiv3\pmod4$ | $m\equiv C+12\pmod{16}$ | $m-C\equiv12\pmod{16}$; $m-A,m-B\equiv3\pmod4$ |

Thus all three offsets are excluded.

### Case II: $A\not\equiv B\pmod4$

Relabel $A,B$ so that $A\equiv C+3\pmod4$. Their equal parity and different classes modulo $4$ imply $B-A\equiv2$ or $6\pmod8$.

| Condition | Choose the target class | Forbidden differences |
| --- | --- | --- |
| $B-A\equiv2\pmod8$ | $m\equiv A+24\pmod{32}$ | $m-A\equiv24\pmod{32}$; $m-B\equiv6\pmod8$; $m-C\equiv3\pmod4$ |
| $B-A\equiv6\pmod8$ | $m\equiv A+12\pmod{16}$ | $m-A\equiv12\pmod{16}$; $m-B\equiv6\pmod8$; $m-C\equiv3\pmod4$ |

Again every difference has a finite obstruction from Section 1.

### Restore the original scale

In every case, a class $m\equiv r_0\pmod{32}$ can be chosen inside the displayed class. Set

$$
n\equiv s_0+2^e r_0\pmod{2^{e+5}}.
$$

For every original offset $s$,

$$
n-s=2^e(m-t_s).
$$

The forbidden odd part is preserved. Its detecting modulus is at most $2^{e+5}$, so (2) is impossible with $K=e+5$. This proves the theorem.

The progression contains infinitely many positive integers greater than $\max S$. The result is therefore not caused by choosing an offset larger than the target.

## 3. Why the normalized modulus bound can reach 32

For $S=\{0,1,2\}$, the residues of two squares modulo $16$ are

$$
R_{16}=\{0,1,2,4,5,8,9,10,13\}.
$$

They satisfy

$$
R_{16}\cup(R_{16}+1)\cup(R_{16}+2)=\mathbb Z/16\mathbb Z.
$$

Hence these three shifts have no missing class modulo $16$, or modulo a smaller power of two. But $m=24\pmod{32}$ is missing: its three differences are $24,23,22$, with respective odd parts $3,23,11$, all $3$ modulo $4$. Thus the modulus $32$ in the normalized construction cannot uniformly be replaced by $16$.

This is an explicit residue argument, not a parameter scan. No least-modulus assertion is made for every other triple.

## 4. Apply the lower bound to A303656

The earlier [local theorem and bounded corollary](PRIME_POWER_LOCAL_COVER.md) prove that the legal palette

$$
S_4=\{3^0+5^0,\ 3^1+5^0,\ 3^0+5^1,\ 3^1+5^1\}
   =\{2,4,6,8\}
$$

covers every individual prime power. For each $n>1$ and each prime, one offset is at most $n$ and works at all depths of that prime with its exponents fixed.

Section 2 rules out every fixed palette with at most three offsets, including palettes using arbitrarily large exponents. **Four is therefore the exact minimum for this local-cover problem.**

For the four three-element subsets of $S_4$, the missing progressions can be written particularly simply:

| Retained offsets | Missing positive targets, $t\ge0$ | Differences at the displayed first target |
| --- | --- | --- |
| $\{2,4,6\}$ | $n=50+64t$ | $48,\ 46,\ 44$ |
| $\{2,4,8\}$ | $n=32+32t$ | $30,\ 28,\ 24$ |
| $\{2,6,8\}$ | $n=30+32t$ | $28,\ 24,\ 22$ |
| $\{4,6,8\}$ | $n=52+64t$ | $48,\ 46,\ 44$ |

Each difference has odd part $3$ modulo $4$, and the displayed modulus preserves the detecting congruence.

## 5. Distinguish the local minimum from the global obstruction

The earlier [#14719 fixed-finite-family argument](../sun_a308734_residue_covering/RESEARCH_MEMO.md), Proposition 3, excludes global equality for infinitely many targets for **every** fixed finite offset set. It assigns different odd obstruction primes to different offsets and applies CRT.

The result here is different: **at most three offsets already fail at the single prime 2**. Four offsets can cover every individual prime power, while still failing simultaneously at a suitable composite modulus, as the existing A303656 note demonstrates.

Nothing here rules out target-dependent exponent choices, a finite description of an infinite offset family, or a strategy controlling shared exponents across primes. The full conjecture remains unsolved by these notes. This continuation changes no executable, finite evidence, computation result or sponsor action.
