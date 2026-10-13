'use strict';

// Exact integer traces for an explicitly proved cubic Beatty family.
// Mathematical statement and provenance: CUBIC_TRACE_API.md.
// No provider, process, filesystem, floating-root or dynamic-code operations.
const SCHEMA = 'commons.ppl034.cubic_trace_index/v1';
const LIMITS = Object.freeze({
  min_m: 6, max_m: 128, max_trace_index: 8192,
  max_threshold_digits: 4096, max_window: 64,
  max_trace_records: 128, max_floor_certificates: 64, max_queries: 32,
});

function boundedInteger(value, label, lower, upper) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)
      || value < lower || value > upper) {
    throw new RangeError(label + ' must be an integer in [' + lower + ', ' + upper + ']');
  }
  return value;
}

function positiveIntegerText(value, label) {
  const result = typeof value === 'bigint' ? value.toString() : value;
  if (typeof result !== 'string' || !/^[1-9][0-9]*$/.test(result)
      || result.length > LIMITS.max_threshold_digits) {
    throw new RangeError(label + ' must be a positive canonical decimal string or BigInt within the digit cap');
  }
  return result;
}

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createCubicTraceIndex(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)
      || Object.keys(input).some(key => key !== 'm')) {
    throw new TypeError('Supply an object with only the integer parameter m');
  }
  const m = boundedInteger(input.m, 'm', LIMITS.min_m, LIMITS.max_m);
  const b = BigInt(m);
  const M = b - 1n;
  const L = (2 * m).toString(2).length;
  const startK = (m - 2) * L;
  const maxK = LIMITS.max_trace_index - 1;
  const seeds = [3n, b, b * b - 2n * b + 2n];
  const powers = [[0n, 1n, 0n]];
  const traces = new Map();
  const certificates = new Map();
  const queries = [];
  const stats = {
    polynomial_products: 0, power_squares_built: 0, term_products: 0,
    trace_records_built: 0, trace_cache_hits: 0,
    floor_certificates_built: 0, floor_certificate_cache_hits: 0,
    root_approximations: 0, linear_prefix_steps: 0,
  };
  for (let k = 0; k < 3; k++) {
    const basis = [0n, 0n, 0n];
    basis[k] = 1n;
    traces.set(k, {k, value: seeds[k], coefficients: basis, power_bits: [], kind: 'Newton seed'});
  }
  const proof = {
    family: 'x^3 - m*x^2 + (m-1)*x - 1, integer m >= 6',
    polynomial_coefficients_descending: ['1', (-b).toString(), M.toString(), '-1'],
    slope: 'largest real root alpha',
    isolated_roots: [
      {name: 'beta', lower: ['0', '1'], upper: ['1', '2']},
      {name: 'gamma', lower: ['1', '2'], upper: [(M - 1n).toString(), M.toString()]},
      {name: 'alpha', lower: [M.toString(), '1'], upper: [b.toString(), '1']},
    ],
    scaled_polynomial_signs: [
      {x: ['0', '1'], value_numerator: '-1', value_denominator: '1'},
      {x: ['1', '2'], value_numerator: (2n * b - 11n).toString(), value_denominator: '8'},
      {x: [(M - 1n).toString(), M.toString()],
        value_numerator: (-(2n * M * M - 2n * M + 1n)).toString(),
        value_denominator: (M * M * M).toString()},
      {x: [M.toString(), '1'], value_numerator: '-1', value_denominator: '1'},
      {x: [b.toString(), '1'], value_numerator: (b * M - 1n).toString(), value_denominator: '1'},
    ],
    rational_root_exclusion: {at_one: '-1', at_minus_one: (-(2n * b + 1n)).toString()},
    trace_seeds: seeds.map(String),
    recurrence_coefficients: [b.toString(), (-M).toString(), '1'],
    recurrence: 'S[k+3] = m*S[k+2] - (m-1)*S[k+1] + S[k]',
    error: '0 < alpha*S[k] - S[k+1] < 2*m*((m-2)/(m-1))^k',
    dyadic_block_length: m - 2,
    dyadic_blocks: L,
    certified_start_k: startK,
    dyadic_ceiling: {numerator: (2n * b).toString(), denominator: (1n << BigInt(L)).toString(), strict_less_than_one: true},
    beatty_pair: '(n,a) = (S[k],S[k+1]) for every k >= certified_start_k',
  };

  function product(left, right) {
    const row = [0n, 0n, 0n, 0n, 0n];
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) row[i + j] += left[i] * right[j];
    }
    // x^3 = m*x^2 - (m-1)*x + 1; reduce highest degree first.
    for (let degree = 4; degree >= 3; degree--) {
      const coefficient = row[degree];
      row[degree - 1] += b * coefficient;
      row[degree - 2] -= M * coefficient;
      row[degree - 3] += coefficient;
      row[degree] = 0n;
    }
    stats.polynomial_products++;
    return row.slice(0, 3);
  }

  function ensurePowers(k) {
    while (2 ** powers.length <= k) {
      powers.push(product(powers[powers.length - 1], powers[powers.length - 1]));
      stats.power_squares_built++;
    }
  }

  function trace(k) {
    boundedInteger(k, 'trace index', 0, LIMITS.max_trace_index);
    if (traces.has(k)) {
      stats.trace_cache_hits++;
      return traces.get(k).value;
    }
    if (traces.size >= LIMITS.max_trace_records) {
      throw new RangeError('Retained trace-record cap reached; export the existing result');
    }
    ensurePowers(k);
    let remaining = k;
    let bit = 0;
    let coefficients = [1n, 0n, 0n];
    const powerBits = [];
    while (remaining > 0) {
      if (remaining % 2 === 1) {
        coefficients = product(coefficients, powers[bit]);
        stats.term_products++;
        powerBits.push(bit);
      }
      remaining = Math.floor(remaining / 2);
      bit++;
    }
    const value = coefficients[0] * seeds[0] + coefficients[1] * seeds[1] + coefficients[2] * seeds[2];
    if (value <= 0n) throw new Error('Exact trace is not positive');
    traces.set(k, {k, value, coefficients, power_bits: powerBits, kind: 'power-basis evaluation'});
    stats.trace_records_built++;
    return value;
  }

  function scaledPolynomial(numerator, denominator) {
    return numerator * numerator * numerator
      - b * numerator * numerator * denominator
      + M * numerator * denominator * denominator
      - denominator * denominator * denominator;
  }

  function certificate(k) {
    boundedInteger(k, 'constructed trace index', startK, maxK);
    if (certificates.has(k)) {
      stats.floor_certificate_cache_hits++;
      return certificates.get(k);
    }
    if (certificates.size >= LIMITS.max_floor_certificates) {
      throw new RangeError('Retained floor-certificate cap reached; export the existing result');
    }
    const n = trace(k);
    const a = trace(k + 1);
    const lowerSign = scaledPolynomial(a, n);
    const upperSign = scaledPolynomial(a + 1n, n);
    if (a < M * n || a + 1n > b * n || lowerSign >= 0n || upperSign <= 0n) {
      throw new Error('The exact rational floor bracket does not match the proved cubic family');
    }
    const row = {
      k, beatty_index: n.toString(), beatty_value: a.toString(),
      floor_witness: {
        lower_root_bound: {numerator: a.toString(), denominator: n.toString(), inclusive: false},
        upper_root_bound: {numerator: (a + 1n).toString(), denominator: n.toString(), inclusive: false},
        scaled_polynomial_at_lower: lowerSign.toString(),
        scaled_polynomial_at_upper: upperSign.toString(),
        polynomial_scale: 'denominator^3',
        increasing_polynomial_interval: [M.toString(), b.toString()],
        conclusion: 'a < alpha*n < a+1, hence a = floor(alpha*n)',
      },
      theorem_start_k: startK,
    };
    certificates.set(k, row);
    stats.floor_certificates_built++;
    return row;
  }

  function reserveQuery(operation) {
    if (queries.length >= LIMITS.max_queries) {
      throw new RangeError('Query-record cap reached; export the existing result');
    }
    const row = {id: queries.length + 1, operation, status: 'in_progress'};
    queries.push(row);
    return row;
  }

  function at(k) {
    return copy(certificate(k));
  }

  function firstValueAtLeast(value) {
    const targetText = positiveIntegerText(value, 'threshold');
    const target = BigInt(targetText);
    const record = reserveQuery('first_value_at_least');
    Object.assign(record, {threshold: targetText, domain: {first_k: startK, last_k: maxK}, probes: []});
    const observed = new Map();
    function observe(k) {
      if (observed.has(k)) return observed.get(k);
      const wasCached = traces.has(k + 1);
      const result = trace(k + 1);
      observed.set(k, result);
      record.probes.push({k, value: result.toString(),
        comparison: result < target ? 'below' : result === target ? 'equal' : 'above',
        trace_previously_cached: wasCached});
      return result;
    }
    try {
      let upper = startK;
      let lower = null;
      if (observe(upper) < target) {
        lower = startK;
        let step = 1;
        upper = Math.min(maxK, startK + step);
        while (observe(upper) < target) {
          if (upper === maxK) {
            Object.assign(record, {status: 'outside_index_limit', last_k: maxK,
              last_value: observed.get(maxK).toString()});
            return copy(record);
          }
          lower = upper;
          step *= 2;
          upper = Math.min(maxK, startK + step);
        }
        while (upper - lower > 1) {
          const middle = Math.floor((upper + lower) / 2);
          if (observe(middle) < target) lower = middle;
          else upper = middle;
        }
      }
      const found = certificate(upper);
      const predecessor = upper === startK ? null : {
        k: upper - 1,
        value: trace(upper).toString(),
      };
      if (BigInt(found.beatty_value) < target
          || (predecessor !== null && BigInt(predecessor.value) >= target)) {
        throw new Error('Exact threshold bracket failed');
      }
      Object.assign(record, {status: 'found', k: upper,
        beatty_index: found.beatty_index, value: found.beatty_value,
        predecessor, floor_certificate_k: upper,
        minimality_scope: 'constructed subsequence within the declared index domain'});
      return copy(record);
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  function window(start, count) {
    boundedInteger(start, 'window start', startK, maxK);
    boundedInteger(count, 'window count', 1, LIMITS.max_window);
    if (start + count - 1 > maxK) throw new RangeError('Window exceeds the declared trace-index domain');
    const record = reserveQuery('window');
    Object.assign(record, {start, count, certificate_indices: []});
    try {
      const rows = [];
      for (let k = start; k < start + count; k++) {
        rows.push(at(k));
        record.certificate_indices.push(k);
      }
      record.status = 'complete';
      return rows;
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  function snapshot() {
    return copy({
      schema: SCHEMA, m, limits: LIMITS,
      constructed_domain: {first_k: startK, last_k: maxK},
      proof, stats,
      power_rows: powers.map((row, bit) => ({bit, exponent: 2 ** bit, coefficients: row.map(String)})),
      trace_rows: [...traces.values()].sort((left, right) => left.k - right.k).map(row => ({
        k: row.k, value: row.value.toString(), coefficients: row.coefficients.map(String),
        power_bits: row.power_bits, kind: row.kind,
      })),
      floor_certificates: [...certificates.values()].sort((left, right) => left.k - right.k),
      queries,
    });
  }

  return Object.freeze({
    m, first_k: startK, last_k: maxK, at, firstValueAtLeast, window, snapshot,
    proof: () => copy(proof),
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {createCubicTraceIndex, LIMITS, SCHEMA};
}
