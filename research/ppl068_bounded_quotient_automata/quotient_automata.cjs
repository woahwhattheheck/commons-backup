"use strict";
const VERSION="1.0.0",SCHEMA="commons.bounded-quotient-automata.v1";
const MAX_JSON=24000000;
function fail(s){throw new Error(s);}
function copy(x){return JSON.parse(JSON.stringify(x));}
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function nat(x,name){
 if(typeof x==="bigint")x=x.toString();
 if(typeof x==="number"){integer(x,name,0,Number.MAX_SAFE_INTEGER);x=String(x);}
 if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>1024)fail(name+" requires canonical nonnegative decimal");
 return BigInt(x);
}
function inputContract(input){
 if(!input||typeof input!=="object")fail("input required");
 const base=integer(input.base,"base",2,10),alphabet=base*base;
 if(!Array.isArray(input.transition)||!input.transition.length||input.transition.length>32)fail("1..32 DFA states required");
 const states=input.transition.length;
 const transition=input.transition.map(row=>{
  if(!Array.isArray(row)||row.length!==alphabet)fail("complete DFA rows required");
  return row.map(x=>integer(x,"DFA target",0,states-1));
 });
 const start=integer(input.start,"start",0,states-1);
 if(!Array.isArray(input.accept))fail("accept array required");
 let old=-1;const accept=input.accept.map(x=>{integer(x,"accept state",0,states-1);if(x<=old)fail("accept states sorted and distinct");old=x;return x;});
 if(!Array.isArray(input.quotients)||!input.quotients.length||input.quotients.length>64)fail("nonempty quotient list required");
 old=0;const quotients=input.quotients.map(q=>{integer(q,"quotient",1,64);if(q<=old)fail("quotients sorted and distinct");old=q;return q;});
 const max_length=integer(input.max_length,"max_length",1,256);
 return {base,alphabet,states,transition,start,accept,quotients,max_length,provenance:copy(input.provenance||{})};
}
function decoded(symbols,base){
 let x=0n,y=0n;const b=BigInt(base);
 for(const c of symbols){x=x*b+BigInt(Math.floor(c/base));y=y*b+BigInt(c%base);}
 return {x:x.toString(),y:y.toString(),x_digits:symbols.map(c=>Math.floor(c/base)).join(""),y_digits:symbols.map(c=>c%base).join("")};
}
function compileQuotientIndex(raw,options={}){
 const started=Date.now(),input=inputContract(raw),{base,alphabet,states,transition,start,accept,quotients,max_length}=input;
 const cellBudget=options.coefficient_budget===undefined?2000000:integer(options.coefficient_budget,"coefficient_budget",1,4000000);
 const nodeCount=quotients.reduce((a,q)=>a+states*q+1,0),cells=nodeCount*(max_length+1);
 if(cells>cellBudget||nodeCount*alphabet>1000000||cells*(2*max_length+4)>16000000)fail("preflight state/table or conservative decimal-storage budget exceeded");
 const finalSet=new Set(accept),families=[],work={product_transition_candidates:0,valid_product_transitions:0,
  bfs_edge_visits:0,bfs_nodes:0,coefficient_cells:cells,coefficient_additions:0,
  integer_pairs_enumerated:0,old_transducer_or_kernel_evaluations:0};
 for(const q of quotients){
  const canonicalStart=states*q,N=canonicalStart+1,edges=Array.from({length:N},()=>Array(alphabet).fill(-1)),final=Array(N).fill(false);
  for(let node=0;node<N;node++){
   const phase=node===canonicalStart,p=phase?start:Math.floor(node/q),r=phase?0:node%q;
   if(!phase&&r===0&&finalSet.has(p))final[node]=true;
   for(let symbol=0;symbol<alphabet;symbol++){
    work.product_transition_candidates++;
    if(phase&&symbol===0)continue;
    const a=Math.floor(symbol/base),b=symbol%base,nextR=base*r+b-q*a;
    if(nextR<0||nextR>=q)continue;
    edges[node][symbol]=transition[p][symbol]*q+nextR;work.valid_product_transitions++;
   }
  }
  const distance=Array(N).fill(-1),parent=Array(N).fill(null),queue=[canonicalStart];
  distance[canonicalStart]=0;
  for(let head=0;head<queue.length;head++){
   const node=queue[head];work.bfs_nodes++;
   for(let symbol=0;symbol<alphabet;symbol++){
    const to=edges[node][symbol];if(to<0)continue;work.bfs_edge_visits++;
    if(distance[to]<0){distance[to]=distance[node]+1;parent[to]={node,symbol};queue.push(to);}
   }
  }
  const terminal=queue.find(node=>final[node]);
  let shortest=null;
  if(terminal!==undefined){
   const symbols=[];let at=terminal;
   while(at!==canonicalStart){const p=parent[at];symbols.push(p.symbol);at=p.node;}
   symbols.reverse();shortest={length:symbols.length,symbols,...decoded(symbols,base),terminal};
  }
  const counts=[final.map(v=>v?1n:0n)];
  for(let length=1;length<=max_length;length++){
   const previous=counts[length-1],row=Array(N).fill(0n);
   for(let node=0;node<N;node++)for(const to of edges[node])if(to>=0){row[node]+=previous[to];work.coefficient_additions++;}
   counts.push(row);
  }
  families.push({quotient:q,node_count:N,canonical_start:canonicalStart,edges,final,
   reachability:{distance,parent,bfs_order:queue,reachable_count:queue.length,shortest,exists:shortest!==null},
   counts:counts.map(row=>row.map(String)),length_counts:counts.map(row=>row[canonicalStart].toString())});
 }
 const totalByLength=Array.from({length:max_length+1},(_,l)=>families.reduce((a,f)=>a+BigInt(f.length_counts[l]),0n).toString());
 return {schema:SCHEMA,version:VERSION,input,
  encoding:{direction:"MSD first",symbol:"base*x_digit+y_digit",canonical:"nonempty with first symbol nonzero",
   domain:"x>0, y=quotient*x, quotient in supplied positive finite list",order:"quotient increasing, then digit-pair lexicographic"},
  families,summary:{quotients:quotients.length,product_nodes:nodeCount,coefficient_cells:cells,max_length,
   total_by_length:totalByLength,by_quotient:families.map(f=>({quotient:f.quotient,exists:f.reachability.exists,
    reachable_nodes:f.reachability.reachable_count,shortest:f.reachability.shortest,count_at_max_length:f.length_counts[max_length]}))},
  construction:{...work,coefficient_budget:cellBudget,elapsed_ms_observation:Date.now()-started}};
}
function openQuotientIndex(raw){
 if(typeof raw==="string"){if(raw.length>MAX_JSON)fail("JSON cap");raw=JSON.parse(raw);}
 const text=JSON.stringify(raw);if(text.length>MAX_JSON)fail("JSON cap");const snap=JSON.parse(text);
 if(snap.schema!==SCHEMA||snap.version!==VERSION)fail("unsupported snapshot");
 const input=inputContract(snap.input),{base,alphabet,states,quotients,max_length}=input;
 if(!Array.isArray(snap.families)||snap.families.length!==quotients.length)fail("complete quotient family required");
 const stats={opened_nodes:0,opened_coefficient_cells:0,saved_parent_checks:0,saved_closure_checks:0,
  queries:0,saved_count_lookups:0,query_transition_visits:0,selected_symbols:0,
  product_transition_rebuilds:0,bfs_replays:0,coefficient_recurrences:0,old_transducer_or_kernel_evaluations:0};
 const map=new Map();
 for(let index=0;index<quotients.length;index++){
  const f=snap.families[index],q=quotients[index],N=states*q+1,S=N-1;
  if(f.quotient!==q||f.node_count!==N||f.canonical_start!==S||
   !Array.isArray(f.edges)||f.edges.length!==N||!Array.isArray(f.final)||f.final.length!==N)fail("product graph shape");
  for(let node=0;node<N;node++){
   if(!Array.isArray(f.edges[node])||f.edges[node].length!==alphabet||typeof f.final[node]!=="boolean")fail("edge row shape");
   for(const to of f.edges[node])integer(to,"saved target",-1,N-2);
  }
  if(f.final[S]||f.edges[S][0]!==-1)fail("canonical start contract");
  const r=f.reachability;
  if(!r||!Array.isArray(r.distance)||r.distance.length!==N||!Array.isArray(r.parent)||r.parent.length!==N||
    !Array.isArray(r.bfs_order)||r.distance[S]!==0||r.parent[S]!==null)fail("reachability shape");
  const seen=new Set();
  for(const node of r.bfs_order){integer(node,"BFS node",0,N-1);if(seen.has(node)||r.distance[node]<0)fail("BFS order references");seen.add(node);}
  if(r.bfs_order[0]!==S||r.reachable_count!==seen.size)fail("BFS start/count");
  for(let node=0;node<N;node++){
   const d=integer(r.distance[node],"distance",-1,N-1);
   if((d>=0)!==seen.has(node))fail("reachable coverage");
   if(d<0){if(r.parent[node]!==null)fail("unreachable parent");continue;}
   if(node!==S){
    const p=r.parent[node];if(!p)fail("reachable parent missing");
    integer(p.node,"parent",0,N-1);integer(p.symbol,"parent symbol",0,alphabet-1);
    if(f.edges[p.node][p.symbol]!==node||r.distance[p.node]!==d-1)fail("parent distance certificate");
    stats.saved_parent_checks++;
   }
   for(const to of f.edges[node])if(to>=0){
    if(r.distance[to]<0||r.distance[to]>d+1)fail("closure/shortest-distance certificate");stats.saved_closure_checks++;
   }
  }
  if(!Array.isArray(f.counts)||f.counts.length!==max_length+1||
   !Array.isArray(f.length_counts)||f.length_counts.length!==max_length+1)fail("all count layers required");
  const numeric=f.counts.map((row,l)=>{
   if(!Array.isArray(row)||row.length!==N)fail("coefficient row width");
   const out=row.map(x=>nat(x,"saved count"));stats.opened_coefficient_cells+=N;
   if(l===0&&out.some((x,node)=>x!==(f.final[node]?1n:0n)))fail("empty suffix identity");
   if(f.length_counts[l]!==row[S])fail("length count binding");return out;
  });
  stats.opened_nodes+=N;map.set(q,{f,numeric});
 }
 function family(q){integer(q,"quotient",1,64);const x=map.get(q);if(!x)fail("quotient outside compiled scope");return x;}
 function length(l){return integer(l,"length",0,max_length);}
 function symbols(a,max=max_length){if(!Array.isArray(a)||a.length>max)fail("symbol array limit");return a.map(x=>integer(x,"symbol",0,alphabet-1));}
 function count(q,l,node){stats.saved_count_lookups++;return family(q).numeric[l][node];}
 function fullCount(q,l){const {f}=family(q);return count(q,l,f.canonical_start);}
 function total(l){return quotients.reduce((sum,q)=>sum+fullCount(q,l),0n);}
 function prefix(q,l,rawSymbols){
  const {f}=family(q),word=symbols(rawSymbols);if(word.length>l)fail("prefix longer than requested word");
  let node=f.canonical_start,offset=0n;const trace=[];
  for(let i=0;i<word.length;i++){
   const symbol=word[i],remaining=l-i-1;let skipped=0n;
   for(let c=0;c<symbol;c++){const to=f.edges[node][c];if(to>=0)skipped+=count(q,remaining,to);}
   const to=f.edges[node][symbol];stats.query_transition_visits++;
   if(to<0)return {quotient:q,length:l,symbols:word,valid:false,count:"0",first_rank:null,rejected_at:i,trace};
   offset+=skipped;trace.push({position:i,node,symbol,next:to,skipped:skipped.toString()});node=to;
  }
  const completion=count(q,l-word.length,node);
  return {quotient:q,length:l,symbols:word,valid:true,node,count:completion.toString(),
   first_rank:completion?offset.toString():null,trace};
 }
 function select(q,l,rank){
  const {f}=family(q),amount=fullCount(q,l);if(rank>=amount)fail("rank outside fixed-length family");
  let node=f.canonical_start;const original=rank,word=[],trace=[];
  for(let i=0;i<l;i++){
   let chosen=false,skipped=0n;
   for(let symbol=0;symbol<alphabet;symbol++){
    const to=f.edges[node][symbol];if(to<0)continue;stats.query_transition_visits++;
    const c=count(q,l-i-1,to);if(rank>=c){rank-=c;skipped+=c;continue;}
    trace.push({position:i,node,symbol,next:to,skipped:skipped.toString(),branch_count:c.toString(),residual_rank:rank.toString()});
    word.push(symbol);node=to;chosen=true;stats.selected_symbols++;break;
   }
   if(!chosen)fail("saved counts have no selected branch");
  }
  if(!f.final[node]||rank!==0n)fail("selection terminal mismatch");
  return {quotient:q,length:l,rank:original.toString(),count:amount.toString(),symbols:word,...decoded(word,base),trace};
 }
 function selectAll(l,rank){
  const original=rank,amount=total(l);if(rank>=amount)fail("aggregate rank outside family");
  for(const q of quotients){const c=fullCount(q,l);if(rank>=c){rank-=c;continue;}
   return {aggregate_rank:original.toString(),aggregate_count:amount.toString(),selected:select(q,l,rank)};}
  fail("aggregate selection inconsistent");
 }
 return {
  summary(){stats.queries++;return copy(snap.summary);},
  quotient(q){stats.queries++;const {f}=family(q);return {quotient:q,node_count:f.node_count,reachability:copy(f.reachability),length_counts:f.length_counts.slice()};},
  count(l,q=null){stats.queries++;l=length(l);return {length:l,quotient:q,count:(q===null?total(l):fullCount(q,l)).toString()};},
  prefix(q,l,word){stats.queries++;return prefix(q,length(l),word);},
  select(q,l,rank){stats.queries++;return select(q,length(l),nat(rank,"rank"));},
  rank(q,word){
   stats.queries++;const a=symbols(word),p=prefix(q,a.length,a);
   return {quotient:q,length:a.length,symbols:a,accepted:p.valid&&p.count==="1",rank:p.valid&&p.count==="1"?p.first_rank:null,trace:p.trace};
  },
  selectAll(l,rank){stats.queries++;return selectAll(length(l),nat(rank,"rank"));},
  pageAll(l,start=0,limit=8){
   stats.queries++;l=length(l);let rank=nat(start,"start");integer(limit,"limit",1,32);
   const amount=total(l);if(rank>amount)fail("page start outside family");const initial=rank,rows=[];
   for(let i=0;i<limit&&rank<amount;i++,rank++)rows.push(selectAll(l,rank));
   return {length:l,start:initial.toString(),count:amount.toString(),rows,next:rank<amount?rank.toString():null};
  },
  statePage(q,start=0,limit=32){
   stats.queries++;const {f}=family(q);integer(start,"start",0,f.node_count);integer(limit,"limit",1,64);
   const end=Math.min(f.node_count,start+limit),rows=[];
   for(let node=start;node<end;node++)rows.push({node,dfa_state:node===f.canonical_start?null:Math.floor(node/q),
    residual:node===f.canonical_start?null:node%q,canonical_start:node===f.canonical_start,
    final:f.final[node],edges:f.edges[node].slice(),distance:f.reachability.distance[node],parent:copy(f.reachability.parent[node])});
   return {quotient:q,start,total:f.node_count,rows,next:end<f.node_count?end:null};
  },
  coefficientPage(q,l,start=0,limit=32){
   stats.queries++;l=length(l);const {f}=family(q);integer(start,"start",0,f.node_count);integer(limit,"limit",1,64);
   const end=Math.min(f.node_count,start+limit);
   return {quotient:q,length:l,start,total:f.node_count,rows:f.counts[l].slice(start,end).map((c,i)=>({node:start+i,count:c})),next:end<f.node_count?end:null};
  },
  membership(x,y){
   stats.queries++;const a=nat(x,"x"),b=nat(y,"y");if(a===0n)return {in_scope:false,reason:"x must be positive"};
   if(b===0n||b%a!==0n)return {in_scope:false,reason:"positive integer quotient required"};
   const quotient=b/a;if(quotient>64n||!map.has(Number(quotient)))return {in_scope:false,reason:"quotient outside compiled list",quotient:quotient.toString()};
   const q=Number(quotient),{f}=family(q),xd=a.toString(base),yd=b.toString(base),L=Math.max(xd.length,yd.length);
   if(L>4096)fail("membership word limit");const xs=xd.padStart(L,"0"),ys=yd.padStart(L,"0");
   let node=f.canonical_start;const trace=[];
   for(let i=0;i<L;i++){const symbol=base*Number(xs[i])+Number(ys[i]),to=f.edges[node][symbol];stats.query_transition_visits++;
    trace.push({position:i,node,symbol,next:to});if(to<0)return {in_scope:true,accepted:false,quotient:q,x:a.toString(),y:b.toString(),trace};node=to;}
   return {in_scope:true,accepted:f.final[node],quotient:q,x:a.toString(),y:b.toString(),length:L,trace};
  },
  statistics(){return copy(stats);}
 };
}
module.exports={VERSION,compileQuotientIndex,openQuotientIndex};
