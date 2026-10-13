"use strict";
const VERSION="1.0.0",SCHEMA="commons.ap-coloring-dag.v1";
function fail(s){throw new Error(s);}
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside limits");return x;}
function pop(x){let n=0;while(x){x&=x-1;n++;}return n;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function rankValue(x){if(typeof x==="number"){if(!Number.isSafeInteger(x)||x<0)fail("rank must be nonnegative safe integer or decimal");x=String(x);}if(typeof x!=="string"||! /^(0|[1-9][0-9]*)$/.test(x)||x.length>100)fail("rank decimal limit");return BigInt(x);}
function normalize(rows,color,stats){const sorted=Array.from(new Set(rows)).sort((a,b)=>pop(a)-pop(b)||a-b),kept=[],discarded=[];for(const m of sorted){let by=null;for(const k of kept){stats.subsumption_comparisons++;if((k&m)===k){by=k;break;}}if(by===null)kept.push(m);else{discarded.push({color,mask:m,by});stats.discarded_supersets++;}}kept.sort((a,b)=>a-b);return{kept,discarded};}
function compileAPColorings(input,options={}){
 if(!input)fail("input required");const n=integer(input.n,2,24,"n"),k=integer(input.length,2,n,"progression length"),maxNodes=integer(options.max_nodes===undefined?300000:options.max_nodes,1,500000,"max_nodes"),maxCoefficients=integer(options.max_coefficients===undefined?1000000:options.max_coefficients,1,2000000,"max_coefficients");
 const progressions=[];for(let d=1;(k-1)*d<n;d++)for(let a=1;a+(k-1)*d<=n;a++){const vertices=Array.from({length:k},(_,i)=>a+i*d),mask=vertices.reduce((s,x)=>s+2**(x-1),0);progressions.push({id:progressions.length,start:a,difference:d,vertices,mask});}
 const stats={progressions_generated:progressions.length,recursive_calls:0,memo_hits:0,nodes:0,transitions:0,rejecting_transitions:0,residual_masks_visited:0,subsumption_comparisons:0,discarded_supersets:0,coefficient_cells:0,coefficient_additions:0,individual_colorings_enumerated:0,old_three_term_family_recomputed:0};
 const nodes=[],memo=new Map();
 function visit(level,forbidden){
  stats.recursive_calls++;const key=level+"|"+forbidden[0].join(",")+"|"+forbidden[1].join(",");if(memo.has(key)){stats.memo_hits++;return memo.get(key);}
  if(nodes.length>=maxNodes)fail("node budget exhausted; no final snapshot");const size=n-level+1;if(stats.coefficient_cells+size>maxCoefficients)fail("coefficient budget exhausted; no final snapshot");
  const id=nodes.length,row={id,level,forbidden:forbidden.map(a=>a.slice()),arcs:[],coefficients:null};nodes.push(row);memo.set(key,id);stats.nodes++;stats.coefficient_cells+=size;
  if(level===n){if(forbidden[0].length||forbidden[1].length)fail("nonempty terminal residual");row.coefficients=["1"];return id;}
  const bit=2**level;
  for(let color=0;color<2;color++){
   stats.transitions++;const candidates=[[],[]];let rejected=null,removed=0;
   for(let c=0;c<2;c++){for(const mask of forbidden[c]){stats.residual_masks_visited++;if(mask&bit){if(c===color){const tail=mask-bit;if(tail===0){rejected={color,mask,position:level+1};break;}candidates[c].push(tail);}else removed++;}else candidates[c].push(mask);}if(rejected)break;}
   if(rejected){row.arcs.push({color,child:-1,rejection:rejected});stats.rejecting_transitions++;continue;}
   const a=normalize(candidates[0],0,stats),b=normalize(candidates[1],1,stats),child=visit(level+1,[a.kept,b.kept]);row.arcs.push({color,child,satisfied_removed:removed,discarded:a.discarded.concat(b.discarded)});
  }
  const coeff=Array(size).fill(0n);for(const arc of row.arcs)if(arc.child>=0){const child=nodes[arc.child].coefficients;for(let j=0;j<child.length;j++){coeff[j+arc.color]+=BigInt(child[j]);stats.coefficient_additions++;}}row.coefficients=coeff.map(String);return id;
 }
 const all=progressions.map(a=>a.mask).sort((a,b)=>a-b),root=visit(0,[all,all]),coeff=nodes[root].coefficients,total=coeff.reduce((s,x)=>s+BigInt(x),0n);
 return{schema:SCHEMA,version:VERSION,input:{n,length:k,provenance:input.provenance===undefined?null:copy(input.provenance)},progressions,root,nodes,summary:{n,length:k,colors:[0,1],color_labels_distinguished:true,progression_count:progressions.length,total:total.toString(),by_ones:coeff.slice(),node_count:nodes.length,coefficient_cells:stats.coefficient_cells},construction:stats};
}
function openAPColorings(raw,options={}){
 if(typeof raw==="string"){if(raw.length>32000000)fail("snapshot text limit");raw=JSON.parse(raw);}const s=copy(raw);if(!s||s.schema!==SCHEMA||s.version!==VERSION)fail("wrong snapshot schema");
 const n=integer(s.input.n,2,24,"n"),k=integer(s.input.length,2,n,"progression length"),full=2**n-1,maxConditionStates=integer(options.max_condition_states===undefined?500000:options.max_condition_states,1,1000000,"max_condition_states");
 if(!Array.isArray(s.nodes)||s.nodes.length<1||s.nodes.length>500000||!Array.isArray(s.progressions)||s.progressions.length>1000)fail("invalid saved arrays");integer(s.root,0,s.nodes.length-1,"root");if(s.nodes[s.root].level!==0)fail("invalid root level");
 let coeffCells=0;const coeff=s.nodes.map((v,id)=>{if(v.id!==id)fail("invalid node id");integer(v.level,0,n,"node level");if(!Array.isArray(v.forbidden)||v.forbidden.length!==2)fail("invalid residual family");for(const rows of v.forbidden){if(!Array.isArray(rows)||rows.length>s.progressions.length)fail("invalid residual masks");let last=-1;for(const m of rows){integer(m,1,full,"residual mask");if(m<=last||m%(2**v.level)!==0)fail("unordered or assigned residual bit");last=m;}}if(!Array.isArray(v.coefficients)||v.coefficients.length!==n-v.level+1)fail("invalid coefficient length");coeffCells+=v.coefficients.length;if(coeffCells>2000000)fail("coefficient cell cap");return v.coefficients.map(x=>{if(typeof x!=="string"||! /^(0|[1-9][0-9]*)$/.test(x)||x.length>100)fail("invalid coefficient");return BigInt(x);});});
 for(const v of s.nodes){if(!Array.isArray(v.arcs)||v.arcs.length!==(v.level===n?0:2))fail("invalid branch count");if(v.level===n&&(v.forbidden.some(a=>a.length)||v.coefficients[0]!=="1"))fail("invalid terminal");for(let c=0;c<v.arcs.length;c++){const a=v.arcs[c];if(a.color!==c)fail("branch order");if(a.child===-1){if(!a.rejection||a.rejection.color!==c||a.rejection.position!==v.level+1||a.rejection.mask!==2**v.level||!v.forbidden[c].includes(a.rejection.mask))fail("invalid singleton rejection");}else{integer(a.child,0,s.nodes.length-1,"child");if(s.nodes[a.child].level!==v.level+1||!Array.isArray(a.discarded))fail("invalid child");for(const d of a.discarded){integer(d.color,0,1,"discard color");integer(d.mask,1,full,"discard mask");integer(d.by,1,full,"subset witness");if((d.by&d.mask)!==d.by||!s.nodes[a.child].forbidden[d.color].includes(d.by))fail("invalid subsumption witness");}}}}
 for(let id=0;id<s.progressions.length;id++){const e=s.progressions[id];if(e.id!==id||!Array.isArray(e.vertices)||e.vertices.length!==k)fail("invalid progression row");let mask=0;for(let j=0;j<e.vertices.length;j++){const x=integer(e.vertices[j],1,n,"progression vertex");if(j&&x<=e.vertices[j-1])fail("unordered progression");mask+=2**(x-1);}if(mask!==e.mask)fail("saved progression mask mismatch");}
 const stats={opened_nodes:s.nodes.length,opened_coefficients:coeffCells,opened_progressions:s.progressions.length,queries:0,conditioning_states:0,conditioning_cache_hits:0,saved_coefficient_lookups:0,selection_steps:0,rank_steps:0,source_progression_checks:0,new_progressions_generated:0,new_residual_states:0,new_subsumption_comparisons:0,new_base_coefficients:0};
 const contexts=new Map();function fixedInput(fixed){if(!Array.isArray(fixed)||fixed.length>n)fail("fixed assignments array required");const a=fixed.map(v=>{if(!Array.isArray(v)||v.length!==2)fail("fixed pair required");return[integer(v[0],1,n,"position"),integer(v[1],0,1,"color")];}).sort((a,b)=>a[0]-b[0]);for(let i=1;i<a.length;i++)if(a[i][0]===a[i-1][0])fail("duplicate fixed position");return a;}
 function getContext(fixed=[],ones=null){
  const a=fixedInput(fixed);if(ones!==null)integer(ones,0,n,"ones");const key=JSON.stringify([a,ones]);if(contexts.has(key)){stats.conditioning_cache_hits++;return contexts.get(key);}if(contexts.size>=64)fail("conditioning context cap");
  const map=new Map(a),last=a.length?a[a.length-1][0]:0,memo=new Map(),rows=[];
  function C(id,t){if(id<0||t!==null&&(t<0||t>n-s.nodes[id].level))return 0n;const key=id+":"+(t===null?"*":t);if(memo.has(key))return memo.get(key);if(stats.conditioning_states>=maxConditionStates)fail("conditioning state budget exhausted");stats.conditioning_states++;const v=s.nodes[id];let result,kind;
   if(v.level>=last){stats.saved_coefficient_lookups++;result=t===null?coeff[id].reduce((z,x)=>z+x,0n):coeff[id][t];kind="saved_coefficient";}
   else{kind="conditioned_branch";const forced=map.get(v.level+1);result=0n;for(const arc of v.arcs)if(forced===undefined||forced===arc.color)result+=C(arc.child,t===null?null:t-arc.color);}
   memo.set(key,result);rows.push({node:id,remaining_ones:t,count:result.toString(),kind});return result;
  }
  const ctx={fixed:a,ones,total:C(s.root,ones),map,C,rows};contexts.set(key,ctx);return ctx;
 }
 function wordInput(word){if(typeof word!=="string"||word.length!==n||! /^[01]+$/.test(word))fail("complete binary word required");return word;}
 function witness(word,last){for(const e of s.progressions){stats.source_progression_checks++;if(e.vertices[e.vertices.length-1]>last)continue;const c=word[e.vertices[0]-1];if(e.vertices.every(x=>word[x-1]===c))return{progression_id:e.id,vertices:e.vertices.slice(),color:Number(c)};}return null;}
 function select(ctx,rank){let r=rankValue(rank);if(r>=ctx.total)fail("rank outside conditioned family");const original=r,idStart=s.root,trace=[];let id=idStart,t=ctx.ones,word="";
  while(s.nodes[id].level<n){const v=s.nodes[id],pos=v.level+1,forced=ctx.map.get(pos),zero=forced===1?0n:ctx.C(v.arcs[0].child,t),before=r;let c;if(forced!==undefined)c=forced;else if(r<zero)c=0;else{c=1;r-=zero;}const arc=v.arcs[c];if(arc.child<0)fail("saved counts select rejection");if(t!==null)t-=c;trace.push({position:pos,node:id,color:c,zero_count:zero.toString(),rank_before:before.toString(),rank_after:r.toString(),child:arc.child});word+=c;id=arc.child;stats.selection_steps++;}
  if(r!==0n||t!==null&&t!==0)fail("saved counts fail terminal rank");return{rank:original.toString(),word,ones:[...word].filter(c=>c==="1").length,fixed:copy(ctx.fixed),required_ones:ctx.ones,trace};
 }
 function rank(ctx,word){word=wordInput(word);const actual=[...word].filter(c=>c==="1").length;if(ctx.ones!==null&&actual!==ctx.ones)return{valid:false,reason:"color count"};for(const [pos,c]of ctx.fixed)if(Number(word[pos-1])!==c)return{valid:false,reason:"fixed position",position:pos};let id=s.root,t=ctx.ones,r=0n;const trace=[];
  while(s.nodes[id].level<n){const v=s.nodes[id],pos=v.level+1,c=Number(word[pos-1]),forced=ctx.map.get(pos);let skipped=0n;if(c===1&&forced===undefined){skipped=ctx.C(v.arcs[0].child,t);r+=skipped;}const arc=v.arcs[c];stats.rank_steps++;trace.push({position:pos,node:id,color:c,skipped:skipped.toString(),child:arc.child});if(arc.child<0)return{valid:false,reason:"monochromatic progression",failed_position:pos,witness:witness(word,pos),trace};id=arc.child;if(t!==null)t-=c;}
  return{valid:true,rank:r.toString(),word,ones:actual,fixed:copy(ctx.fixed),required_ones:ctx.ones,trace};
 }
 function page(rows,start=0,limit=32){integer(start,0,rows.length,"start");integer(limit,0,64,"limit");return{start,total:rows.length,rows:copy(rows.slice(start,start+limit)),next:start+limit<rows.length?start+limit:null};}
 return Object.freeze({
  summary(){stats.queries++;return copy(s.summary);},
  progressionsPage(start=0,limit=32){stats.queries++;return page(s.progressions,start,limit);},
  nodesPage(start=0,limit=32){stats.queries++;return page(s.nodes,start,limit);},
  node(id){stats.queries++;integer(id,0,s.nodes.length-1,"node");return copy(s.nodes[id]);},
  countFixed(fixed=[],ones=null){stats.queries++;const c=getContext(fixed,ones);return{fixed:copy(c.fixed),ones:c.ones,count:c.total.toString()};},
  countPrefix(bits,ones=null){stats.queries++;if(typeof bits!=="string"||bits.length>n||! /^[01]*$/.test(bits))fail("invalid prefix");const c=getContext([...bits].map((x,i)=>[i+1,Number(x)]),ones);return{prefix:bits,ones:c.ones,count:c.total.toString()};},
  selectFixed(fixed,ones,rank){stats.queries++;return select(getContext(fixed,ones),rank);},
  rankFixed(word,fixed=[],ones=null){stats.queries++;return rank(getContext(fixed,ones),word);},
  conditioningData(fixed=[],ones=null){stats.queries++;const c=getContext(fixed,ones);return{schema:"commons.ap-coloring-conditioning.v1",fixed:copy(c.fixed),ones:c.ones,total:c.total.toString(),rows:copy(c.rows)};},
  statistics(){return copy(stats);}
 });
}
module.exports={VERSION,compileAPColorings,openAPColorings};
