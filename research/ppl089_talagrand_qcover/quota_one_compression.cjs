"use strict";

// Exact recognition and witnesses; see QUOTA_ONE_COMPRESSION_API.md.
const QUOTA_ONE_LIMITS = Object.freeze({
  max_universe_size: 256,
  max_blocks: 4096,
  max_raw_memberships: 65536,
  max_active_pair_visits: 262144,
  max_raw_selection_entries: 1024,
  max_cover_classes: 256
});

function createQuotaOneIndex(options) {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const size = options.universe_size;
  if (!Number.isSafeInteger(size) || size < 0 ||
      size > QUOTA_ONE_LIMITS.max_universe_size) {
    throw new RangeError("universe_size must be an integer from 0 through 256");
  }
  if (!Array.isArray(options.blocks) ||
      options.blocks.length > QUOTA_ONE_LIMITS.max_blocks) {
    throw new RangeError("blocks must be an array of at most 4096 quotas");
  }
  function coordinate(value, label) {
    if (!Number.isSafeInteger(value) || value < 0 || value >= size) {
      throw new RangeError(label + " must be a coordinate in the declared universe");
    }
    return value === 0 ? 0 : value;
  }
  const copy = value => JSON.parse(JSON.stringify(value));
  const work = {
    raw_memberships_read: 0,
    normalized_memberships: 0,
    duplicate_memberships_removed: 0,
    active_pair_visits: 0,
    unique_conflict_edges: 0,
    component_neighbor_visits: 0,
    shortest_path_searches: 0,
    shortest_path_neighbor_visits: 0,
    subsets_enumerated: 0,
    general_colorings_searched: 0
  };
  const originalFrequency = Array(size).fill(0);
  const activeFrequency = Array(size).fill(0);
  const zeroSources = Array.from({ length: size }, () => []);
  const blocks = options.blocks.map((block, sourceIndex) => {
    if (!block || typeof block !== "object" || Array.isArray(block) ||
        (block.capacity !== 0 && block.capacity !== 1) ||
        !Array.isArray(block.members)) {
      throw new TypeError("each block needs capacity 0 or 1 and a members array");
    }
    work.raw_memberships_read += block.members.length;
    if (work.raw_memberships_read > QUOTA_ONE_LIMITS.max_raw_memberships) {
      throw new RangeError("too many raw block memberships");
    }
    const members = [...new Set(block.members.map(value =>
      coordinate(value, "block member")))].sort((a, b) => a - b);
    work.normalized_memberships += members.length;
    work.duplicate_memberships_removed += block.members.length - members.length;
    for (const member of members) {
      originalFrequency[member]++;
      if (block.capacity === 0) zeroSources[member].push(sourceIndex);
    }
    return {
      source_block_index: sourceIndex,
      capacity: block.capacity,
      raw_member_count: block.members.length,
      members,
      active_members: []
    };
  });
  const forcedZero = [];
  for (let value = 0; value < size; value++) {
    if (zeroSources[value].length) {
      forcedZero.push({
        coordinate: value,
        source_block_indices: zeroSources[value].slice()
      });
    }
  }
  let plannedPairVisits = 0;
  for (const block of blocks) {
    if (block.capacity === 0) continue;
    block.active_members = block.members.filter(value => zeroSources[value].length === 0);
    for (const value of block.active_members) activeFrequency[value]++;
    const count = block.active_members.length;
    plannedPairVisits += count * (count - 1) / 2;
    if (plannedPairVisits > QUOTA_ONE_LIMITS.max_active_pair_visits) {
      throw new RangeError("active source pairs exceed the retained-witness limit");
    }
  }

  const key = (a, b) => a < b ? a * size + b : b * size + a;
  const edgeMap = new Map();
  for (const block of blocks) {
    const members = block.active_members;
    for (let i = 0; i < members.length; i++) {
      for (let j = i + 1; j < members.length; j++) {
        work.active_pair_visits++;
        const a = members[i], b = members[j], pair = key(a, b);
        if (!edgeMap.has(pair)) {
          edgeMap.set(pair, { endpoints: [a, b], source_block_indices: [] });
        }
        edgeMap.get(pair).source_block_indices.push(block.source_block_index);
      }
    }
  }
  const edges = [...edgeMap.values()].sort((a, b) =>
    a.endpoints[0] - b.endpoints[0] || a.endpoints[1] - b.endpoints[1]);
  const neighbors = Array.from({ length: size }, () => []);
  const adjacent = Array.from({ length: size }, () => new Set());
  edges.forEach((edge, edgeId) => {
    edge.edge_id = edgeId;
    const [a, b] = edge.endpoints;
    neighbors[a].push(b);
    neighbors[b].push(a);
    adjacent[a].add(b);
    adjacent[b].add(a);
  });
  for (const list of neighbors) list.sort((a, b) => a - b);
  work.unique_conflict_edges = edges.length;

  const componentOf = Array(size).fill(-1);
  const components = [];
  for (let start = 0; start < size; start++) {
    if (zeroSources[start].length || componentOf[start] !== -1) continue;
    const componentId = components.length;
    const queue = [start];
    componentOf[start] = componentId;
    for (let head = 0; head < queue.length; head++) {
      for (const next of neighbors[queue[head]]) {
        work.component_neighbor_visits++;
        if (componentOf[next] === -1) {
          componentOf[next] = componentId;
          queue.push(next);
        }
      }
    }
    queue.sort((a, b) => a - b);
    const edgeCount = queue.reduce((sum, value) => sum + neighbors[value].length, 0) / 2;
    components.push({
      component_id: componentId,
      members: queue,
      edge_count: edgeCount,
      complete_graph_edge_count: queue.length * (queue.length - 1) / 2,
      is_clique: edgeCount === queue.length * (queue.length - 1) / 2
    });
  }
  const badComponent = components.find(component => !component.is_clique);
  let obstruction = null;
  if (badComponent) {
    const members = badComponent.members;
    let source = -1, target = -1;
    for (let i = 0; i < members.length && source === -1; i++) {
      for (let j = i + 1; j < members.length; j++) {
        if (!adjacent[members[i]].has(members[j])) {
          source = members[i];
          target = members[j];
          break;
        }
      }
    }
    work.shortest_path_searches++;
    const parent = Array(size).fill(-1), queue = [source];
    parent[source] = source;
    for (let head = 0; head < queue.length && parent[target] === -1; head++) {
      const current = queue[head];
      for (const next of neighbors[current]) {
        work.shortest_path_neighbor_visits++;
        if (parent[next] === -1) {
          parent[next] = current;
          queue.push(next);
        }
      }
    }
    if (parent[target] === -1) throw new Error("component path invariant failed");
    const path = [target];
    while (path[path.length - 1] !== source) path.push(parent[path[path.length - 1]]);
    path.reverse();
    const [a, b, c] = path;
    if (path.length < 3 || adjacent[a].has(c)) {
      throw new Error("shortest-path induced-P3 invariant failed");
    }
    obstruction = {
      kind: "INDUCED_THREE_VERTEX_PATH",
      component_id: badComponent.component_id,
      ordered_vertices: [a, b, c],
      forbidden_pairs: [copy(edgeMap.get(key(a, b))), copy(edgeMap.get(key(b, c)))],
      compatible_endpoints: [a, c],
      endpoints_avoid_forced_zero: true,
      conclusion: "no equivalent disjoint zero/one quota representation on this universe"
    };
  }
  const status = obstruction === null ? "EXACT_DISJOINT_QUOTAS" : "NOT_A_PARTITION_QUOTA_SYSTEM";
  const freeCoordinates = components.filter(component => component.members.length === 1)
    .map(component => component.members[0]);
  const compressed = obstruction === null ? [] : null;
  if (compressed) {
    if (forcedZero.length) {
      compressed.push({
        quota_index: compressed.length,
        capacity: 0,
        members: forcedZero.map(row => row.coordinate),
        component_id: null,
        is_vacuous: false
      });
    }
    for (const component of components) {
      compressed.push({
        quota_index: compressed.length,
        capacity: 1,
        members: component.members.slice(),
        component_id: component.component_id,
        is_vacuous: component.members.length === 1
      });
    }
  }
  const maximum = values => values.reduce((best, value) => Math.max(best, value), 0);
  const statistics = {
    universe_size: size,
    input_block_count: blocks.length,
    zero_quota_count: blocks.filter(block => block.capacity === 0).length,
    positive_quota_count: blocks.filter(block => block.capacity === 1).length,
    forced_zero_count: forcedZero.length,
    free_coordinate_count: freeCoordinates.length,
    active_coordinate_count: size - forcedZero.length,
    conflict_edge_count: edges.length,
    component_count: components.length,
    maximum_component_size: maximum(components.map(component => component.members.length)),
    maximum_conflict_degree: maximum(neighbors.map(list => list.length)),
    maximum_original_coordinate_frequency: maximum(originalFrequency),
    maximum_active_coordinate_frequency: maximum(activeFrequency),
    compressed_block_count: compressed === null ? null : compressed.length,
    nonvacuous_compressed_block_count: compressed === null ? null :
      compressed.filter(block => !block.is_vacuous).length,
    maximum_compressed_coordinate_frequency: compressed === null ? null : (size === 0 ? 0 : 1)
  };
  const snapshot = {
    schema: "talagrand.quota_one_compression/v1",
    status,
    universe_size: size,
    normalized_blocks: blocks,
    forced_zero: forcedZero,
    free_coordinates: freeCoordinates,
    original_coordinate_frequency: originalFrequency,
    active_coordinate_frequency: activeFrequency,
    components,
    coordinate_component_ids: componentOf,
    edge_witnesses: edges,
    compressed_quotas: compressed,
    compression_obstruction: obstruction,
    statistics,
    limits: { ...QUOTA_ONE_LIMITS },
    work: { ...work }
  };

  function decompose(options) {
    if (!options || typeof options !== "object" || Array.isArray(options)) {
      throw new TypeError("cover options must be an object");
    }
    const q = options.q;
    if (!Number.isSafeInteger(q) || q < 1 || q > QUOTA_ONE_LIMITS.max_cover_classes) {
      throw new RangeError("q must be an integer from 1 through 256");
    }
    if (!Array.isArray(options.selected) ||
        options.selected.length > QUOTA_ONE_LIMITS.max_raw_selection_entries) {
      throw new RangeError("selected must be an array of at most 1024 coordinates");
    }
    const selected = [...new Set(options.selected.map(value =>
      coordinate(value, "selected coordinate")))].sort((a, b) => a - b);
    if (obstruction !== null) {
      const error = new Error("q-cover decomposition requires exact partition compression");
      error.name = "NonPartitionQuotaError";
      error.compression_obstruction = copy(obstruction);
      throw error;
    }
    const base = {
      schema: "talagrand.quota_one_cover/v1",
      q,
      selected,
      raw_selection_entries: options.selected.length,
      duplicate_selection_entries_removed: options.selected.length - selected.length
    };
    const zero = selected.find(value => zeroSources[value].length > 0);
    if (zero !== undefined) {
      return {
        ...base,
        status: "NOT_COVERABLE",
        partition: null,
        obstruction: {
          kind: "FORCED_ZERO_SINGLETON",
          members: [zero],
          source_block_indices: zeroSources[zero].slice()
        }
      };
    }
    const chosen = new Set(selected);
    const selectedByComponent = components.map(component =>
      component.members.filter(value => chosen.has(value)));
    for (let index = 0; index < components.length; index++) {
      if (selectedByComponent[index].length <= q) continue;
      const members = selectedByComponent[index].slice(0, q + 1), pairEdgeIds = [];
      for (let i = 0; i < members.length; i++) {
        for (let j = i + 1; j < members.length; j++) {
          pairEdgeIds.push(edgeMap.get(key(members[i], members[j])).edge_id);
        }
      }
      return {
        ...base,
        status: "NOT_COVERABLE",
        partition: null,
        obstruction: {
          kind: "COMPONENT_LOAD_EXCEEDS_Q",
          component_id: components[index].component_id,
          component_load: selectedByComponent[index].length,
          members,
          pair_edge_ids: pairEdgeIds
        }
      };
    }
    const partition = Array.from({ length: q }, (_, color) => ({ color, members: [] }));
    for (const members of selectedByComponent) {
      members.forEach((value, color) => partition[color].members.push(value));
    }
    for (const part of partition) part.members.sort((a, b) => a - b);
    return {
      ...base,
      status: "COVERABLE",
      partition,
      obstruction: null,
      minimum_nonempty_classes: maximum(selectedByComponent.map(members => members.length)),
      empty_classes_allowed: true,
      union_is_exact_selected_set: true,
      classes_are_disjoint: true
    };
  }

  return Object.freeze({
    describe() {
      return copy({
        schema: snapshot.schema,
        status,
        statistics,
        compression_obstruction: obstruction,
        limits: snapshot.limits,
        work: snapshot.work
      });
    },
    snapshot() { return copy(snapshot); },
    decompose
  });
}

module.exports = { createQuotaOneIndex, QUOTA_ONE_LIMITS };
