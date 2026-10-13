"use strict";

// Exact navigation of lines in a full finite integer rectangle.
// No I/O or dependencies. Saved opens validate structure, not mathematical proof.
const SCHEMA = "erdos588.rectangular_line_navigation/v1";
const LIMITS = Object.freeze({
  side: 512, positive_direction_candidates: 4096, directions: 8194,
  profile_rows: 50000, page_size: 256, sessions: 64, events_per_session: 256,
  source_id_chars: 512, origin_digits: 128, point_digits: 129,
  copy_items: 3000000, copy_text_chars: 32000000, copy_depth: 32
});
const WORK_KEYS = Object.freeze([
  "compiler_calls", "direction_candidates_scanned", "direction_gcd_steps",
  "absolute_profiles_built", "profile_limit_quotients", "step_weight_rows_built",
  "threshold_rows_built", "signed_directions_created", "global_prefix_blocks_built",
  "global_threshold_views_built", "aggregate_pair_terms",
  "point_pairs_enumerated", "complete_lines_enumerated", "complete_grid_points_enumerated",
  "query_calls", "query_binary_search_steps", "query_divisions", "query_gcd_steps",
  "line_descriptors_materialized", "line_point_records_materialized",
  "point_incidence_directions_examined", "count_rows_returned"
]);
function fail(code, message) { const error = new Error(message); error.code = code; throw error; }
function need(test, code, message) { if (!test) fail(code, message); }
function object(value, name) {
  need(value !== null && typeof value === "object" && !Array.isArray(value) &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null),
    "INVALID_OBJECT", name + " must be a plain object");
  return value;
}
function integer(value, min, max, name) {
  need(Number.isSafeInteger(value) && value >= min && value <= max,
    "INVALID_INTEGER", name + " is outside its exact integer range");
  return value;
}
function array(value, max, name) {
  need(Array.isArray(value) && value.length <= max, "INVALID_ARRAY", name + " must be a bounded array");
  return value;
}
function fields(value, keys, name) {
  object(value, name);
  const actual = Object.keys(value).sort(), expected = keys.slice().sort();
  need(actual.length === expected.length && actual.every((key, i) => key === expected[i]),
    "INVALID_FIELDS", name + " has missing or unsupported fields");
}
function options(value, keys, name) {
  object(value, name);
  need(Object.keys(value).every(key => keys.includes(key)), "INVALID_OPTIONS", name + " has unsupported options");
}
function sourceId(value, name) {
  need(typeof value === "string" && value.length > 0 && value.length <= LIMITS.source_id_chars,
    "INVALID_SOURCE_ID", name + " must be a bounded nonempty string");
  return value;
}
function coordinate(value, name, digits = LIMITS.origin_digits) {
  let text;
  if (typeof value === "bigint") text = value.toString();
  else if (typeof value === "number" && Number.isSafeInteger(value)) text = String(value);
  else if (typeof value === "string") text = value;
  else fail("INVALID_COORDINATE", name + " must be an exact integer");
  need(/^(?:0|-?[1-9][0-9]*)$/.test(text), "INVALID_COORDINATE", name + " must use canonical integer notation");
  need(text.replace("-", "").length <= digits, "COORDINATE_LIMIT", name + " exceeds its digit bound");
  return BigInt(text);
}
function copy(value) {
  let count = 0, text = 0;
  function visit(x, depth) {
    need(++count <= LIMITS.copy_items && depth <= LIMITS.copy_depth, "COPY_LIMIT", "Retained structure exceeds its copy bound");
    if (x === null || typeof x === "boolean") return x;
    if (typeof x === "number") return integer(x, -Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, "retained number");
    if (typeof x === "string") {
      text += x.length; need(text <= LIMITS.copy_text_chars, "COPY_LIMIT", "Retained text exceeds its copy bound"); return x;
    }
    if (Array.isArray(x)) return x.map(y => visit(y, depth + 1));
    object(x, "retained object"); const result = {};
    for (const key of Object.keys(x)) {
      need(!["__proto__", "constructor", "prototype"].includes(key), "INVALID_FIELD", "Reserved retained-object key");
      result[key] = visit(x[key], depth + 1);
    }
    return result;
  }
  return visit(value, 0);
}
function zeroWork() { return Object.fromEntries(WORK_KEYS.map(key => [key, 0])); }
function validateWork(work, name) {
  fields(work, WORK_KEYS, name);
  for (const key of WORK_KEYS) integer(work[key], 0, Number.MAX_SAFE_INTEGER, name + "." + key);
}
function rectangle(value) {
  fields(value, ["x_origin", "y_origin", "width", "height"], "rectangle");
  const width = integer(value.width, 1, LIMITS.side, "width");
  const height = integer(value.height, 1, LIMITS.side, "height");
  need((width - 1) * (height - 1) <= LIMITS.positive_direction_candidates,
    "DIRECTION_CAPACITY", "The positive direction-candidate rectangle is too large");
  return {x_origin: coordinate(value.x_origin, "x_origin").toString(),
    y_origin: coordinate(value.y_origin, "y_origin").toString(), width, height};
}
function compileRectangularLineIndex(args) {
  options(args, ["source_id", "rectangle_source_id", "rectangle"], "compile options");
  const id = sourceId(args.source_id, "source_id");
  const rectangleId = sourceId(args.rectangle_source_id, "rectangle_source_id");
  const rect = rectangle(args.rectangle), w = rect.width, h = rect.height, maximum = Math.max(w, h);
  const work = zeroWork(); work.compiler_calls = 1;
  const gcdCandidates = [], profiles = [], directions = [], views = [];
  let retainedProfileRows = 0;
  function makeProfile(a, b, gcdId) {
    const quotients = [];
    if (a !== 0) { quotients.push(Math.floor((w - 1) / a)); work.profile_limit_quotients++; }
    if (b !== 0) { quotients.push(Math.floor((h - 1) / b)); work.profile_limit_quotients++; }
    const length = 1 + Math.min(...quotients);
    need(length >= 2 && length <= maximum, "INTERNAL_DIRECTION", "Direction cannot support its declared line length");
    const weights = [], rows = [];
    // Adjacent T_k values reuse these exact step weights.
    for (let steps = 1; steps <= length + 1; steps++) {
      const width = Math.max(w - steps * a, 0), height = Math.max(h - steps * b, 0);
      weights.push({steps, width, height, starts: width * height});
      work.step_weight_rows_built++;
    }
    for (let k = 2; k <= length + 1; k++) {
      const current = weights[k - 2], next = weights[k - 1];
      const alpha = Math.min(a, current.width), beta = Math.min(b, current.height);
      const first = {x_start: 0, width: alpha, height: current.height, count: alpha * current.height};
      const second = {x_start: alpha, width: current.width - alpha, height: beta,
        count: (current.width - alpha) * beta};
      const total = current.starts - next.starts;
      need(first.count + second.count === total && total >= 0,
        "INTERNAL_START_COUNT", "Boundary-start decomposition and segment difference disagree");
      rows.push({k, start_weight_row: k - 2, next_weight_row: k - 1,
        slab_a: first, slab_b: second, at_least_count: total, exact_count: 0});
      work.threshold_rows_built++; retainedProfileRows++;
      need(retainedProfileRows <= LIMITS.profile_rows, "PROFILE_CAPACITY", "Retained count-profile row capacity exceeded");
    }
    for (let index = 0; index < rows.length; index++)
      rows[index].exact_count = rows[index].at_least_count -
        (index + 1 < rows.length ? rows[index + 1].at_least_count : 0);
    const profile = {id: profiles.length, a, b, gcd_candidate_id: gcdId,
      maximum_length: length, step_weights: weights, threshold_rows: rows};
    profiles.push(profile); work.absolute_profiles_built++;
    return profile.id;
  }
  function addDirection(u, v, profileId) {
    directions.push({id: -1, u, v, profile_id: profileId});
    work.signed_directions_created++;
  }
  if (h > 1) addDirection(0, 1, makeProfile(0, 1, null));
  if (w > 1) addDirection(1, 0, makeProfile(1, 0, null));
  for (let a = 1; a < w; a++) for (let b = 1; b < h; b++) {
    let x = a, y = b; const chain = [];
    while (y !== 0) {
      const quotient = Math.floor(x / y), remainder = x % y;
      chain.push({dividend: x, divisor: y, quotient, remainder});
      x = y; y = remainder; work.direction_gcd_steps++;
    }
    const candidate = {id: gcdCandidates.length, a, b, gcd: x, divisions: chain};
    gcdCandidates.push(candidate); work.direction_candidates_scanned++;
    if (x === 1) {
      const profileId = makeProfile(a, b, candidate.id);
      addDirection(a, -b, profileId); addDirection(a, b, profileId);
    }
  }
  directions.sort((a, b) => a.u - b.u || a.v - b.v);
  directions.forEach((direction, index) => { direction.id = index; });
  need(directions.length <= LIMITS.directions, "DIRECTION_CAPACITY", "Signed direction capacity exceeded");
  for (let k = 2; k <= maximum + 1; k++) {
    const blocks = []; let total = 0;
    for (const direction of directions) {
      const profile = profiles[direction.profile_id], rowIndex = k - 2;
      if (rowIndex >= profile.threshold_rows.length) continue;
      const row = profile.threshold_rows[rowIndex];
      if (row.at_least_count === 0) continue;
      blocks.push({direction_id: direction.id, profile_row_index: rowIndex,
        prefix_start: total, prefix_end: total + row.at_least_count, count: row.at_least_count});
      total += row.at_least_count; work.global_prefix_blocks_built++;
    }
    views.push({k, blocks, total, exact_count: 0}); work.global_threshold_views_built++;
  }
  let representedPairs = 0, incidences = 0;
  for (let index = 0; index < views.length; index++) {
    const row = views[index], next = index + 1 < views.length ? views[index + 1].total : 0;
    row.exact_count = row.total - next;
    need(row.exact_count >= 0, "INTERNAL_HISTOGRAM", "Exact line count is negative");
    if (row.k <= maximum) {
      representedPairs += row.exact_count * row.k * (row.k - 1) / 2;
      incidences += row.exact_count * row.k; work.aggregate_pair_terms++;
    }
  }
  const points = w * h, expectedPairs = points * (points - 1) / 2;
  need(Number.isSafeInteger(representedPairs) && representedPairs === expectedPairs,
    "INTERNAL_PAIR_ACCOUNTING", "Complete line histogram does not account for the rectangle's unordered pairs");
  const state = {schema: SCHEMA, source_id: id, rectangle_source_id: rectangleId, rectangle: rect,
    gcd_candidates: gcdCandidates, profiles, directions, threshold_views: views,
    totals: {point_count: points, maximum_collinearity: maximum, determined_lines: views[0].total,
      point_line_incidences: incidences, represented_unordered_pairs: representedPairs,
      expected_unordered_pairs: expectedPairs, pair_accounting_exact: true},
    work, activity: []};
  return makeIndex(state, id, "compile", copy(work), null);
}

function validateSaved(state) {
  fields(state, ["schema", "source_id", "rectangle_source_id", "rectangle", "gcd_candidates",
    "profiles", "directions", "threshold_views", "totals", "work", "activity"], "snapshot");
  need(state.schema === SCHEMA, "INVALID_SCHEMA", "Unsupported rectangular-line snapshot");
  sourceId(state.source_id, "saved source_id"); sourceId(state.rectangle_source_id, "saved rectangle source");
  const rect = rectangle(state.rectangle), w = rect.width, h = rect.height;
  const n = w * h, maximum = Math.max(w, h), pairBound = n * (n - 1) / 2;
  array(state.gcd_candidates, LIMITS.positive_direction_candidates, "gcd candidates");
  need(state.gcd_candidates.length === (w - 1) * (h - 1), "INVALID_CANDIDATE_DOMAIN", "Candidate direction count is incomplete");
  const candidateKeys = new Set();
  state.gcd_candidates.forEach((record, id) => {
    fields(record, ["id", "a", "b", "gcd", "divisions"], "gcd candidate");
    need(record.id === id, "INVALID_REFERENCE", "Gcd candidate IDs must be contiguous");
    integer(record.a, 1, w - 1, "candidate a"); integer(record.b, 1, h - 1, "candidate b");
    const key = record.a + "," + record.b;
    need(!candidateKeys.has(key), "DUPLICATE_CANDIDATE", "Gcd candidate addresses must be unique"); candidateKeys.add(key);
    integer(record.gcd, 1, LIMITS.side, "saved gcd");
    array(record.divisions, 32, "saved gcd divisions");
    for (const step of record.divisions) {
      fields(step, ["dividend", "divisor", "quotient", "remainder"], "gcd division");
      integer(step.dividend, 1, LIMITS.side, "dividend");
      integer(step.divisor, 1, LIMITS.side, "divisor");
      integer(step.quotient, 0, LIMITS.side, "quotient");
      integer(step.remainder, 0, step.divisor - 1, "remainder");
    }
  });
  array(state.profiles, LIMITS.positive_direction_candidates + 2, "profiles");
  let profileRows = 0; const profileKeys = new Set();
  state.profiles.forEach((profile, id) => {
    fields(profile, ["id", "a", "b", "gcd_candidate_id", "maximum_length", "step_weights", "threshold_rows"], "profile");
    need(profile.id === id, "INVALID_REFERENCE", "Profile IDs must be contiguous");
    integer(profile.a, 0, w - 1, "profile a"); integer(profile.b, 0, h - 1, "profile b");
    need(profile.a + profile.b > 0, "ZERO_DIRECTION", "A profile must have a nonzero step");
    const key = profile.a + "," + profile.b;
    need(!profileKeys.has(key), "DUPLICATE_PROFILE", "Absolute profiles must be unique"); profileKeys.add(key);
    if (profile.gcd_candidate_id === null)
      need((profile.a === 0 && profile.b === 1) || (profile.a === 1 && profile.b === 0),
        "INVALID_REFERENCE", "Only axis profiles omit a positive candidate reference");
    else {
      integer(profile.gcd_candidate_id, 0, state.gcd_candidates.length - 1, "profile gcd reference");
      const candidate = state.gcd_candidates[profile.gcd_candidate_id];
      need(candidate.a === profile.a && candidate.b === profile.b && candidate.gcd === 1,
        "INVALID_REFERENCE", "Profile does not reference its retained primitive candidate");
    }
    integer(profile.maximum_length, 2, maximum, "maximum line length");
    array(profile.step_weights, LIMITS.side + 1, "step weights");
    need(profile.step_weights.length === profile.maximum_length + 1, "INVALID_PROFILE", "Step weights require both zero-endpoint addresses");
    profile.step_weights.forEach((weight, index) => {
      fields(weight, ["steps", "width", "height", "starts"], "step weight");
      need(weight.steps === index + 1, "INVALID_REFERENCE", "Step weights must be consecutively addressed");
      integer(weight.width, 0, w, "weight width"); integer(weight.height, 0, h, "weight height");
      integer(weight.starts, 0, n, "segment start count");
    });
    array(profile.threshold_rows, LIMITS.side, "profile threshold rows");
    need(profile.threshold_rows.length === profile.maximum_length, "INVALID_PROFILE", "Threshold rows require their final zero-endpoint address");
    profileRows += profile.threshold_rows.length;
    need(profileRows <= LIMITS.profile_rows, "PROFILE_CAPACITY", "Saved profile rows exceed capacity");
    profile.threshold_rows.forEach((row, index) => {
      fields(row, ["k", "start_weight_row", "next_weight_row", "slab_a", "slab_b",
        "at_least_count", "exact_count"], "profile threshold");
      need(row.k === index + 2 && row.start_weight_row === index && row.next_weight_row === index + 1,
        "INVALID_REFERENCE", "Threshold references must address their consecutive saved weights");
      for (const slab of [row.slab_a, row.slab_b]) {
        fields(slab, ["x_start", "width", "height", "count"], "start slab");
        integer(slab.x_start, 0, w, "slab x start");
        integer(slab.width, 0, w, "slab width"); integer(slab.height, 0, h, "slab height");
        integer(slab.count, 0, n, "slab count");
      }
      integer(row.at_least_count, 0, n, "direction threshold count");
      integer(row.exact_count, 0, n, "direction exact count");
    });
  });
  array(state.directions, LIMITS.directions, "directions");
  let priorDirection = null;
  state.directions.forEach((direction, id) => {
    fields(direction, ["id", "u", "v", "profile_id"], "direction");
    need(direction.id === id, "INVALID_REFERENCE", "Direction IDs must be contiguous");
    integer(direction.u, 0, w - 1, "direction u"); integer(direction.v, 1 - h, h - 1, "direction v");
    need(direction.u > 0 || direction.v === 1, "INVALID_DIRECTION", "Direction must have canonical unoriented sign");
    if (priorDirection)
      need(direction.u > priorDirection.u || (direction.u === priorDirection.u && direction.v > priorDirection.v),
        "INVALID_DIRECTION_ORDER", "Directions must be strictly ordered by signed (u,v)");
    priorDirection = direction;
    integer(direction.profile_id, 0, state.profiles.length - 1, "profile reference");
    const profile = state.profiles[direction.profile_id];
    need(profile.a === direction.u && profile.b === Math.abs(direction.v),
      "INVALID_REFERENCE", "Signed direction does not address its absolute profile");
  });
  array(state.threshold_views, LIMITS.side, "threshold views");
  need(state.threshold_views.length === maximum, "INVALID_VIEW_DOMAIN", "Global views must include all thresholds and the final zero endpoint");
  state.threshold_views.forEach((view, index) => {
    fields(view, ["k", "blocks", "total", "exact_count"], "global threshold view");
    need(view.k === index + 2, "INVALID_REFERENCE", "Global threshold addresses must be consecutive");
    array(view.blocks, state.directions.length, "direction prefix blocks");
    let next = 0, prior = -1;
    for (const block of view.blocks) {
      fields(block, ["direction_id", "profile_row_index", "prefix_start", "prefix_end", "count"], "prefix block");
      integer(block.direction_id, prior + 1, state.directions.length - 1, "block direction");
      prior = block.direction_id;
      need(block.profile_row_index === view.k - 2, "INVALID_REFERENCE", "Prefix block threshold reference differs from its view");
      const profile = state.profiles[state.directions[block.direction_id].profile_id];
      integer(block.profile_row_index, 0, profile.threshold_rows.length - 1, "profile row reference");
      integer(block.count, 1, n, "positive block count");
      integer(block.prefix_start, 0, pairBound, "prefix start"); integer(block.prefix_end, 1, pairBound, "prefix end");
      need(block.prefix_start === next && block.prefix_end - block.prefix_start === block.count &&
        profile.threshold_rows[block.profile_row_index].at_least_count === block.count,
        "INVALID_PREFIX_REFERENCE", "Prefix addresses do not match their retained count references");
      next = block.prefix_end;
    }
    integer(view.total, 0, pairBound, "global threshold count");
    integer(view.exact_count, 0, pairBound, "global exact count");
    need(view.total === next, "INVALID_PREFIX_TOTAL", "Prefix end does not match its declared total");
  });
  fields(state.totals, ["point_count", "maximum_collinearity", "determined_lines", "point_line_incidences",
    "represented_unordered_pairs", "expected_unordered_pairs", "pair_accounting_exact"], "totals");
  need(state.totals.point_count === n && state.totals.maximum_collinearity === maximum &&
    state.totals.determined_lines === state.threshold_views[0].total,
    "INVALID_TOTALS", "Rectangle and retained total addresses disagree");
  for (const key of ["determined_lines", "point_line_incidences", "represented_unordered_pairs", "expected_unordered_pairs"])
    integer(state.totals[key], 0, Number.MAX_SAFE_INTEGER, "total " + key);
  need(state.totals.pair_accounting_exact === true, "INVALID_TOTALS", "Saved compiler must retain its complete-accounting claim");
  validateWork(state.work, "cumulative work");
  array(state.activity, LIMITS.sessions - 1, "prior activity");
  state.activity.forEach((session, id) => {
    fields(session, ["id", "source_id", "opened_by", "loading", "new_work", "events"], "session");
    need(session.id === id, "INVALID_REFERENCE", "Session IDs must be contiguous");
    sourceId(session.source_id, "session source");
    need(session.opened_by === "compile" || session.opened_by === "saved_open", "INVALID_SESSION", "Unknown session origin");
    if (session.loading !== null) {
      fields(session.loading, ["directions_indexed", "absolute_profiles_loaded", "threshold_rows_loaded",
        "gcd_records_loaded", "mathematical_proof_replayed"], "loading");
      need(session.loading.mathematical_proof_replayed === false, "INVALID_LOADING", "Saved open must not claim proof replay");
      for (const key of Object.keys(session.loading)) if (key !== "mathematical_proof_replayed")
        integer(session.loading[key], 0, LIMITS.copy_items, "loading count");
    }
    validateWork(session.new_work, "session work");
    array(session.events, LIMITS.events_per_session, "session events");
    session.events.forEach(event => object(event, "event"));
  });
}
function openRectangularLineIndex(snapshot, args) {
  options(args, ["source_id"], "open options");
  const id = sourceId(args.source_id, "saved reader source_id"), state = copy(snapshot);
  validateSaved(state);
  const loading = {
    directions_indexed: state.directions.length,
    absolute_profiles_loaded: state.profiles.length,
    threshold_rows_loaded: state.profiles.reduce((sum, profile) => sum + profile.threshold_rows.length, 0),
    gcd_records_loaded: state.gcd_candidates.length, mathematical_proof_replayed: false
  };
  return makeIndex(state, id, "saved_open", zeroWork(), loading);
}

function makeIndex(state, readerId, openedBy, initialWork, loading) {
  need(state.activity.length < LIMITS.sessions, "SESSION_LIMIT", "Saved-session capacity exceeded");
  const session = {id: state.activity.length, source_id: readerId, opened_by: openedBy,
    loading, new_work: initialWork, events: []};
  state.activity.push(session);
  const rect = state.rectangle, w = rect.width, h = rect.height;
  const xOrigin = BigInt(rect.x_origin), yOrigin = BigInt(rect.y_origin);
  const byDirection = new Map(state.directions.map(direction => [direction.u + "," + direction.v, direction]));
  const prefixMaps = new Map(state.threshold_views.map(view =>
    [view.k, new Map(view.blocks.map(block => [block.direction_id, block]))]));
  function inc(key, amount = 1) {
    need(WORK_KEYS.includes(key) && Number.isSafeInteger(amount) && amount >= 0,
      "INTERNAL_COUNTER", "Invalid work increment");
    need(Number.isSafeInteger(state.work[key] + amount) && Number.isSafeInteger(session.new_work[key] + amount),
      "COUNTER_LIMIT", "Work counter overflow");
    state.work[key] += amount; session.new_work[key] += amount;
  }
  function invoke(name, request, operation) {
    need(session.events.length < LIMITS.events_per_session, "EVENT_LIMIT", "Open a saved snapshot before making more requests");
    const before = copy(session.new_work); inc("query_calls");
    try {
      const result = operation();
      const delta = Object.fromEntries(WORK_KEYS.map(key => [key, session.new_work[key] - before[key]]));
      const answer = copy({...result, new_work: delta});
      session.events.push({operation: name, request: copy(request), status: result.status});
      return answer;
    } catch (error) {
      session.events.push({operation: name, request: copy(request), status: "error",
        error_code: typeof error.code === "string" ? error.code : "QUERY_ERROR"});
      throw error;
    }
  }
  function minimum(value) { return integer(value, 2, Number.MAX_SAFE_INTEGER - 1, "minimum_points"); }
  function viewFor(k) {
    return k <= state.totals.maximum_collinearity + 1 ?
      state.threshold_views[k - 2] : {k, blocks: [], total: 0, exact_count: 0};
  }
  function quotient(dividend, divisor) {
    need(Number.isSafeInteger(dividend) && dividend >= 0 && Number.isSafeInteger(divisor) && divisor > 0,
      "INTERNAL_DIVISION", "Query quotient requires nonnegative exact integers and a positive divisor");
    inc("query_divisions"); return Math.floor(dividend / divisor);
  }
  function pointInput(value, name) {
    need(Array.isArray(value) && value.length === 2, "INVALID_POINT", name + " must be [x,y]");
    const x = coordinate(value[0], name + ".x", LIMITS.point_digits);
    const y = coordinate(value[1], name + ".y", LIMITS.point_digits);
    const ix = x - xOrigin, iy = y - yOrigin;
    need(ix >= 0n && ix < BigInt(w) && iy >= 0n && iy < BigInt(h),
      "OUTSIDE_RECTANGLE", name + " is outside the declared rectangle");
    return {x_index: Number(ix), y_index: Number(iy), coordinates: [x.toString(), y.toString()]};
  }
  function pointRecord(ix, iy) {
    return {point_id: ix * h + iy, x_index: ix, y_index: iy,
      x: (xOrigin + BigInt(ix)).toString(), y: (yOrigin + BigInt(iy)).toString()};
  }
  function address(direction, startX, startY) {
    return {source_id: state.source_id, direction_id: direction.id,
      start_x: startX, start_y_reflected: startY};
  }
  function addressInput(value) {
    fields(value, ["source_id", "direction_id", "start_x", "start_y_reflected"], "line address");
    need(value.source_id === state.source_id, "ADDRESS_SOURCE_MISMATCH", "Line address belongs to another declared index");
    integer(value.direction_id, 0, state.directions.length - 1, "address direction");
    integer(value.start_x, 0, w - 1, "address start x");
    integer(value.start_y_reflected, 0, h - 1, "address reflected start y");
    const direction = state.directions[value.direction_id], a = direction.u, b = Math.abs(direction.v);
    need(value.start_x < a || value.start_y_reflected < b,
      "NONCANONICAL_START", "Line address must begin where the previous primitive step leaves the rectangle");
    return copy(value);
  }
  function backwardStart(point, direction) {
    const a = direction.u, b = Math.abs(direction.v);
    const y = direction.v < 0 ? h - 1 - point.y_index : point.y_index;
    const quotients = [];
    if (a > 0) quotients.push({axis: "x", dividend: point.x_index, step: a, quotient: quotient(point.x_index, a)});
    if (b > 0) quotients.push({axis: "reflected_y", dividend: y, step: b, quotient: quotient(y, b)});
    const steps = Math.min(...quotients.map(row => row.quotient));
    return {address: address(direction, point.x_index - steps * a, y - steps * b),
      backward_steps: steps, quotients};
  }
  function forwardLength(lineAddress, direction) {
    const a = direction.u, b = Math.abs(direction.v), quotients = [];
    if (a > 0) quotients.push({axis: "x", dividend: w - 1 - lineAddress.start_x,
      step: a, quotient: quotient(w - 1 - lineAddress.start_x, a)});
    if (b > 0) quotients.push({axis: "reflected_y", dividend: h - 1 - lineAddress.start_y_reflected,
      step: b, quotient: quotient(h - 1 - lineAddress.start_y_reflected, b)});
    const steps = Math.min(...quotients.map(row => row.quotient));
    return {length: steps + 1, forward_steps: steps, quotients};
  }
  function pointAt(lineAddress, direction, offset) {
    const ix = lineAddress.start_x + offset * direction.u;
    const reflectedY = lineAddress.start_y_reflected + offset * Math.abs(direction.v);
    const iy = direction.v < 0 ? h - 1 - reflectedY : reflectedY;
    return pointRecord(ix, iy);
  }
  function descriptor(lineAddress, knownForward) {
    const direction = state.directions[lineAddress.direction_id];
    const forward = knownForward || forwardLength(lineAddress, direction);
    need(forward.length >= 2, "NOT_DETERMINED_LINE", "Address contains fewer than two grid points");
    const first = pointAt(lineAddress, direction, 0), last = pointAt(lineAddress, direction, forward.length - 1);
    let A = BigInt(direction.v), B = -BigInt(direction.u);
    let C = BigInt(direction.u) * BigInt(first.y) - BigInt(direction.v) * BigInt(first.x);
    if (A < 0n || (A === 0n && B < 0n)) { A = -A; B = -B; C = -C; }
    inc("line_descriptors_materialized");
    return {address: copy(lineAddress), direction: {u: direction.u, v: direction.v},
      absolute_profile_id: direction.profile_id, length: forward.length,
      first_point: first, last_point: last, equation: {a: A.toString(), b: B.toString(), c: C.toString(), form: "a*x+b*y+c=0"},
      forward_quotients: forward.quotients};
  }
  function localRank(lineAddress, k) {
    const direction = state.directions[lineAddress.direction_id];
    const profile = state.profiles[direction.profile_id], row = profile.threshold_rows[k - 2];
    const block = prefixMaps.get(k)?.get(direction.id);
    if (!row || !block) return null;
    const x = lineAddress.start_x, y = lineAddress.start_y_reflected;
    let local = null, slabName = null;
    for (const [name, slab] of [["a", row.slab_a], ["b", row.slab_b]]) {
      if (slab.count > 0 && x >= slab.x_start && x < slab.x_start + slab.width && y >= 0 && y < slab.height) {
        local = (name === "a" ? 0 : row.slab_a.count) + (x - slab.x_start) * slab.height + y;
        slabName = name; break;
      }
    }
    if (local === null) return null;
    return {rank: block.prefix_start + local, local_rank: local, slab: slabName,
      prefix_start: block.prefix_start, prefix_end: block.prefix_end,
      profile_row_index: block.profile_row_index};
  }
  function selectRaw(k, rank) {
    const view = viewFor(k);
    if (rank >= view.total) return {status: "rank_out_of_range", minimum_points: k, rank, total: view.total};
    let low = 0, high = view.blocks.length;
    while (low < high) {
      inc("query_binary_search_steps"); const middle = Math.floor((low + high) / 2);
      if (rank < view.blocks[middle].prefix_end) high = middle; else low = middle + 1;
    }
    const block = view.blocks[low], direction = state.directions[block.direction_id];
    const profile = state.profiles[direction.profile_id], row = profile.threshold_rows[block.profile_row_index];
    const local = rank - block.prefix_start, firstSlab = local < row.slab_a.count;
    const slab = firstSlab ? row.slab_a : row.slab_b;
    const slabRank = firstSlab ? local : local - row.slab_a.count;
    need(slab.count > 0 && slab.height > 0 && slabRank < slab.count,
      "INVALID_SAVED_SELECTION", "Retained prefix does not select a nonempty boundary slab");
    const column = quotient(slabRank, slab.height), y = slabRank - column * slab.height;
    const lineAddress = address(direction, slab.x_start + column, y);
    const line = descriptor(lineAddress);
    need(line.length >= k, "INVALID_SAVED_SELECTION", "Selected saved start fails its threshold");
    return {status: "selected", minimum_points: k, rank, total: view.total,
      direction_block: {direction_id: direction.id, prefix_start: block.prefix_start,
        prefix_end: block.prefix_end, local_rank: local, slab: firstSlab ? "a" : "b", slab_rank: slabRank},
      line};
  }
  function countLines(args) {
    options(args, ["minimum_points"], "count options");
    const k = minimum(args.minimum_points);
    return invoke("countLines", {minimum_points: k}, () => {
      const view = viewFor(k); inc("count_rows_returned");
      return {status: "retained_count", minimum_points: k, at_least_count: view.total,
        exact_count: view.exact_count, maximum_collinearity: state.totals.maximum_collinearity,
        ordering: "signed direction (u,v), then start_x, then start_y_reflected"};
    });
  }
  function selectLine(args) {
    options(args, ["minimum_points", "rank"], "select options");
    const k = minimum(args.minimum_points), rank = integer(args.rank, 0, Number.MAX_SAFE_INTEGER, "rank");
    return invoke("selectLine", {minimum_points: k, rank}, () => selectRaw(k, rank));
  }
  function rankLine(args) {
    options(args, ["minimum_points", "point_a", "point_b"], "rank options");
    const k = minimum(args.minimum_points), first = pointInput(args.point_a, "point_a"), second = pointInput(args.point_b, "point_b");
    need(first.x_index !== second.x_index || first.y_index !== second.y_index,
      "COINCIDENT_POINTS", "Two distinct points are required to determine a line");
    return invoke("rankLine", {minimum_points: k, point_a: first.coordinates, point_b: second.coordinates}, () => {
      let dx = second.x_index - first.x_index, dy = second.y_index - first.y_index;
      let a = Math.abs(dx), b = Math.abs(dy); const chain = [];
      while (b !== 0) {
        const q = quotient(a, b), remainder = a - q * b;
        chain.push({dividend: a, divisor: b, quotient: q, remainder});
        a = b; b = remainder; inc("query_gcd_steps");
      }
      const divisor = a;
      const originalDifference = {dx, dy};
      dx = (dx < 0 ? -1 : 1) * quotient(Math.abs(dx), divisor);
      dy = (dy < 0 ? -1 : 1) * quotient(Math.abs(dy), divisor);
      if (dx < 0 || (dx === 0 && dy < 0)) { dx = -dx; dy = -dy; }
      const direction = byDirection.get(dx + "," + dy);
      need(direction, "INVALID_SAVED_DIRECTION", "Retained catalog omits the determined primitive direction");
      const backward = backwardStart(first, direction), forward = forwardLength(backward.address, direction);
      const line = descriptor(backward.address, forward);
      const rank = localRank(backward.address, k);
      if (forward.length < k) return {status: "below_threshold", minimum_points: k, rank: null,
        line, normalization: {difference: originalDifference, gcd: divisor, gcd_divisions: chain, backward}};
      need(rank !== null, "INVALID_SAVED_RANK", "Qualified line is absent from its retained prefix view");
      return {status: "ranked", minimum_points: k, total: viewFor(k).total, ...rank, line,
        normalization: {difference: originalDifference, gcd: divisor, gcd_divisions: chain, backward}};
    });
  }

  function pageLines(args) {
    options(args, ["minimum_points", "offset", "limit"], "line-page options");
    const k = minimum(args.minimum_points);
    const offset = args.offset === undefined ? 0 : integer(args.offset, 0, Number.MAX_SAFE_INTEGER, "offset");
    const limit = args.limit === undefined ? 64 : integer(args.limit, 1, LIMITS.page_size, "limit");
    return invoke("pageLines", {minimum_points: k, offset, limit}, () => {
      const total = viewFor(k).total, start = Math.min(offset, total), end = Math.min(start + limit, total);
      const items = [];
      for (let rank = start; rank < end; rank++) items.push(selectRaw(k, rank));
      return {status: "line_page", minimum_points: k, offset, limit, total, returned: items.length,
        next_offset: end < total ? end : null, items};
    });
  }
  function pageLinePoints(args) {
    options(args, ["address", "offset", "limit"], "point-page options");
    const lineAddress = addressInput(args.address);
    const offset = args.offset === undefined ? 0 : integer(args.offset, 0, Number.MAX_SAFE_INTEGER, "offset");
    const limit = args.limit === undefined ? 64 : integer(args.limit, 1, LIMITS.page_size, "limit");
    return invoke("pageLinePoints", {address: lineAddress, offset, limit}, () => {
      const direction = state.directions[lineAddress.direction_id], forward = forwardLength(lineAddress, direction);
      need(forward.length >= 2, "NOT_DETERMINED_LINE", "Address does not represent a line determined by the grid");
      const start = Math.min(offset, forward.length), end = Math.min(start + limit, forward.length), items = [];
      for (let position = start; position < end; position++) {
        items.push({position, ...pointAt(lineAddress, direction, position)});
        inc("line_point_records_materialized");
      }
      return {status: "line_point_page", line: descriptor(lineAddress, forward), offset, limit,
        total: forward.length, returned: items.length, next_offset: end < forward.length ? end : null, items};
    });
  }
  function assess(args) {
    options(args, ["k"], "assessment options");
    const k = integer(args.k, 4, Number.MAX_SAFE_INTEGER - 1, "k");
    return invoke("assess", {k}, () => {
      const current = viewFor(k), next = viewFor(k + 1);
      const admissible = state.totals.maximum_collinearity <= k;
      inc("count_rows_returned", 2);
      const overfull = next.total > 0 ? selectRaw(k + 1, 0).line : null;
      return {status: "assessment", k, point_count: state.totals.point_count,
        maximum_collinearity: state.totals.maximum_collinearity, property_P_k: admissible,
        exact_k_lines: current.exact_count, at_least_k_lines: current.total,
        overfull_line_count: next.total, first_overfull_line: overfull,
        finite_extremal_lower_bound: admissible ? {notation: "f_k(n)", k,
          n: state.totals.point_count, at_least: current.exact_count} : null,
        global_optimum_claimed: false, asymptotic_claimed: false};
    });
  }
  function linesThroughPoint(args) {
    options(args, ["point", "minimum_points"], "point-incidence options");
    const point = pointInput(args.point, "point"), k = minimum(args.minimum_points);
    return invoke("linesThroughPoint", {point: point.coordinates, minimum_points: k}, () => {
      const scanned = [], matches = [];
      for (const direction of state.directions) {
        inc("point_incidence_directions_examined");
        const backward = backwardStart(point, direction), forward = forwardLength(backward.address, direction);
        let rank = null;
        if (forward.length >= k) {
          const ranked = localRank(backward.address, k);
          need(ranked !== null, "INVALID_SAVED_INCIDENCE", "Qualified point-line incidence is absent from its retained prefix view");
          rank = ranked.rank;
          matches.push({address: backward.address, length: forward.length, rank});
        }
        scanned.push([direction.id, backward.address.start_x, backward.address.start_y_reflected,
          backward.backward_steps, forward.length, rank]);
      }
      return {status: "point_incidences", point: pointRecord(point.x_index, point.y_index),
        minimum_points: k, total: matches.length, matches,
        scanned_row_fields: ["direction_id", "start_x", "start_y_reflected", "backward_steps", "maximal_length", "qualified_rank_or_null"],
        scanned_directions: scanned};
    });
  }
  function summary() {
    return copy({schema: SCHEMA, source_id: state.source_id, rectangle_source_id: state.rectangle_source_id,
      rectangle: state.rectangle, ordering: "signed direction (u,v), then start_x, then start_y_reflected",
      ranks: "zero-based and threshold-specific", point_id: "x_index*height+y_index",
      positive_direction_candidates: state.gcd_candidates.length, absolute_profiles: state.profiles.length,
      signed_directions: state.directions.length,
      retained_step_weights: state.profiles.reduce((sum, profile) => sum + profile.step_weights.length, 0),
      retained_profile_thresholds: state.profiles.reduce((sum, profile) => sum + profile.threshold_rows.length, 0),
      retained_global_prefix_blocks: state.threshold_views.reduce((sum, view) => sum + view.blocks.length, 0),
      totals: state.totals,
      histogram: state.threshold_views.filter(view => view.k <= state.totals.maximum_collinearity)
        .map(view => ({multiplicity: view.k, exact_lines: view.exact_count, at_least_lines: view.total})),
      work: state.work,
      active_session: {id: session.id, source_id: session.source_id, opened_by: session.opened_by,
        loading: session.loading, new_work: session.new_work, event_count: session.events.length}});
  }
  function snapshot() { return copy(state); }
  return Object.freeze({countLines, assess, selectLine, rankLine, pageLines,
    pageLinePoints, linesThroughPoint, summary, snapshot});
}
module.exports = Object.freeze({SCHEMA, LIMITS, compileRectangularLineIndex, openRectangularLineIndex});
