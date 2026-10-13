"use strict";

/*
 * Exact finite navigation for Turan's classical cyclic three-part 3-graph.
 * Construction attribution: Frohmader, EJC 15 (2008), R137, introduction.
 * Complement convention: Pikhurko, Adv. Math. 464 (2025), 110148.
 * This module proves no extremal equality or new limiting density.
 * Pure CommonJS: no I/O, dependencies, randomness, or native runtime.
 */

const CYCLIC_TURAN_LIMITS = Object.freeze({
  vertex_digits: 256,
  rank_digits: 768,
  page_size: 128,
  source_id_characters: 2048
});
const SCHEMA = "commons.cyclic_turan_index/v1";
const CONSTRUCTION = "ABC_AAB_BBC_CCA";
const PARTS = ["A", "B", "C"];
const DEFINITIONS = [
  { name: "ABC", family: "edge", multiplicities: [1,1,1], mode: "mixed" },
  { name: "AAB", family: "edge", multiplicities: [2,1,0], mode: "pair", pair: 0, single: 1 },
  { name: "BBC", family: "edge", multiplicities: [0,2,1], mode: "pair", pair: 1, single: 2 },
  { name: "CCA", family: "edge", multiplicities: [1,0,2], mode: "pair", pair: 2, single: 0 },
  { name: "AAA", family: "nonedge", multiplicities: [3,0,0], mode: "triple", part: 0 },
  { name: "BBB", family: "nonedge", multiplicities: [0,3,0], mode: "triple", part: 1 },
  { name: "CCC", family: "nonedge", multiplicities: [0,0,3], mode: "triple", part: 2 },
  { name: "AAC", family: "nonedge", multiplicities: [2,0,1], mode: "pair", pair: 0, single: 2 },
  { name: "ABB", family: "nonedge", multiplicities: [1,2,0], mode: "pair", pair: 1, single: 0 },
  { name: "BCC", family: "nonedge", multiplicities: [0,1,2], mode: "pair", pair: 2, single: 1 }
];

function fail(message) { throw new RangeError(message); }
function record(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(name + " must be an object");
  return value;
}
function array(value, length, name) {
  if (!Array.isArray(value) || value.length !== length) fail(name + " has the wrong length");
  return value;
}
function integer(value, name, digits, minimum = 0n) {
  let text;
  if (typeof value === "bigint") text = value.toString();
  else if (typeof value === "number" && Number.isSafeInteger(value)) text = String(value);
  else if (typeof value === "string") text = value;
  else fail(name + " must be a safe integer, BigInt, or canonical decimal string");
  if (text.length > digits || !/^(0|[1-9][0-9]*)$/.test(text)) fail(name + " is outside the decimal integer contract");
  const result = BigInt(text);
  if (result < minimum) fail(name + " is below its minimum");
  return result;
}
function decimal(value, name, digits) {
  if (typeof value !== "string") fail(name + " must be a canonical decimal string");
  return integer(value, name, digits);
}
function sourceId(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > CYCLIC_TURAN_LIMITS.source_id_characters)
    fail("source_id must be a nonempty bounded string");
  return value;
}
function choose(n, r) {
  if (n < BigInt(r)) return 0n;
  if (r === 1) return n;
  if (r === 2) return n * (n - 1n) / 2n;
  if (r === 3) return n * (n - 1n) * (n - 2n) / 6n;
  fail("unsupported binomial order");
}
function familyName(value) {
  if (value !== "edge" && value !== "nonedge") fail("family must be edge or nonedge");
  return value;
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function freshWork() {
  return {
    descriptor_builds: 0, descriptor_opens: 0,
    construction_binomial_evaluations: 0, construction_blocks: 0,
    structural_part_rows: 0, structural_block_rows: 0,
    vertices_enumerated: 0, full_triple_families_enumerated: 0, full_four_set_families_enumerated: 0,
    count_queries: 0, rank_queries: 0, select_queries: 0, degree_queries: 0,
    four_set_queries: 0, page_queries: 0, parsed_query_vertices: 0,
    query_binomial_evaluations: 0, selection_binary_steps: 0,
    selected_triples: 0, witnessed_four_sets: 0
  };
}
function balancedSizes(n) {
  return [(n + 2n) / 3n, (n + 1n) / 3n, n / 3n];
}
function isBalanced(sizes) {
  const sorted = sizes.slice().sort((a,b) => a < b ? -1 : a > b ? 1 : 0);
  return sorted[2] - sorted[0] <= 1n;
}

function createCyclicTuranIndex(options) {
  record(options, "options");
  const hasN = Object.prototype.hasOwnProperty.call(options, "n");
  const hasParts = Object.prototype.hasOwnProperty.call(options, "part_sizes");
  if (hasN === hasParts) fail("supply exactly one of n or part_sizes");
  const sid = sourceId(options.source_id);
  let sizes, mode;
  if (hasN) {
    sizes = balancedSizes(integer(options.n, "n", CYCLIC_TURAN_LIMITS.vertex_digits));
    mode = "balanced";
  } else {
    sizes = array(options.part_sizes, 3, "part_sizes").map((x,i) =>
      integer(x, "part_sizes[" + i + "]", CYCLIC_TURAN_LIMITS.vertex_digits));
    mode = "part_sizes";
  }
  const n = sizes[0] + sizes[1] + sizes[2];
  integer(n, "vertex_count", CYCLIC_TURAN_LIMITS.vertex_digits);
  const work = freshWork();
  work.descriptor_builds = 1;
  const buildChoose = (x,r) => { work.construction_binomial_evaluations++; return choose(x,r); };
  const pairs = sizes.map(x => buildChoose(x,2));
  const triples = sizes.map(x => buildChoose(x,3));
  const total = buildChoose(n,3);
  const vertexPairs = buildChoose(n === 0n ? 0n : n - 1n,2);
  const counts = DEFINITIONS.map(d =>
    d.mode === "mixed" ? sizes[0] * sizes[1] * sizes[2] :
    d.mode === "pair" ? pairs[d.pair] * sizes[d.single] : triples[d.part]);
  const totals = { edge: 0n, nonedge: 0n };
  const blocks = DEFINITIONS.map((d,i) => {
    const start = totals[d.family];
    totals[d.family] += counts[i];
    work.construction_blocks++;
    return { name: d.name, family: d.family, multiplicities: d.multiplicities.slice(),
      start: String(start), count: String(counts[i]) };
  });
  if (totals.edge + totals.nonedge !== total) fail("construction count identity failed");
  let offset = 0n, edgeDegreeSum = 0n, nonedgeDegreeSum = 0n;
  const parts = sizes.map((size,i) => {
    let edgeDegree = null, nonedgeDegree = null;
    if (size > 0n) {
      const next = (i + 1) % 3, previous = (i + 2) % 3;
      edgeDegree = sizes[next] * sizes[previous] + (size - 1n) * sizes[next] + pairs[previous];
      nonedgeDegree = vertexPairs - edgeDegree;
      if (nonedgeDegree < 0n) fail("construction degree identity failed");
      edgeDegreeSum += size * edgeDegree;
      nonedgeDegreeSum += size * nonedgeDegree;
    }
    const row = {
      name: PARTS[i], offset: String(offset), size: String(size),
      first: size === 0n ? null : String(offset + 1n),
      last: size === 0n ? null : String(offset + size),
      edge_degree: edgeDegree === null ? null : String(edgeDegree),
      nonedge_degree: nonedgeDegree === null ? null : String(nonedgeDegree)
    };
    offset += size;
    return row;
  });
  if (edgeDegreeSum !== 3n * totals.edge || nonedgeDegreeSum !== 3n * totals.nonedge)
    fail("construction incidence accounting failed");
  const data = {
    schema: SCHEMA, construction: CONSTRUCTION, source_id: sid, input_mode: mode,
    vertex_count: String(n), part_sizes: sizes.map(String), balanced: isBalanced(sizes),
    parts, blocks, edge_count: String(totals.edge), nonedge_count: String(totals.nonedge),
    total_triples: String(total),
    arithmetic: {
      part_pair_counts: pairs.map(String), part_triple_counts: triples.map(String),
      vertex_pair_count: String(vertexPairs),
      edge_degree_sum: String(edgeDegreeSum), nonedge_degree_sum: String(nonedgeDegreeSum),
      three_edge_count: String(3n * totals.edge), three_nonedge_count: String(3n * totals.nonedge)
    }
  };
  return instantiate(data, work);
}

function normalizeSnapshot(snapshot, work) {
  record(snapshot, "snapshot");
  if (snapshot.schema !== SCHEMA || snapshot.construction !== CONSTRUCTION) fail("unsupported snapshot schema or orientation");
  const sid = sourceId(snapshot.source_id);
  const vd = CYCLIC_TURAN_LIMITS.vertex_digits, rd = CYCLIC_TURAN_LIMITS.rank_digits;
  const sizes = array(snapshot.part_sizes,3,"part_sizes").map((x,i) => decimal(x,"part size " + i,vd));
  const n = decimal(snapshot.vertex_count,"vertex_count",vd);
  if (sizes[0] + sizes[1] + sizes[2] !== n) fail("part sizes do not sum to vertex_count");
  if (snapshot.input_mode !== "balanced" && snapshot.input_mode !== "part_sizes") fail("unsupported input_mode");
  if (snapshot.input_mode === "balanced" && balancedSizes(n).some((x,i) => x !== sizes[i]))
    fail("balanced allocation does not match its declared order");
  if (snapshot.balanced !== isBalanced(sizes)) fail("incorrect balanced flag");
  const arithmeticSource = record(snapshot.arithmetic,"arithmetic");
  const pairs = array(arithmeticSource.part_pair_counts,3,"part_pair_counts").map((x,i) => String(decimal(x,"pair count " + i,rd)));
  const triples = array(arithmeticSource.part_triple_counts,3,"part_triple_counts").map((x,i) => String(decimal(x,"triple count " + i,rd)));
  const vertexPairs = decimal(arithmeticSource.vertex_pair_count,"vertex_pair_count",rd);
  let offset = 0n;
  const parts = array(snapshot.parts,3,"parts").map((x,i) => {
    record(x,"part");
    if (x.name !== PARTS[i] || decimal(x.size,"part size",vd) !== sizes[i] ||
        decimal(x.offset,"part offset",vd) !== offset) fail("inconsistent part row");
    const size = sizes[i];
    let ed = null, nd = null;
    if (size === 0n) {
      if (x.first !== null || x.last !== null || x.edge_degree !== null || x.nonedge_degree !== null)
        fail("empty parts must have null endpoints and degrees");
    } else {
      if (decimal(x.first,"first",vd) !== offset + 1n || decimal(x.last,"last",vd) !== offset + size)
        fail("inconsistent part endpoints");
      ed = decimal(x.edge_degree,"edge_degree",rd);
      nd = decimal(x.nonedge_degree,"nonedge_degree",rd);
      if (ed + nd !== vertexPairs) fail("degrees do not partition the supplied vertex pair count");
    }
    const row = { name:PARTS[i],offset:String(offset),size:String(size),
      first:size === 0n ? null : String(offset + 1n),last:size === 0n ? null : String(offset + size),
      edge_degree:ed === null ? null : String(ed),nonedge_degree:nd === null ? null : String(nd) };
    offset += size;
    work.structural_part_rows++;
    return row;
  });
  const totals = {edge:0n,nonedge:0n};
  const blocks = array(snapshot.blocks,10,"blocks").map((x,i) => {
    record(x,"block");
    const d=DEFINITIONS[i];
    if(x.name !== d.name || x.family !== d.family ||
       array(x.multiplicities,3,"multiplicities").some((v,j) => v !== d.multiplicities[j]))
      fail("block metadata does not match the fixed construction");
    const start=decimal(x.start,"block start",rd), count=decimal(x.count,"block count",rd);
    if(start !== totals[d.family]) fail("block starts are not contiguous");
    totals[d.family] += count;
    work.structural_block_rows++;
    return {name:d.name,family:d.family,multiplicities:d.multiplicities.slice(),start:String(start),count:String(count)};
  });
  const edge=decimal(snapshot.edge_count,"edge_count",rd);
  const nonedge=decimal(snapshot.nonedge_count,"nonedge_count",rd);
  const total=decimal(snapshot.total_triples,"total_triples",rd);
  if(totals.edge !== edge || totals.nonedge !== nonedge || edge + nonedge !== total)
    fail("supplied block and family totals disagree");
  const eds=decimal(arithmeticSource.edge_degree_sum,"edge_degree_sum",rd);
  const nds=decimal(arithmeticSource.nonedge_degree_sum,"nonedge_degree_sum",rd);
  const te=decimal(arithmeticSource.three_edge_count,"three_edge_count",rd);
  const tn=decimal(arithmeticSource.three_nonedge_count,"three_nonedge_count",rd);
  if(eds !== te || nds !== tn || te !== 3n*edge || tn !== 3n*nonedge)
    fail("supplied incidence totals disagree");
  // These are structural/additive consistency checks, not a replay or proof
  // of the supplied binomial counts, degrees, source identity, or provenance.
  return {
    schema:SCHEMA,construction:CONSTRUCTION,source_id:sid,input_mode:snapshot.input_mode,
    vertex_count:String(n),part_sizes:sizes.map(String),balanced:snapshot.balanced,parts,blocks,
    edge_count:String(edge),nonedge_count:String(nonedge),total_triples:String(total),
    arithmetic:{part_pair_counts:pairs,part_triple_counts:triples,vertex_pair_count:String(vertexPairs),
      edge_degree_sum:String(eds),nonedge_degree_sum:String(nds),three_edge_count:String(te),three_nonedge_count:String(tn)}
  };
}

function openRetainedCyclicTuranIndex(snapshot) {
  const work=freshWork();
  work.descriptor_opens=1;
  return instantiate(normalizeSnapshot(snapshot,work),work);
}

function instantiate(data, work) {
  const n=BigInt(data.vertex_count), sizes=data.part_sizes.map(BigInt);
  const offsets=data.parts.map(p=>BigInt(p.offset));
  const totals={edge:BigInt(data.edge_count),nonedge:BigInt(data.nonedge_count)};
  const blockNumbers=data.blocks.map(b=>({start:BigInt(b.start),count:BigInt(b.count)}));
  const byComposition=new Map(DEFINITIONS.map((d,i)=>[d.multiplicities.join(","),i]));
  function queryChoose(x,r){work.query_binomial_evaluations++;return choose(x,r);}
  function partOf(v){
    for(let i=0;i<3;i++) if(v>offsets[i] && v<=offsets[i]+sizes[i]) return i;
    fail("vertex is not in a part");
  }
  function parseVertices(input,length){
    const values=array(input,length,"vertices").map((v,i)=>
      integer(v,"vertex " + i,CYCLIC_TURAN_LIMITS.vertex_digits,1n));
    values.sort((a,b)=>a<b?-1:a>b?1:0);
    for(let i=0;i<length;i++){
      if(values[i]>n) fail("vertex exceeds vertex_count");
      if(i && values[i]===values[i-1]) fail("vertices must be distinct");
    }
    work.parsed_query_vertices+=length;
    const groups=[[],[],[]];
    for(const v of values){const p=partOf(v);groups[p].push(v-offsets[p]-1n);}
    return {values,groups};
  }
  function colexRank(values){
    let rank=values[0];
    for(let j=1;j<values.length;j++)rank+=queryChoose(values[j],j+1);
    return rank;
  }
  function colexSelect(rank,size,order){
    if(size<BigInt(order))fail("retained block count contradicts its part size");
    const out=new Array(order);
    let remainder=rank,upper=size;
    for(let j=order;j>=2;j--){
      let low=BigInt(j-1),high=upper-1n,best=low,bestValue=0n;
      while(low<=high){
        const mid=(low+high)/2n,value=queryChoose(mid,j);
        work.selection_binary_steps++;
        if(value<=remainder){best=mid;bestValue=value;low=mid+1n;}
        else high=mid-1n;
      }
      out[j-1]=best;
      remainder-=bestValue;
      upper=best;
    }
    if(remainder<0n || remainder>=upper)fail("retained block count permits an invalid colex rank");
    out[0]=remainder;
    return out;
  }
  function result(d,rank,inner,vertices){
    return {family:d.family,rank:String(rank),class:d.name,block_rank:String(inner),vertices:vertices.map(String)};
  }
  function rankTriple(vertices){
    work.rank_queries++;
    const parsed=parseVertices(vertices,3);
    const index=byComposition.get(parsed.groups.map(g=>g.length).join(","));
    if(index===undefined)fail("invalid triple composition");
    const d=DEFINITIONS[index],b=blockNumbers[index],g=parsed.groups;
    let inner;
    if(d.mode==="mixed")inner=(g[0][0]*sizes[1]+g[1][0])*sizes[2]+g[2][0];
    else if(d.mode==="pair")inner=colexRank(g[d.pair])*sizes[d.single]+g[d.single][0];
    else inner=colexRank(g[d.part]);
    if(inner<0n || inner>=b.count)fail("retained block count contradicts this triple");
    return result(d,b.start+inner,inner,parsed.values);
  }
  function select(family,rankInput){
    family=familyName(family);
    const rank=integer(rankInput,"rank",CYCLIC_TURAN_LIMITS.rank_digits);
    if(rank>=totals[family])fail("rank is outside the chosen family");
    work.select_queries++;
    const index=DEFINITIONS.findIndex((d,i)=>d.family===family &&
      rank>=blockNumbers[i].start && rank<blockNumbers[i].start+blockNumbers[i].count);
    if(index<0)fail("no retained block contains the rank");
    const d=DEFINITIONS[index],inner=rank-blockNumbers[index].start;
    let vertices;
    if(d.mode==="mixed"){
      if(sizes.some(x=>x===0n))fail("retained mixed block has an empty part");
      let q=inner;
      const c=q%sizes[2];q/=sizes[2];
      const b=q%sizes[1],a=q/sizes[1];
      if(a>=sizes[0])fail("retained mixed block count is too large");
      vertices=[offsets[0]+a+1n,offsets[1]+b+1n,offsets[2]+c+1n];
    }else if(d.mode==="pair"){
      if(sizes[d.single]===0n)fail("retained pair block has an empty singleton part");
      const pair=colexSelect(inner/sizes[d.single],sizes[d.pair],2);
      const one=inner%sizes[d.single];
      vertices=[...pair.map(v=>offsets[d.pair]+v+1n),offsets[d.single]+one+1n];
    }else{
      vertices=colexSelect(inner,sizes[d.part],3).map(v=>offsets[d.part]+v+1n);
    }
    vertices.sort((a,b)=>a<b?-1:a>b?1:0);
    work.selected_triples++;
    return result(d,rank,inner,vertices);
  }
  function page(family,options={}){
    family=familyName(family);record(options,"page options");
    const start=integer(options.start===undefined?"0":options.start,"page start",CYCLIC_TURAN_LIMITS.rank_digits);
    const limit=options.limit===undefined?CYCLIC_TURAN_LIMITS.page_size:options.limit;
    if(!Number.isSafeInteger(limit)||limit<1||limit>CYCLIC_TURAN_LIMITS.page_size)fail("page limit is outside its bounds");
    if(start>totals[family])fail("page starts beyond the chosen family");
    work.page_queries++;
    const rows=[];
    let cursor=start;
    while(cursor<totals[family] && rows.length<limit){rows.push(select(family,cursor));cursor++;}
    return {family,start:String(start),returned:rows.length,total:String(totals[family]),
      next_rank:cursor===totals[family]?null:String(cursor),records:rows};
  }
  function degree(vertex){
    const v=integer(vertex,"vertex",CYCLIC_TURAN_LIMITS.vertex_digits,1n);
    if(v>n)fail("vertex exceeds vertex_count");
    work.degree_queries++;work.parsed_query_vertices++;
    const p=partOf(v),row=data.parts[p];
    return {vertex:String(v),part:PARTS[p],local_index:String(v-offsets[p]-1n),
      edge_degree:row.edge_degree,nonedge_degree:row.nonedge_degree};
  }
  function nonedgeInFour(vertices){
    work.four_set_queries++;
    const parsed=parseVertices(vertices,4),g=parsed.groups;
    let chosen=null,certificate=null;
    for(let p=0;p<3;p++){
      if(g[p].length>=3){
        chosen=g[p].slice(0,3).map(v=>offsets[p]+v+1n);
        certificate={case:"same_part_triple",part:PARTS[p]};
        break;
      }
    }
    if(chosen===null){
      for(let p=0;p<3;p++){
        const q=(p+2)%3;
        if(g[p].length>=2 && g[q].length>=1){
          chosen=[offsets[p]+g[p][0]+1n,offsets[p]+g[p][1]+1n,offsets[q]+g[q][0]+1n];
          certificate={case:"reverse_cyclic_pair",pair_part:PARTS[p],singleton_part:PARTS[q],
            permitted_singleton_part:PARTS[(p+1)%3]};
          break;
        }
      }
    }
    if(chosen===null)fail("four-set composition invariant failed");
    const missing=rankTriple(chosen);
    if(missing.family!=="nonedge")fail("four-set witness invariant failed");
    work.witnessed_four_sets++;
    return {vertices:parsed.values.map(String),part_counts:g.map(x=>x.length),certificate,missing};
  }
  return Object.freeze({
    count(family){family=familyName(family);work.count_queries++;return String(totals[family]);},
    summary(){
      return clone({schema:SCHEMA,construction:CONSTRUCTION,source_id:data.source_id,
        input_mode:data.input_mode,vertex_count:data.vertex_count,part_sizes:data.part_sizes,
        balanced:data.balanced,parts:data.parts,blocks:data.blocks,edge_count:data.edge_count,
        nonedge_count:data.nonedge_count,total_triples:data.total_triples,
        edge_density_fraction:n<3n?null:{numerator:data.edge_count,denominator:data.total_triples},
        nonedge_density_fraction:n<3n?null:{numerator:data.nonedge_count,denominator:data.total_triples}});
    },
    classifyTriple:rankTriple,
    rankTriple,
    select,
    page,
    degree,
    nonedgeInFour,
    snapshot(){return clone(data);},
    work(){return {...work};}
  });
}

module.exports={createCyclicTuranIndex,openRetainedCyclicTuranIndex,CYCLIC_TURAN_LIMITS};
