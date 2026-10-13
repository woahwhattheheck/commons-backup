"use strict";
const SCHEMA="erdos671.finite_lebesgue/v1";
const LIMITS=Object.freeze({max_nodes:16,max_abs_integer_node:1000000,max_splits:512,
  max_depth:48,max_fraction_digits:4096,max_input_digits:1024,max_snapshot_chars:16000000,max_page_size:64,max_cached_points:256});
function fail(s){throw new Error("lagrange_lebesgue: "+s);}
function copy(v){return JSON.parse(JSON.stringify(v));}
function abs(x){return x<0n?-x:x;}
function natural(v,max,label){if(!Number.isSafeInteger(v)||v<0||v>max)fail(label+" out of range");return v;}
function arithmetic(work){
  function gcd(a,b){work.gcd_calls++;a=abs(a);b=abs(b);while(b){const t=a%b;a=b;b=t;}return a;}
  function R(n,d=1n){
    if(d===0n)fail("zero denominator");if(d<0n){n=-n;d=-d;}
    const g=gcd(n,d);n/=g;d/=g;
    if(String(abs(n)).length>LIMITS.max_fraction_digits||String(d).length>LIMITS.max_fraction_digits)fail("fraction digit budget exceeded");
    return [n,d];
  }
  function parse(v){
    if(!Array.isArray(v)||v.length!==2)fail("rational must be [numerator,denominator]");
    const z=v.map((a,i)=>{
      if(typeof a==="number"){if(!Number.isSafeInteger(a))fail("inexact rational number");a=String(a);}
      else if(typeof a==="bigint")a=String(a);
      if(typeof a!=="string"||! /^-?(0|[1-9][0-9]*)$/.test(a)||a==="-0"||a.replace("-","").length>LIMITS.max_input_digits)
        fail("rational input integer format");
      return BigInt(a);
    });
    if(z[1]<=0n)fail("denominator must be positive");return R(z[0],z[1]);
  }
  function cmp(a,b){work.rational_comparisons++;const d=a[0]*b[1]-b[0]*a[1];return d<0n?-1:d>0n?1:0;}
  function add(a,b){work.rational_additions++;return R(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);}
  function sub(a,b){return add(a,[-b[0],b[1]]);}
  function mul(a,b){work.rational_multiplications++;return R(a[0]*b[0],a[1]*b[1]);}
  function div(a,b){work.rational_divisions++;return R(a[0]*b[1],a[1]*b[0]);}
  function pack(a){return a.map(String);}
  function common(nums,den){
    let g=den;for(const x of nums)g=gcd(g,x);
    const v=nums.map(x=>x/g),d=den/g;
    if(v.some(x=>String(abs(x)).length>LIMITS.max_fraction_digits)||String(d).length>LIMITS.max_fraction_digits)fail("coefficient digit budget");
    return {nums:v,den:d};
  }
  return {gcd,R,parse,cmp,add,sub,mul,div,pack,common};
}
function newWork(){return {gcd_calls:0,rational_comparisons:0,rational_additions:0,
  rational_multiplications:0,rational_divisions:0,cardinal_polynomials_constructed:0,
  root_factor_updates:0,piece_polynomials_constructed:0,power_to_bernstein_terms:0,
  subdivision_additions:0,subdivision_calls:0,leaf_upper_comparisons:0,cardinal_horner_steps:0,
  saved_cardinal_evaluations:0,cardinal_cache_hits:0,queries:0};}
function integerNodes(values){
  if(!Array.isArray(values)||values.length<2||values.length>LIMITS.max_nodes)fail("node count must be 2..16");
  for(let i=0;i<values.length;i++){
    if(!Number.isSafeInteger(values[i])||Math.abs(values[i])>LIMITS.max_abs_integer_node||
       (i&&values[i]<=values[i-1]))fail("integer coordinates must be bounded and strictly increasing");
  }return values.map(BigInt);
}
function compileLebesgue(values,options={}){
  const b=integerNodes(values),n=b.length,d=n-1,work=newWork(),a=arithmetic(work),{R,cmp,add,sub,mul,div,pack}=a;
  const maxSplits=options.max_splits===undefined?128:natural(options.max_splits,LIMITS.max_splits,"split budget");
  const tolerance=a.parse(options.tolerance===undefined?["1","1000000"]:options.tolerance);
  if(tolerance[0]<=0n)fail("tolerance must be positive");
  const sourceId=options.source_id===undefined?"caller-supplied integer nodes":options.source_id;
  if(typeof sourceId!=="string"||sourceId.length>2048)fail("source_id format");
  const width=b[d]-b[0],center=b[d]+b[0];
  const normalize=z=>div(sub(mul(R(2n),z),R(center)),R(width));
  const cardinal=[];
  for(let i=0;i<n;i++){
    let c=[1n],den=1n;
    for(let j=0;j<n;j++)if(j!==i){
      const next=Array(c.length+1).fill(0n);
      for(let k=0;k<c.length;k++){next[k]-=b[j]*c[k];next[k+1]+=c[k];work.root_factor_updates++;}
      c=next;den*=b[i]-b[j];
    }
    if(den<0n){den=-den;c=c.map(x=>-x);}
    cardinal.push({numerators:c,denominator:den});work.cardinal_polynomials_constructed++;
  }
  let commonDen=1n;for(const c of cardinal)commonDen=commonDen/a.gcd(commonDen,c.denominator)*c.denominator;
  const choose=Array.from({length:n},()=>[]);
  for(let i=0;i<=d;i++){choose[i][0]=choose[i][i]=1n;for(let j=1;j<i;j++)choose[i][j]=choose[i-1][j-1]+choose[i-1][j];}
  let bernScale=1n;for(let j=0;j<=d;j++)bernScale=bernScale/a.gcd(bernScale,choose[d][j])*choose[d][j];
  const pieces=[],nodes=[],roots=[],leaves=[],steps=[];
  let bestValue=R(1n),bestZ=R(b[0]);
  function consider(value,z){if(cmp(value,bestValue)>0){bestValue=value;bestZ=z;}}
  function makeNode(piece,parent,depth,lo,hi,nums,den){
    const normalized=a.common(nums,den);nums=normalized.nums;den=normalized.den;
    let mx=nums[0];for(const x of nums)if(x>mx)mx=x;
    const node={id:nodes.length,piece,parent,depth,lo,hi,nums,den,upper:R(mx,den),children:null};
    nodes.push(node);consider(R(nums[0],den),lo);consider(R(nums[d],den),hi);return node.id;
  }
  for(let k=0;k<d;k++){
    const signs=Array.from({length:n},(_,i)=>(k+i+(i>k?1:0))%2===0?1:-1);
    let coeff=Array(n).fill(0n);
    for(let i=0;i<n;i++){const scale=BigInt(signs[i])*(commonDen/cardinal[i].denominator);
      for(let j=0;j<=d;j++)coeff[j]+=scale*cardinal[i].numerators[j];}
    const normalized=a.common(coeff,commonDen);coeff=normalized.nums;const den=normalized.den;
    const lo=b[k],w=b[k+1]-lo,local=[];
    for(let j=0;j<=d;j++){
      let v=0n;for(let q=j;q<=d;q++)v+=coeff[q]*choose[q][j]*(lo**BigInt(q-j));
      local.push(v*(w**BigInt(j)));
    }
    const bern=[];
    for(let i=0;i<=d;i++){
      let v=0n;for(let j=0;j<=i;j++){v+=local[j]*choose[i][j]*(bernScale/choose[d][j]);work.power_to_bernstein_terms++;}
      bern.push(v);
    }
    pieces.push({index:k,lo:String(lo),hi:String(b[k+1]),signs,coefficients:coeff.map(String),denominator:String(den)});
    const id=makeNode(k,null,0,R(lo),R(b[k+1]),bern,den*bernScale);roots.push(id);leaves.push(id);work.piece_polynomials_constructed++;
  }
  function largestLeaf(){
    let pos=0;for(let i=1;i<leaves.length;i++){work.leaf_upper_comparisons++;
      if(cmp(nodes[leaves[i]].upper,nodes[leaves[pos]].upper)>0)pos=i;}return pos;
  }
  function record(step,splitNode,children){
    const pos=largestLeaf(),top=nodes[leaves[pos]];
    const row={step,split_node:splitNode,children,lower:pack(bestValue),upper:pack(top.upper),
      best_z:pack(bestZ),best_x:pack(normalize(bestZ)),upper_node:top.id,gap:pack(sub(top.upper,bestValue))};
    steps.push(row);return {pos,top,row};
  }
  let state=record(0,null,[]),status;
  while(true){
    if(cmp(sub(state.top.upper,bestValue),tolerance)<=0){status="TOLERANCE_MET";break;}
    if(work.subdivision_calls>=maxSplits){status="SPLIT_BUDGET";break;}
    const parent=state.top;if(parent.depth>=LIMITS.max_depth){status="DEPTH_BUDGET";break;}
    const left=[],right=[];let row=parent.nums.slice();
    for(let level=0;level<=d;level++){
      const factor=1n<<BigInt(d-level);left[level]=row[0]*factor;right[d-level]=row[row.length-1]*factor;
      if(level<d){const next=[];for(let i=0;i<row.length-1;i++){next.push(row[i]+row[i+1]);work.subdivision_additions++;}row=next;}
    }
    const mid=div(add(parent.lo,parent.hi),R(2n)),den=parent.den*(1n<<BigInt(d));
    const l=makeNode(parent.piece,parent.id,parent.depth+1,parent.lo,mid,left,den);
    const r=makeNode(parent.piece,parent.id,parent.depth+1,mid,parent.hi,right,den);
    parent.children=[l,r];leaves.splice(state.pos,1,l,r);work.subdivision_calls++;
    state=record(work.subdivision_calls,parent.id,[l,r]);
  }
  const snapshot={schema:SCHEMA,source_id:sourceId,integer_nodes:values.slice(),
    normalized_nodes:b.map(x=>pack(normalize(R(x)))),degree:d,
    coordinate_map:{z_min:String(b[0]),z_max:String(b[d]),x_from_z:"(2z-min-max)/(max-min)",domain:["-1","1"]},
    cardinal:cardinal.map((c,i)=>({index:i,numerators:c.numerators.map(String),denominator:String(c.denominator)})),
    pieces,roots,tree:nodes.map(v=>({id:v.id,piece:v.piece,parent:v.parent,depth:v.depth,z_lo:pack(v.lo),z_hi:pack(v.hi),
      bernstein_numerators:v.nums.map(String),denominator:String(v.den),upper:pack(v.upper),children:v.children})),
    leaves,steps,result:{status,lower:pack(bestValue),upper:pack(state.top.upper),gap:pack(sub(state.top.upper,bestValue)),
      best_z:pack(bestZ),best_x:pack(normalize(bestZ)),upper_node:state.top.id,tolerance:pack(tolerance)},
    options:{max_splits:maxSplits,max_depth:LIMITS.max_depth},work,
    scope:"One finite interpolation row. Sampled lower bound and full-partition upper bound; no infinite-row convergence conclusion."};
  if(JSON.stringify(snapshot).length>LIMITS.max_snapshot_chars)fail("snapshot character budget");
  return snapshot;
}
function openLebesgue(input){
  const text=typeof input==="string"?input:JSON.stringify(input);
  if(text.length>LIMITS.max_snapshot_chars)fail("snapshot character budget");
  const s=JSON.parse(text);if(!s||s.schema!==SCHEMA)fail("schema mismatch");
  const b=integerNodes(s.integer_nodes),n=b.length,d=n-1,work=newWork(),a=arithmetic(work),{R,cmp,add,sub,mul,div,pack}=a;
  function savedInt(x,positive=false){
    if(typeof x!=="string"||! /^-?(0|[1-9][0-9]*)$/.test(x)||x==="-0"||x.replace("-","").length>LIMITS.max_fraction_digits)
      fail("saved integer format");const v=BigInt(x);if(positive&&v<=0n)fail("saved denominator");return v;
  }
  function savedR(x){if(!Array.isArray(x)||x.length!==2)fail("saved rational shape");return [savedInt(x[0]),savedInt(x[1],true)];}
  function polynomial(r){if(!Array.isArray(r.numerators)||r.numerators.length!==n)fail("cardinal dimensions");
    return {nums:r.numerators.map(x=>savedInt(x)),den:savedInt(r.denominator,true)};}
  if(s.degree!==d||!Array.isArray(s.cardinal)||s.cardinal.length!==n||
     !Array.isArray(s.pieces)||s.pieces.length!==d||!Array.isArray(s.normalized_nodes)||s.normalized_nodes.length!==n)
    fail("row dimensions");
  const cardinal=s.cardinal.map(polynomial),knots=s.normalized_nodes.map(savedR);
  if(!Array.isArray(s.tree)||s.tree.length<d||s.tree.length>d+2*LIMITS.max_splits||
     !Array.isArray(s.leaves)||!Array.isArray(s.roots)||s.roots.length!==d||!Array.isArray(s.steps))fail("tree dimensions");
  const parsedNodes=s.tree.map((v,i)=>{
    if(v.id!==i)fail("node identity");natural(v.piece,d-1,"piece index");natural(v.depth,LIMITS.max_depth,"depth");
    if(v.parent!==null)natural(v.parent,i-1,"parent reference");
    if(!Array.isArray(v.bernstein_numerators)||v.bernstein_numerators.length!==n)fail("Bernstein dimensions");
    v.bernstein_numerators.forEach(x=>savedInt(x));savedInt(v.denominator,true);
    if(v.children!==null){if(!Array.isArray(v.children)||v.children.length!==2)fail("children shape");
      v.children.forEach(x=>natural(x,s.tree.length-1,"child reference"));}
    return {lo:savedR(v.z_lo),hi:savedR(v.z_hi),upper:savedR(v.upper)};
  });
  s.roots.forEach(x=>natural(x,s.tree.length-1,"root reference"));
  const seen=new Set();for(const x of s.leaves){natural(x,s.tree.length-1,"leaf reference");if(seen.has(x)||s.tree[x].children!==null)fail("leaf structure");seen.add(x);}
  const lower=savedR(s.result.lower),upper=savedR(s.result.upper),bestX=savedR(s.result.best_x);
  if(cmp(lower,upper)>0)fail("bound order");
  const width=b[d]-b[0],center=b[d]+b[0],cache=new Map();
  function weights(x){
    const key=pack(x).join("/");if(cache.has(key)){work.cardinal_cache_hits++;return cache.get(key);}
    const z=div(add(mul(R(width),x),R(center)),R(2n)),w=[];
    for(const c of cardinal){let y=R(c.nums[d]);for(let j=d-1;j>=0;j--){y=add(mul(y,z),R(c.nums[j]));work.cardinal_horner_steps++;}
      w.push(div(y,R(c.den)));}
    let lambda=R(0n);for(const v of w)lambda=add(lambda,[abs(v[0]),v[1]]);
    const item={x,z,weights:w,lambda};if(cache.size>=LIMITS.max_cached_points)cache.delete(cache.keys().next().value);
    cache.set(key,item);work.saved_cardinal_evaluations++;return item;
  }
  function xInput(v){const x=a.parse(v);if(cmp(x,R(-1n))<0||cmp(x,R(1n))>0)fail("x outside [-1,1]");return x;}
  function page(array,start,count){natural(start,array.length,"page start");natural(count,LIMITS.max_page_size,"page count");
    const end=Math.min(start+count,array.length);return {start,rows:copy(array.slice(start,end)),next_index:end,end:end===array.length};}
  function scaledDecimal(q,places,up){
    const scale=10n**BigInt(places),num=q[0]*scale,den=q[1];
    let v=num/den;if(num%den!==0n){if(up&&num>0n)v++;if(!up&&num<0n)v--;}
    const sign=v<0n?"-":"",digits=String(abs(v)).padStart(places+1,"0");
    return sign+(places?digits.slice(0,-places)+"."+digits.slice(-places):digits);
  }
  return Object.freeze({
    summary(){work.queries++;return {schema:SCHEMA,source_id:s.source_id,integer_nodes:s.integer_nodes.slice(),
      normalized_nodes:copy(s.normalized_nodes),degree:d,pieces:d,tree_nodes:s.tree.length,leaves:s.leaves.length,
      subdivision_calls:s.work.subdivision_calls,result:copy(s.result),loader:"Structural only; coefficients, partition completeness and bound derivation are not replayed."};},
    bounds(places=8){work.queries++;natural(places,100,"decimal places");return {lower:pack(lower),upper:pack(upper),
      decimal_lower:scaledDecimal(lower,places,false),decimal_upper:scaledDecimal(upper,places,true),
      best_x:pack(bestX),status:s.result.status};},
    evaluate(x){work.queries++;const r=weights(xInput(x));return {x:pack(r.x),z:pack(r.z),cardinal_values:r.weights.map(pack),lebesgue_value:pack(r.lambda)};},
    interpolate(x,values){work.queries++;if(!Array.isArray(values)||values.length!==n)fail("nodal value count");
      const v=values.map(a.parse),r=weights(xInput(x));let y=R(0n);for(let i=0;i<n;i++)y=add(y,mul(v[i],r.weights[i]));
      return {x:pack(r.x),nodal_values:v.map(pack),interpolated_value:pack(y)};},
    nodalWitness(x){work.queries++;const r=weights(xInput(x)),v=r.weights.map(w=>w[0]<0n?-1n:1n),segments=[];
      for(let i=0;i<d;i++){
        const slope=div(R(v[i+1]-v[i]),sub(knots[i+1],knots[i]));
        const intercept=sub(R(v[i]),mul(slope,knots[i]));
        segments.push({interval:[pack(knots[i]),pack(knots[i+1])],slope:pack(slope),intercept:pack(intercept)});
      }
      return {x:pack(r.x),nodal_values:v.map(t=>[String(t),"1"]),cardinal_values:r.weights.map(pack),
        continuous_piecewise_linear_segments:segments,input_sup_norm:["1","1"],
        interpolated_at_x:pack(r.lambda),global_output_norm_lower_bound:pack(r.lambda),
        global_output_norm_upper_bound:pack(upper),global_maximizer_asserted:false};},
    nodePage(start=0,count=32){work.queries++;return page(s.tree,start,count);},
    piecePage(start=0,count=32){work.queries++;return page(s.pieces,start,count);},
    stepPage(start=0,count=32){work.queries++;return page(s.steps,start,count);},
    leafPage(start=0,count=32){work.queries++;return page(s.leaves.map(i=>s.tree[i]),start,count);},
    stats(){return {...copy(work),saved_nodes_structurally_read:parsedNodes.length,cache_entries:cache.size};},
    snapshot(){return copy(s);}
  });
}
module.exports={SCHEMA,LIMITS,compileLebesgue,openLebesgue};
