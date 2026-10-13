"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
function integer(x,n,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(n);return x;}
function add(low,high){const c=Array(Math.max(low.length,high.length+1)).fill(0n);for(let i=0;i<low.length;i++)c[i]+=low[i];for(let i=0;i<high.length;i++)c[i+1]+=high[i];while(c.length&&c.at(-1)===0n)c.pop();return c;}
function compile(input){
 const N=integer(input.N,"N",3,128),lim=input.limits;
 if(!lim||lim.max_N!==128||lim.max_component_vertices!==24||lim.max_states!==200000||lim.max_coefficient_cells!==2000000)throw new Error("fixed constructor limits required");
 const work={factor_divisions:0,constraints:0,new_states:0,memo_hits:0,nodes:0,coefficient_cells:0,unique_node_hits:0,zero_high_reductions:0};
 const groups=new Map(),cores=Array(N+1).fill(0);
 for(let n=1;n<=N;n++){let c=n;while(c%2===0){c/=2;work.factor_divisions++;}while(c%3===0){c/=3;work.factor_divisions++;}cores[n]=c;if(!groups.has(c))groups.set(c,[]);groups.get(c).push(n);}
 const order=[],components=[...groups].sort((a,b)=>a[0]-b[0]).map(([core,vertices],id)=>{if(vertices.length>24)throw new Error("component cap");const first=order.length;order.push(...vertices);return {id,core,vertices,first_variable:first,local_constraints:[],root:null,tail_root:null};});
 const pos=new Map(order.map((x,i)=>[x,i])),compByCore=new Map(components.map(c=>[c.core,c])),constraints=[];
 for(let n=1;3*n<=N;n++){const triple=[n,2*n,3*n],c=compByCore.get(cores[n]);if(cores[2*n]!==c.core||cores[3*n]!==c.core)throw new Error("component premise");const local=triple.reduce((mask,v)=>mask|2**(pos.get(v)-c.first_variable),0);c.local_constraints.push(local);constraints.push(triple);work.constraints++;}
 const nodes=[{id:0,v:N,lo:null,hi:null},{id:1,v:N,lo:null,hi:null}],polys=[[],[1n]],unique=new Map();
 function node(v,lo,hi){if(hi===0){work.zero_high_reductions++;return lo;}const key=v+","+lo+","+hi;if(unique.has(key)){work.unique_node_hits++;return unique.get(key);}
  const p=add(polys[lo],polys[hi]);if(work.coefficient_cells+p.length>lim.max_coefficient_cells)throw new Error("coefficient cap");work.coefficient_cells+=p.length;
  const id=nodes.length;nodes.push({id,v,lo,hi});polys.push(p);unique.set(key,id);work.nodes++;return id;
 }
 let root=1;
 for(let ci=components.length-1;ci>=0;ci--){const c=components[ci],memo=new Map(),tail=root;c.tail_root=tail;
  function solve(i,edges){const key=i+":"+edges.join(",");if(memo.has(key)){work.memo_hits++;return memo.get(key);}if(++work.new_states>lim.max_states)throw new Error("state cap");
   if(i===c.vertices.length){if(edges.length)throw new Error("terminal constraints");memo.set(key,tail);return tail;}
   const bit=2**i,loEdges=edges.filter(e=>(e&bit)===0),hiEdges=[...new Set(edges.map(e=>e&~bit))].sort((a,b)=>a-b);
   const lo=solve(i+1,loEdges),hi=hiEdges.includes(0)?0:solve(i+1,hiEdges),out=node(c.first_variable+i,lo,hi);memo.set(key,out);return out;
  }
  root=solve(0,c.local_constraints.slice().sort((a,b)=>a-b));c.root=root;c.memo_states=memo.size;
 }
 const serial=nodes.map((n,i)=>({...n,coefficients:polys[i].map(String)})),p=polys[root];
 return {schema:"dilated-triple-family/v1",N,order,core_by_value:cores,components,constraints,nodes:serial,root,total:String(p.reduce((a,b)=>a+b,0n)),maximum_size:p.length-1,maximum_count:String(p.at(-1)),provenance:clone(input.provenance),limits:clone(lim),work};
}
function openIndex(snapshot){
 const S=clone(snapshot),N=S.N;
 integer(N,"saved N",3,128);if(S.schema!=="dilated-triple-family/v1"||S.order.length!==N||S.nodes.length<2)throw new Error("saved shape");
 const pos=new Map(S.order.map((v,i)=>[v,i]));if(pos.size!==N||S.order.some(v=>!Number.isSafeInteger(v)||v<1||v>N))throw new Error("saved permutation");
 const polys=S.nodes.map((n,i)=>{if(n.id!==i||!Array.isArray(n.coefficients))throw new Error("saved node shape");if(i>=2&&(!Number.isSafeInteger(n.v)||n.v<0||n.v>=N||n.lo>=i||n.hi>=i||n.lo<0||n.hi<0||S.nodes[n.lo].v<=n.v||S.nodes[n.hi].v<=n.v))throw new Error("saved DAG order");return n.coefficients.map(x=>{if(typeof x!=="string"||!/^\d+$/.test(x))throw new Error("saved coefficient");return BigInt(x);});});
 const work={queries:0,conditions:0,cache_hits:0,conditional_nodes:0,conditional_coefficient_cells:0,saved_polynomial_shortcuts:0,skipped_required_rejections:0,selection_steps:0,rank_steps:0,constraint_checks:0,new_constructor_states:0,new_factor_divisions:0,new_constraints:0,new_base_coefficients:0};
 const cache=new Map();
 function labels(a=[]){if(!Array.isArray(a))throw new Error("labels array");const out=[...new Set(a.map(v=>integer(v,"label",1,N)))].sort((a,b)=>a-b);if(out.length!==a.length)throw new Error("duplicate label");return out;}
 function condition(q={}){
  const required=labels(q.required),forbidden=labels(q.forbidden);if(required.some(v=>forbidden.includes(v)))throw new Error("required/forbidden overlap");const key=JSON.stringify([required,forbidden]);if(cache.has(key)){work.cache_hits++;return cache.get(key);}if(cache.size>=16)throw new Error("16-condition cap");
  const req=Array(N).fill(false),ban=Array(N).fill(false);required.forEach(v=>req[pos.get(v)]=true);forbidden.forEach(v=>ban[pos.get(v)]=true);
  const pref=[0],con=[0];for(let i=0;i<N;i++){pref.push(pref[i]+Number(req[i]));con.push(con[i]+Number(req[i]||ban[i]));}
  const memo=new Map();
  function edge(id,from){const v=S.nodes[id].v;if(pref[v]>pref[from]){work.skipped_required_rejections++;return [];}return evaluate(id);}
  function evaluate(id){if(id<2)return polys[id];const n=S.nodes[id];if(con[N]===con[n.v]){work.saved_polynomial_shortcuts++;return polys[id];}if(memo.has(id))return memo.get(id);
   const low=req[n.v]?[]:edge(n.lo,n.v+1),high=ban[n.v]?[]:edge(n.hi,n.v+1),p=add(low,high);if(work.conditional_coefficient_cells+p.length>500000)throw new Error("reader coefficient cap");work.conditional_coefficient_cells+=p.length;work.conditional_nodes++;memo.set(id,p);return p;
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
 function query(q){work.queries++;let out;
  if(q.op==="summary")out={N,nodes:S.nodes.length,components:S.components.length,constraints:S.constraints.length,total:S.total,maximum_size:S.maximum_size,maximum_count:S.maximum_count,order:S.order,construction_work:S.work};
  else if(q.op==="classify"){const values=labels(q.values),set=new Set(values);let violation=null;for(const t of S.constraints){work.constraint_checks++;if(t.every(v=>set.has(v))){violation=t;break;}}out={values,member:violation===null,violation};}
  else if(q.op==="component")out=S.components[integer(q.id,"component id",0,S.components.length-1)];
  else if(q.op==="node")out=S.nodes[integer(q.id,"node id",0,S.nodes.length-1)];
  else if(q.op==="conditions")out=[...cache.values()].map(c=>describe(c,null));
  else{const c=condition(q.condition),k=size(q);
   if(q.op==="family")out=describe(c,k);
   else if(q.op==="select")out=select(c,k,q.rank);
   else if(q.op==="rank")out=rank(c,k,q.values);
   else if(q.op==="page"){if(typeof q.offset!=="string"||!/^\d+$/.test(q.offset))throw new Error("decimal offset");const offset=BigInt(q.offset),total=mass(c.poly,k);if(offset>total)throw new RangeError("offset");const lim=integer(q.limit??20,"limit",0,256),rows=[];let at=offset;for(let j=0;j<lim&&at<total;j++,at++)rows.push(select(c,k,String(at)));out={total:String(total),offset:q.offset,next:at<total?String(at):null,rows};}
   else throw new Error("unknown operation");
  }return clone(out);
 }
 return {query,work:()=>clone(work)};
}
module.exports={compile,openIndex};
