"use strict";

/*
 * Canonical Kimberling Rule 1: a(1)=1, d(1)=0.
 * Sources: OEIS A131388 / A131389.
 * Continue an identified published prefix; never regenerate its choices.
 * Mirrored occupancy provides negative-target masks without reversal per step.
 * No imports, I/O, approximate arithmetic, or unbounded search.
 */

const GREEDY_DIFFERENCE_LIMITS = Object.freeze({
  max_terms: 16384,
  max_page_size: 128,
  max_segments: 32,
  max_source_id_chars: 1024
});
const L = GREEDY_DIFFERENCE_LIMITS;
const SCHEMA = "commons.kimberling13.greedy_difference_state/v1";
const POP4 = [0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4];

function clone(x) { return JSON.parse(JSON.stringify(x)); }
function integer(x, lo, hi, name) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) throw new RangeError(name + " outside integer contract");
  return x;
}
function sourceId(x, name) {
  if (typeof x !== "string" || !x.length || x.length > L.max_source_id_chars) throw new TypeError(name + " required");
  return x;
}
function lowPositiveMask(upper) {
  return upper <= 0 ? 0n : (1n << BigInt(upper + 1)) - 2n;
}
function bit(index) { return 1n << BigInt(index); }
function sign(x) { return x > 0 ? 1 : x < 0 ? -1 : 0; }
function freshWork(mode) {
  return {
    mode, constructor_calls: 0, retained_opens: 0, append_calls: 0,
    seed_pairs_loaded: 0, structural_history_pairs: 0, structural_prior_events: 0, structural_certificate_masks: 0,
    occurrence_entries_indexed: 0, occupancy_builds: 0, seed_bit_insertions: 0,
    saved_mask_parses: 0, snapshot_mask_serializations: 0,
    new_steps: 0, negative_searches: 0, positive_searches: 0,
    target_shift_projections: 0, availability_masks: 0, least_bit_selections: 0,
    new_bit_insertions: 0, blocking_certificates: 0, blocking_hex_characters: 0,
    completed_new_windows: 0, query_calls: 0, query_popcount_digits: 0,
    query_selection_digits: 0, query_records_decoded: 0,
    accepted_greedy_steps_recomputed: 0, prior_window_checks_recomputed: 0,
    old_masks_rebuilt_on_open: 0
  };
}
function workDelta(before, after) {
  const out = {};
  for (const k of Object.keys(after)) if (typeof after[k] === "number") out[k] = after[k] - before[k];
  return out;
}
function readHex(s, upperBit, name) {
  if (typeof s !== "string" || !/^(?:0|[1-9a-f][0-9a-f]*)$/.test(s) ||
      s.length > Math.ceil((upperBit + 1) / 4)) throw new TypeError(name + " canonical bounded hex required");
  const value = BigInt("0x" + s);
  if (value >> BigInt(upperBit + 1)) throw new RangeError(name + " bit bound");
  return value;
}
function validateHistory(positions, differences, cap, work, seeded) {
  if (!Array.isArray(positions) || !Array.isArray(differences) ||
      !positions.length || positions.length !== differences.length || positions.length > cap)
    throw new TypeError("complete paired history arrays required");
  if (positions[0] !== 1 || differences[0] !== 0) throw new Error("canonical seed must be a(1)=1,d(1)=0");
  const B = 2 * (cap - 1), A = positions.slice(), D = differences.slice(), seenA = new Set(), seenD = new Set();
  for (let i = 0; i < A.length; i++) {
    integer(A[i], 1, B, "position");
    integer(D[i], 1 - B, B - 1, "difference");
    if ((i && D[i] === 0) || seenA.has(A[i]) || seenD.has(D[i])) throw new Error("histories must contain distinct positions and signed differences");
    seenA.add(A[i]); seenD.add(D[i]);
  }
  if (seeded) work.seed_pairs_loaded += A.length; else work.structural_history_pairs += A.length;
  return { A, D };
}
function buildOccupancy(A, D, B, work) {
  work.occupancy_builds++;
  const bits = { position: 0n, mirror: 0n, positive: 0n, negative: 0n };
  for (let i = 0; i < A.length; i++) {
    bits.position |= bit(A[i]); bits.mirror |= bit(B - A[i]); work.seed_bit_insertions += 2;
    if (D[i] > 0) { bits.positive |= bit(D[i]); work.seed_bit_insertions++; }
    else if (D[i] < 0) { bits.negative |= bit(-D[i]); work.seed_bit_insertions++; }
  }
  return bits;
}
function parseOccupancy(state, work) {
  const B = state.universe_bound, h = state.bitsets;
  if (!h || typeof h !== "object") throw new TypeError("saved bitsets required");
  const bits = {
    position: readHex(h.position_hex, B, "positions"),
    mirror: readHex(h.mirrored_position_hex, B - 1, "mirrored positions"),
    positive: readHex(h.positive_difference_hex, B - 1, "positive differences"),
    negative: readHex(h.negative_difference_hex, B - 1, "negative differences")
  };
  if ((bits.position & 1n) || !(bits.position & 2n) ||
      !(bits.mirror & bit(B - 1)) || (bits.positive & 1n) || (bits.negative & 1n))
    throw new Error("canonical bitset endpoints");
  work.saved_mask_parses += 4;
  return bits;
}
function serializeOccupancy(bits, work) {
  work.snapshot_mask_serializations += 4;
  return {
    position_hex: bits.position.toString(16),
    mirrored_position_hex: bits.mirror.toString(16),
    positive_difference_hex: bits.positive.toString(16),
    negative_difference_hex: bits.negative.toString(16)
  };
}
function leastBitIndex(mask, work) {
  if (mask <= 0n) throw new Error("nonempty available mask required");
  work.least_bit_selections++;
  const low = mask & -mask, hex = low.toString(16), leading = parseInt(hex[0], 16);
  const offset = leading === 1 ? 0 : leading === 2 ? 1 : leading === 4 ? 2 : leading === 8 ? 3 : -1;
  if (offset < 0) throw new Error("least-bit power shape");
  return 4 * (hex.length - 1) + offset;
}
function blockingCertificate(direction, domainUpper, prefixUpper, chosenMagnitude, used, targets, work) {
  const prefix = lowPositiveMask(prefixUpper), usedPart = used & prefix;
  const targetPart = targets & prefix & ~used;
  if ((usedPart | targetPart) !== prefix) throw new Error("greedy blocking prefix incomplete");
  const usedHex = usedPart.toString(16), targetHex = targetPart.toString(16);
  work.blocking_certificates++; work.blocking_hex_characters += usedHex.length + targetHex.length;
  return {
    direction, domain_upper_magnitude: domainUpper,
    covered_prefix_upper_magnitude: prefixUpper, selected_magnitude: chosenMagnitude,
    used_difference_mask_hex: usedHex,
    additional_visited_destination_mask_hex: targetHex,
    disjoint_union_is_full_prefix: true
  };
}
function validateCertificate(c, B, work) {
  if (!c || (c.direction !== "negative" && c.direction !== "positive")) throw new Error("certificate direction");
  integer(c.domain_upper_magnitude, 0, B - 1, "certificate domain");
  integer(c.covered_prefix_upper_magnitude, 0, c.domain_upper_magnitude, "certificate prefix");
  if (c.selected_magnitude !== null) integer(c.selected_magnitude, 1, c.domain_upper_magnitude, "certificate selected magnitude");
  for (const key of ["used_difference_mask_hex", "additional_visited_destination_mask_hex"]) {
    readHex(c[key], c.covered_prefix_upper_magnitude, key); work.structural_certificate_masks++;
  }
  if (c.disjoint_union_is_full_prefix !== true) throw new Error("certificate flag shape");
}
function validateSaved(raw, work) {
  if (!raw || raw.schema !== SCHEMA) throw new TypeError("saved greedy-difference schema");
  const cap = integer(raw.term_cap, 2, L.max_terms, "term cap");
  if (raw.universe_bound !== 2 * (cap - 1)) throw new Error("linear universe identity");
  const hist = validateHistory(raw.positions, raw.differences, cap, work, false);
  const state = clone(raw); state.positions = hist.A; state.differences = hist.D;
  sourceId(state.source_id, "saved source id");
  if (state.parent_source_id !== null) sourceId(state.parent_source_id, "parent source id");
  const p = state.premises;
  if (!p) throw new Error("seed provenance required");
  sourceId(p.seed_source_id, "seed source id");
  integer(p.seed_size, 1, hist.A.length, "seed size");
  if (p.seed_terminal_position !== hist.A[p.seed_size - 1] || p.seed_terminal_difference !== hist.D[p.seed_size - 1])
    throw new Error("seed endpoint identity");
  if (!Array.isArray(state.events) || state.events.length !== hist.A.length - p.seed_size ||
      !Array.isArray(state.segments) || state.segments.length > L.max_segments || !state.statistics)
    throw new Error("saved event coverage");
  for (let j = 0; j < state.events.length; j++) {
    const e = state.events[j], i = p.seed_size + j + 1;
    if (!e || e.index !== i || e.previous_position !== hist.A[i - 2] ||
        e.position !== hist.A[i - 1] || e.difference !== hist.D[i - 1] ||
        !e.selected_destination_was_unused || !e.selected_difference_was_unused)
      throw new Error("saved event identity");
    validateCertificate(e.negative_search, state.universe_bound, work);
    if (e.positive_search !== null) validateCertificate(e.positive_search, state.universe_bound, work);
    if (i >= 4) {
      const w = e.completed_window;
      if (!w || w.start_index !== i - 3 || !Array.isArray(w.signs) || w.signs.length !== 4 ||
          !Array.isArray(w.same_sign_future_offsets)) throw new Error("saved completed-window shape");
      for (const s of w.signs) integer(s, -1, 1, "saved window sign");
    } else if (e.completed_window !== null) throw new Error("early window must be absent");
    work.structural_prior_events++;
  }
  if (state.statistics.new_steps !== state.events.length ||
      !Array.isArray(state.statistics.window_violations)) throw new Error("saved statistics shape");
  return state;
}
function makeIndex(state, work, initialBits) {
  const A = state.positions, D = state.differences, B = state.universe_bound;
  const bits = initialBits || parseOccupancy(state, work);
  const positionIndex = new Map(A.map((v, i) => [v, i + 1]));
  const differenceIndex = new Map(D.map((v, i) => [v, i + 1]));
  work.occurrence_entries_indexed += A.length + D.length;
  let dirty = Boolean(initialBits);
  function sync() {
    if (dirty) { state.bitsets = serializeOccupancy(bits, work); dirty = false; }
  }
  function summary() {
    return {
      source_id: state.source_id, parent_source_id: state.parent_source_id,
      seed_size: state.premises.seed_size, size: A.length, term_cap: state.term_cap,
      universe_bound: B, terminal_position: A[A.length - 1], terminal_difference: D[D.length - 1],
      statistics: clone(state.statistics),
      new_completed_window_starts: {
        first: Math.max(1, state.premises.seed_size - 2),
        last: A.length - 3,
        scope: "only windows whose fourth term is newly appended"
      },
      uncompleted_starts_at_end: [Math.max(1, A.length - 2), A.length],
      segments: state.segments.length
    };
  }
  function oneStep() {
    const k = A.length, x = A[k - 1], index = k + 1;
    const negativeUpper = Math.max(0, x - 2);
    const negativeTargets = bits.mirror >> BigInt(B - x);
    work.negative_searches++; work.target_shift_projections++; work.availability_masks++;
    const availableNegative = lowPositiveMask(negativeUpper) & ~(bits.negative | negativeTargets);
    let h, negativeSearch, positiveSearch = null;
    if (availableNegative) {
      const magnitude = leastBitIndex(availableNegative, work); h = -magnitude;
      negativeSearch = blockingCertificate("negative", negativeUpper, magnitude - 1, magnitude,
        bits.negative, negativeTargets, work);
    } else {
      negativeSearch = blockingCertificate("negative", negativeUpper, negativeUpper, null,
        bits.negative, negativeTargets, work);
      const positiveUpper = B - x, positiveTargets = bits.position >> BigInt(x);
      work.positive_searches++; work.target_shift_projections++; work.availability_masks++;
      const availablePositive = lowPositiveMask(positiveUpper) & ~(bits.positive | positiveTargets);
      if (!availablePositive) throw new Error("no positive move in proved linear universe; invalid seed or state");
      const magnitude = leastBitIndex(availablePositive, work); h = magnitude;
      positiveSearch = blockingCertificate("positive", positiveUpper, magnitude - 1, magnitude,
        bits.positive, positiveTargets, work);
    }
    const y = x + h, magnitude = Math.abs(h), used = h > 0 ? bits.positive : bits.negative;
    if (!Number.isSafeInteger(y) || y < 2 || y > B || y > 2 * k ||
        (bits.position & bit(y)) || (used & bit(magnitude)))
      throw new Error("new step violates canonical choice or linear bound");

    A.push(y); D.push(h); positionIndex.set(y, index); differenceIndex.set(h, index);
    bits.position |= bit(y); bits.mirror |= bit(B - y);
    if (h > 0) bits.positive |= bit(h); else bits.negative |= bit(-h);
    dirty = true; work.new_bit_insertions += 3; work.new_steps++;
    const stat = state.statistics; stat.new_steps++;
    if (h > 0) stat.new_positive_steps++; else stat.new_negative_steps++;
    stat.maximum_new_position = stat.maximum_new_position === null ? y : Math.max(stat.maximum_new_position, y);
    stat.maximum_new_step_magnitude = stat.maximum_new_step_magnitude === null ? magnitude : Math.max(stat.maximum_new_step_magnitude, magnitude);

    let window = null;
    if (index >= 4) {
      const signs = D.slice(index - 4, index).map(sign), initialSign = signs[0], offsets = [];
      for (let q = 1; q <= 3; q++) if (signs[q] === initialSign) offsets.push(q);
      const eligible = initialSign !== 0, holds = eligible ? offsets.length > 0 : null;
      window = {
        start_index: index - 3, signs, initial_sign: initialSign,
        same_sign_future_offsets: offsets, applicable: eligible, satisfies_three_step_condition: holds
      };
      work.completed_new_windows++; stat.completed_new_windows++;
      if (initialSign > 0) stat.positive_start_windows++;
      else if (initialSign < 0) stat.negative_start_windows++;
      else stat.zero_start_windows++;
      if (eligible && !holds) stat.window_violations.push({ start_index: index - 3, initial_sign: initialSign });
    }
    state.events.push({
      index, previous_position: x, difference: h, position: y,
      negative_search: negativeSearch, positive_search: positiveSearch,
      selected_destination_was_unused: true, selected_difference_was_unused: true,
      linear_bound: 2 * k, completed_window: window
    });
  }
  function appendThrough(request) {
    if (!request || typeof request !== "object") throw new TypeError("append request required");
    const target = integer(request.target_size, 1, Number.MAX_SAFE_INTEGER, "target size");
    if (target > state.term_cap) return { status: "ABOVE_TERM_CAP", maximum_terms: state.term_cap, unchanged: true };
    if (target < A.length) throw new RangeError("cannot shrink retained history");
    if (target === A.length) return { status: "NO_NEW_TERMS", summary: summary(), unchanged: true };
    if (state.segments.length >= L.max_segments) return { status: "SEGMENT_CAP", maximum_segments: L.max_segments, unchanged: true };
    const id = sourceId(request.source_id, "new source id");
    if (id === state.source_id) throw new Error("append needs a new source id");
    const oldId = state.source_id, oldSize = A.length, before = clone(work);
    work.append_calls++;
    while (A.length < target) oneStep();
    state.source_id = id; state.parent_source_id = oldId; sync();
    const segment = { source_id: id, parent_source_id: oldId,
      first_new_index: oldSize + 1, last_new_index: target,
      completed_window_starts: [Math.max(1, oldSize - 2), target - 3],
      work: workDelta(before, work) };
    state.segments.push(segment);
    return { status: "COMPLETE", summary: summary(), segment: clone(segment) };
  }
  function query() { work.query_calls++; }
  function kindMask(kind) {
    if (kind === "position") return { used: bits.position, bound: B, sign: 1 };
    if (kind === "positive_difference") return { used: bits.positive, bound: B - 1, sign: 1 };
    if (kind === "negative_difference") return { used: bits.negative, bound: B - 1, sign: -1 };
    throw new TypeError("kind must be position, positive_difference or negative_difference");
  }
  function unused(kind, through) {
    const k = kindMask(kind);
    integer(through, 0, k.bound, "finite magnitude ceiling");
    return { mask: lowPositiveMask(through) & ~k.used, sign: k.sign };
  }
  function popcount(mask) {
    const text = mask.toString(16);
    let count = 0;
    for (let i = 0; i < text.length; i++) {
      work.query_popcount_digits++; count += POP4[parseInt(text[i], 16)];
    }
    return count;
  }
  function bitPage(mask, start, limit) {
    const text = mask.toString(16), values = [];
    let skip = start, rank = start;
    for (let i = text.length - 1; i >= 0 && values.length < limit; i--) {
      work.query_selection_digits++;
      const nibble = parseInt(text[i], 16), count = POP4[nibble];
      if (skip >= count) { skip -= count; continue; }
      for (let b = 0; b < 4 && values.length < limit; b++) {
        if (!(nibble & (1 << b))) continue;
        if (skip) { skip--; continue; }
        values.push({ rank: rank++, magnitude: 4 * (text.length - 1 - i) + b });
      }
    }
    return values;
  }
  function signedRows(kind, rows, signValue) {
    work.query_records_decoded += rows.length;
    return rows.map(r => ({ rank: r.rank, value: signValue * r.magnitude, magnitude: r.magnitude, kind }));
  }
  function oneTerm(index) {
    work.query_records_decoded++;
    return { index, position: A[index - 1], difference: D[index - 1],
      provenance: index <= state.premises.seed_size ? "accepted_seed" : "new_continuation" };
  }
  return Object.freeze({
    summary() { query(); return summary(); },
    appendThrough,
    term(index) { query(); integer(index, 1, A.length, "term index"); return oneTerm(index); },
    eventAt(index) {
      query(); integer(index, state.premises.seed_size + 1, A.length, "new event index");
      work.query_records_decoded++; return clone(state.events[index - state.premises.seed_size - 1]);
    },
    pageTerms(firstIndex, limit) {
      query(); integer(firstIndex, 1, Number.MAX_SAFE_INTEGER, "first term index");
      integer(limit, 1, L.max_page_size, "term page size");
      const end = Math.min(A.length, firstIndex + limit - 1), rows = [];
      for (let i = firstIndex; i <= end; i++) rows.push(oneTerm(i));
      return { first_index: firstIndex, rows, total_terms: A.length, next_index: end < A.length ? end + 1 : null };
    },
    positionOccurrence(value) {
      query(); integer(value, 1, Number.MAX_SAFE_INTEGER, "position value");
      const index = positionIndex.get(value);
      return index === undefined ? { status: "UNVISITED_WITHIN_PREFIX", value, prefix_terms: A.length } :
        { status: "FOUND", value, ...oneTerm(index) };
    },
    differenceOccurrence(value) {
      query(); integer(value, -Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, "signed difference");
      const index = differenceIndex.get(value);
      return index === undefined ? { status: "UNUSED_WITHIN_PREFIX", value, prefix_terms: A.length } :
        { status: "FOUND", value, ...oneTerm(index) };
    },
    countUnused(kind, through) {
      query(); const u = unused(kind, through);
      return { kind, through_magnitude: through, count: popcount(u.mask), prefix_terms: A.length };
    },
    selectUnused(kind, rank, through) {
      query(); integer(rank, 0, Number.MAX_SAFE_INTEGER, "unused rank");
      const u = unused(kind, through), count = popcount(u.mask);
      if (rank >= count) return { status: "OUT_OF_RANGE", kind, count, through_magnitude: through, prefix_terms: A.length };
      return { status: "FOUND", ...signedRows(kind, bitPage(u.mask, rank, 1), u.sign)[0],
        through_magnitude: through, prefix_terms: A.length };
    },
    rankUnused(kind, value, through) {
      query(); const u = unused(kind, through);
      integer(value, -Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, "unused value");
      const magnitude = u.sign * value;
      if (magnitude < 1 || magnitude > through || !(u.mask & bit(magnitude)))
        return { status: "NOT_IN_FINITE_UNUSED_INDEX", kind, value, through_magnitude: through, prefix_terms: A.length };
      return { status: "FOUND", kind, value, magnitude, rank: popcount(u.mask & lowPositiveMask(magnitude - 1)),
        through_magnitude: through, prefix_terms: A.length };
    },
    pageUnused(kind, start, limit, through) {
      query(); integer(start, 0, Number.MAX_SAFE_INTEGER, "unused page start");
      integer(limit, 1, L.max_page_size, "unused page size");
      const u = unused(kind, through), count = popcount(u.mask);
      const rows = signedRows(kind, bitPage(u.mask, start, limit), u.sign);
      const end = start + rows.length;
      return { kind, start, rows, count, through_magnitude: through, prefix_terms: A.length,
        next_start: end < count ? end : null };
    },
    windowAt(startIndex) {
      query(); integer(startIndex, 1, Number.MAX_SAFE_INTEGER, "window start");
      const endpoint = startIndex + 3;
      if (endpoint <= state.premises.seed_size || endpoint > A.length)
        return { status: "OUTSIDE_NEW_COMPLETED_WINDOWS", start_index: startIndex, prefix_terms: A.length };
      work.query_records_decoded++;
      return { status: "FOUND", ...clone(state.events[endpoint - state.premises.seed_size - 1].completed_window) };
    },
    snapshot() { sync(); return clone(state); },
    work() { return clone(work); }
  });
}
function continueGreedyDifferences(request) {
  if (!request || !request.seed) throw new TypeError("accepted canonical prefix required");
  const cap = integer(request.term_cap === undefined ? L.max_terms : request.term_cap, 2, L.max_terms, "term cap");
  const target = integer(request.target_size, 1, Number.MAX_SAFE_INTEGER, "target size");
  if (target > cap) return { status: "ABOVE_TERM_CAP", maximum_terms: cap, index: null };
  const id = sourceId(request.source_id, "source id"), seedId = sourceId(request.seed.source_id, "seed source id");
  if (id === seedId) throw new Error("new source id must differ from seed id");
  const work = freshWork("construct"); work.constructor_calls = 1;
  const hist = validateHistory(request.seed.positions, request.seed.differences, cap, work, true);
  if (target <= hist.A.length) throw new RangeError("constructor must add a new term");
  const B = 2 * (cap - 1), bits = buildOccupancy(hist.A, hist.D, B, work);
  const state = {
    schema: SCHEMA, source_id: seedId, parent_source_id: null,
    term_cap: cap, universe_bound: B,
    premises: { seed_source_id: seedId, seed_size: hist.A.length,
      seed_terminal_position: hist.A[hist.A.length - 1], seed_terminal_difference: hist.D[hist.D.length - 1],
      convention: "canonical a(1)=1,d(1)=0; literal Rule 1 negative interval",
      validation_scope: "structural; prefix choices are an identified accepted premise" },
    positions: hist.A, differences: hist.D, bitsets: null, events: [], segments: [],
    statistics: { new_steps: 0, new_positive_steps: 0, new_negative_steps: 0,
      maximum_new_position: null, maximum_new_step_magnitude: null,
      completed_new_windows: 0, positive_start_windows: 0, negative_start_windows: 0,
      zero_start_windows: 0, window_violations: [] }
  };
  const index = makeIndex(state, work, bits), result = index.appendThrough({ target_size: target, source_id: id });
  return { status: result.status, index };
}
function openRetainedGreedyDifferences(snapshot) {
  const work = freshWork("retained"); work.retained_opens = 1;
  return makeIndex(validateSaved(snapshot, work), work);
}
module.exports = { continueGreedyDifferences, openRetainedGreedyDifferences, GREEDY_DIFFERENCE_LIMITS };
