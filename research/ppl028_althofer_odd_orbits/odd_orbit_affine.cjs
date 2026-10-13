"use strict";

// Positive odd accelerated Xn+1 orbits, saved dyadic affine blocks, finite seed classes.
// Source map: Ingo Althofer, https://althofer.de/collatz-prizes.html.
// A finite prefix, its maximum, and a budget stop make no divergence claim.

const SCHEMA = "commons.odd_orbit_affine/v1";
const LIMITS = Object.freeze({
  max_multiplier: 65535, max_odd_steps: 512, max_steps_per_advance: 256,
  max_value_bits: 8192, max_coefficient_bits: 16384, max_result_bits: 32768,
  max_cumulative_halvings: 16382, max_decimal_query_digits: 1024,
  max_sessions: 32, max_events_per_session: 256, max_advances: 64,
  max_cached_ranges: 128, max_page: 64, max_source_id_chars: 512,
  max_copy_items: 4000000, max_copy_chars: 32000000, max_copy_depth: 48
});
function fail(code, message) { const error = new Error(message); error.code = code; throw error; }
function object(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    fail("INVALID_INPUT", name + " must be an object");
  return value;
}
function integer(value, low, high, name) {
  if (!Number.isSafeInteger(value) || value < low || value > high)
    fail("INVALID_INPUT", name + " must be a safe integer in [" + low + "," + high + "]");
  return value;
}
function sourceId(value) {
  if (typeof value !== "string" || !value.length || value.length > LIMITS.max_source_id_chars)
    fail("INVALID_INPUT", "source_id must be a nonempty bounded string");
  return value;
}
function copy(input) {
  let items = 0, chars = 0;
  function walk(value, depth) {
    if (++items > LIMITS.max_copy_items || depth > LIMITS.max_copy_depth)
      fail("COPY_LIMIT", "aggregate copy item/depth bound exceeded");
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) fail("INVALID_RECORD", "nonfinite number");
      return value;
    }
    if (typeof value === "string") {
      chars += value.length;
      if (chars > LIMITS.max_copy_chars) fail("COPY_LIMIT", "aggregate copy character bound exceeded");
      return value;
    }
    if (Array.isArray(value)) return value.map(x => walk(x, depth + 1));
    if (typeof value !== "object") fail("INVALID_RECORD", "only JSON values are supported");
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) fail("INVALID_RECORD", "nonplain object");
    const result = {};
    for (const key of Object.keys(value)) {
      chars += key.length;
      if (chars > LIMITS.max_copy_chars) fail("COPY_LIMIT", "aggregate copy character bound exceeded");
      Object.defineProperty(result, key, {
        value: walk(value[key], depth + 1), enumerable: true, writable: true, configurable: true
      });
    }
    return result;
  }
  return walk(input, 0);
}
function workRecord() {
  return {
    multiplications: 0, additions: 0, subtractions: 0, divisions: 0, remainders: 0,
    left_shifts: 0, right_shifts: 0, bit_length_inspections: 0,
    trailing_zero_bit_tests: 0, total_halvings: 0, odd_transitions: 0,
    leaf_blocks: 0, internal_blocks: 0, anchor_equalities: 0,
    cycle_lookups: 0, new_seen_entries: 0, saved_seen_entries_loaded: 0,
    query_calls: 0, range_cache_hits: 0, new_range_caches: 0,
    block_nodes_visited: 0, blocks_selected: 0, range_compositions: 0,
    binary_steps: 0, interval_counts: 0, seed_jumps: 0, progression_images: 0,
    returned_records: 0
  };
}
function plus(a, b, work) { work.additions++; return a + b; }
function minus(a, b, work) { work.subtractions++; return a - b; }
function times(a, b, work) { work.multiplications++; return a * b; }
function quotient(a, b, work) { work.divisions++; return a / b; }
function remainder(a, b, work) { work.remainders++; return a % b; }
function left(a, amount, work) { work.left_shifts++; return a << BigInt(amount); }
function right(a, amount, work) { work.right_shifts++; return a >> BigInt(amount); }
function bits(value, work) { if (work) work.bit_length_inspections++; return value.toString(2).length; }
function addWork(total, delta) { for (const key of Object.keys(delta)) total[key] += delta[key]; }
function decimal(value, name, positive, odd) {
  if (typeof value !== "string" || value.length > LIMITS.max_decimal_query_digits ||
      !/^(?:0|[1-9][0-9]*)$/.test(value))
    fail("INVALID_INPUT", name + " must be a bounded canonical unsigned decimal string");
  if (positive && value === "0") fail("INVALID_INPUT", name + " must be positive");
  if (odd && !/[13579]$/.test(value)) fail("INVALID_INPUT", name + " must be odd");
  return BigInt(value);
}
function checkedBits(value, maximum, name, work) {
  const length = bits(value, work);
  if (length > maximum) fail("BIT_LIMIT", name + " exceeds its bit bound");
  return length;
}
function affineData(A, B, shift, anchor, expected, work, verifyAnchor) {
  checkedBits(A, LIMITS.max_coefficient_bits, "affine A", work);
  checkedBits(B, LIMITS.max_coefficient_bits, "affine B", work);
  integer(shift, 0, LIMITS.max_cumulative_halvings, "affine shift");
  const modulus = left(1n, shift + 1, work);
  const residue = remainder(anchor, modulus, work);
  let anchorRecord = null;
  if (verifyAnchor) {
    const numerator = plus(times(A, anchor, work), B, work);
    checkedBits(numerator, LIMITS.max_result_bits, "anchor numerator", work);
    const output = right(numerator, shift, work); work.anchor_equalities++;
    if (output !== expected) fail("INTERNAL_INVARIANT", "new affine block anchor mismatch");
    anchorRecord = { input: anchor.toString(), numerator: numerator.toString(),
      output: output.toString(), expected_output: expected.toString(), matches: true };
  }
  return { A: A.toString(), B: B.toString(), shift,
    cylinder: { modulus: modulus.toString(), modulus_exponent: shift + 1, residue: residue.toString() },
    anchor_check: anchorRecord };
}
function composeValues(first, second, work) {
  const A = times(BigInt(second.A), BigInt(first.A), work);
  const B = plus(times(BigInt(second.A), BigInt(first.B), work),
    left(BigInt(second.B), first.shift, work), work);
  const shift = first.shift + second.shift;
  integer(shift, 0, LIMITS.max_cumulative_halvings, "composed shift");
  checkedBits(A, LIMITS.max_coefficient_bits, "composed A", work);
  checkedBits(B, LIMITS.max_coefficient_bits, "composed B", work);
  return { A: A.toString(), B: B.toString(), shift };
}
function createOddOrbit(request) {
  object(request, "request");
  const id = sourceId(request.source_id);
  const multiplier = integer(request.multiplier, 5, LIMITS.max_multiplier, "multiplier");
  if (multiplier % 2 !== 1) fail("INVALID_INPUT", "multiplier must be odd");
  const start = decimal(request.start, "start", true, true);
  const work = workRecord(), startBits = checkedBits(start, LIMITS.max_value_bits, "start", work);
  work.new_seen_entries = 1;
  const data = {
    schema: SCHEMA, source_id: id, request: { source_id: id, multiplier, start: start.toString() },
    conventions: {
      domain: "positive odd integers; fixed odd multiplier at least five",
      accelerated_step: "multiply by X, add one, remove every factor of two",
      primitive_step: "one odd multiply/add operation, then one operation for each halving",
      stop_at_one: false,
      finite_scope: "a finite prefix or finite repeated-state certificate; no divergence inference",
      block_scope: "one source, fixed multiplier and contiguous observed exponent range",
      saved_semantic_premise: "retained exact transitions and affine records; opening is not independent proof authentication"
    },
    orbit: {
      status: "extendable", stop: null, transitions: [],
      states: [{ index: 0, value: start.toString(), value_bits: startBits,
        primitive_step: 0, new_record_high: true }],
      seen_first: [{ value: start.toString(), odd_index: 0 }],
      total_halvings: 0, total_primitive_steps: 0,
      maximum: { value: start.toString(), odd_index: 0, value_bits: startBits },
      minimum: { value: start.toString(), odd_index: 0, value_bits: startBits },
      blocks: [], forest: [], advances: [], work: workRecord()
    },
    ranges: [], construction_work: work, sessions: []
  };
  return makeEngine(data, id, { kind: "constructor", validation: null });
}
function appendBlock(data, transition, work) {
  const orbit = data.orbit, index = transition.index;
  const start = BigInt(transition.input), end = BigInt(transition.output);
  const leafId = orbit.blocks.length;
  const leafAffine = affineData(BigInt(data.request.multiplier), 1n, transition.halvings,
    start, end, work, false);
  const leaf = {
    id: leafId, start: index, end: index + 1, length: 1, level: 0,
    left_child: null, right_child: null,
    observed_start: transition.input, observed_end: transition.output,
    primitive_start: transition.primitive_start, primitive_end: transition.primitive_end,
    ...leafAffine,
    anchor_check: { kind: "retained_transition", transition_index: index,
      input: transition.input, numerator: transition.raw_value, output: transition.output, matches: true }
  };
  orbit.blocks.push(leaf); orbit.forest.push(leafId); work.leaf_blocks++;
  while (orbit.forest.length >= 2) {
    const rightId = orbit.forest[orbit.forest.length - 1], leftId = orbit.forest[orbit.forest.length - 2];
    const first = orbit.blocks[leftId], second = orbit.blocks[rightId];
    if (first.length !== second.length) break;
    if (first.end !== second.start || first.observed_end !== second.observed_start)
      fail("INTERNAL_INVARIANT", "noncontiguous dyadic block composition");
    const combined = composeValues(first, second, work);
    const affine = affineData(BigInt(combined.A), BigInt(combined.B), combined.shift,
      BigInt(first.observed_start), BigInt(second.observed_end), work, true);
    const id = orbit.blocks.length;
    orbit.blocks.push({ id, start: first.start, end: second.end,
      length: first.length + second.length, level: first.level + 1,
      left_child: leftId, right_child: rightId,
      observed_start: first.observed_start, observed_end: second.observed_end,
      primitive_start: first.primitive_start, primitive_end: second.primitive_end,
      ...affine });
    orbit.forest.pop(); orbit.forest.pop(); orbit.forest.push(id); work.internal_blocks++;
  }
}
function extendDraft(data, requested) {
  const orbit = data.orbit, work = workRecord();
  if (orbit.advances.length >= LIMITS.max_advances) fail("ADVANCE_LIMIT", "advance history is full");
  const before = { transitions: orbit.transitions.length, states: orbit.states.length,
    blocks: orbit.blocks.length, forest: orbit.forest.slice(), status: orbit.status,
    total_halvings: orbit.total_halvings, total_primitive_steps: orbit.total_primitive_steps };
  const seen = new Map(orbit.seen_first.map(row => [row.value, row.odd_index]));
  work.saved_seen_entries_loaded = seen.size;
  const X = BigInt(data.request.multiplier);
  for (let added = 0; added < requested && orbit.status === "extendable"; added++) {
    if (orbit.transitions.length >= LIMITS.max_odd_steps) {
      orbit.status = "bound_reached"; orbit.stop = { kind: "total_odd_step_limit",
        completed_odd_steps: orbit.transitions.length }; break;
    }
    const prior = orbit.states[orbit.states.length - 1], value = BigInt(prior.value);
    const raw = plus(times(X, value, work), 1n, work);
    const binary = raw.toString(2); work.bit_length_inspections++;
    if (binary.length > LIMITS.max_value_bits) {
      orbit.status = "bound_reached";
      orbit.stop = { kind: "raw_value_bit_limit", attempted_odd_index: prior.index + 1,
        input: prior.value, raw_value: raw.toString(), raw_value_bits: binary.length };
      break;
    }
    let halvings = 0;
    for (let at = binary.length - 1; at >= 0; at--) {
      work.trailing_zero_bit_tests++;
      if (binary[at] !== "0") break;
      halvings++;
    }
    if (halvings < 1) fail("INTERNAL_INVARIANT", "odd X and odd n did not produce an even numerator");
    if (orbit.total_halvings + halvings > LIMITS.max_cumulative_halvings) {
      orbit.status = "bound_reached";
      orbit.stop = { kind: "cumulative_halving_limit", attempted_odd_index: prior.index + 1,
        input: prior.value, raw_value: raw.toString(), halvings,
        prior_total_halvings: orbit.total_halvings };
      break;
    }
    const next = right(raw, halvings, work);
    const nextBits = checkedBits(next, LIMITS.max_value_bits, "new odd value", work);
    const index = orbit.transitions.length, primitiveEnd = prior.primitive_step + 1 + halvings;
    const transition = { index, input: prior.value, raw_value: raw.toString(),
      raw_value_bits: binary.length, halvings, output: next.toString(),
      primitive_start: prior.primitive_step, primitive_raw_step: prior.primitive_step + 1,
      primitive_end: primitiveEnd };
    orbit.transitions.push(transition);
    const newHigh = next > BigInt(orbit.maximum.value);
    orbit.states.push({ index: index + 1, value: next.toString(), value_bits: nextBits,
      primitive_step: primitiveEnd, new_record_high: newHigh });
    orbit.total_halvings += halvings; orbit.total_primitive_steps = primitiveEnd;
    work.odd_transitions++; work.total_halvings += halvings;
    if (newHigh) orbit.maximum = { value: next.toString(), odd_index: index + 1, value_bits: nextBits };
    if (next < BigInt(orbit.minimum.value))
      orbit.minimum = { value: next.toString(), odd_index: index + 1, value_bits: nextBits };
    appendBlock(data, transition, work);
    work.cycle_lookups++;
    if (seen.has(next.toString())) {
      const first = seen.get(next.toString());
      orbit.status = "cycle_found";
      orbit.stop = { kind: "first_repeated_odd_state", first_odd_index: first,
        repeated_odd_index: index + 1, repeated_value: next.toString(),
        preperiod_odd_steps: first, period_odd_steps: index + 1 - first,
        preperiod_primitive_steps: orbit.states[first].primitive_step,
        period_primitive_steps: primitiveEnd - orbit.states[first].primitive_step,
        first_repeat_with_distinct_prior_values: true };
    } else {
      seen.set(next.toString(), index + 1);
      orbit.seen_first.push({ value: next.toString(), odd_index: index + 1 });
      work.new_seen_entries++;
    }
  }
  if (orbit.status === "extendable" && orbit.transitions.length >= LIMITS.max_odd_steps) {
    orbit.status = "bound_reached"; orbit.stop = { kind: "total_odd_step_limit",
      completed_odd_steps: orbit.transitions.length };
  }
  addWork(orbit.work, work);
  const after = { transitions: orbit.transitions.length, states: orbit.states.length,
    blocks: orbit.blocks.length, forest: orbit.forest.slice(), status: orbit.status,
    total_halvings: orbit.total_halvings, total_primitive_steps: orbit.total_primitive_steps };
  const id = orbit.advances.length;
  const termination = orbit.status === "extendable" ? "requested_prefix_complete" : orbit.status;
  orbit.advances.push({ id, requested_odd_steps: requested, before, after,
    termination, work: copy(work) });
  return { advance_id: id, requested_odd_steps: requested,
    added_odd_steps: after.transitions - before.transitions, completed_odd_steps: after.transitions,
    state_count: after.states, block_count: after.blocks, status: orbit.status, termination,
    last_state: copy(orbit.states[orbit.states.length - 1]), maximum: copy(orbit.maximum),
    total_halvings: orbit.total_halvings, total_primitive_steps: orbit.total_primitive_steps,
    stop: copy(orbit.stop), divergence_proved: false, work };
}

function getRange(data, from, to, work) {
  const m = data.orbit.transitions.length;
  integer(from, 0, m, "from"); integer(to, from, m, "to");
  const key = from + ":" + to;
  const cached = data.ranges.find(range => range.key === key);
  if (cached) { work.range_cache_hits++; return cached; }
  if (data.ranges.length >= LIMITS.max_cached_ranges) fail("RANGE_LIMIT", "range cache is full");
  const selected = [];
  function visit(id) {
    work.block_nodes_visited++;
    const node = data.orbit.blocks[id];
    if (node.end <= from || node.start >= to) return;
    if (from <= node.start && node.end <= to) { selected.push(id); work.blocks_selected++; return; }
    if (node.left_child === null || node.right_child === null)
      fail("INTERNAL_INVARIANT", "partial overlap of an integer leaf range");
    visit(node.left_child); visit(node.right_child);
  }
  if (from !== to) for (const id of data.orbit.forest) visit(id);
  let cursor = from;
  for (const id of selected) {
    if (data.orbit.blocks[id].start !== cursor) fail("INTERNAL_INVARIANT", "range block gap");
    cursor = data.orbit.blocks[id].end;
  }
  if (cursor !== to) fail("INTERNAL_INVARIANT", "range blocks do not cover requested interval");
  const start = data.orbit.states[from].value, end = data.orbit.states[to].value;
  let affine, origin;
  if (selected.length === 0) {
    affine = { A: "1", B: "0", shift: 0,
      cylinder: { modulus: "2", modulus_exponent: 1, residue: "1" },
      anchor_check: { kind: "identity", input: start, output: end, matches: true } };
    origin = "empty_identity";
  } else if (selected.length === 1) {
    const node = data.orbit.blocks[selected[0]];
    affine = { A: node.A, B: node.B, shift: node.shift,
      cylinder: copy(node.cylinder), anchor_check: copy(node.anchor_check) };
    origin = "saved_block";
  } else {
    const first = data.orbit.blocks[selected[0]];
    let combined = { A: first.A, B: first.B, shift: first.shift };
    for (let i = 1; i < selected.length; i++) {
      combined = composeValues(combined, data.orbit.blocks[selected[i]], work);
      work.range_compositions++;
    }
    affine = affineData(BigInt(combined.A), BigInt(combined.B), combined.shift,
      BigInt(start), BigInt(end), work, true);
    origin = "new_composition_of_saved_blocks";
  }
  const range = { id: data.ranges.length, key, source_id: data.source_id,
    multiplier: data.request.multiplier, from, to, odd_steps: to - from,
    primitive_steps: data.orbit.states[to].primitive_step - data.orbit.states[from].primitive_step,
    block_ids: selected, origin, observed_start: start, observed_end: end, ...affine,
    semantic_basis: "exact recorded valuation sequence on this contiguous range",
    tail_or_divergence_claim: false };
  data.ranges.push(range); work.new_range_caches++; return range;
}
function parseInterval(args) {
  const lower = decimal(args.lower, "lower", false, false);
  const upper = decimal(args.upper, "upper", false, false);
  if (lower > upper) fail("INVALID_INPUT", "lower must not exceed upper");
  return { lower, upper };
}
function seedInterval(range, lower, upper, work) {
  work.interval_counts++;
  const modulus = BigInt(range.cylinder.modulus), residue = BigInt(range.cylinder.residue);
  const effective = lower < 1n ? 1n : lower;
  let first = residue;
  if (effective > residue) {
    const distance = minus(effective, residue, work);
    const rounded = plus(distance, minus(modulus, 1n, work), work);
    first = plus(residue, times(quotient(rounded, modulus, work), modulus, work), work);
  }
  if (effective > upper || first > upper)
    return { range_id: range.id, lower: lower.toString(), effective_lower: effective.toString(),
      upper: upper.toString(), modulus: modulus.toString(), residue: residue.toString(),
      count: "0", first: null, last: null, empty: true };
  const count = plus(quotient(minus(upper, first, work), modulus, work), 1n, work);
  const last = plus(first, times(minus(count, 1n, work), modulus, work), work);
  return { range_id: range.id, lower: lower.toString(), effective_lower: effective.toString(),
    upper: upper.toString(), modulus: modulus.toString(), residue: residue.toString(),
    count: count.toString(), first: first.toString(), last: last.toString(), empty: false };
}
function evaluateSeed(range, seed, work) {
  const modulus = BigInt(range.cylinder.modulus), expected = BigInt(range.cylinder.residue);
  const observed = remainder(seed, modulus, work);
  if (observed !== expected)
    return { range_id: range.id, seed: seed.toString(), realizes_recorded_block: false,
      expected_residue: expected.toString(), observed_residue: observed.toString(),
      numerator: null, output: null, shift: range.shift, divergence_claim: false };
  const numerator = plus(times(BigInt(range.A), seed, work), BigInt(range.B), work);
  checkedBits(numerator, LIMITS.max_result_bits, "jump numerator", work);
  const output = right(numerator, range.shift, work);
  checkedBits(output, LIMITS.max_result_bits, "jump output", work);
  work.seed_jumps++;
  return { range_id: range.id, seed: seed.toString(), realizes_recorded_block: true,
    expected_residue: expected.toString(), observed_residue: observed.toString(),
    numerator: numerator.toString(), output: output.toString(), shift: range.shift,
    accelerated_steps: range.odd_steps, primitive_steps: range.primitive_steps,
    divergence_claim: false };
}
function validateSnapshot(data) {
  object(data, "snapshot");
  if (data.schema !== SCHEMA) fail("INVALID_RECORD", "unsupported snapshot schema");
  sourceId(data.source_id); object(data.request, "request");
  if (data.request.source_id !== data.source_id) fail("INVALID_RECORD", "request source binding");
  const X = integer(data.request.multiplier, 5, LIMITS.max_multiplier, "multiplier");
  if (X % 2 !== 1) fail("INVALID_RECORD", "even multiplier");
  decimal(data.request.start, "start", true, true);
  const checks = { odd_states: 0, transitions: 0, blocks: 0, ranges: 0, seen_entries: 0,
    decimal_fields_parsed: 0, reference_checks: 0, primitive_index_relations: 0,
    power_of_two_shapes: 0, first_value_table_bindings: 0,
    orbit_steps_replayed: 0, valuations_recomputed: 0, affine_products_replayed: 0,
    residues_recomputed: 0, mathematical_proof_authenticated: false };
  function number(value, maximum, name, positive = false, odd = false) {
    if (typeof value !== "string" || value.length > 10000 || !/^(?:0|[1-9][0-9]*)$/.test(value))
      fail("INVALID_RECORD", name + " is not bounded canonical decimal");
    if (positive && value === "0") fail("INVALID_RECORD", name + " must be positive");
    if (odd && !/[13579]$/.test(value)) fail("INVALID_RECORD", name + " must be odd");
    const parsed = BigInt(value); checks.decimal_fields_parsed++;
    if (parsed.toString(2).length > maximum) fail("INVALID_RECORD", name + " exceeds bit bound");
    return parsed;
  }
  function exactLength(value, length, name) {
    if (!Array.isArray(value) || value.length !== length) fail("INVALID_RECORD", name + " length");
  }
  function ids(value, limit, name) {
    if (!Array.isArray(value)) fail("INVALID_RECORD", name + " must be an array");
    const seen = new Set();
    for (const id of value) {
      integer(id, 0, limit - 1, name + " id");
      if (seen.has(id)) fail("INVALID_RECORD", name + " repeats an id");
      seen.add(id); checks.reference_checks++;
    }
  }
  function work(value, name) {
    object(value, name);
    const expected = Object.keys(workRecord());
    if (Object.keys(value).length !== expected.length || expected.some(key => !Object.hasOwn(value, key)))
      fail("INVALID_RECORD", name + " counter keys");
    for (const key of expected)
      integer(value[key], 0, Number.MAX_SAFE_INTEGER, name + "." + key);
  }
  function affine(value, name) {
    number(value.A, LIMITS.max_coefficient_bits, name + ".A", true, true);
    number(value.B, LIMITS.max_coefficient_bits, name + ".B");
    integer(value.shift, 0, LIMITS.max_cumulative_halvings, name + ".shift");
    const cylinder = object(value.cylinder, name + ".cylinder");
    const modulus = number(cylinder.modulus, LIMITS.max_coefficient_bits, name + ".modulus", true);
    const residue = number(cylinder.residue, LIMITS.max_coefficient_bits, name + ".residue", true, true);
    if (cylinder.modulus_exponent !== value.shift + 1 || residue >= modulus)
      fail("INVALID_RECORD", "cylinder exponent or residue range");
    const binary = modulus.toString(2);
    if (!/^10+$/.test(binary) || binary.length !== cylinder.modulus_exponent + 1)
      fail("INVALID_RECORD", "cylinder modulus is not the recorded power of two");
    checks.power_of_two_shapes++;
    const anchor = object(value.anchor_check, name + ".anchor_check");
    if (anchor.matches !== true) fail("INVALID_RECORD", "anchor match field");
    number(anchor.input, LIMITS.max_value_bits, name + ".anchor.input", true, true);
    number(anchor.output, LIMITS.max_value_bits, name + ".anchor.output", true, true);
    if (anchor.numerator !== undefined)
      number(anchor.numerator, LIMITS.max_result_bits, name + ".anchor.numerator", true);
  }
  const orbit = object(data.orbit, "orbit");
  if (!["extendable", "cycle_found", "bound_reached"].includes(orbit.status))
    fail("INVALID_RECORD", "orbit status");
  if (!Array.isArray(orbit.transitions) || orbit.transitions.length > LIMITS.max_odd_steps)
    fail("INVALID_RECORD", "transition count");
  const m = orbit.transitions.length;
  exactLength(orbit.states, m + 1, "odd states");
  integer(orbit.total_halvings, 0, LIMITS.max_cumulative_halvings, "total halvings");
  integer(orbit.total_primitive_steps, 0, LIMITS.max_cumulative_halvings + LIMITS.max_odd_steps,
    "total primitive steps");
  if (orbit.states[0].value !== data.request.start || orbit.states[0].primitive_step !== 0)
    fail("INVALID_RECORD", "initial state binding");
  for (let i = 0; i <= m; i++) {
    const state = object(orbit.states[i], "odd state");
    if (state.index !== i) fail("INVALID_RECORD", "odd state index");
    number(state.value, LIMITS.max_value_bits, "odd state value", true, true);
    integer(state.value_bits, 1, LIMITS.max_value_bits, "odd state bit count");
    integer(state.primitive_step, 0, orbit.total_primitive_steps, "odd state primitive index");
    if (typeof state.new_record_high !== "boolean") fail("INVALID_RECORD", "record-high field");
    checks.odd_states++;
  }
  for (let i = 0; i < m; i++) {
    const t = object(orbit.transitions[i], "transition");
    if (t.index !== i || t.input !== orbit.states[i].value || t.output !== orbit.states[i + 1].value)
      fail("INVALID_RECORD", "transition state binding");
    number(t.raw_value, LIMITS.max_value_bits, "raw value", true);
    integer(t.raw_value_bits, 1, LIMITS.max_value_bits, "raw bit count");
    integer(t.halvings, 1, LIMITS.max_value_bits - 1, "transition halvings");
    if (t.primitive_start !== orbit.states[i].primitive_step ||
        t.primitive_raw_step !== t.primitive_start + 1 ||
        t.primitive_end !== t.primitive_start + 1 + t.halvings ||
        t.primitive_end !== orbit.states[i + 1].primitive_step)
      fail("INVALID_RECORD", "primitive address linkage");
    checks.primitive_index_relations += 4; checks.transitions++;
  }
  if (orbit.states[m].primitive_step !== orbit.total_primitive_steps ||
      orbit.total_primitive_steps !== m + orbit.total_halvings)
    fail("INVALID_RECORD", "cumulative primitive addresses");
  checks.primitive_index_relations += 2;
  for (const label of ["maximum", "minimum"]) {
    const record = object(orbit[label], label);
    integer(record.odd_index, 0, m, label + " index");
    if (record.value !== orbit.states[record.odd_index].value) fail("INVALID_RECORD", label + " state binding");
    integer(record.value_bits, 1, LIMITS.max_value_bits, label + " bits"); checks.reference_checks++;
  }
  if (!Array.isArray(orbit.blocks) || orbit.blocks.length > 2 * LIMITS.max_odd_steps)
    fail("INVALID_RECORD", "block count");
  const B = orbit.blocks.length, leaves = new Set();
  for (let i = 0; i < B; i++) {
    const block = object(orbit.blocks[i], "block");
    if (block.id !== i) fail("INVALID_RECORD", "block id");
    integer(block.start, 0, m, "block start"); integer(block.end, block.start + 1, m, "block end");
    integer(block.level, 0, 9, "block level");
    if (block.length !== block.end - block.start || block.length !== 2 ** block.level)
      fail("INVALID_RECORD", "dyadic length");
    if (block.observed_start !== orbit.states[block.start].value ||
        block.observed_end !== orbit.states[block.end].value ||
        block.primitive_start !== orbit.states[block.start].primitive_step ||
        block.primitive_end !== orbit.states[block.end].primitive_step)
      fail("INVALID_RECORD", "block observed state binding");
    if (block.shift !== block.primitive_end - block.primitive_start - block.length)
      fail("INVALID_RECORD", "block exponent/address linkage");
    checks.primitive_index_relations++;
    affine(block, "block");
    if (block.anchor_check.input !== block.observed_start || block.anchor_check.output !== block.observed_end)
      fail("INVALID_RECORD", "block anchor binding");
    if (block.level === 0) {
      if (block.left_child !== null || block.right_child !== null ||
          block.A !== String(X) || block.B !== "1" ||
          block.shift !== orbit.transitions[block.start].halvings ||
          block.anchor_check.transition_index !== block.start ||
          block.anchor_check.numerator !== orbit.transitions[block.start].raw_value ||
          leaves.has(block.start)) fail("INVALID_RECORD", "leaf transition binding");
      leaves.add(block.start);
    } else {
      integer(block.left_child, 0, i - 1, "left child");
      integer(block.right_child, 0, i - 1, "right child");
      const first = orbit.blocks[block.left_child], second = orbit.blocks[block.right_child];
      if (first.start !== block.start || first.end !== second.start || second.end !== block.end ||
          first.level + 1 !== block.level || second.level !== first.level)
        fail("INVALID_RECORD", "dyadic children linkage");
      checks.reference_checks += 2;
    }
    checks.blocks++;
  }
  if (leaves.size !== m) fail("INVALID_RECORD", "missing transition leaf");
  ids(orbit.forest, B, "forest");
  let cursor = 0, previousLevel = 10;
  for (const id of orbit.forest) {
    const node = orbit.blocks[id];
    if (node.start !== cursor || node.level >= previousLevel) fail("INVALID_RECORD", "forest range/order");
    cursor = node.end; previousLevel = node.level;
  }
  if (cursor !== m) fail("INVALID_RECORD", "forest does not cover the complete prefix");
  if (!Array.isArray(orbit.seen_first) || orbit.seen_first.length > m + 1)
    fail("INVALID_RECORD", "seen table count");
  const unique = new Set();
  for (let i = 0; i < orbit.seen_first.length; i++) {
    const row = orbit.seen_first[i];
    if (row.odd_index !== i || row.value !== orbit.states[i].value || unique.has(row.value))
      fail("INVALID_RECORD", "first-value table binding");
    unique.add(row.value); checks.first_value_table_bindings++; checks.seen_entries++;
  }
  if (orbit.status === "cycle_found") {
    const stop = object(orbit.stop, "cycle stop");
    if (stop.kind !== "first_repeated_odd_state" || stop.repeated_odd_index !== m ||
        orbit.seen_first.length !== m || stop.first_repeat_with_distinct_prior_values !== true)
      fail("INVALID_RECORD", "first-repeat record");
    integer(stop.first_odd_index, 0, m - 1, "cycle start");
    if (stop.repeated_value !== orbit.states[m].value ||
        stop.repeated_value !== orbit.states[stop.first_odd_index].value ||
        stop.preperiod_odd_steps !== stop.first_odd_index ||
        stop.period_odd_steps !== m - stop.first_odd_index ||
        stop.preperiod_primitive_steps !== orbit.states[stop.first_odd_index].primitive_step ||
        stop.period_primitive_steps !== orbit.total_primitive_steps - orbit.states[stop.first_odd_index].primitive_step)
      fail("INVALID_RECORD", "cycle reference binding");
    checks.reference_checks += 2;
  } else {
    if (orbit.seen_first.length !== m + 1) fail("INVALID_RECORD", "seen table coverage");
    if (orbit.status === "extendable" && orbit.stop !== null) fail("INVALID_RECORD", "extendable stop field");
    if (orbit.status === "bound_reached") object(orbit.stop, "bound stop");
  }
  if (!Array.isArray(orbit.advances) || orbit.advances.length > LIMITS.max_advances)
    fail("INVALID_RECORD", "advance count");
  for (let i = 0; i < orbit.advances.length; i++) {
    const advance = orbit.advances[i];
    if (advance.id !== i) fail("INVALID_RECORD", "advance id");
    integer(advance.requested_odd_steps, 1, LIMITS.max_steps_per_advance, "advance request");
    ids(advance.before.forest, B, "advance before forest");
    ids(advance.after.forest, B, "advance after forest");
    work(advance.work, "advance work");
  }
  if (orbit.advances.length) {
    const last = orbit.advances[orbit.advances.length - 1].after;
    if (last.transitions !== m || last.states !== m + 1 || last.blocks !== B ||
        last.status !== orbit.status || last.total_halvings !== orbit.total_halvings ||
        JSON.stringify(last.forest) !== JSON.stringify(orbit.forest))
      fail("INVALID_RECORD", "last advance/current state");
  }
  work(orbit.work, "orbit work"); work(data.construction_work, "construction work");
  if (!Array.isArray(data.ranges) || data.ranges.length > LIMITS.max_cached_ranges)
    fail("INVALID_RECORD", "range cache count");
  const rangeKeys = new Set();
  for (let i = 0; i < data.ranges.length; i++) {
    const range = data.ranges[i];
    if (range.id !== i || range.source_id !== data.source_id || range.multiplier !== X ||
        range.key !== range.from + ":" + range.to || rangeKeys.has(range.key))
      fail("INVALID_RECORD", "range source/id binding");
    rangeKeys.add(range.key);
    integer(range.from, 0, m, "range from"); integer(range.to, range.from, m, "range to");
    if (range.odd_steps !== range.to - range.from ||
        range.observed_start !== orbit.states[range.from].value ||
        range.observed_end !== orbit.states[range.to].value)
      fail("INVALID_RECORD", "range state binding");
    ids(range.block_ids, B, "range blocks");
    let at = range.from;
    for (const id of range.block_ids) {
      const block = orbit.blocks[id];
      if (block.start !== at || block.end > range.to) fail("INVALID_RECORD", "range block cover");
      at = block.end;
    }
    if (at !== range.to) fail("INVALID_RECORD", "incomplete range block cover");
    affine(range, "range");
    if (range.primitive_steps !== orbit.states[range.to].primitive_step - orbit.states[range.from].primitive_step ||
        range.shift !== range.primitive_steps - range.odd_steps ||
        range.anchor_check.input !== range.observed_start || range.anchor_check.output !== range.observed_end)
      fail("INVALID_RECORD", "range primitive/anchor binding");
    if (range.from === range.to && (range.A !== "1" || range.B !== "0" || range.shift !== 0 ||
        range.cylinder.modulus !== "2" || range.cylinder.residue !== "1"))
      fail("INVALID_RECORD", "empty range identity");
    checks.primitive_index_relations += 2; checks.ranges++;
  }
  if (!Array.isArray(data.sessions) || data.sessions.length >= LIMITS.max_sessions)
    fail("INVALID_RECORD", "session count");
  const sources = new Set();
  for (let i = 0; i < data.sessions.length; i++) {
    const session = data.sessions[i];
    if (session.id !== i) fail("INVALID_RECORD", "session id");
    sourceId(session.source_id);
    if (sources.has(session.source_id)) fail("INVALID_RECORD", "duplicate session source");
    sources.add(session.source_id);
    if (!Array.isArray(session.queries) || !Array.isArray(session.advance_ids) ||
        session.queries.length + session.advance_ids.length > LIMITS.max_events_per_session)
      fail("INVALID_RECORD", "session events");
    ids(session.advance_ids, orbit.advances.length, "session advances");
    session.queries.forEach((query, j) => {
      if (query.id !== j || !["ok", "error"].includes(query.status)) fail("INVALID_RECORD", "query identity");
      work(query.work, "query work");
    });
    work(session.query_work, "session query work");
  }
  return checks;
}
function openOddOrbit(snapshot, options) {
  object(options, "options"); const id = sourceId(options.source_id), data = copy(snapshot);
  const validation = validateSnapshot(data);
  if (data.sessions.some(session => session.source_id === id))
    fail("INVALID_INPUT", "new session source_id already exists");
  return makeEngine(data, id, { kind: "saved_open", validation });
}

function makeEngine(initialData, id, loading) {
  sourceId(id);
  let state = copy(initialData);
  if (state.sessions.length >= LIMITS.max_sessions) fail("SESSION_LIMIT", "session history is full");
  const sessionIndex = state.sessions.length;
  state.sessions.push({ id: sessionIndex, source_id: id, kind: loading.kind,
    validation: loading.validation, queries: [], advance_ids: [], query_work: workRecord() });
  state = copy(state);
  function session(data) { return data.sessions[sessionIndex]; }
  function available() {
    const current = session(state);
    if (current.queries.length + current.advance_ids.length >= LIMITS.max_events_per_session)
      fail("EVENT_LIMIT", "session event history is full");
  }
  function page(args, length) {
    const offset = integer(args.offset, 0, length, "offset");
    const count = integer(args.limit, 1, LIMITS.max_page, "limit");
    return { offset, end: Math.min(length, offset + count), total: length };
  }
  function pageOutput(bounds, records) {
    return { offset: bounds.offset, total: bounds.total, records,
      next_offset: bounds.end < bounds.total ? bounds.end : null };
  }
  function query(method, args, operation) {
    available(); object(args, "query arguments");
    const retainedArgs = copy(args), draft = copy(state), work = workRecord(); work.query_calls = 1;
    try {
      const result = copy(operation(draft, args, work));
      const current = session(draft);
      current.queries.push({ id: current.queries.length, method, args: retainedArgs,
        status: "ok", result: copy(result), work: copy(work) });
      addWork(current.query_work, work);
      const exported = copy(draft), callerResult = copy(result);
      state = exported; return callerResult;
    } catch (error) {
      try {
        const failed = copy(state), current = session(failed);
        current.queries.push({ id: current.queries.length, method, args: retainedArgs,
          status: "error", error: { code: error.code || "QUERY_ERROR", message: error.message },
          work: copy(work) });
        addWork(current.query_work, work); state = copy(failed);
      } catch (retentionError) {
        error.retention_error = retentionError.message;
      }
      throw error;
    }
  }
  const api = {
    advance(args) {
      available(); object(args, "advance arguments");
      const requested = integer(args.odd_steps, 1, LIMITS.max_steps_per_advance, "odd_steps");
      if (state.orbit.status !== "extendable") fail("ORBIT_STOPPED", "saved orbit is not extendable");
      const draft = copy(state);
      const result = extendDraft(draft, requested);
      draft.orbit.advances[result.advance_id].session_id = sessionIndex;
      session(draft).advance_ids.push(result.advance_id);
      const exported = copy(draft), callerResult = copy(result);
      state = exported; return callerResult;
    },
    getState(args) {
      return query("getState", args, (data, input, work) => {
        const index = integer(input.odd_index, 0, data.orbit.states.length - 1, "odd_index");
        work.returned_records++; return data.orbit.states[index];
      });
    },
    pageStates(args) {
      return query("pageStates", args, (data, input, work) => {
        const bounds = page(input, data.orbit.states.length);
        const records = data.orbit.states.slice(bounds.offset, bounds.end);
        work.returned_records += records.length; return pageOutput(bounds, records);
      });
    },
    getTransition(args) {
      return query("getTransition", args, (data, input, work) => {
        const index = integer(input.odd_index, 0, data.orbit.transitions.length - 1, "odd_index");
        work.returned_records++; return data.orbit.transitions[index];
      });
    },
    pageTransitions(args) {
      return query("pageTransitions", args, (data, input, work) => {
        const bounds = page(input, data.orbit.transitions.length);
        const records = data.orbit.transitions.slice(bounds.offset, bounds.end);
        work.returned_records += records.length; return pageOutput(bounds, records);
      });
    },
    primitiveState(args) {
      return query("primitiveState", args, (data, input, work) => {
        const at = integer(input.primitive_step, 0, data.orbit.total_primitive_steps, "primitive_step");
        work.returned_records++;
        if (at === 0) return { primitive_step: 0, value: data.orbit.states[0].value,
          kind: "initial_odd_state", odd_index: 0, transition_index: null, halvings_applied: 0 };
        let low = 0, high = data.orbit.transitions.length;
        while (low < high) {
          const middle = Math.floor((low + high) / 2); work.binary_steps++;
          if (data.orbit.transitions[middle].primitive_end < at) low = middle + 1; else high = middle;
        }
        const transition = data.orbit.transitions[low];
        const offset = at - transition.primitive_start, halves = offset - 1;
        if (offset < 1 || halves > transition.halvings)
          fail("INTERNAL_INVARIANT", "primitive address did not bind a retained transition");
        const value = right(BigInt(transition.raw_value), halves, work);
        return { primitive_step: at, transition_index: low, within_transition_offset: offset,
          value: value.toString(), kind: halves === transition.halvings ? "odd_endpoint" : "even_intermediate",
          odd_index: halves === transition.halvings ? low + 1 : null,
          halvings_applied: halves, source_raw_value: transition.raw_value };
      });
    },
    getBlock(args) {
      return query("getBlock", args, (data, input, work) => {
        const id = integer(input.block_id, 0, data.orbit.blocks.length - 1, "block_id");
        work.returned_records++; return data.orbit.blocks[id];
      });
    },
    pageBlocks(args) {
      return query("pageBlocks", args, (data, input, work) => {
        const bounds = page(input, data.orbit.blocks.length);
        const records = data.orbit.blocks.slice(bounds.offset, bounds.end);
        work.returned_records += records.length; return pageOutput(bounds, records);
      });
    },
    rangeCertificate(args) {
      return query("rangeCertificate", args, (data, input, work) => {
        const range = getRange(data, input.from, input.to, work);
        work.returned_records++; return range;
      });
    },
    countSeeds(args) {
      return query("countSeeds", args, (data, input, work) => {
        const bounds = parseInterval(input);
        const range = getRange(data, input.from, input.to, work);
        work.returned_records++; return seedInterval(range, bounds.lower, bounds.upper, work);
      });
    },
    selectSeed(args) {
      return query("selectSeed", args, (data, input, work) => {
        const bounds = parseInterval(input), rank = decimal(input.rank, "rank", false, false);
        const range = getRange(data, input.from, input.to, work);
        const interval = seedInterval(range, bounds.lower, bounds.upper, work);
        work.returned_records++;
        if (rank >= BigInt(interval.count))
          return { range_id: range.id, rank: rank.toString(), interval,
            found: false, seed: null, reason: "rank_outside_interval" };
        const seed = plus(BigInt(interval.first), times(rank, BigInt(interval.modulus), work), work);
        checkedBits(seed, LIMITS.max_result_bits, "selected seed", work);
        return { range_id: range.id, rank: rank.toString(), interval, found: true, seed: seed.toString() };
      });
    },
    rankSeed(args) {
      return query("rankSeed", args, (data, input, work) => {
        const bounds = parseInterval(input), seed = decimal(input.seed, "seed", false, false);
        const range = getRange(data, input.from, input.to, work);
        const interval = seedInterval(range, bounds.lower, bounds.upper, work);
        work.returned_records++;
        if (interval.empty || seed < BigInt(interval.effective_lower) || seed > bounds.upper)
          return { range_id: range.id, seed: seed.toString(), interval,
            belongs: false, rank: null, reason: "outside_positive_interval" };
        const observed = remainder(seed, BigInt(interval.modulus), work);
        if (observed !== BigInt(interval.residue))
          return { range_id: range.id, seed: seed.toString(), interval,
            belongs: false, rank: null, reason: "different_valuation_class",
            observed_residue: observed.toString() };
        const rank = quotient(minus(seed, BigInt(interval.first), work), BigInt(interval.modulus), work);
        return { range_id: range.id, seed: seed.toString(), interval, belongs: true, rank: rank.toString() };
      });
    },
    jumpSeed(args) {
      return query("jumpSeed", args, (data, input, work) => {
        const seed = decimal(input.seed, "seed", true, true);
        const range = getRange(data, input.from, input.to, work);
        work.returned_records++; return evaluateSeed(range, seed, work);
      });
    },
    imageSeeds(args) {
      return query("imageSeeds", args, (data, input, work) => {
        const bounds = parseInterval(input);
        const range = getRange(data, input.from, input.to, work);
        const interval = seedInterval(range, bounds.lower, bounds.upper, work);
        const stride = left(BigInt(range.A), 1, work);
        work.returned_records++; work.progression_images++;
        if (interval.empty)
          return { range_id: range.id, interval, count: "0", first_output: null, last_output: null,
            output_stride: stride.toString(), finite_block_only: true };
        const first = evaluateSeed(range, BigInt(interval.first), work);
        if (!first.realizes_recorded_block) fail("INTERNAL_INVARIANT", "interval first seed missed its cylinder");
        const last = plus(BigInt(first.output),
          times(minus(BigInt(interval.count), 1n, work), stride, work), work);
        checkedBits(last, LIMITS.max_result_bits, "last progression output", work);
        return { range_id: range.id, interval, count: interval.count,
          first_input: interval.first, last_input: interval.last,
          first_output: first.output, last_output: last.toString(),
          output_stride: stride.toString(), first_jump_witness: first, finite_block_only: true };
      });
    },
    summary() {
      const orbit = state.orbit, current = session(state);
      return copy({ schema: SCHEMA, source_id: state.source_id, multiplier: state.request.multiplier,
        start: state.request.start, completed_odd_steps: orbit.transitions.length,
        odd_state_count: orbit.states.length, total_halvings: orbit.total_halvings,
        total_primitive_steps: orbit.total_primitive_steps, block_count: orbit.blocks.length,
        forest: orbit.forest, range_cache_count: state.ranges.length, status: orbit.status,
        stop: orbit.stop, last_state: orbit.states[orbit.states.length - 1],
        maximum: orbit.maximum, minimum: orbit.minimum, construction_work: state.construction_work,
        orbit_work: orbit.work, advances: orbit.advances.length, divergence_proved: false,
        session: { id: current.id, source_id: current.source_id, kind: current.kind,
          validation: current.validation, query_calls: current.queries.length,
          advance_calls: current.advance_ids.length, query_work: current.query_work } });
    },
    snapshot() { return copy(state); }
  };
  return Object.freeze(api);
}
module.exports = Object.freeze({ SCHEMA, LIMITS, createOddOrbit, openOddOrbit });
