# A 40-point cycle switch attaining the fixed-host optimum

## Result

Let
$$
S=\{0,1,9,14,24,35,41,53,57,60\},\qquad H=S\times S.
$$

The retained [Commons #31227](https://github.com/woahwhattheheck/commons/pull/31227) incidence ledger for this particular 100-point host has exactly 21 lines containing at least four points: ten vertical lines, ten horizontal lines and the diagonal $x=y$. Each contains ten host points. Every other host line contains at most three.

The new subset $Q\subset H$ described below has 40 points, no five collinear points, and exactly 21 four-point lines. Consequently,
$$
\max\{t_4(R):R\subset H,\ |R|=40,\ R\text{ satisfies }P_4\}=21.
$$

This is an exact optimum within the fixed host $H$. As a real-plane configuration, $Q$ also establishes
$$
f_4(40)\ge21.
$$

It does not assert the global equality $f_4(40)=21$. The complete new point and line records appear in [cycle_switch_template_optimum.json](cycle_switch_template_optimum.json).

## The four-cycle switch

Write $s_0<\cdots<s_9$ for the elements of $S$. The original accepted subset is
$$
Q_0=\{(s_i,s_{(i+j)\bmod10}):0\le i<10,\ j\in\{1,2,3,4\}\}.
$$

It has four points for each fixed first coordinate, four for each fixed second coordinate, and no points on $x=y$. Define
$$
Q=(Q_0\setminus R)\cup A,
$$
where the following four index pairs are removed and four diagonal pairs are added.

| Removed index pair | Removed point | Added index pair | Added point |
|---|---|---|---|
| $(0,1)$ | $(0,1)$ | $(0,0)$ | $(0,0)$ |
| $(1,3)$ | $(1,14)$ | $(1,1)$ | $(1,1)$ |
| $(3,6)$ | $(14,41)$ | $(3,3)$ | $(14,14)$ |
| $(6,0)$ | $(41,0)$ | $(6,6)$ | $(41,41)$ |

The removed steps around the index cycle $0\to1\to3\to6\to0$ are $1,2,3,4$ modulo 10. Thus all four removed points belong to $Q_0$. None of the four added diagonal points belongs to $Q_0$. All four removed and all four added points are distinct, so the cardinality remains 40.

The removed pairs use first-coordinate indices $0,1,3,6$ once each, and second-coordinate indices $1,3,6,0$ once each. The added pairs use the same four indices once on each side. Every fixed-coordinate count therefore remains four. Exactly four points now lie on the main diagonal.

This switch was supplied in the coordinated Commons follow-up to the released incidence construction. It changes the selected points without changing the host geometry or the public API.

## Why the construction has exactly 21 four-point lines

The ten vertical lines and ten horizontal lines each contain four points of $Q$, and $x=y$ contains the four new diagonal points. These 21 lines are distinct.

Every line containing two points of $Q$ is already determined by two points of $H$. The accepted complete host ledger states that any host line outside the 21 named lines has at most three host points. Such a line can therefore have at most three points of $Q$.

It follows that all 21 named lines have exactly four selected points and no line has more than four. Hence $Q$ satisfies $P_4$ and
$$
t_4(Q)=T_4(Q)=21.
$$

This deduction consumes the complete retained host incidence result. It does not repeat its pair enumeration, and it does not rely on checking only row and column counts.

## The fixed-host upper bound

For a finite host point set $H$ and $k\ge2$, every geometric line containing exactly $k$ points of a subset $R\subset H$ also contains at least $k$ points of $H$. Distinct geometric lines of $R$ remain distinct geometric lines of $H$. This inclusion gives
$$
t_k(R)\le T_k(H).
$$

In particular, it applies to every admissible $R$ satisfying $P_k$. The cap ensures that its exact-$k$ lines are also all of its at-least-$k$ lines.

Here the retained value is $T_4(H)=21$. Every 40-point $P_4$ subset of $H$ thus has at most 21 four-point lines. The constructed $Q$ attains that bound, which proves the displayed fixed-host maximum.

The argument supplies no upper bound for configurations containing points outside $H$. It does not optimize over arbitrary integer coordinates or arbitrary real-plane configurations. No enumeration of all 40-point subsets is needed: the host-line inclusion supplies the upper bound, and the explicit switch supplies attainment.

## Actual API consumption and complete output

The consumer uses the unchanged [integer_line_incidence.cjs](integer_line_incidence.cjs), blob **c9ecc841f6d5b2470e3619206682d3ea8c360449**. The retained input is [sidon_grid_and_cyclic_subset.json](sidon_grid_and_cyclic_subset.json), blob **40063e5bc6a8bbab814e74b0060a1fc535fc2ce7**, from the accepted merge **c5c98b32215d769a7b710962c07d5322169d7820**.

A connected V8 call restored that saved host certificate and invoked `subset` once with the switched point IDs. It did not reconstruct the previous subset or repeat host point-pair construction.

The exact resulting profile is:

| Points on a line | Distinct lines |
|---:|---:|
| 2 | 636 |
| 3 | 6 |
| 4 | 21 |

There are 663 determined lines in total. The maximum collinearity is four. Pair accounting is
$$
636+3(6)+6(21)=780={40\choose2}.
$$

The exact ratio $t_4(Q)/40^2$ is $21/1600$. The API assessment returns $P_4$ true, no overfull line, and the finite lower bound 21.

The dataset retains all 40 coordinates, all 663 canonical primitive line equations, every incident point ID, the complete assessment, the 21 rich-line records, and all line records returned through two pages of 512 and 151 records. The page concatenation equals the complete new snapshot.

All 21 accepted rich host line IDs occur in the new exact-four-point line export. The data also retains the removed/added index pairs, their source point IDs, all selected IDs, the ten first-coordinate counts, the ten second-coordinate counts and the diagonal count. Each coordinate count is four, and the diagonal count is four.

Certificate restoration validates the saved records as prescribed by the existing public API. The new subset operation then scans 3,970 retained line records and 8,136 point memberships, with no coordinate arithmetic, gcd operations or point-pair constructions. The data retains the actual work counters and single-run timing observations; those times are not a comparative benchmark.

The accepted host and the old subset remain available in their original file. This continuation adds the new complete snapshot and derivation, and updates only the directory README.

## Reuse the new snapshot

After loading the unchanged public module text as `moduleText` and parsing the new JSON as `saved`:

```javascript
const m = { exports: {} };
new Function("module", "exports", moduleText)(m, m.exports);

const selected = m.exports.createIntegerLineIncidenceIndex({
  snapshot: saved.snapshot
});
const assessment = selected.assess({ k: 4 });
const richLines = selected.linePage({
  min_points: 4,
  max_points: 4,
  offset: 0,
  limit: 1000
});
```

The new snapshot is complete for its listed 40 points. Its point and line IDs retain the source namespaces, so their gaps are intentional. Snapshot restoration certifies those listed incidences; the separate retained host record and its Git binding supply the fixed-host upper-bound input.

The public module's existing coordinate, point-count, line-count and page limits remain as stated in [INTEGER_LINE_INCIDENCE_API.md](INTEGER_LINE_INCIDENCE_API.md). This continuation introduces no source/API change.

## Attribution and mathematical boundary

The underlying extremal problem is Erdős's Problem 36 in [*Research problems*, Periodica Mathematica Hungarica 15(1) (1984), 101–103](https://www.renyi.hu/~p_erdos/1984-18.pdf). Its $P_k$ condition requires no line to contain more than $k$ distinct points, and $f_k(n)$ ranges over admissible sets of $n$ points in the real plane.

Prior asymptotic construction credit remains with [József Solymosi and Miloš Stojaković, *Many collinear k-tuples with no k+1 collinear points*](https://arxiv.org/pdf/1107.0327), Discrete & Computational Geometry 50 (2013), 811–820. This finite host calculation does not alter that theorem or claim a new external frontier.

The ten values of $S$ retain their original #31157 provenance, as carried by #31177 and #31227. The earlier Sidon search, ordered-representation computation, host-line enumeration and old-subset computation were not rerun.

The proven conclusion is exact fixed-host optimality and the global lower bound $f_4(40)\ge21$. There is no global extremal equality, asymptotic, priority, native-execution or sponsor claim.
