'use strict';
const SCHEMA='commons.k4_free_triple_family/v1';
const copy=x=>JSON.parse(JSON.stringify(x));
function nat(x,name,max){if(!Number.isSafeInteger(x)||x<0||x>max)throw new TypeError(name+' out of range');return x;}
function rankValue(x){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>128)throw new TypeError('canonical bounded rank');return BigInt(x);}
function combinations(n,k){const out=[],a=[];function go(s){if(a.length===k){out.push(a.slice());return;}for(let x=s;x<n;x++){a.push(x);go(x+1);a.pop();}}go(0);return out;}
function pc(x){let n=0;while(x){x&=x-1;n++;}return n;}
function addPolynomial(lo,hi){const out=Array(Math.max(lo.length,hi.length+1)).fill(0n);for(let i=0;i<lo.length;i++)out[i]+=lo[i];for(let i=0;i<hi.length;i++)out[i+1]+=hi[i];while(out.length>1&&out[out.length-1]===0n)out.pop();return out;}
function buildIndex(input){
 if(!input||typeof input!=='object')throw new TypeError('input');const n=nat(input.n,'n',6);if(n<3)throw new RangeError('n >= 3');
 const edges=combinations(n,3),fourSets=combinations(n,4),E=edges.length,rank=new Map(edges.map((e,i)=>[e.join(','),i]));
 const constraints=fourSets.map(v=>{let mask=0;for(let i=0;i<4;i++)mask|=1<<rank.get(v.filter((_,j)=>i!==j).join(','));return {vertices:v,edge_mask:mask};});
 const nodes=[{variable:E,lo:0,hi:0,coefficients:['0'],total:'0'},{variable:E,lo:1,hi:1,coefficients:['1'],total:'1'}],polys=[[0n],[1n]],unique=new Map(),memo=new Map(),states=[];
 const work={residual_states:0,decision_nodes:0,coefficient_cells:2,subset_tests:0,zero_terminal_hits:0,one_terminal_hits:0,zero_suppressions:0,candidate_edge_sets_enumerated:0};
 function normalize(a){const list=Array.from(new Set(a)).sort((x,y)=>pc(x)-pc(y)||x-y),out=[];for(const x of list){let redundant=false;for(const y of out){work.subset_tests++;if((x&y)===y){redundant=true;break;}}if(!redundant)out.push(x);}return out.sort((x,y)=>x-y);}
 function visit(k,cs){
  if(cs.includes(0)){work.zero_terminal_hits++;return 0;}if(k===E){work.one_terminal_hits++;return 1;}
  cs=normalize(cs);const key=k+':'+cs.join(',');if(memo.has(key))return memo.get(key);
  if(states.length>=100000)throw new RangeError('residual-state cap');const sid=states.length;states.push(null);work.residual_states++;
  const bit=1<<k,lo=visit(k+1,cs.filter(x=>!(x&bit))),hi=visit(k+1,cs.map(x=>x&~bit));let id;
  if(hi===0){id=lo;work.zero_suppressions++;}else{const nk=k+','+lo+','+hi;if(unique.has(nk))id=unique.get(nk);else{
   id=nodes.length;if(id>=100000)throw new RangeError('node cap');const p=addPolynomial(polys[lo],polys[hi]);work.coefficient_cells+=p.length;if(work.coefficient_cells>1500000)throw new RangeError('coefficient cap');
   polys.push(p);nodes.push({variable:k,lo,hi,coefficients:p.map(String),total:p.reduce((a,b)=>a+b,0n).toString()});unique.set(nk,id);work.decision_nodes++;
  }}
  states[sid]={position:k,forbidden_masks:cs,lo,hi,result:id};memo.set(key,id);return id;
 }
 const root=visit(0,constraints.map(c=>c.edge_mask)),coeff=nodes[root].coefficients,max=coeff.length-1;
 return {record:{schema:SCHEMA,input:copy(input),n,edges,four_set_constraints:constraints,nodes,states,root,summary:{vertices:n,possible_edges:E,four_set_constraints:constraints.length,total_families:nodes[root].total,coefficients:coeff.slice(),maximum_edges:max,maximum_families:coeff[max]},work},scope:'All labelled simple K4^3-free hypergraphs on the supplied vertex set; no asymptotic or novelty claim.'};
}
function openIndex(saved){
 if(!saved||saved.schema!==SCHEMA)throw new TypeError('schema');const r=copy(saved),n=nat(r.n,'n',6);if(n<3)throw new RangeError('n');const E=r.edges.length,ALL=(1<<E)-1;
 if(E>20||!Array.isArray(r.nodes)||r.nodes.length<2||r.nodes.length>100000)throw new TypeError('nodes');
 nat(r.root,'root',r.nodes.length-1);const polys=r.nodes.map((v,i)=>{nat(v.variable,'variable',E);if(i>=2){nat(v.lo,'lo',i-1);nat(v.hi,'hi',i-1);if(!v.hi||r.nodes[v.lo].variable<=v.variable||r.nodes[v.hi].variable<=v.variable)throw new TypeError('node order');}if(!Array.isArray(v.coefficients)||v.coefficients.length>E+1)throw new TypeError('coefficients');return v.coefficients.map(rankValue);});
 const work={saved_nodes_indexed:r.nodes.length,saved_coefficient_cells:polys.reduce((s,p)=>s+p.length,0),node_visits:0,conditional_cells:0,conditional_coefficient_cells:0,conditional_memo_hits:0,base_recurrence_updates:0,constraint_generations:0,hypergraphs_enumerated:0};
 function maskFromIndices(a){if(!Array.isArray(a))throw new TypeError('indices');let z=0;for(const i of a){nat(i,'edge index',E-1);if(z&(1<<i))throw new TypeError('duplicate edge');z|=1<<i;}return z;}
 function decode(mask){nat(mask,'mask',ALL);return {mask,edge_indices:r.edges.map((_,i)=>i).filter(i=>mask&(1<<i)),edges:r.edges.filter((_,i)=>mask&(1<<i)).map(e=>e.slice()),cardinality:pc(mask)};}
 function sizeArg(k){if(k===null)return null;return nat(k,'cardinality',E);}
 const total=p=>p.reduce((a,b)=>a+b,0n);
 const count=(p,k)=>k===null?total(p):(p[k]||0n);
 function makeFamily(present,absent){
  if(present&absent)throw new TypeError('incompatible conditions');
  const conditional=present!==0||absent!==0,memo=new Map(),cells=[];
  function get(id,req){
   if(id===0)return {id,required:req,lo:0,hi:0,coeff:[0n]};
   if(id===1)return {id,required:req,lo:0,hi:0,coeff:req?[0n]:[1n]};
   const node=r.nodes[id],bit=1<<node.variable;
   if(req&(bit-1))return {id,required:req,lo:0,hi:0,coeff:[0n]};
   if(!conditional)return {id,required:0,lo:node.lo,hi:node.hi,coeff:polys[id]};
   const key=id+':'+req;if(memo.has(key)){work.conditional_memo_hits++;return memo.get(key);}
   if(cells.length>=100000)throw new RangeError('condition cell cap');
   const allowLo=!(req&bit),allowHi=!(absent&bit),lc=allowLo?get(node.lo,req).coeff:[0n],hc=allowHi?get(node.hi,req&~bit).coeff:[0n],p=addPolynomial(lc,hc);
   const obj={id,required:req,lo:allowLo?node.lo:0,hi:allowHi?node.hi:0,coeff:p};memo.set(key,obj);cells.push(obj);work.conditional_cells++;work.conditional_coefficient_cells+=p.length;return obj;
  }
  const root=get(r.root,present),coefficient=root.coeff;
  function select(k,text){sizeArg(k);let z=rankValue(text);const original=z,ct=count(coefficient,k);if(z>=ct)throw new RangeError('rank');let id=r.root,req=present,mask=0,need=k;const trace=[];
   while(id>=2){const v=r.nodes[id],bit=1<<v.variable,c=get(id,req),lo=c.lo?get(c.lo,req):{coeff:[0n]},a=count(lo.coeff,need);work.node_visits++;
    if(z<a){trace.push({node:id,variable:v.variable,choice:0,lo_count:a.toString(),residual_rank:z.toString()});id=c.lo;}
    else{z-=a;if(!c.hi||need===0)throw new Error('invalid branch');trace.push({node:id,variable:v.variable,choice:1,lo_count:a.toString(),residual_rank:z.toString()});mask|=bit;req&=~bit;if(need!==null)need--;id=c.hi;}
   }
   if(id!==1||req||need!==null&&need!==0)throw new Error('invalid terminal');
   return {rank:original.toString(),count:ct.toString(),cardinality_filter:k,condition:{present_mask:present,absent_mask:absent},...decode(mask),trace};
  }
  function rank(mask,k=null){nat(mask,'mask',ALL);sizeArg(k);if((mask&present)!==present||(mask&absent)||k!==null&&pc(mask)!==k)return null;let rest=mask,id=r.root,req=present,need=k,z=0n;const trace=[];
   while(id>=2){const v=r.nodes[id],bit=1<<v.variable;if(rest&(bit-1))return null;const c=get(id,req),lo=c.lo?get(c.lo,req):{coeff:[0n]},a=count(lo.coeff,need);work.node_visits++;
    if(rest&bit){if(!c.hi||need===0)return null;z+=a;trace.push({node:id,variable:v.variable,choice:1,lo_count:a.toString(),rank_so_far:z.toString()});rest&=~bit;req&=~bit;if(need!==null)need--;id=c.hi;}
    else{if(!c.lo)return null;trace.push({node:id,variable:v.variable,choice:0,rank_so_far:z.toString()});id=c.lo;}
   }
   if(id!==1||rest||req||need!==null&&need!==0)return null;return {mask,rank:z.toString(),count:count(coefficient,k).toString(),cardinality_filter:k,trace};
  }
  return {summary:()=>{let maximum=coefficient.length-1;while(maximum>=0&&coefficient[maximum]===0n)maximum--;return {present_mask:present,absent_mask:absent,total:total(coefficient).toString(),coefficients:coefficient.map(String),maximum_edges:maximum<0?null:maximum,maximum_families:maximum<0?'0':coefficient[maximum].toString()};},
   select,rank,page:(k,offset,limit)=>{sizeArg(k);const z=rankValue(offset),ct=count(coefficient,k);nat(limit,'limit',256);if(z>ct)throw new RangeError('offset');const a=[];for(let j=0;j<limit&&z+BigInt(j)<ct;j++)a.push(select(k,(z+BigInt(j)).toString()));return a;},
   snapshot:()=>({condition:{present_mask:present,absent_mask:absent},root_coefficients:coefficient.map(String),cells:cells.map(c=>({id:c.id,required:c.required,lo:c.lo,hi:c.hi,coefficients:c.coeff.map(String)}))})
  };
 }
 const base=makeFamily(0,0);
 return {summary:()=>copy({...r.summary,construction_work:r.work}),edges:()=>copy(r.edges),constraints:()=>copy(r.four_set_constraints),select:base.select,rank:base.rank,page:base.page,
 condition:({present=[],absent=[]}={})=>makeFamily(maskFromIndices(present),maskFromIndices(absent)),
 membership:mask=>{const q=base.rank(mask);return {mask,accepted:q!==null,rank:q?q.rank:null};},
 decode,snapshot:()=>copy(r),work:()=>copy(work)};
}
module.exports={buildIndex,openIndex};
