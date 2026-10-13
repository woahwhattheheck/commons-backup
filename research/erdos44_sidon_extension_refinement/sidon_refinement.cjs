"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
function integer(x,n,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(n);return x;}
function add(low,high){const c=Array(Math.max(low.length,high.length+1)).fill(0n);for(let i=0;i<low.length;i++)c[i]+=low[i];for(let i=0;i<high.length;i++)c[i+1]+=high[i];while(c.length&&c.at(-1)===0n)c.pop();return c;}
function shape(base){
 const N=integer(base.N,"host N",3,24);
 if(base.schema!=="b2-two-family/v1"||base.g!==2||base.order.length!==N||base.order.some((x,i)=>x!==i+1)||base.fibers.length!==2*N-1||base.nodes.length<2||base.nodes.length>300000)throw new Error("base shape");
 if(base.nodes[0].coefficients.length||base.nodes[1].coefficients.join(",")!=="1")throw new Error("terminals");
 for(let i=0;i<base.nodes.length;i++){const n=base.nodes[i];if(n.id!==i||!Array.isArray(n.coefficients)||n.coefficients.some(x=>typeof x!=="string"||!/^\d+$/.test(x)))throw new Error("base coefficients");
 if(i<2){if(n.v!==N||n.lo!==null||n.hi!==null)throw new Error("terminal shape");}
 else if(!Number.isSafeInteger(n.v)||n.v<0||n.v>=N||!Number.isSafeInteger(n.lo)||!Number.isSafeInteger(n.hi)||n.lo<0||n.hi<=0||n.lo>=i||n.hi>=i||base.nodes[n.lo].v<=n.v||base.nodes[n.hi].v<=n.v)throw new Error("base DAG");}
 integer(base.root,"base root",1,base.nodes.length-1);return N;
}
function refine(base,input){
 const N=shape(base),lim=input.limits;
 if(!lim||lim.max_N!==24||lim.max_new_states!==200000||lim.max_new_coefficient_cells!==1000000)throw new Error("explicit limits required");
 const work={new_pair_sums:0,new_old_triple_obstructions:0,new_base_coefficients:0,
  saved_nodes:base.nodes.length,saved_coefficients:base.nodes.reduce((a,n)=>a+n.coefficients.length,0),
  saved_pair_records:0,two_pair_witnesses:0,distinct_constraints:0,new_states:0,memo_hits:0,
  skipped_constraint_drops:0,unchanged_subgraph_returns:0,zero_high_reductions:0,
  old_node_reuses:0,new_unique_hits:0,new_nodes:0,new_coefficient_cells:0};
 const witnesses=[],set=new Set();
 for(let fi=0;fi<base.fibers.length;fi++){
  const f=base.fibers[fi];if(f.sum!==fi+2||!Array.isArray(f.pairs)||f.pairs.length>N)throw new Error("fiber shape");
  for(const p of f.pairs){integer(p.a,"pair a",1,N);integer(p.b,"pair b",p.a,N);if(p.mask!==((2**(p.a-1))|(2**(p.b-1))))throw new Error("pair mask");work.saved_pair_records++;}
  for(let a=0;a<f.pairs.length;a++)for(let b=a+1;b<f.pairs.length;b++){
   const p=f.pairs[a],q=f.pairs[b],mask=p.mask|q.mask;
   witnesses.push({id:witnesses.length,sum:f.sum,pairs:[[p.a,p.b],[q.a,q.b]],mask});
   set.add(mask);work.two_pair_witnesses++;
  }
 }
 const constraints=[...set].sort((a,b)=>a-b);work.distinct_constraints=constraints.length;
 const nodes=base.nodes.slice(),polys=nodes.map(n=>n.coefficients.map(BigInt)),unique=new Map(),memo=new Map();
 for(let i=2;i<nodes.length;i++){const n=nodes[i];unique.set(n.v+","+n.lo+","+n.hi,i);}
 function node(v,lo,hi){
  if(hi===0){work.zero_high_reductions++;return lo;}
  const key=v+","+lo+","+hi;if(unique.has(key)){const id=unique.get(key);if(id<base.nodes.length)work.old_node_reuses++;else work.new_unique_hits++;return id;}
  const p=add(polys[lo],polys[hi]);if(work.new_coefficient_cells+p.length>lim.max_new_coefficient_cells)throw new Error("new coefficient cap");
  work.new_coefficient_cells+=p.length;const id=nodes.length;
  nodes.push({id,v,lo,hi,coefficients:p.map(String)});polys.push(p);unique.set(key,id);work.new_nodes++;return id;
 }
 function solve(id,from,edges){
  if(id===0)return 0;
  const v=nodes[id].v,skipped=(2**v-1)^(2**from-1),rest=edges.filter(e=>(e&skipped)===0);
  work.skipped_constraint_drops+=edges.length-rest.length;
  if(rest.length===0){work.unchanged_subgraph_returns++;return id;}
  if(id===1)throw new Error("unresolved terminal constraints");
  const key=id+":"+rest.join(",");if(memo.has(key)){work.memo_hits++;return memo.get(key);}
  if(++work.new_states>lim.max_new_states)throw new Error("new state cap");
  const bit=2**v,loEdges=rest.filter(e=>(e&bit)===0),
   hiEdges=[...new Set(rest.map(e=>e&~bit))].sort((a,b)=>a-b);
  const n=nodes[id],lo=solve(n.lo,v+1,loEdges),hi=hiEdges.includes(0)?0:solve(n.hi,v+1,hiEdges),out=node(v,lo,hi);
  memo.set(key,out);return out;
 }
 const root=solve(base.root,0,constraints),p=polys[root];
 return {schema:"sidon-refinement-delta/v1",N,g:1,order:base.order.slice(),base:clone(input.base),
  base_node_count:base.nodes.length,base_root:base.root,witnesses,constraints,
  delta_nodes:nodes.slice(base.nodes.length),root,coefficients:p.map(String),
  total:String(p.reduce((a,b)=>a+b,0n)),maximum_size:p.length-1,maximum_count:String(p.at(-1)),
  seed:clone(input.seed),provenance:clone(input.provenance),limits:clone(lim),work};
}
function openIndex(base,delta){
 const N0=shape(base);
 if(delta.schema!=="sidon-refinement-delta/v1"||delta.N!==N0||delta.base_node_count!==base.nodes.length||delta.base_root!==base.root)throw new Error("delta/base shape");
 const snapshot={...delta,nodes:base.nodes.concat(delta.delta_nodes),fibers:base.fibers,pair_count:base.pair_count,obstructions:delta.witnesses};

 const S=clone(snapshot),N=S.N;
 integer(N,"saved N",3,24);if(S.schema!=="sidon-refinement-delta/v1"||S.g!==1||S.order.length!==N||S.nodes.length<2)throw new Error("saved shape");
 const pos=new Map(S.order.map((v,i)=>[v,i]));if(pos.size!==N||S.order.some(v=>!Number.isSafeInteger(v)||v<1||v>N))throw new Error("saved permutation");
 const polys=S.nodes.map((n,i)=>{if(n.id!==i||!Array.isArray(n.coefficients))throw new Error("saved node shape");if(i>=2&&(!Number.isSafeInteger(n.v)||n.v<0||n.v>=N||n.lo>=i||n.hi>=i||n.lo<0||n.hi<0||S.nodes[n.lo].v<=n.v||S.nodes[n.hi].v<=n.v))throw new Error("saved DAG order");return n.coefficients.map(x=>{if(typeof x!=="string"||!/^\d+$/.test(x))throw new Error("saved coefficient");return BigInt(x);});});
 const work={queries:0,conditions:0,cache_hits:0,conditional_nodes:0,conditional_coefficient_cells:0,saved_polynomial_shortcuts:0,skipped_required_rejections:0,selection_steps:0,rank_steps:0,pair_membership_checks:0,fiber_reads:0,extension_candidates:0,new_constructor_states:0,new_pair_sums:0,new_constraints:0,new_base_coefficients:0,new_refinement_states:0,new_two_pair_obstructions:0};
 const cache=new Map();
 function labels(a=[]){if(!Array.isArray(a))throw new Error("labels array");const out=[...new Set(a.map(v=>integer(v,"label",1,N)))].sort((a,b)=>a-b);if(out.length!==a.length)throw new Error("duplicate label");return out;}
 function condition(q={}){
  const required=labels(q.required),forbidden=labels(q.forbidden);if(required.some(v=>forbidden.includes(v)))throw new Error("required/forbidden overlap");const key=JSON.stringify([required,forbidden]);if(cache.has(key)){work.cache_hits++;return cache.get(key);}if(cache.size>=32)throw new Error("32-condition cap");
  const req=Array(N).fill(false),ban=Array(N).fill(false);required.forEach(v=>req[pos.get(v)]=true);forbidden.forEach(v=>ban[pos.get(v)]=true);
  const pref=[0],con=[0];for(let i=0;i<N;i++){pref.push(pref[i]+Number(req[i]));con.push(con[i]+Number(req[i]||ban[i]));}
  const memo=new Map();
  function edge(id,from){const v=S.nodes[id].v;if(pref[v]>pref[from]){work.skipped_required_rejections++;return [];}return evaluate(id);}
  function evaluate(id){if(id<2)return polys[id];const n=S.nodes[id];if(con[N]===con[n.v]){work.saved_polynomial_shortcuts++;return polys[id];}if(memo.has(id))return memo.get(id);
   const low=req[n.v]?[]:edge(n.lo,n.v+1),high=ban[n.v]?[]:edge(n.hi,n.v+1),p=add(low,high);if(work.conditional_coefficient_cells+p.length>1000000)throw new Error("reader coefficient cap");work.conditional_coefficient_cells+=p.length;work.conditional_nodes++;memo.set(id,p);return p;
  }
  const p=edge(S.root,0),c={required,forbidden,req,ban,pref,edge,poly:p};cache.set(key,c);work.conditions++;return c;
 }
 const mass=(p,k)=>k===null?p.reduce((a,b)=>a+b,0n):(p[k]??0n);
 function size(q){return q.size===undefined?null:integer(q.size,"size",0,N);}
 function describe(c,k){return {condition:{required:c.required,forbidden:c.forbidden},size:k,count:String(mass(c.poly,k)),coefficients:c.poly.map(String),maximum_size:c.poly.length?c.poly.length-1:null,maximum_count:c.poly.length?String(c.poly.at(-1)):"0"};}
 function select(c,k,rank){
  if(typeof rank!=="string"||!/^\d+$/.test(rank))throw new Error("decimal rank");let r=BigInt(rank);if(r>=mass(c.poly,k))throw new RangeError("rank");const values=[];let id=S.root,remaining=k;
  while(id>=2){const n=S.nodes[id];work.selection_steps++;const low=c.req[n.v]?[]:c.edge(n.lo,n.v+1),m=mass(low,remaining);
   if(r<m)id=n.lo;else{r-=m;if(c.ban[n.v])throw new Error("forbidden selection");values.push(S.order[n.v]);if(remaining!==null)remaining--;id=n.hi;}
  }
  if(id!==1||r!==0n||(remaining!==null&&remaining!==0))throw new Error("selection terminal");
  return {rank,values:values.sort((a,b)=>a-b),size:values.length};
 }
 function rank(c,k,values){const xs=labels(values),bits=Array(N).fill(false);xs.forEach(v=>bits[pos.get(v)]=true);if(k!==null&&k!==xs.length)return {member:false,rank:null};if(c.required.some(v=>!xs.includes(v))||c.forbidden.some(v=>xs.includes(v)))return {member:false,rank:null};
  let id=S.root,from=0,r=0n,remaining=k;while(id>=2){const n=S.nodes[id];work.rank_steps++;if(bits.slice(from,n.v).some(Boolean))return {member:false,rank:null};
   if(bits[n.v]){const low=c.req[n.v]?[]:c.edge(n.lo,n.v+1);r+=mass(low,remaining);if(remaining!==null)remaining--;id=n.hi;}else id=n.lo;from=n.v+1;
  }
  if(id!==1||bits.slice(from).some(Boolean)||(remaining!==null&&remaining!==0))return {member:false,rank:null};return {member:true,rank:String(r)};
 }
 function classify(values){
  const xs=labels(values),set=new Set(xs);let maximum=0,violation=null;const fibers=[];
  for(const f of S.fibers){
   const active=[];
   for(const p of f.pairs){work.pair_membership_checks++;if(set.has(p.a)&&set.has(p.b))active.push([p.a,p.b]);}
   if(active.length){fibers.push({sum:f.sum,count:active.length,pairs:active});maximum=Math.max(maximum,active.length);}
   if(!violation&&active.length>1)violation={sum:f.sum,pairs:active.slice(0,2)};
  }
  return {values:xs,member:violation===null,maximum_multiplicity:maximum,violation,fibers};
 }
 function extension(e){
  if(!e||typeof e!=="object")throw new Error("extension required");
  const n=integer(e.N,"seed interval N",1,N-1),m=integer(e.M,"extension M",n+1,N),seed=labels(e.seed);
  if(seed.some(v=>v>n))throw new Error("seed outside old interval");
  const forbidden=S.order.filter(v=>(v<=n&&!seed.includes(v))||v>m);
  return {N:n,M:m,seed,condition:{required:seed,forbidden}};
 }
 function query(q){work.queries++;let out;
  if(q.op==="summary")out={N,g:1,base_nodes:S.base_node_count,delta_nodes:S.delta_nodes.length,nodes:S.nodes.length,pairs:S.pair_count,obstructions:S.obstructions.length,
    distinct_obstruction_masks:S.constraints.length,total:S.total,maximum_size:S.maximum_size,
    maximum_count:S.maximum_count,order:S.order,construction_work:S.work};
  else if(q.op==="classify")out=classify(q.values);
  else if(q.op==="extensions"){
   const spec=extension(q.extension),baseResult=classify(spec.seed);
   const allowed=[],rejected=[];
   if(baseResult.member)for(let v=spec.N+1;v<=spec.M;v++){
    work.extension_candidates++;const next=classify([...spec.seed,v]);
    if(next.member)allowed.push(v);else rejected.push({value:v,violation:next.violation});
   }
   out={extension:spec,seed_member:baseResult.member,seed_violation:baseResult.violation,
     allowed:baseResult.member?allowed:null,rejected:baseResult.member?rejected:null};
  }
  else if(q.op==="fiber"){const sum=integer(q.sum,"sum",2,2*N);work.fiber_reads++;out=S.fibers[sum-2];}
  else if(q.op==="obstruction")out=S.obstructions[integer(q.id,"obstruction id",0,S.obstructions.length-1)];
  else if(q.op==="node")out=S.nodes[integer(q.id,"node id",0,S.nodes.length-1)];
  else if(q.op==="conditions")out=[...cache.values()].map(c=>describe(c,null));
  else{if(q.extension!==undefined&&q.condition!==undefined)throw new Error("choose extension or condition");const c=condition(q.extension===undefined?q.condition:extension(q.extension).condition),k=size(q);
   if(q.op==="family")out=describe(c,k);
   else if(q.op==="select")out=select(c,k,q.rank);
   else if(q.op==="rank")out=rank(c,k,q.values);
   else if(q.op==="page"){if(typeof q.offset!=="string"||!/^\d+$/.test(q.offset))throw new Error("decimal offset");const offset=BigInt(q.offset),total=mass(c.poly,k);if(offset>total)throw new RangeError("offset");const lim=integer(q.limit??20,"limit",0,256),rows=[];let at=offset;for(let j=0;j<lim&&at<total;j++,at++)rows.push(select(c,k,String(at)));out={total:String(total),offset:q.offset,next:at<total?String(at):null,rows};}
   else throw new Error("unknown operation");
  }return clone(out);
 }
 return {query,work:()=>clone(work)};
}

module.exports={refine,openIndex};
