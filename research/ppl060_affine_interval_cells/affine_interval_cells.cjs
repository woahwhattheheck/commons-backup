"use strict";
const VERSION="1.0.0",SCHEMA="commons.affine-interval-cells.v1";
function fail(s){throw new Error(s);}
function gcd(a,b){a=a<0n?-a:a;while(b){const t=a%b;a=b;b=t;}return a;}
function R(n,d=1n){if(d===0n)fail("zero denominator");if(d<0n){n=-n;d=-d;}const g=gcd(n,d);return[n/g,d/g];}
const Z=[0n,1n],ONE=[1n,1n];
function parse(x){if(typeof x==="number"){if(!Number.isSafeInteger(x))fail("rational number must be a safe integer");x=String(x);}if(typeof x!=="string"||x.length>8200||! /^-?(?:0|[1-9][0-9]*)(?:\/[1-9][0-9]*)?$/.test(x))fail("invalid rational");const a=x.split("/");if(a.some(y=>y.replace("-","").length>4096))fail("rational input digit limit");return R(BigInt(a[0]),a[1]?BigInt(a[1]):1n);}
function str(a){const n=String(a[0]),d=String(a[1]);if(n.replace("-","").length>4096||d.length>4096)fail("rational output digit budget exhausted");return a[1]===1n?n:n+"/"+d;}
function inputRat(x){const a=parse(x);if(String(a[0]).replace("-","").length>80||String(a[1]).length>80)fail("input rational digit limit 80");return a;}
function add(a,b){return R(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);}
function neg(a){return[-a[0],a[1]];}
function sub(a,b){return add(a,neg(b));}
function mul(a,b){return R(a[0]*b[0],a[1]*b[1]);}
function div(a,b){if(b[0]===0n)fail("division by zero");return R(a[0]*b[1],a[1]*b[0]);}
function cmp(a,b){const x=a[0]*b[1]-b[0]*a[1];return x<0n?-1:x>0n?1:0;}
function eqp(a,b){return cmp(a[0],b[0])===0&&cmp(a[1],b[1])===0;}
function lex(a,b){return cmp(a[0],b[0])||cmp(a[1],b[1]);}
function cross(a,b,c){return sub(mul(sub(b[0],a[0]),sub(c[1],a[1])),mul(sub(b[1],a[1]),sub(c[0],a[0])));}
function area2(p){let a=Z;for(let i=0;i<p.length;i++){const q=p[(i+1)%p.length];a=add(a,sub(mul(p[i][0],q[1]),mul(p[i][1],q[0])));}return a;}
function normalize(p){let q=[];for(const v of p)if(!q.length||!eqp(q[q.length-1],v))q.push(v);if(q.length>1&&eqp(q[0],q[q.length-1]))q.pop();if(q.length<2)return q;const a=area2(q);if(a[0]===0n){q.sort(lex);return eqp(q[0],q[q.length-1])?[q[0]]:[q[0],q[q.length-1]];}if(a[0]<0n)q.reverse();let changed=true;while(changed&&q.length>3){changed=false;for(let i=0;i<q.length;i++){if(cross(q[(i+q.length-1)%q.length],q[i],q[(i+1)%q.length])[0]===0n){q.splice(i,1);changed=true;break;}}}let k=0;for(let i=1;i<q.length;i++)if(lex(q[i],q[k])<0)k=i;return q.slice(k).concat(q.slice(0,k));}
function serialize(p){return p.map(v=>v.map(str));}
function deserialize(p){return p.map(v=>v.map(parse));}
function dim(p){return p.length===0?-1:p.length===1?0:area2(p)[0]===0n?1:2;}
function area(p){const a=area2(p);return R(a[0]<0n?-a[0]:a[0],a[1]*2n);}
function extent(p,k){let lo=p[0][k],hi=lo;for(const v of p){if(cmp(v[k],lo)<0)lo=v[k];if(cmp(v[k],hi)>0)hi=v[k];}return[lo,hi];}
function clip(p,A,B,C,stats){if(stats)stats.halfplane_clips++;if(!p.length)return{polygon:[],minimum:null,minimum_vertex:null};const f=p.map(v=>sub(add(mul(A,v[0]),mul(B,v[1])),C));if(stats)stats.vertex_inequality_evaluations+=p.length;let k=0;for(let i=1;i<f.length;i++)if(cmp(f[i],f[k])<0)k=i;if(f[k][0]>0n)return{polygon:[],minimum:f[k],minimum_vertex:k};let out=[];for(let i=0;i<p.length;i++){const j=(i+1)%p.length,inside=f[i][0]<=0n,next=f[j][0]<=0n;if(inside)out.push(p[i]);if(inside!==next){const t=div(f[i],sub(f[i],f[j]));out.push([add(p[i][0],mul(t,sub(p[j][0],p[i][0]))),add(p[i][1],mul(t,sub(p[j][1],p[i][1])))]);if(stats)stats.new_edge_intersections++;}}return{polygon:normalize(out),minimum:f[k],minimum_vertex:k};}
function boundInteger(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside limits");return x;}
function inputOf(input){if(!input||!Array.isArray(input.pattern)||input.pattern.length<1||input.pattern.length>16)fail("pattern size 1..16 required");const pattern=input.pattern.map(inputRat);for(let i=1;i<pattern.length;i++)if(cmp(pattern[i-1],pattern[i])>=0)fail("pattern must be strictly increasing");if(!Array.isArray(input.intervals)||input.intervals.length<1||input.intervals.length>6)fail("1..6 target intervals required");const intervals=input.intervals.map(a=>{if(!Array.isArray(a)||a.length!==2)fail("interval pair required");return a.map(inputRat);});for(let i=0;i<intervals.length;i++){if(cmp(intervals[i][0],intervals[i][1])>=0)fail("target intervals must have positive length");if(i&&cmp(intervals[i-1][1],intervals[i][0])>=0)fail("closed target intervals must be strictly separated and ordered");}if(!Array.isArray(input.scale)||input.scale.length!==2||!Array.isArray(input.translation)||input.translation.length!==2)fail("parameter bounds required");const scale=input.scale.map(inputRat),translation=input.translation.map(inputRat);if(cmp(scale[0],Z)<=0||cmp(scale[0],scale[1])>0||cmp(translation[0],translation[1])>0)fail("positive ordered scale and ordered translation bounds required");return{pattern,intervals,scale,translation};}
function unionIntervals(rows){const q=rows.map(a=>a.slice()).sort((a,b)=>cmp(a[0],b[0])||cmp(a[1],b[1])),out=[];for(const v of q){const last=out[out.length-1];if(!last||cmp(v[0],last[1])>0)out.push(v.slice());else if(cmp(v[1],last[1])>0)last[1]=v[1];}return out;}
function compileAffineIntervals(input,options={}){
 const v=inputOf(input),maxNodes=boundInteger(options.max_nodes===undefined?20000:options.max_nodes,1,30000,"max_nodes"),maxBranches=boundInteger(options.max_branches===undefined?100000:options.max_branches,1,200000,"max_branches");
 const stats={accepted_prefix_nodes:1,attempted_branches:0,rejected_lower:0,rejected_upper:0,halfplane_clips:0,vertex_inequality_evaluations:0,new_edge_intersections:0,final_cells:0,old_subset_sums_recomputed:0};
 const root=normalize([[v.scale[0],v.translation[0]],[v.scale[1],v.translation[0]],[v.scale[1],v.translation[1]],[v.scale[0],v.translation[1]]]);
 const nodes=[{id:0,parent:null,point_index:-1,interval:null,polygon:root,branches:[]}],branches=[];let frontier=[0];
 for(let k=0;k<v.pattern.length;k++){const next=[];for(const parent of frontier){const pn=nodes[parent],first=pn.interval===null?0:pn.interval;for(let j=first;j<v.intervals.length;j++){
  if(branches.length>=maxBranches)fail("branch budget exhausted; no final snapshot");
  const id=branches.length,row={id,parent,point_index:k,interval:j,child:null};branches.push(row);pn.branches.push(id);stats.attempted_branches++;
  const lower=clip(pn.polygon,neg(v.pattern[k]),neg(ONE),neg(v.intervals[j][0]),stats);
  if(!lower.polygon.length){row.rejection={half:"lower",minimum:str(lower.minimum),minimum_vertex:lower.minimum_vertex};stats.rejected_lower++;continue;}
  const upper=clip(lower.polygon,v.pattern[k],ONE,v.intervals[j][1],stats);
  if(!upper.polygon.length){row.rejection={half:"upper",minimum:str(upper.minimum),minimum_vertex:upper.minimum_vertex,lower_polygon:serialize(lower.polygon)};stats.rejected_upper++;continue;}
  if(nodes.length>=maxNodes)fail("node budget exhausted; no final snapshot");
  const child=nodes.length;row.child=child;nodes.push({id:child,parent,point_index:k,interval:j,polygon:upper.polygon,branches:[]});next.push(child);stats.accepted_prefix_nodes++;
 }}frontier=next;}
 const assignment=id=>{const a=[];while(id){a.push(nodes[id].interval);id=nodes[id].parent;}return a.reverse();};
 let total=Z;const counts=[0,0,0],cells=frontier.map((node,id)=>{const p=nodes[node].polygon,d=dim(p),a=area(p);total=add(total,a);counts[d]++;return{id,node,assignment:assignment(node),dimension:d,area:str(a),scale:extent(p,0).map(str),translation:extent(p,1).map(str)};});stats.final_cells=cells.length;
 const projection=unionIntervals(frontier.map(id=>extent(nodes[id].polygon,0))),domain=mul(sub(v.scale[1],v.scale[0]),sub(v.translation[1],v.translation[0]));let largest=null,largestIds=[];for(const c of cells){const z=parse(c.scale[1]);if(largest===null||cmp(z,largest)>0){largest=z;largestIds=[c.id];}else if(cmp(z,largest)===0)largestIds.push(c.id);}
 return{schema:SCHEMA,version:VERSION,input:{pattern:v.pattern.map(str),intervals:v.intervals.map(a=>a.map(str)),scale:v.scale.map(str),translation:v.translation.map(str),provenance:input.provenance===undefined?null:JSON.parse(JSON.stringify(input.provenance))},nodes:nodes.map(n=>({...n,polygon:serialize(n.polygon)})),branches,cells,summary:{pattern_size:v.pattern.length,target_intervals:v.intervals.length,target_measure:str(v.intervals.reduce((s,a)=>add(s,sub(a[1],a[0])),Z)),cell_count:cells.length,dimensions:counts,area:str(total),parameter_rectangle_area:str(domain),area_fraction:domain[0]===0n?null:str(div(total,domain)),scale_projection:projection.map(a=>a.map(str)),largest_scale:largest===null?null:str(largest),largest_scale_cell_ids:largestIds},construction:stats};
}
function copy(x){return JSON.parse(JSON.stringify(x));}
function openAffineIntervals(raw){
 if(typeof raw==="string"){if(raw.length>24000000)fail("snapshot text limit");raw=JSON.parse(raw);}const s=copy(raw);
 if(!s||s.schema!==SCHEMA||s.version!==VERSION)fail("wrong snapshot schema");const v=inputOf(s.input);
 if(!Array.isArray(s.nodes)||s.nodes.length<1||s.nodes.length>30000||!Array.isArray(s.branches)||s.branches.length>200000||!Array.isArray(s.cells))fail("invalid saved arrays");
 const polys=s.nodes.map((n,i)=>{if(n.id!==i||!Array.isArray(n.polygon)||n.polygon.length<1||n.polygon.length>2*v.pattern.length+8||!Array.isArray(n.branches))fail("invalid saved node");if(i===0){if(n.parent!==null||n.point_index!==-1||n.interval!==null)fail("invalid root");}else{if(!Number.isInteger(n.parent)||n.parent<0||n.parent>=i||!Number.isInteger(n.point_index)||n.point_index<0||n.point_index>=v.pattern.length||n.point_index!==s.nodes[n.parent].point_index+1||!Number.isInteger(n.interval)||n.interval<0||n.interval>=v.intervals.length||(s.nodes[n.parent].interval!==null&&n.interval<s.nodes[n.parent].interval))fail("invalid prefix links");}return deserialize(n.polygon);});
 const referenced=new Set();for(const n of s.nodes){const expected=n.point_index===v.pattern.length-1?0:v.intervals.length-(n.interval===null?0:n.interval);if(n.branches.length!==expected)fail("incomplete saved branch list");for(let q=0;q<n.branches.length;q++){const id=n.branches[q],b=s.branches[id];if(!b||b.id!==id||referenced.has(id)||b.parent!==n.id||b.point_index!==n.point_index+1||b.interval!==(n.interval===null?0:n.interval)+q)fail("invalid branch link");referenced.add(id);if(b.child!==null){const c=s.nodes[b.child];if(!c||c.parent!==n.id||c.point_index!==b.point_index||c.interval!==b.interval||b.rejection!==undefined)fail("invalid accepted branch");}else{if(!b.rejection||!["lower","upper"].includes(b.rejection.half)||parse(b.rejection.minimum)[0]<=0n)fail("invalid rejected branch");if(b.rejection.half==="upper"){if(!Array.isArray(b.rejection.lower_polygon)||!b.rejection.lower_polygon.length)fail("missing lower clipping evidence");deserialize(b.rejection.lower_polygon);}}}}
 if(referenced.size!==s.branches.length)fail("orphan branch");
 const leafIds=s.nodes.filter(n=>n.point_index===v.pattern.length-1).map(n=>n.id);if(s.cells.length!==leafIds.length)fail("incomplete cell list");
 for(let i=0;i<s.cells.length;i++){const c=s.cells[i];if(c.id!==i||c.node!==leafIds[i]||!Array.isArray(c.assignment)||c.assignment.length!==v.pattern.length||![0,1,2].includes(c.dimension))fail("invalid cell");let id=c.node;for(let k=v.pattern.length-1;k>=0;k--){if(c.assignment[k]!==s.nodes[id].interval)fail("invalid saved assignment");id=s.nodes[id].parent;}parse(c.area);c.scale.map(parse);c.translation.map(parse);}
 const stats={opened_nodes:s.nodes.length,opened_branches:s.branches.length,opened_cells:s.cells.length,queries:0,saved_cells_scanned:0,new_query_clips:0,new_query_edge_intersections:0,new_query_vertex_evaluations:0,new_affine_point_evaluations:0,new_subset_sums:0,new_assignment_branches:0,new_compiler_clips:0};
 function cid(i){return boundInteger(i,0,s.cells.length-1,"cell id");}
 function page(a,start=0,limit=32){boundInteger(start,0,a.length,"page start");boundInteger(limit,0,64,"page limit");return{start,total:a.length,rows:copy(a.slice(start,start+limit)),next:start+limit<a.length?start+limit:null};}
 function cutQuery(p,A,B,C){const t={halfplane_clips:0,vertex_inequality_evaluations:0,new_edge_intersections:0};const q=clip(p,A,B,C,t);stats.new_query_clips+=t.halfplane_clips;stats.new_query_vertex_evaluations+=t.vertex_inequality_evaluations;stats.new_query_edge_intersections+=t.new_edge_intersections;return q.polygon;}
 function fiber(axis,value){const z=parse(value),other=1-axis,rows=[];for(const c of s.cells){stats.saved_cells_scanned++;const p=polys[c.node],points=[];for(let i=0;i<p.length;i++){const j=(i+1)%p.length,a=p[i][axis],b=p[j][axis];if(cmp(a,z)===0)points.push(p[i][other]);if((cmp(a,z)<0&&cmp(b,z)>0)||(cmp(a,z)>0&&cmp(b,z)<0)){const t=div(sub(z,a),sub(b,a));points.push(add(p[i][other],mul(t,sub(p[j][other],p[i][other]))));stats.new_query_edge_intersections++;}}if(points.length){points.sort(cmp);rows.push({cell_id:c.id,assignment:c.assignment,interval:[str(points[0]),str(points[points.length-1])]});}}
 const merged=unionIntervals(rows.map(r=>r.interval.map(parse)));let measure=Z;for(const r of merged)measure=add(measure,sub(r[1],r[0]));return{axis:axis===0?"scale":"translation",value:str(z),rows:copy(rows),union:merged.map(a=>a.map(str)),measure:str(measure)};}
 return Object.freeze({
  summary(){stats.queries++;return copy(s.summary);},
  cellsPage(start=0,limit=32){stats.queries++;return page(s.cells,start,limit);},
  nodesPage(start=0,limit=32){stats.queries++;return page(s.nodes,start,limit);},
  branchesPage(start=0,limit=32){stats.queries++;return page(s.branches,start,limit);},
  cell(id){stats.queries++;id=cid(id);return{...copy(s.cells[id]),polygon:copy(s.nodes[s.cells[id].node].polygon)};},
  witness(id){stats.queries++;id=cid(id);const c=s.cells[id],p=polys[c.node],n=R(BigInt(p.length));let a=Z,b=Z;for(const t of p){a=add(a,t[0]);b=add(b,t[1]);}a=div(a,n);b=div(b,n);const images=v.pattern.map((x,k)=>{stats.new_affine_point_evaluations++;const y=add(mul(a,x),b),target=v.intervals[c.assignment[k]];return{point_index:k,point:str(x),image:str(y),interval:c.assignment[k],inside:cmp(y,target[0])>=0&&cmp(y,target[1])<=0};});return{cell_id:id,dimension:c.dimension,scale:str(a),translation:str(b),images};},
  locate(scale,translation){stats.queries++;const a=parse(scale),b=parse(translation);if(cmp(a,v.scale[0])<0||cmp(a,v.scale[1])>0||cmp(b,v.translation[0])<0||cmp(b,v.translation[1])>0)return{inside_domain:false,feasible:false};const assignment=[];for(let k=0;k<v.pattern.length;k++){stats.new_affine_point_evaluations++;const y=add(mul(a,v.pattern[k]),b);let j=-1;for(let t=0;t<v.intervals.length;t++)if(cmp(y,v.intervals[t][0])>=0&&cmp(y,v.intervals[t][1])<=0){j=t;break;}if(j<0)return{inside_domain:true,feasible:false,first_failed_point:k,image:str(y)};assignment.push(j);}for(const c of s.cells){stats.saved_cells_scanned++;if(c.assignment.every((x,k)=>x===assignment[k]))return{inside_domain:true,feasible:true,cell_id:c.id,assignment};}fail("saved snapshot missing feasible assignment");},
  translationFiber(scale){stats.queries++;return fiber(0,scale);},
  scaleFiber(translation){stats.queries++;return fiber(1,translation);},
  areaThrough(scale){stats.queries++;const z=parse(scale);let a=Z;const rows=[];for(const c of s.cells){stats.saved_cells_scanned++;if(c.dimension!==2)continue;const p=cutQuery(polys[c.node],ONE,Z,z),x=area(p);a=add(a,x);if(x[0]!==0n)rows.push({cell_id:c.id,area:str(x)});}return{through_scale:str(z),area:str(a),positive_cells:rows};},
  assignmentPrefix(prefix){stats.queries++;if(!Array.isArray(prefix)||prefix.length>v.pattern.length)fail("invalid assignment prefix");prefix.forEach((x,k)=>{boundInteger(x,0,v.intervals.length-1,"interval id");if(k&&x<prefix[k-1])fail("assignment prefix must be nondecreasing");});let a=Z;const ids=[];for(const c of s.cells){stats.saved_cells_scanned++;if(prefix.every((x,k)=>x===c.assignment[k])){ids.push(c.id);a=add(a,parse(c.area));}}return{prefix:prefix.slice(),cell_ids:ids,area:str(a)};},
  statistics(){return copy(stats);}
 });
}
module.exports={VERSION,compileAffineIntervals,openAffineIntervals};
