# Finite Lagrange and Lebesgue index

An exact rational interpolation API with complete Bernstein range certificates and saved query support.

Files:

- [lagrange_lebesgue.cjs](lagrange_lebesgue.cjs): dependency-free constructor and saved reader.
- [LEBESGUE_API.md](LEBESGUE_API.md): derivation, source conventions, public interface, limits and scope.
- [thirteen_node_lebesgue.json](thirteen_node_lebesgue.json): full actual coefficients/tree and thirteen query outputs.

The identified thirteen integer coordinates are affinely normalized to [-1,1]. The constructor forms thirteen cardinal polynomials and twelve sign-fixed Lebesgue pieces. Fourteen half-subdivisions leave forty tree nodes and twenty-six leaves, giving the outward norm enclosure:

**[672.216472773058, 672.216472987746]**

The rational gap is below 10^-6. A continuous piecewise-linear nodal-sign witness at x=365241/2136064 attains the sampled lower bound; the point is not asserted to maximize the Lebesgue function. The reader also evaluates actual interpolants of |x| and exports the saved pieces, leaves and subdivision history.

~~~js
const { openLebesgue } = require("./lagrange_lebesgue.cjs");
const api = openLebesgue(savedRecord.snapshot);
const bounds = api.bounds(12);
const witness = api.nodalWitness(bounds.best_x);
const valueAtZero = api.interpolate(["0", "1"], witness.nodal_values);
~~~

New query evaluation uses exact Horner arithmetic, with cached cardinal values. It does not rebuild polynomials, transform coefficients or subdivide. The loader checks structure; mathematical authenticity of imported coefficients and bounds remains an explicit saved-source premise.

[Berrut–Trefethen (2004)](https://people.maths.ox.ac.uk/trefethen/barycentric.pdf) and [Garloff (1993)](https://interval.louisiana.edu/reliable-computing-journal/1993/interval-computations-1993-2-pp-154-168.pdf) supply the classical interpolation and Bernstein context. The integer coordinates are reused from #31427 only as coordinates, without any B3 or finite-field computation.

The PPL128/Erdős671 card asks two infinite-row convergence/divergence questions. This finite operator certificate establishes neither, and the unavailable formal/canonical routes are not treated as a current-status finding. No global optimality, novelty or sponsor claim is made.
