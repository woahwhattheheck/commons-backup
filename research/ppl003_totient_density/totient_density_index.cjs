'use strict';

// Exact finite-prime density bounds; no integer-prefix scan or period enumeration.
const SCHEMA = 'commons.ppl003.totient_density_index/v1';
const SCALE = 1000000000000n;
const LIMITS = Object.freeze({
  max_basis_primes: 15, max_sieve_limit: 100000, max_prime_records: 10000,
  max_atoms: 32768, max_retained_atom_rows: 65535, max_queries: 32,
  max_bound_records: 64, max_bound_terms: 131072, max_page: 64,
  max_decimal_digits: 128, max_snapshot_nodes: 1500000,
  max_snapshot_string_chars: 32000000,
});

function plain(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}
function fields(value, allowed, required) {
  plain(value, 'query');
  if (Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError('Expected fields: ' + allowed.join(', '));
  }
}
function integer(value, label, lower, upper) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)
      || value < lower || value > upper) {
    throw new RangeError(label + ' must be an integer in [' + lower + ', ' + upper + ']');
  }
  return value;
}
function natural(value, label, allowBigInt = false) {
  const text = allowBigInt && typeof value === 'bigint' ? value.toString() : value;
  if (typeof text !== 'string' || !/^(0|[1-9][0-9]*)$/.test(text)
      || text.length > LIMITS.max_decimal_digits) {
    throw new RangeError(label + ' must be a bounded canonical nonnegative decimal');
  }
  return BigInt(text);
}
function array(value, label, minimum, maximum) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    throw new RangeError(label + ' has an unsupported length');
  }
  return value;
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function boundedClone(value) {
  let nodes = 0;
  let chars = 0;
  function copy(item, depth) {
    if (++nodes > LIMITS.max_snapshot_nodes || depth > 24) {
      throw new RangeError('Snapshot structure cap exceeded');
    }
    if (item === null || typeof item === 'boolean') return item;
    if (typeof item === 'string') {
      chars += item.length;
      if (chars > LIMITS.max_snapshot_string_chars) throw new RangeError('Snapshot string cap exceeded');
      return item;
    }
    if (typeof item === 'number' && Number.isSafeInteger(item)) return item;
    if (Array.isArray(item)) return item.map(value => copy(value, depth + 1));
    plain(item, 'snapshot member');
    const result = {};
    for (const key of Object.keys(item)) {
      chars += key.length;
      if (chars > LIMITS.max_snapshot_string_chars) throw new RangeError('Snapshot string cap exceeded');
      Object.defineProperty(result, key, {
        value: copy(item[key], depth + 1), enumerable: true, writable: true, configurable: true,
      });
    }
    return result;
  }
  return copy(value, 0);
}
function ceilDiv(a, b) { return (a + b - 1n) / b; }
function gcd(a, b, stats) {
  while (b !== 0n) {
    const next = a % b;
    a = b; b = next;
    if (stats) stats.gcd_steps++;
  }
  return a;
}
function fraction(value, stats) {
  fields(value, ['numerator', 'denominator'], ['numerator', 'denominator']);
  const numerator = natural(value.numerator, 'threshold numerator', true);
  const denominator = natural(value.denominator, 'threshold denominator', true);
  if (denominator === 0n || numerator > denominator) {
    throw new RangeError('Threshold must be a rational in [0,1]');
  }
  const divisor = gcd(numerator, denominator, stats);
  return [numerator / divisor, denominator / divisor];
}
function fractionText(value) {
  return {numerator: value[0].toString(), denominator: value[1].toString()};
}
function freshStats() {
  return {
    sieve_runs: 0, sieve_mark_visits: 0, prime_tail_terms_created: 0,
    versions_created: 0, atom_rows_created: 0, merge_comparisons: 0,
    prefix_mass_additions: 0, gcd_steps: 0, cdf_comparisons: 0,
    bounds_computed: 0, bound_cache_hits: 0, upper_terms_evaluated: 0,
    source_atom_rows_copied: 0, source_bound_records_copied: 0,
    source_bound_terms_copied: 0, integer_totients_evaluated: 0,
    primorial_residues_enumerated: 0,
  };
}

function primeTable(limit, stats) {
  const composite = new Uint8Array(limit + 1);
  const primes = [];
  stats.sieve_runs++;
  for (let p = 2; p <= limit; p++) {
    if (composite[p]) continue;
    primes.push(p);
    if (primes.length > LIMITS.max_prime_records) throw new RangeError('Prime record cap exceeded');
    for (let multiple = p * p; multiple <= limit; multiple += p) {
      composite[multiple] = 1;
      stats.sieve_mark_visits++;
    }
  }
  const terms = primes.map(p => {
    stats.prime_tail_terms_created++;
    return ceilDiv(SCALE, BigInt(p) * BigInt(p));
  });
  const suffix = new Array(primes.length + 1);
  suffix[primes.length] = ceilDiv(SCALE, BigInt(limit));
  for (let i = primes.length - 1; i >= 0; i--) suffix[i] = suffix[i + 1] + terms[i];
  return {limit, primes, terms, suffix};
}

// Each atom row is [subset mask, ratio numerator, ratio denominator,
// integer CRT weight, cumulative CRT weight]. Ratios are reduced and sorted.
function appendCore(state) {
  const old = state.versions[state.versions.length - 1];
  if (old.basis_count >= LIMITS.max_basis_primes) throw new RangeError('Prime-basis cap reached');
  const prime = state.table.primes[old.basis_count];
  if (prime === undefined) throw new Error('Recorded prime table has no next basis prime');
  const count = old.rows.length * 2;
  if (count > LIMITS.max_atoms || state.totalRows + count > LIMITS.max_retained_atom_rows) {
    throw new RangeError('Retained atom cap reached');
  }
  const p = BigInt(prime), bit = 2 ** old.basis_count;
  const absent = [], present = [];
  for (const row of old.rows) {
    absent.push([row[0], row[1], row[2], row[3] * (p - 1n), 0n]);
    const n = row[1] * (p - 1n), d = row[2] * p;
    const divisor = gcd(n, d, state.stats);
    present.push([row[0] + bit, n / divisor, d / divisor, row[3], 0n]);
    state.stats.atom_rows_created += 2;
  }
  const rows = [];
  let a = 0, b = 0, cumulative = 0n;
  while (a < absent.length || b < present.length) {
    let row;
    if (a === absent.length) row = present[b++];
    else if (b === present.length) row = absent[a++];
    else {
      const left = absent[a][1] * present[b][2];
      const right = present[b][1] * absent[a][2];
      state.stats.merge_comparisons++;
      if (left === right) throw new Error('Distinct prime-subset ratios unexpectedly coincide');
      row = left < right ? absent[a++] : present[b++];
    }
    cumulative += row[3];
    state.stats.prefix_mass_additions++;
    row[4] = cumulative;
    rows.push(row);
  }
  const denominator = old.denominator * p;
  if (cumulative !== denominator) throw new Error('Constructed CRT weights do not sum to their period');
  const version = {basis_count: old.basis_count + 1, prime, denominator, rows};
  state.versions.push(version);
  state.totalRows += rows.length;
  state.stats.versions_created++;
  return version;
}

function publicIndex(state) {
  function active() { return state.versions[state.versions.length - 1]; }
  function runQuery(operation, input, work) {
    if (state.queries.length >= LIMITS.max_queries) throw new RangeError('Query cap reached; export the snapshot');
    const record = {
      id: state.queries.length + 1, operation, input: clone(input),
      source_version: active().basis_count, status: 'in_progress',
    };
    state.queries.push(record);
    try {
      const result = work();
      Object.assign(record, {status: 'complete'}, result.trace);
      return clone(result.value);
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }
  function closedCdfRow(version, c) {
    let low = 0, high = version.rows.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      const row = version.rows[middle];
      state.stats.cdf_comparisons++;
      if (row[1] * c[1] <= c[0] * row[2]) low = middle + 1;
      else high = middle;
    }
    return low;
  }
  function boundRecord(c) {
    const version = active();
    const key = version.basis_count + ':' + c[0] + '/' + c[1];
    if (state.bounds.has(key)) {
      state.stats.bound_cache_hits++;
      return state.bounds.get(key);
    }
    if (state.bounds.size >= LIMITS.max_bound_records) throw new RangeError('Bound record cap reached');
    const rowCount = closedCdfRow(version, c);
    const zeroEndpoint = c[0] === 0n;
    const needed = zeroEndpoint ? 0 : version.rows.length - rowCount;
    if (state.termCount + needed > LIMITS.max_bound_terms) throw new RangeError('Bound contribution cap reached');
    const lowerWeight = rowCount === 0 ? 0n : version.rows[rowCount - 1][4];
    const tail = state.table.suffix[version.basis_count];
    let upperWeight = lowerWeight * SCALE;
    let capped = 0, rounded = 0;
    const contributions = [];
    if (!zeroEndpoint) {
      for (let i = rowCount; i < version.rows.length; i++) {
        const row = version.rows[i];
        const gap = row[1] * c[1] - c[0] * row[2];
        const numerator = row[3] * tail * row[1] * c[1];
        const maximum = row[3] * SCALE;
        let units;
        if (numerator >= maximum * gap) {
          units = maximum;
          capped++;
        } else {
          units = ceilDiv(numerator, gap);
          if (numerator % gap !== 0n) rounded++;
        }
        contributions.push([i, units.toString()]);
        upperWeight += units;
        state.stats.upper_terms_evaluated++;
      }
    }
    const record = {
      key, basis_count: version.basis_count,
      threshold: fractionText(c), kind: zeroEndpoint ? 'exact_zero_endpoint' : 'conditional_tail',
      at_or_below_rows: rowCount, lower_weight: lowerWeight.toString(),
      upper_scaled_weight: upperWeight.toString(), tail_scaled: tail.toString(),
      capped_terms: capped, rounded_terms: rounded, upper_contributions: contributions,
    };
    state.bounds.set(key, record);
    state.termCount += contributions.length;
    state.stats.bounds_computed++;
    return record;
  }
  function boundValue(record) {
    const version = state.versions[record.basis_count];
    return {
      key: record.key, basis_count: version.basis_count, cutoff_prime: version.prime,
      threshold: record.threshold, kind: record.kind,
      lower: {numerator: record.lower_weight, denominator: version.denominator.toString()},
      upper: {numerator: record.upper_scaled_weight, denominator: (version.denominator * SCALE).toString()},
      tail_bound: {numerator: record.tail_scaled, denominator: SCALE.toString()},
      at_or_below_rows: record.at_or_below_rows,
      above_rows: version.rows.length - record.at_or_below_rows,
      capped_terms: record.capped_terms, rounded_terms: record.rounded_terms,
      upper_contributions: record.upper_contributions,
    };
  }

  function bound(query) {
    const c = fraction(query, state.stats);
    return runQuery('bound', fractionText(c), () => {
      const record = boundRecord(c);
      return {value: boundValue(record), trace: {bound_key: record.key}};
    });
  }
  function interval(query) {
    fields(query, ['lower', 'upper'], ['lower', 'upper']);
    const lower = fraction(query.lower, state.stats);
    const upper = fraction(query.upper, state.stats);
    if (lower[0] * upper[1] >= upper[0] * lower[1]) {
      throw new RangeError('Interval requires 0 <= lower < upper <= 1');
    }
    return runQuery('interval', {lower: fractionText(lower), upper: fractionText(upper)}, () => {
      const left = boundRecord(lower), right = boundRecord(upper);
      const version = active(), denominator = version.denominator * SCALE;
      const rawLower = BigInt(right.lower_weight) * SCALE - BigInt(left.upper_scaled_weight);
      const rawUpper = BigInt(right.upper_scaled_weight) - BigInt(left.lower_weight) * SCALE;
      const lowerUnits = rawLower < 0n ? 0n : rawLower;
      const upperUnits = rawUpper > denominator ? denominator : rawUpper;
      const value = {
        basis_count: version.basis_count,
        event: 'lower <= phi(n)/n < upper',
        endpoints: {lower: fractionText(lower), upper: fractionText(upper)},
        lower: {numerator: lowerUnits.toString(), denominator: denominator.toString()},
        upper: {numerator: upperUnits.toString(), denominator: denominator.toString()},
        bound_keys: [left.key, right.key],
      };
      return {value, trace: {bound_keys: value.bound_keys}};
    });
  }
  function atomPage(query) {
    fields(query, ['offset', 'limit'], []);
    const version = active();
    const offset = integer(query.offset === undefined ? 0 : query.offset, 'offset', 0, version.rows.length);
    const limit = integer(query.limit === undefined ? 16 : query.limit, 'limit', 1, LIMITS.max_page);
    return runQuery('atom_page', {offset, limit}, () => {
      const end = Math.min(version.rows.length, offset + limit);
      const rows = [];
      for (let index = offset; index < end; index++) {
        const row = version.rows[index];
        rows.push({
          row: index, subset_mask: row[0],
          primes_dividing: state.table.primes.slice(0, version.basis_count)
            .filter((_, bit) => (row[0] & 2 ** bit) !== 0),
          ratio: {numerator: row[1].toString(), denominator: row[2].toString()},
          weight: row[3].toString(), cumulative_weight: row[4].toString(),
          probability_denominator: version.denominator.toString(),
        });
      }
      const value = {
        basis_count: version.basis_count, offset, limit, total_rows: version.rows.length,
        next_offset: end < version.rows.length ? end : null, rows,
      };
      return {value, trace: {offset, returned_rows: rows.length, next_offset: value.next_offset}};
    });
  }
  function appendNextPrime() {
    if (arguments.length !== 0) throw new TypeError('appendNextPrime takes no arguments');
    return runQuery('append_next_prime', {}, () => {
      const previous = active(), version = appendCore(state);
      const value = {
        previous_basis_count: previous.basis_count, added_prime: version.prime,
        basis_count: version.basis_count, previous_rows: previous.rows.length,
        new_rows: version.rows.length, previous_denominator: previous.denominator.toString(),
        denominator: version.denominator.toString(), retained_old_versions: state.versions.length - 1,
        sieve_runs_added: 0, old_atom_rows_reconstructed: 0,
      };
      return {value, trace: {added_prime: version.prime, resulting_version: version.basis_count}};
    });
  }
  function summary() {
    const version = active();
    return clone({
      schema: SCHEMA, origin: state.origin, basis_count: version.basis_count,
      cutoff_prime: version.prime, denominator: version.denominator.toString(),
      atom_rows: version.rows.length, retained_versions: state.versions.length,
      retained_atom_rows: state.totalRows, sieve_limit: state.table.limit,
      prime_records: state.table.primes.length, bound_records: state.bounds.size,
      retained_bound_terms: state.termCount, retained_queries: state.queries.length,
      stats: state.stats, imported_summary: state.importedSummary,
      derivative_question: 'Not resolved by finite-prime CDF enclosures.',
    });
  }
  function snapshot() {
    return clone({
      schema: SCHEMA, scale: SCALE.toString(), limits: LIMITS, summary: summary(),
      prime_table: {
        sieve_limit: state.table.limit, primes: state.table.primes,
        ceiling_terms: state.table.terms.map(value => value.toString()),
        suffix_units: state.table.suffix.map(value => value.toString()),
      },
      versions: state.versions.map(version => ({
        basis_count: version.basis_count, prime: version.prime,
        denominator: version.denominator.toString(),
        rows: version.rows.map(row => [row[0], ...row.slice(1).map(value => value.toString())]),
      })),
      bounds: [...state.bounds.values()], queries: state.queries,
      provenance: 'Restoration checks structure; it does not authenticate a source or re-prove its arithmetic.',
    });
  }
  return Object.freeze({schema: SCHEMA, bound, interval, atomPage, appendNextPrime, summary, snapshot});
}

function createTotientDensityIndex(options = {}) {
  fields(options, ['primeCount', 'sieveLimit'], []);
  const count = integer(options.primeCount === undefined ? 10 : options.primeCount,
    'primeCount', 1, LIMITS.max_basis_primes);
  const limit = integer(options.sieveLimit === undefined ? 4096 : options.sieveLimit,
    'sieveLimit', 53, LIMITS.max_sieve_limit);
  const stats = freshStats();
  const table = primeTable(limit, stats);
  const state = {
    origin: 'constructed', importedSummary: null, table,
    versions: [{basis_count: 0, prime: null, denominator: 1n, rows: [[0, 1n, 1n, 1n, 1n]]}],
    totalRows: 1, bounds: new Map(), termCount: 0, queries: [], stats,
  };
  stats.versions_created = 1;
  stats.atom_rows_created = 1;
  for (let i = 0; i < count; i++) appendCore(state);
  return publicIndex(state);
}

function openTotientDensityIndex(input) {
  const saved = boundedClone(input);
  plain(saved, 'snapshot');
  if (saved.schema !== SCHEMA || saved.scale !== SCALE.toString()) {
    throw new TypeError('Unsupported saved index schema or scale');
  }
  const originalTable = plain(saved.prime_table, 'prime table');
  const limit = integer(originalTable.sieve_limit, 'sieve limit', 53, LIMITS.max_sieve_limit);
  const primes = array(originalTable.primes, 'prime list', 16, LIMITS.max_prime_records);
  for (let i = 0; i < primes.length; i++) {
    integer(primes[i], 'recorded prime', 2, limit);
    if (i > 0 && primes[i] <= primes[i - 1]) throw new Error('Recorded primes must increase strictly');
  }
  const terms = array(originalTable.ceiling_terms, 'prime ceiling terms', primes.length, primes.length)
    .map(value => natural(value, 'recorded ceiling term'));
  const suffix = array(originalTable.suffix_units, 'tail suffix units', primes.length + 1, primes.length + 1)
    .map(value => natural(value, 'recorded tail suffix'));
  if (terms.some(value => value === 0n) || suffix.some(value => value === 0n)) {
    throw new Error('Recorded tail terms must be positive');
  }
  const originalVersions = array(saved.versions, 'versions', 2, LIMITS.max_basis_primes + 1);
  let totalRows = 0;
  const versions = originalVersions.map((original, basis) => {
    plain(original, 'version');
    if (original.basis_count !== basis
        || original.prime !== (basis === 0 ? null : primes[basis - 1])) {
      throw new Error('Recorded version headers are inconsistent');
    }
    const denominator = natural(original.denominator, 'recorded CRT denominator');
    if (denominator === 0n) throw new Error('CRT denominator must be positive');
    const rawRows = array(original.rows, 'atom rows', 2 ** basis, 2 ** basis);
    totalRows += rawRows.length;
    if (totalRows > LIMITS.max_retained_atom_rows) throw new RangeError('Recorded atom row cap exceeded');
    const masks = new Set();
    const rows = rawRows.map((raw, index) => {
      array(raw, 'atom row', 5, 5);
      const mask = integer(raw[0], 'subset mask', 0, 2 ** basis - 1);
      if (masks.has(mask)) throw new Error('Duplicate source subset mask');
      masks.add(mask);
      const n = natural(raw[1], 'recorded ratio numerator');
      const d = natural(raw[2], 'recorded ratio denominator');
      const weight = natural(raw[3], 'recorded integer weight');
      const cumulative = natural(raw[4], 'recorded cumulative weight');
      if (n === 0n || d === 0n || n > d || weight === 0n || weight > denominator
          || cumulative === 0n || cumulative > denominator) {
        throw new Error('Recorded atom bounds are invalid');
      }
      if (index > 0) {
        const previous = rawRows[index - 1];
        if (BigInt(previous[1]) * d >= n * BigInt(previous[2])
            || BigInt(previous[4]) >= cumulative) {
          throw new Error('Recorded atom order or cumulative weights do not increase');
        }
      }
      return [mask, n, d, weight, cumulative];
    });
    if (rows[rows.length - 1][4] !== denominator) throw new Error('Final recorded mass must equal its denominator');
    return {basis_count: basis, prime: original.prime, denominator, rows};
  });
  const sourceBounds = array(saved.bounds, 'saved bounds', 0, LIMITS.max_bound_records);
  const bounds = new Map();
  let termCount = 0;
  for (const original of sourceBounds) {
    plain(original, 'saved bound');
    const basis = integer(original.basis_count, 'bound basis', 1, versions.length - 1);
    const version = versions[basis];
    const threshold = plain(original.threshold, 'saved threshold');
    const n = natural(threshold.numerator, 'saved threshold numerator');
    const d = natural(threshold.denominator, 'saved threshold denominator');
    if (d === 0n || n > d) throw new Error('Saved threshold is outside [0,1]');
    const key = basis + ':' + n + '/' + d;
    if (original.key !== key || bounds.has(key)) throw new Error('Invalid or duplicate saved bound key');
    if (!['conditional_tail', 'exact_zero_endpoint'].includes(original.kind)) {
      throw new TypeError('Unsupported saved bound kind');
    }
    const cut = integer(original.at_or_below_rows, 'CDF boundary row', 0, version.rows.length);
    const lower = natural(original.lower_weight, 'saved lower weight');
    const upper = natural(original.upper_scaled_weight, 'saved upper weight');
    const tail = natural(original.tail_scaled, 'saved tail bound');
    if (lower > version.denominator || upper < lower * SCALE || upper > version.denominator * SCALE
        || tail === 0n || tail !== suffix[basis]) {
      throw new Error('Saved probability or tail bounds are inconsistent');
    }
    const needed = original.kind === 'exact_zero_endpoint' ? 0 : version.rows.length - cut;
    const contributions = array(original.upper_contributions, 'saved contributions', needed, needed);
    for (let i = 0; i < contributions.length; i++) {
      const row = array(contributions[i], 'saved contribution', 2, 2);
      if (row[0] !== cut + i) throw new Error('Saved contribution row sequence is inconsistent');
      const units = natural(row[1], 'saved contribution units');
      if (units > version.rows[row[0]][3] * SCALE) throw new Error('Saved contribution exceeds atom mass');
    }
    integer(original.capped_terms, 'capped term count', 0, contributions.length);
    integer(original.rounded_terms, 'rounded term count', 0, contributions.length);
    termCount += contributions.length;
    if (termCount > LIMITS.max_bound_terms) throw new RangeError('Saved contribution cap exceeded');
    bounds.set(key, original);
  }
  const queries = array(saved.queries, 'saved queries', 0, LIMITS.max_queries);
  queries.forEach((query, index) => {
    plain(query, 'saved query');
    if (query.id !== index + 1 || !['bound', 'interval', 'atom_page', 'append_next_prime'].includes(query.operation)
        || !['complete', 'incomplete'].includes(query.status)) {
      throw new Error('Saved query header is inconsistent');
    }
    integer(query.source_version, 'query source version', 1, versions.length - 1);
  });
  const stats = freshStats();
  stats.source_atom_rows_copied = totalRows;
  stats.source_bound_records_copied = bounds.size;
  stats.source_bound_terms_copied = termCount;
  const state = {
    origin: 'restored_structural_only',
    importedSummary: saved.summary === undefined ? null : saved.summary,
    table: {limit, primes, terms, suffix}, versions, totalRows, bounds, termCount, queries, stats,
  };
  return publicIndex(state);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    createTotientDensityIndex, openTotientDensityIndex,
    SCHEMA, SCALE: SCALE.toString(), LIMITS,
  };
}
