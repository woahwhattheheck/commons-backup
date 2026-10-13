# Erdős 30: a finite Singer plane and Sidon index

The public API consumes an identified accepted prime-cubic power cycle and
retains a new trace-zero difference-set certificate. For the actual GF(13³)
input, the set modulo 183 is

```text
4, 7, 32, 50, 52, 61, 85, 91, 101, 108, 122, 123, 127, 135
```

All 182 nonzero ordered differences and 105 unordered two-sums are retained,
including 14 diagonal sums. Translating by −3 gives an ordinary integer
Sidon set of size 14 ending at 132, so **h(132) ≥ 14**.

The size is optimal for cyclic Sidon subsets modulo 183, by
k(k−1) ≤ 182. This does not establish h(132)=14 or solve the sharp
Erdős 30 error-term problem.

The associated finite projective plane has 183 points, 183 lines and
14 incidences per point or line. Its 2,562 incidences are represented by
cyclic translation. These finite-field objects are not real-plane points
and lines.

## Use the saved result

```js
const moduleBox = { exports: {} };
new Function("module", "exports", moduleText)(
  moduleBox, moduleBox.exports
);
const saved = JSON.parse(artifactText);
const plane = moduleBox.exports.openRetainedSingerPlane(saved.snapshot);

plane.join(53, 60);  // line 135
plane.meet(53, 60);  // point 161
plane.pairForSum(8); // exactly 4 + 4
```

See [SINGER_PLANE_API.md](SINGER_PLANE_API.md) for the complete contracts,
derivation and source boundaries. The
[complete artifact](prime13_singer_plane.json) includes every trace
classification and difference/sum witness plus all 16 fresh reader results.
The [module](singer_plane_index.cjs) also supports line/pencil pages,
rank/select navigation, modular sum decoding and positive integer lifts.

## Source and validation scope

The input is the unchanged
[Commons #31278](https://github.com/woahwhattheheck/commons/pull/31278)
field record, blob `2b77e0e8dc97c5107ab5a4e5cca162a92c12de38`.
The new source was frozen at
`171abd0a5332617eb6c3874617e6e1926dd615db` before its single actual run.
A fresh reader checked the saved finite difference/sum rows and made 16
queries with zero field, trace, cycle or pair enumerations.

The classical construction is credited to Singer (1938); the explicit
trace-zero quotient account is in
[Mészáros–Rónyai–Szabó, §1.2](https://arxiv.org/pdf/1908.05591).
The [formal Erdős 30 statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/30.lean)
asks h(N)=√N+Oε(N^ε) for every ε>0 and records a separate stronger O(1)
question. The guide retains dated primary-source status and the full
finite/global distinction.

Only q=13 was exercised. Other supported prime inputs and refusal branches
were source-inspected; no synthetic suite, accepted field/B₃ replay,
new asymptotic result, external record or prize claim is involved.
