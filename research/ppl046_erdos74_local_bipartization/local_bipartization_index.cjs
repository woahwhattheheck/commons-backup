"use strict";

/*
 * Complete finite induced-subgraph edge-bipartization profiles.
 * Source parameter: Erdos-Hajnal-Szemeredi (1982), Definition 3.1.
 * Mycielski construction is prior source material. See the guide for scope.
 * Plain bounded integer arithmetic; no dependencies, I/O or random search.
 */
const LOCAL_BIPARTIZATION_LIMITS=Object.freeze({
 max_vertices:14,max_input_edges:4096,max_page_size:256,
 max_subset_filter_cache_entries:16,max_integer_digits:16
});
const SCHEMA="commons.local_bipartization_cut_index.v1";
const HEX=Array.from({length:256},(_,i)=>i.toString(16).padStart(2,"0"));
const copy=x=>JSON.parse(JSON.stringify(x));
function fail(s){throw new Error(s);}
function object(x,name){if(!x||typeof x!=="object"||Array.isArray(x))fail(name+" must be an object");return x;}
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside supported integer range");return x;}
function boundedNat(x,hi,name){
 let s;if(typeof x==="bigint")s=x.toString();
 else if(typeof x==="number"&&Number.isSafeInteger(x)&&x>=0)s=String(x);
 else if(typeof x==="string")s=x;else fail(name+" must be a nonnegative integer");
 if(!/^(0|[1-9][0-9]*)$/.test(s)||s.length>LOCAL_BIPARTIZATION_LIMITS.max_integer_digits)
  fail(name+" must use bounded canonical nonnegative decimal notation");
 const n=BigInt(s);if(n>BigInt(hi))fail(name+" outside family");return Number(n);
}
function popcount(x){let c=0;while(x){x&=x-1;c++;}return c;}
function vertices(mask,n){const a=[];for(let i=0;i<n;i++)if(mask&(1<<i))a.push(i);return a;}
function bitIndex(bit){return 31-Math.clz32(bit);}
function workRecord(phase){return {
 phase,input_edge_pairs:0,duplicate_input_pairs:0,adjacency_insertions:0,
 subset_edge_states:0,subset_adjacency_popcounts:0,component_searches:0,
 component_vertex_expansions:0,cut_cost_evaluations:0,
 optimal_component_anchor_checks:0,profile_updates:0,
 retained_subsets:0,retained_canonical_cuts:0,retained_optimal_cut_codes:0,
 retained_minimum_deletion_codes:0,reader_cost_cells_checked:0,
 reader_optimal_codes_checked:0,reader_component_records_checked:0,
 reader_profile_updates:0,query_calls:0,subset_filter_compilations:0,
 subset_filter_cache_hits:0,subset_filter_cache_evictions:0,
 subset_filter_rows_inspected:0,subset_rows_returned:0,
 cut_rows_returned:0,witness_edge_inspections:0,selected_witness_cost_checks:0,
 budget_profile_rows_inspected:0
};}
function normalizeGraph(input,maxVertices=LOCAL_BIPARTIZATION_LIMITS.max_vertices,work=null){
 object(input,"graph");const n=integer(input.vertex_count,0,maxVertices,"vertex_count");
 if(!Array.isArray(input.edges)||input.edges.length>LOCAL_BIPARTIZATION_LIMITS.max_input_edges)
  fail("bounded edge-pair array required");
 const keys=new Set();
 for(const e of input.edges){
  if(work)work.input_edge_pairs++;
  if(!Array.isArray(e)||e.length!==2)fail("an edge must have two endpoints");
  let u=integer(e[0],0,n-1,"edge endpoint"),v=integer(e[1],0,n-1,"edge endpoint");
  if(u===v)fail("loops are not supported");if(u>v){const t=u;u=v;v=t;}
  const key=u*n+v;
  if(keys.has(key)){if(work)work.duplicate_input_pairs++;}else keys.add(key);
 }
 const edges=[...keys].sort((a,b)=>a-b).map(k=>[Math.floor(k/n),k%n]),
  adjacency=new Array(n).fill(0);
 for(const [u,v] of edges){adjacency[u]|=1<<v;adjacency[v]|=1<<u;if(work)work.adjacency_insertions+=2;}
 return {vertex_count:n,edge_count:edges.length,edges,adjacency_masks:adjacency};
}
function mycielskiGraph(base){
 const g=normalizeGraph(base,Math.floor((LOCAL_BIPARTIZATION_LIMITS.max_vertices-1)/2)),
  n=g.vertex_count,root=2*n,edges=g.edges.map(e=>e.slice());
 for(const [u,v] of g.edges){edges.push([u,n+v],[v,n+u]);}
 for(let i=0;i<n;i++)edges.push([n+i,root]);
 const result=normalizeGraph({vertex_count:2*n+1,edges});
 return {vertex_count:result.vertex_count,edges:result.edges,
  construction:{name:"Mycielski graph",base_vertex_count:n,base_edge_count:g.edge_count,
   base_edges:g.edges,base_vertices:Array.from({length:n},(_,i)=>i),
   twin_of:Array.from({length:n},(_,i)=>n+i),apex:root,
   rule:"retain base edges; each base edge xy adds x-twin(y) and y-twin(x); join the apex to all twins",
   generated_edge_count:3*g.edge_count+n,
   attribution:"Jan Mycielski, Sur le coloriage des graphes, Colloquium Mathematicum 3 (1955), 161-162"}};
}
function sizesThrough(n){
 const a=new Array(1<<n).fill(0);for(let s=1;s<a.length;s++)a[s]=a[s&(s-1)]+1;return a;
}
function cutCountFromSize(s){return s===0?1:1<<(s-1);}
function maskFromCode(s,code){
 if(s===0)return 0;
 const p=s&-s;let rest=s^p,a=p,j=0;
 while(rest){const b=rest&-rest;if(code&(1<<j))a|=b;rest^=b;j++;}
 return a;
}
function codeFromMask(s,a){
 if(s===0)return 0;
 let rest=s^(s&-s),code=0,j=0;
 while(rest){const b=rest&-rest;if(a&b)code|=1<<j;rest^=b;j++;}
 return code;
}
function componentPartition(s,adjacency,work){
 const out=[];let remaining=s,anchors=0;
 if(s)work.component_searches++;
 while(remaining){
  const root=remaining&-remaining;anchors|=root;
  let seen=root,todo=root;
  while(todo){
   const b=todo&-todo;todo^=b;const v=bitIndex(b);work.component_vertex_expansions++;
   const fresh=adjacency[v]&s&~seen;seen|=fresh;todo|=fresh;
  }
  out.push(seen);remaining^=seen;
 }
 return {components:out,anchors};
}
function emptyProfiles(n,edges){return Array.from({length:n+1},(_,size)=>({
 size,subset_count:0,minimum_minimum:null,maximum_minimum:null,
 minimum_distribution:new Array(edges+1).fill(0),maximizer_masks:[]
}));}
function updateProfile(p,s,minimum){
 p.subset_count++;p.minimum_distribution[minimum]++;
 if(p.minimum_minimum===null||minimum<p.minimum_minimum)p.minimum_minimum=minimum;
 if(p.maximum_minimum===null||minimum>p.maximum_minimum){p.maximum_minimum=minimum;p.maximizer_masks=[s];}
 else if(minimum===p.maximum_minimum)p.maximizer_masks.push(s);
}
function compileLocalBipartization(input){
 const work=workRecord("constructor"),graph=normalizeGraph(input,LOCAL_BIPARTIZATION_LIMITS.max_vertices,work),
  n=graph.vertex_count,total=1<<n,sizes=sizesThrough(n),
  edgeCounts=new Array(total).fill(0),components=[],anchors=[],costRows=[],
  histograms=[],minima=[],optimal=[],deletionSets=[],profiles=emptyProfiles(n,graph.edge_count);
 for(let s=1;s<total;s++){
  const b=s&-s,rest=s^b;edgeCounts[s]=edgeCounts[rest]+popcount(graph.adjacency_masks[bitIndex(b)]&rest);
  work.subset_edge_states++;work.subset_adjacency_popcounts++;
 }
 for(let s=0;s<total;s++){
  const cp=componentPartition(s,graph.adjacency_masks,work);
  components.push(cp.components);anchors.push(cp.anchors);
  const expected=cutCountFromSize(sizes[s]),p=s&-s,rest=s^p;
  let t=0,code=0,row="",best=edgeCounts[s]+1,opts=[],dels=[];
  const histogram=new Array(edgeCounts[s]+1).fill(0);
  do{
   const a=p|t,b=s^a,cost=edgeCounts[a]+edgeCounts[b];
   row+=HEX[cost];histogram[cost]++;work.cut_cost_evaluations++;
   if(cost<=best){
    work.optimal_component_anchor_checks++;
    if(cost<best){best=cost;opts=[];dels=[];}
    opts.push(code);if((a&cp.anchors)===cp.anchors)dels.push(code);
   }
   code++;t=(t-rest)&rest;
  }while(t!==0);
  if(code!==expected)fail("canonical cut coverage mismatch");
  const multiplicity=s===0?1:2**(cp.components.length-1);
  if(opts.length!==dels.length*multiplicity)fail("component-flip multiplicity mismatch");
  costRows.push(row);histograms.push(histogram);minima.push(best);optimal.push(opts);deletionSets.push(dels);
  updateProfile(profiles[sizes[s]],s,best);work.profile_updates++;
  work.retained_canonical_cuts+=code;work.retained_optimal_cut_codes+=opts.length;
  work.retained_minimum_deletion_codes+=dels.length;
 }
 const expectedTotal=(3**n+1)/2;
 if(work.retained_canonical_cuts!==expectedTotal)fail("complete cut-family total mismatch");
 work.retained_subsets=total;
 const snapshot={
  schema:SCHEMA,graph,
  ordering:{vertices:"integer labels 0..vertex_count-1",subsets:"increasing numeric vertex mask",
   canonical_vertex_bipartitions:"the least vertex of a nonempty subset belongs to A; empty classes allowed",
   cut_codes:"increasing A-mask; compress the other subset bits into a zero-based code",
   minimum_deletion_sets:"least vertex of each original connected component belongs to A",
   empty_subset:"one empty coloring, cut and deletion set"},
  encoding:{cut_cost_radix:16,cut_cost_hex_width:2,cut_rows:"one complete row for each numeric subset mask"},
  coverage:{subset_count:total,canonical_cut_count:expectedTotal,
   nonempty_subset_canonical_cut_count:expectedTotal-1,empty_cut_count:1},
  edge_count_by_subset:edgeCounts,component_masks_by_subset:components,
  component_anchor_mask_by_subset:anchors,cut_cost_hex_by_subset:costRows,
  cut_cost_histogram_by_subset:histograms,minimum_deletions_by_subset:minima,
  optimal_cut_codes_by_subset:optimal,minimum_deletion_codes_by_subset:deletionSets,
  profile_by_size:profiles,
  source_parameter:{authors:"P. Erdos, A. Hajnal, E. Szemeredi",year:1982,
   title:"On almost bipartite large chromatic graphs",definition:"3.1",
   url:"https://renyi.hu/~p_erdos/1982-11.pdf"},
  mathematical_scope:"complete finite host profile; no infinite-chromatic construction or status proof",
  construction_work:copy(work)
 };
 return makeInterface(snapshot,work);
}
function equal(a,b){return JSON.stringify(a)===JSON.stringify(b);}
function sortedCodes(a,max,name){
 if(!Array.isArray(a)||a.length===0)fail(name+" requires at least one code");
 let last=-1;for(const x of a){integer(x,0,max-1,name);if(x<=last)fail(name+" not strictly increasing");last=x;}
}
function validateSnapshot(raw){
 object(raw,"snapshot");if(raw.schema!==SCHEMA)fail("unsupported snapshot schema");
 const graph=normalizeGraph(raw.graph),n=graph.vertex_count,total=1<<n,
  sizes=sizesThrough(n),work=workRecord("saved_reader"),expectedTotal=(3**n+1)/2;
 if(!equal(raw.graph,graph))fail("canonical graph representation mismatch");
 if(!raw.encoding||raw.encoding.cut_cost_radix!==16||raw.encoding.cut_cost_hex_width!==2)
  fail("cost encoding mismatch");
 if(!raw.coverage||raw.coverage.subset_count!==total||raw.coverage.canonical_cut_count!==expectedTotal||
    raw.coverage.nonempty_subset_canonical_cut_count!==expectedTotal-1||raw.coverage.empty_cut_count!==1)
  fail("coverage metadata mismatch");
 const arrayNames=["edge_count_by_subset","component_masks_by_subset","component_anchor_mask_by_subset",
  "cut_cost_hex_by_subset","cut_cost_histogram_by_subset","minimum_deletions_by_subset",
  "optimal_cut_codes_by_subset","minimum_deletion_codes_by_subset"];
 for(const name of arrayNames)if(!Array.isArray(raw[name])||raw[name].length!==total)fail("complete "+name+" required");
 const profiles=emptyProfiles(n,graph.edge_count);
 for(let s=0;s<total;s++){
  const edgeCount=integer(raw.edge_count_by_subset[s],0,graph.edge_count,"subset edge count"),
   minimum=integer(raw.minimum_deletions_by_subset[s],0,edgeCount,"minimum deletions"),
   count=cutCountFromSize(sizes[s]),row=raw.cut_cost_hex_by_subset[s],
   cp=raw.component_masks_by_subset[s],opts=raw.optimal_cut_codes_by_subset[s],
   dels=raw.minimum_deletion_codes_by_subset[s];
  if((s===0&&edgeCount!==0)||(s===total-1&&edgeCount!==graph.edge_count))fail("endpoint edge count mismatch");
  if(!Array.isArray(cp))fail("component-mask array required");
  let union=0,anchor=0,lastRoot=-1;
  for(const c of cp){
   integer(c,1,total-1,"component mask");const root=c&-c;
   if((c&s)!==c||(c&union)!==0||root<=lastRoot)fail("component partition/order mismatch");
   union|=c;anchor|=root;lastRoot=root;work.reader_component_records_checked++;
  }
  if(union!==s||raw.component_anchor_mask_by_subset[s]!==anchor)fail("component union/anchor mismatch");
  if(typeof row!=="string"||row.length!==2*count||!/^[0-9a-f]+$/.test(row))fail("complete fixed-width cost row required");
  sortedCodes(opts,count,"optimal cut codes");sortedCodes(dels,count,"minimum deletion codes");
  const hist=new Array(edgeCount+1).fill(0);let oi=0;
  for(let code=0;code<count;code++){
   const cost=parseInt(row.slice(2*code,2*code+2),16);work.reader_cost_cells_checked++;
   if(cost<minimum||cost>edgeCount)fail("saved cost outside minimum/edge range");
   hist[cost]++;
   if(cost===minimum){if(opts[oi]!==code)fail("optimal code coverage mismatch");oi++;}
  }
  if(oi!==opts.length||!equal(hist,raw.cut_cost_histogram_by_subset[s]))fail("saved histogram/minimum mismatch");
  let di=0;
  for(const code of opts){
   const a=maskFromCode(s,code);work.reader_optimal_codes_checked++;
   if((a&anchor)===anchor){if(dels[di]!==code)fail("minimum deletion representative mismatch");di++;}
  }
  const multiplicity=s===0?1:2**(cp.length-1);
  if(di!==dels.length||opts.length!==dels.length*multiplicity)fail("saved component multiplicity mismatch");
  updateProfile(profiles[sizes[s]],s,minimum);work.reader_profile_updates++;
  work.retained_canonical_cuts+=count;work.retained_optimal_cut_codes+=opts.length;
  work.retained_minimum_deletion_codes+=dels.length;
 }
 if(!equal(profiles,raw.profile_by_size))fail("profile aggregation mismatch");
 object(raw.ordering,"ordering");object(raw.source_parameter,"source_parameter");object(raw.construction_work,"construction_work");
 work.retained_subsets=total;
 return {snapshot:copy(raw),work};
}
function openRetainedLocalBipartization(snapshot){
 const v=validateSnapshot(snapshot);return makeInterface(v.snapshot,v.work);
}
function makeInterface(snapshot,work){
 const graph=snapshot.graph,n=graph.vertex_count,total=1<<n,full=total-1,
  sizes=sizesThrough(n),cache=new Map();
 function mask(x,name){return boundedNat(x,full,name);}
 function pageLimit(x){return integer(x,1,LOCAL_BIPARTIZATION_LIMITS.max_page_size,"page limit");}
 function rank(x,count,name,allowEnd){
  const r=boundedNat(x,count,name);if(!allowEnd&&r===count)fail(name+" outside family");return r;
 }
 function row(s){
  return {subset_mask:s,vertices:vertices(s,n),size:sizes[s],
   edge_count:snapshot.edge_count_by_subset[s],
   component_masks:snapshot.component_masks_by_subset[s].slice(),
   component_count:snapshot.component_masks_by_subset[s].length,
   component_anchor_mask:snapshot.component_anchor_mask_by_subset[s],
   minimum_deletions:snapshot.minimum_deletions_by_subset[s],
   maximum_crossing_edges:snapshot.edge_count_by_subset[s]-snapshot.minimum_deletions_by_subset[s],
   canonical_vertex_bipartition_count:cutCountFromSize(sizes[s]),
   optimal_vertex_bipartition_count:snapshot.optimal_cut_codes_by_subset[s].length,
   minimum_deletion_set_count:snapshot.minimum_deletion_codes_by_subset[s].length,
   vertex_bipartitions_per_minimum_deletion_set:s===0?1:2**(snapshot.component_masks_by_subset[s].length-1)};
 }
 function queryFamily(query={}){
  object(query,"subset query");
  const size=query.size===undefined||query.size===null?null:integer(query.size,0,n,"subset size"),
   lo=query.minimum_at_least===undefined?0:integer(query.minimum_at_least,0,graph.edge_count,"minimum_at_least"),
   hi=query.minimum_at_most===undefined?graph.edge_count:integer(query.minimum_at_most,0,graph.edge_count,"minimum_at_most"),
   contain=query.contains===undefined?0:mask(query.contains,"contains mask"),
   exclude=query.excludes===undefined?0:mask(query.excludes,"excludes mask");
  if(lo>hi)fail("reversed minimum-deletion range");if(contain&exclude)fail("contains/excludes masks conflict");
  const q={size,minimum_at_least:lo,minimum_at_most:hi,contains:contain,excludes:exclude},
   key=[size===null?"*":size,lo,hi,contain,exclude].join("/");
  if(cache.has(key)){work.subset_filter_cache_hits++;return cache.get(key);}
  const ids=[];
  for(let s=0;s<total;s++){
   work.subset_filter_rows_inspected++;
   if(size!==null&&sizes[s]!==size)continue;
   if((s&contain)!==contain||(s&exclude)!==0)continue;
   const v=snapshot.minimum_deletions_by_subset[s];if(v>=lo&&v<=hi)ids.push(s);
  }
  if(cache.size>=LOCAL_BIPARTIZATION_LIMITS.max_subset_filter_cache_entries){
   cache.delete(cache.keys().next().value);work.subset_filter_cache_evictions++;
  }
  const out={query:q,ids};cache.set(key,out);work.subset_filter_compilations++;return out;
 }
 function search(a,x){let lo=0,hi=a.length;while(lo<hi){const mid=(lo+hi)>>1;if(a[mid]<x)lo=mid+1;else hi=mid;}return lo;}
 function family(s,kind){
  if(kind==="all")return {count:cutCountFromSize(sizes[s]),codes:null};
  if(kind==="optimal")return {count:snapshot.optimal_cut_codes_by_subset[s].length,codes:snapshot.optimal_cut_codes_by_subset[s]};
  if(kind==="deletion_sets")return {count:snapshot.minimum_deletion_codes_by_subset[s].length,codes:snapshot.minimum_deletion_codes_by_subset[s]};
  fail("cut kind must be all, optimal or deletion_sets");
 }
 function costAt(s,code){return parseInt(snapshot.cut_cost_hex_by_subset[s].slice(2*code,2*code+2),16);}
 function cutRecord(s,code){
  const a=maskFromCode(s,code),b=s^a,cost=costAt(s,code),deleted=[],kept=[];
  graph.edges.forEach(([u,v],id)=>{
   work.witness_edge_inspections++;const bits=(1<<u)|(1<<v);if((s&bits)!==bits)return;
   if(Boolean(a&(1<<u))===Boolean(a&(1<<v)))deleted.push(id);else kept.push(id);
  });
  work.selected_witness_cost_checks++;if(deleted.length!==cost)fail("selected cut disagrees with graph witness");
  return {subset_mask:s,cut_code:code,A_mask:a,B_mask:b,
   A:vertices(a,n),B:vertices(b,n),deletions:cost,optimal:cost===snapshot.minimum_deletions_by_subset[s],
   canonical_minimum_deletion_representative:cost===snapshot.minimum_deletions_by_subset[s]&&
    (a&snapshot.component_anchor_mask_by_subset[s])===snapshot.component_anchor_mask_by_subset[s],
   deleted_edge_ids:deleted,deleted_edges:deleted.map(id=>graph.edges[id].slice()),
   kept_edge_ids:kept,kept_edge_count:kept.length};
 }
 function canonicalA(s,a,kind){
  if((a&s)!==a)fail("A must be a subset of the selected vertices");
  if(kind==="deletion_sets"){
   for(const c of snapshot.component_masks_by_subset[s])if((a&(c&-c))===0)a^=c;
  }else if(s&&(a&(s&-s))===0)a^=s;
  return a;
 }
 return Object.freeze({
  summary(){work.query_calls++;return {schema:SCHEMA,vertex_count:n,edge_count:graph.edge_count,
   coverage:copy(snapshot.coverage),full_graph:row(full),scope:snapshot.mathematical_scope};},
  graph(){work.query_calls++;return copy(graph);},
  profile(){work.query_calls++;return copy(snapshot.profile_by_size);},
  subset(subsetMask){work.query_calls++;const s=mask(subsetMask,"subset mask");work.subset_rows_returned++;return row(s);},
  subsetCount(query={}){work.query_calls++;const f=queryFamily(query);return {query:copy(f.query),count:f.ids.length,order:"increasing numeric subset mask"};},
  selectSubset(query,ordinal){work.query_calls++;const f=queryFamily(query),r=rank(ordinal,f.ids.length,"subset rank",false);
   work.subset_rows_returned++;return {query:copy(f.query),rank:r,subset:row(f.ids[r])};},
  rankSubset(query,subsetMask){work.query_calls++;const f=queryFamily(query),s=mask(subsetMask,"subset mask"),r=search(f.ids,s),
   found=r<f.ids.length&&f.ids[r]===s;
   return {query:copy(f.query),subset_mask:s,found,rank:found?r:null,insertion_rank:r};},
  pageSubsets(query={},start=0,count=64){
   work.query_calls++;const f=queryFamily(query),s=rank(start,f.ids.length,"subset page start",true),
    end=Math.min(f.ids.length,s+pageLimit(count));work.subset_rows_returned+=end-s;
   return {query:copy(f.query),total:f.ids.length,start:s,
    rows:f.ids.slice(s,end).map((id,j)=>({rank:s+j,subset:row(id)})),next:end<f.ids.length?end:null};
  },
  cutHistogram(subsetMask){work.query_calls++;const s=mask(subsetMask,"subset mask");
   return {subset_mask:s,canonical_vertex_bipartition_count:cutCountFromSize(sizes[s]),
    histogram:snapshot.cut_cost_histogram_by_subset[s].map((count,deletions)=>({deletions,count}))};},
  cutCount(subsetMask,kind="optimal"){work.query_calls++;const s=mask(subsetMask,"subset mask"),f=family(s,kind);
   return {subset_mask:s,kind,count:f.count};},
  selectCut(subsetMask,ordinal,kind="optimal"){
   work.query_calls++;const s=mask(subsetMask,"subset mask"),f=family(s,kind),
    r=rank(ordinal,f.count,"cut rank",false),code=f.codes?f.codes[r]:r;
   work.cut_rows_returned++;return {kind,rank:r,cut:cutRecord(s,code)};
  },
  rankCut(subsetMask,A,kind="optimal"){
   work.query_calls++;const s=mask(subsetMask,"subset mask"),f=family(s,kind),
    original=mask(A,"A mask"),a=canonicalA(s,original,kind),code=codeFromMask(s,a),
    r=f.codes?search(f.codes,code):code,found=!f.codes||(r<f.count&&f.codes[r]===code);
   return {subset_mask:s,kind,original_A_mask:original,normalized_A_mask:a,
    normalized_B_mask:s^a,cut_code:code,deletions:costAt(s,code),found,rank:found?r:null,insertion_rank:r};
  },
  pageCuts(subsetMask,start=0,count=64,kind="optimal"){
   work.query_calls++;const s=mask(subsetMask,"subset mask"),f=family(s,kind),
    r=rank(start,f.count,"cut page start",true),end=Math.min(f.count,r+pageLimit(count));
   work.cut_rows_returned+=end-r;
   return {subset_mask:s,kind,total:f.count,start:r,
    rows:Array.from({length:end-r},(_,j)=>({rank:r+j,cut:cutRecord(s,f.codes?f.codes[r+j]:r+j)})),
    next:end<f.count?end:null};
  },
  budgetReport(bounds){
   work.query_calls++;if(!Array.isArray(bounds)||bounds.length!==n+1)fail("one integer budget per size 0..vertex_count required");
   bounds.forEach(x=>integer(x,0,Number.MAX_SAFE_INTEGER,"deletion budget"));
   const violations=[];let badSubsets=0;
   for(const p of snapshot.profile_by_size){
    work.budget_profile_rows_inspected++;const b=bounds[p.size];let count=0;
    for(let d=b+1;d<p.minimum_distribution.length;d++)count+=p.minimum_distribution[d];
    badSubsets+=count;
    if(count)violations.push({size:p.size,budget:b,maximum_minimum:p.maximum_minimum,
     excess:p.maximum_minimum-b,counterexample_subset_count:count,first_maximizer_mask:p.maximizer_masks[0]});
   }
   return {bounds:bounds.slice(),all_finite_host_subgraphs_within_budget:violations.length===0,
    counterexample_subset_count:badSubsets,violations,
    scope:"only subgraphs of this finite host, for sizes 0..vertex_count; no infinite-graph conclusion"};
  },
  snapshot(){return copy(snapshot);},
  work(){return copy(work);}
 });
}
module.exports={mycielskiGraph,compileLocalBipartization,openRetainedLocalBipartization,LOCAL_BIPARTIZATION_LIMITS};
