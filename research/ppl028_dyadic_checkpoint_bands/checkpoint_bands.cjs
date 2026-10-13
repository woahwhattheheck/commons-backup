"use strict";
function assert(x,m){if(!x)throw new TypeError(m);}
function nat(s){assert(typeof s==="string"&&/^(0|[1-9][0-9]*)$/.test(s)&&s.length<=2048,"canonical nonnegative decimal string required");return BigInt(s);}
function ceil(a,b){assert(b>0n,"positive divisor required");return a>=0n?(a+b-1n)/b:a/b;}
function compile(input){
 const r=nat(input.residue),M=nat(input.modulus),lo=nat(input.parameter_lower),hi=nat(input.parameter_upper),H=input.thresholds.map(nat);
 assert(lo>=1n&&hi>=lo&&M>0n&&r<M,"invalid parameter cylinder/window");
 for(let i=0;i<H.length;i++)assert(H[i]>0n&&(!i||H[i]>H[i-1]),"thresholds not increasing");
 const work={savedBlockCopies:0,newSlopes:0,thresholdEntryDivisions:0,eventComparisons:0,newCells:0,newOrbitSteps:0,newValuations:0,anchorRecalculations:0,blockCompositions:0};
 const lines=[{checkpoint:0,kind:"initial",source_block:null,intercept:input.residue,slope:input.modulus}];
 for(const b of input.blocks){
  const den=1n<<BigInt(b.shift);assert(M%den===0n,"cylinder modulus does not cover selected shift");
  const slope=nat(b.A)*(M/den);assert(slope>0n,"nonpositive slope");
  lines.push({checkpoint:b.checkpoint,kind:"dyadic",source_block:b.source_block,intercept:b.observed_end,slope:String(slope)});
  work.savedBlockCopies++;work.newSlopes++;
 }
 const events=[],cuts=new Map([[String(lo),[]]]);
 for(let j=0;j<lines.length;j++)for(let b=0;b<H.length;b++){
  const raw=ceil(H[b]-nat(lines[j].intercept),nat(lines[j].slope)),entry=raw<lo?lo:raw;
  const e={coordinate:j,checkpoint:lines[j].checkpoint,threshold_index:b,threshold:String(H[b]),unclamped_entry:String(raw),entry:String(entry),in_window:entry<=hi};
  events.push(e);work.thresholdEntryDivisions++;
  if(entry>lo&&entry<=hi){const k=String(entry);if(!cuts.has(k))cuts.set(k,[]);cuts.get(k).push(events.length-1);}
 }
 const starts=Array.from(cuts.keys()).map(BigInt).sort((a,b)=>{work.eventComparisons++;return a<b?-1:a>b?1:0;});
 const cells=[];
 for(let i=0;i<starts.length;i++){
  const left=starts[i],right=i+1<starts.length?starts[i+1]-1n:hi;
  if(right<left)continue;
  const bands=lines.map((_,j)=>events.filter(e=>e.coordinate===j&&BigInt(e.entry)<=left).length);
  cells.push({id:cells.length,lower:String(left),upper:String(right),count:String(right-left+1n),bands,entry_events:cuts.get(String(left))});work.newCells++;
 }
 return {schema:"commons.ppl028.dyadic_checkpoint_bands/v1",input_id:input.id,residue:input.residue,modulus:input.modulus,parameter_lower:input.parameter_lower,parameter_upper:input.parameter_upper,thresholds:input.thresholds,lines,events,cells,total_parameters:String(hi-lo+1n),band_convention:"band b is [H_(b-1),H_b), with outer bounds 0 and infinity; threshold equality enters higher band",work,scope:"Saved dyadic checkpoints only; initial state is coordinate zero, not a dyadic transition."};
}
function createReader(c){
 assert(c.schema==="commons.ppl028.dyadic_checkpoint_bands/v1","unrecognized certificate");
 const lo=BigInt(c.parameter_lower),hi=BigInt(c.parameter_upper),M=BigInt(c.modulus),r=BigInt(c.residue),n=c.lines.length,maxBand=c.thresholds.length,cache=new Map();
 const work={conditionsBuilt:0,conditionHits:0,cellsScanned:0,bandComparisons:0,selectedIntervals:0,selectionIntervals:0,rankingIntervals:0,seedProjections:0,seedResidueChecks:0,lineEvaluations:0,firstCheckpointInspections:0,marginalCells:0,newEvents:0,newOrbitSteps:0,newValuations:0,blockCompositions:0};
 function condition(q={}){
  let lower=q.lower===undefined?lo:nat(q.lower),upper=q.upper===undefined?hi:nat(q.upper);if(lower<lo)lower=lo;if(upper>hi)upper=hi;
  const min=q.min_bands||Array(n).fill(0),max=q.max_bands||Array(n).fill(maxBand);
  assert(Array.isArray(min)&&Array.isArray(max)&&min.length===n&&max.length===n,"ten band bounds required");
  for(let i=0;i<n;i++)assert(Number.isInteger(min[i])&&Number.isInteger(max[i])&&min[i]>=0&&min[i]<=maxBand&&max[i]>=0&&max[i]<=maxBand,"invalid band bound");
  const key=JSON.stringify([String(lower),String(upper),min,max]);if(cache.has(key)){work.conditionHits++;return cache.get(key);}
  work.conditionsBuilt++;const intervals=[];let count=0n;
  if(lower<=upper)for(const cell of c.cells){
   work.cellsScanned++;let allowed=true;for(let i=0;i<n;i++){work.bandComparisons++;if(cell.bands[i]<min[i]||cell.bands[i]>max[i]){allowed=false;break;}}
   if(!allowed)continue;const a=BigInt(cell.lower)>lower?BigInt(cell.lower):lower,b=BigInt(cell.upper)<upper?BigInt(cell.upper):upper;
   if(a>b)continue;const size=b-a+1n;intervals.push({cell_id:cell.id,lower:String(a),upper:String(b),count:String(size),rank_start:String(count),bands:cell.bands});count+=size;work.selectedIntervals++;
  }
  const out={key,lower:String(lower),upper:String(upper),min_bands:min,max_bands:max,count:String(count),intervals,empty:count===0n};cache.set(key,out);return out;
 }
 function project(t){work.seedProjections++;return String(r+M*t);}
 function select(q){
  const x=condition(q),rank=nat(q.rank);if(rank>=BigInt(x.count))return {status:"OUT_OF_RANGE",count:x.count};
  for(const interval of x.intervals){work.selectionIntervals++;const offset=rank-BigInt(interval.rank_start);if(offset>=0n&&offset<BigInt(interval.count)){const t=BigInt(interval.lower)+offset;return {status:"FOUND",rank:q.rank,count:x.count,parameter:String(t),seed:project(t),cell_id:interval.cell_id,bands:interval.bands};}}
  throw Error("selection invariant");
 }
 function rank(q){
  const x=condition(q);let t;
  if(q.seed!==undefined){
   const seed=nat(q.seed);work.seedResidueChecks++;if(seed<r||(seed-r)%M!==0n)return {status:"NOT_IN_CYLINDER",count:x.count};t=(seed-r)/M;
  }else t=nat(q.parameter);
  if(t<lo||t>hi)return {status:"OUTSIDE_DECLARED_WINDOW",count:x.count};
  for(const interval of x.intervals){work.rankingIntervals++;if(t>=BigInt(interval.lower)&&t<=BigInt(interval.upper))return {status:"FOUND",parameter:String(t),rank:String(BigInt(interval.rank_start)+t-BigInt(interval.lower)),count:x.count,cell_id:interval.cell_id};}
  return {status:"NOT_IN_CONDITION",count:x.count};
 }
 function locate(t){
  for(const cell of c.cells)if(t>=BigInt(cell.lower)&&t<=BigInt(cell.upper))return cell;
  return null;
 }
 function state(q){
  const t=nat(q.parameter);assert(t>=lo&&t<=hi,"parameter outside declared window");const cell=locate(t),values=[];
  let peak=null,peakCoordinates=[];
  for(let i=0;i<n;i++){const value=BigInt(c.lines[i].intercept)+BigInt(c.lines[i].slope)*t;work.lineEvaluations++;values.push({coordinate:i,checkpoint:c.lines[i].checkpoint,kind:c.lines[i].kind,value:String(value),band:cell.bands[i]});if(peak===null||value>peak){peak=value;peakCoordinates=[i];}else if(value===peak)peakCoordinates.push(i);}
  return {parameter:q.parameter,seed:project(t),cell_id:cell.id,values,checkpoint_peak:String(peak),peak_coordinates:peakCoordinates};
 }
 function firstCheckpoint(q){
  const t=nat(q.parameter);assert(t>=lo&&t<=hi&&Number.isInteger(q.at_least_band)&&q.at_least_band>=0&&q.at_least_band<=maxBand,"invalid first-checkpoint query");
  const cell=locate(t),start=q.include_initial===true?0:1;
  for(let i=start;i<n;i++){work.firstCheckpointInspections++;if(cell.bands[i]>=q.at_least_band)return {status:"FOUND",coordinate:i,checkpoint:c.lines[i].checkpoint,kind:c.lines[i].kind,band:cell.bands[i],initial_included:start===0};}
  return {status:"NO_SAVED_CHECKPOINT",initial_included:start===0};
 }
 function marginals(q){
  const x=condition(q),rows=Array.from({length:n},()=>Array(maxBand+1).fill(0n));
  for(const interval of x.intervals){work.marginalCells++;for(let i=0;i<n;i++)rows[i][interval.bands[i]]+=BigInt(interval.count);}
  return {count:x.count,rows:rows.map((a,i)=>({coordinate:i,checkpoint:c.lines[i].checkpoint,kind:c.lines[i].kind,band_counts:a.map(String)}))};
 }
 return {condition,select,rank,state,firstCheckpoint,marginals,summary:()=>({coordinates:n,dyadic_checkpoints:n-1,cells:c.cells.length,events:c.events.length,total_parameters:c.total_parameters,parameter_lower:c.parameter_lower,parameter_upper:c.parameter_upper}),snapshot:()=>({conditions:Array.from(cache.values())}),work:()=>({...work})};
}
module.exports={compile,createReader};
