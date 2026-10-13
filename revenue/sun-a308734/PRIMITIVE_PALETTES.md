# A308734: minimum fixed palettes on the primitive core

**Results.** On the primitive domain $n>1$, $4\nmid n$, three fixed legal restricted totals suffice for coverage at every individual prime power. Two never suffice. If the chosen total must also satisfy $T\le n$ for **every** target in that domain, the exact minimum is four.

The respective palettes are

$$
S_3=\{2,8,10\},\qquad S_4=\{2,5,8,10\}.
$$

Operation: **A308734-PRIMITIVE-PALETTE-20261004-7CA6**. This continues [#14694](https://github.com/woahwhattheheck/commons/issues/14694), the [bounded local-pair theorem](LOCAL_PRIME_POWERS.md) and the [dyadic growth result](DYADIC_GROWTH.md). The original atlas, earlier scaling and finite-offset barrier in [#14719](https://github.com/woahwhattheheck/commons/pull/14719), and their source credit remain intact. No novelty or full-conjecture claim is made.

## 1. Meaning of a fixed local palette

A legal total has the form

$$
T=4^a9^b+4^c25^d,\qquad a,b,c,d\ge0.
$$

For a fixed finite set $S$ of such totals, individual-prime coverage means

$$
\forall n>1,\ 4\nmid n\quad
\forall p\ \text{prime}\quad
\exists T\in S\quad
\forall k\ge1\quad
\exists x_k,y_k\in\mathbb Z_{\ge0}:
\quad n\equiv T+x_k^2+y_k^2\pmod{p^k}.
\tag{1}
$$

One total is fixed across all depths of the chosen prime. It may differ between primes. The bounded version adds $T\le n$ inside the existential choice. The square coordinates remain modular; their squares need not fit below $n-T$.

These are local questions derived from the [primary A308734 target](https://oeis.org/A308734). The earlier dyadic growth result already excludes every fixed finite legal palette on the unrestricted target domain. Restricting to $4$-free targets removes that particular obstruction.

## 2. Three totals cover the primitive domain

The totals in $S_3$ are legal:

$$
2=4^0 9^0+4^0 25^0,\qquad
8=4^1 9^0+4^1 25^0,\qquad
10=4^0 9^1+4^0 25^0.
$$

For an odd prime $p$, at least one of $n-2$ and $n-10$ is a unit modulo $p$, since their difference is $8$. The [proved odd-unit lifting lemma](LOCAL_PRIME_POWERS.md#1-odd-prime-powers) gives a sum of two squares for that same remainder modulo every $p^k$.

For the prime $2$, use the following complete partition of the $4$-free classes.

| Target class | Fixed total $T$ | Remainder class |
| --- | ---: | --- |
| $n\equiv1\pmod4$ | $8$ | $n-T\equiv1\pmod4$ |
| $n\equiv3\pmod4$ | $2$ | $n-T\equiv1\pmod4$ |
| $n\equiv2\pmod8$ | $8$ | $n-T\equiv2\pmod8$ |
| $n\equiv6\pmod{16}$ | $2$ | $n-T\equiv4\pmod{16}$ |
| $n\equiv14\pmod{16}$ | $10$ | $n-T\equiv4\pmod{16}$ |

Every displayed remainder has odd part $1$ modulo $4$. Such an integer is a sum of two squares at every dyadic depth: for an odd part $z\equiv1\pmod4$, choose $y=0$ or $2$ so that $z-y^2\equiv1\pmod8$, then use the [accepted square-root lifting lemma](../../research/sun_a303656/PRIME_POWER_LOCAL_COVER.md). Multiplication by $2$ preserves a two-square representation through

$$
2(x^2+y^2)=(x+y)^2+(x-y)^2.
$$

This proves (1) for $S_3$. The congruence construction also permits a negative remainder; boundedness is addressed separately.

### Exactly one small bounded exception

For $n\ge10$, all three totals fit below $n$. The primitive targets below $10$ are $2,3,5,6,7,9$. Apart from $5$, they have exact representations using $S_3$:

| $n$ | Total $T$ | Two unrestricted squares |
| ---: | ---: | --- |
| $2$ | $2$ | $0^2+0^2$ |
| $3$ | $2$ | $1^2+0^2$ |
| $6$ | $2$ | $2^2+0^2$ |
| $7$ | $2$ | $1^2+2^2$ |
| $9$ | $8$ | $1^2+0^2$ |

At $n=5$, only the total $2$ in $S_3$ fits, and its remainder $3$ fails modulo $4$. Thus $S_3$ gives bounded coverage for every primitive $n>1$ except exactly $5$, in particular for every primitive $n\ge6$.

Adding the legal total $5=4^0 9^0+4^1 25^0$ supplies the zero remainder at $n=5$. Therefore $S_4$ gives bounded coverage for every primitive target $n>1$.

## 3. Two legal totals always miss primitive targets

A legal odd total is always $1$ modulo $4$: exactly one restricted square is odd, and every odd restricted square is $1$ modulo $4$. A legal even total is either $0$ or $2$ modulo $4$.

We show that every pair of legal totals has a common missing dyadic progression whose targets are $4$-free. Repeated totals are allowed, so the argument also covers one-element palettes.

We use the [proved forbidden dyadic form](../../research/sun_a303656/DYADIC_PALETTE_BOUND.md#1-a-forbidden-dyadic-form): a remainder congruent to $3\cdot2^v$ modulo $2^{v+2}$ cannot be a sum of two squares. Its obstruction persists after multiplication by a power of two.

### Both totals are odd

Write them as $O_1,O_2\equiv1\pmod4$ and put $\Delta=(O_2-O_1)/4$. The [general dyadic missing-class lemma](../../research/sun_a303656/DYADIC_PALETTE_BOUND.md#2-any-three-translates-have-a-common-missing-class), applied to the at-most-two shifts $\{0,\Delta\}$, supplies a progression of integers $m$ on which both $m$ and $m-\Delta$ have a common finite dyadic obstruction.

Set $n=O_1+4m$. Then

$$
n-O_1=4m,\qquad n-O_2=4(m-\Delta).
$$

Both remainders remain forbidden after increasing the detecting modulus by a factor of $4$. Every target is $1$ modulo $4$.

### Exactly one total is odd

Let $O\equiv1\pmod4$ be odd and $E$ even.

| Even total | Choose the target class | Forbidden remainders |
| --- | --- | --- |
| $E\equiv0\pmod4$ | $n\equiv O+6\pmod8$ | $n-O\equiv6\pmod8$; $n-E\equiv3\pmod4$ |
| $E\equiv2\pmod4$ | $n\equiv O+12\pmod{16}$ | $n-O\equiv12\pmod{16}$; $n-E\equiv3\pmod4$ |

The targets are respectively $3$ and $1$ modulo $4$.

### Both totals are even

If the totals have the same class modulo $4$, choose $n$ three larger than that class. Both remainders are $3$ modulo $4$, and $n$ is odd.

Otherwise name the totals $E\equiv2\pmod4$ and $F\equiv0\pmod4$. Their difference is $2$ or $6$ modulo $8$.

| Difference | Choose the target class | Forbidden remainders |
| --- | --- | --- |
| $F-E\equiv2\pmod8$ | $n\equiv E+24\pmod{32}$ | $n-E\equiv24\pmod{32}$; $n-F\equiv6\pmod8$ |
| $F-E\equiv6\pmod8$ | $n\equiv E+12\pmod{16}$ | $n-E\equiv12\pmod{16}$; $n-F\equiv6\pmod8$ |

Here every target is $2$ modulo $4$.

All cases give an infinite primitive progression. Taking its positive tail makes $n$ exceed both totals, so even eventual bounded coverage is impossible for a two-element legal palette. Together with Section 2, **three is the exact minimum for (1), and for bounded coverage of all sufficiently large primitive targets**.

## 4. Bounded coverage of every primitive target needs four

Suppose a palette of at most three legal totals covers every primitive $n>1$ with $T\le n$.

The target $n=2$ forces the palette to contain $2$, the smallest legal total. The target $n=5$ forces it to contain $5$, since the only smaller legal total is $2$ and $5-2=3$ fails modulo $4$.

At $n=17$, the complete list of legal totals at most $17$ is

$$
\{2,5,8,10,13,17\}.
$$

To see completeness directly, the first restricted square can only be $1,4,9,16$, and the second can only be $1,4,16$. Their sums at most $17$ give exactly this list.

The totals $2,5,10$ leave remainders $15,12,7$ at $n=17$, all dyadically forbidden. Thus the third total must be $8$, $13$ or $17$. Each possible palette now has a specific primitive obstruction:

| Only possible palette | Primitive target | Remainders | Common detecting modulus |
| --- | ---: | --- | ---: |
| $\{2,5,8\}$ | $29$ | $27,24,21$ | $81$ |
| $\{2,5,17\}$ | $29$ | $27,24,12$ | $81$ |
| $\{2,5,13\}$ | $61$ | $59,56,48$ | $64$ |

For the first two rows, each remainder has odd $3$-adic valuation. If $3$ divides a sum of two squares, reduction modulo $3$ forces both coordinates to be divisible by $3$; division by $9$ repeats. Thus valuation one fails modulo $9$, and valuation three fails modulo $81$.

In the last row, the odd parts are $59,7,3$, respectively. They are all $3$ modulo $4$, and their detecting dyadic moduli divide $64$.

Consequently no three-element legal palette gives bounded coverage for every primitive target. The $S_4$ construction in Section 2 proves that **four is the exact minimum**. This lower bound is a finite exhaustion forced by three small targets, not an interval search.

## 5. The cross-prime gap remains

The three-element palette still fails as a global equality family on infinitely many primitive targets. The existing [#14719 CRT barrier](../../research/sun_a308734_residue_covering/RESEARCH_MEMO.md) supplies the general reason. A concrete instance for $S_3$ imposes

$$
n\equiv5\pmod9,\qquad
n\equiv15\pmod{49},\qquad
n\equiv21\pmod{121}.
$$

These give valuation-one obstructions for $n-2$ at $3$, $n-8$ at $7$, and $n-10$ at $11$. One solution class is $42008$ modulo $53361$. Its primitive subprogression is

$$
n=95369+213444t,\qquad t\ge0.
$$

Every target is $1$ modulo $4$ and greater than all three totals. Each total fails at one of the three odd primes, although Section 2 guarantees that some total works at every individual prime. The same construction fails simultaneously modulo $9\cdot49\cdot121=53361$.

This example consumes the earlier general barrier; it does not claim a new CRT principle. The minimum palette results identify exactly how little choice suffices for the primitive individual-prime problem. A common restricted total across primes and the global integer equality remain unresolved by this note. No executable, finite certificate, prior execution result or sponsor action is changed.
