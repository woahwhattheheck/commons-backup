'use strict';

// Decode fixed-length triple sums from an established saved Bose-Chowla source.
const INPUT_SCHEMA = 'erdos241.bose_chowla_b3/v1';
const SCHEMA = 'erdos241.bose_chowla_triple_decoder/v1';
const LIMITS = Object.freeze({
  min_prime: 2, max_prime: 43, max_power_codes: 79506,
  max_sum_digits: 1024, max_queries: 64, max_cached_polynomials: 64,
  max_source_id_chars: 512, max_snapshot_nodes: 400000,
  max_snapshot_chars: 4000000, max_snapshot_depth: 24,
});

class DecoderSourceError extends Error {
  constructor(message) { super(message); this.name = 'DecoderSourceError'; }
}
function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}
function fields(value, allowed, required, label) {
  object(value, label);
  if (Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError(label + ' expects fields: ' + allowed.join(', '));
  }
}
function integer(value, label, low, high) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(label + ' must be a safe integer in [' + low + ', ' + high + ']');
  }
  return value;
}
function array(value, label, length) {
  if (!Array.isArray(value) || value.length !== length) throw new TypeError(label + ' has an invalid length');
  return value;
}
function identity(value, label) {
  if (typeof value !== 'string' || !value.trim() || value.length > LIMITS.max_source_id_chars) {
    throw new TypeError(label + ' must be a nonempty bounded string');
  }
  return value;
}
function mod(value, modulus) { return ((value % modulus) + modulus) % modulus; }
function modBig(value, modulus) { return ((value % modulus) + modulus) % modulus; }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function boundedClone(input) {
  let nodes = 0, chars = 0;
  function copy(value, depth) {
    if (++nodes > LIMITS.max_snapshot_nodes || depth > LIMITS.max_snapshot_depth) {
      throw new RangeError('Source snapshot structure cap exceeded');
    }
    if (value === null || typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      chars += value.length;
      if (chars > LIMITS.max_snapshot_chars) throw new RangeError('Source snapshot character cap exceeded');
      return value;
    }
    if (typeof value === 'number' && Number.isSafeInteger(value)) return value;
    if (Array.isArray(value)) return value.map(item => copy(item, depth + 1));
    object(value, 'source snapshot member');
    const out = {};
    for (const key of Object.keys(value)) {
      chars += key.length;
      if (chars > LIMITS.max_snapshot_chars) throw new RangeError('Source snapshot character cap exceeded');
      Object.defineProperty(out, key, {
        value: copy(value[key], depth + 1), enumerable: true, configurable: true, writable: true,
      });
    }
    return out;
  }
  return copy(input, 0);
}
function sumText(value) {
  const text = typeof value === 'bigint' ? value.toString()
    : typeof value === 'number' && Number.isSafeInteger(value) ? String(value) : value;
  if (typeof text !== 'string' || !/^(0|-?[1-9][0-9]*)$/.test(text)
      || text.replace(/^-/, '').length > LIMITS.max_sum_digits) {
    throw new TypeError('sum must be a bounded canonical integer string, BigInt or safe integer');
  }
  return text;
}
function coefficients(code, prime) {
  return [code % prime, Math.floor(code / prime) % prime, Math.floor(code / (prime * prime))];
}
function sameArray(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function loadSource(input) {
  const source = boundedClone(input);
  object(source, 'construction');
  if (source.schema !== INPUT_SCHEMA || source.status !== 'EXACT_CONSTRUCTED_B3_SET'
      || source.order_of_sums !== 3) throw new DecoderSourceError('Unsupported complete B3 source');
  const prime = integer(source.prime, 'source prime', LIMITS.min_prime, LIMITS.max_prime);
  const modulus = integer(source.cyclic_modulus, 'source modulus', 7, LIMITS.max_power_codes);
  if (source.field_size !== prime ** 3 || modulus !== prime ** 3 - 1) {
    throw new DecoderSourceError('Source field size and modulus disagree');
  }
  for (const value of array(source.cubic_coefficients, 'source cubic coefficients', 3)) {
    integer(value, 'source cubic coefficient', 0, prime - 1);
  }
  const encoding = object(source.field_encoding, 'source encoding');
  if (!sameArray(array(encoding.basis, 'source basis labels', 3), ['1', 'alpha', 'alpha^2'])
      || encoding.code !== 'c0 + prime*c1 + prime^2*c2'
      || encoding.coefficient_order !== 'constant, linear, quadratic') {
    throw new DecoderSourceError('Unsupported source field encoding');
  }
  const generator = object(source.generator_search, 'source generator');
  const theta = integer(generator.selected_code, 'source generator code', 1, modulus);
  const thetaCoefficients = array(generator.selected_coefficients, 'source generator coefficients', 3);
  if (!sameArray(thetaCoefficients, coefficients(theta, prime))) {
    throw new DecoderSourceError('Source generator coefficient/code mismatch');
  }
  const degree = object(source.degree_three_certificate, 'source degree certificate');
  if (degree.determinant_nonzero !== true) throw new DecoderSourceError('A retained nonzero degree certificate is required');
  integer(degree.determinant_mod_prime, 'source basis determinant', 1, prime - 1);
  const basis = array(degree.basis_columns, 'source basis columns', 3);
  for (const column of basis) {
    for (const value of array(column, 'source basis column', 3)) integer(value, 'basis coefficient', 0, prime - 1);
  }
  const thetaSquared = integer(degree.theta_squared_code, 'saved theta squared code', 1, modulus);
  if (!sameArray(basis[0], [1, 0, 0]) || !sameArray(basis[1], thetaCoefficients)
      || !sameArray(basis[2], coefficients(thetaSquared, prime))) {
    throw new DecoderSourceError('Source basis columns do not identify 1, theta and theta squared');
  }
  const cycle = object(source.power_cycle, 'source power cycle');
  const codes = array(cycle.codes, 'source power codes', modulus);
  if (cycle.exponent_start !== 0 || cycle.exponent_end_inclusive !== modulus - 1
      || cycle.unique_nonzero_codes !== modulus || cycle.next_code_after_cycle !== 1
      || codes[0] !== 1 || codes[1] !== theta || codes[2] !== thetaSquared) {
    throw new DecoderSourceError('Source power-cycle declarations disagree');
  }
  const seen = new Set();
  for (const code of codes) {
    integer(code, 'saved nonzero field code', 1, modulus);
    if (seen.has(code)) throw new DecoderSourceError('Duplicate saved field code');
    seen.add(code);
  }
  const offsetRows = array(source.affine_offset_exponents, 'source offset records', prime);
  const byOffset = new Array(prime);
  const exponents = new Set();
  for (const row of offsetRows) {
    object(row, 'offset record');
    const offset = integer(row.offset, 'source offset', 0, prime - 1);
    const exponent = integer(row.canonical_exponent, 'source exponent', 1, modulus - 1);
    const code = integer(row.target_code, 'source offset target', 1, modulus);
    const vector = array(row.target_coefficients, 'source target coefficients', 3);
    const expected = [mod(thetaCoefficients[0] + offset, prime), thetaCoefficients[1], thetaCoefficients[2]];
    if (byOffset[offset] !== undefined || exponents.has(exponent)
        || !sameArray(vector, coefficients(code, prime)) || !sameArray(vector, expected)
        || codes[exponent] !== code) {
      throw new DecoderSourceError('Source offset, code or saved exponent references disagree');
    }
    byOffset[offset] = row; exponents.add(exponent);
  }
  const residues = array(source.canonical_residues, 'source canonical residues', prime);
  if (!sameArray(residues, [...exponents].sort((a, b) => a - b))) {
    throw new DecoderSourceError('Source residue list disagrees with its offset map');
  }
  const consequences = object(source.theorem_consequences, 'source theorem declarations');
  if (consequences.cardinality !== prime || consequences.modular_B3 !== true
      || consequences.repetitions_in_triples_allowed !== true || consequences.equal_sums_identify_multisets !== true) {
    throw new DecoderSourceError('The retained repeated-triple B3 premise is required');
  }
  return {source, prime, modulus, codes, basis, byOffset, theta, thetaSquared};
}

function openBoseChowlaTripleDecoder(input, options) {
  fields(options, ['source_id', 'affine_source_id', 'unit', 'translation'], ['source_id'], 'decoder options');
  const sourceId = identity(options.source_id, 'source_id');
  const affineSourceId = options.affine_source_id === undefined ? null
    : identity(options.affine_source_id, 'affine_source_id');
  const loaded = loadSource(input);
  const {prime, modulus, codes, basis, byOffset} = loaded;
  const unit = integer(options.unit === undefined ? 1 : options.unit, 'unit', 1, modulus - 1);
  const translation = integer(options.translation === undefined ? 0 : options.translation, 'translation', 0, modulus - 1);
  const stats = {
    source_power_codes_loaded: codes.length, source_offset_records_loaded: byOffset.length,
    source_code_permutation_entries_checked: codes.length,
    source_constructor_calls: 0, source_primitive_tests: 0, source_cycle_steps: 0,
    extension_field_multiplications: 0, field_power_calls: 0,
    affine_orbit_evaluations: 0, triple_candidates_enumerated: 0,
    modular_inverse_calls: 0, euclidean_steps: 0,
    basis_row_swaps: 0, base_field_products: 0, base_field_additions: 0,
    coordinate_transforms: 0, arithmetic_saved_power_reads: 0,
    decoder_field_code_decodings: 0, positive_term_maps: 0,
    sum_normalizations: 0, polynomial_cache_misses: 0, polynomial_cache_hits: 0,
    root_offsets_visited: 0, synthetic_division_attempts: 0, linear_factors_removed: 0,
    integer_sum_comparisons: 0,
  };
  const queries = [], cache = new Map();
  function product(a, b) { stats.base_field_products++; return (a * b) % prime; }
  function add(a, b) { stats.base_field_additions++; return mod(a + b, prime); }
  function inverse(value, ring, label) {
    stats.modular_inverse_calls++;
    let oldR = value, r = ring, oldS = 1, s = 0;
    while (r !== 0) {
      const quotient = Math.floor(oldR / r);
      [oldR, r] = [r, oldR - quotient * r];
      [oldS, s] = [s, oldS - quotient * s];
      stats.euclidean_steps++;
    }
    if (oldR !== 1) throw new DecoderSourceError(label + ' is not invertible');
    const inv = mod(oldS, ring);
    return {value, modulus: ring, inverse: inv, bezout_modulus_coefficient: (1 - value * inv) / ring};
  }
  const unitInverse = inverse(unit, modulus, 'affine unit');
  const matrix = Array.from({length: 3}, (_, row) => [
    ...basis.map(column => column[row]), ...Array.from({length: 3}, (_, column) => row === column ? 1 : 0),
  ]);
  const elimination = [];
  for (let column = 0; column < 3; column++) {
    let pivot = column;
    while (pivot < 3 && matrix[pivot][column] === 0) pivot++;
    if (pivot === 3) throw new DecoderSourceError('Saved degree basis is singular');
    if (pivot !== column) {
      [matrix[pivot], matrix[column]] = [matrix[column], matrix[pivot]];
      stats.basis_row_swaps++;
      elimination.push({operation: 'swap', rows: [pivot, column], matrix_after: clone(matrix)});
    }
    const witness = inverse(matrix[column][column], prime, 'basis pivot');
    matrix[column] = matrix[column].map(value => product(value, witness.inverse));
    elimination.push({operation: 'scale', row: column, inverse_witness: witness, matrix_after: clone(matrix)});
    for (let row = 0; row < 3; row++) {
      if (row === column || matrix[row][column] === 0) continue;
      const factor = matrix[row][column];
      for (let j = 0; j < 6; j++) matrix[row][j] = add(matrix[row][j], -product(factor, matrix[column][j]));
      elimination.push({operation: 'subtract_scaled_row', row, source_row: column, factor, matrix_after: clone(matrix)});
    }
  }
  const inverseBasis = matrix.map(row => row.slice(3));
  function transform(vector) {
    stats.coordinate_transforms++;
    return inverseBasis.map(row => {
      let value = 0;
      for (let column = 0; column < 3; column++) value = add(value, product(row[column], vector[column]));
      return value;
    });
  }
  function savedPower(exponent) {
    stats.arithmetic_saved_power_reads++;
    stats.decoder_field_code_decodings++;
    const code = codes[exponent], vector = coefficients(code, prime);
    return {exponent, code, alpha_coefficients: vector, theta_coefficients: transform(vector)};
  }
  const thetaCubed = savedPower(3);
  const minimalPolynomial = [...thetaCubed.theta_coefficients.map(value => mod(-value, prime)), 1];
  const terms = byOffset.map(row => {
    const residue = mod(unit * row.canonical_exponent + translation, modulus);
    stats.positive_term_maps++;
    return {
      offset: row.offset, canonical_exponent: row.canonical_exponent,
      source_target_code: row.target_code, positive_integer: residue === 0 ? modulus : residue,
    };
  });
  const positiveValues = terms.map(row => row.positive_integer).sort((a, b) => a - b);
  const calibration = {
    coefficient_order: 'constant first', basis_columns: clone(basis),
    inverse_basis_rows: clone(inverseBasis), basis_elimination: elimination,
    saved_theta_cubed: thetaCubed, minimal_polynomial: minimalPolynomial,
    minimal_polynomial_reason: 'Saved theta cubed expressed in the retained degree-three basis.',
    affine: {
      unit, translation, unit_inverse: unitInverse,
      positive_representative: 'The unique representative in 1..modulus; zero residue is represented by modulus.',
      sum_normalization: 'source_exponent = unit_inverse * (sum - 3*translation) modulo modulus',
    },
  };

  function divideByRoot(polynomial, root) {
    const degree = polynomial.length - 1;
    const quotient = new Array(degree);
    quotient[degree - 1] = polynomial[degree];
    for (let index = degree - 1; index >= 1; index--) {
      quotient[index - 1] = add(polynomial[index], product(root, quotient[index]));
    }
    const remainder = add(polynomial[0], product(root, quotient[0]));
    stats.synthetic_division_attempts++;
    return {quotient, remainder};
  }
  function polynomialFor(exponent) {
    if (cache.has(exponent)) {
      stats.polynomial_cache_hits++;
      const old = cache.get(exponent);
      if (old.status === 'source_error') throw new DecoderSourceError(old.error);
      return old;
    }
    if (cache.size >= LIMITS.max_cached_polynomials) throw new RangeError('Polynomial cache cap reached');
    stats.polynomial_cache_misses++;
    const entry = {source_exponent: exponent, status: 'in_progress', division_trace: [], decoded: null};
    cache.set(exponent, entry);
    const before = {
      base_field_products: stats.base_field_products, base_field_additions: stats.base_field_additions,
      coordinate_transforms: stats.coordinate_transforms, arithmetic_saved_power_reads: stats.arithmetic_saved_power_reads,
      root_offsets_visited: stats.root_offsets_visited, synthetic_division_attempts: stats.synthetic_division_attempts,
      linear_factors_removed: stats.linear_factors_removed,
    };
    try {
      entry.saved_power = savedPower(exponent);
      const values = entry.saved_power.theta_coefficients;
      let polynomial = [add(minimalPolynomial[0], values[0]),
        add(minimalPolynomial[1], values[1]), add(minimalPolynomial[2], values[2]), 1];
      entry.monic_polynomial = polynomial.slice();
      const offsets = [];
      for (let offset = 0; offset < prime && polynomial.length > 1; offset++) {
        stats.root_offsets_visited++;
        const root = mod(-offset, prime);
        while (polynomial.length > 1) {
          const division = divideByRoot(polynomial, root);
          entry.division_trace.push({
            offset, root, dividend: polynomial.slice(), quotient: division.quotient.slice(),
            remainder: division.remainder,
          });
          if (division.remainder !== 0) break;
          polynomial = division.quotient;
          offsets.push(offset);
          stats.linear_factors_removed++;
        }
      }
      entry.offset_multiset = offsets;
      entry.residual_polynomial = polynomial.slice();
      entry.root_scan_scope = polynomial.length === 1
        ? 'Stopped after complete splitting; all three factors are retained.'
        : 'Every base-field offset was visited; no further linear factor remains.';
      if (polynomial.length !== 1) {
        entry.status = 'not_split';
        entry.reason = 'The unique monic cubic does not split into three source linear factors.';
        return entry;
      }
      if (polynomial[0] !== 1 || offsets.length !== 3) {
        throw new DecoderSourceError('The synthetic factor record has an inconsistent degree or leading coefficient');
      }
      const decodedTerms = offsets.map(offset => clone(terms[offset]))
        .sort((left, right) => left.positive_integer - right.positive_integer);
      const sourceSum = decodedTerms.reduce((sum, row) => sum + row.canonical_exponent, 0);
      if (mod(sourceSum, modulus) !== exponent) {
        throw new DecoderSourceError('Factored source labels disagree with the saved exponent address');
      }
      const integerSum = decodedTerms.reduce((sum, row) => sum + row.positive_integer, 0);
      if (mod(integerSum, modulus) !== mod(unit * exponent + 3 * translation, modulus)) {
        throw new DecoderSourceError('Factored positive lifts disagree with their affine residue');
      }
      const multiplicities = [];
      for (const term of decodedTerms) {
        const last = multiplicities[multiplicities.length - 1];
        if (last?.offset === term.offset) last.multiplicity++;
        else multiplicities.push({...term, multiplicity: 1});
      }
      entry.status = 'decoded';
      entry.decoded = {
        unique_multiset: true, repeated_summands_allowed: true,
        terms: decodedTerms, positive_values: decodedTerms.map(row => row.positive_integer),
        multiplicities, integer_sum: String(integerSum), integer_sum_residue: mod(integerSum, modulus),
        source_exponent_sum: sourceSum, source_exponent_sum_residue: mod(sourceSum, modulus),
      };
      return entry;
    } catch (error) {
      entry.status = 'source_error';
      entry.error = String(error.message ?? error);
      throw error;
    } finally {
      entry.new_work = Object.fromEntries(Object.entries(before).map(([key, value]) => [key, stats[key] - value]));
    }
  }

  function decode(query, operation) {
    fields(query, ['sum'], ['sum'], 'sum query');
    const text = sumText(query.sum), requested = BigInt(text);
    if (queries.length >= LIMITS.max_queries) throw new RangeError('Query cap reached; retain the current decoder snapshot');
    const record = {id: queries.length + 1, operation, sum: text, status: 'in_progress'};
    queries.push(record);
    try {
      const ring = BigInt(modulus), residue = modBig(requested, ring);
      const exponent = Number(modBig((residue - 3n * BigInt(translation)) * BigInt(unitInverse.inverse), ring));
      stats.sum_normalizations++;
      Object.assign(record, {
        affine_sum_residue: Number(residue), source_exponent: exponent,
        polynomial_key: String(exponent), reused_polynomial: cache.has(exponent),
      });
      const polynomial = polynomialFor(exponent);
      record.modular_representation_exists = polynomial.status === 'decoded';
      if (polynomial.status === 'not_split') {
        record.status = 'no_representation';
        record.reason = 'The source monic cubic does not split completely.';
        record.represented_integer_sum = null;
      } else {
        record.represented_integer_sum = polynomial.decoded.integer_sum;
        if (operation === 'decode_integer_sum') {
          stats.integer_sum_comparisons++;
          record.integer_sum_matches = BigInt(polynomial.decoded.integer_sum) === requested;
          record.status = record.integer_sum_matches ? 'decoded' : 'integer_lift_mismatch';
          if (!record.integer_sum_matches) {
            record.reason = 'The unique modular triple has a different ordinary integer sum.';
          }
        } else {
          record.status = 'decoded';
          record.integer_sum_matches = null;
        }
      }
      record.found = record.status === 'decoded';
      return clone({...record, decoded: polynomial.decoded, polynomial_record: polynomial});
    } catch (error) {
      record.status = error instanceof DecoderSourceError ? 'source_error' : 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  const sourceSummary = {
    schema: INPUT_SCHEMA, source_id: sourceId, affine_source_id: affineSourceId,
    declared_status: loaded.source.status, prime, field_size: loaded.source.field_size,
    modulus, source_generator_code: loaded.theta,
    source_cubic_coefficients: loaded.source.cubic_coefficients.slice(),
    power_codes_copied: codes.length, offset_records_copied: byOffset.length,
    validation: 'Bounded structural/reference checks and decoder basis inversion; no source construction replay.',
    mathematical_premises: 'Caller-established field, primitive element, degree basis, exact powers and plus-offset B3 map.',
    source_identity_authenticated: false,
  };
  function summary() {
    return clone({
      schema: SCHEMA, source: sourceSummary, affine: calibration.affine,
      positive_values: positiveValues, minimum_positive_value: positiveValues[0],
      maximum_positive_value: positiveValues[positiveValues.length - 1],
      stats, cached_polynomials: cache.size, retained_queries: queries.length,
    });
  }
  function snapshot() {
    return clone({
      schema: SCHEMA, limits: LIMITS, summary: summary(),
      calibration, offset_terms: terms,
      polynomials: [...cache.values()], queries,
      source_data: 'The complete power table remains in its identified source artifact; this records new decoder activity.',
      reopening: 'This activity snapshot is not a constructor input or a cache-restoration format.',
      proof_boundary: 'Decoding is conditional on the retained source mathematics; no extremal or asymptotic claim.',
    });
  }
  return Object.freeze({
    schema: SCHEMA,
    decodeModSum: query => decode(query, 'decode_mod_sum'),
    decodeIntegerSum: query => decode(query, 'decode_integer_sum'),
    summary, snapshot,
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {openBoseChowlaTripleDecoder, DecoderSourceError, INPUT_SCHEMA, SCHEMA, LIMITS};
}
