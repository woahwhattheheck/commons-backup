"use strict";

/**
 * Exact squared-distance profiles of finite Cartesian products of integer sets.
 * Zero self-distance is retained. A saved reader checks structural consistency,
 * not the coordinate arithmetic or mathematical provenance of its source.
 */
const CARTESIAN_DISTANCE_LIMITS = Object.freeze({
  max_raw_axis_entries: 64,
  max_axis_entries: 32,
  coordinate_digits: 32,
  squared_distance_digits: 66,
  max_profile_pairs: 1024,
  max_convolution_terms: 131072,
  max_page_size: 128,
  query_rank_digits: 16,
  source_id_chars: 512
});
const SCHEMA = "commons.erdos604.cartesian_distance_index/v1";
function fail(message) { throw new TypeError(message); }
function obj(x, name) {
  if (!x || typeof x !== "object" || Array.isArray(x)) fail(name + " must be an object");
  return x;
}
function arr(x, cap, name) {
  if (!Array.isArray(x) || x.length > cap) fail(name + " exceeds its array contract");
  return x;
}
function integer(x, digits, signed, name) {
  let s;
  if (typeof x === "bigint") s = x.toString();
  else if (typeof x === "number" && Number.isSafeInteger(x)) s = String(x);
  else if (typeof x === "string") s = x;
  else fail(name + " must be an exact integer");
  const pattern = signed ? /^(0|-?[1-9][0-9]*)$/ : /^(0|[1-9][0-9]*)$/;
  if (!pattern.test(s) || s.replace("-", "").length > digits) fail(name + " exceeds its integer contract");
  return BigInt(s);
}
function savedInteger(x, digits, signed, name) {
  if (typeof x !== "string") fail(name + " must be a canonical decimal string");
  return integer(x, digits, signed, name);
}
function small(x, cap, name) {
  if (!Number.isInteger(x) || x < 0 || x > cap) fail(name + " must be a bounded integer");
  return x;
}
function id(x) {
  if (typeof x !== "string" || !x.length || x.length > CARTESIAN_DISTANCE_LIMITS.source_id_chars)
    fail("source_id must be a nonempty bounded string");
  return x;
}
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function freshWork(mode) {
  return { mode, compiler_calls: 0, axes_compiled: 0,
    coordinate_squared_differences: 0, axis_target_references_created: 0,
    distinct_axis_profiles: 0, equal_axis_profiles_reused: 0,
    profile_convolutions: 0, convolution_terms_constructed: 0,
    planar_point_pairs_evaluated: 0,
    structural_axis_pair_rows: 0, structural_axis_target_references: 0,
    structural_axis_profile_terms: 0, structural_coefficient_rows: 0,
    structural_convolution_term_rows: 0,
    query_calls: 0, query_profiles_indexed: 0, query_coefficient_rows_indexed: 0,
    query_convolution_term_rows_indexed: 0, query_binary_search_steps: 0,
    query_circle_tables_materialized: 0, query_circle_points_materialized: 0,
    query_circle_cache_hits: 0 };
}
function normalizedAxis(raw, name) {
  const L = CARTESIAN_DISTANCE_LIMITS;
  arr(raw, L.max_raw_axis_entries, name);
  const values = Array.from(new Set(raw.map(x => integer(x, L.coordinate_digits, true, name).toString())))
    .map(BigInt).sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
  if (!values.length || values.length > L.max_axis_entries) fail(name + " must normalize to 1..32 distinct coordinates");
  return values;
}
function compileAxis(values, work) {
  work.axes_compiled++;
  const n = values.length;
  const buckets = Array.from({ length: n }, (_, i) => new Map([["0", [i]]]));
  work.axis_target_references_created += n;
  const witnesses = [];
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const delta = values[j] - values[i], sq = (delta * delta).toString();
    work.coordinate_squared_differences++;
    witnesses.push([i, j, sq]);
    if (!buckets[i].has(sq)) buckets[i].set(sq, []);
    if (!buckets[j].has(sq)) buckets[j].set(sq, []);
    buckets[i].get(sq).push(j); buckets[j].get(sq).push(i);
    work.axis_target_references_created += 2;
  }
  const profiles = [], pins = [], bySignature = new Map();
  for (let i = 0; i < n; i++) {
    const rows = Array.from(buckets[i].entries()).sort((a, b) =>
      BigInt(a[0]) < BigInt(b[0]) ? -1 : BigInt(a[0]) > BigInt(b[0]) ? 1 : 0);
    const terms = rows.map(([s, targets]) => [s, targets.length]);
    const signature = JSON.stringify(terms);
    let p = bySignature.get(signature);
    if (p === undefined) {
      p = profiles.length; bySignature.set(signature, p);
      profiles.push({ profile_id: p, terms, pin_indices: [] });
      work.distinct_axis_profiles++;
    } else work.equal_axis_profiles_reused++;
    profiles[p].pin_indices.push(i);
    pins.push({ profile_id: p, targets_by_term: rows.map(([, targets]) => targets.slice().sort((a, b) => a - b)) });
  }
  return { coordinates: values.map(String), unordered_pair_witnesses: witnesses, profiles, pins };
}
function compileProfilePair(x, y, xId, yId, pairId, pointCount, work) {
  const X = x.terms.map(([s, c]) => [BigInt(s), c]);
  const Y = y.terms.map(([s, c]) => [BigInt(s), c]);
  const bins = new Map(), pending = [];
  for (let i = 0; i < X.length; i++) for (let j = 0; j < Y.length; j++) {
    const sum = X[i][0] + Y[j][0], key = sum.toString(), weight = X[i][1] * Y[j][1];
    let row = bins.get(key);
    if (!row) { row = { squared: sum, count: 0 }; bins.set(key, row); }
    row.count += weight;
    pending.push([i, j, key, weight]);
    work.convolution_terms_constructed++;
  }
  const ordered = Array.from(bins.values()).sort((a, b) =>
    a.squared < b.squared ? -1 : a.squared > b.squared ? 1 : 0);
  const coefficients = ordered.map(x => [x.squared.toString(), x.count]);
  const binIndex = new Map(coefficients.map(([s], i) => [s, i])), flat = [];
  for (const [i, j, key, weight] of pending) flat.push(i, j, binIndex.get(key), weight);
  work.profile_convolutions++;
  return { profile_pair_id: pairId, x_profile_id: xId, y_profile_id: yId,
    represented_pin_count: x.pin_indices.length * y.pin_indices.length,
    point_count: pointCount, coefficients, terms_flat: flat };
}
function pinRecord(axes, i, j) {
  return { pin_indices: [i, j], point_id: i * axes.y.coordinates.length + j,
    coordinates: [axes.x.coordinates[i], axes.y.coordinates[j]] };
}
function summarize(axes, pairs) {
  const histogram = new Map();
  let minimum = Infinity, maximum = -Infinity;
  for (const p of pairs) {
    const n = p.coefficients.length;
    minimum = Math.min(minimum, n); maximum = Math.max(maximum, n);
    histogram.set(n, (histogram.get(n) || 0) + p.represented_pin_count);
  }
  const minimumPairs = [], maximumPairs = [], minimumPins = [], maximumPins = [];
  for (const p of pairs) {
    const n = p.coefficients.length;
    if (n !== minimum && n !== maximum) continue;
    if (n === minimum) minimumPairs.push(p.profile_pair_id);
    if (n === maximum) maximumPairs.push(p.profile_pair_id);
    for (const i of axes.x.profiles[p.x_profile_id].pin_indices)
      for (const j of axes.y.profiles[p.y_profile_id].pin_indices) {
        const rec = pinRecord(axes, i, j);
        if (n === minimum) minimumPins.push(rec);
        if (n === maximum) maximumPins.push(rec);
      }
  }
  minimumPins.sort((a, b) => a.point_id - b.point_id);
  maximumPins.sort((a, b) => a.point_id - b.point_id);
  return { point_count: axes.x.coordinates.length * axes.y.coordinates.length,
    x_coordinate_count: axes.x.coordinates.length, y_coordinate_count: axes.y.coordinates.length,
    x_profile_count: axes.x.profiles.length, y_profile_count: axes.y.profiles.length,
    profile_pair_count: pairs.length,
    coefficient_row_count: pairs.reduce((n, p) => n + p.coefficients.length, 0),
    convolution_term_count: pairs.reduce((n, p) => n + p.terms_flat.length / 4, 0),
    minimum_distinct_including_zero: minimum, minimum_positive_distances: minimum - 1,
    maximum_distinct_including_zero: maximum, maximum_positive_distances: maximum - 1,
    minimum_profile_pair_ids: minimumPairs, maximum_profile_pair_ids: maximumPairs,
    minimum_pins: minimumPins, maximum_pins: maximumPins,
    pin_count_by_distinct_distance_count: Array.from(histogram.entries()).sort((a, b) => a[0] - b[0]),
    convention: "zero self-distance included once; positive-distance count is one smaller",
    mathematical_scope: "the supplied finite Cartesian product, not a universal pinned-distance lower bound" };
}

function validateSaved(raw, work) {
  const L = CARTESIAN_DISTANCE_LIMITS, s = copy(obj(raw, "saved index"));
  if (s.schema !== SCHEMA) fail("unsupported saved-index schema");
  id(s.source_id); obj(s.axes, "axes");
  function axis(a, name) {
    obj(a, name);
    const cs = arr(a.coordinates, L.max_axis_entries, name + " coordinates"), n = cs.length;
    if (!n) fail("empty saved coordinate set");
    let last = null;
    for (const c of cs) {
      const v = savedInteger(c, L.coordinate_digits, true, "coordinate");
      if (last !== null && v <= last) fail("saved coordinates must be strictly increasing");
      last = v;
    }
    const pw = arr(a.unordered_pair_witnesses, n * (n - 1) / 2, "axis pair witnesses");
    if (pw.length !== n * (n - 1) / 2) fail("saved axis pair count is incomplete");
    let expectedI = 0, expectedJ = 1;
    for (const row of pw) {
      arr(row, 3, "axis pair row");
      if (row.length !== 3 || row[0] !== expectedI || row[1] !== expectedJ)
        fail("saved axis pair order/coverage differs");
      if (savedInteger(row[2], L.squared_distance_digits, false, "squared difference") === 0n)
        fail("a saved distinct-coordinate pair must have a positive squared-difference field");
      work.structural_axis_pair_rows++;
      expectedJ++; if (expectedJ === n) { expectedI++; expectedJ = expectedI + 1; }
    }
    const profiles = arr(a.profiles, n, "axis profiles"), pins = arr(a.pins, n, "axis pins");
    if (!profiles.length || pins.length !== n) fail("saved axis profile/pin counts differ");
    const coveredPins = new Set();
    for (let p = 0; p < profiles.length; p++) {
      const pr = obj(profiles[p], "axis profile");
      if (pr.profile_id !== p) fail("saved axis profile_id differs");
      arr(pr.terms, n, "axis profile terms");
      if (!pr.terms.length) fail("empty axis coefficient profile");
      let prev = -1n;
      for (const term of pr.terms) {
        arr(term, 2, "axis term");
        if (term.length !== 2) fail("axis term must have two fields");
        const sq = savedInteger(term[0], L.squared_distance_digits, false, "axis squared distance");
        if (sq <= prev) fail("axis squared distances must be strictly increasing");
        prev = sq;
        small(term[1], 2, "axis multiplicity");
        if (term[1] < 1) fail("axis multiplicity must be positive");
        work.structural_axis_profile_terms++;
      }
      if (pr.terms[0][0] !== "0" || pr.terms[0][1] !== 1) fail("axis self-distance term differs");
      arr(pr.pin_indices, n, "axis profile pins");
      if (!pr.pin_indices.length) fail("unused saved axis profile");
      for (const i of pr.pin_indices) {
        small(i, n - 1, "axis pin index");
        if (coveredPins.has(i)) fail("axis pin appears in two profiles");
        coveredPins.add(i);
      }
    }
    if (coveredPins.size !== n) fail("saved axis profiles do not cover all pins");
    for (let i = 0; i < n; i++) {
      const pin = obj(pins[i], "axis pin"), p = small(pin.profile_id, profiles.length - 1, "axis profile reference");
      const pr = profiles[p];
      if (!pr.pin_indices.includes(i)) fail("saved axis profile membership differs");
      arr(pin.targets_by_term, n, "axis targets_by_term");
      if (pin.targets_by_term.length !== pr.terms.length) fail("saved axis target-term count differs");
      const seen = new Set();
      for (let t = 0; t < pr.terms.length; t++) {
        const targets = arr(pin.targets_by_term[t], 2, "axis target list");
        if (targets.length !== pr.terms[t][1]) fail("axis target multiplicity differs");
        let previous = -1;
        for (const target of targets) {
          small(target, n - 1, "axis target index");
          if (target <= previous || seen.has(target)) fail("axis targets must partition coordinates");
          previous = target; seen.add(target); work.structural_axis_target_references++;
        }
      }
      if (seen.size !== n || pin.targets_by_term[0][0] !== i) fail("saved axis target/self coverage differs");
    }
    return a;
  }
  const X = axis(s.axes.x, "x axis"), Y = axis(s.axes.y, "y axis");
  const pointCount = X.coordinates.length * Y.coordinates.length;
  const pairCount = X.profiles.length * Y.profiles.length;
  const pairs = arr(s.profile_pairs, L.max_profile_pairs, "profile_pairs");
  if (pairs.length !== pairCount) fail("saved profile pairs do not cover the product");
  let totalTerms = 0;
  for (let k = 0; k < pairs.length; k++) {
    const p = obj(pairs[k], "profile pair"), xi = Math.floor(k / Y.profiles.length), yi = k % Y.profiles.length;
    if (p.profile_pair_id !== k || p.x_profile_id !== xi || p.y_profile_id !== yi ||
        p.point_count !== pointCount ||
        p.represented_pin_count !== X.profiles[xi].pin_indices.length * Y.profiles[yi].pin_indices.length)
      fail("saved profile-pair identity differs");
    const bins = arr(p.coefficients, pointCount, "coefficients");
    if (!bins.length) fail("empty saved distance profile");
    let previous = -1n, mass = 0;
    for (const row of bins) {
      arr(row, 2, "coefficient row");
      if (row.length !== 2) fail("coefficient row must have two fields");
      const sq = savedInteger(row[0], L.squared_distance_digits, false, "squared distance");
      if (sq <= previous) fail("saved squared distances must be increasing");
      previous = sq;
      small(row[1], pointCount, "point multiplicity");
      if (!row[1]) fail("point multiplicity must be positive");
      mass += row[1]; work.structural_coefficient_rows++;
    }
    if (bins[0][0] !== "0" || bins[0][1] !== 1 || mass !== pointCount)
      fail("saved self-distance or coefficient mass differs");
    const nx = X.profiles[xi].terms.length, ny = Y.profiles[yi].terms.length;
    const flat = arr(p.terms_flat, 4 * L.max_convolution_terms, "terms_flat");
    if (flat.length !== 4 * nx * ny) fail("saved convolution term coverage differs");
    totalTerms += nx * ny;
    if (totalTerms > L.max_convolution_terms) fail("saved convolution term cap exceeded");
    for (let t = 0; t < nx * ny; t++) {
      const o = 4 * t;
      if (flat[o] !== Math.floor(t / ny) || flat[o + 1] !== t % ny)
        fail("saved convolution input-term order differs");
      small(flat[o + 2], bins.length - 1, "coefficient reference");
      small(flat[o + 3], 4, "convolution weight");
      if (!flat[o + 3]) fail("convolution weight must be positive");
      work.structural_convolution_term_rows++;
    }
  }
  const summary = obj(s.summary, "summary");
  if (summary.point_count !== pointCount || summary.x_coordinate_count !== X.coordinates.length ||
      summary.y_coordinate_count !== Y.coordinates.length || summary.profile_pair_count !== pairCount ||
      summary.convolution_term_count !== totalTerms) fail("saved summary dimensions differ");
  for (const key of ["minimum_distinct_including_zero", "maximum_distinct_including_zero"]) {
    small(summary[key], pointCount, key); if (!summary[key]) fail("saved extremal count must be positive");
  }
  for (const key of ["minimum_pins", "maximum_pins"]) {
    arr(summary[key], pointCount, key);
    for (const rec of summary[key]) {
      arr(rec.pin_indices, 2, "extremal pin"); if (rec.pin_indices.length !== 2) fail("pin must have two indices");
      const i = small(rec.pin_indices[0], X.coordinates.length - 1, "x pin");
      const j = small(rec.pin_indices[1], Y.coordinates.length - 1, "y pin");
      if (rec.point_id !== i * Y.coordinates.length + j ||
          JSON.stringify(rec.coordinates) !== JSON.stringify([X.coordinates[i], Y.coordinates[j]]))
        fail("saved extremal pin identity differs");
    }
  }
  return s;
}

function makeIndex(state, work) {
  const L = CARTESIAN_DISTANCE_LIMITS, X = state.axes.x, Y = state.axes.y;
  const caches = new Map(), circles = new Map();
  function pin(pin) {
    arr(pin, 2, "pin"); if (pin.length !== 2) fail("pin must have two coordinate indices");
    const i = small(pin[0], X.coordinates.length - 1, "x pin index");
    const j = small(pin[1], Y.coordinates.length - 1, "y pin index");
    const p = X.pins[i].profile_id * Y.profiles.length + Y.pins[j].profile_id;
    return { i, j, p, record: pinRecord(state.axes, i, j) };
  }
  function indexed(p) {
    let c = caches.get(p);
    if (c) return c;
    const row = state.profile_pairs[p], keys = row.coefficients.map(r => BigInt(r[0]));
    const prefix = [0], refs = row.coefficients.map(() => []);
    for (const [, count] of row.coefficients) prefix.push(prefix[prefix.length - 1] + count);
    for (let i = 0; i < row.terms_flat.length; i += 4) refs[row.terms_flat[i + 2]].push(i / 4);
    c = { row, keys, prefix, refs }; caches.set(p, c);
    work.query_profiles_indexed++;
    work.query_coefficient_rows_indexed += keys.length;
    work.query_convolution_term_rows_indexed += row.terms_flat.length / 4;
    return c;
  }
  function lowerBound(keys, q) {
    let a = 0, b = keys.length;
    while (a < b) {
      const m = (a + b) >>> 1; work.query_binary_search_steps++;
      if (keys[m] < q) a = m + 1; else b = m;
    }
    return a;
  }
  function zeroOption(options) {
    if (options === undefined) return true;
    obj(options, "options");
    if (options.include_zero === undefined) return true;
    if (typeof options.include_zero !== "boolean") fail("include_zero must be Boolean");
    return options.include_zero;
  }
  function rankValue(r) { return integer(r, L.query_rank_digits, false, "rank"); }
  function squareValue(q) { return integer(q, L.squared_distance_digits, false, "squared distance"); }
  function coefficient(p, at, includeZero) {
    const row = state.profile_pairs[p].coefficients[at];
    return { profile_pair_id: p, coefficient_row_index: at, rank: at - (includeZero ? 0 : 1),
      squared_distance: row[0], point_multiplicity: row[1], is_zero: at === 0 };
  }
  function circle(pinInfo, bin) {
    const key = pinInfo.record.point_id + ":" + bin;
    if (circles.has(key)) { work.query_circle_cache_hits++; return circles.get(key); }
    const c = indexed(pinInfo.p), rows = [];
    for (const t of c.refs[bin]) {
      const offset = 4 * t, xt = c.row.terms_flat[offset], yt = c.row.terms_flat[offset + 1];
      const targetsX = X.pins[pinInfo.i].targets_by_term[xt];
      const targetsY = Y.pins[pinInfo.j].targets_by_term[yt];
      for (const i of targetsX) for (const j of targetsY)
        rows.push(Object.assign(pinRecord(state.axes, i, j), {
          convolution_term_index: t, x_axis_term_index: xt, y_axis_term_index: yt
        }));
    }
    rows.sort((a, b) => a.point_id - b.point_id);
    if (rows.length !== c.row.coefficients[bin][1])
      fail("saved circle incidences and coefficient multiplicity disagree");
    work.query_circle_tables_materialized++;
    work.query_circle_points_materialized += rows.length;
    circles.set(key, rows); return rows;
  }
  const api = {
    summary() { return copy(Object.assign({ schema: SCHEMA, source_id: state.source_id,
      x_coordinates: X.coordinates, y_coordinates: Y.coordinates }, state.summary)); },
    pinSummary(pinIndices) {
      work.query_calls++;
      const p = pin(pinIndices), row = state.profile_pairs[p.p];
      return Object.assign({}, p.record, { source_id: state.source_id, profile_pair_id: p.p,
        distinct_distances_including_zero: row.coefficients.length,
        positive_distances: row.coefficients.length - 1, total_points: row.point_count,
        maximum_squared_distance: row.coefficients[row.coefficients.length - 1][0] });
    },
    selectDistance(pinIndices, rank, options) {
      work.query_calls++;
      const p = pin(pinIndices), includeZero = zeroOption(options), r = rankValue(rank);
      const length = state.profile_pairs[p.p].coefficients.length - (includeZero ? 0 : 1);
      if (r >= BigInt(length)) return { status: "OUT_OF_RANGE", available: length, requested_rank: r.toString() };
      const at = Number(r) + (includeZero ? 0 : 1);
      return Object.assign({ status: "FOUND", pin: p.record, include_zero: includeZero }, coefficient(p.p, at, includeZero));
    },
    rankDistance(pinIndices, squaredDistance, options) {
      work.query_calls++;
      const p = pin(pinIndices), includeZero = zeroOption(options), q = squareValue(squaredDistance);
      const c = indexed(p.p), at = lowerBound(c.keys, q);
      if (!includeZero && q === 0n) return { status: "EXCLUDED_ZERO", include_zero: false };
      if (at === c.keys.length || c.keys[at] !== q) return { status: "ABSENT", squared_distance: q.toString() };
      return Object.assign({ status: "FOUND", pin: p.record, include_zero: includeZero }, coefficient(p.p, at, includeZero));
    },
    pageDistances(pinIndices, startRank, limit, options) {
      work.query_calls++;
      const p = pin(pinIndices), includeZero = zeroOption(options), start = rankValue(startRank);
      small(limit, L.max_page_size, "page limit"); if (!limit) fail("page limit must be positive");
      const n = state.profile_pairs[p.p].coefficients.length - (includeZero ? 0 : 1), rows = [];
      if (start < BigInt(n)) for (let j = Number(start); j < n && rows.length < limit; j++)
        rows.push(coefficient(p.p, j + (includeZero ? 0 : 1), includeZero));
      const next = start + BigInt(rows.length);
      return { pin: p.record, include_zero: includeZero, start_rank: start.toString(),
        rows, next_rank: next.toString(), has_more: next < BigInt(n) };
    },
    countPointsThrough(pinIndices, squaredDistance) {
      work.query_calls++;
      const p = pin(pinIndices), q = squareValue(squaredDistance), c = indexed(p.p);
      let at = lowerBound(c.keys, q);
      if (at < c.keys.length && c.keys[at] === q) at++;
      return { pin: p.record, profile_pair_id: p.p,
        upper_squared_distance_inclusive: q.toString(), point_count_including_pin: c.prefix[at] };
    },
    pagePointsAtDistance(pinIndices, squaredDistance, startRank, limit) {
      work.query_calls++;
      const p = pin(pinIndices), q = squareValue(squaredDistance), start = rankValue(startRank);
      small(limit, L.max_page_size, "page limit"); if (!limit) fail("page limit must be positive");
      const c = indexed(p.p), at = lowerBound(c.keys, q);
      if (at === c.keys.length || c.keys[at] !== q) return { status: "ABSENT", pin: p.record,
        squared_distance: q.toString(), points: [], total_points: 0, has_more: false };
      const all = circle(p, at), begin = start < BigInt(all.length) ? Number(start) : all.length;
      const rows = copy(all.slice(begin, begin + limit)), next = start + BigInt(rows.length);
      return { status: "FOUND", pin: p.record, profile_pair_id: p.p, coefficient_row_index: at,
        squared_distance: q.toString(), start_rank: start.toString(), points: rows,
        total_points: all.length, next_rank: next.toString(), has_more: next < BigInt(all.length) };
    },
    sourceProfile(pinIndices) {
      work.query_calls++;
      return copy(state.profile_pairs[pin(pinIndices).p]);
    },
    snapshot() { return copy(state); },
    work() { return copy(work); }
  };
  return Object.freeze(api);
}

function compileCartesianDistanceIndex(request) {
  const L = CARTESIAN_DISTANCE_LIMITS;
  obj(request, "compile request");
  const sourceId = id(request.source_id);
  const xs = normalizedAxis(request.x_coordinates, "x_coordinates");
  const ys = normalizedAxis(request.y_coordinates, "y_coordinates");
  const work = freshWork("compile"); work.compiler_calls = 1;
  const axes = { x: compileAxis(xs, work), y: compileAxis(ys, work) };
  const pairCount = axes.x.profiles.length * axes.y.profiles.length;
  const requiredTerms = axes.x.profiles.reduce((n, p) => n + p.terms.length, 0) *
    axes.y.profiles.reduce((n, p) => n + p.terms.length, 0);
  if (pairCount > L.max_profile_pairs || requiredTerms > L.max_convolution_terms)
    return { status: "CAP_STOP", reason: pairCount > L.max_profile_pairs ? "PROFILE_PAIR_CAP" : "CONVOLUTION_TERM_CAP",
      source_id: sourceId, required_profile_pairs: pairCount, required_convolution_terms: requiredTerms,
      retained_axes: copy(axes), work: copy(work), index: null };
  const pairs = [], pointCount = xs.length * ys.length;
  for (let i = 0; i < axes.x.profiles.length; i++)
    for (let j = 0; j < axes.y.profiles.length; j++)
      pairs.push(compileProfilePair(axes.x.profiles[i], axes.y.profiles[j], i, j, pairs.length, pointCount, work));
  const state = { schema: SCHEMA, source_id: sourceId, axes, profile_pairs: pairs,
    summary: summarize(axes, pairs) };
  return { status: "COMPLETE", index: makeIndex(state, work) };
}
function openRetainedCartesianDistanceIndex(snapshot) {
  const work = freshWork("retained");
  return makeIndex(validateSaved(snapshot, work), work);
}
module.exports = { compileCartesianDistanceIndex, openRetainedCartesianDistanceIndex,
  CARTESIAN_DISTANCE_LIMITS };
