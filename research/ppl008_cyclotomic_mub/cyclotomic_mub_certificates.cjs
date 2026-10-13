'use strict';

// Exact basis-family evidence in Z[zeta_12], with constant-first coefficients.
const FAMILY_SCHEMA = 'commons.cyclotomic12_basis_family/v1';
const SCHEMA = 'commons.cyclotomic12_mub_certificate/v1';
const READER_SCHEMA = 'commons.cyclotomic12_mub_reader/v1';
const LIMITS = Object.freeze({
  min_dimension: 2, max_dimension: 6, max_bases: 7,
  max_input_digits: 64, max_result_digits: 300,
  max_id_chars: 512, max_queries: 64, max_page_size: 36,
  max_source_nodes: 20000, max_source_chars: 1000000,
  max_certificate_nodes: 500000, max_certificate_chars: 12000000,
  max_depth: 24,
});
const POWER12 = Object.freeze([
  [1,0,0,0], [0,1,0,0], [0,0,1,0], [0,0,0,1],
  [-1,0,1,0], [0,-1,0,1], [-1,0,0,0], [0,-1,0,0],
  [0,0,-1,0], [0,0,0,-1], [1,0,-1,0], [0,1,0,-1],
].map(row => Object.freeze(row.map(String))));
const RING = Object.freeze({
  order: 12, embedding: 'zeta = exp(2*pi*i/12) = (sqrt(3)+i)/2',
  basis: Object.freeze(['1', 'zeta', 'zeta^2', 'zeta^3']),
  minimal_polynomial: Object.freeze([1, 0, -1, 0, 1]),
  coefficient_order: 'constant-first', coefficient_format: 'canonical signed decimal integer strings',
  relation: 'zeta^4 = zeta^2 - 1',
  normalization: 'Each column is divided by the positive square root of its squared norm.',
});

function plain(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}
function fields(value, allowed, required, label) {
  plain(value, label);
  if (Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError(label + ' expects fields: ' + allowed.join(', '));
  }
}
function integer(value, label, low, high) {
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(label + ' must be an integer in [' + low + ', ' + high + ']');
  }
  return value;
}
function array(value, length, label) {
  if (!Array.isArray(value) || value.length !== length) throw new TypeError(label + ' has an invalid length');
  return value;
}
function identifier(value, label) {
  if (typeof value !== 'string' || !value.trim() || value.length > LIMITS.max_id_chars) {
    throw new TypeError(label + ' must be a nonempty bounded string');
  }
  return value;
}
function decimal(value, digits, label) {
  if (typeof value !== 'string' || !/^(0|-?[1-9][0-9]*)$/.test(value)
      || value.replace(/^-/, '').length > digits) {
    throw new TypeError(label + ' must be a bounded canonical integer string');
  }
  return value;
}
function encoded(value, digits, label) {
  return array(value, 4, label).map(x => decimal(x, digits, label));
}
function unpack(value) { return value.map(BigInt); }
function pack(value) { return value.map(String); }
function equal(left, right) { return left.every((value, index) => value === right[index]); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function boundedCopy(input, certificate) {
  const capNodes = certificate ? LIMITS.max_certificate_nodes : LIMITS.max_source_nodes;
  const capChars = certificate ? LIMITS.max_certificate_chars : LIMITS.max_source_chars;
  let nodes = 0, chars = 0;
  function copy(value, depth) {
    if (++nodes > capNodes || depth > LIMITS.max_depth) throw new RangeError('Copy structure cap exceeded');
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      chars += value.length;
      if (chars > capChars) throw new RangeError('Copy character cap exceeded');
      return value;
    }
    if (typeof value === 'number' && Number.isSafeInteger(value)) return value;
    if (Array.isArray(value)) return value.map(x => copy(x, depth + 1));
    plain(value, 'copied member');
    const out = {};
    for (const key of Object.keys(value)) {
      chars += key.length;
      if (chars > capChars) throw new RangeError('Copy character cap exceeded');
      Object.defineProperty(out, key, {
        value: copy(value[key], depth + 1), enumerable: true, configurable: true, writable: true,
      });
    }
    return out;
  }
  return copy(input, 0);
}
function inspectFamily(family) {
  fields(family, ['schema', 'source_id', 'dimension', 'bases', 'construction'],
    ['schema', 'source_id', 'dimension', 'bases'], 'basis family');
  if (family.schema !== FAMILY_SCHEMA) throw new TypeError('Unsupported family schema');
  identifier(family.source_id, 'family source_id');
  const dimension = integer(family.dimension, 'dimension', LIMITS.min_dimension, LIMITS.max_dimension);
  if (!Array.isArray(family.bases)) throw new TypeError('bases must be an array');
  integer(family.bases.length, 'basis count', 1, Math.min(LIMITS.max_bases, dimension + 1));
  const ids = new Set();
  for (const basis of family.bases) {
    fields(basis, ['id', 'columns'], ['id', 'columns'], 'basis');
    identifier(basis.id, 'basis id');
    if (ids.has(basis.id)) throw new TypeError('Duplicate basis id');
    ids.add(basis.id);
    for (const column of array(basis.columns, dimension, 'columns')) {
      for (const entry of array(column, dimension, 'column')) {
        encoded(entry, LIMITS.max_input_digits, 'coordinate');
      }
    }
  }
  return dimension;
}

function arithmetic(stats) {
  function add(a, b) {
    stats.ring_additions++; stats.integer_additions += 4;
    return a.map((x, i) => x + b[i]);
  }
  function conjugate(a) {
    stats.ring_conjugations++; stats.integer_additions += 2; stats.integer_negations += 2;
    return [a[0] + a[2], a[1], -a[2], -(a[1] + a[3])];
  }
  function multiply(a, b) {
    stats.ring_products++; stats.integer_products += 16; stats.integer_additions += 21;
    const q = Array(7).fill(0n);
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) q[i + j] += a[i] * b[j];
    return [q[0] - q[4] - q[6], q[1] - q[5], q[2] + q[4], q[3] + q[5]];
  }
  function scale(a, value) {
    stats.ring_scalar_products++; stats.integer_products += 4;
    return a.map(x => x * value);
  }
  function scalarProduct(a, b) { stats.integer_products++; return a * b; }
  function probability(numerator, denominator) {
    if (numerator.slice(1).some(x => x !== 0n) || numerator[0] < 0n) return null;
    let a = numerator[0], b = denominator;
    stats.rational_reductions++;
    while (b !== 0n) { [a, b] = [b, a % b]; stats.euclidean_steps++; }
    stats.exact_integer_divisions += 2;
    return {numerator: String(numerator[0] / a), denominator: String(denominator / a)};
  }
  return {add, conjugate, multiply, scale, scalarProduct, probability};
}

function buildDimensionSixProductTriple(options) {
  fields(options, ['source_id'], ['source_id'], 'construction options');
  const sourceId = identifier(options.source_id, 'source_id');
  const bases = [
    {id: 'computational', columns: []},
    {id: 'fourier_product', columns: []},
    {id: 'quadratic_product', columns: []},
  ];
  const phases = [[], [], []];
  for (let column = 0; column < 6; column++) {
    const b = Math.floor(column / 3), j = column % 3;
    const columns = [[], [], []], labels = [[], [], []];
    for (let row = 0; row < 6; row++) {
      const x = Math.floor(row / 3), y = row % 3;
      const a = (6 * x * b + 4 * y * j) % 12;
      const c = (3 * x + 6 * x * b + 4 * (y * y + y * j)) % 12;
      columns[0].push(row === column ? POWER12[0].slice() : ['0','0','0','0']);
      columns[1].push(POWER12[a].slice()); columns[2].push(POWER12[c].slice());
      labels[0].push(row === column ? 0 : null); labels[1].push(a); labels[2].push(c);
    }
    for (let k = 0; k < 3; k++) { bases[k].columns.push(columns[k]); phases[k].push(labels[k]); }
  }
  return {
    schema: FAMILY_SCHEMA, source_id: sourceId, dimension: 6, bases,
    construction: {
      formula: ['I6', 'H2 tensor F3', 'Y2 tensor (D F3)'],
      H2_rows: [[1,1],[1,-1]], Y2_rows: [['1','1'],['i','-i']],
      F3_entry: 'omega^(y*j)', D_entry: 'omega^(y*y)',
      phase_binding: 'i = zeta^3; omega = zeta^4',
      row_order: 'row = 3*x+y, x=0..1, y=0..2',
      column_order: 'column = 3*b+j, b=0..1, j=0..2',
      phase_exponents_by_basis_column_row: phases,
      power_table: clone(POWER12),
      stats: {identity_entries_written: 36, phase_formula_evaluations: 72, phase_table_lookups: 72},
      scope: 'The classical three product bases; no four-basis construction or global bound.',
    },
  };
}

function certifyCyclotomicMubFamily(input) {
  const family = boundedCopy(input, false);
  const dimension = inspectFamily(family), count = family.bases.length;
  const stats = {
    compiler_calls: 1, input_columns: count * dimension,
    input_coordinates: count * dimension * dimension,
    input_coefficients: 4 * count * dimension * dimension,
    precomputed_coordinate_conjugates: 0, inner_products: 0, retained_component_terms: 0,
    ring_products: 0, ring_additions: 0, ring_conjugations: 0, ring_scalar_products: 0,
    integer_products: 0, integer_additions: 0, integer_negations: 0,
    rational_reductions: 0, euclidean_steps: 0, exact_integer_divisions: 0,
    norm_checks: 0, orthogonality_checks: 0, unbiasedness_checks: 0,
    normalized_overlap_records: 0, floating_point_decisions: 0,
  };
  const op = arithmetic(stats);
  const values = family.bases.map(basis => basis.columns.map(column => column.map(unpack)));
  const adjoints = values.map(basis => basis.map(column => column.map(entry => {
    stats.precomputed_coordinate_conjugates++; return op.conjugate(entry);
  })));
  const records = [], norms = Array.from({length: count}, () => Array(dimension).fill(null));
  const failedNorms = [];
  function address(basis, column) { return {basis, basis_id: family.bases[basis].id, column}; }
  function inner(leftBasis, leftColumn, rightBasis, rightColumn, kind) {
    stats.inner_products++;
    let sum = [0n,0n,0n,0n];
    const terms = [];
    for (let coordinate = 0; coordinate < dimension; coordinate++) {
      const left = adjoints[leftBasis][leftColumn][coordinate];
      const right = values[rightBasis][rightColumn][coordinate];
      const product = op.multiply(left, right);
      sum = op.add(sum, product);
      terms.push({
        coordinate, left_conjugate: pack(left), right: pack(right),
        product: pack(product), partial_sum: pack(sum),
      });
      stats.retained_component_terms++;
    }
    const conjugate = op.conjugate(sum), absoluteSquare = op.multiply(sum, conjugate);
    const row = {
      id: records.length, kind, left: address(leftBasis, leftColumn),
      right: address(rightBasis, rightColumn), terms,
      inner_product: pack(sum), conjugate_inner_product: pack(conjugate),
      absolute_square: pack(absoluteSquare), passed: null, comparison: null,
    };
    records.push(row);
    return {row, sum, absoluteSquare};
  }
  function result(status, complete) {
    return {
      schema: SCHEMA, status, complete, coordinates: clone(RING), limits: clone(LIMITS),
      family, conjugate_columns: adjoints.map(b => b.map(c => c.map(pack))),
      column_squared_norms: norms.map(row => row.map(x => x === null ? null : String(x))),
      records, checks: {
        positive_integer_norms: {checked: stats.norm_checks, failed: failedNorms},
        orthogonality: {checked: stats.orthogonality_checks, failed: records.filter(x => x.kind === 'orthogonality' && !x.passed).map(x => x.id)},
        unbiasedness: {checked: stats.unbiasedness_checks, failed: records.filter(x => x.kind === 'unbiasedness' && !x.passed).map(x => x.id)},
      },
      coverage: {
        norm_records_expected: count * dimension,
        orthogonality_records_expected: count * dimension * (dimension - 1) / 2,
        unbiasedness_records_expected: count * (count - 1) / 2 * dimension * dimension,
        ordering: 'All norms, then within-basis upper pairs, then ordered basis pairs with every column pair.',
        reverse_orientation: 'Conjugate inner products are retained for reverse queries; component traces use the canonical orientation.',
      },
      stats: clone(stats),
      source_identity_authenticated: false,
      proof_scope: 'Exact finite matrix arithmetic under the stated cyclotomic embedding; no global MUB maximum or nonextension proof.',
    };
  }
  for (let b = 0; b < count; b++) for (let column = 0; column < dimension; column++) {
    const item = inner(b, column, b, column, 'norm');
    stats.norm_checks++;
    const valid = item.sum[0] > 0n && item.sum.slice(1).every(x => x === 0n);
    item.row.passed = valid;
    item.row.comparison = {condition: 'positive_integer_squared_norm', observed: pack(item.sum)};
    if (valid) norms[b][column] = item.sum[0];
    else failedNorms.push(item.row.id);
  }
  if (failedNorms.length) return result('UNSUPPORTED_COLUMN_NORMS', false);
  for (let b = 0; b < count; b++) for (let left = 0; left < dimension; left++) {
    for (let right = left + 1; right < dimension; right++) {
      const item = inner(b, left, b, right, 'orthogonality');
      stats.orthogonality_checks++;
      item.row.passed = item.sum.every(x => x === 0n);
      item.row.comparison = {condition: 'zero_inner_product', observed: pack(item.sum), expected: ['0','0','0','0']};
    }
  }
  for (let leftBasis = 0; leftBasis < count; leftBasis++) {
    for (let rightBasis = leftBasis + 1; rightBasis < count; rightBasis++) {
      for (let left = 0; left < dimension; left++) for (let right = 0; right < dimension; right++) {
        const item = inner(leftBasis, left, rightBasis, right, 'unbiasedness');
        stats.unbiasedness_checks++;
        const scaled = op.scale(item.absoluteSquare, BigInt(dimension));
        const target = op.scalarProduct(norms[leftBasis][left], norms[rightBasis][right]);
        item.row.passed = equal(scaled, [target,0n,0n,0n]);
        item.row.comparison = {
          condition: 'dimension_times_absolute_square_equals_norm_product',
          observed: pack(scaled), expected: [String(target),'0','0','0'],
        };
      }
    }
  }
  for (const row of records) {
    const leftNorm = norms[row.left.basis][row.left.column], rightNorm = norms[row.right.basis][row.right.column];
    const denominator = row.kind === 'unbiasedness'
      ? BigInt(row.comparison.expected[0]) : op.scalarProduct(leftNorm, rightNorm);
    const square = unpack(row.absolute_square);
    row.normalization = {
      left_squared_norm: String(leftNorm), right_squared_norm: String(rightNorm),
      squared_overlap: {numerator: row.absolute_square.slice(), denominator: String(denominator)},
      rational_probability: op.probability(square, denominator),
    };
    stats.normalized_overlap_records++;
  }
  return result(records.every(row => row.passed) ? 'EXACT_MUTUALLY_UNBIASED_BASES' : 'NOT_MUTUALLY_UNBIASED', true);
}

function openCyclotomicMubCertificate(input, options) {
  fields(options, ['source_id'], ['source_id'], 'reader options');
  const sourceId = identifier(options.source_id, 'reader source_id');
  const source = boundedCopy(input, true);
  if (source.schema !== SCHEMA || source.complete !== true
      || !['EXACT_MUTUALLY_UNBIASED_BASES', 'NOT_MUTUALLY_UNBIASED'].includes(source.status)
      || JSON.stringify(source.coordinates) !== JSON.stringify(RING)) {
    throw new TypeError('A completed certificate in the exact coordinate convention is required');
  }
  const dimension = inspectFamily(source.family), bases = source.family.bases;
  const count = bases.length, norms = array(source.column_squared_norms, count, 'norm rows');
  function positive(text, label) {
    decimal(text, LIMITS.max_result_digits, label);
    if (BigInt(text) <= 0n) throw new TypeError(label + ' must be positive');
  }
  for (const row of norms) for (const value of array(row, dimension, 'norm row')) positive(value, 'squared norm');
  for (const basis of array(source.conjugate_columns, count, 'conjugate bases')) {
    for (const column of array(basis, dimension, 'conjugate columns')) {
      for (const entry of array(column, dimension, 'conjugate column')) encoded(entry, LIMITS.max_result_digits, 'conjugate coordinate');
    }
  }
  const expected = count * dimension * (dimension + 1) / 2
    + count * (count - 1) / 2 * dimension * dimension;
  array(source.records, expected, 'complete records');
  const index = new Map(), kinds = {all: [], norm: [], orthogonality: [], unbiasedness: []};
  const basisIds = new Map(bases.map((basis, i) => [basis.id, i]));
  let termsCopied = 0;
  function key(left, right) { return left.basis + ':' + left.column + '|' + right.basis + ':' + right.column; }
  function address(value) {
    plain(value, 'record address');
    integer(value.basis, 'address basis', 0, count - 1);
    integer(value.column, 'address column', 0, dimension - 1);
    if (value.basis_id !== bases[value.basis].id) throw new TypeError('Address id disagrees with basis index');
  }
  for (let i = 0; i < source.records.length; i++) {
    const row = source.records[i]; plain(row, 'certificate record');
    if (row.id !== i || typeof row.passed !== 'boolean') throw new TypeError('Invalid record identity or decision');
    address(row.left); address(row.right);
    const left = row.left, right = row.right;
    const kind = left.basis < right.basis ? 'unbiasedness'
      : left.basis === right.basis && left.column === right.column ? 'norm'
      : left.basis === right.basis && left.column < right.column ? 'orthogonality' : null;
    if (row.kind !== kind || kind === null) throw new TypeError('Noncanonical record address');
    if (kind === 'norm' && row.passed !== true) throw new TypeError('Completed source lacks supported positive norms');
    const lookup = key(left, right);
    if (index.has(lookup)) throw new TypeError('Duplicate certificate address');
    index.set(lookup, i); kinds.all.push(i); kinds[kind].push(i);
    for (const name of ['inner_product', 'conjugate_inner_product', 'absolute_square']) {
      encoded(row[name], LIMITS.max_result_digits, name);
    }
    for (let j = 0; j < dimension; j++) {
      const term = array(row.terms, dimension, 'complete component terms')[j];
      plain(term, 'component term');
      if (term.coordinate !== j) throw new TypeError('Component coordinate mismatch');
      for (const name of ['left_conjugate', 'right', 'product', 'partial_sum']) {
        encoded(term[name], LIMITS.max_result_digits, 'component ' + name);
      }
      termsCopied++;
    }
    plain(row.comparison, 'comparison');
    encoded(row.comparison.observed, LIMITS.max_result_digits, 'comparison observed');
    if (kind !== 'norm') encoded(row.comparison.expected, LIMITS.max_result_digits, 'comparison expected');
    const normalized = plain(row.normalization, 'normalization');
    if (normalized.left_squared_norm !== norms[left.basis][left.column]
        || normalized.right_squared_norm !== norms[right.basis][right.column]) {
      throw new TypeError('Normalization norm references disagree');
    }
    plain(normalized.squared_overlap, 'squared overlap');
    if (!equal(encoded(normalized.squared_overlap.numerator, LIMITS.max_result_digits, 'overlap numerator'), row.absolute_square)) {
      throw new TypeError('Squared-overlap numerator disagrees with retained absolute square');
    }
    positive(normalized.squared_overlap.denominator, 'overlap denominator');
    if (normalized.rational_probability !== null) {
      fields(normalized.rational_probability, ['numerator', 'denominator'], ['numerator', 'denominator'], 'rational probability');
      decimal(normalized.rational_probability.numerator, LIMITS.max_result_digits, 'probability numerator');
      if (BigInt(normalized.rational_probability.numerator) < 0n) throw new TypeError('Negative probability numerator');
      positive(normalized.rational_probability.denominator, 'probability denominator');
    }
  }
  if ((source.status === 'EXACT_MUTUALLY_UNBIASED_BASES') !== source.records.every(row => row.passed)) {
    throw new TypeError('Declared status disagrees with retained decisions');
  }
  const queries = [], returned = new Set();
  const stats = {
    reader_opens: 1, source_records_copied: source.records.length,
    source_component_terms_copied: termsCopied, indexed_records: index.size,
    overlap_queries: 0, basis_queries: 0, page_queries: 0,
    source_record_materializations: 0, basis_coordinates_returned: 0,
    source_compiler_calls: 0, new_inner_products: 0, new_ring_products: 0,
    new_rational_reductions: 0, floating_point_decisions: 0,
  };
  function begin(operation, request) {
    if (queries.length >= LIMITS.max_queries) throw new RangeError('Reader query cap reached');
    const query = {id: queries.length + 1, operation, request: clone(request), status: 'in_progress'};
    queries.push(query); return query;
  }
  function basisIndex(id) {
    if (typeof id !== 'string' || !basisIds.has(id)) throw new TypeError('Unknown basis id');
    return basisIds.get(id);
  }
  function materialize(id) {
    returned.add(id); stats.source_record_materializations++;
    return clone(source.records[id]);
  }
  function getOverlap(request) {
    fields(request, ['left_basis', 'left_column', 'right_basis', 'right_column'],
      ['left_basis', 'left_column', 'right_basis', 'right_column'], 'overlap query');
    let left = {basis: basisIndex(request.left_basis), column: integer(request.left_column, 'left column', 0, dimension - 1)};
    let right = {basis: basisIndex(request.right_basis), column: integer(request.right_column, 'right column', 0, dimension - 1)};
    const reversed = left.basis > right.basis || left.basis === right.basis && left.column > right.column;
    if (reversed) [left, right] = [right, left];
    const id = index.get(key(left, right));
    if (id === undefined) throw new TypeError('Retained certificate has no requested address');
    const query = begin('get_overlap', request);
    stats.overlap_queries++;
    const row = materialize(id);
    Object.assign(query, {status: 'complete', source_record_id: id, reversed});
    return {
      ...clone(query), inner_product: (reversed ? row.conjugate_inner_product : row.inner_product).slice(),
      normalization: clone(row.normalization), source_record: row,
      normalization_order: 'Norm factors are stored in canonical source orientation; their product and squared overlap are unchanged by reversal.',
      component_trace_orientation: 'The source record retains its canonical left/right addresses.',
    };
  }
  function getBasis(request) {
    fields(request, ['basis'], ['basis'], 'basis query');
    const b = basisIndex(request.basis), query = begin('get_basis', request);
    stats.basis_queries++; stats.basis_coordinates_returned += dimension * dimension;
    Object.assign(query, {status: 'complete', basis_index: b});
    return {
      ...clone(query), basis: clone(bases[b]), squared_norms: norms[b].slice(),
      conjugate_columns: clone(source.conjugate_columns[b]), coordinates: clone(source.coordinates),
    };
  }
  function page(request) {
    fields(request, ['kind', 'offset', 'limit'], ['kind', 'offset', 'limit'], 'page query');
    if (!Object.prototype.hasOwnProperty.call(kinds, request.kind)) throw new TypeError('Unknown record kind');
    const list = kinds[request.kind];
    integer(request.offset, 'offset', 0, list.length);
    integer(request.limit, 'limit', 1, LIMITS.max_page_size);
    const query = begin('page', request), ids = list.slice(request.offset, request.offset + request.limit);
    stats.page_queries++;
    const rows = ids.map(materialize), next = request.offset + ids.length;
    Object.assign(query, {status: 'complete', returned: rows.length, source_record_ids: ids});
    return {...clone(query), records: rows, total: list.length, next_offset: next < list.length ? next : null};
  }
  function summary() {
    return clone({
      schema: READER_SCHEMA, source_id: sourceId, family_source_id: source.family.source_id,
      source_status: source.status, dimension, basis_ids: bases.map(b => b.id),
      record_counts: Object.fromEntries(Object.entries(kinds).map(([name, ids]) => [name, ids.length])),
      retained_queries: queries.length, unique_returned_records: returned.size, stats,
      validation: 'Bounded structural, address and selected-reference checks; no arithmetic replay or source authentication.',
    });
  }
  function snapshot() {
    return clone({
      schema: READER_SCHEMA, summary: summary(), queries, returned_record_ids: [...returned],
      source_data: 'Retain the identified complete certificate separately.',
      reopening: 'This activity record is not a certificate input or cache-restoration format.',
    });
  }
  return Object.freeze({schema: READER_SCHEMA, getOverlap, getBasis, page, summary, snapshot});
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    buildDimensionSixProductTriple, certifyCyclotomicMubFamily, openCyclotomicMubCertificate,
    FAMILY_SCHEMA, SCHEMA, READER_SCHEMA, LIMITS,
  };
}
