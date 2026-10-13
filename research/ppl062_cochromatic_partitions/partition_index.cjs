"use strict";
// Exact unordered set partitions of a supplied finite labelled graph.
// No Mycielski constructor, cut solver, graph sampler or complement builder.
const VERSION = "1.0.0";
const SCHEMA = "commons.homogeneous-partition-index.v1";
const MODES = ["independent", "clique", "homogeneous"];
const MAX_VERTICES = 14;
const MAX_JSON = 12000000;
function fail(s) { throw new Error(s); }
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function integer(x, name, lo, hi) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) fail(name + " outside integer bounds");
  return x;
}
function decimal(x, name) {
  if (typeof x === "bigint") x = x.toString();
  if (typeof x === "number") { integer(x, name, 0, Number.MAX_SAFE_INTEGER); x = String(x); }
  if (typeof x !== "string" || !/^(0|[1-9][0-9]*)$/.test(x) || x.length > 100) fail(name + " requires canonical nonnegative decimal, at most 100 digits");
  return BigInt(x);
}
function popcount(x) { let c = 0; for (; x; x &= x - 1) c++; return c; }
function vertices(mask, n) { const out = []; for (let i = 0; i < n; i++) if (mask & (1 << i)) out.push(i); return out; }
function modeIndex(mode) { const i = MODES.indexOf(mode); if (i < 0) fail("unknown partition mode"); return i; }
function admits(code, m) { return m === 0 ? (code & 1) !== 0 : m === 1 ? (code & 2) !== 0 : code !== 0; }
function inputGraph(input) {
  if (!input || typeof input !== "object") fail("graph object required");
  const n = integer(input.vertex_count, "vertex_count", 0, MAX_VERTICES);
  if (!Array.isArray(input.edges) || input.edges.length > n * (n - 1) / 2) fail("edge list shape");
  let previous = -1;
  const edges = input.edges.map(pair => {
    if (!Array.isArray(pair) || pair.length !== 2) fail("edge pair shape");
    const u = integer(pair[0], "edge endpoint", 0, n - 1), v = integer(pair[1], "edge endpoint", 0, n - 1);
    const key = u * n + v;
    if (u >= v || key <= previous) fail("edges must be distinct canonical pairs in lexicographic order");
    previous = key; return [u, v];
  });
  return { vertex_count: n, edges };
}
function compilePartitionIndex(input, options = {}) {
  const started = Date.now(), graph = inputGraph(input), n = graph.vertex_count;
  const budget = options.coefficient_budget === undefined ? 2000000 :
    integer(options.coefficient_budget, "coefficient_budget", 1, 20000000);
  const total = 1 << n, full = total - 1, adjacency = Array(n).fill(0);
  for (const [u, v] of graph.edges) { adjacency[u] |= 1 << v; adjacency[v] |= 1 << u; }
  const sizes = Array(total).fill(0), kinds = Array(total).fill(0); kinds[0] = 3;
  const work = { graph_edges_consumed: graph.edges.length, block_classification_states: 0,
    anchored_block_candidates: 0, coefficient_visits: 0, positive_coefficient_additions: 0,
    partition_enumerations: 0, old_graph_generations: 0, old_cut_or_component_evaluations: 0 };
  for (let s = 1; s < total; s++) {
    const bit = s & -s, rest = s ^ bit, v = 31 - Math.clz32(bit);
    sizes[s] = sizes[rest] + 1;
    if ((kinds[rest] & 1) && (adjacency[v] & rest) === 0) kinds[s] |= 1;
    if ((kinds[rest] & 2) && (adjacency[v] & rest) === rest) kinds[s] |= 2;
    work.block_classification_states++;
  }
  const tables = MODES.map(() => Array(total));
  for (let m = 0; m < 3; m++) tables[m][0] = [1n];
  for (let s = 1; s < total; s++) {
    const rows = MODES.map(() => Array(sizes[s] + 1).fill(0n)), anchor = s & -s;
    for (let b = s; b; b = (b - 1) & s) {
      if (!(b & anchor)) continue;
      work.anchored_block_candidates++;
      const code = kinds[b], rest = s ^ b;
      for (let m = 0; m < 3; m++) {
        if (!admits(code, m)) continue;
        const prior = tables[m][rest];
        for (let k = 0; k < prior.length; k++) {
          work.coefficient_visits++;
          if (work.coefficient_visits > budget) fail("coefficient budget exceeded; no partial snapshot returned");
          if (prior[k] !== 0n) { rows[m][k + 1] += prior[k]; work.positive_coefficient_additions++; }
        }
      }
    }
    for (let m = 0; m < 3; m++) tables[m][s] = rows[m];
  }
  const minima = MODES.map((_, m) => tables[m].map(row => row.findIndex(x => x !== 0n)));
  const profile = new Map();
  for (let s = 0; s < total; s++) {
    const tuple = [sizes[s], minima[0][s], minima[1][s], minima[2][s]], key = tuple.join("/");
    if (!profile.has(key)) profile.set(key, { size: tuple[0], chromatic: tuple[1],
      complement_chromatic: tuple[2], cochromatic: tuple[3], subsets: 0, first_mask: s });
    profile.get(key).subsets++;
  }
  const modes = {};
  for (let m = 0; m < 3; m++) modes[MODES[m]] = {
    coefficients: tables[m].map(row => row.map(String)), minima: minima[m]
  };
  const rows = [...profile.values()].sort((a, b) => a.size - b.size || a.chromatic - b.chromatic ||
    a.complement_chromatic - b.complement_chromatic || a.cochromatic - b.cochromatic);
  return {
    schema: SCHEMA, version: VERSION, graph, provenance: copy(input.provenance || {}),
    ordering: { subset: "numeric bit mask", partition: "block minima increasing; recursive first-block numeric-mask order",
      blocks: "nonempty and unlabelled; singleton has one role, not two typed copies" },
    sizes, block_kinds: kinds,
    block_kind_encoding: { empty: 3, neither: 0, independent_only: 1, clique_only: 2, singleton: 3 },
    modes, profile: rows,
    summary: {
      vertex_count: n, edge_count: graph.edges.length, induced_subsets: total,
      coefficient_cells: tables.reduce((sum, tab) => sum + tab.reduce((t, r) => t + r.length, 0), 0),
      profile_rows: rows.length,
      full_graph: {
        mask: full, chromatic: minima[0][full], complement_chromatic: minima[1][full],
        cochromatic: minima[2][full],
        optimal_counts: Object.fromEntries(MODES.map((mode, m) => [mode, tables[m][full][minima[m][full]].toString()])),
        all_partition_counts: Object.fromEntries(MODES.map((mode, m) => [mode, tables[m][full].reduce((a,b) => a+b, 0n).toString()]))
      }
    },
    construction: { ...work, coefficient_budget: budget, elapsed_ms_observation: Date.now() - started }
  };
}
function openPartitionIndex(value) {
  if (typeof value === "string") {
    if (value.length > MAX_JSON) fail("snapshot JSON limit");
    value = JSON.parse(value);
  }
  const text = JSON.stringify(value); if (text.length > MAX_JSON) fail("snapshot JSON limit");
  const snap = JSON.parse(text);
  if (!snap || snap.schema !== SCHEMA || snap.version !== VERSION) fail("unsupported snapshot");
  const graph = inputGraph(snap.graph), n = graph.vertex_count, total = 1 << n, full = total - 1;
  if (!Array.isArray(snap.sizes) || !Array.isArray(snap.block_kinds) ||
      snap.sizes.length !== total || snap.block_kinds.length !== total) fail("complete block rows required");
  for (let s = 0; s < total; s++) {
    if (snap.sizes[s] !== popcount(s)) fail("mask size mismatch");
    integer(snap.block_kinds[s], "saved block kind", 0, 3);
    if (snap.sizes[s] <= 1 && snap.block_kinds[s] !== 3) fail("empty/singleton kind mismatch");
  }
  const tables = [], minima = [];
  for (const mode of MODES) {
    const tab = snap.modes && snap.modes[mode];
    if (!tab || !Array.isArray(tab.coefficients) || !Array.isArray(tab.minima) ||
        tab.coefficients.length !== total || tab.minima.length !== total) fail("complete mode tables required");
    const numeric = [];
    for (let s = 0; s < total; s++) {
      const row = tab.coefficients[s];
      if (!Array.isArray(row) || row.length !== snap.sizes[s] + 1) fail("coefficient row shape");
      const counts = row.map(x => decimal(x, "saved coefficient"));
      if ((s === 0 && counts[0] !== 1n) || (s !== 0 && counts[0] !== 0n) || counts[counts.length - 1] !== 1n)
        fail("empty/all-singleton coefficient identity");
      const first = counts.findIndex(x => x > 0n);
      if (tab.minima[s] !== first) fail("saved minimum identity");
      numeric.push(counts);
    }
    tables.push(numeric); minima.push(tab.minima);
  }
  if (!Array.isArray(snap.profile)) fail("profile shape");
  const work = { opened_subsets: total, opened_coefficient_cells: tables.reduce((sum,t) => sum+t.reduce((a,r)=>a+r.length,0),0),
    queries: 0, candidate_blocks_inspected: 0, saved_completion_lookups: 0,
    selected_blocks: 0, labelled_polynomial_terms: 0,
    block_classifications_recomputed: 0, partition_polynomial_recurrences: 0,
    old_graph_generations: 0, old_cut_or_component_evaluations: 0 };
  function mask(x) { return integer(x, "subset mask", 0, full); }
  function kValue(k) { return integer(k, "block count", 0, n); }
  function coefficient(s, m, k) {
    work.saved_completion_lookups++;
    return k < 0 || k >= tables[m][s].length ? 0n : tables[m][s][k];
  }
  function blocks(s, m) {
    const a = s & -s, list = [];
    for (let b = s; b; b = (b - 1) & s) {
      if (!(b & a)) continue;
      work.candidate_blocks_inspected++;
      if (admits(snap.block_kinds[b], m)) list.push(b);
    }
    return list.reverse();
  }
  function parameters(s) {
    return { mask: s, vertices: vertices(s, n), size: snap.sizes[s],
      chromatic: minima[0][s], complement_chromatic: minima[1][s], cochromatic: minima[2][s],
      chromatic_gap: minima[0][s] - minima[2][s], complement_gap: minima[1][s] - minima[2][s],
      optimal_partition_counts: Object.fromEntries(MODES.map((mode,m)=>[mode,tables[m][s][minima[m][s]].toString()])) };
  }
  function describe(b) {
    return { mask: b, vertices: vertices(b,n), kind: snap.sizes[b] === 1 ? "singleton" :
      snap.block_kinds[b] === 1 ? "independent" : "clique" };
  }
  function select(s, m, k, rank) {
    const family = coefficient(s,m,k), original = rank;
    if (rank >= family) fail("partition rank outside family");
    const out = [], trace = []; let remaining = s, left = k;
    while (remaining) {
      let selected = false, skipped = 0n;
      for (const b of blocks(remaining,m)) {
        const count = coefficient(remaining ^ b,m,left-1);
        if (rank >= count) { rank -= count; skipped += count; continue; }
        trace.push({ remaining_mask: remaining, blocks_left: left, chosen_mask: b,
          skipped_completions: skipped.toString(), chosen_completions: count.toString(), residual_rank: rank.toString() });
        out.push(describe(b)); remaining ^= b; left--; selected=true; work.selected_blocks++; break;
      }
      if (!selected) fail("saved table has no selected branch");
    }
    if (left !== 0 || rank !== 0n) fail("saved table ended inconsistently");
    return { mask:s,mode:MODES[m],block_count:k,rank:original.toString(),family_count:family.toString(),blocks:out,trace };
  }
  function prefix(s,m,k,chosen) {
    if (!Array.isArray(chosen) || chosen.length > k) fail("block prefix shape");
    let remaining=s,left=k,offset=0n; const trace=[];
    for (const value of chosen) {
      const b=integer(value,"block mask",1,full);
      if (!remaining || (b & remaining)!==b || !(b & (remaining & -remaining)) ||
          !admits(snap.block_kinds[b],m)) fail("prefix must use canonical admissible blocks");
      let skipped=0n;
      for (const prior of blocks(remaining,m)) {
        if (prior>=b) break;
        skipped+=coefficient(remaining ^ prior,m,left-1);
      }
      offset+=skipped;
      trace.push({remaining_mask:remaining,blocks_left:left,chosen_mask:b,skipped_completions:skipped.toString()});
      remaining^=b;left--;
    }
    const count=coefficient(remaining,m,left);
    return {mask:s,mode:MODES[m],block_count:k,block_masks:chosen.slice(),remaining_mask:remaining,
      remaining_blocks:left,count:count.toString(),first_rank:count ? offset.toString() : null,trace};
  }
  return {
    summary(){work.queries++;return copy(snap.summary);},
    parameters(subset){work.queries++;return parameters(mask(subset));},
    coefficients(subset,mode){work.queries++;const s=mask(subset),m=modeIndex(mode);return {
      mask:s,mode,coefficients:tables[m][s].map(String),minimum:minima[m][s]};},
    count(subset,mode,k){work.queries++;return coefficient(mask(subset),modeIndex(mode),kValue(k)).toString();},
    profile(){work.queries++;return copy(snap.profile);},
    parameterPage(start=0,limit=32){
      work.queries++;integer(start,"start",0,total);integer(limit,"limit",1,64);
      const end=Math.min(total,start+limit);
      return {start,total,rows:Array.from({length:end-start},(_,i)=>parameters(start+i)),next:end<total?end:null};
    },
    selectPartition(subset,mode,k,rank){
      work.queries++;return select(mask(subset),modeIndex(mode),kValue(k),decimal(rank,"rank"));
    },
    rankPartition(subset,mode,k,blockMasks){
      work.queries++;const result=prefix(mask(subset),modeIndex(mode),kValue(k),blockMasks);
      if(result.remaining_mask!==0||result.remaining_blocks!==0||result.count!=="1")fail("complete canonical partition required");
      return {mask:result.mask,mode,block_count:k,rank:result.first_rank,trace:result.trace};
    },
    prefixCount(subset,mode,k,blockMasks){
      work.queries++;return prefix(mask(subset),modeIndex(mode),kValue(k),blockMasks);
    },
    partitionPage(subset,mode,k,start=0,limit=16){
      work.queries++;const s=mask(subset),m=modeIndex(mode),countK=kValue(k),r=decimal(start,"start"),
        count=coefficient(s,m,countK);integer(limit,"limit",1,64);if(r>count)fail("page start outside family");
      const rows=[];let at=r;for(let i=0;i<limit&&at<count;i++,at++)rows.push(select(s,m,countK,at));
      return {mask:s,mode,block_count:countK,start:r.toString(),total:count.toString(),rows,next:at<count?at.toString():null};
    },
    labelledColourings(subset,mode,colours){
      work.queries++;const s=mask(subset),m=modeIndex(mode),q=decimal(colours,"colours");
      let fall=1n,sum=0n;const terms=[];
      for(let k=0;k<tables[m][s].length;k++){
        if(k>0)fall*=q-BigInt(k-1);
        const contribution=tables[m][s][k]*fall;
        terms.push({blocks:k,partitions:tables[m][s][k].toString(),falling_factorial:fall.toString(),contribution:contribution.toString()});
        sum+=contribution;work.labelled_polynomial_terms++;
        if(q===BigInt(k))break;
      }
      return {mask:s,mode,colours:q.toString(),count:sum.toString(),terms};
    },
    statistics(){return copy(work);}
  };
}
module.exports={VERSION,MODES,compilePartitionIndex,openPartitionIndex};
