"use strict";

// Finite inverse fibers of the Erdos-Hajnal tournament construction.
// CFS, arXiv:0808.3760, printed p.3: cyclic triples red, other triples blue.
// Labels and reversed orientations are distinct. No asymptotic Ramsey claim.

const SCHEMA = "commons.tournament_inverse_fibers/v1";
const LIMITS = Object.freeze({
  min_vertices: 3, max_vertices: 6, max_page: 64,
  max_sessions: 24, max_events_per_session: 128, max_source_id_chars: 512,
  max_copy_items: 4000000, max_copy_chars: 32000000, max_copy_depth: 48
});
function fail(code, message) { const error = new Error(message); error.code = code; throw error; }
function object(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    fail("INVALID_INPUT", name + " must be an object");
  return value;
}
function integer(value, lower, upper, name) {
  if (!Number.isSafeInteger(value) || value < lower || value > upper)
    fail("INVALID_INPUT", name + " must be a safe integer in [" + lower + "," + upper + "]");
  return value;
}
function sourceId(value) {
  if (typeof value !== "string" || value.length < 1 || value.length > LIMITS.max_source_id_chars)
    fail("INVALID_INPUT", "source_id must be a nonempty bounded string");
  return value;
}
function cloneReport(input) {
  let items = 0, chars = 0, maxDepth = 0;
  function walk(value, depth) {
    items++; maxDepth = Math.max(maxDepth, depth);
    if (items > LIMITS.max_copy_items || depth > LIMITS.max_copy_depth)
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
    if (Array.isArray(value)) {
      const result = [];
      for (let i = 0; i < value.length; i++) {
        if (!Object.hasOwn(value, i)) fail("INVALID_RECORD", "sparse arrays are not JSON records");
        result.push(walk(value[i], depth + 1));
      }
      return result;
    }
    if (typeof value !== "object") fail("INVALID_RECORD", "only plain JSON records can be retained");
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
  const value = walk(input, 0);
  return { value, items, chars, max_depth: maxDepth };
}
function copy(input) { return cloneReport(input).value; }
function queryWork() {
  return {
    calls: 0, binary_steps: 0, orientation_word_reads: 0, orientation_edge_bit_reads: 0,
    fiber_records_read: 0, signature_mask_checks: 0, subset_mask_checks: 0,
    pattern_fibers_scanned: 0, prefix_count_additions: 0, order_score_increments: 0,
    order_sort_comparisons: 0, order_score_shape_checks: 0, reversal_complements: 0,
    constraint_bits_set: 0, constraint_overlap_checks: 0,
    returned_records: 0, orientations_enumerated: 0, cyclic_triples_reclassified: 0,
    inverse_index_rebuilt: 0
  };
}
function addWork(total, delta) { for (const key of Object.keys(delta)) total[key] += delta[key]; }
function lowerBound(array, wanted, work) {
  let lo = 0, hi = array.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2); work.binary_steps++;
    if (array[mid] < wanted) lo = mid + 1; else hi = mid;
  }
  return lo;
}
function compileTournamentFibers(request) {
  object(request, "request");
  const id = sourceId(request.source_id);
  const n = integer(request.vertices, LIMITS.min_vertices, LIMITS.max_vertices, "vertices");
  const work = {
    edge_records: 0, triple_records: 0, quadruple_records: 0, quadruple_face_bindings: 0,
    subset_records: 0, subset_vertex_bit_reads: 0, subset_triple_containment_checks: 0,
    orientations_enumerated: 0, edge_bit_extractions: 0, cyclic_triple_classifications: 0,
    cyclic_comparison_tests: 0, cyclic_bit_updates: 0, histogram_updates: 0,
    inverse_bucket_insertions: 0, signature_sort_comparisons: 0,
    inverse_codes_appended: 0, inverse_fibers: 0, inverse_prefix_additions: 0
  };
  const edges = [], edgeLookup = Array.from({ length: n }, () => Array(n).fill(-1));
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const eid = edges.length;
    edges.push({ id: eid, lower_vertex: i, upper_vertex: j });
    edgeLookup[i][j] = eid; work.edge_records++;
  }
  const triples = [], tripleLookup = new Map();
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++)
    for (let k = j + 1; k < n; k++) {
      const tid = triples.length;
      triples.push({ id: tid, vertices: [i, j, k],
        vertex_mask: (1 << i) | (1 << j) | (1 << k),
        edge_ids: [edgeLookup[i][j], edgeLookup[i][k], edgeLookup[j][k]] });
      tripleLookup.set(i + "," + j + "," + k, tid); work.triple_records++;
    }
  const quadruples = [];
  for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++)
    for (let c = b + 1; c < n; c++) for (let d = c + 1; d < n; d++) {
      const vertices = [a, b, c, d], tripleIds = [];
      let mask = 0;
      for (let omit = 0; omit < 4; omit++) {
        const face = vertices.filter((_, index) => index !== omit);
        const tid = tripleLookup.get(face.join(","));
        tripleIds.push(tid); mask |= 1 << tid; work.quadruple_face_bindings++;
      }
      quadruples.push({ id: quadruples.length, vertices, triple_ids: tripleIds, triple_mask: mask });
      work.quadruple_records++;
    }
  const subsets = [];
  for (let mask = 0; mask < 2 ** n; mask++) {
    const vertices = [];
    for (let v = 0; v < n; v++) {
      work.subset_vertex_bit_reads++;
      if ((mask & (1 << v)) !== 0) vertices.push(v);
    }
    let tripleMask = 0;
    for (const triple of triples) {
      work.subset_triple_containment_checks++;
      if ((mask & triple.vertex_mask) === triple.vertex_mask) tripleMask |= 1 << triple.id;
    }
    subsets.push({ mask, size: vertices.length, vertices, triple_mask: tripleMask });
    work.subset_records++;
  }
  const total = 2 ** edges.length, words = Array(total), buckets = new Map();
  const histogram = Array(triples.length + 1).fill(0);
  let maximum = { cyclic_triples: -1, first_orientation_code: null, signature: null };
  for (let code = 0; code < total; code++) {
    let signature = 0, cyclicCount = 0;
    for (const triple of triples) {
      const a = (code >>> triple.edge_ids[0]) & 1;
      const b = (code >>> triple.edge_ids[1]) & 1;
      const c = (code >>> triple.edge_ids[2]) & 1;
      work.edge_bit_extractions += 3; work.cyclic_triple_classifications++;
      work.cyclic_comparison_tests++;
      let cyclic = false;
      if (a === c) { work.cyclic_comparison_tests++; cyclic = b !== a; }
      if (cyclic) { signature |= 1 << triple.id; cyclicCount++; work.cyclic_bit_updates++; }
    }
    words[code] = signature; histogram[cyclicCount]++; work.histogram_updates++;
    if (cyclicCount > maximum.cyclic_triples)
      maximum = { cyclic_triples: cyclicCount, first_orientation_code: code, signature };
    let bucket = buckets.get(signature);
    if (bucket === undefined) { bucket = []; buckets.set(signature, bucket); }
    bucket.push(code); work.inverse_bucket_insertions++; work.orientations_enumerated++;
  }
  const signatures = Array.from(buckets.keys()).sort((a, b) => {
    work.signature_sort_comparisons++; return a - b;
  });
  const offsets = [0], codes = [], sizeHistogram = new Map();
  let largest = { fiber_index: null, signature: null, count: -1 };
  for (let f = 0; f < signatures.length; f++) {
    const signature = signatures[f], bucket = buckets.get(signature);
    for (const code of bucket) { codes.push(code); work.inverse_codes_appended++; }
    offsets.push(offsets[offsets.length - 1] + bucket.length);
    work.inverse_prefix_additions++; work.inverse_fibers++;
    sizeHistogram.set(bucket.length, (sizeHistogram.get(bucket.length) || 0) + 1);
    if (bucket.length > largest.count) largest = { fiber_index: f, signature, count: bucket.length };
  }
  const data = {
    schema: SCHEMA, source_id: id, request: { source_id: id, vertices: n },
    conventions: {
      vertices: "integer labels zero through n-1",
      edge_order: "lexicographic unordered pairs i<j; bit1 means i points to j",
      triple_order: "lexicographic unordered triples i<j<k",
      cyclic_color: "red; edge bits ij=jk and ik differs",
      transitive_color: "blue",
      orientation_order: "increasing integer edge-bit code",
      fiber_order: "increasing cyclic-triple signature, then increasing orientation code",
      reversal: "all edge bits complemented; both orientations remain distinct",
      family_scope: "images of labeled tournaments only, not every K4-free 3-graph",
      subset_scope: "empty, singleton and pair subsets are vacuously transitive",
      semantic_premise: "retained exact construction; saved opening is not independent proof authentication"
    },
    topology: { vertex_count: n, edge_count: edges.length, triple_count: triples.length,
      orientation_count: total, signature_space_size: 2 ** triples.length,
      edges, triples, quadruples, subsets },
    forward: { cyclic_words: words },
    inverse: { signatures, offsets, orientation_codes: codes },
    result: {
      complete_orientation_space: true, orientations: total, distinct_signatures: signatures.length,
      cyclic_count_histogram: histogram,
      fiber_size_histogram: Array.from(sizeHistogram).sort((a, b) => a[0] - b[0])
        .map(([size, fibers]) => ({ size, fibers })),
      maximum_cyclic: maximum, largest_fiber: largest,
      asymptotic_ramsey_claim: false
    },
    construction_work: work, sessions: []
  };
  return copy(data);
}

function validateSaved(data) {
  object(data, "saved index");
  if (data.schema !== SCHEMA) fail("INVALID_RECORD", "unsupported schema");
  sourceId(data.source_id); object(data.request, "request");
  if (data.request.source_id !== data.source_id) fail("INVALID_RECORD", "source/request binding");
  const n = integer(data.request.vertices, LIMITS.min_vertices, LIMITS.max_vertices, "vertices");
  const topology = object(data.topology, "topology");
  const E = n * (n - 1) / 2, T = n * (n - 1) * (n - 2) / 6, N = 2 ** E, W = 2 ** T;
  const checks = { edges: 0, triples: 0, quadruples: 0, subsets: 0, words: 0,
    fibers: 0, inverse_code_bindings: 0, reference_checks: 0, pattern_view_bindings: 0,
    orientations_reenumerated: 0, cyclic_triples_reclassified: 0,
    inverse_index_rebuilt: 0, mathematical_proof_authenticated: false };
  function length(value, expected, name) {
    if (!Array.isArray(value) || value.length !== expected) fail("INVALID_RECORD", name + " length");
  }
  function increasing(value, maximum, name, expected) {
    if (!Array.isArray(value) || (expected !== undefined && value.length !== expected))
      fail("INVALID_RECORD", name + " array");
    let last = -1;
    for (const item of value) {
      integer(item, 0, maximum, name);
      if (item <= last) fail("INVALID_RECORD", name + " must be strictly increasing");
      last = item; checks.reference_checks++;
    }
  }
  function counts(value, name, expectedKeys) {
    object(value, name);
    if (expectedKeys && (Object.keys(value).length !== expectedKeys.length ||
        expectedKeys.some(key => !Object.hasOwn(value, key))))
      fail("INVALID_RECORD", name + " counter keys");
    for (const [key, amount] of Object.entries(value))
      integer(amount, 0, Number.MAX_SAFE_INTEGER, name + "." + key);
  }
  if (topology.vertex_count !== n || topology.edge_count !== E || topology.triple_count !== T ||
      topology.orientation_count !== N || topology.signature_space_size !== W)
    fail("INVALID_RECORD", "topology counts");
  length(topology.edges, E, "edges"); length(topology.triples, T, "triples");
  length(topology.quadruples, n * (n - 1) * (n - 2) * (n - 3) / 24, "quadruples");
  length(topology.subsets, 2 ** n, "subsets");
  let priorPair = -1;
  for (let i = 0; i < E; i++) {
    const edge = topology.edges[i];
    if (edge.id !== i) fail("INVALID_RECORD", "edge id");
    integer(edge.lower_vertex, 0, n - 2, "lower vertex");
    integer(edge.upper_vertex, edge.lower_vertex + 1, n - 1, "upper vertex");
    const key = edge.lower_vertex * n + edge.upper_vertex;
    if (key <= priorPair) fail("INVALID_RECORD", "edge order"); priorPair = key; checks.edges++;
  }
  let priorTriple = -1;
  for (let i = 0; i < T; i++) {
    const triple = topology.triples[i];
    if (triple.id !== i) fail("INVALID_RECORD", "triple id");
    increasing(triple.vertices, n - 1, "triple vertices", 3);
    length(triple.edge_ids, 3, "triple edges");
    const [a, b, c] = triple.vertices, wanted = [[a, b], [a, c], [b, c]];
    const key = (a * n + b) * n + c;
    if (key <= priorTriple) fail("INVALID_RECORD", "triple order"); priorTriple = key;
    integer(triple.vertex_mask, 0, 2 ** n - 1, "triple vertex mask");
    for (let j = 0; j < 3; j++) {
      const eid = integer(triple.edge_ids[j], 0, E - 1, "triple edge id");
      const edge = topology.edges[eid];
      if (edge.lower_vertex !== wanted[j][0] || edge.upper_vertex !== wanted[j][1])
        fail("INVALID_RECORD", "triple edge binding");
      checks.reference_checks++;
    }
    checks.triples++;
  }
  for (let i = 0; i < topology.quadruples.length; i++) {
    const quad = topology.quadruples[i];
    if (quad.id !== i) fail("INVALID_RECORD", "quadruple id");
    increasing(quad.vertices, n - 1, "quadruple vertices", 4);
    length(quad.triple_ids, 4, "quadruple faces");
    const seen = new Set();
    for (const tid of quad.triple_ids) {
      integer(tid, 0, T - 1, "quadruple triple");
      if (seen.has(tid)) fail("INVALID_RECORD", "duplicate quadruple face");
      seen.add(tid); checks.reference_checks++;
    }
    integer(quad.triple_mask, 0, W - 1, "quadruple mask"); checks.quadruples++;
  }
  for (let mask = 0; mask < topology.subsets.length; mask++) {
    const subset = topology.subsets[mask];
    if (subset.mask !== mask) fail("INVALID_RECORD", "subset mask index");
    integer(subset.size, 0, n, "subset size");
    increasing(subset.vertices, n - 1, "subset vertices", subset.size);
    integer(subset.triple_mask, 0, W - 1, "subset triple mask"); checks.subsets++;
  }
  const forward = object(data.forward, "forward"), inverse = object(data.inverse, "inverse");
  length(forward.cyclic_words, N, "forward words");
  for (const word of forward.cyclic_words) {
    integer(word, 0, W - 1, "cyclic word"); checks.words++;
  }
  increasing(inverse.signatures, W - 1, "signatures");
  const F = inverse.signatures.length;
  integer(F, 1, N, "fiber count"); length(inverse.offsets, F + 1, "offsets");
  length(inverse.orientation_codes, N, "inverse codes");
  if (inverse.offsets[0] !== 0 || inverse.offsets[F] !== N)
    fail("INVALID_RECORD", "inverse endpoints");
  const seenCodes = new Set();
  for (let f = 0; f < F; f++) {
    const start = integer(inverse.offsets[f], 0, N - 1, "fiber start");
    const end = integer(inverse.offsets[f + 1], start + 1, N, "fiber end");
    let prior = -1;
    for (let j = start; j < end; j++) {
      const code = integer(inverse.orientation_codes[j], 0, N - 1, "orientation code");
      if (code <= prior || seenCodes.has(code)) fail("INVALID_RECORD", "inverse code order/uniqueness");
      if (forward.cyclic_words[code] !== inverse.signatures[f])
        fail("INVALID_RECORD", "forward/inverse word binding");
      prior = code; seenCodes.add(code); checks.inverse_code_bindings++;
    }
    checks.fibers++;
  }
  if (seenCodes.size !== N) fail("INVALID_RECORD", "inverse permutation coverage");
  const result = object(data.result, "result");
  if (result.complete_orientation_space !== true || result.orientations !== N ||
      result.distinct_signatures !== F) fail("INVALID_RECORD", "complete index summary binding");
  counts(data.construction_work, "construction work");
  if (!Array.isArray(data.sessions) || data.sessions.length >= LIMITS.max_sessions)
    fail("INVALID_RECORD", "session count");
  const sessionSources = new Set();
  for (let si = 0; si < data.sessions.length; si++) {
    const session = data.sessions[si];
    if (session.id !== si) fail("INVALID_RECORD", "session id");
    sourceId(session.source_id);
    if (sessionSources.has(session.source_id)) fail("INVALID_RECORD", "duplicate session source");
    sessionSources.add(session.source_id);
    if (!Array.isArray(session.queries) || session.queries.length > LIMITS.max_events_per_session)
      fail("INVALID_RECORD", "query count");
    counts(session.query_work, "session work", Object.keys(queryWork()));
    for (let qi = 0; qi < session.queries.length; qi++) {
      const query = session.queries[qi];
      if (query.id !== qi || !["ok", "error"].includes(query.status) ||
          typeof query.method !== "string" || query.method.length > 200)
        fail("INVALID_RECORD", "query id/status/method");
      counts(query.work, "query work", Object.keys(queryWork()));
      if (query.method === "createPatternView" && query.status === "ok") {
        const view = object(query.result, "pattern view");
        object(view.reference, "pattern reference");
        if (view.kind !== "signature_pattern" || view.source_id !== data.source_id ||
            view.reference.session_id !== si || view.reference.query_id !== qi)
          fail("INVALID_RECORD", "pattern source/reference");
        integer(view.required_cyclic_mask, 0, W - 1, "required cyclic mask");
        integer(view.required_transitive_mask, 0, W - 1, "required transitive mask");
        increasing(view.fiber_indices, F - 1, "view fiber ids");
        length(view.orientation_prefixes, view.fiber_indices.length + 1, "view prefixes");
        if (view.orientation_prefixes[0] !== 0 ||
            view.signature_count !== view.fiber_indices.length ||
            view.orientation_count !== view.orientation_prefixes[view.fiber_indices.length])
          fail("INVALID_RECORD", "view count/endpoints");
        for (let j = 0; j < view.fiber_indices.length; j++) {
          const f = view.fiber_indices[j];
          if (view.orientation_prefixes[j + 1] - view.orientation_prefixes[j] !==
              inverse.offsets[f + 1] - inverse.offsets[f])
            fail("INVALID_RECORD", "view fiber weight binding");
          integer(view.orientation_prefixes[j + 1], 1, N, "view prefix"); checks.pattern_view_bindings++;
        }
      }
    }
  }
  return checks;
}
function openTournamentFibers(saved, options) {
  object(options, "options"); const id = sourceId(options.source_id);
  const copied = cloneReport(saved), data = copied.value, validation = validateSaved(data);
  if (data.sessions.some(session => session.source_id === id))
    fail("INVALID_INPUT", "session source_id already exists");
  const sessionIndex = data.sessions.length;
  const current = { id: sessionIndex, source_id: id, validation, queries: [], query_work: queryWork() };
  const sessionCopy = cloneReport(current);
  const occupied = { items: copied.items + sessionCopy.items, chars: copied.chars + sessionCopy.chars,
    max_depth: Math.max(copied.max_depth, sessionCopy.max_depth + 2) };
  if (occupied.items > LIMITS.max_copy_items || occupied.chars > LIMITS.max_copy_chars ||
      occupied.max_depth > LIMITS.max_copy_depth) fail("COPY_LIMIT", "new session exceeds export budget");
  data.sessions.push(sessionCopy.value);
  const session = data.sessions[sessionIndex], n = data.topology.vertex_count,
    N = data.topology.orientation_count, W = data.topology.signature_space_size;
  function appendEvent(report) {
    const nextItems = occupied.items + report.items, nextChars = occupied.chars + report.chars;
    const nextDepth = Math.max(occupied.max_depth, report.max_depth + 4);
    if (nextItems > LIMITS.max_copy_items || nextChars > LIMITS.max_copy_chars ||
        nextDepth > LIMITS.max_copy_depth) fail("COPY_LIMIT", "query receipt exceeds export budget");
    const nextWork = {};
    for (const key of Object.keys(session.query_work)) {
      const count = session.query_work[key] + report.value.work[key];
      integer(count, 0, Number.MAX_SAFE_INTEGER, "accumulated query work"); nextWork[key] = count;
    }
    session.queries.push(report.value);
    for (const key of Object.keys(nextWork)) session.query_work[key] = nextWork[key];
    occupied.items = nextItems; occupied.chars = nextChars; occupied.max_depth = nextDepth;
  }
  function query(method, args, run) {
    if (session.queries.length >= LIMITS.max_events_per_session)
      fail("EVENT_LIMIT", "session query history is full");
    object(args, "query arguments"); const retainedArgs = copy(args), work = queryWork(); work.calls = 1;
    const queryId = session.queries.length;
    try {
      const result = run(args, work, queryId);
      const event = cloneReport({ id: queryId, method, args: retainedArgs, status: "ok",
        result, work });
      const callerResult = copy(result);
      appendEvent(event); return callerResult;
    } catch (error) {
      try {
        appendEvent(cloneReport({ id: queryId, method, args: retainedArgs, status: "error",
          error: { code: error.code || "QUERY_ERROR", message: error.message }, work }));
      } catch (retentionError) { error.retention_error = retentionError.message; }
      throw error;
    }
  }
  function signature(value) { return integer(value, 0, W - 1, "signature"); }
  function orientation(value) { return integer(value, 0, N - 1, "orientation_code"); }
  function fiberIndex(word, work) {
    const at = lowerBound(data.inverse.signatures, word, work);
    return at < data.inverse.signatures.length && data.inverse.signatures[at] === word ? at : -1;
  }
  function fiberDescription(f, work) {
    work.fiber_records_read++;
    const start = data.inverse.offsets[f], end = data.inverse.offsets[f + 1];
    return { found: true, fiber_index: f, signature: data.inverse.signatures[f],
      orientation_count: end - start, first_orientation_code: data.inverse.orientation_codes[start],
      last_orientation_code: data.inverse.orientation_codes[end - 1], complete_orientation_space: true };
  }
  function missingFiber(word) {
    return { found: false, fiber_index: null, signature: word, orientation_count: 0,
      first_orientation_code: null, last_orientation_code: null, complete_orientation_space: true,
      reason: "no_orientation_in_complete_labeled_space" };
  }
  function fiberRank(f, code, work) {
    let lo = data.inverse.offsets[f], hi = data.inverse.offsets[f + 1];
    const start = lo, end = hi;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2); work.binary_steps++;
      if (data.inverse.orientation_codes[mid] < code) lo = mid + 1; else hi = mid;
    }
    return lo < end && data.inverse.orientation_codes[lo] === code ? lo - start : -1;
  }
  function pageBounds(args, total) {
    const offset = integer(args.offset, 0, total, "offset");
    const limit = integer(args.limit, 1, LIMITS.max_page, "limit");
    return { offset, end: Math.min(total, offset + limit), total };
  }
  function pageResult(bounds, records) {
    return { offset: bounds.offset, total: bounds.total, records,
      next_offset: bounds.end < bounds.total ? bounds.end : null };
  }
  function patternReference(args) {
    const ref = object(args.view, "view reference");
    const si = integer(ref.session_id, 0, data.sessions.length - 1, "view session");
    const qi = integer(ref.query_id, 0, data.sessions[si].queries.length - 1, "view query");
    const record = data.sessions[si].queries[qi];
    if (record.method !== "createPatternView" || record.status !== "ok" ||
        record.result.kind !== "signature_pattern" || record.result.source_id !== data.source_id ||
        record.result.reference.session_id !== si || record.result.reference.query_id !== qi)
      fail("INVALID_INPUT", "reference is not a retained pattern view");
    return record.result;
  }
  function selectPattern(view, rank, work) {
    if (rank >= view.orientation_count)
      return { found: false, rank, orientation_code: null, signature: null, fiber_index: null,
        reason: "rank_outside_pattern_view" };
    let lo = 0, hi = view.fiber_indices.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2); work.binary_steps++;
      if (view.orientation_prefixes[mid + 1] <= rank) lo = mid + 1; else hi = mid;
    }
    const f = view.fiber_indices[lo], within = rank - view.orientation_prefixes[lo];
    const code = data.inverse.orientation_codes[data.inverse.offsets[f] + within];
    return { found: true, rank, orientation_code: code, signature: data.inverse.signatures[f],
      fiber_index: f, within_fiber_rank: within, view_fiber_position: lo };
  }

  const api = {
    findFiber(args) {
      return query("findFiber", args, (input, work) => {
        const word = signature(input.signature), f = fiberIndex(word, work);
        work.returned_records++; return f < 0 ? missingFiber(word) : fiberDescription(f, work);
      });
    },
    pageSignatures(args) {
      return query("pageSignatures", args, (input, work) => {
        const bounds = pageBounds(input, data.inverse.signatures.length), records = [];
        for (let f = bounds.offset; f < bounds.end; f++) records.push(fiberDescription(f, work));
        work.returned_records += records.length; return pageResult(bounds, records);
      });
    },
    getOrientation(args) {
      return query("getOrientation", args, (input, work) => {
        const code = orientation(input.orientation_code), word = data.forward.cyclic_words[code];
        work.orientation_word_reads++;
        const directedEdges = data.topology.edges.map(edge => {
          const forward = ((code >>> edge.id) & 1) === 1; work.orientation_edge_bit_reads++;
          return { edge_id: edge.id, from: forward ? edge.lower_vertex : edge.upper_vertex,
            to: forward ? edge.upper_vertex : edge.lower_vertex, forward_bit: forward ? 1 : 0 };
        });
        const f = fiberIndex(word, work);
        work.returned_records++;
        return { orientation_code: code, signature: word, fiber_index: f, directed_edges: directedEdges,
          cyclic_word_basis: "retained constructor output; no triple reclassification" };
      });
    },
    pageFiber(args) {
      return query("pageFiber", args, (input, work) => {
        const word = signature(input.signature), f = fiberIndex(word, work);
        const size = f < 0 ? 0 : data.inverse.offsets[f + 1] - data.inverse.offsets[f];
        const bounds = pageBounds(input, size), records = [];
        if (f >= 0) for (let rank = bounds.offset; rank < bounds.end; rank++) {
          records.push({ rank, orientation_code: data.inverse.orientation_codes[data.inverse.offsets[f] + rank],
            signature: word, fiber_index: f });
        }
        work.returned_records += records.length;
        return { found: f >= 0, signature: word, fiber_index: f < 0 ? null : f,
          ...pageResult(bounds, records), complete_orientation_space: true };
      });
    },
    selectFiber(args) {
      return query("selectFiber", args, (input, work) => {
        const word = signature(input.signature), f = fiberIndex(word, work);
        const rank = integer(input.rank, 0, Number.MAX_SAFE_INTEGER, "rank");
        work.returned_records++;
        const size = f < 0 ? 0 : data.inverse.offsets[f + 1] - data.inverse.offsets[f];
        if (rank >= size)
          return { found: false, signature: word, rank, orientation_count: size,
            orientation_code: null, fiber_index: f < 0 ? null : f,
            reason: f < 0 ? "signature_not_realizable" : "rank_outside_fiber" };
        return { found: true, signature: word, rank, orientation_count: size, fiber_index: f,
          orientation_code: data.inverse.orientation_codes[data.inverse.offsets[f] + rank] };
      });
    },
    rankFiber(args) {
      return query("rankFiber", args, (input, work) => {
        const word = signature(input.signature), code = orientation(input.orientation_code);
        const observed = data.forward.cyclic_words[code]; work.orientation_word_reads++;
        const f = fiberIndex(word, work); work.returned_records++;
        if (f < 0 || observed !== word)
          return { belongs: false, signature: word, orientation_code: code, observed_signature: observed,
            fiber_index: f < 0 ? null : f, rank: null, reason: "different_or_absent_signature" };
        const rank = fiberRank(f, code, work);
        if (rank < 0) fail("INTERNAL_INVARIANT", "saved forward code absent from inverse fiber");
        return { belongs: true, signature: word, orientation_code: code, fiber_index: f, rank,
          orientation_count: data.inverse.offsets[f + 1] - data.inverse.offsets[f] };
      });
    },
    reverseOrientation(args) {
      return query("reverseOrientation", args, (input, work) => {
        const code = orientation(input.orientation_code), reversed = N - 1 - code;
        work.reversal_complements++;
        const word = data.forward.cyclic_words[code], reversedWord = data.forward.cyclic_words[reversed];
        work.orientation_word_reads += 2;
        if (word !== reversedWord) fail("INTERNAL_INVARIANT", "retained reversal signature mismatch");
        const f = fiberIndex(word, work), rank = fiberRank(f, code, work);
        if (rank < 0) fail("INTERNAL_INVARIANT", "orientation rank missing");
        const size = data.inverse.offsets[f + 1] - data.inverse.offsets[f];
        work.returned_records++;
        return { orientation_code: code, reversed_orientation_code: reversed,
          signature: word, reversed_signature: reversedWord, fiber_index: f, orientation_count: size,
          rank, reversed_rank: size - 1 - rank, reversal_is_distinct: code !== reversed,
          ordering_scope: "rank reversal within this one increasing-code fiber" };
      });
    },
    transitiveSubsets(args) {
      return query("transitiveSubsets", args, (input, work) => {
        const word = signature(input.signature), f = fiberIndex(word, work);
        work.returned_records++;
        if (f < 0) return { signature: word, realizable: false, fiber_index: null,
          records: [], reason: "transitive-tournament interpretation requires a realizable signature" };
        const records = [], counts = Array(n + 1).fill(0);
        let maximumSize = -1, maximumMasks = [];
        for (const subset of data.topology.subsets) {
          work.subset_mask_checks++;
          const transitive = (word & subset.triple_mask) === 0;
          records.push([subset.mask, subset.size, transitive]);
          if (transitive) {
            counts[subset.size]++;
            if (subset.size > maximumSize) { maximumSize = subset.size; maximumMasks = []; }
            if (subset.size === maximumSize) maximumMasks.push(subset.mask);
          }
        }
        return { signature: word, realizable: true, fiber_index: f,
          record_columns: ["vertex_mask", "vertex_count", "transitive"],
          records, transitive_counts_by_size: counts,
          maximum_transitive_size: maximumSize, maximum_vertex_masks: maximumMasks,
          applies_to_every_orientation_in_fiber: true,
          mathematical_basis: "no retained cyclic triple wholly inside the vertex subset" };
      });
    },
    transitiveOrder(args) {
      return query("transitiveOrder", args, (input, work) => {
        const code = orientation(input.orientation_code);
        const mask = integer(input.vertex_mask, 0, 2 ** n - 1, "vertex_mask");
        const subset = data.topology.subsets[mask], word = data.forward.cyclic_words[code];
        work.orientation_word_reads++; work.subset_mask_checks++; work.returned_records++;
        const obstruction = word & subset.triple_mask;
        if (obstruction !== 0)
          return { transitive: false, orientation_code: code, vertex_mask: mask,
            signature: word, cyclic_subword: obstruction, order: null,
            reason: "subset_contains_a_retained_cyclic_triple" };
        const scores = Array(n).fill(0);
        for (const edge of data.topology.edges) {
          if ((mask & (1 << edge.lower_vertex)) === 0 || (mask & (1 << edge.upper_vertex)) === 0) continue;
          const forward = ((code >>> edge.id) & 1) === 1; work.orientation_edge_bit_reads++;
          scores[forward ? edge.lower_vertex : edge.upper_vertex]++; work.order_score_increments++;
        }
        const order = subset.vertices.slice().sort((a, b) => {
          work.order_sort_comparisons++; return scores[b] - scores[a] || a - b;
        });
        for (let i = 0; i < order.length; i++) {
          work.order_score_shape_checks++;
          if (scores[order[i]] !== order.length - 1 - i)
            fail("INTERNAL_INVARIANT", "transitive subset scores do not form a strict total order");
        }
        return { transitive: true, orientation_code: code, vertex_mask: mask,
          signature: word, order, within_subset_outdegrees: order.map(vertex => ({ vertex, outdegree: scores[vertex] })),
          all_edges_point_forward_in_order: true, unique_order: true,
          cyclic_word_basis: "retained constructor output; newly decoded subset orientation scores" };
      });
    },
    createPatternView(args) {
      return query("createPatternView", args, (input, work, queryId) => {
        function required(value, name) {
          if (!Array.isArray(value) || value.length > data.topology.triple_count)
            fail("INVALID_INPUT", name + " must be a bounded triple-id array");
          const seen = new Set(); let mask = 0;
          for (const tid of value) {
            integer(tid, 0, data.topology.triple_count - 1, name + " triple id");
            if (seen.has(tid)) fail("INVALID_INPUT", name + " repeats a triple id");
            seen.add(tid); mask |= 1 << tid; work.constraint_bits_set++;
          }
          return mask;
        }
        const cyclic = required(input.required_cyclic, "required_cyclic");
        const transitive = required(input.required_transitive, "required_transitive");
        const overlap = cyclic & transitive; work.constraint_overlap_checks++;
        const fibers = [], prefixes = [0];
        if (overlap === 0) for (let f = 0; f < data.inverse.signatures.length; f++) {
          const word = data.inverse.signatures[f]; work.pattern_fibers_scanned++;
          work.signature_mask_checks++;
          if ((word & cyclic) !== cyclic) continue;
          work.signature_mask_checks++;
          if ((word & transitive) !== 0) continue;
          fibers.push(f); work.fiber_records_read++;
          prefixes.push(prefixes[prefixes.length - 1] +
            data.inverse.offsets[f + 1] - data.inverse.offsets[f]); work.prefix_count_additions++;
        }
        work.returned_records++;
        return { kind: "signature_pattern", source_id: data.source_id,
          reference: { session_id: sessionIndex, query_id: queryId },
          required_cyclic_mask: cyclic, required_transitive_mask: transitive,
          contradictory_triple_mask: overlap, consistent_requirements: overlap === 0,
          fiber_indices: fibers, orientation_prefixes: prefixes,
          signature_count: fibers.length, orientation_count: prefixes[prefixes.length - 1],
          order: "increasing signature then increasing orientation code within each signature",
          complete_orientation_space: true,
          family_scope: "labeled tournament orientations satisfying these partial triple colors" };
      });
    },
    selectPatternOrientation(args) {
      return query("selectPatternOrientation", args, (input, work) => {
        const view = patternReference(input), rank = integer(input.rank, 0, Number.MAX_SAFE_INTEGER, "rank");
        work.returned_records++;
        return { view: copy(view.reference), ...selectPattern(view, rank, work) };
      });
    },
    rankPatternOrientation(args) {
      return query("rankPatternOrientation", args, (input, work) => {
        const view = patternReference(input), code = orientation(input.orientation_code);
        const word = data.forward.cyclic_words[code]; work.orientation_word_reads++;
        const f = fiberIndex(word, work), position = lowerBound(view.fiber_indices, f, work);
        work.returned_records++;
        if (position >= view.fiber_indices.length || view.fiber_indices[position] !== f)
          return { view: copy(view.reference), belongs: false, orientation_code: code,
            signature: word, rank: null, reason: "signature_outside_pattern_view" };
        const within = fiberRank(f, code, work);
        if (within < 0) fail("INTERNAL_INVARIANT", "pattern member missing from inverse fiber");
        return { view: copy(view.reference), belongs: true, orientation_code: code, signature: word,
          fiber_index: f, view_fiber_position: position, within_fiber_rank: within,
          rank: view.orientation_prefixes[position] + within };
      });
    },
    pagePatternOrientations(args) {
      return query("pagePatternOrientations", args, (input, work) => {
        const view = patternReference(input), bounds = pageBounds(input, view.orientation_count), records = [];
        for (let rank = bounds.offset; rank < bounds.end; rank++) records.push(selectPattern(view, rank, work));
        work.returned_records += records.length;
        return { view: copy(view.reference), ...pageResult(bounds, records) };
      });
    },
    summary() {
      return copy({ schema: SCHEMA, source_id: data.source_id, vertices: n,
        edge_count: data.topology.edge_count, triple_count: data.topology.triple_count,
        result: data.result, construction_work: data.construction_work,
        session: { id: sessionIndex, source_id: id, validation: session.validation,
          query_count: session.queries.length, query_work: session.query_work },
        export_budget: { ...occupied, accounting: "exact JSON-value visits and string/key characters; scalar Number replacements preserve these counts" },
        query_copy_scope: "arguments, result and new receipt; fixed index is not copied per query" });
    },
    snapshot() { return copy(data); }
  };
  return Object.freeze(api);
}
module.exports = Object.freeze({ SCHEMA, LIMITS, compileTournamentFibers, openTournamentFibers });
