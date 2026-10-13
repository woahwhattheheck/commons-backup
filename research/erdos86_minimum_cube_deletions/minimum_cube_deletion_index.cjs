"use strict";
// Complete minimum-cover family consumer. See MINIMUM_CUBE_DELETION_API.md.
const SCHEMA="commons.minimum_cube_deletion_index/v1";
const pop=x=>{let n=0;for(;x;x&=x-1)n++;return n;};
const has=(mask,i)=>Math.floor(mask/2**i)%2===1;
const clone=x=>JSON.parse(JSON.stringify(x));
function compile(input,limits={}) {
  const cap=Object.assign({states:100000,profile_cells:1000000},limits);
  const m=input.square_count, edges=input.edges, squares=input.squares;
  if(!Number.isInteger(m)||m<1||m>30||!Array.isArray(edges)||edges.length>52||!Array.isArray(squares)||squares.length!==m)throw Error("invalid finite incidence shape");
  if(!Number.isInteger(input.minimum_deleted_edges)||input.minimum_deleted_edges<1)throw Error("minimum premise required");
  const masks=edges.map((e,i)=>{
    if(e.id!==i||!Number.isInteger(e.direction)||e.direction<0||e.direction>=input.dimension)throw Error("edge labels");
    const x=Number(BigInt(e.square_mask));
    if(!Number.isSafeInteger(x)||x<1||x>=2**m)throw Error("edge incidence mask");
    return x;
  });
  for(let j=0;j<m;j++)if(squares[j].id!==j||!Array.isArray(squares[j].edge_ids)||squares[j].edge_ids.some(i=>!Number.isInteger(i)||i<0||i>=edges.length))throw Error("square labels");
  // Semantic agreement of the two supplied incidence views is an input premise.
  const arity=pop(masks[0]);
  if(masks.some(x=>pop(x)!==arity)||input.minimum_deleted_edges*arity!==m)throw Error("exact-capacity premise required");
  const work={states:0,arc_candidates:0,incidence_subset_checks:0,arcs:0,profile_cells:0,profile_additions:0,old_topology:0,old_optimizer:0,old_proofs:0};
  const nodes=[],memo=new Map();
  function visit(rem) {
    if(memo.has(rem))return memo.get(rem);
    if(nodes.length>=cap.states)throw Error("state cap");
    const id=nodes.length;memo.set(rem,id);nodes.push(null);work.states++;
    const profiles=new Map(),arcs=[];
    let square=null;
    if(rem===0)profiles.set(Array(input.dimension).fill(0).join(","),1n);
    else {
      square=31-Math.clz32(rem&-rem);
      for(const edge of [...squares[square].edge_ids].sort((a,b)=>a-b)) {
        work.arc_candidates++;work.incidence_subset_checks++;
        if((rem&masks[edge])!==masks[edge])continue;
        const child=visit(rem^masks[edge]);arcs.push({edge,child});work.arcs++;
        for(const row of nodes[child].profiles) {
          const p=row.profile.slice();p[edges[edge].direction]++;
          const k=p.join(",");profiles.set(k,(profiles.get(k)||0n)+BigInt(row.count));work.profile_additions++;
        }
      }
    }
    const rows=[...profiles].map(([k,n])=>({profile:k.split(",").map(Number),count:n.toString()})).sort((a,b)=>a.profile.join(",").localeCompare(b.profile.join(",")));
    work.profile_cells+=rows.length;if(work.profile_cells>cap.profile_cells)throw Error("profile cap");
    nodes[id]={id,remaining:rem,square,arcs,profiles:rows,count:rows.reduce((n,x)=>n+BigInt(x.count),0n).toString()};
    return id;
  }
  const root=visit(2**m-1);
  return {schema:SCHEMA,input:clone(input),order:"least uncovered square; increasing outgoing edge ID",caps:cap,root,nodes,summary:{total:nodes[root].count,minimum_deleted:input.minimum_deleted_edges,maximum_kept:edges.length-input.minimum_deleted_edges,direction_profiles:nodes[root].profiles},work};
}
function openIndex(data,retainedCaches=[]) {
  if(data.schema!==SCHEMA||!Array.isArray(data.nodes)||!data.nodes[data.root])throw Error("index shape");
  const E=data.input.edges,S=data.input.squares,N=data.nodes,D=data.input.dimension,cache=new Map();
  const work={conditions:0,condition_states:0,condition_arcs:0,base_count_reads:0,base_profile_reads:0,cache_hits:0,selection_steps:0,rank_steps:0,materialized_edges:0,square_assignments:0,vertex_degree_increments:0,new_incidence_construction:0,new_base_DAG:0,new_base_profiles:0};
  for(const c of retainedCaches)cache.set(c.key,{options:c.options,memo:new Map(c.entries)});
  function ids(a,label){if(a===undefined)return[];if(!Array.isArray(a))throw Error(label);const r=[...a].sort((a,b)=>a-b);if(r.some((x,i)=>!Number.isInteger(x)||x<0||x>=E.length||(i&&x===r[i-1])))throw Error(label);return r;}
  function opts(o={}) {
    const require=ids(o.require,"required edge IDs"),forbid=ids(o.forbid,"forbidden edge IDs");
    if(o.profile!==undefined&&!Array.isArray(o.profile))throw Error("direction profile");
    const profile=o.profile===undefined?null:o.profile.slice();
    if(profile&&(profile.length!==D||profile.some(x=>!Number.isInteger(x)||x<0)))throw Error("direction profile");
    const q={require,forbid,profile},key=JSON.stringify(q);
    if(!cache.has(key)){cache.set(key,{options:q,memo:new Map()});work.conditions++;}
    return {q,key,c:cache.get(key),req:require.reduce((s,i)=>s+2**i,0),forbid:forbid.reduce((s,i)=>s+2**i,0)};
  }
  function ways(ctx,id,req,p) {
    if(ctx.q.require.some(i=>has(ctx.forbid,i)))return 0n;
    if(p&&p.some(x=>x<0))return 0n;
    const n=N[id];
    if(req===0&&ctx.forbid===0) {
      if(!p){work.base_count_reads++;return BigInt(n.count);}
      work.base_profile_reads++;const r=n.profiles.find(x=>x.profile.every((v,i)=>v===p[i]));return r?BigInt(r.count):0n;
    }
    const key=id+"|"+req+"|"+(p?p.join(","):"*");
    if(ctx.c.memo.has(key)){work.cache_hits++;return BigInt(ctx.c.memo.get(key));}
    work.condition_states++;
    let total=0n;
    if(n.remaining===0)total=req===0&&(!p||p.every(x=>x===0))?1n:0n;
    else for(const a of n.arcs) {
      work.condition_arcs++;
      if(has(ctx.forbid,a.edge))continue;
      const next=p?p.slice():null;if(next)next[E[a.edge].direction]--;
      total+=ways(ctx,a.child,has(req,a.edge)?req-2**a.edge:req,next);
    }
    ctx.c.memo.set(key,total.toString());return total;
  }
  function count(o={}){const c=opts(o);return {options:c.q,count:ways(c,data.root,c.req,c.q.profile).toString()};}
  function materialize(selected,trace) {
    const sorted=selected.slice().sort((a,b)=>a-b),set=new Set(sorted),degrees=Array(data.input.vertex_count).fill(0),profile=Array(D).fill(0),hits=Array(S.length).fill(null);
    for(const i of sorted){const e=E[i];work.materialized_edges++;profile[e.direction]++;degrees[e.base]++;degrees[e.tip]++;work.vertex_degree_increments+=2;for(const s of e.square_ids){hits[s]=i;work.square_assignments++;}}
    return {deleted_edge_ids:sorted,kept_edge_ids:E.filter(e=>!set.has(e.id)).map(e=>e.id),direction_profile:profile,deleted_degrees:degrees,square_assignment:hits,trace};
  }
  function select(rank,o={}) {
    let r=BigInt(rank);const c=opts(o),total=ways(c,data.root,c.req,c.q.profile);
    if(r<0n||r>=total)throw RangeError("rank outside family");
    const original=r.toString(),selected=[],trace=[];let id=data.root,req=c.req,p=c.q.profile;
    while(N[id].remaining!==0) {
      let chosen=false;
      for(const a of N[id].arcs) {
        if(has(c.forbid,a.edge))continue;
        const next=p?p.slice():null;if(next)next[E[a.edge].direction]--;
        const rq=has(req,a.edge)?req-2**a.edge:req,w=ways(c,a.child,rq,next);work.selection_steps++;
        if(r>=w){r-=w;continue;}
        trace.push({node:id,square:N[id].square,edge:a.edge,child:a.child,branch_count:w.toString(),residual_rank:r.toString()});
        selected.push(a.edge);id=a.child;req=rq;p=next;chosen=true;break;
      }
      if(!chosen)throw Error("inconsistent saved family");
    }
    return {rank:original,total:total.toString(),options:c.q,...materialize(selected,trace)};
  }
  function rank(edgeIds,o={}) {
    const selected=ids(edgeIds,"deletion edge IDs"),set=new Set(selected),c=opts(o);
    if(selected.length!==data.input.minimum_deleted_edges)return {member:false,reason:"cardinality"};
    let id=data.root,req=c.req,p=c.q.profile,r=0n;const trace=[],used=new Set();
    while(N[id].remaining!==0) {
      let chosen=null;
      for(const a of N[id].arcs) {
        if(has(c.forbid,a.edge))continue;
        const next=p?p.slice():null;if(next)next[E[a.edge].direction]--;
        const rq=has(req,a.edge)?req-2**a.edge:req,w=ways(c,a.child,rq,next);work.rank_steps++;
        if(set.has(a.edge)){if(w===0n)return {member:false,reason:"condition or dead branch"};chosen={a,next,rq};break;}
        r+=w;
      }
      if(!chosen)return {member:false,reason:"no saved exact-cover branch"};
      const {a,next,rq}=chosen;used.add(a.edge);trace.push({node:id,edge:a.edge,child:a.child,prefix_rank:r.toString()});id=a.child;req=rq;p=next;
    }
    if(used.size!==selected.length||req!==0||(p&&p.some(x=>x!==0)))return {member:false,reason:"terminal condition"};
    return {member:true,rank:r.toString(),total:ways(c,data.root,c.req,c.q.profile).toString(),options:c.q,trace};
  }
  function page(start,limit,o={}) {
    if(!Number.isInteger(limit)||limit<0||limit>1000)throw RangeError("page limit");
    const total=BigInt(count(o).count),s=BigInt(start);if(s<0n||s>total)throw RangeError("page start");
    const out=[];for(let r=s;r<total&&out.length<limit;r++)out.push(select(r,o));
    return {start:s.toString(),total:total.toString(),records:out,next:s+BigInt(out.length)<total?(s+BigInt(out.length)).toString():null};
  }
  return {summary:()=>clone(data.summary),count,select,rank,page,
    edge:i=>{if(!Number.isInteger(i)||!E[i])throw RangeError("edge");return clone(E[i]);},
    square:i=>{if(!Number.isInteger(i)||!S[i])throw RangeError("square");return clone(S[i]);},
    node:i=>{if(!Number.isInteger(i)||!N[i])throw RangeError("node");return clone(N[i]);},
    caches:()=>[...cache].map(([key,c])=>({key,options:c.options,entries:[...c.memo]})),
    work:()=>clone(work)};
}
module.exports={compile,openIndex};
