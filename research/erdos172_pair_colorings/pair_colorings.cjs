"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
function big(s){if(typeof s!=="string"||! /^(0|[1-9][0-9]*)$/.test(s)||s.length>4096)throw new TypeError("rank string");return BigInt(s);}
function buildIndex(input){
 const N=input.N;if(!Number.isInteger(N)||N<2||N>24)throw new RangeError("N2..24");
 const work={pair_visits:0,in_range_pairs:0,normalizations:0,subsumption_checks:0,state_calls:0,memo_hits:0,coefficient_cells:0};
 const edges=[],byMask=new Map();
 for(let x=1;x<=N;x++)for(let y=x+1;y<=N;y++){
  work.pair_visits++;if(x+y>N||x*y>N)continue;work.in_range_pairs++;
  const values=[...new Set([x,y,x+y,x*y])].sort((a,b)=>a-b),mask=values.reduce((m,v)=>m|(1<<(v-1)),0);
  if(!byMask.has(mask)){byMask.set(mask,edges.length);edges.push({id:edges.length,mask,values,pairs:[]});}edges[byMask.get(mask)].pairs.push([x,y]);
 }
 function norm(a){work.normalizations++;const arr=[...new Set(a)].sort((a,b)=>a-b),out=[];if(arr[0]===0)return[0];for(const a of arr){let redundant=false;for(const b of out){work.subsumption_checks++;if((a&b)===b){redundant=true;break;}}if(!redundant)out.push(a);}return out;}
 const nodes=[{id:0,level:N,positive:[0],negative:[],zero:null,one:null,coefficients:["0"],count:"0"},{id:1,level:N,positive:[],negative:[],zero:null,one:null,coefficients:["1"],count:"1"}],memo=new Map();
 function build(level,pos,neg){
  work.state_calls++;if(pos[0]===0||neg[0]===0)return 0;if(level===N){if(pos.length||neg.length)throw new Error("terminal clauses");return 1;}
  const key=level+"|"+pos.join(",")+"|"+neg.join(",");if(memo.has(key)){work.memo_hits++;return memo.get(key);}
  if(memo.size>=250000)throw new RangeError("state cap");memo.set(key,-1);
  const bit=1<<level;
  const zero=build(level+1,norm(pos.map(m=>m&~bit)),norm(neg.filter(m=>!(m&bit))));
  const one=build(level+1,norm(pos.filter(m=>!(m&bit))),norm(neg.map(m=>m&~bit)));
  const coeff=Array(N-level+1).fill(0n),a=nodes[zero].coefficients,b=nodes[one].coefficients;
  for(let k=0;k<coeff.length;k++){coeff[k]=BigInt(a[k]||"0")+(k?BigInt(b[k-1]||"0"):0n);work.coefficient_cells++;}
  const id=nodes.length;nodes.push({id,level,positive:pos,negative:neg,zero,one,coefficients:coeff.map(String),count:String(coeff.reduce((a,b)=>a+b,0n))});memo.set(key,id);return id;
 }
 const initial=norm(edges.map(e=>e.mask)),root=build(0,initial,initial);
 return{format:"sum-product-pair-colorings-v1",input:clone(input),N,edges,nodes,root,summary:{N,colors:2,in_range_pairs:work.in_range_pairs,distinct_patterns:edges.length,nodes:nodes.length,accepted_colorings:nodes[root].count,weight_histogram:nodes[root].coefficients},work};
}
function openIndex(s){
 if(!s||s.format!=="sum-product-pair-colorings-v1"||s.nodes[s.root].level!==0)throw new TypeError("snapshot");
 const work={queries:0,base_cell_reads:0,conditional_cell_reads:0,new_conditional_nodes:0,new_conditional_coefficients:0,traversal_steps:0,pattern_scans:0};
 const profiles=[{id:0,fixed:[],rows:{},count:s.nodes[s.root].count,weight_histogram:s.nodes[s.root].coefficients}],keys=new Map([["[]",0]]);
 function profile(id=0){if(!Number.isInteger(id)||id<0||id>=profiles.length)throw new RangeError("condition id");return profiles[id];}
 function coeff(id,p){if(Object.prototype.hasOwnProperty.call(p.rows,id)){work.conditional_cell_reads++;return p.rows[id];}work.base_cell_reads++;return s.nodes[id].coefficients;}
 function count(id,p,weight){const a=coeff(id,p);if(weight===undefined)return a.reduce((n,x)=>n+BigInt(x),0n);if(weight<0)return 0n;return BigInt(a[weight]||"0");}
 function weight(w){if(w!==undefined&&(!Number.isInteger(w)||w<0||w>s.N))throw new RangeError("weight");return w;}
 function condition(fixed){
  if(!Array.isArray(fixed))throw new TypeError("fixed pairs");const map=new Map();
  for(const p of fixed){if(!Array.isArray(p)||p.length!==2||!Number.isInteger(p[0])||p[0]<1||p[0]>s.N||![0,1].includes(p[1]))throw new TypeError("position/bit");if(map.has(p[0])&&map.get(p[0])!==p[1])throw new RangeError("contradictory fixed bit");map.set(p[0],p[1]);}
  const pairs=[...map.entries()].sort((a,b)=>a[0]-b[0]),key=JSON.stringify(pairs);if(keys.has(key))return clone(profiles[keys.get(key)]);
  const rows={},last=pairs[pairs.length-1][0];
  function visit(id){
   if(id<2||s.nodes[id].level+1>last){work.base_cell_reads++;return s.nodes[id].coefficients;}
   if(Object.prototype.hasOwnProperty.call(rows,id)){work.conditional_cell_reads++;return rows[id];}
   const n=s.nodes[id],f=map.get(n.level+1),a=f===1?["0"]:visit(n.zero),b=f===0?["0"]:visit(n.one),c=Array(s.N-n.level+1).fill("0");
   for(let k=0;k<c.length;k++){c[k]=String(BigInt(a[k]||"0")+(k?BigInt(b[k-1]||"0"):0n));work.new_conditional_coefficients++;}
   rows[id]=c;work.new_conditional_nodes++;return c;
  }
  const histogram=visit(s.root),p={id:profiles.length,fixed:pairs,rows,count:String(histogram.reduce((a,b)=>a+BigInt(b),0n)),weight_histogram:histogram};profiles.push(p);keys.set(key,p.id);return clone(p);
 }
 function coloring(sx){if(typeof sx!=="string"||sx.length!==s.N||! /^[01]+$/.test(sx))throw new TypeError("complete binary coloring");return sx;}
 function select(rank,p,w){
  const total=count(s.root,p,w);if(rank>=total)throw new RangeError("rank");const original=rank,fixed=new Map(p.fixed),trace=[];let id=s.root,remaining=w,bits="";
  for(let pos=1;pos<=s.N;pos++){
   const n=s.nodes[id];if(id<2||n.level!==pos-1)throw new Error("saved level");work.traversal_steps++;
   const force=fixed.get(pos),left=force===1?0n:count(n.zero,p,remaining);let bit;
   if(rank<left){bit=0;id=n.zero;}else{rank-=left;bit=1;if(force===0)throw new Error("forced select");id=n.one;if(remaining!==undefined)remaining--;}
   bits+=bit;trace.push({position:pos,bit,zero_count:String(left),residual_rank:String(rank),node_after:id});
  }
  if(id!==1||rank!==0n||(remaining!==undefined&&remaining!==0))throw new Error("select terminal");
  return{condition:p.id,weight:w===undefined?null:w,rank:String(original),coloring:bits,ones:[...bits].filter(c=>c==="1").length,trace};
 }
 function ranking(bits,p,w){
  coloring(bits);const fixed=new Map(p.fixed),trace=[];let id=s.root,rank=0n,remaining=w;
  for(let pos=1;pos<=s.N;pos++){
   if(id<2)throw new RangeError("coloring rejected");const n=s.nodes[id],b=Number(bits[pos-1]),force=fixed.get(pos);work.traversal_steps++;
   if(force!==undefined&&force!==b)throw new RangeError("violates fixed bit");
   const skipped=b&&force!==1?count(n.zero,p,remaining):0n;rank+=skipped;id=b?n.one:n.zero;if(b&&remaining!==undefined)remaining--;
   trace.push({position:pos,bit:b,skipped:String(skipped),node_after:id});
  }
  if(id!==1||(remaining!==undefined&&remaining!==0))throw new RangeError("coloring rejected or wrong weight");
  return{condition:p.id,weight:w===undefined?null:w,coloring:bits,rank:String(rank),trace};
 }
 function query(q){work.queries++;switch(q.op){
  case"summary":return clone(s.summary);
  case"patterns":return clone(s.edges);
  case"node":if(!Number.isInteger(q.id)||q.id<0||q.id>=s.nodes.length)throw new RangeError("node");return clone(s.nodes[q.id]);
  case"condition":return condition(q.fixed);
  case"conditionSummary":{const p=profile(q.condition);return clone({id:p.id,fixed:p.fixed,count:p.count,weight_histogram:p.weight_histogram});}
  case"count":{const p=profile(q.condition),w=weight(q.weight);return{condition:p.id,weight:w===undefined?null:w,count:String(count(s.root,p,w))};}
  case"select":return select(big(q.rank),profile(q.condition),weight(q.weight));
  case"rank":return ranking(q.coloring,profile(q.condition),weight(q.weight));
  case"page":{const p=profile(q.condition),w=weight(q.weight),start=big(q.start),total=count(s.root,p,w);if(start>total||!Number.isInteger(q.limit)||q.limit<0||q.limit>1000)throw new RangeError("page");const out=[];for(let i=start;i<total&&out.length<q.limit;i++)out.push(select(i,p,w));return{condition:p.id,weight:w===undefined?null:w,start:q.start,records:out};}
  case"classify":{
   const bits=coloring(q.coloring);for(const e of s.edges){work.pattern_scans++;const b=bits[e.values[0]-1];if(e.values.every(v=>bits[v-1]===b))return{coloring:bits,accepted:false,witness:clone(e),color:Number(b)};}
   return{accepted:true,...ranking(bits,profiles[0],undefined)};
  }
  case"caches":return clone(profiles);
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>clone(work)};
}
module.exports={buildIndex,openIndex};
