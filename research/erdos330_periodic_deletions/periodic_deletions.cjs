'use strict';
const SCHEMA='periodic-basis-finite-deletions/v1';
const copy=x=>JSON.parse(JSON.stringify(x));
function integer(x,name,min,max){if(!Number.isSafeInteger(x)||x<min||x>max)throw new RangeError(name);return x;}
function nat(x,name){if(typeof x==='bigint'){if(x<0n)throw new RangeError(name);return x;}if(typeof x==='number'){if(!Number.isSafeInteger(x)||x<0)throw new RangeError(name);return BigInt(x);}if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>2000)throw new TypeError(name+' canonical natural required');return BigInt(x);}
function compare(a,b){return a<b?-1:a>b?1:0;}
function ceil(a,b){return a>=0n?(a+b-1n)/b:a/b;}
function validate(input){
 const a=copy(input),m=integer(a.modulus,'modulus',2,64);
 if(!Array.isArray(a.members)||!a.members.length)throw new TypeError('members');
 a.members.forEach((x,i)=>{integer(x,'member',0,m-1);if(i&&x<=a.members[i-1])throw new RangeError('members increase');});
 if(!Array.isArray(a.ordered)||!Array.isArray(a.carry)||a.ordered.length!==m||a.carry.length!==m)throw new TypeError('profile');
 a.ordered.forEach((x,r)=>{integer(x,'positive inherited ordered coefficient',1,m);integer(a.carry[r],'inherited carry',0,x);});
 if(!Array.isArray(a.pairs)||a.pairs.length>m*m)throw new TypeError('inherited pairs');
 const members=new Set(a.members),seen=new Set();
 a.pairs.forEach(p=>{integer(p.a,'pair a',0,m-1);integer(p.b,'pair b',0,m-1);integer(p.residue,'pair residue',0,m-1);integer(p.carry,'pair carry',0,1);const k=p.a+':'+p.b;if(seen.has(k)||!members.has(p.a)||!members.has(p.b))throw new RangeError('pair shape');seen.add(k);});
 if(!Array.isArray(a.holes)||a.holes.length>128)throw new RangeError('at most 128 finite deletions');
 const holes=a.holes.map(x=>nat(x,'hole')).sort(compare);
 holes.forEach((d,i)=>{if(i&&d===holes[i-1])throw new RangeError('distinct holes');if(!members.has(Number(d%BigInt(m))))throw new RangeError('hole must belong to periodic source');});
 a.holes=holes.map(String);return a;
}
function buildIndex(input){
 const a=validate(input),m=a.modulus,M=BigInt(m),memberSet=new Set(a.members),holes=a.holes.map(BigInt);
 const buckets=Array.from({length:m},()=>[]),events=Array.from({length:m},()=>new Map()),thresholds=[],pairImpulses=[];
 const work={holes_classified:holes.length,threshold_membership_checks:0,threshold_events:0,new_unordered_hole_pairs:0,ordered_hole_pair_weight:0,impulse_updates:0,aggregate_events:0,affine_segments:0,integer_targets_enumerated:0,inherited_pair_sums_recomputed:0,inherited_profiles_recomputed:0};
 holes.forEach((d,i)=>buckets[Number(d%M)].push([String(d/M),i]));
 function event(r,q,delta){const k=String(q);events[r].set(k,(events[r].get(k)||0)+delta);}
 for(let i=0;i<holes.length;i++){const d=holes[i],s=Number(d%M),u=d/M;
  for(let r=0;r<m;r++){work.threshold_membership_checks++;if(memberSet.has((r-s+m)%m)){const q=u+BigInt(r<s?1:0);thresholds.push([r,String(q),i]);event(r,q,-2);work.threshold_events++;}}
 }
 for(let i=0;i<holes.length;i++)for(let j=i;j<holes.length;j++){
  const n=holes[i]+holes[j],r=Number(n%M),q=n/M,weight=i===j?1:2;
  pairImpulses.push([i,j,String(n),r,String(q),weight]);event(r,q,weight);event(r,q+1n,-weight);
  work.new_unordered_hole_pairs++;work.ordered_hole_pair_weight+=weight;work.impulse_updates+=2;
 }
 const eventRows=[],segments=[],gaps=[];
 for(let r=0;r<m;r++){
  if(!events[r].has('0'))events[r].set('0',0);
  const points=[...events[r]].map(([q,delta])=>[BigInt(q),delta]).sort((x,y)=>compare(x[0],y[0]));
  let intercept=a.ordered[r]-a.carry[r];const list=[];
  for(let k=0;k<points.length;k++){
   const [lo,delta]=points[k];intercept+=delta;const hi=k+1<points.length?points[k+1][0]-1n:null;
   eventRows.push([r,String(lo),delta]);const last=list.at(-1);
   if(last&&last[2]===intercept){last[1]=hi===null?null:String(hi);}else list.push([String(lo),hi===null?null:String(hi),intercept]);
  }
  for(const row of list){const lo=BigInt(row[0]),hi=row[1]===null?null:BigInt(row[1]),R=BigInt(a.ordered[r]),b=BigInt(row[2]);
   if(R*lo+b<0n)throw new Error('inherited premise/event count produced negative representations');
   if((-b)%R===0n){const q=(-b)/R;if(q>=lo&&(hi===null||q<=hi))gaps.push(String(M*q+BigInt(r)));}
  }
  segments.push(list);work.affine_segments+=list.length;
 }
 gaps.sort((x,y)=>compare(BigInt(x),BigInt(y)));work.aggregate_events=eventRows.length;
 const conductor=gaps.length?String(BigInt(gaps.at(-1))+1n):'0';
 return{schema:SCHEMA,input:a,modulus:m,threshold_schema:['target_residue','start_quotient','hole_index'],thresholds,hole_pair_schema:['first_hole','second_hole','target','target_residue','quotient','ordered_weight'],pair_impulses:pairImpulses,event_schema:['target_residue','quotient','intercept_delta'],events:eventRows,segment_schema:['first_quotient','last_quotient_or_null','intercept'],segments,deleted_quotients:buckets,gaps,summary:{holes:holes.length,thresholds:thresholds.length,hole_pairs:pairImpulses.length,events:eventRows.length,segments:work.affine_segments,gaps:gaps.length,conductor,largest_gap:gaps.length?gaps.at(-1):null,guaranteed_coverage_from:String(M*BigInt(2*holes.length+1)),tail_slopes:a.ordered.slice(),density:[a.members.length,m]},work};
}
function openIndex(saved){
 const d=typeof saved==='string'?JSON.parse(saved):copy(saved);
 if(!d||d.schema!==SCHEMA)throw new TypeError('saved schema');
 const a=validate(d.input),m=a.modulus,M=BigInt(m),members=new Set(a.members),holeSet=new Set(a.holes),holes=a.holes.map(BigInt);
 if(!Array.isArray(d.segments)||d.segments.length!==m||!Array.isArray(d.deleted_quotients)||d.deleted_quotients.length!==m||!Array.isArray(d.gaps))throw new TypeError('saved shapes');
 const segments=d.segments.map((list,r)=>{if(!Array.isArray(list)||!list.length)throw new TypeError('segments');return list.map((row,i)=>{if(!Array.isArray(row)||row.length!==3)throw new TypeError('segment');const lo=nat(row[0],'segment start'),hi=row[1]===null?null:nat(row[1],'segment end');integer(row[2],'intercept',-1000000,1000000);if(i===0&&lo!==0n||hi!==null&&hi<lo||i===list.length-1&&hi!==null)throw new RangeError('segment coverage');if(i&&list[i-1][1]!==String(lo-1n))throw new RangeError('segment adjacency');return[lo,hi,BigInt(row[2])];});});
 const deleted=d.deleted_quotients.map(rows=>rows.map(([q,i])=>[nat(q,'deleted quotient'),integer(i,'hole index',0,holes.length-1)]));
 const gaps=d.gaps.map(x=>nat(x,'gap'));gaps.forEach((x,i)=>{if(i&&x<=gaps[i-1])throw new RangeError('gap order');});
 const impulses=new Map();for(const row of d.pair_impulses){const k=row[2];if(!impulses.has(k))impulses.set(k,[]);impulses.get(k).push(row);}
 const work={queries:0,segments_indexed:segments.reduce((s,x)=>s+x.length,0),impulse_records_indexed:d.pair_impulses.length,gap_records_indexed:gaps.length,segment_search_steps:0,mass_segment_scans:0,gap_search_steps:0,branch_pair_scans:0,deleted_quotient_scans:0,excluded_positions:0,pair_selection_steps:0,pair_rank_steps:0,threshold_explanation_scans:0,new_events:0,new_segments:0,inherited_pair_sums_recomputed:0,inherited_profiles_recomputed:0};
 function upperGap(n){let lo=0,hi=gaps.length;while(lo<hi){work.gap_search_steps++;const mid=(lo+hi)>>1;if(gaps[mid]<=n)lo=mid+1;else hi=mid;}return lo;}
 function locate(n){const r=Number(n%M),q=n/M,list=segments[r];let lo=0,hi=list.length;while(lo<hi){work.segment_search_steps++;const mid=(lo+hi)>>1;if(list[mid][0]<=q)lo=mid+1;else hi=mid;}return{r,q,index:lo-1,row:list[lo-1]};}
 function point(n){const t=locate(n),ordered=BigInt(a.ordered[t.r])*t.q+t.row[2],half=n/2n,diagonal=n%2n===0n&&members.has(Number(half%M))&&!holeSet.has(String(half))?1n:0n;return{target:String(n),residue:t.r,quotient:String(t.q),segment:t.index,ordered:String(ordered),diagonal:String(diagonal),unordered:String((ordered+diagonal)/2n),covered:ordered>0n};}
 function mass(lo,hi){
  let ordered=0n;
  for(let r=0;r<m;r++){let qlo=ceil(lo-BigInt(r),M);if(qlo<0n)qlo=0n;const qhi=hi>=BigInt(r)?(hi-BigInt(r))/M:-1n;
   for(const [x,y,b]of segments[r]){work.mass_segment_scans++;const left=qlo>x?qlo:x,right=y===null?qhi:qhi<y?qhi:y;if(left<=right){const count=right-left+1n;ordered+=BigInt(a.ordered[r])*(left+right)*count/2n+b*count;}}
  }
  const lower=(lo+1n)/2n,upper=hi/2n;let diagonal=0n;
  if(lower<=upper){for(const r of a.members){const min=ceil(lower-BigInt(r),M),max=upper>=BigInt(r)?(upper-BigInt(r))/M:-1n,l=min<0n?0n:min;if(l<=max)diagonal+=max-l+1n;}for(const h of holes){work.deleted_quotient_scans++;if(h>=lower&&h<=upper)diagonal--;}}
  return{lo:String(lo),hi:String(hi),ordered:String(ordered),diagonal:String(diagonal),unordered:String((ordered+diagonal)/2n)};
 }
 function branches(n){
  const r=Number(n%M),q=n/M,out=[];
  for(const p of a.pairs){work.branch_pair_scans++;if(p.residue!==r)continue;const Q=q-BigInt(p.carry);if(Q<0n)continue;const bad=new Set();
   for(const [u]of deleted[p.a]){work.deleted_quotient_scans++;if(u<=Q)bad.add(String(u));}
   for(const [v]of deleted[p.b]){work.deleted_quotient_scans++;if(v<=Q)bad.add(String(Q-v));}
   const excluded=[...bad].map(BigInt).sort(compare);work.excluded_positions+=excluded.length;
   out.push({pair_id:p.id,a:p.a,b:p.b,split_sum:String(Q),excluded:excluded.map(String),count:String(Q+1n-BigInt(excluded.length))});
  }
  return{target:String(n),ordering:'retained ordered residue-pair order, then first quotient',branches:out,total:String(out.reduce((s,b)=>s+BigInt(b.count),0n))};
 }
 return{
  summary(){work.queries++;return{...copy(d.summary),construction_work:copy(d.work)};},
  point(n){work.queries++;return point(nat(n,'target'));},
  explain(n){work.queries++;const N=nat(n,'target'),p=point(N),active=[];for(const t of d.thresholds){work.threshold_explanation_scans++;if(t[0]===p.residue&&BigInt(t[1])<=BigInt(p.quotient))active.push(t[2]);}const repairs=copy(impulses.get(String(N))||[]);return{...p,baseline:String(BigInt(a.ordered[p.residue])*(BigInt(p.quotient)+1n)-BigInt(a.carry[p.residue])),active_deleted_indices:active,double_subtraction:2*active.length,hole_pair_repairs:repairs,repair_weight:repairs.reduce((s,x)=>s+x[5],0)};},
  representationMass(lo,hi){work.queries++;const L=nat(lo,'lo'),H=nat(hi,'hi');if(L>H)throw new RangeError('interval');return mass(L,H);},
  coverageCount(bound){work.queries++;const N=nat(bound,'bound'),missing=upperGap(N);return{bound:String(N),covered:String(N+1n-BigInt(missing)),missing};},
  coverageRank(n){work.queries++;const N=nat(n,'target'),p=point(N);return{...p,rank:p.covered?String(N-BigInt(upperGap(N))):null};},
  coverageSelect(rank){work.queries++;const k=nat(rank,'rank');let lo=k,hi=k+BigInt(gaps.length);while(lo<hi){const mid=(lo+hi)>>1n;if(mid+1n-BigInt(upperGap(mid))>k)hi=mid;else lo=mid+1n;}return{rank:String(k),...point(lo)};},
  gapPage(offset=0,limit=64){work.queries++;integer(offset,'offset',0,gaps.length);integer(limit,'limit',0,256);return{offset,total:gaps.length,next:Math.min(gaps.length,offset+limit),values:gaps.slice(offset,offset+limit).map(String)};},
  residue(r){work.queries++;integer(r,'residue',0,m-1);return{residue:r,slope:a.ordered[r],segments:copy(d.segments[r])};},
  pairBranches(n){work.queries++;return branches(nat(n,'target'));},
  pairSelect(n,rank){work.queries++;const N=nat(n,'target'),K=nat(rank,'rank'),plan=branches(N);if(K>=BigInt(plan.total))throw new RangeError('pair rank');let rest=K;for(const b of plan.branches){const count=BigInt(b.count);if(rest>=count){rest-=count;continue;}let u=rest;for(const s of b.excluded){work.pair_selection_steps++;const v=BigInt(s);if(v<=u)u++;else break;}const x=BigInt(b.a)+M*u;return{target:String(N),rank:String(K),total:plan.total,pair:[String(x),String(N-x)],pair_id:b.pair_id,first_quotient:String(u),ordering:plan.ordering};}throw new Error('selection');},
  pairRank(x,y){work.queries++;const X=nat(x,'x'),Y=nat(y,'y'),plan=branches(X+Y),ar=Number(X%M),br=Number(Y%M),u=X/M;let before=0n;for(const b of plan.branches){if(b.a===ar&&b.b===br){if(u>BigInt(b.split_sum)||b.excluded.includes(String(u)))return{target:plan.target,pair:[String(X),String(Y)],member:false,rank:null};let less=0n;for(const z of b.excluded){work.pair_rank_steps++;if(BigInt(z)<u)less++;else break;}return{target:plan.target,pair:[String(X),String(Y)],member:true,rank:String(before+u-less),total:plan.total};}before+=BigInt(b.count);}return{target:plan.target,pair:[String(X),String(Y)],member:false,rank:null};},
  work(){return copy(work);}
 };
}
module.exports={buildIndex,openIndex,SCHEMA};
