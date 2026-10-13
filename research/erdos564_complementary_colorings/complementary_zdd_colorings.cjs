'use strict';
const SCHEMA='commons.complementary_zdd_product/v1';
const clone=x=>JSON.parse(JSON.stringify(x));
function nat(x,n,max){if(!Number.isSafeInteger(x)||x<0||x>max)throw new TypeError(n+' out of range');return x;}
function integerText(x){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>256)throw new TypeError('canonical nonnegative integer text required');return BigInt(x);}
function pop(x){let n=0;while(x){x&=x-1;n++;}return n;}
function add(lo,hi){const p=Array(Math.max(lo.length,hi.length+1)).fill(0n);for(let i=0;i<lo.length;i++)p[i]+=lo[i];for(let i=0;i<hi.length;i++)p[i+1]+=hi[i];while(p.length>1&&!p[p.length-1])p.pop();return p;}
function compile(input){
 if(!input||input.schema!=='commons.complementary_zdd_input/v1')throw new TypeError('input schema');
 const E=nat(input.variables,'variables',24);if(E<1)throw new RangeError('positive variable count');
 const S=input.source_nodes;if(!Array.isArray(S)||S.length<2||S.length>100000)throw new TypeError('source nodes');
 nat(input.source_root,'source root',S.length-1);if(!Array.isArray(input.labels)||input.labels.length!==E)throw new TypeError('labels');
 for(let i=0;i<S.length;i++){const n=S[i];nat(n.variable,'variable',E);if(i>=2){nat(n.lo,'lo',i-1);nat(n.hi,'hi',i-1);if(!n.hi||S[n.lo].variable<=n.variable||S[n.hi].variable<=n.variable)throw new TypeError('source ZDD order');}}
 if(S[0].variable!==E||S[1].variable!==E)throw new TypeError('terminal variables');
 const limits=input.limits||{},maxStates=nat(limits.max_product_states||250000,'max states',250000),maxNodes=nat(limits.max_nodes||250000,'max nodes',250000),maxCells=nat(limits.max_coefficient_cells||4000000,'max cells',4000000);
 const nodes=[{variable:E,lo:0,hi:0,coefficients:['0'],total:'0'},{variable:E,lo:1,hi:1,coefficients:['1'],total:'1'}],polys=[[0n],[1n]],states=[],memo=new Map(),unique=new Map();
 const work={source_nodes_copied:S.length,product_states:0,product_memo_hits:0,source_transitions:0,dead_transition_hits:0,decision_nodes:0,coefficient_cells:2,coefficient_additions:0,old_constraint_generation:0,old_family_compilation:0,tournament_computation:0,complete_colorings_enumerated:0};
 function advance(id,k,bit){work.source_transitions++;if(!id)return 0;const n=S[id];if(n.variable<k)throw new Error('source order');return n.variable===k?(bit?n.hi:n.lo):(bit?0:id);}
 function visit(k,a,b){
  if(!a||!b){work.dead_transition_hits++;return 0;}
  if(k===E){if(a!==1||b!==1)throw new Error('nonterminal source');return 1;}
  const key=k+':'+a+':'+b;if(memo.has(key)){work.product_memo_hits++;return memo.get(key);}
  if(states.length>=maxStates)throw new RangeError('product-state cap');const sid=states.length;states.push(null);work.product_states++;
  const lo=visit(k+1,advance(a,k,0),advance(b,k,1)),hi=visit(k+1,advance(a,k,1),advance(b,k,0));let id=0;
  if(lo||hi){const nk=k+':'+lo+':'+hi;if(unique.has(nk))id=unique.get(nk);else{
   if(nodes.length>=maxNodes)throw new RangeError('decision-node cap');const p=add(polys[lo],polys[hi]);if(work.coefficient_cells+p.length>maxCells)throw new RangeError('coefficient cap');
   work.coefficient_additions+=polys[lo].length+polys[hi].length;work.coefficient_cells+=p.length;id=nodes.length;nodes.push({variable:k,lo,hi,coefficients:p.map(String),total:p.reduce((x,y)=>x+y,0n).toString()});polys.push(p);unique.set(nk,id);work.decision_nodes++;
  }}
  states[sid]={position:k,red_source:a,blue_source:b,lo,hi,result:id};memo.set(key,id);return id;
 }
 const root=visit(0,input.source_root,input.source_root),c=nodes[root].coefficients,positive=c.map((x,i)=>x!=='0'?i:null).filter(x=>x!==null);
 return{schema:SCHEMA,input:clone(input),nodes,states,root,summary:{variables:E,source_nodes:S.length,source_root:input.source_root,total:nodes[root].total,red_coefficients:c.slice(),minimum_red:positive.length?positive[0]:null,maximum_red:positive.length?positive[positive.length-1]:null},work};
}
function openIndex(saved){
 if(!saved||saved.schema!==SCHEMA)throw new TypeError('saved schema');const r=clone(saved),E=nat(r.input.variables,'variables',24),ALL=(1<<E)-1;
 if(!Array.isArray(r.nodes)||r.nodes.length<2||r.nodes.length>250000)throw new TypeError('nodes');nat(r.root,'root',r.nodes.length-1);
 const polynomials=r.nodes.map((n,id)=>{nat(n.variable,'variable',E);if(id>=2){nat(n.lo,'lo',id-1);nat(n.hi,'hi',id-1);if(n.variable>=E||n.lo&&r.nodes[n.lo].variable!==n.variable+1||n.hi&&r.nodes[n.hi].variable!==n.variable+1)throw new TypeError('full-level decision order');}if(!Array.isArray(n.coefficients)||n.coefficients.length>E+1)throw new TypeError('coefficients');return n.coefficients.map(integerText);});
 const totals=r.nodes.map(n=>integerText(n.total));
 const work={saved_nodes_indexed:r.nodes.length,saved_coefficient_cells:polynomials.reduce((s,p)=>s+p.length,0),node_visits:0,coefficient_reads:0,rank_additions:0,selected_colorings:0,edge_decodes:0,conditional_nodes:0,conditional_coefficient_cells:0,conditional_additions:0,conditional_memo_hits:0,old_source_transitions:0,new_product_states:0,new_base_coefficients:0};
 const cache=new Map();
 function mask(x){return nat(x,'mask',ALL);}
 function size(k){return k===null?null:nat(k,'red cardinality',E);}
 function fromIndices(a){if(!Array.isArray(a))throw new TypeError('edge indices');let m=0;for(const v of a){nat(v,'edge index',E-1);if(m&(1<<v))throw new TypeError('duplicate index');m|=1<<v;}return m;}
 function decode(m){mask(m);const red=[],blue=[];for(let i=0;i<E;i++){work.edge_decodes++;(m&(1<<i)?red:blue).push(i);}return{mask:m,complement_mask:ALL^m,red_count:red.length,red_indices:red,blue_indices:blue};}
 function family(red,blue){
  mask(red);mask(blue);if(red&blue)throw new TypeError('conflicting fixed colors');const key=red+':'+blue;if(cache.has(key))return cache.get(key).api;
  const conditional=red!==0||blue!==0,memo=new Map(),cells=[];
  function get(id){
   if(!conditional)return{lo:r.nodes[id].lo,hi:r.nodes[id].hi,p:polynomials[id],total:totals[id]};
   if(id<2)return{lo:0,hi:0,p:polynomials[id],total:totals[id]};
   if(memo.has(id)){work.conditional_memo_hits++;return memo.get(id);}
   if(cells.length>=1000000)throw new RangeError('conditional cell cap');
   const n=r.nodes[id],bit=1<<n.variable,lo=red&bit?0:n.lo,hi=blue&bit?0:n.hi,lp=get(lo).p,hp=get(hi).p,p=add(lp,hp),obj={id,lo,hi,p,total:p.reduce((a,b)=>a+b,0n)};
   work.conditional_nodes++;work.conditional_coefficient_cells+=p.length;work.conditional_additions+=lp.length+hp.length;memo.set(id,obj);cells.push(obj);return obj;
  }
  const root=get(r.root);
  function count(c,k){work.coefficient_reads++;return k===null?c.total:(c.p[k]||0n);}
  function summary(){const positive=root.p.map((x,i)=>x?i:null).filter(x=>x!==null);return{red_mask:red,blue_mask:blue,total:root.total.toString(),red_coefficients:root.p.map(String),minimum_red:positive.length?positive[0]:null,maximum_red:positive.length?positive[positive.length-1]:null};}
  function select(k,text){size(k);let rank=integerText(text),need=k,id=r.root,m=0;const original=rank,total=count(root,k),trace=[];if(rank>=total)throw new RangeError('rank');
   while(id>=2){const n=r.nodes[id],c=get(id),lo=count(get(c.lo),need);work.node_visits++;if(rank<lo){trace.push({node:id,variable:n.variable,color:0,zero_count:lo.toString(),residual_rank:rank.toString()});id=c.lo;}
    else{rank-=lo;if(!c.hi||need===0)throw new Error('invalid selected branch');trace.push({node:id,variable:n.variable,color:1,zero_count:lo.toString(),residual_rank:rank.toString()});m|=1<<n.variable;if(need!==null)need--;id=c.hi;}}
   if(id!==1||need!==null&&need!==0||rank!==0n)throw new Error('invalid terminal');work.selected_colorings++;return{rank:original.toString(),count:total.toString(),red_cardinality:k,condition:{red_mask:red,blue_mask:blue},...decode(m),trace};
  }
  function rank(m,k=null){mask(m);size(k);if((m&red)!==red||(m&blue)||k!==null&&pop(m)!==k)return null;let id=r.root,need=k,z=0n;const trace=[];
   while(id>=2){const n=r.nodes[id],c=get(id),lo=count(get(c.lo),need);work.node_visits++;if(m&(1<<n.variable)){if(!c.hi||need===0)return null;z+=lo;work.rank_additions++;trace.push({node:id,variable:n.variable,color:1,zero_count:lo.toString(),rank_so_far:z.toString()});if(need!==null)need--;id=c.hi;}else{trace.push({node:id,variable:n.variable,color:0,rank_so_far:z.toString()});id=c.lo;}}
   if(id!==1||need!==null&&need!==0)return null;return{mask:m,rank:z.toString(),count:count(root,k).toString(),red_cardinality:k,condition:{red_mask:red,blue_mask:blue},trace};
  }
  function page(k,offset,limit){size(k);nat(limit,'limit',256);const a=integerText(offset),total=count(root,k);if(a>total)throw new RangeError('offset');const out=[];for(let i=0;i<limit&&a+BigInt(i)<total;i++)out.push(select(k,(a+BigInt(i)).toString()));return out;}
  const api={summary,select,rank,page,snapshot:()=>({condition:{red_mask:red,blue_mask:blue},root_coefficients:root.p.map(String),cells:cells.map(c=>({id:c.id,lo:c.lo,hi:c.hi,coefficients:c.p.map(String),total:c.total.toString()}))})};cache.set(key,{api});return api;
 }
 const base=family(0,0);
 return{summary:()=>clone({...r.summary,construction_work:r.work}),labels:()=>clone(r.input.labels),decode,select:base.select,rank:base.rank,page:base.page,
 condition:({red=[],blue=[]}={})=>family(fromIndices(red),fromIndices(blue)),
 complement:(m,k=null)=>{const original=base.rank(m,k);if(!original)return null;return{original,complement:base.rank(ALL^m,k===null?null:E-k)};},
 exportConditions:()=>Array.from(cache.values()).map(x=>x.api.snapshot()),work:()=>clone(work)};
}
module.exports={compile,openIndex};
