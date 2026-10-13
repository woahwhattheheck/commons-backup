"use strict";
const copy=x=>JSON.parse(JSON.stringify(x));
function nat(s){if(typeof s!=="string"||s.length>4096||! /^(0|[1-9][0-9]*)$/.test(s))throw new TypeError("rank string");return BigInt(s);}
function first(mask){return 31-Math.clz32(mask&-mask);}
function buildIndex(input){
 const n=input.vertices,edges=input.edges.map(e=>e.slice());if(!Number.isInteger(n)||n<1||n>12||edges.length>16)throw new RangeError("vertices1..12,edges<=16");
 const m=edges.length,adj=Array.from({length:n},()=>[]),edgeMap=new Map();
 edges.forEach((e,id)=>{if(e.length!==2||!e.every(Number.isInteger)||e[0]<0||e[1]>=n||e[0]>=e[1])throw new TypeError("sorted distinct edge endpoints");const key=e.join(",");if(edgeMap.has(key))throw new RangeError("duplicate edge");edgeMap.set(key,id);adj[e[0]].push(e[1]);adj[e[1]].push(e[0]);});
 adj.forEach(a=>a.sort((a,b)=>a-b));
 const work={cycle_neighbor_visits:0,cycle_extensions:0,cycle_closures:0,state_count:1,piece_subset_checks:0,valid_transitions:0,coefficient_additions:0,coefficient_cells:1};
 const cycles=[],seen=new Set();
 function edgeId(a,b){return edgeMap.get(a<b?a+","+b:b+","+a);}
 for(let start=0;start<n;start++){
  function dfs(path,visited,mask){
   const last=path[path.length-1];
   for(const v of adj[last]){
    work.cycle_neighbor_visits++;
    if(v===start){if(path.length>=3&&path[1]<last){const full=mask|(1<<edgeId(last,start));if(seen.has(full))throw new Error("duplicate canonical cycle");seen.add(full);cycles.push({vertices:path.slice(),mask:full});work.cycle_closures++;}continue;}
    if(v<start||(visited&(1<<v)))continue;
    work.cycle_extensions++;dfs([...path,v],visited|(1<<v),mask|(1<<edgeId(last,v)));
   }
  }
  dfs([start],1<<start,0);
 }
 cycles.sort((a,b)=>a.mask-b.mask);
 const pieces=edges.map((edge,id)=>({id,kind:"edge",mask:1<<id,edge_ids:[id],vertices:edge.slice()}));
 for(const c of cycles){const ids=[];for(let i=0;i<m;i++)if(c.mask&(1<<i))ids.push(i);pieces.push({id:pieces.length,kind:"cycle",mask:c.mask,edge_ids:ids,vertices:c.vertices});}
 const byEdge=Array.from({length:m},()=>[]);for(const p of pieces)for(const e of p.edge_ids)byEdge[e].push(p.id);
 const full=(1<<m)-1,states=[[[0,"1"]]],minimum_histogram=Array(m+1).fill(0);minimum_histogram[0]=1;
 for(let mask=1;mask<=full;mask++){
  const anchor=first(mask),acc=new Map();work.state_count++;
  for(const id of byEdge[anchor]){const p=pieces[id];work.piece_subset_checks++;if((mask&p.mask)!==p.mask)continue;work.valid_transitions++;
   for(const [k,c] of states[mask^p.mask]){acc.set(k+1,(acc.get(k+1)||0n)+BigInt(c));work.coefficient_additions++;}
  }
  const row=[...acc].sort((a,b)=>a[0]-b[0]).map(([k,c])=>[k,String(c)]);if(!row.length)throw new Error("singletons must partition");states.push(row);work.coefficient_cells+=row.length;minimum_histogram[row[0][0]]++;
 }
 const root=states[full],cycle_lengths={};for(const p of pieces)if(p.kind==="cycle")cycle_lengths[p.edge_ids.length]=(cycle_lengths[p.edge_ids.length]||0)+1;
 return{format:"cycle-edge-partition-index-v1",input:copy(input),vertices:n,edges,pieces,by_edge:byEdge,states,full_mask:full,summary:{vertices:n,edges:m,cycles:cycles.length,cycle_lengths,states:states.length,coefficient_cells:work.coefficient_cells,total_decompositions:String(root.reduce((a,r)=>a+BigInt(r[1]),0n)),minimum_pieces:root[0][0],minimum_count:root[0][1],piece_histogram:root,minimum_histogram},work};
}
function openIndex(s){
 if(!s||s.format!=="cycle-edge-partition-index-v1"||s.states.length!==s.full_mask+1)throw new TypeError("snapshot");
 const work={queries:0,state_reads:0,coefficient_visits:0,piece_visits:0,mask_checks:0,rank_steps:0,selection_steps:0};
 function mask(x=s.full_mask){if(!Number.isInteger(x)||x<0||x>s.full_mask)throw new RangeError("edge mask");return x;}
 function row(x){work.state_reads++;return s.states[x];}
 function count(x,k){let total=0n;for(const [j,c] of row(x)){work.coefficient_visits++;if(k===undefined||j===k)total+=BigInt(c);}return total;}
 function kvalue(k){if(k!==undefined&&(!Number.isInteger(k)||k<0||k>s.edges.length))throw new RangeError("piece count");return k;}
 function piece(id){if(!Number.isInteger(id)||id<0||id>=s.pieces.length)throw new RangeError("piece id");work.piece_visits++;return s.pieces[id];}
 function validate(x,ids,complete=true){
  if(!Array.isArray(ids))throw new TypeError("piece ids");const owner=Array(s.edges.length).fill(null);let remaining=x;
  for(const id of ids){const p=piece(id);work.mask_checks++;if((remaining&p.mask)!==p.mask)return{valid:false,reason:"piece outside or overlapping",piece:id};remaining^=p.mask;for(const e of p.edge_ids)owner[e]=id;}
  if(complete&&remaining)return{valid:false,reason:"uncovered edges",remaining};
  return{valid:true,remaining,owner};
 }
 function select(x,rank,k){
  if(rank>=count(x,k))throw new RangeError("rank");const original=rank,initial=x,ids=[],trace=[];let need=k;
  while(x){work.selection_steps++;const anchor=first(x);let found=false,skipped=0n;
   for(const id of s.by_edge[anchor]){const p=piece(id);work.mask_checks++;if((x&p.mask)!==p.mask)continue;const c=count(x^p.mask,need===undefined?undefined:need-1);
    if(rank>=c){rank-=c;skipped+=c;continue;}
    trace.push({remaining_before:x,anchor_edge:anchor,piece:id,skipped:String(skipped),residual_rank:String(rank),remaining_after:x^p.mask});ids.push(id);x^=p.mask;if(need!==undefined)need--;found=true;break;
   }
   if(!found)throw new Error("saved selection");
  }
  if(rank!==0n||(need!==undefined&&need!==0))throw new Error("selection terminal");
  return{mask:initial,requested_piece_count:k===undefined?null:k,rank:String(original),pieces:ids,piece_count:ids.length,trace};
 }
 function ranking(x,ids,k){
  const v=validate(x,ids);if(!v.valid)throw new RangeError(v.reason);if(k!==undefined&&k!==ids.length)throw new RangeError("wrong piece count");
  const initial=x,trace=[],canonical=[];let rank=0n,need=k;
  while(x){work.rank_steps++;const anchor=first(x),chosen=v.owner[anchor];let skipped=0n,found=false;
   for(const id of s.by_edge[anchor]){const p=piece(id);work.mask_checks++;if((x&p.mask)!==p.mask)continue;if(id===chosen){found=true;break;}skipped+=count(x^p.mask,need===undefined?undefined:need-1);}
   if(!found)throw new Error("rank piece");const p=piece(chosen);rank+=skipped;trace.push({remaining_before:x,anchor_edge:anchor,piece:chosen,skipped:String(skipped),remaining_after:x^p.mask});canonical.push(chosen);x^=p.mask;if(need!==undefined)need--;
  }
  return{mask:initial,requested_piece_count:k===undefined?null:k,rank:String(rank),pieces:canonical,piece_count:canonical.length,trace};
 }
 function profile(x){const a=row(x);return{mask:x,total:String(a.reduce((n,r)=>n+BigInt(r[1]),0n)),minimum:a[0][0],minimum_count:a[0][1],histogram:copy(a)};}
 function query(q){work.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"graph":return copy({vertices:s.vertices,edges:s.edges,full_mask:s.full_mask});
  case"cycles":return copy(s.pieces.filter(p=>p.kind==="cycle"));
  case"piece":return copy(piece(q.id));
  case"profile":return profile(mask(q.mask));
  case"count":{const x=mask(q.mask),k=kvalue(q.piece_count);return{mask:x,piece_count:k===undefined?null:k,count:String(count(x,k))};}
  case"select":return select(mask(q.mask),nat(q.rank),kvalue(q.piece_count));
  case"rank":return ranking(mask(q.mask),q.pieces,kvalue(q.piece_count));
  case"page":{const x=mask(q.mask),k=kvalue(q.piece_count),start=nat(q.start),total=count(x,k);if(start>total||!Number.isInteger(q.limit)||q.limit<0||q.limit>1000)throw new RangeError("page");const out=[];for(let r=start;r<total&&out.length<q.limit;r++)out.push(select(x,r,k));return{mask:x,piece_count:k===undefined?null:k,start:q.start,records:out};}
  case"validate":return{mask:mask(q.mask),pieces:copy(q.pieces),...validate(mask(q.mask),q.pieces)};
  case"force":{const x=mask(q.mask),v=validate(x,q.pieces,false);if(!v.valid)return{mask:x,...v};const a=profile(v.remaining);return{mask:x,required_pieces:copy(q.pieces),residual_mask:v.remaining,count:a.total,minimum:q.pieces.length+a.minimum,minimum_count:a.minimum_count,histogram:a.histogram.map(([k,c])=>[k+q.pieces.length,c])};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(work)};
}
module.exports={buildIndex,openIndex};
