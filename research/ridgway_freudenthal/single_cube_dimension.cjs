'use strict';

/**
 * Exact single-cube Freudenthal divergence dimensions for velocity degrees 4 and 5.
 * Geometry and normalized Bernstein conventions follow kuhn.py and
 * p4_mean_repair.py in this directory; see SINGLE_CUBE_DIMENSION.md.
 * No floating-point rank tolerance or sampled polynomial values are used.
 */

function indices(degree) {
  const result = [];
  for (let a = 0; a <= degree; a++)
    for (let b = 0; b <= degree - a; b++)
      for (let c = 0; c <= degree - a - b; c++)
        result.push([a, b, c, degree - a - b - c]);
  return result;
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function gradients(tet) {
  const [u, v, w] = tet.slice(1).map(p => p.map((x, i) => x - tet[0][i]));
  const det = u.reduce((sum, x, i) => sum + x * cross(v, w)[i], 0);
  if (det !== 1) throw new Error('Expected a positive unit Kuhn tetrahedron');
  const g = [cross(v, w), cross(w, u), cross(u, v)];
  return [Array.from({length: 3}, (_, i) => -g.reduce((s, q) => s + q[i], 0)), ...g];
}

function kuhnTetrahedra() {
  const cells = [];
  // Lexicographic permutations and the same positive-orientation swap as kuhn.py.
  for (let a = 0; a < 3; a++)
    for (let b = 0; b < 3; b++) {
      if (b === a) continue;
      const c = 3 - a - b, point = [0, 0, 0], tet = [[0, 0, 0]];
      for (const axis of [a, b, c]) {
        point[axis] = 1;
        tet.push([...point]);
      }
      const [u, v, w] = tet.slice(1);
      if (u.reduce((s, x, i) => s + x * cross(v, w)[i], 0) < 0)
        [tet[1], tet[2]] = [tet[2], tet[1]];
      gradients(tet);
      cells.push(tet);
    }
  return cells;
}

function coefficientPoint(tet, alpha) {
  return [0, 1, 2].map(axis =>
    alpha.reduce((sum, weight, i) => sum + weight * tet[i][axis], 0));
}

function assembleSingleCube(degree) {
  if (degree !== 4 && degree !== 5)
    throw new RangeError('The single-cube calculation supports degree 4 or 5');
  const cells = kuhnTetrahedra(), nodesByKey = new Map();
  const interior = p => p.every(x => x > 0 && x < degree);
  for (const tet of cells)
    for (const alpha of indices(degree)) {
      const p = coefficientPoint(tet, alpha);
      if (interior(p)) nodesByKey.set(p.join(','), p);
    }
  const nodes = [...nodesByKey.values()].sort((a, b) =>
    a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  if (nodes.length !== (degree - 1) ** 3)
    throw new Error('Incomplete continuous Dirichlet coefficient lattice');
  const nodeId = new Map(nodes.map((p, i) => [p.join(','), i]));
  const pressureIndices = indices(degree - 1), matrix = [];
  for (const tet of cells) {
    const g = gradients(tet);
    for (const beta of pressureIndices) {
      const row = Array(3 * nodes.length).fill(0n);
      for (let i = 0; i < 4; i++) {
        const alpha = [...beta];
        alpha[i]++;
        const id = nodeId.get(coefficientPoint(tet, alpha).join(','));
        if (id === undefined) continue; // The prescribed boundary coefficient is zero.
        for (let axis = 0; axis < 3; axis++) row[3 * id + axis] += BigInt(g[i][axis]);
      }
      matrix.push(row);
    }
  }
  return {degree, cells, nodes, pressureIndices, matrix};
}

// Fraction-free elimination. Every division is an exact Sylvester/Bareiss identity.
// The last nonzero pivot is the determinant of the selected original-row/column minor.
function fractionFreeEchelon(A) {
  const R = A.map(row => [...row]), width = R[0].length;
  const rowIds = R.map((_, i) => i), pivotColumns = [];
  let rank = 0, previous = 1n;
  for (let col = 0; col < width && rank < R.length; col++) {
    let selected = rank;
    while (selected < R.length && R[selected][col] === 0n) selected++;
    if (selected === R.length) continue;
    [R[rank], R[selected]] = [R[selected], R[rank]];
    [rowIds[rank], rowIds[selected]] = [rowIds[selected], rowIds[rank]];
    const pivot = R[rank][col];
    for (let i = rank + 1; i < R.length; i++) {
      const coefficient = R[i][col];
      for (let j = col + 1; j < width; j++) {
        const numerator = pivot * R[i][j] - coefficient * R[rank][j];
        if (numerator % previous !== 0n) throw new Error('Nonexact Bareiss division');
        R[i][j] = numerator / previous;
      }
      R[i][col] = 0n;
    }
    pivotColumns.push(col);
    previous = pivot;
    rank++;
  }
  return {echelon: R, pivotColumns, pivotRows: rowIds.slice(0, rank), minorDeterminant: previous};
}

// Back-substitution clears each denominator by positive scaling. The result is a
// primitive integral basis over Q (and R), not a claim about a saturated Z-module.
function integralKernelCertificate(A, echelon, pivotColumns) {
  const n = A[0].length, rank = pivotColumns.length;
  for (let i = 0; i < rank; i++) {
    const p = pivotColumns[i];
    if (echelon[i][p] === 0n || echelon[i].slice(0, p).some(x => x !== 0n))
      throw new Error('Invalid row-echelon pivot structure');
  }
  if (echelon.slice(rank).some(row => row.some(x => x !== 0n)))
    throw new Error('Unlisted nonzero row');
  const abs = x => x < 0n ? -x : x;
  const gcd = (a, b) => {
    a = abs(a); b = abs(b);
    while (b !== 0n) [a, b] = [b, a % b];
    return a;
  };
  const pivotSet = new Set(pivotColumns);
  const freeColumns = Array.from({length: n}, (_, j) => j).filter(j => !pivotSet.has(j));
  const basis = [], freeDiagonal = [];
  for (const f of freeColumns) {
    const v = Array(n).fill(0n);
    v[f] = 1n;
    for (let i = rank - 1; i >= 0; i--) {
      const p = pivotColumns[i], d = echelon[i][p];
      let sum = 0n;
      for (let j = p + 1; j < n; j++) sum += echelon[i][j] * v[j];
      const g = gcd(sum, d), scale = abs(d) / g;
      if (scale !== 1n) for (let j = 0; j < n; j++) v[j] *= scale;
      v[p] = -(sum / g) * (d < 0n ? -1n : 1n);
    }
    let common = 0n;
    for (const x of v) common = gcd(common, x);
    if (common > 1n) for (let j = 0; j < n; j++) v[j] /= common;
    if (v[f] <= 0n || freeColumns.some(j => j !== f && v[j] !== 0n))
      throw new Error('Free-coordinate independence identity failed');
    for (const row of A) {
      let sum = 0n;
      for (let j = 0; j < n; j++) sum += row[j] * v[j];
      if (sum !== 0n) throw new Error('Original-matrix kernel identity failed');
    }
    basis.push(v);
    freeDiagonal.push(v[f]);
  }
  return {basis, freeColumns, freeDiagonal};
}

function singleCubeDimension(degree) {
  const {cells, nodes, pressureIndices, matrix: A} = assembleSingleCube(degree);
  const width = A[0].length;
  // All six cells have equal volume, and normalized Bernstein functions have
  // equal integrals. Zero column sums express the global zero-mean divergence.
  for (let j = 0; j < width; j++)
    if (A.reduce((sum, row) => sum + row[j], 0n) !== 0n)
      throw new Error('Global mean identity failed');
  const E = fractionFreeEchelon(A);
  const K = integralKernelCertificate(A, E.echelon, E.pivotColumns);
  const sparse = vector => vector.flatMap((value, column) =>
    value === 0n ? [] : [[column, value.toString()]]);
  return {
    degree,
    cells,
    nodeNumerators: nodes,
    nodeDenominator: degree,
    pressureMultiIndices: pressureIndices,
    operator: 'A = div / degree in normalized Bernstein coefficients',
    rowOrder: 'cell, then pressureMultiIndices',
    columnOrder: 'nodeNumerators, then x/y/z component',
    velocityDimension: width,
    pressureAmbientDimension: A.length,
    matrixNonzeros: A.reduce((sum, row) => sum + row.filter(x => x !== 0n).length, 0),
    imageDimension: E.pivotColumns.length,
    kernelDimension: K.basis.length,
    pivotRows: E.pivotRows,
    pivotColumns: E.pivotColumns,
    minorDeterminant: E.minorDeterminant.toString(),
    freeColumns: K.freeColumns,
    freeDiagonal: K.freeDiagonal.map(x => x.toString()),
    kernelBasis: K.basis.map(sparse),
    identities: {
      columnSums: 'zero',
      originalMatrixTimesKernel: 'zero',
      freeCoordinateSubmatrix: 'positive diagonal',
    },
  };
}

module.exports = {assembleSingleCube, singleCubeDimension};

if (typeof require !== 'undefined' && require.main === module) {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args.length === 1 && !['4', '5'].includes(args[0])))
    throw new Error('Usage: node single_cube_dimension.cjs [4|5]');
  const degrees = args.length ? [Number(args[0])] : [4, 5];
  process.stdout.write(JSON.stringify(degrees.map(singleCubeDimension), null, 2) + '\n');
}
