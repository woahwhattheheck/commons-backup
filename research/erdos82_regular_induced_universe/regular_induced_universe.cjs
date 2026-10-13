"use strict";
const copy=x=>JSON.parse(JSON.stringify(x));
function integer(v,lo,hi,label){if(!Number.isInteger(v)||v<lo||v>hi)throw new RangeError(label);return v;}
function pop(x){let n=0;while(x){x&=x-1;n++;}return n;}
function rankValue(x){if(typeof x!=="string"||x.length>4096||! /^(0|[1-9][0-9]*)$/.test(x))throw new TypeError("rank string");return BigInt(x);}
function buildIndex(input){
 const n=integer(input.vertices,1,6,"vertices"),edges=[];for(let u=0;u<n;u++)for(let v=u+1;v<n;v++)edges.push([u,v]);
 const graphCount=1<<edges.length,subsetCount=1<<n,subsets=Array.from({length:subsetCount},(_,mask)=>({mask,size:pop(mask),vertices:Array.from({length:n},(_,v)=>v).filter(v=>mask&(1<<v))}));
 const rows=Array(graphCount),groups=Array.from({length:n+1},()=>[]),occurrences=Array.from({length:n+1},()=>Array(n).fill(0)),adj=Array(n).fill(0);
 const work={graph_count:0,gray_edge_toggles:0,nonempty_subset_checks:0,internal_degree_counts:0,regular_nonempty_subsets:0,empty_records:0};
 let previous=0,totalRegular=0;
 for(let step=0;step<graphCount;step++){
  const mask=step^(step>>1);if(step){const changed=previous^mask,id=31-Math.clz32(changed),[u,v]=edges[id];adj[u]^=1<<v;adj[v]^=1<<u;work.gray_edge_toggles++;}previous=mask;
  const degreeBits=Array(n).fill(0n);degreeBits[0]=1n;let maximum=0,maximumCount=1;work.graph_count++;work.empty_records++;occurrences[0][0]++;totalRegular++;
  for(let S=1;S<subsetCount;S++){
   work.nonempty_subset_checks++;let degree=-1,regular=true;
   for(const v of subsets[S].vertices){const d=pop(adj[v]&S);work.internal_degree_counts++;if(degree<0)degree=d;else if(d!==degree){regular=false;break;}}
   if(!regular)continue;degreeBits[degree]|=1n<<BigInt(S);work.regular_nonempty_subsets++;totalRegular++;occurrences[subsets[S].size][degree]++;
   if(subsets[S].size>maximum){maximum=subsets[S].size;maximumCount=1;}else if(subsets[S].size===maximum)maximumCount++;
  }
  rows[mask]=[maximum,maximumCount,...degreeBits.map(x=>x.toString(16))];groups[maximum].push(mask);
 }
 groups.forEach(a=>a.sort((a,b)=>a-b));const finiteF=groups.findIndex(a=>a.length>0);
 return{format:"regular-induced-universe-v1",input:copy(input),vertices:n,edges,subsets,rows,maximum_groups:groups,occurrences_by_size_degree:occurrences,summary:{vertices:n,possible_edges:edges.length,graphs:graphCount,vertex_subsets:subsetCount,regular_subset_occurrences:totalRegular,maximum_histogram:groups.map(a=>a.length),finite_F:finiteF,worst_graphs:groups[finiteF].length,empty_convention:"one degree-zero record per graph"},work};
}
function openIndex(s){
 if(!s||s.format!=="regular-induced-universe-v1"||s.rows.length!==s.summary.graphs)throw new TypeError("snapshot");
 const n=s.vertices,full=(1<<n)-1,work={queries:0,graph_row_reads:0,subset_checks:0,saved_degree_bit_tests:0,edge_bit_decodes:0,group_reads:0};
 const graph=g=>integer(g,0,s.rows.length-1,"graph mask");
 function family(q){
  const g=graph(q.graph),required=q.required===undefined?0:integer(q.required,0,full,"required mask"),forbidden=q.forbidden===undefined?0:integer(q.forbidden,0,full,"forbidden mask");
  if(q.size!==undefined)integer(q.size,0,n,"size");if(q.degree!==undefined)integer(q.degree,0,n-1,"degree");if(q.largest!==undefined&&typeof q.largest!=="boolean")throw new TypeError("largest");
  const row=s.rows[g];work.graph_row_reads++;const bits=row.slice(2).map(x=>BigInt("0x"+x)),out=[];
  for(let S=0;S<=full;S++){work.subset_checks++;const size=s.subsets[S].size;if((S&required)!==required||(S&forbidden)!==0||(q.size!==undefined&&size!==q.size)||(q.largest&&size!==row[0]))continue;
   const low=q.degree===undefined?0:q.degree,high=q.degree===undefined?n-1:q.degree;
   for(let d=low;d<=high;d++){work.saved_degree_bit_tests++;if((bits[d]&(1n<<BigInt(S)))!==0n){out.push({mask:S,size,degree:d});break;}}
  }
  return{graph:g,required,forbidden,filters:{size:q.size===undefined?null:q.size,degree:q.degree===undefined?null:q.degree,largest:!!q.largest},records:out};
 }
 function profile(f){const histogram=Array.from({length:n+1},()=>Array(n).fill(0));let maximum=null,maximumCount=0;
  for(const r of f.records){histogram[r.size][r.degree]++;if(maximum===null||r.size>maximum){maximum=r.size;maximumCount=1;}else if(r.size===maximum)maximumCount++;}
  return{graph:f.graph,required:f.required,forbidden:f.forbidden,filters:f.filters,count:String(f.records.length),maximum_size:maximum,maximum_count:String(maximumCount),histogram_by_size_degree:histogram};
 }
 function record(r){return{...r,vertices:s.subsets[r.mask].vertices.slice()};}
 function query(q){work.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"graph":{const g=graph(q.graph),edges=[];for(let i=0;i<s.edges.length;i++){work.edge_bit_decodes++;if(g&(1<<i))edges.push(s.edges[i].slice());}work.graph_row_reads++;return{graph:g,vertices:n,edges,maximum_size:s.rows[g][0],maximum_count:String(s.rows[g][1]),degree_bits:s.rows[g].slice(2)};}
  case"subset":return copy(s.subsets[integer(q.mask,0,full,"subset mask")]);
  case"global_profiles":return copy({maximum_histogram:s.summary.maximum_histogram,occurrences_by_size_degree:s.occurrences_by_size_degree});
  case"profile":return profile(family(q));
  case"count":{const f=family(q);return{...profile(f),count:String(f.records.length)};}
  case"select":{const f=family(q),rank=rankValue(q.rank);if(rank>=BigInt(f.records.length))throw new RangeError("rank");return{graph:f.graph,rank:String(rank),filters:f.filters,required:f.required,forbidden:f.forbidden,record:record(f.records[Number(rank)])};}
  case"rank":{const f=family(q),S=integer(q.mask,0,full,"subset mask"),rank=f.records.findIndex(r=>r.mask===S);if(rank<0)throw new RangeError("not in selected family");return{graph:f.graph,rank:String(rank),filters:f.filters,required:f.required,forbidden:f.forbidden,record:record(f.records[rank])};}
  case"page":{const f=family(q),start=rankValue(q.start),limit=integer(q.limit,0,1000,"limit");if(start>BigInt(f.records.length))throw new RangeError("page");return{graph:f.graph,start:q.start,filters:f.filters,required:f.required,forbidden:f.forbidden,count:String(f.records.length),records:f.records.slice(Number(start),Number(start)+limit).map(record)};}
  case"graph_select":{const maximum=integer(q.maximum_size,0,n,"maximum size"),list=s.maximum_groups[maximum];work.group_reads++;const rank=rankValue(q.rank);if(rank>=BigInt(list.length))throw new RangeError("graph rank");return{maximum_size:maximum,rank:String(rank),graph:list[Number(rank)],count:String(list.length)};}
  case"graph_rank":{const g=graph(q.graph),maximum=s.rows[g][0];work.graph_row_reads++;const list=s.maximum_groups[maximum];work.group_reads++;let lo=0,hi=list.length;while(lo<hi){const mid=(lo+hi)>>1;if(list[mid]<g)lo=mid+1;else hi=mid;}if(list[lo]!==g)throw new Error("saved group");return{graph:g,maximum_size:maximum,rank:String(lo),count:String(list.length)};}
  case"graph_page":{const maximum=integer(q.maximum_size,0,n,"maximum size"),list=s.maximum_groups[maximum];work.group_reads++;const start=rankValue(q.start),limit=integer(q.limit,0,1000,"limit");if(start>BigInt(list.length))throw new RangeError("graph page");return{maximum_size:maximum,start:q.start,count:String(list.length),graphs:list.slice(Number(start),Number(start)+limit)};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(work)};
}
module.exports={buildIndex,openIndex};
