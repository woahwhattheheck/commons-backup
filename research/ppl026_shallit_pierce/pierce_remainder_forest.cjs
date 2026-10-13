"use strict";

/**
 * Fixed-modulus Pierce remainders and exact terminal-cofactor records.
 * For a > b > 0, repeat b <- a mod b until zero. P(a,b) counts steps
 * including the final exact division. No dependencies or I/O.
 */
const PIERCE_LIMITS = Object.freeze({
  modulus: 65536,
  profile_entries: 65535,
  page_size: 128,
  trace_steps: 256
});

function integer(value, name, lo, hi) {
  if (!Number.isSafeInteger(value) || value < lo || value > hi)
    throw new RangeError(name + " must be a safe integer in [" + lo + "," + hi + "]");
  return value;
}
function sourceLabel(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > 512)
    throw new TypeError("source_id must be a nonempty string of at most 512 code units");
  return value;
}
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function orderedCounts(map, field) {
  return Array.from(map, ([value, count]) => ({[field]: value, count})).sort((x, y) => x[field] - y[field]);
}

function compilePierceRemainderForest(request) {
  if (!request || typeof request !== "object" || Array.isArray(request))
    throw new TypeError("request must be an object");
  const source_id = sourceLabel(request.source_id);
  const a = integer(request.a, "a", 2, PIERCE_LIMITS.modulus);
  const records = [], byLength = new Map(), terminalCounts = new Map();
  const roots = [];
  let maxLength = 0, lengthSum = 0, cofactorProducts = 0;
  for (let b = 1; b < a; b++) {
    const quotient = Math.floor(a / b), remainder = a - quotient * b;
    let length, terminal, cofactor;
    if (remainder === 0) {
      length = 1; terminal = b; cofactor = 1; roots.push(b);
    } else {
      const child = records[remainder - 1];
      length = child[2] + 1; terminal = child[3];
      const productRemainder = (quotient * child[4]) % a;
      cofactor = productRemainder === 0 ? 0 : a - productRemainder;
      cofactorProducts++;
    }
    const modulusCoefficient = (terminal - cofactor * b) / a;
    records.push([remainder, quotient, length, terminal, cofactor, modulusCoefficient]);
    if (!byLength.has(length)) byLength.set(length, []);
    byLength.get(length).push(b);
    terminalCounts.set(terminal, (terminalCounts.get(terminal) || 0) + 1);
    if (length > maxLength) maxLength = length;
    lengthSum += length;
  }
  const lengthGroups = Array.from(byLength, ([length, starts]) => ({length, starts}))
    .sort((x, y) => x.length - y.length);
  const summary = {
    starts: a - 1, maximum_length: maxLength,
    maximizing_starts: byLength.get(maxLength).slice(),
    length_sum: lengthSum,
    mean_length_fraction: {numerator: lengthSum, denominator: a - 1, reduced: false},
    length_histogram: lengthGroups.map(x => ({length: x.length, count: x.starts.length})),
    terminal_histogram: orderedCounts(terminalCounts, "terminal"),
    terminal_one_starts: terminalCounts.get(1) || 0,
    proper_terminal_starts: a - 1 - (terminalCounts.get(1) || 0),
    terminal_roots: roots
  };
  const snapshot = {
    schema: "shallit.pierce_remainder_forest/v1", source_id, a,
    record_indexing: "row b-1 represents starting value b, for 1<=b<a",
    record_columns: ["next_remainder", "quotient", "length_to_zero", "terminal_positive",
      "cofactor_residue", "modulus_coefficient"],
    certificate: "cofactor_residue*b + modulus_coefficient*a = terminal_positive",
    records, starts_by_length: lengthGroups, summary
  };
  return {
    schema: "shallit.pierce_forest_compilation/v1", status: "EXACT_FOREST",
    source_id, a, summary,
    work: {quotient_divisions: a - 1, remainder_products: a - 1,
      cofactor_modular_products: cofactorProducts, certificate_quotient_divisions: a - 1,
      records_written: a - 1, gcd_tests: 0, primality_tests: 0},
    snapshot,
    scope: "All positive starts below this one bounded modulus. No asymptotic or external-record claim."
  };
}

function openRetainedPierceForest(request) {
  if (!request || typeof request !== "object" || Array.isArray(request))
    throw new TypeError("request must be an object");
  const source_id = sourceLabel(request.source_id), saved = request.snapshot;
  if (!saved || saved.schema !== "shallit.pierce_remainder_forest/v1")
    throw new TypeError("A complete Pierce forest snapshot is required");
  const a = integer(saved.a, "snapshot.a", 2, PIERCE_LIMITS.modulus);
  sourceLabel(saved.source_id);
  if (!Array.isArray(saved.records) || saved.records.length !== a - 1)
    throw new RangeError("One retained row is required for each 1<=b<a");
  for (let at = 0; at < saved.records.length; at++) {
    const row = saved.records[at], b = at + 1;
    if (!Array.isArray(row) || row.length !== 6) throw new TypeError("Invalid record shape at b=" + b);
    integer(row[0], "remainder", 0, b - 1);
    integer(row[1], "quotient", 1, a);
    integer(row[2], "length", 1, b);
    integer(row[3], "terminal", 1, b);
    integer(row[4], "cofactor", 0, a - 1);
    integer(row[5], "modulus coefficient", -(a - 1), 0);
  }
  if (!Array.isArray(saved.starts_by_length) || saved.starts_by_length.length > a - 1)
    throw new TypeError("starts_by_length must be a bounded array");
  const groups = new Map();
  let previousLength = 0, totalGroupEntries = 0;
  for (const group of saved.starts_by_length) {
    if (!group || typeof group !== "object") throw new TypeError("Invalid length group");
    const length = integer(group.length, "group length", 1, a - 1);
    if (length <= previousLength || !Array.isArray(group.starts) || group.starts.length > a - 1)
      throw new RangeError("Length groups must be increasing and bounded");
    let previousStart = 0;
    for (const b of group.starts) {
      integer(b, "group start", 1, a - 1);
      if (b <= previousStart) throw new RangeError("Each length group must have increasing starts");
      previousStart = b;
    }
    totalGroupEntries += group.starts.length;
    if (totalGroupEntries > a - 1) throw new RangeError("Too many grouped starts");
    groups.set(length, group.starts.slice());
    previousLength = length;
  }
  if (totalGroupEntries !== a - 1) throw new RangeError("Length-group entry count must be a-1");
  const snapshot = copy(saved), records = snapshot.records;
  const boundary = {
    source_id, snapshot_source_id: saved.source_id,
    source_authenticated: false, quotients_recomputed: false,
    remainder_recursion_replayed: false, lengths_recomputed: false,
    cofactor_certificates_reverified: false, length_group_membership_reverified: false,
    unit_membership_checked: false,
    validation: "Full bounded row shape and index coverage, numeric ranges, ordered group shapes and total entry count only. Mathematical identities, groups and summary remain trusted source premises."
  };
  function lookup(b) {
    integer(b, "b", 1, a - 1);
    const row = records[b - 1];
    return {
      b, next_remainder: row[0], quotient: row[1], length_to_zero: row[2],
      terminal_positive: row[3], cofactor_residue: row[4], modulus_coefficient: row[5],
      certificate: {b, c: row[4], a, k: row[5], d: row[3], identity: "c*b+k*a=d"},
      inverse_from_this_chain: row[3] === 1 ? row[4] : null,
      interpretation: row[3] === 1
        ? "The retained cofactor is an inverse modulo a."
        : "This cofactor is not an inverse modulo a; this does not assert that b itself is a nonunit."
    };
  }
  function groupFor(length) {
    integer(length, "length", 1, a - 1);
    const starts = groups.get(length);
    if (!starts) throw new RangeError("No retained starts at this length");
    return starts;
  }
  function profileStarts(input) {
    if (!input || typeof input !== "object") throw new TypeError("profileStarts requires an object");
    const input_source_id = sourceLabel(input.source_id);
    if (!Array.isArray(input.starts) || input.starts.length > PIERCE_LIMITS.profile_entries)
      throw new RangeError("starts must be a bounded array");
    const starts = Array.from(new Set(input.starts.map(b => integer(b, "profile start", 1, a - 1))))
      .sort((x, y) => x - y);
    const lengths = new Map(), terminals = new Map(), rows = [];
    let max = 0, sum = 0, inverseCount = 0;
    const maxima = [];
    for (const b of starts) {
      const row = records[b - 1], length = row[2], terminal = row[3];
      rows.push([b, length, terminal, row[4], row[5]]);
      lengths.set(length, (lengths.get(length) || 0) + 1);
      terminals.set(terminal, (terminals.get(terminal) || 0) + 1);
      sum += length;
      if (terminal === 1) inverseCount++;
      if (length > max) { max = length; maxima.length = 0; maxima.push(b); }
      else if (length === max) maxima.push(b);
    }
    return {
      status: "PROFILED_RETAINED_STARTS", source_id, input_source_id, a,
      raw_start_entries: input.starts.length, distinct_starts: starts.length,
      duplicate_starts_removed: input.starts.length - starts.length,
      record_columns: ["start", "length_to_zero", "terminal_positive", "cofactor_residue", "modulus_coefficient"],
      records: rows, maximum_length: starts.length ? max : null, maximizing_starts: maxima,
      length_sum: sum, length_histogram: orderedCounts(lengths, "length"),
      terminal_histogram: orderedCounts(terminals, "terminal"),
      chain_inverse_count: inverseCount, other_terminal_count: starts.length - inverseCount,
      unit_membership_checked: false,
      work: {saved_rows_read: starts.length, remainder_operations: 0, gcd_tests: 0},
      scope: "A profile of the supplied distinct starts. Any interpretation as a complete unit set is an external source premise."
    };
  }
  return Object.freeze({
    describe() { return {status: "OPEN_RETAINED_FOREST", a, summary: copy(snapshot.summary), boundary: copy(boundary)}; },
    lookup,
    trace(input) {
      if (!input || typeof input !== "object") throw new TypeError("trace requires {b,limit}");
      const b = integer(input.b, "b", 1, a - 1);
      const limit = integer(input.limit === undefined ? PIERCE_LIMITS.trace_steps : input.limit,
        "limit", 1, PIERCE_LIMITS.trace_steps);
      const steps = [], values = [b];
      let current = b;
      while (current > 0 && steps.length < limit) {
        const row = lookup(current);
        steps.push(row); current = row.next_remainder; values.push(current);
      }
      return {status: current === 0 ? "COMPLETE_RETAINED_TRACE" : "TRACE_PAGE",
        source_id, a, initial_b: b, values, steps, next_b: current === 0 ? null : current,
        recorded_initial_length: records[b - 1][2], actual_steps_in_page: steps.length,
        remainders_recomputed: false};
    },
    selectStart(input) {
      if (!input || typeof input !== "object") throw new TypeError("selectStart requires {length,rank}");
      const starts = groupFor(input.length);
      const rank = integer(input.rank, "rank", 0, starts.length - 1);
      return {length: input.length, rank, total: starts.length, record: lookup(starts[rank]), source_id};
    },
    rankStart(b) {
      integer(b, "b", 1, a - 1);
      const length = records[b - 1][2], starts = groupFor(length);
      let lo = 0, hi = starts.length;
      while (lo < hi) { const mid = Math.floor((lo + hi) / 2); if (starts[mid] < b) lo = mid + 1; else hi = mid; }
      if (starts[lo] !== b) throw new Error("Retained length group lacks this start");
      return {b, length, rank: lo, total: starts.length, source_id};
    },
    pageStarts(input) {
      if (!input || typeof input !== "object") throw new TypeError("pageStarts requires a length");
      const starts = groupFor(input.length);
      const at = integer(input.start_index === undefined ? 0 : input.start_index,
        "start_index", 0, starts.length);
      const limit = integer(input.limit === undefined ? 32 : input.limit, "limit", 1, PIERCE_LIMITS.page_size);
      const end = Math.min(at + limit, starts.length);
      return {length: input.length, start_index: at, records: starts.slice(at, end).map(lookup),
        next_index: end < starts.length ? end : null, total: starts.length, source_id};
    },
    profileStarts,
    snapshot() { return copy(snapshot); }
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {compilePierceRemainderForest, openRetainedPierceForest, PIERCE_LIMITS};
}
