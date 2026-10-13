"use strict";

// Exact finite edge-cover search for coordinate squares of Q_d.
// Source conventions: Rahil Baber, arXiv:1201.3587, Introduction.
// This module proves no asymptotic statement and enumerates no isomorphism classes.

const SCHEMA = "commons.cube_square_cover/v1";
const LIMITS = Object.freeze({
  max_dimension: 6, max_processed_nodes: 2048, max_generated_nodes: 8193,
  max_nodes_per_advance: 256, max_sessions: 32, max_events_per_session: 256,
  max_page: 64, max_node_page: 8, max_source_id_chars: 512,
  max_copy_items: 4000000, max_copy_chars: 32000000, max_copy_depth: 48
});
function fail(code, message) {
  const error = new Error(message); error.code = code; throw error;
}
function object(value, name) {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    fail("INVALID_INPUT", name + " must be an object");
  return value;
}
function integer(value, low, high, name) {
  if (!Number.isSafeInteger(value) || value < low || value > high)
    fail("INVALID_INPUT", name + " must be a safe integer in [" + low + "," + high + "]");
  return value;
}
function textId(value, name) {
  if (typeof value !== "string" || value.length < 1 || value.length > LIMITS.max_source_id_chars)
    fail("INVALID_INPUT", name + " must be a nonempty bounded string");
  return value;
}
function copy(input) {
  let items = 0, chars = 0;
  function walk(value, depth) {
    if (++items > LIMITS.max_copy_items || depth > LIMITS.max_copy_depth)
      fail("COPY_LIMIT", "record copy item/depth bound exceeded");
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) fail("INVALID_RECORD", "nonfinite number");
      return value;
    }
    if (typeof value === "string") {
      chars += value.length;
      if (chars > LIMITS.max_copy_chars) fail("COPY_LIMIT", "record copy character bound exceeded");
      return value;
    }
    if (Array.isArray(value)) return value.map(x => walk(x, depth + 1));
    if (typeof value !== "object") fail("INVALID_RECORD", "only JSON values may be copied");
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) fail("INVALID_RECORD", "nonplain object");
    const out = {};
    for (const key of Object.keys(value)) {
      chars += key.length;
      if (chars > LIMITS.max_copy_chars) fail("COPY_LIMIT", "record copy character bound exceeded");
      Object.defineProperty(out, key, {
        value: walk(value[key], depth + 1), enumerable: true, writable: true, configurable: true
      });
    }
    return out;
  }
  return walk(input, 0);
}
function hx(mask) { return "0x" + mask.toString(16); }
function bit(id) { return 1n << BigInt(id); }
function fullMask(length) { return (1n << BigInt(length)) - 1n; }
function parseMask(value, length, name) {
  if (typeof value !== "string" || !/^0x(?:0|[1-9a-f][0-9a-f]*)$/.test(value))
    fail("INVALID_RECORD", name + " is not a canonical hexadecimal mask");
  const mask = BigInt(value);
  if (mask > fullMask(length)) fail("INVALID_RECORD", name + " has out-of-universe bits");
  return mask;
}
function idMask(ids) {
  let result = 0n; for (const id of ids) result |= bit(id); return result;
}
function idList(mask, length) {
  const out = [];
  for (let id = 0; id < length; id++) if ((mask & bit(id)) !== 0n) out.push(id);
  return out;
}
function popcount(mask, work, key) {
  let count = 0;
  while (mask !== 0n) { mask &= mask - 1n; count++; if (work) work[key]++; }
  return count;
}
function sortedIds(value, length, name, counts) {
  if (!Array.isArray(value)) fail("INVALID_RECORD", name + " must be an array");
  let prior = -1;
  for (const id of value) {
    integer(id, 0, length - 1, name + " id");
    if (id <= prior) fail("INVALID_RECORD", name + " must be strictly increasing");
    prior = id; if (counts) counts.id_references_checked++;
  }
  return value;
}
function arbitraryIds(value, length, name, counts) {
  if (!Array.isArray(value)) fail("INVALID_RECORD", name + " must be an array");
  const seen = new Set();
  for (const id of value) {
    integer(id, 0, length - 1, name + " id");
    if (seen.has(id)) fail("INVALID_RECORD", name + " repeats an id");
    seen.add(id); if (counts) counts.id_references_checked++;
  }
  return value;
}
function workRecord() {
  return {
    greedy_steps: 0, gain_entries_evaluated: 0, gain_popcount_steps: 0,
    uncovered_popcount_steps: 0, square_availability_rows: 0, square_edge_checks: 0,
    packing_candidates: 0, packing_rows: 0, capacity_divisions: 0,
    processed_nodes: 0, generated_nodes: 0, branches: 0,
    infeasible_nodes: 0, bound_prunes: 0, covered_leaves: 0, global_closed_nodes: 0,
    incumbent_candidates: 0, incumbent_improvements: 0,
    cover_square_checks: 0, cover_edge_checks: 0
  };
}
function queryWork() {
  return { calls: 0, binary_steps: 0, returned_records: 0, edge_membership_checks: 0,
    search_nodes_processed: 0, topology_rows_constructed: 0, cover_proofs_replayed: 0 };
}
function addWork(total, delta) {
  for (const key of Object.keys(delta)) total[key] += delta[key];
}
function compileCubeSquareCover(request) {
  object(request, "request");
  const dimension = integer(request.dimension, 1, LIMITS.max_dimension, "dimension");
  const sourceId = textId(request.source_id, "source_id");
  const V = 2 ** dimension, E = dimension * 2 ** (dimension - 1);
  const S = dimension === 1 ? 0 : dimension * (dimension - 1) / 2 * 2 ** (dimension - 2);
  const compileWork = {
    vertices_materialized: 0, vertex_weight_bit_steps: 0,
    edges_materialized: 0, squares_materialized: 0, edge_square_memberships: 0,
    baseline_edge_parity_checks: 0, baseline_square_checks: 0, baseline_edge_hit_checks: 0,
    global_capacity_divisions: 0
  };
  const vertices = [];
  for (let v = 0; v < V; v++) {
    const bits = [];
    let weight = 0;
    for (let i = 0; i < dimension; i++) {
      const digit = Math.floor(v / 2 ** i) % 2;
      bits.push(digit); weight += digit; compileWork.vertex_weight_bit_steps++;
    }
    vertices.push({ id: v, bits_little_endian: bits, weight, incident_edge_ids: [] });
    compileWork.vertices_materialized++;
  }
  const edges = [], lookup = Array.from({ length: dimension }, () => new Map());
  for (let direction = 0; direction < dimension; direction++) {
    for (let base = 0; base < V; base++) {
      if (vertices[base].bits_little_endian[direction] !== 0) continue;
      const id = edges.length, tip = base + 2 ** direction;
      edges.push({ id, direction, base, tip, lower_weight: vertices[base].weight,
        square_ids: [], square_mask: "0x0" });
      lookup[direction].set(base, id);
      vertices[base].incident_edge_ids.push(id); vertices[tip].incident_edge_ids.push(id);
      compileWork.edges_materialized++;
    }
  }
  const squares = [], edgeSquareMasks = Array.from({ length: E }, () => 0n);
  for (let i = 0; i < dimension; i++) for (let j = i + 1; j < dimension; j++) {
    for (let base = 0; base < V; base++) {
      if (vertices[base].bits_little_endian[i] || vertices[base].bits_little_endian[j]) continue;
      const a = base + 2 ** i, b = base + 2 ** j, c = a + 2 ** j;
      const edgeIds = [lookup[i].get(base), lookup[j].get(a), lookup[i].get(b), lookup[j].get(base)];
      const id = squares.length;
      squares.push({ id, directions: [i, j], base, cycle_vertices: [base, a, c, b],
        edge_ids: edgeIds, edge_mask: hx(idMask(edgeIds)) });
      for (const eid of edgeIds) {
        edges[eid].square_ids.push(id); edgeSquareMasks[eid] |= bit(id);
        compileWork.edge_square_memberships++;
      }
      compileWork.squares_materialized++;
    }
  }
  if (edges.length !== E || squares.length !== S) fail("INTERNAL_INVARIANT", "cube universe count mismatch");
  for (const edge of edges) {
    edge.square_mask = hx(edgeSquareMasks[edge.id]);
    if (edge.square_ids.length !== dimension - 1)
      fail("INTERNAL_INVARIANT", "edge incidence capacity mismatch");
  }
  const deleted = [], kept = [];
  for (const edge of edges) {
    compileWork.baseline_edge_parity_checks++;
    (edge.lower_weight % 2 === 1 ? deleted : kept).push(edge.id);
  }
  const deletionMask = idMask(deleted);
  const hits = squares.map(square => {
    compileWork.baseline_square_checks++;
    const hit = square.edge_ids.filter(eid => {
      compileWork.baseline_edge_hit_checks++; return (deletionMask & bit(eid)) !== 0n;
    }).sort((a, b) => a - b);
    if (!hit.length) fail("INTERNAL_INVARIANT", "alternating-layer baseline misses a square");
    return { square_id: square.id, deleted_edge_ids: hit };
  });
  const lower = dimension === 1 ? 0 : Math.ceil(S / (dimension - 1));
  if (dimension !== 1) compileWork.global_capacity_divisions++;
  const root = { id: 0, parent: null, depth: 0, selected_edge_ids: [], forbidden_edge_ids: [],
    selected_mask: "0x0", forbidden_mask: "0x0", covered_square_mask: "0x0",
    transition: null, status: "pending", analysis: null, children: [], disposition: null };
  const incumbent = { id: 0, origin: { kind: "alternating_layers", deleted_lower_weight_parity: 1 },
    deleted_edge_ids: deleted, kept_edge_ids: kept, deleted_mask: hx(deletionMask),
    deletion_count: deleted.length, kept_count: kept.length, square_hit_witnesses: hits,
    feasible: true };
  const data = {
    schema: SCHEMA, source_id: sourceId,
    request: { source_id: sourceId, dimension },
    conventions: {
      vertices: "nonnegative binary integers; bit zero is least significant",
      edges: "direction first, then increasing lower endpoint with that direction bit zero",
      squares: "coordinate pair i<j first, then increasing base with both bits zero",
      graph: "arbitrary undirected simple edge subset on the entire fixed cube vertex set",
      objective: "minimize deleted edges that hit every coordinate square",
      solution_scope: "one optimum witness only; equal-size alternatives may be pruned",
      semantic_premise: "retained compiler and search records; saved opening is not independent proof verification"
    },
    topology: { dimension, vertex_count: V, edge_count: E, square_count: S,
      vertices, edges, squares, all_edge_mask: hx(fullMask(E)), all_square_mask: hx(fullMask(S)),
      global_capacity_bound: { kind: dimension === 1 ? "no_squares" : "incidence_capacity",
        square_count: S, maximum_squares_per_deleted_edge: dimension - 1,
        deletion_lower_bound: lower, edge_incidence_counts: edges.map(e => e.square_ids.length) } },
    construction_work: compileWork,
    search: { status: "incomplete", completion: null, nodes: [root], frontier: [0],
      processed_nodes: 0, next_node_id: 1, incumbent_id: 0, incumbents: [incumbent],
      greedy: { status: "pending", steps: [], final_deleted_edge_ids: null },
      advances: [], work: workRecord() },
    sessions: []
  };
  return makeEngine(data, sourceId, { kind: "constructor", validation: null });
}

function runtime(topology) {
  return {
    edgeMasks: topology.edges.map(edge => BigInt(edge.square_mask)),
    squareEdgeMasks: topology.squares.map(square => BigInt(square.edge_mask)),
    allEdges: BigInt(topology.all_edge_mask), allSquares: BigInt(topology.all_square_mask)
  };
}
function gains(topology, rt, covered, selected, forbidden, work) {
  const remaining = rt.allSquares & ~covered;
  const rows = Array.from({ length: topology.edge_count }, () => null);
  let maximum = 0;
  for (let id = 0; id < topology.edge_count; id++) {
    if (((selected | forbidden) & bit(id)) !== 0n) continue;
    const gain = popcount(rt.edgeMasks[id] & remaining, work, "gain_popcount_steps");
    rows[id] = gain; work.gain_entries_evaluated++;
    if (gain > maximum) maximum = gain;
  }
  return { rows, maximum };
}
function candidateIncumbent(topology, deletionIds, origin, search, work) {
  work.incumbent_candidates++;
  const ids = deletionIds.slice().sort((a, b) => a - b), mask = idMask(ids);
  const best = search.incumbents[search.incumbent_id];
  if (ids.length >= best.deletion_count) return null;
  const hits = [];
  for (const square of topology.squares) {
    work.cover_square_checks++;
    const hit = [];
    for (const eid of square.edge_ids) {
      work.cover_edge_checks++;
      if ((mask & bit(eid)) !== 0n) hit.push(eid);
    }
    hit.sort((a, b) => a - b);
    if (hit.length === 0) fail("INTERNAL_INVARIANT", "candidate incumbent misses a square");
    hits.push({ square_id: square.id, deleted_edge_ids: hit });
  }
  const kept = [];
  for (let eid = 0; eid < topology.edge_count; eid++) if ((mask & bit(eid)) === 0n) kept.push(eid);
  const id = search.incumbents.length;
  search.incumbents.push({ id, origin, deleted_edge_ids: ids, kept_edge_ids: kept,
    deleted_mask: hx(mask), deletion_count: ids.length, kept_count: kept.length,
    square_hit_witnesses: hits, feasible: true });
  search.incumbent_id = id; work.incumbent_improvements++;
  return id;
}
function runGreedy(topology, rt, search, work) {
  if (search.greedy.status !== "pending") return false;
  let selected = 0n, covered = 0n;
  const steps = [];
  while (covered !== rt.allSquares) {
    const gain = gains(topology, rt, covered, selected, 0n, work);
    if (gain.maximum === 0) fail("INTERNAL_INVARIANT", "full cube has an uncovered un-hittable square");
    let chosen = -1;
    for (let eid = 0; eid < gain.rows.length; eid++)
      if (gain.rows[eid] === gain.maximum) { chosen = eid; break; }
    const before = covered, beforeSelected = selected;
    selected |= bit(chosen); covered |= rt.edgeMasks[chosen];
    steps.push({ id: steps.length, selected_before_mask: hx(beforeSelected),
      covered_before_mask: hx(before), gain_by_edge: gain.rows,
      chosen_edge_id: chosen, chosen_gain: gain.maximum,
      covered_after_mask: hx(covered),
      uncovered_count_after: popcount(rt.allSquares & ~covered, work, "uncovered_popcount_steps") });
    work.greedy_steps++;
  }
  const ids = idList(selected, topology.edge_count);
  search.greedy = { status: "complete", steps, final_deleted_edge_ids: ids };
  candidateIncumbent(topology, ids, { kind: "greedy", steps: steps.length }, search, work);
  return true;
}
function analyzeNode(topology, rt, node, work) {
  const selected = BigInt(node.selected_mask), forbidden = BigInt(node.forbidden_mask);
  const covered = BigInt(node.covered_square_mask), remaining = rt.allSquares & ~covered;
  const uncovered = idList(remaining, topology.square_count);
  const gain = gains(topology, rt, covered, selected, forbidden, work);
  const availability = [];
  let firstEmpty = null;
  for (const sid of uncovered) {
    const square = topology.squares[sid], available = [];
    for (const eid of square.edge_ids) {
      work.square_edge_checks++;
      if ((forbidden & bit(eid)) === 0n) available.push(eid);
    }
    available.sort((a, b) => a - b);
    if (!available.length && firstEmpty === null) firstEmpty = sid;
    availability.push({ square_id: sid, available_edge_ids: available,
      available_edge_mask: hx(idMask(available)) });
    work.square_availability_rows++;
  }
  const ordered = availability.slice().sort((a, b) =>
    a.available_edge_ids.length - b.available_edge_ids.length || a.square_id - b.square_id);
  const packing = [];
  let packingMask = 0n;
  for (const row of ordered) {
    work.packing_candidates++;
    const mask = BigInt(row.available_edge_mask);
    if (mask !== 0n && (mask & packingMask) === 0n) {
      packing.push(copy(row)); packingMask |= mask; work.packing_rows++;
    }
  }
  const impossible = firstEmpty !== null || (uncovered.length > 0 && gain.maximum === 0);
  let capacity = null;
  if (!impossible) {
    capacity = uncovered.length === 0 ? 0 : Math.ceil(uncovered.length / gain.maximum);
    if (uncovered.length > 0) work.capacity_divisions++;
  }
  const branchRow = ordered.length ? ordered[0] : null;
  const branchOrder = impossible || !branchRow ? [] : branchRow.available_edge_ids.slice().sort((a, b) =>
    gain.rows[b] - gain.rows[a] || a - b);
  return {
    uncovered_square_ids: uncovered, gain_by_edge: gain.rows, maximum_available_gain: gain.maximum,
    availability, packing, packing_available_union_mask: hx(packingMask),
    capacity_lower_bound: capacity, packing_lower_bound: packing.length,
    additional_deletion_lower_bound: impossible ? null : Math.max(capacity, packing.length),
    infeasible: impossible, empty_available_square_id: firstEmpty,
    branch_square_id: branchRow === null ? null : branchRow.square_id, branch_order: branchOrder
  };
}
function closeByRootBound(topology, search, work) {
  const incumbent = search.incumbents[search.incumbent_id];
  const bound = topology.global_capacity_bound;
  if (incumbent.deletion_count < bound.deletion_lower_bound)
    fail("INTERNAL_INVARIANT", "feasible cover is below the retained global capacity bound");
  if (incumbent.deletion_count !== bound.deletion_lower_bound) return false;
  const closed = search.frontier.slice();
  for (const id of closed) {
    const node = search.nodes[id];
    if (node.status !== "pending") fail("INTERNAL_INVARIANT", "nonpending frontier node");
    node.status = "global_bound_closed";
    node.disposition = { kind: "root_capacity_attained", incumbent_id: incumbent.id,
      global_deletion_lower_bound: bound.deletion_lower_bound };
    work.global_closed_nodes++;
  }
  search.frontier = [];
  search.status = "optimal";
  search.completion = { kind: "root_capacity_attained", incumbent_id: incumbent.id,
    global_bound: copy(bound), deleted_count: incumbent.deletion_count,
    capacity_product: incumbent.deletion_count * bound.maximum_squares_per_deleted_edge,
    covered_square_count: topology.square_count, closed_node_ids: closed };
  return true;
}
function processSearchNode(topology, rt, search, work) {
  const id = search.frontier.pop(), node = search.nodes[id];
  if (!node || node.status !== "pending") fail("INTERNAL_INVARIANT", "invalid pending node");
  const incumbent = search.incumbents[search.incumbent_id];
  const selected = BigInt(node.selected_mask), forbidden = BigInt(node.forbidden_mask);
  const covered = BigInt(node.covered_square_mask), count = node.selected_edge_ids.length;
  if ((selected & forbidden) !== 0n) fail("INTERNAL_INVARIANT", "selected and forbidden overlap");
  search.processed_nodes++; work.processed_nodes++;
  if (covered === rt.allSquares) {
    node.status = "covered"; work.covered_leaves++;
    const improved = candidateIncumbent(topology, node.selected_edge_ids,
      { kind: "search_node", node_id: id }, search, work);
    node.disposition = { kind: "full_square_cover", entry_incumbent_id: incumbent.id,
      improved_incumbent_id: improved, selected_count: count };
    return;
  }
  if (count >= incumbent.deletion_count) {
    node.status = "pruned"; work.bound_prunes++;
    node.disposition = { kind: "selected_count_bound", incumbent_id: incumbent.id,
      selected_count: count, additional_lower_bound: 0, incumbent_deletion_count: incumbent.deletion_count };
    return;
  }
  const analysis = analyzeNode(topology, rt, node, work);
  node.analysis = analysis;
  if (analysis.infeasible) {
    node.status = "infeasible"; work.infeasible_nodes++;
    node.disposition = { kind: "unhittable_square", empty_available_square_id: analysis.empty_available_square_id,
      maximum_available_gain: analysis.maximum_available_gain };
    return;
  }
  if (count + analysis.additional_deletion_lower_bound >= incumbent.deletion_count) {
    node.status = "pruned"; work.bound_prunes++;
    node.disposition = { kind: "remaining_cover_bound", incumbent_id: incumbent.id, selected_count: count,
      additional_lower_bound: analysis.additional_deletion_lower_bound,
      incumbent_deletion_count: incumbent.deletion_count };
    return;
  }
  const order = analysis.branch_order, children = [], earlier = [];
  let earlierMask = 0n;
  for (let branch = 0; branch < order.length; branch++) {
    const edge = order[branch], nextSelected = selected | bit(edge);
    const nextForbidden = forbidden | earlierMask;
    if (search.next_node_id >= LIMITS.max_generated_nodes)
      fail("INTERNAL_INVARIANT", "generated-node bound exceeded");
    const childId = search.next_node_id++;
    const child = {
      id: childId, parent: id, depth: node.depth + 1,
      selected_edge_ids: idList(nextSelected, topology.edge_count),
      forbidden_edge_ids: idList(nextForbidden, topology.edge_count),
      selected_mask: hx(nextSelected), forbidden_mask: hx(nextForbidden),
      covered_square_mask: hx(covered | rt.edgeMasks[edge]),
      transition: { square_id: analysis.branch_square_id, branch_index: branch,
        selected_edge_id: edge, earlier_available_edge_ids: earlier.slice() },
      status: "pending", analysis: null, children: [], disposition: null
    };
    search.nodes.push(child); children.push(childId); work.generated_nodes++;
    earlier.push(edge); earlierMask |= bit(edge);
  }
  if (children.length === 0) fail("INTERNAL_INVARIANT", "empty feasible branch");
  node.status = "branched"; node.children = children; work.branches++;
  node.disposition = { kind: "first_selected_available_edge_partition",
    square_id: analysis.branch_square_id, frozen_edge_order: order.slice() };
  for (let i = children.length - 1; i >= 0; i--) search.frontier.push(children[i]);
}
function advanceTransaction(data, nodeBudget) {
  const search = copy(data.search), topology = data.topology;
  if (search.advances.length >= LIMITS.max_events_per_session)
    fail("EVENT_LIMIT", "search advance history is full");
  const delta = workRecord(), rt = runtime(topology);
  const frontierBefore = search.frontier.slice(), incumbentBefore = search.incumbent_id;
  const processedBefore = search.processed_nodes, generatedBefore = search.nodes.length;
  let greedyRan = false;
  if (search.status !== "optimal") {
    greedyRan = runGreedy(topology, rt, search, delta);
    closeByRootBound(topology, search, delta);
  }
  while (search.status !== "optimal" && search.frontier.length &&
      delta.processed_nodes < nodeBudget && search.processed_nodes < LIMITS.max_processed_nodes) {
    processSearchNode(topology, rt, search, delta);
    if (closeByRootBound(topology, search, delta)) break;
  }
  if (search.status !== "optimal" && search.frontier.length === 0) {
    search.status = "optimal";
    search.completion = { kind: "frontier_exhausted", incumbent_id: search.incumbent_id,
      processed_nodes: search.processed_nodes, generated_nodes: search.nodes.length };
  }
  const termination = search.status === "optimal" ? "optimal" :
    search.processed_nodes >= LIMITS.max_processed_nodes ? "total_node_limit" : "node_budget";
  addWork(search.work, delta);
  const advance = {
    id: search.advances.length, node_budget: nodeBudget, greedy_ran: greedyRan,
    status: search.status, termination, processed_before: processedBefore,
    processed_after: search.processed_nodes, generated_before: generatedBefore,
    generated_after: search.nodes.length, incumbent_before: incumbentBefore,
    incumbent_after: search.incumbent_id, frontier_before: frontierBefore,
    frontier_after: search.frontier.slice(), saved_topology_masks_decoded: topology.edge_count + topology.square_count + 2,
    work: delta
  };
  search.advances.push(advance);
  const best = search.incumbents[search.incumbent_id];
  const result = { advance_id: advance.id, status: search.status, termination,
    processed_nodes: search.processed_nodes, pending_nodes: search.frontier.length,
    incumbent_id: best.id, deleted_count: best.deletion_count, kept_count: best.kept_count,
    root_deletion_lower_bound: topology.global_capacity_bound.deletion_lower_bound,
    optimum_certified_by_retained_records: search.status === "optimal", work: copy(delta) };
  return { search, result };
}

function validateSnapshot(data) {
  object(data, "snapshot");
  if (data.schema !== SCHEMA) fail("INVALID_RECORD", "unsupported snapshot schema");
  textId(data.source_id, "snapshot source_id");
  const top = object(data.topology, "topology"), d = integer(top.dimension, 1, LIMITS.max_dimension, "dimension");
  const V = 2 ** d, E = d * 2 ** (d - 1), S = d === 1 ? 0 : d * (d - 1) / 2 * 2 ** (d - 2);
  if (top.vertex_count !== V || top.edge_count !== E || top.square_count !== S)
    fail("INVALID_RECORD", "universe size fields disagree");
  object(data.request, "request");
  if (data.request.source_id !== data.source_id || data.request.dimension !== d)
    fail("INVALID_RECORD", "request identity disagrees");
  const checks = { vertices: 0, edges: 0, squares: 0, nodes: 0, incumbents: 0,
    id_references_checked: 0, mask_bindings_checked: 0, parent_links_checked: 0,
    pending_references_checked: 0, universe_size_equalities: 3,
    coverage_unions_recomputed: 0, gain_or_packing_bounds_replayed: 0,
    global_capacity_proof_replayed: 0, search_expansions_replayed: 0,
    mathematical_proof_authenticated: false };
  function length(value, expected, name) {
    if (!Array.isArray(value) || value.length !== expected) fail("INVALID_RECORD", name + " length disagrees");
  }
  function bindMask(value, ids, size, name) {
    const mask = parseMask(value, size, name);
    if (mask !== idMask(ids)) fail("INVALID_RECORD", name + " disagrees with its retained id list");
    checks.mask_bindings_checked++; return mask;
  }
  function checkWork(value, name) {
    object(value, name);
    for (const [key, count] of Object.entries(value))
      integer(count, 0, Number.MAX_SAFE_INTEGER, name + "." + key);
  }
  length(top.vertices, V, "vertices"); length(top.edges, E, "edges"); length(top.squares, S, "squares");
  if (parseMask(top.all_edge_mask, E, "all_edge_mask") !== fullMask(E) ||
      parseMask(top.all_square_mask, S, "all_square_mask") !== fullMask(S))
    fail("INVALID_RECORD", "full universe masks disagree");
  checks.mask_bindings_checked += 2;
  for (let i = 0; i < V; i++) {
    const v = object(top.vertices[i], "vertex");
    if (v.id !== i) fail("INVALID_RECORD", "vertex id order");
    length(v.bits_little_endian, d, "vertex bits");
    v.bits_little_endian.forEach(x => integer(x, 0, 1, "vertex bit"));
    integer(v.weight, 0, d, "vertex weight");
    sortedIds(v.incident_edge_ids, E, "incident edges", checks);
    if (v.incident_edge_ids.length !== d) fail("INVALID_RECORD", "vertex degree record length");
    checks.vertices++;
  }
  for (let i = 0; i < E; i++) {
    const edge = object(top.edges[i], "edge");
    if (edge.id !== i) fail("INVALID_RECORD", "edge id order");
    integer(edge.direction, 0, d - 1, "edge direction");
    integer(edge.base, 0, V - 1, "edge base"); integer(edge.tip, 0, V - 1, "edge tip");
    if (edge.base === edge.tip) fail("INVALID_RECORD", "edge loop");
    integer(edge.lower_weight, 0, d - 1, "edge lower weight");
    sortedIds(edge.square_ids, S, "edge square references", checks);
    if (edge.square_ids.length !== d - 1) fail("INVALID_RECORD", "edge incidence record length");
    bindMask(edge.square_mask, edge.square_ids, S, "edge square mask");
    checks.edges++;
  }
  for (let i = 0; i < S; i++) {
    const square = object(top.squares[i], "square");
    if (square.id !== i) fail("INVALID_RECORD", "square id order");
    length(square.directions, 2, "square directions");
    sortedIds(square.directions, d, "square directions", checks);
    integer(square.base, 0, V - 1, "square base");
    length(square.cycle_vertices, 4, "square vertices");
    arbitraryIds(square.cycle_vertices, V, "square vertices", checks);
    length(square.edge_ids, 4, "square edges");
    arbitraryIds(square.edge_ids, E, "square edges", checks);
    bindMask(square.edge_mask, square.edge_ids, E, "square edge mask");
    checks.squares++;
  }
  const bound = object(top.global_capacity_bound, "global capacity bound");
  integer(bound.square_count, 0, S, "bound square count");
  integer(bound.maximum_squares_per_deleted_edge, 0, d - 1, "bound edge capacity");
  integer(bound.deletion_lower_bound, 0, E, "global deletion lower bound");
  length(bound.edge_incidence_counts, E, "bound incidence counts");
  bound.edge_incidence_counts.forEach(x => integer(x, 0, S, "bound incidence count"));
  checkWork(data.construction_work, "construction work");
  const search = object(data.search, "search");
  if (!["incomplete", "optimal"].includes(search.status)) fail("INVALID_RECORD", "search status");
  if (!Array.isArray(search.nodes) || search.nodes.length < 1 || search.nodes.length > LIMITS.max_generated_nodes)
    fail("INVALID_RECORD", "search node count");
  const N = search.nodes.length;
  if (search.next_node_id !== N) fail("INVALID_RECORD", "next node id");
  integer(search.processed_nodes, 0, LIMITS.max_processed_nodes, "processed nodes");
  if (!Array.isArray(search.incumbents) || !search.incumbents.length || search.incumbents.length > E + 1)
    fail("INVALID_RECORD", "incumbent count");
  for (let i = 0; i < search.incumbents.length; i++) {
    const inc = object(search.incumbents[i], "incumbent");
    if (inc.id !== i || inc.feasible !== true) fail("INVALID_RECORD", "incumbent identity/feasibility field");
    object(inc.origin, "incumbent origin");
    sortedIds(inc.deleted_edge_ids, E, "incumbent deleted edges", checks);
    sortedIds(inc.kept_edge_ids, E, "incumbent kept edges", checks);
    if (inc.deletion_count !== inc.deleted_edge_ids.length || inc.kept_count !== inc.kept_edge_ids.length ||
        inc.deletion_count + inc.kept_count !== E) fail("INVALID_RECORD", "incumbent sizes");
    const deleted = bindMask(inc.deleted_mask, inc.deleted_edge_ids, E, "incumbent deletion mask");
    if ((deleted ^ idMask(inc.kept_edge_ids)) !== fullMask(E) ||
        (deleted & idMask(inc.kept_edge_ids)) !== 0n) fail("INVALID_RECORD", "incumbent edge partition");
    checks.mask_bindings_checked++;
    length(inc.square_hit_witnesses, S, "square hit witnesses");
    for (let sid = 0; sid < S; sid++) {
      const hit = object(inc.square_hit_witnesses[sid], "square hit record");
      if (hit.square_id !== sid) fail("INVALID_RECORD", "square hit id");
      sortedIds(hit.deleted_edge_ids, E, "hit edge references", checks);
      if (!hit.deleted_edge_ids.length || hit.deleted_edge_ids.length > 4)
        fail("INVALID_RECORD", "hit record size");
    }
    checks.incumbents++;
  }
  integer(search.incumbent_id, 0, search.incumbents.length - 1, "incumbent id");
  arbitraryIds(search.frontier, N, "frontier", checks);
  const pending = new Set(search.frontier);
  let processed = 0, pendingCount = 0;
  const statuses = ["pending", "branched", "pruned", "infeasible", "covered", "global_bound_closed"];
  for (let i = 0; i < N; i++) {
    const node = object(search.nodes[i], "node");
    if (node.id !== i || !statuses.includes(node.status)) fail("INVALID_RECORD", "node id/status");
    integer(node.depth, 0, E, "node depth");
    sortedIds(node.selected_edge_ids, E, "selected edges", checks);
    sortedIds(node.forbidden_edge_ids, E, "forbidden edges", checks);
    const selected = bindMask(node.selected_mask, node.selected_edge_ids, E, "selected mask");
    const forbidden = bindMask(node.forbidden_mask, node.forbidden_edge_ids, E, "forbidden mask");
    if ((selected & forbidden) !== 0n) fail("INVALID_RECORD", "selected/forbidden overlap");
    parseMask(node.covered_square_mask, S, "covered square mask"); checks.mask_bindings_checked++;
    if (i === 0) {
      if (node.parent !== null || node.transition !== null || node.depth !== 0)
        fail("INVALID_RECORD", "root identity");
    } else {
      integer(node.parent, 0, i - 1, "parent id");
      const trans = object(node.transition, "transition");
      integer(trans.square_id, 0, S - 1, "transition square");
      integer(trans.branch_index, 0, 3, "branch index");
      integer(trans.selected_edge_id, 0, E - 1, "transition selected edge");
      arbitraryIds(trans.earlier_available_edge_ids, E, "earlier branch edges", checks);
      const parent = search.nodes[node.parent];
      if (!Array.isArray(parent.children) || parent.children[trans.branch_index] !== i)
        fail("INVALID_RECORD", "parent/child reference");
      if (!parent.analysis || parent.analysis.branch_order[trans.branch_index] !== trans.selected_edge_id)
        fail("INVALID_RECORD", "branch order reference");
      if (JSON.stringify(trans.earlier_available_edge_ids) !==
          JSON.stringify(parent.analysis.branch_order.slice(0, trans.branch_index)))
        fail("INVALID_RECORD", "earlier branch references");
      checks.parent_links_checked++;
    }
    arbitraryIds(node.children, N, "children", checks);
    if (node.status === "branched") {
      if (node.children.length < 1 || node.children.length > 4 || node.analysis === null)
        fail("INVALID_RECORD", "branch children missing");
      node.children.forEach(id => {
        if (id <= i || search.nodes[id].parent !== i) fail("INVALID_RECORD", "child reference mismatch");
        checks.parent_links_checked++;
      });
    } else if (node.children.length !== 0) fail("INVALID_RECORD", "nonbranch children");
    if (node.analysis !== null) {
      const a = object(node.analysis, "node analysis");
      sortedIds(a.uncovered_square_ids, S, "uncovered square references", checks);
      length(a.gain_by_edge, E, "edge gain table");
      a.gain_by_edge.forEach(x => { if (x !== null) integer(x, 0, S, "edge gain"); });
      integer(a.maximum_available_gain, 0, S, "maximum gain");
      if (a.capacity_lower_bound !== null) integer(a.capacity_lower_bound, 0, S, "capacity lower bound");
      integer(a.packing_lower_bound, 0, S, "packing lower bound");
      if (a.additional_deletion_lower_bound !== null)
        integer(a.additional_deletion_lower_bound, 0, S, "additional lower bound");
      if (typeof a.infeasible !== "boolean") fail("INVALID_RECORD", "infeasibility field");
      length(a.availability, a.uncovered_square_ids.length, "availability records");
      for (let j = 0; j < a.availability.length; j++) {
        const row = a.availability[j];
        if (row.square_id !== a.uncovered_square_ids[j]) fail("INVALID_RECORD", "availability square reference");
        sortedIds(row.available_edge_ids, E, "available edges", checks);
        bindMask(row.available_edge_mask, row.available_edge_ids, E, "available edge mask");
      }
      if (!Array.isArray(a.packing) || a.packing.length > S) fail("INVALID_RECORD", "packing records");
      for (const row of a.packing) {
        integer(row.square_id, 0, S - 1, "packing square");
        sortedIds(row.available_edge_ids, E, "packing available edges", checks);
        if (!row.available_edge_ids.length) fail("INVALID_RECORD", "empty packing record");
        bindMask(row.available_edge_mask, row.available_edge_ids, E, "packing available mask");
      }
      parseMask(a.packing_available_union_mask, E, "packing union mask"); checks.mask_bindings_checked++;
      if (a.branch_square_id !== null) integer(a.branch_square_id, 0, S - 1, "branch square id");
      arbitraryIds(a.branch_order, E, "branch order", checks);
      if (a.branch_order.length > 4) fail("INVALID_RECORD", "branch order too long");
    }
    if (node.status === "pending") {
      if (!pending.has(i)) fail("INVALID_RECORD", "pending node missing from frontier");
      pendingCount++; checks.pending_references_checked++;
    } else {
      if (pending.has(i)) fail("INVALID_RECORD", "closed node appears in frontier");
      if (node.status !== "global_bound_closed") processed++;
      object(node.disposition, "node disposition");
    }
    checks.nodes++;
  }
  if (pendingCount !== search.frontier.length || processed !== search.processed_nodes)
    fail("INVALID_RECORD", "frontier/processed count disagreement");
  if (search.status === "optimal") {
    const completion = object(search.completion, "completion");
    if (search.frontier.length !== 0 ||
        !["root_capacity_attained", "frontier_exhausted"].includes(completion.kind))
      fail("INVALID_RECORD", "completion/frontier state");
    integer(completion.incumbent_id, 0, search.incumbents.length - 1, "completion incumbent");
    if (completion.kind === "root_capacity_attained")
      arbitraryIds(completion.closed_node_ids, N, "globally closed nodes", checks);
  } else if (search.completion !== null) fail("INVALID_RECORD", "incomplete search has completion");
  const greedy = object(search.greedy, "greedy history");
  if (!["pending", "complete"].includes(greedy.status) || !Array.isArray(greedy.steps) || greedy.steps.length > E)
    fail("INVALID_RECORD", "greedy history bounds");
  for (let i = 0; i < greedy.steps.length; i++) {
    const step = greedy.steps[i];
    if (step.id !== i) fail("INVALID_RECORD", "greedy step id");
    parseMask(step.selected_before_mask, E, "greedy selected mask");
    parseMask(step.covered_before_mask, S, "greedy covered before");
    parseMask(step.covered_after_mask, S, "greedy covered after");
    length(step.gain_by_edge, E, "greedy gain rows");
    step.gain_by_edge.forEach(x => { if (x !== null) integer(x, 0, S, "greedy gain"); });
    integer(step.chosen_edge_id, 0, E - 1, "greedy chosen edge");
    integer(step.chosen_gain, 1, Math.max(1, S), "greedy chosen gain");
    integer(step.uncovered_count_after, 0, S, "greedy remaining count");
    checks.mask_bindings_checked += 3;
  }
  if (greedy.status === "complete") sortedIds(greedy.final_deleted_edge_ids, E, "greedy final edges", checks);
  else if (greedy.final_deleted_edge_ids !== null || greedy.steps.length) fail("INVALID_RECORD", "pending greedy data");
  if (!Array.isArray(search.advances) || search.advances.length > LIMITS.max_events_per_session)
    fail("INVALID_RECORD", "advance history");
  for (let i = 0; i < search.advances.length; i++) {
    const a = search.advances[i];
    if (a.id !== i) fail("INVALID_RECORD", "advance id");
    integer(a.node_budget, 1, LIMITS.max_nodes_per_advance, "advance budget");
    arbitraryIds(a.frontier_before, N, "advance before frontier", checks);
    arbitraryIds(a.frontier_after, N, "advance after frontier", checks);
    checkWork(a.work, "advance work");
  }
  if (search.advances.length) {
    const last = search.advances[search.advances.length - 1];
    if (last.processed_after !== search.processed_nodes || last.incumbent_after !== search.incumbent_id ||
        JSON.stringify(last.frontier_after) !== JSON.stringify(search.frontier))
      fail("INVALID_RECORD", "last advance/current state disagreement");
  }
  checkWork(search.work, "search work");
  if (!Array.isArray(data.sessions) || data.sessions.length >= LIMITS.max_sessions)
    fail("INVALID_RECORD", "session capacity reached");
  const sourceIds = new Set();
  for (let i = 0; i < data.sessions.length; i++) {
    const session = object(data.sessions[i], "session");
    if (session.id !== i) fail("INVALID_RECORD", "session id");
    textId(session.source_id, "session source_id");
    if (sourceIds.has(session.source_id)) fail("INVALID_RECORD", "duplicate session source_id");
    sourceIds.add(session.source_id);
    if (!Array.isArray(session.queries) || !Array.isArray(session.search_advance_ids) ||
        session.queries.length + session.search_advance_ids.length > LIMITS.max_events_per_session)
      fail("INVALID_RECORD", "session event capacity");
    arbitraryIds(session.search_advance_ids, search.advances.length, "session advances", checks);
    session.queries.forEach((q, j) => {
      if (q.id !== j || !["ok", "error"].includes(q.status)) fail("INVALID_RECORD", "query history identity");
      checkWork(q.work, "query work");
    });
    checkWork(session.query_work, "session query work");
  }
  return checks;
}
function openCubeSquareCover(snapshot, options) {
  object(options, "options");
  const sourceId = textId(options.source_id, "reader source_id"), data = copy(snapshot);
  const validation = validateSnapshot(data);
  if (data.sessions.some(s => s.source_id === sourceId)) fail("INVALID_INPUT", "reader source_id already exists");
  return makeEngine(data, sourceId, { kind: "saved_open", validation });
}

function makeEngine(data, sourceId, loading) {
  textId(sourceId, "session source_id");
  if (data.sessions.length >= LIMITS.max_sessions) fail("SESSION_LIMIT", "session capacity reached");
  const session = { id: data.sessions.length, source_id: sourceId, kind: loading.kind,
    validation: loading.validation, query_work: queryWork(), queries: [], search_advance_ids: [] };
  data.sessions.push(session);
  function availableEvent() {
    if (session.queries.length + session.search_advance_ids.length >= LIMITS.max_events_per_session)
      fail("EVENT_LIMIT", "session event history is full");
  }
  function incumbent(args) {
    const id = args.incumbent_id === undefined ? data.search.incumbent_id :
      integer(args.incumbent_id, 0, data.search.incumbents.length - 1, "incumbent_id");
    return data.search.incumbents[id];
  }
  function viewIds(args, inc) {
    if (args.view === "kept") return inc.kept_edge_ids;
    if (args.view === "deleted") return inc.deleted_edge_ids;
    if (args.view === "all") return data.topology.edges.map(edge => edge.id);
    fail("INVALID_INPUT", "view must be all, kept, or deleted");
  }
  function graphEdge(id, inc, work) {
    work.edge_membership_checks++;
    return { ...data.topology.edges[id], incumbent_id: inc.id,
      kept: (BigInt(inc.deleted_mask) & bit(id)) === 0n };
  }
  function pageBounds(args, length, limit) {
    const offset = integer(args.offset, 0, length, "offset");
    const count = integer(args.limit, 1, limit, "limit");
    return { offset, end: Math.min(length, offset + count), total: length };
  }
  function pageResult(bounds, records) {
    return { offset: bounds.offset, total: bounds.total, records,
      next_offset: bounds.end < bounds.total ? bounds.end : null };
  }
  function query(name, args, operation) {
    availableEvent();
    object(args, "query arguments");
    const retainedArgs = copy(args), work = queryWork(); work.calls = 1;
    try {
      const result = copy(operation(args, work));
      const callerResult = copy(result), retainedWork = copy(work);
      session.queries.push({ id: session.queries.length, method: name, args: retainedArgs,
        status: "ok", result, work: retainedWork });
      addWork(session.query_work, work);
      return callerResult;
    } catch (error) {
      session.queries.push({ id: session.queries.length, method: name, args: retainedArgs,
        status: "error", error: { code: error.code || "QUERY_ERROR", message: error.message }, work: copy(work) });
      addWork(session.query_work, work);
      throw error;
    }
  }
  const api = {
    advanceSearch(args) {
      availableEvent(); object(args, "advance arguments");
      const budget = integer(args.node_budget, 1, LIMITS.max_nodes_per_advance, "node_budget");
      const tx = advanceTransaction(data, budget);
      tx.search.advances[tx.search.advances.length - 1].session_id = session.id;
      const result = copy(tx.result);
      data.search = tx.search; session.search_advance_ids.push(result.advance_id);
      return result;
    },
    assess(args = {}) {
      return query("assess", args, (input, work) => {
        const inc = incumbent(input), best = data.search.incumbents[data.search.incumbent_id];
        work.returned_records++;
        return { source_id: data.source_id, dimension: data.topology.dimension,
          edge_count: data.topology.edge_count, square_count: data.topology.square_count,
          selected_incumbent_id: inc.id, selected_kept_count: inc.kept_count,
          selected_deleted_count: inc.deletion_count,
          selected_density: { numerator: inc.kept_count, denominator: data.topology.edge_count },
          search_status: data.search.status, completion: data.search.completion,
          best_incumbent_id: best.id, maximum_kept_lower_bound: best.kept_count,
          maximum_kept_upper_bound: data.search.status === "optimal" ? best.kept_count :
            data.topology.edge_count - data.topology.global_capacity_bound.deletion_lower_bound,
          root_deletion_lower_bound: data.topology.global_capacity_bound.deletion_lower_bound,
          pending_nodes: data.search.frontier.length, retained_feasible_cover: inc.feasible,
          semantic_basis: "retained compiler/search records; this query does not independently reprove them",
          global_or_asymptotic_claim: false };
      });
    },
    getIncumbent(args) {
      return query("getIncumbent", args, (input, work) => {
        work.returned_records++; return incumbent(input);
      });
    },
    getEdge(args) {
      return query("getEdge", args, (input, work) => {
        const id = integer(input.edge_id, 0, data.topology.edge_count - 1, "edge_id");
        work.returned_records++; return graphEdge(id, incumbent(input), work);
      });
    },
    selectEdge(args) {
      return query("selectEdge", args, (input, work) => {
        const inc = incumbent(input), ids = viewIds(input, inc);
        const rank = integer(input.rank, 0, ids.length - 1, "rank");
        work.returned_records++;
        return { view: input.view, rank, total: ids.length, edge: graphEdge(ids[rank], inc, work) };
      });
    },
    rankEdge(args) {
      return query("rankEdge", args, (input, work) => {
        const inc = incumbent(input), ids = viewIds(input, inc);
        const id = integer(input.edge_id, 0, data.topology.edge_count - 1, "edge_id");
        let low = 0, high = ids.length;
        while (low < high) {
          const middle = Math.floor((low + high) / 2); work.binary_steps++;
          if (ids[middle] < id) low = middle + 1; else high = middle;
        }
        work.returned_records++;
        return { incumbent_id: inc.id, view: input.view, edge_id: id, total: ids.length,
          belongs: low < ids.length && ids[low] === id,
          rank: low < ids.length && ids[low] === id ? low : null };
      });
    },
    pageEdges(args) {
      return query("pageEdges", args, (input, work) => {
        const inc = incumbent(input), ids = viewIds(input, inc);
        const bounds = pageBounds(input, ids.length, LIMITS.max_page);
        const records = ids.slice(bounds.offset, bounds.end).map(id => graphEdge(id, inc, work));
        work.returned_records += records.length;
        return { incumbent_id: inc.id, view: input.view, ...pageResult(bounds, records) };
      });
    },
    getSquare(args) {
      return query("getSquare", args, (input, work) => {
        const id = integer(input.square_id, 0, data.topology.square_count - 1, "square_id");
        const inc = incumbent(input), square = data.topology.squares[id];
        work.returned_records++;
        return { incumbent_id: inc.id, square,
          retained_hit_witness: inc.square_hit_witnesses[id],
          edge_assignments: square.edge_ids.map(eid => {
            work.edge_membership_checks++;
            return { edge_id: eid, kept: (BigInt(inc.deleted_mask) & bit(eid)) === 0n };
          }) };
      });
    },
    pageSquareWitnesses(args) {
      return query("pageSquareWitnesses", args, (input, work) => {
        const inc = incumbent(input);
        const bounds = pageBounds(input, data.topology.square_count, LIMITS.max_page);
        const records = [];
        for (let id = bounds.offset; id < bounds.end; id++)
          records.push({ square: data.topology.squares[id], retained_hit_witness: inc.square_hit_witnesses[id] });
        work.returned_records += records.length;
        return { incumbent_id: inc.id, ...pageResult(bounds, records) };
      });
    },
    vertexNeighbours(args) {
      return query("vertexNeighbours", args, (input, work) => {
        const id = integer(input.vertex_id, 0, data.topology.vertex_count - 1, "vertex_id");
        const inc = incumbent(input), vertex = data.topology.vertices[id];
        const rows = vertex.incident_edge_ids.map(eid => {
          const edge = data.topology.edges[eid]; work.edge_membership_checks++;
          return { edge_id: eid, other_vertex: edge.base === id ? edge.tip : edge.base,
            kept: (BigInt(inc.deleted_mask) & bit(eid)) === 0n };
        });
        work.returned_records += rows.length;
        return { incumbent_id: inc.id, vertex, incident_edges: rows,
          kept_neighbour_ids: rows.filter(row => row.kept).map(row => row.other_vertex).sort((a, b) => a - b) };
      });
    },
    getSearchNode(args) {
      return query("getSearchNode", args, (input, work) => {
        const id = integer(input.node_id, 0, data.search.nodes.length - 1, "node_id");
        work.returned_records++; return data.search.nodes[id];
      });
    },
    pageSearchNodes(args) {
      return query("pageSearchNodes", args, (input, work) => {
        const bounds = pageBounds(input, data.search.nodes.length, LIMITS.max_node_page);
        const records = data.search.nodes.slice(bounds.offset, bounds.end);
        work.returned_records += records.length; return pageResult(bounds, records);
      });
    },
    pageFrontier(args) {
      return query("pageFrontier", args, (input, work) => {
        const bounds = pageBounds(input, data.search.frontier.length, LIMITS.max_page);
        const records = data.search.frontier.slice(bounds.offset, bounds.end).map(id => data.search.nodes[id]);
        work.returned_records += records.length;
        return { search_status: data.search.status, ...pageResult(bounds, records) };
      });
    },
    getGreedyStep(args) {
      return query("getGreedyStep", args, (input, work) => {
        const id = integer(input.step_id, 0, data.search.greedy.steps.length - 1, "step_id");
        work.returned_records++; return data.search.greedy.steps[id];
      });
    },
    summary() {
      const best = data.search.incumbents[data.search.incumbent_id];
      return copy({ schema: SCHEMA, source_id: data.source_id, dimension: data.topology.dimension,
        vertex_count: data.topology.vertex_count, edge_count: data.topology.edge_count,
        square_count: data.topology.square_count, status: data.search.status,
        incumbent_id: best.id, deleted_count: best.deletion_count, kept_count: best.kept_count,
        generated_nodes: data.search.nodes.length, processed_nodes: data.search.processed_nodes,
        frontier_count: data.search.frontier.length, advances: data.search.advances.length,
        incumbent_count: data.search.incumbents.length, greedy_steps: data.search.greedy.steps.length,
        construction_work: data.construction_work, search_work: data.search.work,
        session: { id: session.id, source_id: session.source_id, kind: session.kind,
          validation: session.validation, query_calls: session.queries.length,
          search_advances: session.search_advance_ids.length, query_work: session.query_work } });
    },
    snapshot() { return copy(data); }
  };
  return Object.freeze(api);
}
module.exports = Object.freeze({ SCHEMA, LIMITS, compileCubeSquareCover, openCubeSquareCover });
