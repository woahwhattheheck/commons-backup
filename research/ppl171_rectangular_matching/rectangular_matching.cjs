"use strict";
const SCHEMA="rectangular-matching-certificate/v1";
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+" out of range");return x;}
function popcount(x){let n=0;while(x){x&=x-1;n++;}return n;}
function rankInteger(x){if(typeof x==="bigint"&&x>=0n)return x;if(typeof x==="string"&&/^(0|[1-9][0-9]*)$/.test(x))return BigInt(x);if(Number.isSafeInteger(x)&&x>=0)return BigInt(x);throw new RangeError("rank must be a nonnegative exact integer");}
function compile(input){
 if(!input||input.schema!=="rectangular-matching-input/v1")throw new TypeError("input schema");
 const D=integer(input.denominator,1,1000000,"denominator"),n=input.X?.length;
 integer(n,1,10,"cloud size");if(!Array.isArray(input.Y)||input.Y.length!==n)throw new TypeError("equal cloud sizes");
 for(const cloud of [input.X,input.Y])for(const p of cloud){if(!Array.isArray(p)||p.length!==2)throw new TypeError("point");p.forEach(x=>integer(x,0,D,"coordinate"));}
 const full=(1<<n)-1, costs=input.X.map(p=>input.Y.map(q=>[Math.abs(p[0]-q[0]),Math.abs(p[1]-q[1])]));
 const work={coordinate_differences:2*n*n,states:full+1,assignment_branches:0,histogram_transitions:0,histogram_cells:1,pareto_comparisons:0,permutation_enumerations:0,old_matching_or_quota_work:0};
 const states=new Array(full+1);states[full]=[[0,0,"1"]];
 for(let mask=full-1;mask>=0;mask--){
  const i=popcount(mask),map=new Map();
  for(let j=0;j<n;j++)if(!(mask&(1<<j))){
   work.assignment_branches++;
   for(const [x,y,c] of states[mask|(1<<j)]){
    work.histogram_transitions++;
    const bx=Math.max(x,costs[i][j][0]),by=Math.max(y,costs[i][j][1]),key=bx+","+by;
    map.set(key,(map.get(key)||0n)+BigInt(c));
   }
  }
  states[mask]=Array.from(map,([key,c])=>[...key.split(",").map(Number),c.toString()]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  work.histogram_cells+=states[mask].length;
 }
 let bestY=Infinity;const frontier=[];
 for(const [x,y,c] of states[0]){work.pareto_comparisons++;if(y<bestY){frontier.push({maxX:x,maxY:y,exact_count:c});bestY=y;}}
 const total=states[0].reduce((a,r)=>a+BigInt(r[2]),0n).toString();
 return {schema:SCHEMA,input:JSON.parse(JSON.stringify(input)),n,denominator:D,costs,states,frontier,summary:{matchings:total,signatures:states[0].length,pareto_points:frontier.length},construction_work:work};
}
function createIndex(cert){
 if(!cert||cert.schema!==SCHEMA)throw new TypeError("certificate schema");
 const n=integer(cert.n,1,10,"cloud size"),D=integer(cert.denominator,1,1000000,"denominator"),full=(1<<n)-1;
 if(!Array.isArray(cert.states)||cert.states.length!==full+1||!Array.isArray(cert.costs)||cert.costs.length!==n)throw new TypeError("certificate shape");
 const cache=new Map(),conditions=new Map(),hallCache=new Map();
 const work={saved_cell_scans:0,count_cache_hits:0,condition_cache_hits:0,hall_cache_hits:0,prefix_edge_reads:0,rank_candidate_edges:0,select_candidate_edges:0,hall_edge_reads:0,hall_subset_unions:0,hall_cardinalities:0,new_distributions:0,new_coordinate_costs:0};
 function norm(q={}){
  if(!q||typeof q!=="object"||Array.isArray(q))throw new TypeError("condition");
  const maxX=q.maxX===undefined?D:integer(q.maxX,0,D,"maxX"),maxY=q.maxY===undefined?D:integer(q.maxY,0,D,"maxY");
  const prefix=q.prefix===undefined?[]:q.prefix;if(!Array.isArray(prefix)||prefix.length>n)throw new RangeError("prefix");
  let mask=0,violation=null,bx=0,by=0;
  const copy=prefix.map((j,i)=>{integer(j,0,n-1,"Y label");if(mask&(1<<j))throw new RangeError("repeated Y label");mask|=1<<j;const [x,y]=cert.costs[i][j];work.prefix_edge_reads++;bx=Math.max(bx,x);by=Math.max(by,y);if(!violation&&(x>maxX||y>maxY))violation={row:i,column:j,cost:[x,y],maxX,maxY};return j;});
  return {maxX,maxY,prefix:copy,mask,prefix_maxima:[bx,by],violation};
 }
 function count(mask,x,y){
  const key=mask+"|"+x+"|"+y;if(cache.has(key)){work.count_cache_hits++;return BigInt(cache.get(key));}
  let c=0n;for(const [bx,by,v] of cert.states[mask]){work.saved_cell_scans++;if(bx<=x&&by<=y)c+=BigInt(v);}
  cache.set(key,c.toString());return c;
 }
 function normalizedCondition(q){
  const a=norm(q),key=a.maxX+"|"+a.maxY+"|"+a.prefix.join(",");
  if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}
  const c=a.violation?0n:count(a.mask,a.maxX,a.maxY);
  const out={...a,count:c.toString()};conditions.set(key,out);return out;
 }
 function select(q,r){
  const a=normalizedCondition(q);let k=rankInteger(r),c=BigInt(a.count);if(k>=c)throw new RangeError("rank outside family");
  let mask=a.mask;const p=a.prefix.slice(),trace=[];
  for(let i=p.length;i<n;i++)for(let j=0;j<n;j++)if(!(mask&(1<<j))){
   work.select_candidate_edges++;const [x,y]=cert.costs[i][j];if(x>a.maxX||y>a.maxY)continue;
   const v=count(mask|(1<<j),a.maxX,a.maxY);
   if(k>=v){k-=v;continue;}
   trace.push({row:i,column:j,branch_count:v.toString(),residual_rank:k.toString()});p.push(j);mask|=1<<j;break;
  }
  return {permutation:p,rank:rankInteger(r).toString(),count:a.count,trace};
 }
 function rank(q,p){
  const a=normalizedCondition(q);if(a.violation)throw new RangeError("prefix violates bounds");
  if(!Array.isArray(p)||p.length!==n)throw new RangeError("complete permutation required");
  const seen=new Set(p);if(seen.size!==n)throw new RangeError("not a permutation");p.forEach(j=>integer(j,0,n-1,"Y label"));
  for(let i=0;i<a.prefix.length;i++)if(p[i]!==a.prefix[i])throw new RangeError("prefix mismatch");
  let r=0n,mask=a.mask;
  for(let i=a.prefix.length;i<n;i++){
   const chosen=p[i];for(let j=0;j<chosen;j++)if(!(mask&(1<<j))){
    work.rank_candidate_edges++;const [x,y]=cert.costs[i][j];if(x<=a.maxX&&y<=a.maxY)r+=count(mask|(1<<j),a.maxX,a.maxY);
   }
   const [x,y]=cert.costs[i][chosen];if((mask&(1<<chosen))||x>a.maxX||y>a.maxY)throw new RangeError("permutation outside family");
   mask|=1<<chosen;
  }
  return {rank:r.toString(),count:a.count};
 }
 function obstruction(q){
  const a=normalizedCondition(q),key=a.maxX+"|"+a.maxY+"|"+a.prefix.join(",");
  if(hallCache.has(key)){work.hall_cache_hits++;return hallCache.get(key);}
  if(a.violation){const o={kind:"prefix-violation",edge:a.violation};hallCache.set(key,o);return o;}
  if(BigInt(a.count)>0n){const o={kind:"feasible",count:a.count};hallCache.set(key,o);return o;}
  const start=a.prefix.length,m=n-start,neighbors=[];
  for(let i=start;i<n;i++){let ys=0;for(let j=0;j<n;j++)if(!(a.mask&(1<<j))){work.hall_edge_reads++;const [x,y]=cert.costs[i][j];if(x<=a.maxX&&y<=a.maxY)ys|=1<<j;}neighbors.push(ys);}
  const unions=new Array(1<<m).fill(0);
  for(let s=1;s<(1<<m);s++){
   const bit=s&-s,index=31-Math.clz32(bit);unions[s]=unions[s^bit]|neighbors[index];work.hall_subset_unions++;
   const leftCount=popcount(s),rightCount=popcount(unions[s]);work.hall_cardinalities+=2;
   if(rightCount<leftCount){
    const left=[],right=[];for(let i=0;i<m;i++)if(s&(1<<i))left.push(start+i);for(let j=0;j<n;j++)if(unions[s]&(1<<j))right.push(j);
    const o={kind:"hall-deficiency",left,neighbors:right,deficiency:leftCount-rightCount,remaining_rows:m,unused_columns:Array.from({length:n},(_,i)=>i).filter(j=>!(a.mask&(1<<j))),row_neighbor_masks:neighbors};hallCache.set(key,o);return o;
   }
  }
  throw new Error("inconsistent saved zero count: no Hall witness");
 }
 return {
  summary:()=>({n,denominator:D,...cert.summary,frontier:cert.frontier,construction_work:cert.construction_work}),
  distribution:(mask=0)=>{integer(mask,0,full,"used mask");return {used_mask:mask,next_row:popcount(mask),histogram:cert.states[mask]};},
  condition:q=>normalizedCondition(q),select,rank,obstruction,
  caches:()=>({counts:Array.from(cache,([key,count])=>({key,count})),conditions:Array.from(conditions.values()),obstructions:Array.from(hallCache,([key,value])=>({key,value}))}),
  work:()=>({...work})
 };
}
module.exports={compile,createIndex};
