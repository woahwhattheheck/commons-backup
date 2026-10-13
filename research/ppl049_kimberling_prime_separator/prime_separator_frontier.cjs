"use strict";

/*
 * Kimberling's prime separator array (OEIS A129258/A129259/A129260).
 * Finite continuation from an identified accepted boundary prefix.
 * Both new mex values are chosen before adding either new boundary.
 * No I/O, imports, seed regeneration, prime sieve, or old square materialization.
 */

const PRIME_SEPARATOR_LIMITS = Object.freeze({
  max_size: 1024,
  max_basis_limit: 65536,
  max_page_size: 128,
  max_source_id_chars: 1024,
  max_segments: 32
});
const L = PRIME_SEPARATOR_LIMITS;
const SCHEMA = "commons.kimberling12.prime_separator_frontier/v1";
const BOUNDARY_MAX = (L.max_size - 1) ** 2 + 2;
const PRODUCT_MAX = BOUNDARY_MAX ** 2;

function copy(x) { return JSON.parse(JSON.stringify(x)); }
function integer(x, lo, hi, name) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) throw new RangeError(name + " outside integer contract");
  return x;
}
function integerSquareRoot(v) {
  let r = Math.floor(Math.sqrt(v));
  while ((r + 1) * (r + 1) <= v) r++;
  while (r * r > v) r--;
  return r;
}
function sourceId(x, name) {
  if (typeof x !== "string" || !x.length || x.length > L.max_source_id_chars) throw new TypeError(name + " required");
  return x;
}
function freshWork(mode) {
  return {
    mode, construction_calls: 0, retained_opens: 0, append_calls: 0,
    seed_pairs_loaded: 0, structural_basis_entries: 0,
    structural_prior_events: 0, structural_prior_records: 0,
    saved_frontier_nodes_loaded: 0, saved_exhausted_streams_loaded: 0,
    frontier_initializations: 0, initial_streams: 0,
    frontier_binary_searches: 0, frontier_binary_steps: 0,
    product_evaluations: 0, heap_comparisons: 0, heap_pushes: 0, heap_pops: 0,
    product_hits: 0, duplicate_product_hits: 0, exhausted_stream_reinsertions: 0,
    covered_values_emitted: 0, mex_values_emitted: 0, stages_completed: 0,
    least_factor_lookups: 0, trial_divisions: 0, exact_factor_divisions: 0,
    divisor_membership_rows: 0, new_prime_records: 0,
    query_calls: 0, query_binary_steps: 0, query_records_decoded: 0,
    accepted_seed_steps_recomputed: 0, old_square_materializations: 0,
    prime_sieve_calls: 0, saved_product_recomputations: 0
  };
}
function delta(before, after) {
  const out = {};
  for (const k of Object.keys(after)) if (typeof after[k] === "number") out[k] = after[k] - before[k];
  return out;
}
function validateBasis(raw, sizeCap, work) {
  if (!raw || typeof raw !== "object") throw new TypeError("accepted basis required");
  const limit = integer(raw.limit, 2, L.max_basis_limit, "basis limit");
  const required = integerSquareRoot((sizeCap - 1) ** 2 + 2);
  if (limit < required) throw new RangeError("basis does not cover the maximum required square root");
  if (!Array.isArray(raw.primes) || !raw.primes.length ||
      !Array.isArray(raw.least_factor_by_integer) || raw.least_factor_by_integer.length !== limit + 1)
    throw new TypeError("complete retained basis arrays required");
  const primes = raw.primes.slice(), least = raw.least_factor_by_integer.slice();
  if (least[0] !== 0 || least[1] !== 1 || primes[0] !== 2) throw new Error("basis endpoint shape");
  for (let i = 0; i < primes.length; i++) {
    integer(primes[i], 2, limit, "basis prime");
    if (i && primes[i] <= primes[i - 1]) throw new Error("basis primes must be increasing");
  }
  for (let i = 2; i <= limit; i++) integer(least[i], 2, i, "retained least factor");
  work.structural_basis_entries += least.length;
  return { limit, primes, least_factor_by_integer: least };
}
function validateBoundaries(firstRow, firstColumn, cap) {
  if (!Array.isArray(firstRow) || !Array.isArray(firstColumn) ||
      firstRow.length !== firstColumn.length || !firstRow.length || firstRow.length > cap)
    throw new TypeError("equal nonempty finite boundaries required");
  const R = firstRow.slice(), C = firstColumn.slice();
  if (R[0] !== 1 || C[0] !== 1) throw new Error("both boundaries must begin at one");
  for (let j = 0; j < R.length; j++) {
    integer(R[j], 1, BOUNDARY_MAX, "first-row value");
    integer(C[j], 1, BOUNDARY_MAX, "first-column value");
    if (j && !(C[j - 1] < R[j] && R[j] < C[j])) throw new Error("boundary interlacing shape");
    if (j && (R[j] > j * j + 1 || C[j] > j * j + 2)) throw new Error("boundary cardinality bound");
  }
  return { R, C };
}
function less(a, b, work) {
  work.heap_comparisons++;
  return a[0] < b[0] || (a[0] === b[0] && (a[1] < b[1] || (a[1] === b[1] && a[2] < b[2])));
}
function push(heap, node, work) {
  work.heap_pushes++;
  let i = heap.length; heap.push(node);
  while (i) {
    const p = (i - 1) >> 1;
    if (!less(node, heap[p], work)) break;
    heap[i] = heap[p]; i = p;
  }
  heap[i] = node;
}
function pop(heap, work) {
  if (!heap.length) throw new Error("empty heap");
  work.heap_pops++;
  const root = heap[0], last = heap.pop();
  if (heap.length) {
    let i = 0;
    while (true) {
      const left = 2 * i + 1;
      if (left >= heap.length) break;
      const right = left + 1;
      const child = right < heap.length && less(heap[right], heap[left], work) ? right : left;
      if (!less(heap[child], last, work)) break;
      heap[i] = heap[child]; i = child;
    }
    heap[i] = last;
  }
  return root;
}
function product(a, b, work) {
  work.product_evaluations++;
  const v = a * b;
  if (!Number.isSafeInteger(v) || v > PRODUCT_MAX) throw new RangeError("product bound");
  return v;
}
function firstAtLeast(R, C, rowIndex, cursor, work) {
  work.frontier_binary_searches++;
  let lo = 0, hi = C.length;
  while (lo < hi) {
    work.frontier_binary_steps++;
    const mid = (lo + hi) >> 1;
    if (product(R[rowIndex - 1], C[mid], work) < cursor) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}
function initializeFrontier(R, C, work) {
  work.frontier_initializations++;
  const cursor = C[C.length - 1] + 1, heap = [], exhausted = [];
  for (let j = 1; j <= R.length; j++) {
    work.initial_streams++;
    const i = firstAtLeast(R, C, j, cursor, work);
    if (i === C.length) exhausted.push(j);
    else push(heap, [product(R[j - 1], C[i], work), j, i + 1], work);
  }
  return { cursor, heap, exhausted_rows: exhausted };
}
function factorCertificate(value, basis, work) {
  let remaining = value;
  const powers = [], steps = [];
  function add(p, e) {
    const old = powers.find(x => x[0] === p);
    if (old) old[1] += e; else powers.push([p, e]);
  }
  if (value <= basis.limit) {
    while (remaining > 1) {
      work.least_factor_lookups++;
      const p = basis.least_factor_by_integer[remaining], q = remaining / p;
      if (!Number.isSafeInteger(q)) throw new Error("retained least factor does not divide the new candidate");
      steps.push([remaining, p, q]); add(p, 1);
      work.exact_factor_divisions++; remaining = q;
    }
    powers.sort((a, b) => a[0] - b[0]);
    return { method: "accepted_least_factor_table", prime_powers: powers, division_steps: steps,
      trial_rows: [], residual_prime: null };
  }
  const trialRows = [];
  let pi = 0;
  while (pi < basis.primes.length && basis.primes[pi] * basis.primes[pi] <= remaining) {
    const p = basis.primes[pi], before = remaining;
    let e = 0;
    while (true) {
      work.trial_divisions++;
      if (remaining % p !== 0) break;
      const q = remaining / p;
      steps.push([remaining, p, q]); remaining = q; e++; work.exact_factor_divisions++;
    }
    if (e) add(p, e);
    trialRows.push([pi, p, before, e, remaining, remaining % p]);
    pi++;
  }
  let residual = null;
  if (remaining > 1) {
    const next = pi < basis.primes.length ? basis.primes[pi] : null;
    if (next !== null && next * next <= remaining) throw new Error("incomplete trial prefix");
    if (next === null && basis.limit * basis.limit <= remaining) throw new Error("accepted prime basis exhausted");
    residual = { value: remaining, tested_prefix_length: pi, first_untested_prime: next,
      square_root_floor: integerSquareRoot(remaining) };
    add(remaining, 1);
  }
  powers.sort((a, b) => a[0] - b[0]);
  return { method: "accepted_prime_basis_trial", prime_powers: powers, division_steps: steps,
    trial_rows: trialRows, residual_prime: residual };
}
function absenceCertificate(value, Rmap, Cmap, basis, work) {
  const factorization = factorCertificate(value, basis, work);
  let divisors = [1];
  for (const [p, e] of factorization.prime_powers) {
    const old = divisors.slice();
    let power = 1;
    for (let k = 1; k <= e; k++) {
      power *= p;
      for (const d of old) divisors.push(d * power);
    }
  }
  divisors.sort((a, b) => a - b);
  const memberships = divisors.map(d => {
    const q = value / d;
    if (!Number.isSafeInteger(q)) throw new Error("factor expansion did not produce a divisor");
    const ri = Rmap.get(d) || 0, ci = Cmap.get(q) || 0;
    if (ri && ci) throw new Error("new mex has a product representation in the old square");
    work.divisor_membership_rows++;
    return [d, q, ri, ci];
  });
  const pp = factorization.prime_powers;
  const isPrime = pp.length === 1 && pp[0][0] === value && pp[0][1] === 1;
  return { value, classification: isPrime ? "PRIME" : "COMPOSITE",
    factorization, divisor_memberships: memberships };
}
function validateSaved(raw, work) {
  if (!raw || raw.schema !== SCHEMA) throw new TypeError("saved frontier schema");
  const cap = integer(raw.size_cap, 1, L.max_size, "saved size cap");
  const bounds = validateBoundaries(raw.first_row, raw.first_column, cap);
  const state = copy(raw);
  state.first_row = bounds.R; state.first_column = bounds.C;
  sourceId(state.source_id, "saved source id");
  if (state.parent_source_id !== null) sourceId(state.parent_source_id, "parent source id");
  const p = state.premises;
  if (!p || typeof p !== "object") throw new TypeError("identified premises required");
  sourceId(p.seed_source_id, "seed source id"); sourceId(p.basis_source_id, "basis source id");
  integer(p.seed_size, 1, state.first_row.length, "seed size");
  if (p.seed_last_row !== state.first_row[p.seed_size - 1] ||
      p.seed_last_column !== state.first_column[p.seed_size - 1]) throw new Error("seed boundary identity");
  state.basis = validateBasis(state.basis, cap, work);
  const n = state.first_row.length, f = state.frontier;
  if (!f || f.cursor !== state.first_column[n - 1] + 1 ||
      !Array.isArray(f.heap) || !Array.isArray(f.exhausted_rows)) throw new Error("saved frontier shape");
  const seen = new Set();
  for (let k = 0; k < f.heap.length; k++) {
    const node = f.heap[k];
    if (!Array.isArray(node) || node.length !== 3) throw new Error("heap node shape");
    integer(node[0], f.cursor, PRODUCT_MAX, "saved product");
    integer(node[1], 1, n, "saved first-row index");
    integer(node[2], 1, n, "saved first-column index");
    if (seen.has(node[1])) throw new Error("repeated product stream");
    seen.add(node[1]);
    if (k) {
      const parent = f.heap[(k - 1) >> 1];
      if (node[0] < parent[0] || (node[0] === parent[0] &&
          (node[1] < parent[1] || (node[1] === parent[1] && node[2] < parent[2]))))
        throw new Error("saved heap order");
    }
  }
  for (const j of f.exhausted_rows) {
    integer(j, 1, n, "exhausted first-row index");
    if (seen.has(j)) throw new Error("repeated stream ownership");
    seen.add(j);
  }
  if (seen.size !== n) throw new Error("missing saved product stream");
  work.saved_frontier_nodes_loaded += f.heap.length;
  work.saved_exhausted_streams_loaded += f.exhausted_rows.length;
  if (!Array.isArray(state.events) || state.events.length !== n - p.seed_size ||
      !Array.isArray(state.records) || state.records.length !== state.first_column[n - 1] - p.seed_last_column ||
      !Array.isArray(state.prime_record_indices) || !Array.isArray(state.segments) ||
      state.segments.length > L.max_segments) throw new Error("saved coverage shape");
  for (let i = 0; i < state.events.length; i++) {
    const e = state.events[i], index = p.seed_size + i + 1;
    if (!e || e.index !== index || e.old_size !== index - 1 ||
        e.first_row !== state.first_row[index - 1] || e.first_column !== state.first_column[index - 1] ||
        e.old_covered_through !== state.first_column[index - 2] ||
        e.record_start !== e.old_covered_through - p.seed_last_column ||
        e.record_count !== e.first_column - e.old_covered_through ||
        !e.row_absence || !e.column_absence ||
        e.row_absence.value !== e.first_row || e.column_absence.value !== e.first_column ||
        !Array.isArray(e.row_absence.divisor_memberships) || !Array.isArray(e.column_absence.divisor_memberships))
      throw new Error("saved event shape");
    work.structural_prior_events++;
  }
  for (let i = 0; i < state.records.length; i++) {
    const r = state.records[i];
    if (!Array.isArray(r) || r.length !== 5 || r[0] !== p.seed_last_column + i + 1)
      throw new Error("saved classified interval must be contiguous");
    integer(r[1], 0, 2, "record kind");
    integer(r[2], 1, n, "record first-row index");
    integer(r[3], 1, n, "record first-column index");
    integer(r[4], p.seed_size + 1, n, "record stage");
    work.structural_prior_records++;
  }
  for (let i = 0; i < state.prime_record_indices.length; i++) {
    const ri = integer(state.prime_record_indices[i], 0, state.records.length - 1, "prime record index");
    if ((i && ri <= state.prime_record_indices[i - 1]) || state.records[ri][1] === 0)
      throw new Error("saved prime index shape");
  }
  if (!state.statistics || !state.gaps || !Array.isArray(state.gaps.maximum_indices) ||
      state.statistics.new_values !== state.records.length ||
      state.statistics.new_primes !== state.prime_record_indices.length ||
      state.statistics.new_stages !== state.events.length) throw new Error("saved summary shape");
  return state;
}
function makeIndex(state, work) {
  const R = state.first_row, C = state.first_column;
  const Rmap = new Map(R.map((v, i) => [v, i + 1]));
  const Cmap = new Map(C.map((v, i) => [v, i + 1]));
  const exhausted = new Set(state.frontier.exhausted_rows);
  function sync() { state.frontier.exhausted_rows = Array.from(exhausted).sort((a, b) => a - b); }
  function summary() {
    return {
      source_id: state.source_id, parent_source_id: state.parent_source_id,
      seed_size: state.premises.seed_size, size: R.length, size_cap: state.size_cap,
      seed_covered_through: state.premises.seed_last_column,
      newly_classified_interval: { first: state.premises.seed_last_column + 1, last: C[C.length - 1] },
      first_row_last: R[R.length - 1], first_column_last: C[C.length - 1],
      statistics: copy(state.statistics), first_row_gaps: copy(state.gaps),
      frontier: { cursor: state.frontier.cursor, active_streams: state.frontier.heap.length,
        exhausted_streams: exhausted.size, next_product: state.frontier.heap.length ? state.frontier.heap[0][0] : null },
      segments: state.segments.length
    };
  }
  function nextMex(stage) {
    const f = state.frontier, heap = f.heap;
    while (true) {
      const value = f.cursor;
      if (value > BOUNDARY_MAX) throw new RangeError("mex exceeds proven size-cap bound");
      if (!heap.length || heap[0][0] > value) {
        f.cursor++;
        work.mex_values_emitted++;
        return value;
      }
      if (heap[0][0] < value) throw new Error("frontier fell behind cursor");
      const first = heap[0];
      if (R[first[1] - 1] <= 1 || C[first[2] - 1] <= 1) throw new Error("new covered value lacks proper factors");
      state.records.push([value, 0, first[1], first[2], stage]);
      work.covered_values_emitted++; state.statistics.covered_composites++;
      let hits = 0;
      while (heap.length && heap[0][0] === value) {
        const node = pop(heap, work); hits++; work.product_hits++;
        const nextColumn = node[2] + 1;
        if (nextColumn <= C.length)
          push(heap, [product(R[node[1] - 1], C[nextColumn - 1], work), node[1], nextColumn], work);
        else exhausted.add(node[1]);
      }
      work.duplicate_product_hits += hits - 1;
      f.cursor++;
    }
  }
  function oneStage() {
    const oldSize = R.length, index = oldSize + 1, oldCutoff = C[C.length - 1];
    const start = state.records.length, oldRow = R[R.length - 1];
    const rowValue = nextMex(index);
    const rowRecordIndex = state.records.length;
    state.records.push([rowValue, 1, index, 1, index]);
    const columnValue = nextMex(index);
    const columnRecordIndex = state.records.length;
    state.records.push([columnValue, 2, 1, index, index]);

    // Both certificates use maps of the OLD square. Neither boundary is inserted yet.
    const rowAbsence = absenceCertificate(rowValue, Rmap, Cmap, state.basis, work);
    const columnAbsence = absenceCertificate(columnValue, Rmap, Cmap, state.basis, work);
    if (rowValue > oldSize * oldSize + 1 || columnValue > oldSize * oldSize + 2)
      throw new Error("new boundary violates mex cardinality bound");
    for (const [cert, recordIndex, side] of [
      [rowAbsence, rowRecordIndex, "row"], [columnAbsence, columnRecordIndex, "column"]
    ]) {
      if (cert.classification === "PRIME") {
        state.prime_record_indices.push(recordIndex);
        state.statistics.new_primes++; work.new_prime_records++;
        state.statistics[side === "row" ? "first_row_primes" : "first_column_primes"]++;
      } else state.statistics.selected_composites++;
    }

    // Insert both boundaries only after both choices and old-square absence records.
    R.push(rowValue); C.push(columnValue); Rmap.set(rowValue, index); Cmap.set(columnValue, index);
    const heap = state.frontier.heap, cursor = state.frontier.cursor;
    for (const j of Array.from(exhausted)) {
      const value = product(R[j - 1], columnValue, work);
      if (value >= cursor) {
        exhausted.delete(j);
        push(heap, [value, j, index], work);
        work.exhausted_stream_reinsertions++;
      }
    }
    const firstColumn = firstAtLeast(R, C, index, cursor, work);
    if (firstColumn === C.length) exhausted.add(index);
    else push(heap, [product(rowValue, C[firstColumn], work), index, firstColumn + 1], work);

    const gap = rowValue - oldRow;
    if (state.gaps.maximum === null || gap > state.gaps.maximum) {
      state.gaps.maximum = gap; state.gaps.maximum_indices = [index];
    } else if (gap === state.gaps.maximum) state.gaps.maximum_indices.push(index);
    state.gaps.histogram[String(gap)] = (state.gaps.histogram[String(gap)] || 0) + 1;
    state.events.push({
      index, old_size: oldSize, old_covered_through: oldCutoff,
      first_row: rowValue, first_column: columnValue,
      first_row_gap: gap, first_column_gap: columnValue - oldCutoff,
      record_start: start, record_count: columnValue - oldCutoff,
      row_absence: rowAbsence, column_absence: columnAbsence
    });
    if (state.records.length - start !== columnValue - oldCutoff) throw new Error("new interval coverage count");
    state.statistics.new_values += columnValue - oldCutoff;
    state.statistics.new_stages++; work.stages_completed++;
  }
  function appendThrough(request) {
    if (!request || typeof request !== "object") throw new TypeError("append request required");
    const target = integer(request.target_size, 1, Number.MAX_SAFE_INTEGER, "target size");
    if (target > state.size_cap) return { status: "ABOVE_SIZE_CAP", maximum_size: state.size_cap, unchanged: true };
    if (target < R.length) throw new RangeError("cannot shrink retained boundaries");
    if (target === R.length) return { status: "NO_NEW_INDICES", summary: summary(), unchanged: true };
    if (state.segments.length >= L.max_segments) return { status: "SEGMENT_CAP", maximum_segments: L.max_segments, unchanged: true };
    const id = sourceId(request.source_id, "new source id");
    if (id === state.source_id) throw new Error("append source id must identify a new state");
    const before = copy(work), oldId = state.source_id, oldSize = R.length, oldCutoff = C[C.length - 1];
    work.append_calls++;
    while (R.length < target) oneStage();
    state.parent_source_id = oldId; state.source_id = id;
    sync();
    const segment = {
      source_id: id, parent_source_id: oldId, first_index: oldSize + 1, last_index: target,
      first_value: oldCutoff + 1, last_value: C[C.length - 1], work: delta(before, work)
    };
    state.segments.push(segment);
    return { status: "COMPLETE", summary: summary(), segment: copy(segment) };
  }
  function query() { work.query_calls++; }
  function record(value) {
    const i = value - state.premises.seed_last_column - 1;
    if (i < 0 || i >= state.records.length) return {
      status: "OUTSIDE_NEW_INTERVAL", interval: [state.premises.seed_last_column + 1, C[C.length - 1]]
    };
    work.query_records_decoded++;
    const r = state.records[i], stage = state.events[r[4] - state.premises.seed_size - 1];
    if (r[1] === 0) return {
      status: "CLASSIFIED", value, classification: "COMPOSITE", mechanism: "old_square_product",
      first_row_index: r[2], first_column_index: r[3], array_coordinate: [r[3], r[2]],
      factors: [R[r[2] - 1], C[r[3] - 1]], selected_at_stage: r[4]
    };
    const cert = r[1] === 1 ? stage.row_absence : stage.column_absence;
    return {
      status: "CLASSIFIED", value, classification: cert.classification,
      mechanism: r[1] === 1 ? "new_first_row" : "new_first_column",
      boundary_index: r[4], array_coordinate: r[1] === 1 ? [1, r[4]] : [r[4], 1],
      selected_at_stage: r[4], absence_certificate: copy(cert)
    };
  }
  function lowerPrime(value, inclusive) {
    const indices = state.prime_record_indices;
    let lo = 0, hi = indices.length;
    while (lo < hi) {
      work.query_binary_steps++;
      const mid = (lo + hi) >> 1, v = state.records[indices[mid]][0];
      if (v < value || (inclusive && v === value)) lo = mid + 1; else hi = mid;
    }
    return lo;
  }
  function primeAt(rank) {
    const rows = state.prime_record_indices;
    if (rank >= rows.length) return { status: "OUT_OF_RANGE", count: rows.length };
    const r = state.records[rows[rank]];
    work.query_records_decoded++;
    return { status: "FOUND", rank, value: r[0],
      side: r[1] === 1 ? "first_row" : "first_column", boundary_index: r[4],
      event_offset: r[4] - state.premises.seed_size - 1 };
  }
  return Object.freeze({
    summary() { query(); return summary(); },
    appendThrough,
    classifyNewValue(value) { query(); integer(value, 1, Number.MAX_SAFE_INTEGER, "value"); return record(value); },
    boundary(index) {
      query(); integer(index, 1, R.length, "boundary index");
      return { index, first_row: R[index - 1], first_column: C[index - 1],
        provenance: index <= state.premises.seed_size ? "accepted_seed" : "new_continuation" };
    },
    eventAt(index) {
      query(); integer(index, state.premises.seed_size + 1, R.length, "new event index");
      work.query_records_decoded++;
      const e = state.events[index - state.premises.seed_size - 1];
      return Object.assign(copy(e), { classified_records: copy(state.records.slice(e.record_start, e.record_start + e.record_count)) });
    },
    countPrimesThrough(value) {
      query(); integer(value, 0, Number.MAX_SAFE_INTEGER, "upper value");
      return { count: lowerPrime(value, true), lower_exclusive: state.premises.seed_last_column,
        upper_inclusive: Math.min(value, C[C.length - 1]), full_retained_upper: C[C.length - 1] };
    },
    selectPrime(rank) { query(); integer(rank, 0, Number.MAX_SAFE_INTEGER, "prime rank"); return primeAt(rank); },
    rankPrime(value) {
      query(); integer(value, 1, Number.MAX_SAFE_INTEGER, "prime value");
      const rank = lowerPrime(value, false), indices = state.prime_record_indices;
      if (rank < indices.length && state.records[indices[rank]][0] === value) return primeAt(rank);
      return { status: "NOT_IN_NEW_PRIME_INDEX", value, lower_exclusive: state.premises.seed_last_column,
        upper_inclusive: C[C.length - 1] };
    },
    pagePrimes(start, limit) {
      query(); integer(start, 0, Number.MAX_SAFE_INTEGER, "prime page start");
      integer(limit, 1, L.max_page_size, "prime page size");
      const end = Math.min(state.prime_record_indices.length, start + limit), rows = [];
      for (let r = start; r < end; r++) rows.push(primeAt(r));
      return { start, rows, total: state.prime_record_indices.length,
        next_start: end < state.prime_record_indices.length ? end : null };
    },
    pageRowGaps(start, limit) {
      query(); integer(start, 0, Number.MAX_SAFE_INTEGER, "gap page start");
      integer(limit, 1, L.max_page_size, "gap page size");
      const end = Math.min(state.events.length, start + limit), rows = [];
      for (let i = start; i < end; i++) {
        work.query_records_decoded++;
        const e = state.events[i];
        rows.push({ index: e.index, previous: R[e.index - 2], value: e.first_row, gap: e.first_row_gap });
      }
      return { start, rows, total: state.events.length, next_start: end < state.events.length ? end : null };
    },
    snapshot() { sync(); return copy(state); },
    work() { return copy(work); }
  });
}
function continuePrimeSeparator(request) {
  if (!request || !request.seed) throw new TypeError("accepted seed request required");
  const target = integer(request.target_size, 1, Number.MAX_SAFE_INTEGER, "target size");
  const cap = integer(request.size_cap === undefined ? L.max_size : request.size_cap, 1, L.max_size, "size cap");
  if (target > cap) return { status: "ABOVE_SIZE_CAP", maximum_size: cap, index: null };
  const source = sourceId(request.source_id, "source id");
  const seedSource = sourceId(request.seed.source_id, "seed source id");
  const basisSource = sourceId(request.basis_source_id, "basis source id");
  if (source === seedSource) throw new Error("new source id must differ from seed source id");
  const { R, C } = validateBoundaries(request.seed.first_row, request.seed.first_column, cap);
  if (target <= R.length) throw new RangeError("constructor requires at least one new boundary pair");
  const work = freshWork("construct"); work.construction_calls = 1; work.seed_pairs_loaded = R.length;
  const basis = validateBasis(request.basis, cap, work);
  const state = {
    schema: SCHEMA, source_id: seedSource, parent_source_id: null, size_cap: cap,
    premises: { seed_source_id: seedSource, seed_size: R.length,
      seed_last_row: R[R.length - 1], seed_last_column: C[C.length - 1],
      basis_source_id: basisSource, validation_scope: "structural; mathematical seed and prime basis are accepted premises" },
    first_row: R, first_column: C, basis, frontier: initializeFrontier(R, C, work),
    events: [], records: [], prime_record_indices: [], segments: [],
    statistics: { new_stages: 0, new_values: 0, covered_composites: 0, selected_composites: 0,
      new_primes: 0, first_row_primes: 0, first_column_primes: 0 },
    gaps: { first_new_index: R.length + 1, maximum: null, maximum_indices: [], histogram: {} }
  };
  const index = makeIndex(state, work);
  const result = index.appendThrough({ target_size: target, source_id: source });
  return { status: result.status, index };
}
function openRetainedPrimeSeparator(snapshot) {
  const work = freshWork("retained"); work.retained_opens = 1;
  return makeIndex(validateSaved(snapshot, work), work);
}
module.exports = { continuePrimeSeparator, openRetainedPrimeSeparator, PRIME_SEPARATOR_LIMITS };
