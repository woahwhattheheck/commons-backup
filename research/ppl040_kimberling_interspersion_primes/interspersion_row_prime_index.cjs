"use strict";

/**
 * Exact finite prime classifications in Kimberling's triangular-number array.
 * T(r,c) = r + (r+c-2)(r+c-1)/2, with r,c >= 1.
 * Saved loading checks structure, not the arithmetic provenance of its premise.
 */
const INTERSPERSION_ROW_LIMITS = Object.freeze({
  max_prime_basis_limit: 65536,
  max_value: 4294967296,
  max_columns: 20000,
  max_segments: 16,
  parameter_digits: 16,
  query_digits: 1000,
  max_page_size: 128,
  source_id_chars: 512
});
const SCHEMA = "commons.kimberling15.row_prime_index/v1";
function fail(message) { throw new TypeError(message); }
function object(x, name) {
  if (!x || typeof x !== "object" || Array.isArray(x)) fail(name + " must be an object");
  return x;
}
function array(x, cap, name) {
  if (!Array.isArray(x) || x.length > cap) fail(name + " exceeds its array contract");
  return x;
}
function small(x, lo, hi, name) {
  if (!Number.isInteger(x) || x < lo || x > hi) fail(name + " must be a bounded integer");
  return x;
}
function natural(x, digits, positive, name) {
  let s;
  if (typeof x === "bigint") s = x.toString();
  else if (typeof x === "number" && Number.isSafeInteger(x)) s = String(x);
  else if (typeof x === "string") s = x;
  else fail(name + " must be an exact integer");
  if (!/^(0|[1-9][0-9]*)$/.test(s) || s.length > digits) fail(name + " exceeds its integer contract");
  const n = BigInt(s);
  if (positive && n === 0n) fail(name + " must be positive");
  return n;
}
function sourceId(x) {
  if (typeof x !== "string" || !x.length || x.length > INTERSPERSION_ROW_LIMITS.source_id_chars)
    fail("source_id must be a nonempty bounded string");
  return x;
}
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function mod(x, p) { const r = x % p; return r < 0 ? r + p : r; }
function exactValue(row, column) {
  const s = row + column - 2n;
  return row + s * (s + 1n) / 2n;
}
function integerSquareRoot(n) {
  let r = Math.floor(Math.sqrt(n));
  while ((r + 1) * (r + 1) <= n) r++;
  while (r * r > n) r--;
  return r;
}
function freshWork(mode) {
  return { mode, compiler_calls: 0, append_requests: 0,
    prime_bases_constructed: 0, basis_candidate_positions: 0,
    basis_mark_visits: 0, basis_composites_marked: 0,
    local_rules_constructed: 0, modular_power_calls: 0,
    modular_multiply_calls: 0, nonresidue_candidates: 0,
    square_root_order_reductions: 0,
    row_value_initializations: 0, row_value_recurrence_steps: 0,
    columns_sieved: 0, rule_visits: 0, residue_progressions: 0,
    progression_hits: 0, composite_records_assigned: 0,
    earlier_divisor_hits_skipped: 0, basis_prime_self_hits: 0,
    retained_basis_entries_reused: 0, retained_rules_reused: 0,
    retained_column_records_reused: 0,
    structural_basis_entries: 0, structural_prime_references: 0,
    structural_rule_rows: 0, structural_column_records: 0,
    structural_segment_rule_rows: 0,
    query_calls: 0, query_binary_search_steps: 0, query_records_returned: 0 };
}
function compileBasis(limit, work) {
  const least = new Uint32Array(limit + 1), primes = [];
  least[1] = 1; work.prime_bases_constructed++;
  for (let n = 2; n <= limit; n++) {
    work.basis_candidate_positions++;
    if (least[n] !== 0) continue;
    least[n] = n; primes.push(n);
    if (n * n <= limit) for (let j = n * n; j <= limit; j += n) {
      work.basis_mark_visits++;
      if (least[j] === 0) { least[j] = n; work.basis_composites_marked++; }
    }
  }
  return { limit, primes, least_factor_by_integer: Array.from(least) };
}
function multiplyMod(a, b, p, work) {
  work.modular_multiply_calls++;
  return (a * b) % p;
}
function powerMod(a, exponent, p, work) {
  work.modular_power_calls++;
  let answer = 1, b = a, e = exponent;
  while (e > 0) {
    if (e % 2) answer = multiplyMod(answer, b, p, work);
    e = Math.floor(e / 2);
    if (e > 0) b = multiplyMod(b, b, p, work);
  }
  return answer;
}
// For a nonzero quadratic residue modulo an odd prime.
// Repeatedly reduce the 2-power order of t while preserving x^2 = a*t.
function nonzeroSquareRoot(a, p, work) {
  if (p % 4 === 3) return { root: powerMod(a, (p + 1) / 4, p, work),
    method: "p_mod_4_eq_3", nonresidue: null };
  let q = p - 1, s = 0;
  while (q % 2 === 0) { q /= 2; s++; }
  let z = 2;
  while (z < p) {
    work.nonresidue_candidates++;
    if (powerMod(z, (p - 1) / 2, p, work) === p - 1) break;
    z++;
  }
  if (z === p) throw new Error("prime-basis premise has no quadratic nonresidue");
  let c = powerMod(z, q, p, work);
  let x = powerMod(a, (q + 1) / 2, p, work);
  let t = powerMod(a, q, p, work), m = s;
  while (t !== 1) {
    let i = 0, tt = t;
    while (tt !== 1 && i < m) { tt = multiplyMod(tt, tt, p, work); i++; }
    if (i === 0 || i >= m) throw new Error("quadratic-residue order invariant failed");
    const b = powerMod(c, 2 ** (m - i - 1), p, work);
    x = multiplyMod(x, b, p, work);
    c = multiplyMod(b, b, p, work);
    t = multiplyMod(t, c, p, work);
    m = i; work.square_root_order_reductions++;
  }
  return { root: x, method: "two_power_order_reduction", nonresidue: z };
}
function compileRules(row, basis, work) {
  return basis.primes.map((p, index) => {
    work.local_rules_constructed++;
    if (p === 2) {
      const residues = [];
      for (let c = 0; c < 4; c++) {
        const s = mod(row + c - 2, 4);
        if ((s * (s + 1) / 2 + row) % 2 === 0) residues.push(c);
      }
      return { prime_index: index, prime: p, period: 4, column_residues: residues,
        discriminant_mod_prime: null, euler_value: null, square_root: null,
        method: "period_four", nonresidue: null };
    }
    const d = mod(1 - 8 * row, p);
    const euler = d === 0 ? 0 : powerMod(d, (p - 1) / 2, p, work);
    if (euler === p - 1) return { prime_index: index, prime: p, period: p,
      column_residues: [], discriminant_mod_prime: d, euler_value: euler,
      square_root: null, method: "nonresidue", nonresidue: null };
    if (euler !== 0 && euler !== 1) throw new Error("Euler criterion contradicts the prime-basis premise");
    const answer = d === 0 ? { root: 0, method: "zero", nonresidue: null } :
      nonzeroSquareRoot(d, p, work);
    const roots = d === 0 ? [0] : [answer.root, p - answer.root];
    const residues = roots.map(u => {
      const s = multiplyMod(mod(u - 1, p), (p + 1) / 2, p, work);
      return mod(s - row + 2, p);
    }).sort((a, b) => a - b);
    return { prime_index: index, prime: p, period: p, column_residues: residues,
      discriminant_mod_prime: d, euler_value: euler, square_root: answer.root,
      method: answer.method, nonresidue: answer.nonresidue };
  });
}
function capState(row, first, last, basisLimit, segmentCount) {
  const L = INTERSPERSION_ROW_LIMITS;
  if (last < first) fail("last_column precedes first_column");
  const count = last - first + 1n;
  const maximum = exactValue(row, last);
  const common = { row: row.toString(), first_column: first.toString(), last_column: last.toString(),
    requested_columns: count.toString(), maximum_value: maximum.toString(), prime_basis_limit: basisLimit };
  if (count > BigInt(L.max_columns))
    return Object.assign({ status: "CAP_STOP", reason: "COLUMN_COUNT_CAP", cap: L.max_columns }, common);
  if (segmentCount > L.max_segments)
    return Object.assign({ status: "CAP_STOP", reason: "SEGMENT_COUNT_CAP", cap: L.max_segments }, common);
  if (maximum > BigInt(L.max_value))
    return Object.assign({ status: "CAP_STOP", reason: "VALUE_CAP", cap: String(L.max_value) }, common);
  const root = integerSquareRoot(Number(maximum));
  if (basisLimit < root)
    return Object.assign({ status: "CAP_STOP", reason: "BASIS_COVERAGE",
      required_floor_square_root: root }, common);
  return null;
}
// Record layout: [column, value, least_prime_divisor_or_zero, quotient_or_zero, rule_index_or_minus_one].
// Value 1 is a unit; every other unmarked value is prime after complete basis coverage.
function sieveSegment(row, first, last, initialValue, rules, work) {
  const records = [], count = last - first + 1;
  let value = initialValue, difference = row + first - 1;
  work.row_value_initializations++;
  for (let i = 0; i < count; i++) {
    records.push([first + i, value, 0, 0, -1]);
    if (i + 1 < count) { value += difference; difference++; work.row_value_recurrence_steps++; }
  }
  work.columns_sieved += count;
  const ruleUsage = [];
  for (let ri = 0; ri < rules.length; ri++) {
    const rule = rules[ri], p = rule.prime;
    let hits = 0, assigned = 0, self = 0;
    work.rule_visits++;
    for (const residue of rule.column_residues) {
      work.residue_progressions++;
      const initial = first + mod(residue - first, rule.period);
      for (let c = initial; c <= last; c += rule.period) {
        const rec = records[c - first];
        hits++; work.progression_hits++;
        if (rec[2] !== 0) { work.earlier_divisor_hits_skipped++; continue; }
        if (rec[1] === p) { self++; work.basis_prime_self_hits++; continue; }
        const quotient = rec[1] / p;
        if (!Number.isInteger(quotient) || quotient < 2)
          throw new Error("local residue hit has no proper integer quotient");
        rec[2] = p; rec[3] = quotient; rec[4] = ri;
        assigned++; work.composite_records_assigned++;
      }
    }
    ruleUsage.push([ri, hits, assigned, self]);
  }
  const primeIndices = [];
  let composites = 0, units = 0, firstComposite = null, lastComposite = null;
  for (let i = 0; i < records.length; i++) {
    const rec = records[i];
    if (rec[1] === 1) units++;
    else if (rec[2] === 0) primeIndices.push(i);
    else { composites++; if (firstComposite === null) firstComposite = rec[0]; lastComposite = rec[0]; }
  }
  const segment = { first_column: first, last_column: last, first_value: records[0][1],
    last_value: records[records.length - 1][1], column_count: count,
    prime_count: primeIndices.length, composite_count: composites, unit_count: units,
    first_composite_column: firstComposite, last_composite_column: lastComposite,
    rule_usage: ruleUsage };
  return { records, primeIndices, segment };
}
function initialSummary(records, primeIndices, segment) {
  return { column_count: records.length, prime_count: primeIndices.length,
    composite_count: segment.composite_count, unit_count: segment.unit_count,
    first_prime_column: primeIndices.length ? records[primeIndices[0]][0] : null,
    last_prime_column: primeIndices.length ? records[primeIndices[primeIndices.length - 1]][0] : null,
    first_composite_column: segment.first_composite_column,
    last_composite_column: segment.last_composite_column,
    conclusion: "exact classifications in the recorded finite column interval; no row-infinitude claim" };
}
function validateSaved(raw, work) {
  const L = INTERSPERSION_ROW_LIMITS, state = copy(object(raw, "saved state"));
  if (state.schema !== SCHEMA) fail("unsupported saved schema");
  sourceId(state.source_id);
  if (state.parent_source_id !== null) sourceId(state.parent_source_id);
  const row = small(state.row, 1, L.max_value, "row");
  const interval = object(state.interval, "interval");
  const first = small(interval.first_column, 1, L.max_value, "first column");
  const last = small(interval.last_column, first, L.max_value, "last column");
  const count = last - first + 1;
  if (count > L.max_columns) fail("saved column count exceeds cap");
  const basis = object(state.basis, "basis");
  const limit = small(basis.limit, 2, L.max_prime_basis_limit, "basis limit");
  const least = array(basis.least_factor_by_integer, limit + 1, "basis least factors");
  if (least.length !== limit + 1 || least[0] !== 0 || least[1] !== 1) fail("saved basis endpoints differ");
  const primes = array(basis.primes, limit, "basis primes"), primeSet = new Set();
  let previousPrime = 1;
  for (const p of primes) {
    small(p, 2, limit, "saved prime");
    if (p <= previousPrime) fail("saved prime list must be strictly increasing");
    previousPrime = p; primeSet.add(p); work.structural_prime_references++;
  }
  if (!primes.length || primes[0] !== 2) fail("saved prime basis must begin with 2");
  for (let n = 2; n <= limit; n++) {
    const factor = small(least[n], 2, n, "saved basis factor");
    if ((factor === n) !== primeSet.has(n) || !primeSet.has(factor))
      fail("saved basis prime/factor references differ");
  }
  work.structural_basis_entries += least.length;
  const rules = array(state.rules, primes.length, "rules");
  if (rules.length !== primes.length) fail("saved rule list must cover the prime basis");
  for (let i = 0; i < rules.length; i++) {
    const rule = object(rules[i], "rule"), p = primes[i];
    if (rule.prime_index !== i || rule.prime !== p || rule.period !== (p === 2 ? 4 : p))
      fail("saved rule identity differs");
    const residues = array(rule.column_residues, 2, "column residues");
    let prev = -1;
    for (const c of residues) {
      small(c, 0, rule.period - 1, "column residue");
      if (c <= prev) fail("saved residues must be strictly increasing");
      prev = c;
    }
    if (p === 2) {
      if (residues.length !== 2 || rule.method !== "period_four" ||
          rule.discriminant_mod_prime !== null || rule.euler_value !== null ||
          rule.square_root !== null || rule.nonresidue !== null) fail("saved period-four shape differs");
    } else {
      small(rule.discriminant_mod_prime, 0, p - 1, "saved discriminant");
      if (rule.euler_value === 0) {
        if (rule.discriminant_mod_prime !== 0 || rule.square_root !== 0 ||
            residues.length !== 1 || rule.method !== "zero" || rule.nonresidue !== null)
          fail("saved zero-root shape differs");
      } else if (rule.euler_value === p - 1) {
        if (rule.discriminant_mod_prime === 0 || rule.square_root !== null ||
            residues.length !== 0 || rule.method !== "nonresidue" || rule.nonresidue !== null)
          fail("saved nonresidue shape differs");
      } else if (rule.euler_value === 1) {
        small(rule.discriminant_mod_prime, 1, p - 1, "nonzero saved discriminant");
        small(rule.square_root, 1, p - 1, "saved square root");
        if (residues.length !== 2) fail("saved nonzero root must have two column residues");
        if (rule.method === "p_mod_4_eq_3") {
          if (p % 4 !== 3 || rule.nonresidue !== null) fail("saved shortcut shape differs");
        } else if (rule.method === "two_power_order_reduction") {
          small(rule.nonresidue, 2, p - 1, "saved nonresidue reference");
        } else fail("unsupported saved root method");
      } else fail("unsupported saved Euler value");
    }
    work.structural_rule_rows++;
  }
  const records = array(state.records, L.max_columns, "column records");
  if (records.length !== count) fail("saved records do not cover the interval");
  let previousValue = 0, composites = 0, units = 0;
  const expectedPrimeIndices = [];
  for (let i = 0; i < records.length; i++) {
    const rec = array(records[i], 5, "column record");
    if (rec.length !== 5 || rec[0] !== first + i) fail("saved columns must be consecutive");
    small(rec[1], 1, L.max_value, "saved row value");
    if (rec[1] <= previousValue) fail("saved row values must be increasing");
    previousValue = rec[1];
    if (rec[2] === 0) {
      if (rec[3] !== 0 || rec[4] !== -1) fail("unmarked record has a factor reference");
      if (rec[1] === 1) units++; else expectedPrimeIndices.push(i);
    } else {
      small(rec[2], 2, Math.min(limit, rec[1] - 1), "saved proper divisor");
      small(rec[3], 2, rec[1] - 1, "saved quotient");
      small(rec[4], 0, rules.length - 1, "saved rule reference");
      if (rules[rec[4]].prime !== rec[2]) fail("saved divisor and rule differ");
      composites++;
    }
    work.structural_column_records++;
  }
  if (interval.first_value !== records[0][1] || interval.last_value !== records[records.length - 1][1])
    fail("saved interval endpoint values differ");
  const root = small(interval.required_floor_square_root, 0, limit, "required square root");
  // These inequalities bind coverage to the saved maximum, not to an unevaluated row formula.
  if (root * root > interval.last_value || (root + 1) * (root + 1) <= interval.last_value)
    fail("saved square-root coverage interval differs");
  const primeIndices = array(state.prime_record_indices, count, "prime indices");
  if (JSON.stringify(primeIndices) !== JSON.stringify(expectedPrimeIndices))
    fail("saved prime index disagrees with record tags");
  const summary = object(state.summary, "summary");
  if (summary.column_count !== count || summary.prime_count !== primeIndices.length ||
      summary.composite_count !== composites || summary.unit_count !== units)
    fail("saved summary counts differ");
  const expectedFirstPrime = primeIndices.length ? records[primeIndices[0]][0] : null;
  const expectedLastPrime = primeIndices.length ? records[primeIndices[primeIndices.length - 1]][0] : null;
  if (summary.first_prime_column !== expectedFirstPrime || summary.last_prime_column !== expectedLastPrime)
    fail("saved prime endpoints differ");
  for (const key of ["first_composite_column", "last_composite_column"]) {
    if (summary[key] !== null) {
      const c = small(summary[key], first, last, key);
      if (records[c - first][2] === 0) fail("saved composite endpoint is unmarked");
    }
  }
  const segments = array(state.segments, L.max_segments, "segments");
  if (!segments.length) fail("saved index needs at least one segment");
  let next = first;
  for (const segment of segments) {
    object(segment, "segment");
    if (segment.first_column !== next) fail("saved segments must be contiguous");
    small(segment.last_column, next, last, "segment last column");
    const length = segment.last_column - next + 1;
    if (segment.column_count !== length ||
        segment.prime_count + segment.composite_count + segment.unit_count !== length)
      fail("saved segment counts differ");
    for (const key of ["prime_count", "composite_count", "unit_count"])
      small(segment[key], 0, length, "segment " + key);
    if (segment.first_value !== records[next - first][1] ||
        segment.last_value !== records[segment.last_column - first][1]) fail("saved segment values differ");
    const usage = array(segment.rule_usage, rules.length, "segment rule usage");
    if (usage.length !== rules.length) fail("saved segment rule usage is incomplete");
    for (let i = 0; i < usage.length; i++) {
      const u = array(usage[i], 4, "rule usage row");
      if (u.length !== 4 || u[0] !== i) fail("saved rule usage order differs");
      small(u[1], 0, length, "rule hit count");
      small(u[2], 0, u[1], "new assignment count");
      small(u[3], 0, u[1], "prime self-hit count");
      work.structural_segment_rule_rows++;
    }
    next = segment.last_column + 1;
  }
  if (next !== last + 1) fail("saved segments do not cover the interval");
  return state;
}
function makeIndex(state, work) {
  const L = INTERSPERSION_ROW_LIMITS;
  function queryInteger(x, name) { return natural(x, L.query_digits, false, name); }
  function lowerPrime(column) {
    let a = 0, b = state.prime_record_indices.length;
    while (a < b) {
      const m = (a + b) >>> 1; work.query_binary_search_steps++;
      if (BigInt(state.records[state.prime_record_indices[m]][0]) < column) a = m + 1; else b = m;
    }
    return a;
  }
  function decoded(index, primeRank) {
    const rec = state.records[index]; work.query_records_returned++;
    const classification = rec[1] === 1 ? "UNIT" : rec[2] === 0 ? "PRIME" : "COMPOSITE";
    const out = { record_index: index, row: String(state.row), column: String(rec[0]),
      value: String(rec[1]), classification, source_id: state.source_id };
    if (classification === "COMPOSITE") {
      out.least_prime_divisor = rec[2]; out.quotient = String(rec[3]); out.rule_index = rec[4];
      out.rule = copy(state.rules[rec[4]]);
    } else if (classification === "PRIME") {
      out.basis_limit = state.basis.limit;
      out.coverage_floor_square_root = state.interval.required_floor_square_root;
      if (primeRank !== undefined) out.prime_rank = primeRank;
    }
    return out;
  }
  function pageLimit(n) { return small(n, 1, L.max_page_size, "page limit"); }
  return Object.freeze({
    summary() {
      return copy({ schema: SCHEMA, source_id: state.source_id, parent_source_id: state.parent_source_id,
        row: state.row, interval: state.interval, basis_limit: state.basis.limit,
        basis_prime_count: state.basis.primes.length, segment_count: state.segments.length,
        ...state.summary });
    },
    selectPrime(rank) {
      work.query_calls++;
      const r = queryInteger(rank, "prime rank"), available = state.prime_record_indices.length;
      if (r >= BigInt(available)) return { status: "OUT_OF_RANGE", requested_rank: r.toString(), available };
      return { status: "FOUND", record: decoded(state.prime_record_indices[Number(r)], Number(r)) };
    },
    rankPrime(column) {
      work.query_calls++;
      const c = queryInteger(column, "column");
      if (c < BigInt(state.interval.first_column) || c > BigInt(state.interval.last_column))
        return { status: "OUTSIDE_RETAINED_INTERVAL", column: c.toString(), interval: copy(state.interval) };
      const i = lowerPrime(c);
      if (i === state.prime_record_indices.length || BigInt(state.records[state.prime_record_indices[i]][0]) !== c)
        return { status: "NOT_PRIME", record: decoded(Number(c) - state.interval.first_column) };
      return { status: "FOUND", rank: i, record: decoded(state.prime_record_indices[i], i) };
    },
    countPrimesThrough(column) {
      work.query_calls++;
      const c = queryInteger(column, "column"), count = lowerPrime(c + 1n);
      return { first_retained_column: String(state.interval.first_column),
        last_retained_column: String(state.interval.last_column),
        requested_upper_column_inclusive: c.toString(), prime_count: count,
        scope: "only the retained interval; no count for omitted earlier or later columns" };
    },
    pagePrimes(startRank, limit) {
      work.query_calls++;
      const start = queryInteger(startRank, "prime rank"), cap = pageLimit(limit), records = [];
      const n = state.prime_record_indices.length;
      if (start < BigInt(n)) for (let i = Number(start); i < n && records.length < cap; i++)
        records.push(decoded(state.prime_record_indices[i], i));
      const next = start + BigInt(records.length);
      return { source_id: state.source_id, start_rank: start.toString(), records,
        next_rank: next.toString(), has_more: next < BigInt(n) };
    },
    recordAtColumn(column) {
      work.query_calls++;
      const c = queryInteger(column, "column");
      if (c < BigInt(state.interval.first_column) || c > BigInt(state.interval.last_column))
        return { status: "OUTSIDE_RETAINED_INTERVAL", column: c.toString(), interval: copy(state.interval) };
      return { status: "FOUND", record: decoded(Number(c) - state.interval.first_column) };
    },
    pageRecords(startColumn, limit) {
      work.query_calls++;
      const c = queryInteger(startColumn, "column"), cap = pageLimit(limit), records = [];
      const first = state.interval.first_column, last = state.interval.last_column;
      if (c < BigInt(first) || c > BigInt(last)) return { status: "OUTSIDE_RETAINED_INTERVAL",
        start_column: c.toString(), interval: copy(state.interval), records, has_more: false };
      for (let column = Number(c); column <= last && records.length < cap; column++)
        records.push(decoded(column - first));
      const next = c + BigInt(records.length);
      return { status: "FOUND", source_id: state.source_id, start_column: c.toString(), records,
        next_column: next.toString(), has_more: next <= BigInt(last) };
    },
    localRule(prime) {
      work.query_calls++;
      const p = small(prime, 2, state.basis.limit, "prime");
      const index = state.basis.primes.indexOf(p);
      return index < 0 ? { status: "NOT_IN_PRIME_BASIS", requested_prime: p } :
        { status: "FOUND", rule: copy(state.rules[index]) };
    },
    appendThrough(lastColumn, options) {
      work.append_requests++;
      object(options, "append options");
      const nextSource = sourceId(options.source_id);
      const last = natural(lastColumn, L.parameter_digits, true, "last column");
      if (last <= BigInt(state.interval.last_column)) fail("append must add columns strictly to the right");
      const stop = capState(BigInt(state.row), BigInt(state.interval.first_column), last,
        state.basis.limit, state.segments.length + 1);
      if (stop) return Object.assign(stop, { source_id: nextSource, parent_source_id: state.source_id, index: null });
      const appendWork = freshWork("append");
      appendWork.append_requests = 1;
      appendWork.retained_basis_entries_reused = state.basis.least_factor_by_integer.length;
      appendWork.retained_rules_reused = state.rules.length;
      appendWork.retained_column_records_reused = state.records.length;
      const firstNew = state.interval.last_column + 1, lastNew = Number(last);
      const initial = state.interval.last_value + state.row + firstNew - 2;
      const part = sieveSegment(state.row, firstNew, lastNew, initial, state.rules, appendWork);
      const offset = state.records.length, records = state.records.concat(part.records);
      const primeIndices = state.prime_record_indices.concat(part.primeIndices.map(i => i + offset));
      const summary = {
        column_count: records.length, prime_count: primeIndices.length,
        composite_count: state.summary.composite_count + part.segment.composite_count,
        unit_count: state.summary.unit_count + part.segment.unit_count,
        first_prime_column: state.summary.first_prime_column === null && part.primeIndices.length
          ? part.records[part.primeIndices[0]][0] : state.summary.first_prime_column,
        last_prime_column: part.primeIndices.length
          ? part.records[part.primeIndices[part.primeIndices.length - 1]][0] : state.summary.last_prime_column,
        first_composite_column: state.summary.first_composite_column === null
          ? part.segment.first_composite_column : state.summary.first_composite_column,
        last_composite_column: part.segment.last_composite_column === null
          ? state.summary.last_composite_column : part.segment.last_composite_column,
        conclusion: state.summary.conclusion
      };
      const child = {
        schema: SCHEMA, source_id: nextSource, parent_source_id: state.source_id, row: state.row,
        interval: { first_column: state.interval.first_column, last_column: lastNew,
          first_value: state.interval.first_value, last_value: part.segment.last_value,
          required_floor_square_root: integerSquareRoot(part.segment.last_value) },
        basis: state.basis, rules: state.rules, records, prime_record_indices: primeIndices,
        summary, segments: state.segments.concat([part.segment])
      };
      return { status: "COMPLETE", index: makeIndex(child, appendWork),
        appended: copy({ parent_source_id: state.source_id, source_id: nextSource,
          previous_column_count: offset, ...part.segment }) };
    },
    snapshot() { return copy(state); },
    work() { return copy(work); }
  });
}
function compileInterspersionRowPrimeIndex(request) {
  const L = INTERSPERSION_ROW_LIMITS;
  object(request, "compile request");
  const id = sourceId(request.source_id);
  const r = natural(request.row, L.parameter_digits, true, "row");
  const first = natural(request.first_column, L.parameter_digits, true, "first column");
  const last = natural(request.last_column, L.parameter_digits, true, "last column");
  const limit = small(request.prime_basis_limit, 2, L.max_prime_basis_limit, "prime basis limit");
  const stop = capState(r, first, last, limit, 1);
  if (stop) return Object.assign(stop, { source_id: id, index: null });
  const work = freshWork("compile"); work.compiler_calls = 1;
  const row = Number(r), begin = Number(first), end = Number(last);
  const basis = compileBasis(limit, work), rules = compileRules(row, basis, work);
  const part = sieveSegment(row, begin, end, Number(exactValue(r, first)), rules, work);
  const state = {
    schema: SCHEMA, source_id: id, parent_source_id: null, row,
    interval: { first_column: begin, last_column: end,
      first_value: part.segment.first_value, last_value: part.segment.last_value,
      required_floor_square_root: integerSquareRoot(part.segment.last_value) },
    basis, rules, records: part.records, prime_record_indices: part.primeIndices,
    summary: initialSummary(part.records, part.primeIndices, part.segment),
    segments: [part.segment]
  };
  return { status: "COMPLETE", index: makeIndex(state, work) };
}
function openRetainedInterspersionRowPrimeIndex(snapshot) {
  const work = freshWork("retained");
  return makeIndex(validateSaved(snapshot, work), work);
}
module.exports = {
  compileInterspersionRowPrimeIndex, openRetainedInterspersionRowPrimeIndex,
  INTERSPERSION_ROW_LIMITS
};
