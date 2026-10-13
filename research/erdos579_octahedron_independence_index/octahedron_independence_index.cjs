"use strict";
const SCHEMA="commons.octahedron_independence_index/v1";
const copy=x=>JSON.parse(JSON.stringify(x));
function pop(x){let n=0;for(;x;x&=x-1)n++;return n;}
function integer(x){if(typeof x==="number"&&!Number.isSafeInteger(x))throw Error("unsafe integer");try{return BigInt(x);}catch(_){throw Error("integer");}}
function compile(input) {
  const n=input.vertices,E=input.edges,S=input.subsets,Z=input.degree_zero_bits;
  if(n!==6||E.length!==15||S.length!==64||Z.length!==32768)throw Error("six-vertex premise required");
  const work={pairing_nodes:0,partitions:0,pattern_edge_checks:0,graph_rows:0,edge_popcount_steps:0,copy_tests:0,independent_bit_reads:0,independent_size_reads:0,profile_insertions:0,old_graph_enumeration:0,old_adjacency:0,old_induced_degrees:0,old_regularity:0};
  const patterns=[];
  function pair(rest,parts) {
    work.pairing_nodes++;
    if(!rest.length) {
      const labels=Array(6);parts.forEach((part,i)=>part.forEach(v=>labels[v]=i));
      const required=[],optional=[];let edge_mask=0;
      E.forEach(([u,v],id)=>{work.pattern_edge_checks++;if(labels[u]!==labels[v]){required.push(id);edge_mask+=2**id;}else optional.push(id);});
      patterns.push({id:patterns.length,parts:copy(parts),required_edges:required,optional_edges:optional,edge_mask});work.partitions++;return;
    }
    const x=rest[0];for(let j=1;j<rest.length;j++)pair(rest.filter((_,k)=>k!==0&&k!==j),parts.concat([[x,rest[j]]]));
  }
  pair([0,1,2,3,4,5],[]);
  const rows=[],groups=new Map();
  for(let graph=0;graph<Z.length;graph++) {
    let e=0;for(let x=graph;x;x&=x-1){e++;work.edge_popcount_steps++;}
    let bits=0,count=0;for(const p of patterns){work.copy_tests++;if((graph&p.edge_mask)===p.edge_mask){bits+=2**p.id;count++;}}
    const independent=BigInt("0x"+Z[graph]);let alpha=-1,number=0,best=0n;
    for(let mask=0;mask<64;mask++){work.independent_bit_reads++;if(((independent>>BigInt(mask))&1n)===0n)continue;work.independent_size_reads++;const k=S[mask].size;if(k>alpha){alpha=k;number=1;best=1n<<BigInt(mask);}else if(k===alpha){number++;best|=1n<<BigInt(mask);}}
    rows.push([e,alpha,number,best.toString(16),bits,count]);work.graph_rows++;
    const key=e+","+alpha+","+count;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(graph);work.profile_insertions++;
  }
  const profiles=[...groups].map(([key,graphs])=>{const[edges,alpha,copies]=key.split(",").map(Number);return{edges,alpha,copies,count:graphs.length,graphs};}).sort((a,b)=>a.edges-b.edges||a.alpha-b.alpha||a.copies-b.copies).map((p,id)=>({id,...p}));
  const free=profiles.filter(p=>p.copies===0),copy_distribution=[];
  for(const p of profiles){copy_distribution[p.copies]=(copy_distribution[p.copies]||0)+p.count;}
  const frontier=[];for(let threshold=0;threshold<=16;threshold++){const q=free.filter(p=>p.edges>=threshold),count=q.reduce((s,p)=>s+p.count,0),alpha=q.length?Math.min(...q.map(p=>p.alpha)):null;frontier.push({minimum_edges:threshold,graphs:count,minimum_alpha:alpha,attaining_graphs:q.filter(p=>p.alpha===alpha).reduce((s,p)=>s+p.count,0)});}
  return{schema:SCHEMA,input:copy(input),patterns,rows,profiles,frontier,summary:{graphs:rows.length,partitions:patterns.length,profiles:profiles.length,octahedron_free:free.reduce((s,p)=>s+p.count,0),maximum_free_edges:Math.max(...free.map(p=>p.edges)),copy_distribution:Array.from({length:copy_distribution.length},(_,i)=>copy_distribution[i]||0)},work};
}
function openIndex(data,retainedCaches=[]) {
  if(data.schema!==SCHEMA||data.rows.length!==32768)throw Error("saved six-vertex index");
  const R=data.rows,P=data.patterns,G=data.profiles,E=data.input.edges,S=data.input.subsets,C=new Map(retainedCaches.map(c=>[c.key,c]));
  const work={families_built:0,profile_scans:0,graph_mask_scans:0,condition_bit_checks:0,cumulative_additions:0,cache_hits:0,binary_steps:0,graph_record_reads:0,edge_decode_checks:0,maximum_witness_bit_reads:0,copy_bit_reads:0,threshold_divisions:0,new_oct_pattern:0,new_copy_test:0,new_independence_maximum:0};
  function ids(x){if(x===undefined)return[];if(!Array.isArray(x))throw Error("edge list");const a=[...x].sort((a,b)=>a-b);if(a.some((v,i)=>!Number.isInteger(v)||v<0||v>=15||(i&&v===a[i-1])))throw Error("distinct edge IDs");return a;}
  function options(o={}) {
    const q={min_edges:o.min_edges??0,max_edges:o.max_edges??15,min_alpha:o.min_alpha??0,max_alpha:o.max_alpha??6,min_copies:o.min_copies??0,max_copies:o.max_copies??15,require:ids(o.require),forbid:ids(o.forbid)};
    for(const k of ["min_edges","max_edges","min_alpha","max_alpha","min_copies","max_copies"])if(!Number.isSafeInteger(q[k])||q[k]<0)throw Error("nonnegative integer bound");
    return q;
  }
  function family(o={}) {
    const q=options(o),key=JSON.stringify(q);if(C.has(key)){work.cache_hits++;return C.get(key);}work.families_built++;
    const req=q.require.reduce((s,x)=>s+2**x,0),ban=q.forbid.reduce((s,x)=>s+2**x,0),segments=[];let count=0;
    if((req&ban)===0)for(const p of G){work.profile_scans++;if(p.edges<q.min_edges||p.edges>q.max_edges||p.alpha<q.min_alpha||p.alpha>q.max_alpha||p.copies<q.min_copies||p.copies>q.max_copies)continue;
      let indices=null,n=p.count;if(req||ban){indices=[];for(let i=0;i<p.graphs.length;i++){const g=p.graphs[i];work.graph_mask_scans++;work.condition_bit_checks+=2;if((g&req)===req&&(g&ban)===0)indices.push(i);}n=indices.length;}
      if(n){segments.push({profile:p.id,start:count,count:n,indices});count+=n;work.cumulative_additions++;}
    }
    const f={key,options:q,count,segments};C.set(key,f);return f;
  }
  function graph(g) {
    if(!Number.isInteger(g)||!R[g])throw RangeError("graph mask");work.graph_record_reads++;const r=R[g],edges=[],maximum=[],copies=[];
    E.forEach((e,i)=>{work.edge_decode_checks++;if(g&2**i)edges.push({id:i,endpoints:e.slice()});});
    const b=BigInt("0x"+r[3]);for(let s=0;s<64;s++){work.maximum_witness_bit_reads++;if((b>>BigInt(s))&1n)maximum.push(copy(S[s]));}
    for(const p of P){work.copy_bit_reads++;if(r[4]&2**p.id)copies.push(p.id);}
    return{graph:g,edge_count:r[0],density:{numerator:r[0],denominator:36},alpha:r[1],maximum_independent_count:r[2],maximum_independent_sets:maximum,octahedron_count:r[5],octahedron_ids:copies,edges};
  }
  function lower(a,x){let l=0,h=a.length;while(l<h){work.binary_steps++;const m=(l+h)>>1;if(a[m]<x)l=m+1;else h=m;}return l;}
  function count(o={}){const f=family(o);return{options:f.options,count:f.count,profiles:f.segments.length};}
  function select(rank,o={}) {
    const rr=integer(rank),f=family(o);if(rr<0n||rr>=BigInt(f.count))throw RangeError("rank");const r=Number(rr);let lo=0,hi=f.segments.length;while(lo+1<hi){work.binary_steps++;const m=(lo+hi)>>1;if(f.segments[m].start<=r)lo=m;else hi=m;}
    const s=f.segments[lo],p=G[s.profile],k=r-s.start,i=s.indices?s.indices[k]:k;return{rank:r,total:f.count,options:f.options,profile:p.id,...graph(p.graphs[i])};
  }
  function rank(g,o={}) {
    if(!Number.isInteger(g)||!R[g])throw RangeError("graph");const r=R[g],p=G.find(p=>p.edges===r[0]&&p.alpha===r[1]&&p.copies===r[5]),f=family(o),s=f.segments.find(s=>s.profile===p.id);
    if(!s)return{member:false,graph:g,reason:"profile filter"};const i=lower(p.graphs,g),j=s.indices?lower(s.indices,i):i;if(p.graphs[i]!==g||(s.indices&&s.indices[j]!==i))return{member:false,graph:g,reason:"edge condition"};
    return{member:true,graph:g,rank:s.start+j,total:f.count,options:f.options,profile:p.id};
  }
  function page(start,limit,o={}) {
    const s=integer(start),f=family(o);if(s<0n||s>BigInt(f.count)||!Number.isInteger(limit)||limit<0||limit>1000)throw RangeError("page");const records=[];for(let i=Number(s);i<f.count&&records.length<limit;i++)records.push(select(i,o));return{start:Number(s),count:f.count,records,next:Number(s)+records.length<f.count?Number(s)+records.length:null};
  }
  function threshold(numerator,denominator) {
    const a=integer(numerator),b=integer(denominator);if(a<0n||b<=0n)throw Error("nonnegative rational density");const k=(36n*a+b-1n)/b;work.threshold_divisions++;
    const q=k>16n?16:Number(k),f=data.frontier[q];return{density:{numerator:a.toString(),denominator:b.toString()},required_edges:k.toString(),saved_threshold_row:q,graphs:f.graphs,minimum_alpha:f.minimum_alpha,attaining_graphs:f.attaining_graphs,scope:"octahedron-free six-vertex graphs; normalization edges/36"};
  }
  return{summary:()=>copy(data.summary),profiles:()=>G.map(({graphs,...p})=>copy(p)),frontier:()=>copy(data.frontier),graph,count,select,rank,page,threshold,
    pattern:id=>{if(!Number.isInteger(id)||!P[id])throw RangeError("pattern");return copy(P[id]);},
    patterns:()=>copy(P),caches:()=>copy([...C.values()]),work:()=>copy(work)};
}
module.exports={compile,openIndex};
