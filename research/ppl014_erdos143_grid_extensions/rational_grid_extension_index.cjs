"use strict";

/**
 * Finite rational-grid extension index for the hypothesis of Erdos problem 143.
 * Saved indices are mathematical premises: the loader checks structure, not
 * the arithmetic or completeness of the recorded CRT derivation.
 */
const GRID_EXTENSION_LIMITS = Object.freeze({
  max_prefix_entries: 16,
  denominator_digits: 16,
  numerator_digits: 32,
  period_digits: 256,
  max_residues: 32768,
  max_retained_join_rows: 65536,
  query_digits: 1024,
  rank_digits: 512,
  max_page_size: 128,
  source_id_chars: 512
});
const SCHEMA = "commons.erdos143.rational_grid_extension_index/v1";

function fail(message) { throw new TypeError(message); }
function object(x, name) {
  if (!x || typeof x !== "object" || Array.isArray(x)) fail(name + " must be an object");
  return x;
}
function array(x, name, cap) {
  if (!Array.isArray(x) || x.length > cap) fail(name + " exceeds its array contract");
  return x;
}
function natural(x, digits, name) {
  let s;
  if (typeof x === "bigint") s = x.toString();
  else if (typeof x === "number" && Number.isSafeInteger(x)) s = String(x);
  else if (typeof x === "string") s = x;
  else fail(name + " must be an exact nonnegative integer");
  if (!/^(0|[1-9][0-9]*)$/.test(s) || s.length > digits) fail(name + " exceeds its integer contract");
  return BigInt(s);
}
function savedNatural(x, digits, name) {
  if (typeof x !== "string") fail(name + " must be a canonical decimal string");
  return natural(x, digits, name);
}
function savedSigned(x, digits, name) {
  if (typeof x !== "string" || !/^(0|-?[1-9][0-9]*)$/.test(x) ||
      x.replace("-", "").length > digits) fail(name + " must be a bounded signed decimal string");
  return BigInt(x);
}
function small(x, cap, name) {
  if (!Number.isInteger(x) || x < 0 || x > cap) fail(name + " must be a bounded integer");
  return x;
}
function sourceId(x) {
  if (typeof x !== "string" || x.length === 0 || x.length > GRID_EXTENSION_LIMITS.source_id_chars)
    fail("source_id must be a nonempty bounded string");
  return x;
}
function clone(x) { return JSON.parse(JSON.stringify(x)); }
function mod(a, m) { const r = a % m; return r < 0n ? r + m : r; }
function gcd(a, b, work) {
  work.gcd_calls++;
  while (b !== 0n) { const r = a % b; a = b; b = r; work.gcd_remainder_steps++; }
  return a;
}
function inverseCertificate(a, m, work) {
  work.inverse_calls++;
  let r0 = a, r1 = m, u0 = 1n, u1 = 0n, v0 = 0n, v1 = 1n;
  while (r1 !== 0n) {
    const q = r0 / r1;
    [r0, r1] = [r1, r0 - q * r1];
    [u0, u1] = [u1, u0 - q * u1];
    [v0, v1] = [v1, v0 - q * v1];
    work.inverse_euclid_steps++;
  }
  if (r0 !== 1n) throw new Error("internal reduced-modulus invariant failed");
  return { inverse: mod(u0, m).toString(), left_coefficient: u0.toString(),
    right_coefficient: v0.toString(), gcd: "1" };
}
function freshWork(mode) {
  return { mode, compiler_calls: 0, public_append_attempts: 0,
    new_pair_checks: 0, new_crt_steps: 0, compatible_join_rows_constructed: 0,
    gcd_classes_constructed: 0, gcd_calls: 0, gcd_remainder_steps: 0,
    inverse_calls: 0, inverse_euclid_steps: 0,
    structural_stage_rows_read: 0, structural_join_rows_read: 0,
    structural_pair_rows_read: 0, structural_residue_rows_read: 0,
    runtime_residue_values_indexed: 0, query_calls: 0,
    query_binary_search_steps: 0, old_pair_rechecks: 0, old_crt_steps_replayed: 0 };
}
function emptyState(Q, id) {
  return { schema: SCHEMA, source_id: id, denominator: Q.toString(),
    prefix_numerators: [], period: "1", residues: ["0"],
    pair_witnesses: [], stages: [] };
}
function pairWitness(a, b, Q, leftIndex, rightIndex, work) {
  work.new_pair_checks++;
  const quotient = b / a, remainder = b % a;
  const valid = remainder >= Q && a - remainder >= Q;
  const bad = valid ? null : (remainder < Q ? quotient : quotient + 1n).toString();
  return { left_index: leftIndex, right_index: rightIndex,
    a_numerator: a.toString(), b_numerator: b.toString(),
    quotient: quotient.toString(), remainder: remainder.toString(),
    lower_multiple: (quotient * a).toString(),
    upper_multiple: ((quotient + 1n) * a).toString(),
    lower_distance: remainder.toString(), upper_distance: (a - remainder).toString(),
    valid, violating_multiplier: bad };
}
function retainedJoinCount(state) {
  return state.stages.reduce((n, s) => n + s.joins.length, 0);
}
function extendState(state, b, id, work) {
  const L = GRID_EXTENSION_LIMITS, Q = BigInt(state.denominator);
  const prefix = state.prefix_numerators;
  if (prefix.length >= L.max_prefix_entries) fail("prefix-entry cap reached");
  const previousMaximum = prefix.length ? BigInt(prefix[prefix.length - 1]) : Q;
  if (b <= previousMaximum || b <= Q) fail("append numerator must exceed Q and every prefix numerator");
  const witnesses = [];
  for (let i = 0; i < prefix.length; i++) {
    const w = pairWitness(BigInt(prefix[i]), b, Q, i, prefix.length, work);
    witnesses.push(w);
    if (!w.valid) return { status: "INADMISSIBLE", state,
      attempted_numerator: b.toString(), new_pair_witnesses: witnesses, obstruction: w };
  }

  const M = BigInt(state.period), a = b, g = gcd(M, a, work), h = a / g;
  const nextM = M * h, lo = Q, hi = a - Q, bandSize = hi >= lo ? hi - lo + 1n : 0n;
  const groups = new Map();
  for (let i = 0; i < state.residues.length; i++) {
    const rho = mod(BigInt(state.residues[i]), g).toString();
    let group = groups.get(rho);
    if (!group) {
      const first = lo + mod(BigInt(rho) - lo, g);
      const count = bandSize !== 0n && first <= hi ? (hi - first) / g + 1n : 0n;
      group = { residue_mod_gcd: rho, old_residue_indices: [],
        first_compatible_band_residue: count ? first.toString() : null,
        compatible_band_count: count.toString(),
        incompatible_band_count: (bandSize - count).toString() };
      groups.set(rho, group);
    }
    group.old_residue_indices.push(i);
  }
  const classes = Array.from(groups.values()).sort((x, y) =>
    BigInt(x.residue_mod_gcd) < BigInt(y.residue_mod_gcd) ? -1 :
    BigInt(x.residue_mod_gcd) > BigInt(y.residue_mod_gcd) ? 1 : 0);
  work.gcd_classes_constructed += classes.length;
  let prospective = 0n;
  for (const c of classes) prospective += BigInt(c.old_residue_indices.length) * BigInt(c.compatible_band_count);
  const incompatible = BigInt(state.residues.length) * bandSize - prospective;
  const plan = { step_number: prefix.length + 1, operation_source_id: id,
    input_source: { source_id: state.source_id, prefix_count: prefix.length,
      period: state.period, residue_count: state.residues.length },
    appended_numerator: a.toString(), band: [lo.toString(), hi.toString()],
    band_size: bandSize.toString(), gcd: g.toString(),
    reduced_left_modulus: (M / g).toString(), reduced_right_modulus: h.toString(),
    output_period: nextM.toString(), prospective_residue_count: prospective.toString(),
    incompatible_pair_count: incompatible.toString(), gcd_classes: classes };
  let cap = null;
  if (nextM.toString().length > L.period_digits) cap = "PERIOD_DIGIT_CAP";
  else if (prospective > BigInt(L.max_residues)) cap = "RESIDUE_CAP";
  else if (BigInt(retainedJoinCount(state)) + prospective > BigInt(L.max_retained_join_rows))
    cap = "RETAINED_JOIN_CAP";
  if (cap) return { status: "CAP_STOP", reason: cap, state,
    attempted_numerator: b.toString(), new_pair_witnesses: witnesses, planned_step: plan };

  const inverse = h === 1n ? null : inverseCertificate(M / g, h, work);
  const inv = inverse ? BigInt(inverse.inverse) : 0n;
  const joined = [];
  for (const c of classes) {
    const count = Number(BigInt(c.compatible_band_count));
    for (const oldIndex of c.old_residue_indices) {
      const r = BigInt(state.residues[oldIndex]);
      let t = c.first_compatible_band_residue === null ? 0n : BigInt(c.first_compatible_band_residue);
      for (let j = 0; j < count; j++, t += g) {
        const u = h === 1n ? 0n : mod(((t - r) / g) * inv, h);
        joined.push({ oldIndex, t, u, value: r + M * u });
        work.compatible_join_rows_constructed++;
      }
    }
  }
  joined.sort((x, y) => x.value < y.value ? -1 : x.value > y.value ? 1 : 0);
  const residues = joined.map(x => x.value.toString());
  const step = Object.assign(plan, { inverse_certificate: inverse,
    joins: joined.map(x => [x.oldIndex, x.t.toString(), x.u.toString(), x.value.toString()]),
    output_residues: residues });
  work.new_crt_steps++;
  const next = { schema: SCHEMA, source_id: id, denominator: state.denominator,
    prefix_numerators: prefix.concat(a.toString()), period: nextM.toString(),
    residues, pair_witnesses: state.pair_witnesses.concat(witnesses),
    stages: state.stages.concat(step) };
  return { status: "COMPLETE", state: next, appended_numerator: a.toString(),
    new_pair_witnesses: witnesses, completed_step_number: step.step_number };
}

function validateSaved(raw, work) {
  const L = GRID_EXTENSION_LIMITS, s = clone(object(raw, "saved index"));
  if (s.schema !== SCHEMA) fail("unsupported saved-index schema");
  sourceId(s.source_id);
  const Q = savedNatural(s.denominator, L.denominator_digits, "denominator");
  if (Q < 1n) fail("denominator must be positive");
  const prefix = array(s.prefix_numerators, "prefix_numerators", L.max_prefix_entries);
  let last = Q;
  for (const p of prefix) {
    const b = savedNatural(p, L.numerator_digits, "prefix numerator");
    if (b <= last) fail("saved prefix must be strictly increasing above Q");
    last = b;
  }
  array(s.stages, "stages", L.max_prefix_entries);
  if (s.stages.length !== prefix.length) fail("one saved stage is required per prefix entry");
  let oldPeriod = "1", oldResidues = ["0"], previousSource = null, joinTotal = 0;
  function residueList(rows, period, name) {
    array(rows, name, L.max_residues);
    const M = savedNatural(period, L.period_digits, name + " period");
    if (M < 1n) fail("saved period must be positive");
    let previous = -1n;
    for (const r of rows) {
      const n = savedNatural(r, L.period_digits, name + " entry");
      if (n <= previous || n >= M) fail("saved residues must be distinct, sorted and canonical");
      previous = n; work.structural_residue_rows_read++;
    }
  }
  for (let k = 0; k < s.stages.length; k++) {
    const st = object(s.stages[k], "stage"), input = object(st.input_source, "input_source");
    work.structural_stage_rows_read++;
    if (st.step_number !== k + 1 || st.appended_numerator !== prefix[k] ||
        input.prefix_count !== k || input.period !== oldPeriod ||
        input.residue_count !== oldResidues.length) fail("saved stage chain is inconsistent");
    sourceId(st.operation_source_id); sourceId(input.source_id);
    if (previousSource !== null && input.source_id !== previousSource) fail("saved source chain is inconsistent");
    array(st.band, "band", 2);
    if (st.band.length !== 2 || st.band[0] !== s.denominator) fail("saved band shape is inconsistent");
    savedNatural(st.band[1], L.numerator_digits, "band upper bound");
    savedNatural(st.band_size, L.numerator_digits, "band_size");
    const g = savedNatural(st.gcd, L.numerator_digits, "gcd");
    const h = savedNatural(st.reduced_right_modulus, L.numerator_digits, "reduced_right_modulus");
    if (g < 1n || h < 1n) fail("saved reduced moduli must be positive");
    savedNatural(st.reduced_left_modulus, L.period_digits, "reduced_left_modulus");
    savedNatural(st.prospective_residue_count, L.numerator_digits + 8, "prospective count");
    savedNatural(st.incompatible_pair_count, L.numerator_digits + 8, "incompatible count");
    if (st.inverse_certificate !== null) {
      const ic = object(st.inverse_certificate, "inverse_certificate");
      savedNatural(ic.inverse, L.numerator_digits, "inverse");
      savedSigned(ic.left_coefficient, L.period_digits + 1, "left coefficient");
      savedSigned(ic.right_coefficient, L.period_digits + 1, "right coefficient");
      if (ic.gcd !== "1") fail("saved inverse gcd field must equal one");
    }
    const classes = array(st.gcd_classes, "gcd_classes", L.max_residues), seen = new Set();
    for (const c0 of classes) {
      const c = object(c0, "gcd class");
      const rho = savedNatural(c.residue_mod_gcd, L.numerator_digits, "gcd-class residue");
      if (rho >= g) fail("gcd-class residue is not canonical");
      array(c.old_residue_indices, "old_residue_indices", L.max_residues);
      if (c.old_residue_indices.length === 0) fail("saved gcd class must reference an input residue");
      for (const i of c.old_residue_indices) {
        small(i, oldResidues.length - 1, "old residue index");
        if (seen.has(i)) fail("duplicate saved gcd-class input reference");
        seen.add(i);
      }
      if (c.first_compatible_band_residue !== null)
        savedNatural(c.first_compatible_band_residue, L.numerator_digits, "first compatible residue");
      savedNatural(c.compatible_band_count, L.numerator_digits, "compatible count");
      savedNatural(c.incompatible_band_count, L.numerator_digits, "incompatible count");
    }
    if (seen.size !== oldResidues.length) fail("saved gcd classes do not cover input residue indices");
    const joins = array(st.joins, "joins", L.max_residues);
    joinTotal += joins.length;
    if (joinTotal > L.max_retained_join_rows) fail("saved total join cap exceeded");
    residueList(st.output_residues, st.output_period, "output_residues");
    if (st.output_residues.length !== joins.length ||
        st.prospective_residue_count !== String(joins.length)) fail("saved join/output lengths differ");
    for (let j = 0; j < joins.length; j++) {
      const row = array(joins[j], "join row", 4);
      if (row.length !== 4 || row[3] !== st.output_residues[j]) fail("saved join/output row differs");
      small(row[0], oldResidues.length - 1, "join input index");
      savedNatural(row[1], L.numerator_digits, "join band residue");
      const u = savedNatural(row[2], L.numerator_digits, "join multiplier");
      if (u >= h) fail("saved join multiplier is out of range");
      work.structural_join_rows_read++;
    }
    oldPeriod = st.output_period; oldResidues = st.output_residues;
    previousSource = st.operation_source_id;
  }
  if (s.period !== oldPeriod || JSON.stringify(s.residues) !== JSON.stringify(oldResidues))
    fail("saved final period/residues do not match the last stage");
  if (previousSource !== null && s.source_id !== previousSource) fail("saved final source_id differs");
  residueList(s.residues, s.period, "residues");
  const pairs = array(s.pair_witnesses, "pair_witnesses", L.max_prefix_entries * (L.max_prefix_entries - 1) / 2);
  if (pairs.length !== prefix.length * (prefix.length - 1) / 2) fail("saved pair-record count differs");
  const pairIds = new Set();
  for (const w0 of pairs) {
    const w = object(w0, "pair witness");
    const i = small(w.left_index, prefix.length - 1, "left_index");
    const j = small(w.right_index, prefix.length - 1, "right_index");
    if (i >= j || w.a_numerator !== prefix[i] || w.b_numerator !== prefix[j] ||
        w.valid !== true || w.violating_multiplier !== null) fail("saved pair-record structure differs");
    const key = i + "," + j;
    if (pairIds.has(key)) fail("duplicate saved pair reference");
    pairIds.add(key);
    for (const key of ["quotient", "remainder", "lower_multiple", "upper_multiple", "lower_distance", "upper_distance"])
      savedNatural(w[key], L.numerator_digits + 1, key);
    work.structural_pair_rows_read++;
  }
  return s;
}

function makeIndex(state, work) {
  const L = GRID_EXTENSION_LIMITS, Q = BigInt(state.denominator), M = BigInt(state.period);
  const R = state.residues.map(BigInt), size = BigInt(R.length);
  work.runtime_residue_values_indexed += R.length;
  const lower = (state.prefix_numerators.length ?
    BigInt(state.prefix_numerators[state.prefix_numerators.length - 1]) : Q) + 1n;
  function upperBound(x) {
    let lo = 0, hi = R.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1; work.query_binary_search_steps++;
      if (R[mid] <= x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }
  function cumulative(x) {
    if (x < 0n || R.length === 0) return 0n;
    return (x / M) * size + BigInt(upperBound(x % M));
  }
  let offset = null;
  function beforeLower() {
    if (offset === null) offset = cumulative(lower - 1n);
    return offset;
  }
  function selected(rank) {
    if (size === 0n) return { status: "EMPTY", rank: rank.toString() };
    const ordinal = beforeLower() + rank, periodIndex = ordinal / size;
    const residueIndex = Number(ordinal % size), b = periodIndex * M + R[residueIndex];
    return { status: "FOUND", rank: rank.toString(), numerator: b.toString(),
      denominator: state.denominator, period_index: periodIndex.toString(),
      residue_index: residueIndex, residue: state.residues[residueIndex] };
  }
  const api = {
    summary() {
      return { schema: SCHEMA, source_id: state.source_id, denominator: state.denominator,
        prefix_numerators: state.prefix_numerators.slice(), prefix_size: state.prefix_numerators.length,
        period: state.period, real_period: { numerator: state.period, denominator: state.denominator },
        residue_count: R.length, minimum_candidate_numerator: lower.toString(),
        complete_for_stated_prefix: true, empty_candidate_set: R.length === 0,
        grid_frequency: { numerator: String(R.length), denominator: state.period },
        pair_witness_count: state.pair_witnesses.length, crt_stage_count: state.stages.length,
        retained_join_count: retainedJoinCount(state),
        interpretation: "individual larger additions to this prefix, not mutual compatibility of all candidates" };
    },
    lookup(numerator) {
      work.query_calls++;
      const b = natural(numerator, L.query_digits, "query numerator");
      if (b < lower) return { status: "NOT_LARGER", numerator: b.toString(),
        minimum_candidate_numerator: lower.toString() };
      const r = b % M, upper = upperBound(r), i = upper - 1;
      if (i < 0 || R[i] !== r) return { status: "EXCLUDED", numerator: b.toString(),
        residue: r.toString(), period: state.period };
      return { status: "CANDIDATE", numerator: b.toString(), denominator: state.denominator,
        residue: r.toString(), residue_index: i, period_index: (b / M).toString(),
        rank: ((b / M) * size + BigInt(upper) - beforeLower() - 1n).toString() };
    },
    countThrough(numerator) {
      work.query_calls++;
      const b = natural(numerator, L.query_digits, "upper numerator");
      return { upper_numerator_inclusive: b.toString(), denominator: state.denominator,
        count: (b < lower ? 0n : cumulative(b) - beforeLower()).toString() };
    },
    countInRange(low, high) {
      work.query_calls++;
      const a = natural(low, L.query_digits, "lower numerator");
      const b = natural(high, L.query_digits, "upper numerator");
      if (a > b) fail("range must be increasing");
      const effective = a > lower ? a : lower;
      return { lower_numerator_inclusive: a.toString(), upper_numerator_inclusive: b.toString(),
        denominator: state.denominator, count: (b < effective ? 0n : cumulative(b) - cumulative(effective - 1n)).toString() };
    },
    select(rank) {
      work.query_calls++;
      return selected(natural(rank, L.rank_digits, "rank"));
    },
    rank(numerator) { return api.lookup(numerator); },
    page(startRank, limit) {
      work.query_calls++;
      const r = natural(startRank, L.rank_digits, "start rank");
      small(limit, L.max_page_size, "page limit");
      if (limit < 1) fail("page limit must be positive");
      if ((r + BigInt(limit)).toString().length > L.rank_digits) fail("page endpoint exceeds rank-digit cap");
      const rows = [];
      if (size !== 0n) for (let i = 0; i < limit; i++) rows.push(selected(r + BigInt(i)));
      return { start_rank: r.toString(), rows, next_rank: (r + BigInt(rows.length)).toString(),
        has_more: size !== 0n };
    },
    append(request) {
      object(request, "append request");
      const b = natural(request.numerator, L.numerator_digits, "append numerator");
      const id = sourceId(request.source_id);
      work.public_append_attempts++;
      const result = extendState(state, b, id, work), output = Object.assign({}, result);
      delete output.state;
      // Returned witness/plan records must not expose the child's retained state.
      const publicOutput = clone(output);
      publicOutput.index = result.status === "COMPLETE" ? makeIndex(result.state, work) : api;
      return publicOutput;
    },
    snapshot() { return clone(state); },
    work() { return clone(work); }
  };
  return Object.freeze(api);
}

function compileRationalGridExtensionIndex(request) {
  const L = GRID_EXTENSION_LIMITS;
  object(request, "compile request");
  const Q = natural(request.denominator, L.denominator_digits, "denominator");
  if (Q < 1n) fail("denominator must be positive");
  const id = sourceId(request.source_id);
  const input = array(request.prefix_numerators, "prefix_numerators", L.max_prefix_entries);
  const nums = Array.from(new Set(input.map(x => natural(x, L.numerator_digits, "prefix numerator").toString())))
    .map(BigInt).sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
  if (nums.some(x => x <= Q)) fail("every prefix value must be greater than one");
  const work = freshWork("compile"); work.compiler_calls = 1;
  let state = emptyState(Q, id), stopped = null;
  for (const b of nums) {
    const r = extendState(state, b, id, work);
    if (r.status !== "COMPLETE") { stopped = Object.assign({}, r); delete stopped.state; break; }
    state = r.state;
  }
  return { status: stopped ? stopped.status : "COMPLETE",
    requested_prefix_numerators: nums.map(String), consumed_prefix_count: state.prefix_numerators.length,
    stopped, index: makeIndex(state, work) };
}
function openRetainedRationalGridExtensionIndex(snapshot) {
  const work = freshWork("retained");
  return makeIndex(validateSaved(snapshot, work), work);
}

module.exports = { compileRationalGridExtensionIndex, openRetainedRationalGridExtensionIndex,
  GRID_EXTENSION_LIMITS };
