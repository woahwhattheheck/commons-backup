"use strict";
const copy=x=>JSON.parse(JSON.stringify(x));
const abs=x=>x<0n?-x:x;
function gcd(a,b){a=abs(a);b=abs(b);while(b){const t=a%b;a=b;b=t;}return a;}
function rat(a,b=1n){if(b===0n)throw new RangeError("zero denominator");if(b<0n){a=-a;b=-b;}const g=gcd(a,b);return[a/g,b/g];}
const add=(a,b)=>rat(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);
const cmp=(a,b)=>{const d=a[0]*b[1]-b[0]*a[1];return d<0n?-1:d>0n?1:0;};
const pack=a=>a.map(String);
const unpack=a=>a.map(BigInt);
function numberInteger(x,lo,hi,label){if(!Number.isInteger(x)||x<lo||x>hi)throw new RangeError(label);return x;}
function rankValue(x){if(typeof x!=="string"||x.length>4096||! /^(0|[1-9][0-9]*)$/.test(x))throw new TypeError("rank");return BigInt(x);}
function fraction(x){if(!Array.isArray(x)||x.length!==2||!x.every(v=>typeof v==="string"&&v.length<=4096&&/^-?(0|[1-9][0-9]*)$/.test(v))||BigInt(x[1])<=0n)throw new TypeError("fraction");return rat(BigInt(x[0]),BigInt(x[1]));}
function pairRank(n,i,j){if(i>j){const t=i;i=j;j=t;}return i*(2*n-i-1)/2+j-i-1;}
function choose(n,k){let v=1n;for(let i=1;i<=k;i++)v=v*BigInt(n-i+1)/BigInt(i);return v;}
function buildIndex(input){
 const bound=numberInteger(input.max_denominator,1,16,"denominator bound"),params=[];
 const work={parameter_candidates:0,gcd_checks:0,points:0,chords:0,distance_sort_comparisons:0,states:0,candidate_extensions:0,rational_additions:0,objective_comparisons:0,optimal_arcs:0};
 for(let b=1;b<=bound;b++)for(let a=-b;a<b;a++){work.parameter_candidates++;work.gcd_checks++;if(gcd(BigInt(a),BigInt(b))===1n)params.push([a,b]);}
 params.sort((a,b)=>a[0]*b[1]-b[0]*a[1]);
 const n=params.length,k=numberInteger(input.vertices_per_polygon,3,Math.min(n,16),"polygon cardinality");
 const half=[],points=params.map(([a,b],id)=>{const A=BigInt(a),B=BigInt(b),u=B*B-A*A,v=2n*A*B,q=B*B+A*A;half.push([u,v,q]);work.points++;return{id,parameter:[String(a),String(b)],half_circle:[pack(rat(u,q)),pack(rat(v,q))],point:[pack(rat(u*u-v*v,q*q)),pack(rat(2n*u*v,q*q))]};});
 const chords=[];
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){const a=half[i],b=half[j];chords.push(rat(2n*abs(a[0]*b[1]-a[1]*b[0]),a[2]*b[2]));work.chords++;}
 const indices=chords.map((_,i)=>i).sort((a,b)=>{work.distance_sort_comparisons++;return cmp(chords[a],chords[b])||a-b;});
 const classes=[],pairClass=Array(chords.length);
 for(const id of indices){const last=classes[classes.length-1];if(!last||cmp(unpack(last.distance),chords[id])!==0)classes.push({id:classes.length,distance:pack(chords[id]),pair_ranks:[]});classes[classes.length-1].pair_ranks.push(id);pairClass[id]=classes.length-1;}
 const distance=(i,j)=>i===j?[0n,1n]:chords[pairRank(n,i,j)];
 const costs=Array.from({length:n},()=>Array(k).fill(null)),states=Array.from({length:n},()=>Array(k).fill(null));
 for(let i=n-1;i>=0;i--)for(let r=0;r<k&&r<=n-1-i;r++){
  work.states++;
  if(r===0){costs[i][r]=distance(i,0);states[i][r]={cost:pack(costs[i][r]),count:"1",choices:[]};continue;}
  let best=null,count=0n,choices=[];
  for(let j=i+1;j<=n-r;j++){const tail=costs[j][r-1];if(!tail)throw new Error("missing suffix");work.candidate_extensions++;const value=add(distance(i,j),tail);work.rational_additions++;const comparison=best===null?1:cmp(value,best);if(best!==null)work.objective_comparisons++;
   if(comparison>0){best=value;count=BigInt(states[j][r-1].count);choices=[j];}else if(comparison===0){count+=BigInt(states[j][r-1].count);choices.push(j);}
  }
  costs[i][r]=best;states[i][r]={cost:pack(best),count:String(count),choices};work.optimal_arcs+=choices.length;
 }
 const root=states[0][k-1];
 return{format:"rational-circle-polygon-index-v1",input:copy(input),points,chords:chords.map(pack),distance_classes:classes,pair_class:pairClass,states,summary:{points:n,chords:chords.length,distance_classes:classes.length,anchor:0,vertices_per_polygon:k,candidate_polygons:String(choose(n-1,k-1)),maximum_perimeter:root.cost,optimal_polygons:root.count,states:work.states,optimal_arcs:work.optimal_arcs},work};
}
function openIndex(s){
 if(!s||s.format!=="rational-circle-polygon-index-v1"||s.points.length!==s.summary.points||s.states.length!==s.points.length)throw new TypeError("snapshot");
 const n=s.points.length,k=s.summary.vertices_per_polygon,work={queries:0,state_reads:0,choice_visits:0,chord_reads:0,point_reads:0,distance_comparisons:0,rational_additions:0,selection_steps:0,rank_steps:0};
 const vertex=i=>numberInteger(i,0,n-1,"vertex id");
 function state(i,r){work.state_reads++;return s.states[i][r];}
 function distance(i,j){if(i===j)return["0","1"];work.chord_reads++;return s.chords[pairRank(n,i,j)];}
 function select(rank){
  const total=BigInt(s.summary.optimal_polygons);if(rank>=total)throw new RangeError("rank");const original=rank,vertices=[0],trace=[];let i=0,r=k-1;
  while(r){work.selection_steps++;const a=state(i,r);let found=false,skipped=0n;for(const j of a.choices){work.choice_visits++;const count=BigInt(state(j,r-1).count);if(rank>=count){rank-=count;skipped+=count;continue;}trace.push({from:i,remaining:r,next:j,skipped:String(skipped),residual_rank:String(rank)});vertices.push(j);i=j;r--;found=true;break;}if(!found)throw new Error("saved selection");}
  if(rank!==0n)throw new Error("terminal rank");return{rank:String(original),vertices,perimeter:copy(s.summary.maximum_perimeter),trace};
 }
 function polygon(ids){if(!Array.isArray(ids)||ids.length!==k||ids[0]!==0)throw new TypeError("anchored polygon");ids.forEach(vertex);for(let i=1;i<ids.length;i++)if(ids[i]<=ids[i-1])throw new RangeError("increasing polygon");return ids;}
 function ranking(ids){
  polygon(ids);let rank=0n,i=0,r=k-1;const trace=[];
  for(const chosen of ids.slice(1)){work.rank_steps++;const a=state(i,r);let found=false,skipped=0n;for(const j of a.choices){work.choice_visits++;if(j===chosen){found=true;break;}if(j>chosen)break;skipped+=BigInt(state(j,r-1).count);}if(!found)throw new RangeError("polygon is not in optimal family");rank+=skipped;trace.push({from:i,remaining:r,next:chosen,skipped:String(skipped)});i=chosen;r--;}
  return{rank:String(rank),vertices:ids.slice(),perimeter:copy(s.summary.maximum_perimeter),trace};
 }
 function query(q){work.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"point":{const i=vertex(q.id);work.point_reads++;return copy(s.points[i]);}
  case"points":work.point_reads+=n;return copy(s.points);
  case"chord":{const i=vertex(q.i),j=vertex(q.j),id=i===j?null:pairRank(n,i,j);return{i,j,pair_rank:id,class_id:id===null?null:s.pair_class[id],distance:copy(distance(i,j))};}
  case"distance_class":{const id=numberInteger(q.id,0,s.distance_classes.length-1,"class id");return copy(s.distance_classes[id]);}
  case"state":{const i=vertex(q.i),r=numberInteger(q.remaining,0,k-1,"remaining");return{i,remaining:r,state:copy(state(i,r))};}
  case"select":return select(rankValue(q.rank));
  case"rank":return ranking(q.vertices);
  case"page":{const start=rankValue(q.start),total=BigInt(s.summary.optimal_polygons),limit=numberInteger(q.limit,0,1000,"page limit");if(start>total)throw new RangeError("page");const out=[];for(let r=start;r<total&&out.length<limit;r++)out.push(select(r));return{start:q.start,records:out};}
  case"evaluate":{const ids=polygon(q.vertices),edges=[];let perimeter=[0n,1n];for(let p=0;p<k;p++){const i=ids[p],j=ids[(p+1)%k],d=distance(i,j);edges.push({i,j,distance:copy(d)});perimeter=add(perimeter,unpack(d));work.rational_additions++;}work.distance_comparisons++;return{vertices:ids.slice(),perimeter:pack(perimeter),maximum_perimeter:copy(s.summary.maximum_perimeter),comparison_to_maximum:cmp(perimeter,unpack(s.summary.maximum_perimeter)),edges};}
  case"neighbors":{const i=vertex(q.id),threshold=fraction(q.at_most),out=[];for(let j=0;j<n;j++)if(j!==i){const d=distance(i,j);work.distance_comparisons++;if(cmp(unpack(d),threshold)<=0)out.push({id:j,distance:copy(d)});}return{id:i,at_most:pack(threshold),neighbors:out};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(work)};
}
module.exports={buildIndex,openIndex};
